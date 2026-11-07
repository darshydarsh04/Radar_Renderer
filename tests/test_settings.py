"""tests/test_settings.py: persisted view settings and the zoom/pan/goto maths."""
from __future__ import annotations

import json

import pytest

from src import settings as st
from src.renderer import AIRPORT_LOCATIONS, CITY_LOCATIONS


def fresh() -> dict:
    return dict(st.DEFAULTS)


def span(bbox):
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


class TestLoadSave:
    def test_missing_file_gives_defaults(self, tmp_path):
        assert st.load_settings(tmp_path / "nope.json") == st.DEFAULTS

    def test_corrupt_file_gives_defaults(self, tmp_path):
        path = tmp_path / "s.json"
        path.write_text("{not json")
        assert st.load_settings(path) == st.DEFAULTS

    def test_roundtrip(self, tmp_path):
        s = fresh()
        st.set_location(s, "london")
        st.zoom(s, 0.5)
        s["show_map"] = False
        path = tmp_path / "nested" / "s.json"
        st.save_settings(s, path)
        loaded = st.load_settings(path)
        assert loaded["location"] == "london"
        assert loaded["bbox"] == s["bbox"]
        assert loaded["show_map"] is False

    def test_unknown_location_falls_back(self, tmp_path):
        path = tmp_path / "s.json"
        path.write_text(json.dumps({"location": "atlantis"}))
        assert st.load_settings(path)["location"] == st.DEFAULTS["location"]

    def test_invalid_bbox_is_dropped(self, tmp_path):
        path = tmp_path / "s.json"
        path.write_text(json.dumps({"bbox": [50, 10, 40, 20], "custom": True, "label": "X"}))
        loaded = st.load_settings(path)
        assert loaded["bbox"] is None
        assert loaded["custom"] is False
        assert loaded["label"] is None

    def test_out_of_range_bbox_is_dropped(self, tmp_path):
        path = tmp_path / "s.json"
        path.write_text(json.dumps({"bbox": [-95, 0, 10, 20]}))
        assert st.load_settings(path)["bbox"] is None

    def test_negative_routes_clamped(self, tmp_path):
        path = tmp_path / "s.json"
        path.write_text(json.dumps({"routes": -4}))
        assert st.load_settings(path)["routes"] == 0

    def test_bad_size_reset(self, tmp_path):
        path = tmp_path / "s.json"
        path.write_text(json.dumps({"size": "huge"}))
        assert st.load_settings(path)["size"] == st.DEFAULTS["size"]

    def test_unknown_keys_ignored(self, tmp_path):
        path = tmp_path / "s.json"
        path.write_text(json.dumps({"surprise": 1}))
        assert "surprise" not in st.load_settings(path)


class TestParseSize:
    def test_valid(self):
        assert st.parse_size("2560x1440") == (2560, 1440)
        assert st.parse_size("1920X1080") == (1920, 1080)

    @pytest.mark.parametrize("bad", ["", "1920", "axb", "1920x", "1x1", "1920x1080x3"])
    def test_invalid(self, bad):
        assert st.parse_size(bad) is None


class TestPresets:
    def test_default_view_is_preset(self):
        s = fresh()
        assert st.current_bbox(s) == CITY_LOCATIONS["dubai"][1]
        assert st.display_name(s) == CITY_LOCATIONS["dubai"][0]

    def test_set_location_resets_view(self):
        s = fresh()
        st.zoom(s, 0.5)
        st.set_location(s, "tokyo")
        assert s["bbox"] is None
        assert st.current_bbox(s) == CITY_LOCATIONS["tokyo"][1]

    def test_set_location_rejects_unknown(self):
        with pytest.raises(ValueError):
            st.set_location(fresh(), "atlantis")

    def test_airport_mode_uses_airport_preset(self):
        s = fresh()
        st.set_mode(s, True)
        assert st.current_bbox(s) == AIRPORT_LOCATIONS["dubai"][1]

    def test_mode_back_to_city(self):
        s = fresh()
        st.set_mode(s, True)
        st.set_mode(s, False)
        assert st.current_bbox(s) == CITY_LOCATIONS["dubai"][1]


class TestZoom:
    def test_zoom_in_shrinks(self):
        s = fresh()
        before = span(st.current_bbox(s))
        st.zoom(s, 0.5)
        after = span(st.current_bbox(s))
        assert after[0] < before[0] and after[1] < before[1]

    def test_zoom_out_grows(self):
        s = fresh()
        before = span(st.current_bbox(s))
        st.zoom(s, 2.0)
        after = span(st.current_bbox(s))
        assert after[0] > before[0] and after[1] > before[1]

    def test_zoom_keeps_centre(self):
        s = fresh()
        lat_min, lon_min, lat_max, lon_max = st.current_bbox(s)
        st.zoom(s, 0.5)
        n = st.current_bbox(s)
        assert (n[0] + n[2]) / 2 == pytest.approx((lat_min + lat_max) / 2, abs=1e-4)
        assert (n[1] + n[3]) / 2 == pytest.approx((lon_min + lon_max) / 2, abs=1e-4)

    def test_zoom_in_stops_at_minimum(self):
        s = fresh()
        for _ in range(60):
            st.zoom(s, 0.5)
        lat_span, lon_span = span(st.current_bbox(s))
        assert lat_span / 2 >= st.MIN_HALF_SPAN - 1e-4
        assert lon_span / 2 >= st.MIN_HALF_SPAN - 1e-4

    def test_zoom_out_stops_at_maximum(self):
        s = fresh()
        for _ in range(60):
            st.zoom(s, 2.0)
        lat_span, lon_span = span(st.current_bbox(s))
        assert lat_span / 2 <= st.MAX_HALF_SPAN + 1e-4
        assert lon_span / 2 <= st.MAX_HALF_SPAN + 1e-4

    @pytest.mark.parametrize("key", sorted(AIRPORT_LOCATIONS))
    def test_zoom_in_never_enlarges_airport_presets(self, key):
        s = fresh()
        st.set_location(s, key)
        st.set_mode(s, True)
        before = span(st.current_bbox(s))
        st.zoom(s, 0.5)
        after = span(st.current_bbox(s))
        assert after[0] <= before[0] + 1e-4
        assert after[1] <= before[1] + 1e-4

    def test_zoom_rejects_non_positive_factor(self):
        with pytest.raises(ValueError):
            st.zoom(fresh(), 0)

    def test_zoom_level_reports_ratio(self):
        s = fresh()
        st.zoom(s, 0.5)
        assert st.zoom_level(s) == pytest.approx(2.0, rel=1e-3)

    def test_reset_view_returns_to_preset(self):
        s = fresh()
        st.zoom(s, 0.3)
        st.pan(s, 1.0, 1.0)
        st.reset_view(s)
        assert st.current_bbox(s) == CITY_LOCATIONS["dubai"][1]


class TestPan:
    def test_north_increases_latitude(self):
        s = fresh()
        before = st.current_bbox(s)
        st.pan(s, north=0.2)
        assert st.current_bbox(s)[0] > before[0]

    def test_south_decreases_latitude(self):
        s = fresh()
        before = st.current_bbox(s)
        st.pan(s, north=-0.2)
        assert st.current_bbox(s)[0] < before[0]

    def test_east_increases_longitude(self):
        s = fresh()
        before = st.current_bbox(s)
        st.pan(s, east=0.2)
        assert st.current_bbox(s)[1] > before[1]

    def test_pan_is_fraction_of_visible_span(self):
        s = fresh()
        before = st.current_bbox(s)
        st.pan(s, north=1.0)
        assert st.current_bbox(s)[0] == pytest.approx(before[2], abs=1e-4)

    def test_pan_keeps_size(self):
        s = fresh()
        before = span(st.current_bbox(s))
        st.pan(s, 0.4, -0.4)
        after = span(st.current_bbox(s))
        assert after[0] == pytest.approx(before[0], abs=1e-4)
        assert after[1] == pytest.approx(before[1], abs=1e-4)

    def test_pan_stays_inside_the_world(self):
        s = fresh()
        st.set_location(s, "tokyo")
        before = span(st.current_bbox(s))
        for _ in range(100):
            st.pan(s, north=1.0, east=1.0)
        lat_min, lon_min, lat_max, lon_max = st.current_bbox(s)
        assert lat_max <= 90 and lon_max <= 180
        assert span((lat_min, lon_min, lat_max, lon_max))[0] == pytest.approx(before[0], abs=1e-4)

    def test_pan_south_west_stays_inside_the_world(self):
        s = fresh()
        for _ in range(100):
            st.pan(s, north=-1.0, east=-1.0)
        lat_min, lon_min, _, _ = st.current_bbox(s)
        assert lat_min >= -90 and lon_min >= -180


class TestGoto:
    def test_goto_centres_on_point(self):
        s = fresh()
        st.goto(s, 51.47, -0.45, 1.0)
        lat_min, lon_min, lat_max, lon_max = st.current_bbox(s)
        assert (lat_min + lat_max) / 2 == pytest.approx(51.47, abs=1e-4)
        assert (lon_min + lon_max) / 2 == pytest.approx(-0.45, abs=1e-4)
        assert (lat_max - lat_min) / 2 == pytest.approx(1.0, abs=1e-4)

    def test_goto_marks_custom_with_label(self):
        s = fresh()
        st.set_mode(s, True)
        st.goto(s, 51.47, -0.45)
        assert s["custom"] is True
        assert s["airport_mode"] is False
        assert "51.47" in st.display_name(s)

    def test_goto_widens_longitude_away_from_equator(self):
        s = fresh()
        st.goto(s, 60.0, 10.0, 2.0)
        lat_min, lon_min, lat_max, lon_max = st.current_bbox(s)
        assert (lon_max - lon_min) / 2 == pytest.approx(4.0, abs=1e-3)

    def test_goto_near_equator_is_roughly_square(self):
        s = fresh()
        st.goto(s, 0.0, 10.0, 2.0)
        lat_min, lon_min, lat_max, lon_max = st.current_bbox(s)
        assert (lon_max - lon_min) == pytest.approx(lat_max - lat_min, abs=1e-3)

    @pytest.mark.parametrize("lat,lon", [(95, 0), (-91, 0), (0, 181), (0, -200), (float("nan"), 0)])
    def test_goto_rejects_out_of_range(self, lat, lon):
        with pytest.raises(ValueError):
            st.goto(fresh(), lat, lon)

    def test_goto_rejects_bad_radius(self):
        with pytest.raises(ValueError):
            st.goto(fresh(), 10, 10, 0)

    def test_goto_near_pole_stays_valid(self):
        s = fresh()
        st.goto(s, 89.9, 179.9, 5.0)
        lat_min, lon_min, lat_max, lon_max = st.current_bbox(s)
        assert lat_max <= 90 and lon_max <= 180

    def test_zoom_level_for_custom_is_one(self):
        s = fresh()
        st.goto(s, 10, 10, 2.0)
        assert st.zoom_level(s) == 1.0
