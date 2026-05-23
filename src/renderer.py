"""
renderer.py — Flight Wallpaper Renderer

Draws a live radar-style map of flights onto a pygame Surface.

Visual style: dark aerospace HUD — deep navy background, cyan plane icons,
phosphor-green trails, amber altitude rings, monospace telemetry readouts.

Layers (bottom to top):
  1. Background gradient
  2. Grid lines (lat/lon)
  3. Range rings (decorative)
  4. Flight trails (fading polyline)
  5. Plane icons (rotated arrow, heading-aware)
  6. Callsign + altitude labels
  7. HUD overlay (clock, flight count, bbox label)
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pygame
import pygame.gfxdraw

if TYPE_CHECKING:
    from src.flight import Flight


# ---------------------------------------------------------------------------
# Colour palette — aerospace HUD
# ---------------------------------------------------------------------------

C_BG_TOP        = (4,   8,  24)      # deep space navy
C_BG_BOTTOM     = (8,  18,  40)      # slightly lighter navy at horizon
C_GRID          = (18,  40,  72)      # subtle grid lines
C_GRID_BRIGHT   = (24,  56, 100)     # major grid lines (every 5°)
C_RING          = (14,  48,  88)      # range ring
C_RING_PULSE    = (0,  160, 220)     # animated pulse ring
C_TRAIL_HEAD    = (0,  220, 180)     # bright cyan-green trail start
C_TRAIL_TAIL    = (0,   60,  50)     # fade to near-black
C_PLANE         = (0,  220, 255)     # cyan plane icon
C_PLANE_FAST    = (80, 255, 180)     # fast plane (>300 m/s) goes green
C_PLANE_SLOW    = (255, 180,  40)    # slow/helicopter goes amber
C_LABEL_CALL    = (160, 230, 255)    # callsign text
C_LABEL_ALT     = (80,  160, 140)    # altitude text (dimmer)
C_HUD_PRIMARY   = (0,  200, 255)     # HUD title text
C_HUD_DIM       = (40, 100, 130)     # HUD secondary text
C_SCAN_LINE     = (0,  180, 255)     # rotating radar sweep
C_ORIGIN_RING   = (0,  100, 180)     # dot at centre

TRAIL_LENGTH    = 24          # max trail positions stored per flight
TRAIL_MIN_DIST  = 0.0005      # min geo-distance before new trail point added
LABEL_FONT_SIZE = 11
HUD_FONT_SIZE   = 13
HUD_TITLE_SIZE  = 16

# Speed thresholds (m/s) for plane colour
SPEED_FAST      = 220
SPEED_SLOW      = 60


# ---------------------------------------------------------------------------
# Trail store — lives in the renderer, keyed by icao24
# ---------------------------------------------------------------------------

@dataclass
class TrailStore:
    """Keeps the last N geo-positions for each flight, for drawing trails."""
    max_length: int = TRAIL_LENGTH
    _data: dict[str, list[tuple[float, float]]] = field(
        default_factory=dict, repr=False
    )

    def update(self, icao24: str, lon: float, lat: float) -> None:
        trail = self._data.setdefault(icao24, [])
        if trail:
            last_lon, last_lat = trail[-1]
            dist = math.hypot(lon - last_lon, lat - last_lat)
            if dist < TRAIL_MIN_DIST:
                return                          # hasn't moved enough
        trail.append((lon, lat))
        if len(trail) > self.max_length:
            trail.pop(0)

    def get(self, icao24: str) -> list[tuple[float, float]]:
        return self._data.get(icao24, [])

    def prune(self, active_icao24s: set[str]) -> None:
        """Remove trails for flights no longer in the feed."""
        stale = set(self._data) - active_icao24s
        for k in stale:
            del self._data[k]


# ---------------------------------------------------------------------------
# Projection helpers (self-contained so renderer doesn't import config)
# ---------------------------------------------------------------------------

class Projector:
    """Equirectangular geo→pixel projection for a given bounding box."""

    def __init__(
        self,
        bbox: tuple[float, float, float, float],
        screen_w: int,
        screen_h: int,
    ) -> None:
        self.lat_min, self.lon_min, self.lat_max, self.lon_max = bbox
        self.w = screen_w
        self.h = screen_h

    def project(self, lon: float, lat: float) -> tuple[int, int]:
        x = (lon - self.lon_min) / (self.lon_max - self.lon_min) * self.w
        y = (self.lat_max - lat) / (self.lat_max - self.lat_min) * self.h
        return int(x), int(y)

    def centre(self) -> tuple[int, int]:
        mid_lon = (self.lon_min + self.lon_max) / 2
        mid_lat = (self.lat_min + self.lat_max) / 2
        return self.project(mid_lon, mid_lat)

    def lon_to_x(self, lon: float) -> int:
        return int((lon - self.lon_min) / (self.lon_max - self.lon_min) * self.w)

    def lat_to_y(self, lat: float) -> int:
        return int((self.lat_max - lat) / (self.lat_max - self.lat_min) * self.h)


# ---------------------------------------------------------------------------
# Drawing primitives
# ---------------------------------------------------------------------------

def _lerp_colour(
    c1: tuple[int, int, int],
    c2: tuple[int, int, int],
    t: float,
) -> tuple[int, int, int]:
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def _plane_colour(velocity: float) -> tuple[int, int, int]:
    if velocity >= SPEED_FAST:
        return C_PLANE_FAST
    if velocity <= SPEED_SLOW:
        return C_PLANE_SLOW
    return C_PLANE


def _draw_plane_icon(
    surface: pygame.Surface,
    cx: int,
    cy: int,
    heading_deg: float,
    colour: tuple[int, int, int],
    size: int = 8,
) -> None:
    """
    Draw a minimal arrow-plane icon rotated to heading.
    heading_deg: 0=north, clockwise.
    The arrow points in the direction of travel.
    """
    # Arrow defined pointing UP (north = 0°), then rotated
    # Points: nose, left wing, tail, right wing
    half = size
    tip   = (0, -half * 1.6)
    lwing = (-half, half * 0.4)
    tail  = (0,  half * 0.6)
    rwing = ( half, half * 0.4)

    rad = math.radians(heading_deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)

    def rotate(px: float, py: float) -> tuple[int, int]:
        rx = px * cos_a - py * sin_a
        ry = px * sin_a + py * cos_a
        return int(cx + rx), int(cy + ry)

    pts = [rotate(*tip), rotate(*lwing), rotate(*tail), rotate(*rwing)]

    # Filled body
    pygame.draw.polygon(surface, colour, pts)

    # Bright outline for legibility
    bright = _lerp_colour(colour, (255, 255, 255), 0.4)
    pygame.draw.polygon(surface, bright, pts, 1)

    # Nose dot
    nx, ny = rotate(*tip)
    pygame.gfxdraw.filled_circle(surface, nx, ny, 2, (*colour, 200))


def _draw_trail(
    surface: pygame.Surface,
    points: list[tuple[int, int]],
    colour_head: tuple[int, int, int],
    colour_tail: tuple[int, int, int],
) -> None:
    """Draw a fading polyline trail."""
    n = len(points)
    if n < 2:
        return
    for i in range(1, n):
        t = i / (n - 1)                    # 0=tail, 1=head
        col = _lerp_colour(colour_tail, colour_head, t)
        alpha = int(40 + 180 * t)
        # Use a small surface for alpha blending per segment
        x1, y1 = points[i - 1]
        x2, y2 = points[i]
        pygame.draw.line(surface, (*col, alpha), (x1, y1), (x2, y2), 1)


# ---------------------------------------------------------------------------
# Background layers
# ---------------------------------------------------------------------------

def _draw_background_gradient(
    surface: pygame.Surface,
    w: int,
    h: int,
    bg_surf: pygame.Surface | None,
) -> pygame.Surface:
    """
    Draw a vertical gradient background.
    Returns a cached Surface so we only rebuild when size changes.
    """
    if bg_surf is None or bg_surf.get_size() != (w, h):
        bg_surf = pygame.Surface((w, h))
        for y in range(h):
            t = y / h
            col = _lerp_colour(C_BG_TOP, C_BG_BOTTOM, t)
            pygame.draw.line(bg_surf, col, (0, y), (w, y))
    surface.blit(bg_surf, (0, 0))
    return bg_surf


def _draw_grid(
    surface: pygame.Surface,
    proj: Projector,
    grid_step: float = 1.0,
) -> None:
    """Draw lat/lon grid lines."""
    lat_min, lon_min, lat_max, lon_max = (
        proj.lat_min, proj.lon_min, proj.lat_max, proj.lon_max
    )
    w, h = surface.get_size()

    lon = math.ceil(lon_min / grid_step) * grid_step
    while lon <= lon_max:
        x = proj.lon_to_x(lon)
        is_major = abs(lon % 5) < 0.001
        col = C_GRID_BRIGHT if is_major else C_GRID
        pygame.draw.line(surface, col, (x, 0), (x, h), 1)
        lon += grid_step

    lat = math.ceil(lat_min / grid_step) * grid_step
    while lat <= lat_max:
        y = proj.lat_to_y(lat)
        is_major = abs(lat % 5) < 0.001
        col = C_GRID_BRIGHT if is_major else C_GRID
        pygame.draw.line(surface, col, (0, y), (w, y), 1)
        lat += grid_step


def _draw_range_rings(
    surface: pygame.Surface,
    proj: Projector,
    pulse_alpha: float,         # 0.0–1.0 animated pulse
) -> None:
    """Draw concentric decorative range rings from screen centre."""
    cx, cy = proj.centre()
    w = surface.get_size()[0]
    step = w // 6

    ring_surf = pygame.Surface(surface.get_size(), pygame.SRCALPHA)

    for i in range(1, 7):
        r = i * step
        alpha = max(0, 80 - i * 10)
        pygame.gfxdraw.aacircle(ring_surf, cx, cy, r, (*C_RING, alpha))

    # Animated pulse ring
    pulse_r = int(step * 0.5 + pulse_alpha * step * 5.5)
    pulse_a = int((1 - pulse_alpha) * 120)
    if 0 < pulse_r < w and pulse_a > 0:
        pygame.gfxdraw.aacircle(
            ring_surf, cx, cy, pulse_r, (*C_RING_PULSE, pulse_a)
        )

    # Centre dot
    pygame.gfxdraw.filled_circle(ring_surf, cx, cy, 4, (*C_ORIGIN_RING, 180))
    pygame.gfxdraw.aacircle(ring_surf, cx, cy, 4, (*C_HUD_PRIMARY, 220))

    surface.blit(ring_surf, (0, 0))


def _draw_scan_line(
    surface: pygame.Surface,
    proj: Projector,
    angle_deg: float,
) -> None:
    """Rotating radar sweep line with fading wedge."""
    cx, cy = proj.centre()
    w, h = surface.get_size()
    max_r = int(math.hypot(w, h))

    sweep_surf = pygame.Surface((w, h), pygame.SRCALPHA)

    # Sweep wedge (fading arc behind the line)
    wedge_steps = 30
    for i in range(wedge_steps):
        t = i / wedge_steps
        deg = angle_deg - t * 60          # 60° fade arc
        rad = math.radians(deg)
        ex = cx + int(max_r * math.sin(rad))
        ey = cy - int(max_r * math.cos(rad))
        alpha = int((1 - t) * 25)
        if alpha > 0:
            pygame.draw.line(
                sweep_surf, (*C_SCAN_LINE, alpha), (cx, cy), (ex, ey), 2
            )

    # Bright sweep line
    rad = math.radians(angle_deg)
    ex = cx + int(max_r * math.sin(rad))
    ey = cy - int(max_r * math.cos(rad))
    pygame.draw.line(sweep_surf, (*C_SCAN_LINE, 80), (cx, cy), (ex, ey), 1)

    surface.blit(sweep_surf, (0, 0))


# ---------------------------------------------------------------------------
# HUD overlay
# ---------------------------------------------------------------------------

def _draw_hud(
    surface: pygame.Surface,
    font_title: pygame.font.Font,
    font_hud: pygame.font.Font,
    flight_count: int,
    bbox: tuple[float, float, float, float],
    fps: float,
) -> None:
    """Top-left HUD panel."""
    w, h = surface.get_size()
    pad = 18
    line_h = HUD_FONT_SIZE + 5

    now = time.strftime("%H:%M:%S UTC", time.gmtime())
    lat_min, lon_min, lat_max, lon_max = bbox

    lines_left = [
        (f"FLIGHT RADAR", font_title, C_HUD_PRIMARY),
        (f"LIVE",         font_hud,   C_PLANE_FAST),
        (f"",             font_hud,   C_HUD_DIM),
        (f"{flight_count:>4} AIRCRAFT",    font_hud, C_LABEL_CALL),
        (f"{now}",                          font_hud, C_HUD_DIM),
        (f"LAT {lat_min:.1f}°–{lat_max:.1f}°", font_hud, C_HUD_DIM),
        (f"LON {lon_min:.1f}°–{lon_max:.1f}°", font_hud, C_HUD_DIM),
        (f"FPS {fps:>5.1f}",                font_hud, C_HUD_DIM),
    ]

    # Semi-transparent panel background
    panel_w = 180
    panel_h = len(lines_left) * line_h + pad * 2
    panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
    panel.fill((4, 8, 24, 180))
    surface.blit(panel, (pad - 8, pad - 8))

    y = pad
    for text, font, colour in lines_left:
        if text:
            surf = font.render(text, True, colour)
            surface.blit(surf, (pad, y))
        y += line_h

    # Bottom-right: legend
    legend = [
        ("▶  FAST  (>220 m/s)", C_PLANE_FAST),
        ("▶  CRUISE",           C_PLANE),
        ("▶  SLOW  (<60 m/s)",  C_PLANE_SLOW),
    ]
    ly = h - pad - len(legend) * line_h
    panel2_w = 200
    panel2_h = len(legend) * line_h + pad
    panel2 = pygame.Surface((panel2_w, panel2_h), pygame.SRCALPHA)
    panel2.fill((4, 8, 24, 160))
    surface.blit(panel2, (w - panel2_w - pad + 8, ly - 8))

    for text, colour in legend:
        surf = font_hud.render(text, True, colour)
        surface.blit(surf, (w - panel2_w - pad + 16, ly))
        ly += line_h


# ---------------------------------------------------------------------------
# Main Renderer class
# ---------------------------------------------------------------------------

class Renderer:
    """
    Stateful renderer for the flight wallpaper.

    Usage:
        renderer = Renderer(screen, bbox=(22, 45, 30, 60))
        while True:
            renderer.draw(flights)
            pygame.display.flip()
    """

    def __init__(
        self,
        surface: pygame.Surface,
        bbox: tuple[float, float, float, float] = (22.0, 45.0, 30.0, 60.0),
        show_labels: bool = True,
        show_trails: bool = True,
        show_grid: bool = True,
        show_rings: bool = True,
        show_scan: bool = True,
    ) -> None:
        self.surface      = surface
        self.bbox         = bbox
        self.show_labels  = show_labels
        self.show_trails  = show_trails
        self.show_grid    = show_grid
        self.show_rings   = show_rings
        self.show_scan    = show_scan

        w, h = surface.get_size()
        self.proj         = Projector(bbox, w, h)
        self.trails       = TrailStore()

        # Animation state
        self._start_time  = time.time()
        self._scan_angle  = 0.0          # degrees, rotates each frame
        self._pulse_t     = 0.0          # 0–1 loop for range-ring pulse
        self._bg_surf: pygame.Surface | None = None

        # Font setup — monospace for that radar terminal feel
        pygame.font.init()
        mono = pygame.font.match_font("dejavusansmono,liberationmono,monospace,courier")
        self._font_label = pygame.font.Font(mono, LABEL_FONT_SIZE)
        self._font_hud   = pygame.font.Font(mono, HUD_FONT_SIZE)
        self._font_title = pygame.font.Font(mono, HUD_TITLE_SIZE)

        # Label surface cache: icao24 → (Surface, Surface) callsign+alt
        self._label_cache: dict[str, tuple[pygame.Surface, pygame.Surface]] = {}

        # Per-frame stats
        self._fps_clock   = pygame.time.Clock()
        self._fps         = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def draw(self, flights: list[Flight]) -> None:
        """
        Main draw call. Call once per frame.
        Draws all layers onto self.surface in correct order.
        """
        w, h = self.surface.get_size()
        self._tick_animation()

        # 1 — Background gradient (cached)
        self._bg_surf = _draw_background_gradient(
            self.surface, w, h, self._bg_surf
        )

        # 2 — Grid
        if self.show_grid:
            _draw_grid(self.surface, self.proj)

        # 3 — Range rings
        if self.show_rings:
            _draw_range_rings(self.surface, self.proj, self._pulse_t)

        # 4 — Radar sweep
        if self.show_scan:
            _draw_scan_line(self.surface, self.proj, self._scan_angle)

        # 5 — Trails + planes
        active_ids: set[str] = set()
        label_surf = pygame.Surface((w, h), pygame.SRCALPHA)

        for flight in flights:
            active_ids.add(flight.icao24)
            self._draw_flight(label_surf, flight)

        # Composite label layer on top (avoids z-order issues)
        self.surface.blit(label_surf, (0, 0))

        # Prune stale trails
        self.trails.prune(active_ids)

        # 6 — HUD overlay
        _draw_hud(
            self.surface,
            self._font_title,
            self._font_hud,
            len(flights),
            self.bbox,
            self._fps,
        )

        self._fps = self._fps_clock.get_fps()
        self._fps_clock.tick()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _tick_animation(self) -> None:
        dt = 1 / 60                        # assume ~60 fps for smooth anim
        self._scan_angle  = (self._scan_angle + 0.8) % 360
        self._pulse_t     = (self._pulse_t + 0.004) % 1.0

    def _draw_flight(
        self,
        label_surf: pygame.Surface,
        flight: Flight,
    ) -> None:
        """Draw one flight: trail → icon → label."""
        cx, cy = self.proj.project(flight.longitude, flight.latitude)

        # Update trail store
        self.trails.update(flight.icao24, flight.longitude, flight.latitude)

        # Trail
        if self.show_trails:
            trail_geo = self.trails.get(flight.icao24)
            if len(trail_geo) >= 2:
                trail_px = [
                    self.proj.project(lon, lat) for lon, lat in trail_geo
                ]
                trail_layer = pygame.Surface(
                    self.surface.get_size(), pygame.SRCALPHA
                )
                _draw_trail(
                    trail_layer, trail_px, C_TRAIL_HEAD, C_TRAIL_TAIL
                )
                self.surface.blit(trail_layer, (0, 0))

        # Plane icon
        colour = _plane_colour(flight.velocity)
        _draw_plane_icon(
            self.surface, cx, cy, flight.heading, colour
        )

        # Labels
        if self.show_labels:
            self._draw_label(label_surf, flight, cx, cy, colour)

    def _draw_label(
        self,
        surf: pygame.Surface,
        flight: Flight,
        cx: int,
        cy: int,
        colour: tuple[int, int, int],
    ) -> None:
        """Draw callsign + altitude tag near the plane icon."""
        # Build or retrieve cached label surfaces
        if flight.icao24 not in self._label_cache:
            callsign = flight.callsign or flight.icao24.upper()
            alt_ft   = int(flight.altitude * 3.28084)     # metres → feet
            cs_surf  = self._font_label.render(callsign, True, C_LABEL_CALL)
            alt_surf = self._font_label.render(
                f"FL{alt_ft // 100:03d}", True, C_LABEL_ALT
            )
            self._label_cache[flight.icao24] = (cs_surf, alt_surf)

        cs_surf, alt_surf = self._label_cache[flight.icao24]

        ox, oy = 10, -18          # offset from plane centre
        surf.blit(cs_surf,  (cx + ox, cy + oy))
        surf.blit(alt_surf, (cx + ox, cy + oy + LABEL_FONT_SIZE + 1))

        # Tiny connector line from label to plane
        lx = cx + ox - 2
        ly = cy + oy + LABEL_FONT_SIZE
        pygame.draw.line(surf, (*colour, 80), (cx, cy), (lx, ly), 1)

    def invalidate_label_cache(self) -> None:
        """Call when flights are refreshed from API to clear stale labels."""
        self._label_cache.clear()

    def resize(self, new_w: int, new_h: int) -> None:
        """Handle window resize — update projector and clear bg cache."""
        self.proj    = Projector(self.bbox, new_w, new_h)
        self._bg_surf = None

    def set_bbox(self, bbox: tuple[float, float, float, float]) -> None:
        """Change the geographic bounding box at runtime."""
        self.bbox = bbox
        w, h = self.surface.get_size()
        self.proj = Projector(bbox, w, h)
        self.trails = TrailStore()              # trails no longer valid
        self._label_cache.clear()