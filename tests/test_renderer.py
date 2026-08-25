"""
tests/test_renderer.py — updated for split-layout circular radar renderer
"""
from __future__ import annotations
import math
import pytest
from unittest.mock import MagicMock, patch
import pygame

from src.renderer import (
    TrailStore,
    Projector,
    LOCATIONS,
    DEFAULT_LOCATION,
    _lerp_colour,
    _plane_colour,
    _draw_trail,
    SPEED_FAST, SPEED_SLOW,
    C_PLANE, C_PLANE_FAST, C_PLANE_SLOW,
    C_TRAIL_HEAD, C_TRAIL_TAIL,
    Renderer,
)


def make_flight(**kw):
    f = MagicMock()
    f.icao24    = kw.get("icao24",    "abc123")
    f.callsign  = kw.get("callsign",  "UAE001")
    f.longitude = kw.get("longitude", 55.3657)
    f.latitude  = kw.get("latitude",  25.2048)
    f.heading   = kw.get("heading",   90.0)
    f.altitude  = kw.get("altitude",  10000.0)
    f.velocity  = kw.get("velocity",  250.0)
    return f


# ===========================================================================
# TrailStore
# ===========================================================================

class TestTrailStore:
    def test_first_point_always_added(self):
        ts = TrailStore()
        ts.update("a", 55.0, 25.0)
        assert ts.get("a") == [(55.0, 25.0)]

    def test_large_move_adds_point(self):
        ts = TrailStore()
        ts.update("a", 55.0, 25.0)
        ts.update("a", 55.1, 25.1)
        assert len(ts.get("a")) == 2

    def test_duplicate_ignored(self):
        ts = TrailStore()
        ts.update("a", 55.0, 25.0)
        ts.update("a", 55.0, 25.0)
        assert len(ts.get("a")) == 1

    def test_tiny_move_ignored(self):
        ts = TrailStore()
        ts.update("a", 55.0, 25.0)
        ts.update("a", 55.00001, 25.00001)
        assert len(ts.get("a")) == 1

    def test_max_length_respected(self):
        ts = TrailStore(max_length=5)
        for i in range(10):
            ts.update("a", 55.0 + i * 0.01, 25.0)
        assert len(ts.get("a")) == 5

    def test_oldest_dropped_when_full(self):
        ts = TrailStore(max_length=3)
        ts.update("a", 55.00, 25.0)
        ts.update("a", 55.01, 25.0)
        ts.update("a", 55.02, 25.0)
        ts.update("a", 55.03, 25.0)
        assert ts.get("a")[0] == (55.01, 25.0)

    def test_separate_flights_isolated(self):
        ts = TrailStore()
        ts.update("a", 55.0, 25.0)
        ts.update("b", 56.0, 26.0)
        assert ts.get("a") == [(55.0, 25.0)]
        assert ts.get("b") == [(56.0, 26.0)]

    def test_unknown_returns_empty(self):
        assert TrailStore().get("x") == []

    def test_prune_removes_stale(self):
        ts = TrailStore()
        ts.update("a", 55.0, 25.0)
        ts.update("b", 56.0, 26.0)
        ts.prune({"a"})
        assert ts.get("b") == []
        assert ts.get("a") != []

    def test_prune_empty_clears_all(self):
        ts = TrailStore()
        ts.update("a", 55.0, 25.0)
        ts.prune(set())
        assert ts.get("a") == []


# ===========================================================================
# Projector (circular)
# ===========================================================================

class TestProjector:
    CX, CY, R = 1000, 540, 400
    BBOX = (22.0, 45.0, 30.0, 60.0)

    @pytest.fixture
    def proj(self):
        return Projector(self.BBOX, self.CX, self.CY, self.R)

    def test_bbox_centre_maps_to_radar_centre(self, proj):
        mid_lon = (45.0 + 60.0) / 2
        mid_lat = (22.0 + 30.0) / 2
        x, y = proj.project(mid_lon, mid_lat)
        assert x == self.CX
        assert y == self.CY

    def test_north_is_above_centre(self, proj):
        _, y_north = proj.project(52.5, 29.0)
        _, y_south = proj.project(52.5, 23.0)
        assert y_north < y_south

    def test_east_is_right_of_centre(self, proj):
        x_west, _ = proj.project(46.0, 26.0)
        x_east, _ = proj.project(59.0, 26.0)
        assert x_west < x_east

    def test_centre_method(self, proj):
        assert proj.centre() == (self.CX, self.CY)

    def test_in_radar_centre_true(self, proj):
        assert proj.in_radar(52.5, 26.0) is True

    def test_in_radar_far_outside_false(self, proj):
        # project a point way outside bbox — will be far outside circle
        x, y = proj.project(80.0, 50.0)
        dx, dy = x - self.CX, y - self.CY
        assert math.hypot(dx, dy) > self.R
        assert proj.in_radar(80.0, 50.0) is False

    def test_in_radar_edge_approximately_true(self, proj):
        # The bbox edge maps to approximately r distance from centre
        # Use centre lat, slightly inside lon edge
        x, y = proj.project(45.1, 26.0)
        dx, dy = x - self.CX, y - self.CY
        assert math.hypot(dx, dy) < self.R


# ===========================================================================
# Colour helpers
# ===========================================================================

class TestLerpColour:
    def test_t0_returns_c1(self):
        assert _lerp_colour((0,0,0), (255,255,255), 0.0) == (0,0,0)

    def test_t1_returns_c2(self):
        assert _lerp_colour((0,0,0), (255,255,255), 1.0) == (255,255,255)

    def test_midpoint(self):
        r, g, b = _lerp_colour((0,0,0), (200,100,50), 0.5)
        assert r == 100 and g == 50 and b == 25

    def test_returns_ints(self):
        assert all(isinstance(v, int) for v in _lerp_colour((10,20,30),(11,21,31),0.5))


class TestPlaneColour:
    def test_fast(self):      assert _plane_colour(SPEED_FAST + 1) == C_PLANE_FAST
    def test_slow(self):      assert _plane_colour(SPEED_SLOW - 1) == C_PLANE_SLOW
    def test_cruise(self):    assert _plane_colour((SPEED_FAST + SPEED_SLOW) / 2) == C_PLANE
    def test_threshold_fast(self): assert _plane_colour(SPEED_FAST) == C_PLANE_FAST
    def test_threshold_slow(self): assert _plane_colour(SPEED_SLOW) == C_PLANE_SLOW
    def test_zero(self):      assert _plane_colour(0) == C_PLANE_SLOW


# ===========================================================================
# Locations dict
# ===========================================================================

class TestLocations:
    def test_default_location_exists(self):
        assert DEFAULT_LOCATION in LOCATIONS

    def test_each_location_has_name_and_bbox(self):
        for key, (name, bbox) in LOCATIONS.items():
            assert isinstance(name, str) and len(name) > 0
            assert len(bbox) == 4
            lat_min, lon_min, lat_max, lon_max = bbox
            assert lat_min < lat_max
            assert lon_min < lon_max

    def test_known_locations_present(self):
        for loc in ("dubai", "london", "newyork", "tokyo", "paris"):
            assert loc in LOCATIONS


# ===========================================================================
# _draw_trail — real offscreen Surface
# ===========================================================================

class TestDrawTrail:
    @pytest.fixture(autouse=True)
    def init_pg(self):
        pygame.init(); yield; pygame.quit()

    def test_empty_no_crash(self):
        s = pygame.Surface((200,200), pygame.SRCALPHA)
        _draw_trail(s, [], C_TRAIL_HEAD, C_TRAIL_TAIL)

    def test_single_point_no_crash(self):
        s = pygame.Surface((200,200), pygame.SRCALPHA)
        _draw_trail(s, [(10,10)], C_TRAIL_HEAD, C_TRAIL_TAIL)

    def test_two_points_paints_pixels(self):
        s = pygame.Surface((200,200), pygame.SRCALPHA)
        s.fill((0,0,0,0))
        _draw_trail(s, [(10,10),(100,100)], C_TRAIL_HEAD, C_TRAIL_TAIL)
        assert s.get_at((99,99)).a > 0


# ===========================================================================
# Renderer class
# ===========================================================================

def _mock_surf(w=1920, h=1080):
    s = MagicMock(spec=pygame.Surface)
    s.get_size.return_value = (w, h)
    s.blit.return_value = MagicMock()
    return s


def _patch_fonts(f):
    """Decorator stacking the four patches needed for Renderer.__init__."""
    import functools
    @patch("src.renderer.pygame.time.Clock")
    @patch("src.renderer.pygame.font.Font")
    @patch("src.renderer.pygame.font.match_font", return_value=None)
    @patch("src.renderer.pygame.font.init")
    @functools.wraps(f)
    def wrapper(self, _init, _match, _font, _clock, *a, **kw):
        return f(self, *a, **kw)
    return wrapper


class TestRendererInit:
    @_patch_fonts
    def test_default_location_is_dubai(self):
        r = Renderer(_mock_surf())
        assert r.location_name == LOCATIONS["dubai"][0]

    @_patch_fonts
    def test_named_location_sets_bbox(self):
        r = Renderer(_mock_surf(), location="london")
        assert r.bbox == LOCATIONS["london"][1]

    @_patch_fonts
    def test_radar_cx_is_right_of_panel(self):
        r = Renderer(_mock_surf(1920, 1080))
        assert r._radar_cx > r._panel_w

    @_patch_fonts
    def test_radar_cy_is_vertically_centred(self):
        r = Renderer(_mock_surf(1920, 1080))
        assert r._radar_cy == 540

    @_patch_fonts
    def test_trails_empty_on_init(self):
        r = Renderer(_mock_surf())
        assert r.trails.get("anything") == []

    @_patch_fonts
    def test_show_flags_default_true(self):
        r = Renderer(_mock_surf())
        assert r.show_labels and r.show_trails


class TestRendererSetLocation:
    @_patch_fonts
    def test_valid_location_changes_bbox(self):
        r = Renderer(_mock_surf())
        r.set_location("tokyo")
        assert r.bbox == LOCATIONS["tokyo"][1]
        assert r.location_name == LOCATIONS["tokyo"][0]

    @_patch_fonts
    def test_invalid_location_leaves_bbox_unchanged(self):
        r = Renderer(_mock_surf())
        original = r.bbox
        r.set_location("atlantis")
        assert r.bbox == original

    @_patch_fonts
    def test_set_location_clears_trails(self):
        r = Renderer(_mock_surf())
        r.trails.update("x", 55.0, 25.0)
        r.set_location("paris")
        assert r.trails.get("x") == []

    @_patch_fonts
    def test_set_location_clears_label_cache(self):
        r = Renderer(_mock_surf())
        r._label_cache["x"] = (MagicMock(), MagicMock())
        r.set_location("paris")
        assert r._label_cache == {}


class TestRendererZoomPan:
    @_patch_fonts
    def test_zoom_in_shrinks_bbox(self):
        r = Renderer(_mock_surf())
        lat_span_before = r.bbox[2] - r.bbox[0]
        r.zoom(0.5)
        lat_span_after = r.bbox[2] - r.bbox[0]
        assert lat_span_after < lat_span_before

    @_patch_fonts
    def test_zoom_out_grows_bbox(self):
        r = Renderer(_mock_surf())
        lat_span_before = r.bbox[2] - r.bbox[0]
        r.zoom(2.0)
        lat_span_after = r.bbox[2] - r.bbox[0]
        assert lat_span_after > lat_span_before

    @_patch_fonts
    def test_zoom_preserves_centre(self):
        r = Renderer(_mock_surf())
        mid_lat = (r.bbox[0] + r.bbox[2]) / 2
        mid_lon = (r.bbox[1] + r.bbox[3]) / 2
        r.zoom(0.5)
        new_mid_lat = (r.bbox[0] + r.bbox[2]) / 2
        new_mid_lon = (r.bbox[1] + r.bbox[3]) / 2
        assert new_mid_lat == pytest.approx(mid_lat, abs=0.01)
        assert new_mid_lon == pytest.approx(mid_lon, abs=0.01)

    @_patch_fonts
    def test_zoom_in_clamps_at_min(self):
        r = Renderer(_mock_surf())
        for _ in range(30):
            r.zoom(0.1)
        lat_span = r.bbox[2] - r.bbox[0]
        from src.renderer import MIN_ZOOM_SPAN
        assert lat_span >= MIN_ZOOM_SPAN

    @_patch_fonts
    def test_pan_north_increases_lat(self):
        r = Renderer(_mock_surf())
        mid_lat_before = (r.bbox[0] + r.bbox[2]) / 2
        r.pan(1.0, 0)
        mid_lat_after = (r.bbox[0] + r.bbox[2]) / 2
        assert mid_lat_after > mid_lat_before

    @_patch_fonts
    def test_pan_east_increases_lon(self):
        r = Renderer(_mock_surf())
        mid_lon_before = (r.bbox[1] + r.bbox[3]) / 2
        r.pan(0, 1.0)
        mid_lon_after = (r.bbox[1] + r.bbox[3]) / 2
        assert mid_lon_after > mid_lon_before

    @_patch_fonts
    def test_reset_zoom_restores_original_bbox(self):
        r = Renderer(_mock_surf(), location="dubai")
        original_bbox = r.bbox
        r.zoom(0.3)
        r.pan(2.0, 2.0)
        r.reset_zoom()
        assert r.bbox == original_bbox

    @_patch_fonts
    def test_toggle_airport_mode_changes_bbox(self):
        r = Renderer(_mock_surf(), location="dubai")
        city_bbox = r.bbox
        r.toggle_airport_mode()
        assert r.bbox != city_bbox
        assert r._airport_mode is True

    @_patch_fonts
    def test_toggle_airport_mode_twice_returns_to_city(self):
        r = Renderer(_mock_surf(), location="dubai")
        city_bbox = r.bbox
        r.toggle_airport_mode()
        r.toggle_airport_mode()
        assert r._airport_mode is False
        assert r.bbox == city_bbox


class TestRendererAnimation:
    @_patch_fonts
    def test_scan_angle_advances(self):
        r = Renderer(_mock_surf())
        r._scan_angle = 0.0
        r._tick_animation()
        assert r._scan_angle > 0.0

    @_patch_fonts
    def test_scan_angle_wraps(self):
        r = Renderer(_mock_surf())
        r._scan_angle = 359.9
        r._tick_animation()
        assert r._scan_angle < 360.0

    @_patch_fonts
    def test_pulse_advances(self):
        r = Renderer(_mock_surf())
        r._pulse_t = 0.0
        r._tick_animation()
        assert r._pulse_t > 0.0

    @_patch_fonts
    def test_pulse_wraps(self):
        r = Renderer(_mock_surf())
        r._pulse_t = 0.9999
        r._tick_animation()
        assert r._pulse_t < 1.0


class TestRendererResize:
    @_patch_fonts
    def test_resize_clears_bg_cache(self):
        r = Renderer(_mock_surf())
        r._bg_surf = MagicMock()
        r.resize(800, 600)
        assert r._bg_surf is None

    @_patch_fonts
    def test_resize_updates_radar_centre(self):
        r = Renderer(_mock_surf(1920, 1080))
        old_cy = r._radar_cy
        r.surface.get_size.return_value = (1280, 720)
        r.resize(1280, 720)
        assert r._radar_cy != old_cy or r._radar_cx != 1920 // 2


class TestRendererInvalidateCache:
    @_patch_fonts
    def test_clears_label_cache(self):
        r = Renderer(_mock_surf())
        r._label_cache["x"] = (MagicMock(), MagicMock())
        r.invalidate_label_cache()
        assert r._label_cache == {}


# ===========================================================================
# Trail accumulation integration
# ===========================================================================

class TestTrailAccumulation:
    def test_grows_with_large_moves(self):
        ts = TrailStore(max_length=10)
        for i in range(8):
            ts.update("f", 55.0 + i * 0.02, 25.0 + i * 0.02)
        assert len(ts.get("f")) == 8

    def test_capped_at_max(self):
        ts = TrailStore(max_length=5)
        for i in range(20):
            ts.update("f", 55.0 + i * 0.05, 25.0)
        assert len(ts.get("f")) == 5

    def test_stationary_stays_single_point(self):
        ts = TrailStore()
        for _ in range(10):
            ts.update("f", 55.0, 25.0)
        assert len(ts.get("f")) == 1