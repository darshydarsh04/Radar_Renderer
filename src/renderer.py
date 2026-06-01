"""
renderer.py — Flight Wallpaper Renderer

Layout:
  LEFT PANEL  (35% of screen width) — flight list, stats, location info
  RIGHT AREA  (65% of screen width) — circular radar, slightly right-of-centre

Radar is a clipped circle. Only flights inside the circle radius are shown
on the radar. The left panel lists ALL flights in the bbox with details.

To change location at runtime, call renderer.set_bbox(...) or pass a
LOCATION name from the LOCATIONS dict in config.

Visual style: deep navy, cyan radar, phosphor trails, monospace HUD.
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
# Built-in location presets — change location by name
# ---------------------------------------------------------------------------

LOCATIONS: dict[str, tuple[str, tuple[float, float, float, float]]] = {
    "dubai":    ("DUBAI / UAE",        (22.0, 45.0, 30.0, 60.0)),
    "london":   ("LONDON / UK",        (49.0, -6.0, 53.5,  3.0)),
    "newyork":  ("NEW YORK / USA",     (39.0,-76.0, 42.5,-71.0)),
    "tokyo":    ("TOKYO / JAPAN",      (33.0,136.0, 37.0,142.0)),
    "paris":    ("PARIS / FRANCE",     (47.0,  0.5, 50.0,  5.5)),
    "sydney":   ("SYDNEY / AUSTRALIA", (-36.0,148.0,-31.0,153.0)),
    "singapore":("SINGAPORE",          (  1.0,102.0,  2.5,105.0)),
    "edinburgh":("EDINBURGH AIRPORT",  (55.5, -4.5, 56.0, -3.0)),
}

DEFAULT_LOCATION = "edinburgh"


# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------

C_BG            = (4,   8,  24)
C_BG2           = (8,  18,  40)
C_PANEL_BG      = (6,  12,  30)
C_PANEL_BORDER  = (18,  50,  90)
C_GRID          = (14,  34,  62)
C_RING          = (16,  44,  82)
C_RING_BRIGHT   = (0,   80, 140)
C_PULSE         = (0,  160, 220)
C_TRAIL_HEAD    = (0,  220, 180)
C_TRAIL_TAIL    = (0,   50,  40)
C_PLANE         = (0,  220, 255)
C_PLANE_FAST    = (80, 255, 180)
C_PLANE_SLOW    = (255, 180,  40)
C_LABEL_CALL    = (160, 230, 255)
C_LABEL_ALT     = (70,  150, 130)
C_HUD_PRIMARY   = (0,  200, 255)
C_HUD_DIM       = (40, 100, 130)
C_HUD_MID       = (80, 160, 180)
C_SCAN          = (0,  180, 255)
C_DIVIDER       = (20,  55,  95)
C_SELECTED      = (255, 220,  60)
C_CLIP_MASK     = (4,   8,  24)   # same as bg — used to erase outside circle

TRAIL_LENGTH    = 20
TRAIL_MIN_DIST  = 0.0005
LABEL_FONT_SIZE = 10
HUD_FONT_SIZE   = 12
HUD_TITLE_SIZE  = 22
PANEL_FONT_SIZE = 11
PANEL_TITLE_SIZE= 13

SPEED_FAST = 220
SPEED_SLOW = 60

# Left panel takes this fraction of screen width
PANEL_RATIO = 0.32


# ---------------------------------------------------------------------------
# TrailStore
# ---------------------------------------------------------------------------

@dataclass
class TrailStore:
    max_length: int = TRAIL_LENGTH
    _data: dict[str, list[tuple[float, float]]] = field(
        default_factory=dict, repr=False
    )

    def update(self, icao24: str, lon: float, lat: float) -> None:
        trail = self._data.setdefault(icao24, [])
        if trail:
            dist = math.hypot(lon - trail[-1][0], lat - trail[-1][1])
            if dist < TRAIL_MIN_DIST:
                return
        trail.append((lon, lat))
        if len(trail) > self.max_length:
            trail.pop(0)

    def get(self, icao24: str) -> list[tuple[float, float]]:
        return self._data.get(icao24, [])

    def prune(self, active: set[str]) -> None:
        for k in set(self._data) - active:
            del self._data[k]


# ---------------------------------------------------------------------------
# Projector — maps geo coords onto the RADAR CIRCLE area only
# ---------------------------------------------------------------------------

class Projector:
    """
    Projects geo coords into the radar circle.

    The radar circle is centred at (radar_cx, radar_cy) with radius radar_r.
    The bbox centre maps to the circle centre; bbox edges map to the radius.
    """

    def __init__(
        self,
        bbox: tuple[float, float, float, float],
        radar_cx: int,
        radar_cy: int,
        radar_r:  int,
    ) -> None:
        self.lat_min, self.lon_min, self.lat_max, self.lon_max = bbox
        self.radar_cx = radar_cx
        self.radar_cy = radar_cy
        self.radar_r  = radar_r

        self._mid_lon = (self.lon_min + self.lon_max) / 2
        self._mid_lat = (self.lat_min + self.lat_max) / 2
        self._span_lon = (self.lon_max - self.lon_min) / 2   # half-span
        self._span_lat = (self.lat_max - self.lat_min) / 2

    def project(self, lon: float, lat: float) -> tuple[int, int]:
        nx = (lon - self._mid_lon) / self._span_lon   # -1..1
        ny = (lat - self._mid_lat) / self._span_lat   # -1..1
        x = self.radar_cx + int(nx * self.radar_r)
        y = self.radar_cy - int(ny * self.radar_r)    # y flipped
        return x, y

    def in_radar(self, lon: float, lat: float) -> bool:
        """Returns True if the point falls inside the radar circle."""
        x, y = self.project(lon, lat)
        dx, dy = x - self.radar_cx, y - self.radar_cy
        return math.hypot(dx, dy) <= self.radar_r

    def centre(self) -> tuple[int, int]:
        return self.radar_cx, self.radar_cy


# ---------------------------------------------------------------------------
# Drawing primitives
# ---------------------------------------------------------------------------

def _lerp_colour(c1, c2, t):
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def _plane_colour(velocity: float):
    if velocity >= SPEED_FAST:
        return C_PLANE_FAST
    if velocity <= SPEED_SLOW:
        return C_PLANE_SLOW
    return C_PLANE


def _draw_plane_icon(surface, cx, cy, heading_deg, colour, size=7):
    half = size
    tip   = (0, -half * 1.6)
    lwing = (-half, half * 0.4)
    tail  = (0,  half * 0.6)
    rwing = ( half, half * 0.4)
    rad = math.radians(heading_deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)

    def rot(px, py):
        return int(cx + px * cos_a - py * sin_a), int(cy + px * sin_a + py * cos_a)

    pts = [rot(*tip), rot(*lwing), rot(*tail), rot(*rwing)]
    pygame.draw.polygon(surface, colour, pts)
    pygame.draw.polygon(surface, _lerp_colour(colour, (255,255,255), 0.4), pts, 1)
    nx, ny = rot(*tip)
    pygame.gfxdraw.filled_circle(surface, nx, ny, 2, (*colour, 200))


def _draw_trail(surface, points, c_head, c_tail):
    n = len(points)
    if n < 2:
        return
    for i in range(1, n):
        t = i / (n - 1)
        col = _lerp_colour(c_tail, c_head, t)
        alpha = int(30 + 170 * t)
        pygame.draw.line(surface, (*col, alpha), points[i-1], points[i], 1)


# ---------------------------------------------------------------------------
# Radar circle drawing
# ---------------------------------------------------------------------------

def _draw_radar(
    surface: pygame.Surface,
    cx: int, cy: int, r: int,
    pulse_t: float,
    scan_angle: float,
) -> None:
    """Draw the full radar circle: rings, grid lines, sweep, pulse."""
    w, h = surface.get_size()
    radar_surf = pygame.Surface((w, h), pygame.SRCALPHA)

    # Concentric rings
    for i in range(1, 5):
        ring_r = int(r * i / 4)
        alpha = 30 + i * 15
        pygame.gfxdraw.aacircle(radar_surf, cx, cy, ring_r, (*C_RING, alpha))

    # Outer ring — bright
    pygame.gfxdraw.aacircle(radar_surf, cx, cy, r,     (*C_RING_BRIGHT, 180))
    pygame.gfxdraw.aacircle(radar_surf, cx, cy, r - 1, (*C_RING_BRIGHT, 80))

    # Cross-hair lines inside circle
    pygame.draw.line(radar_surf, (*C_GRID, 60), (cx - r, cy), (cx + r, cy), 1)
    pygame.draw.line(radar_surf, (*C_GRID, 60), (cx, cy - r), (cx, cy + r), 1)
    # Diagonal cross
    d = int(r * 0.707)
    pygame.draw.line(radar_surf, (*C_GRID, 30), (cx-d, cy-d), (cx+d, cy+d), 1)
    pygame.draw.line(radar_surf, (*C_GRID, 30), (cx+d, cy-d), (cx-d, cy+d), 1)

    # Animated pulse ring
    pulse_r = int(r * 0.1 + pulse_t * r * 0.9)
    pulse_a = int((1 - pulse_t) * 100)
    if pulse_a > 0:
        pygame.gfxdraw.aacircle(radar_surf, cx, cy, pulse_r, (*C_PULSE, pulse_a))

    # Sweep wedge
    for i in range(40):
        t = i / 40
        deg = scan_angle - t * 70
        rad = math.radians(deg)
        ex = cx + int(r * math.sin(rad))
        ey = cy - int(r * math.cos(rad))
        a  = int((1 - t) * 35)
        if a > 0:
            pygame.draw.line(radar_surf, (*C_SCAN, a), (cx, cy), (ex, ey), 2)

    # Bright sweep line
    rad = math.radians(scan_angle)
    ex  = cx + int(r * math.sin(rad))
    ey  = cy - int(r * math.cos(rad))
    pygame.draw.line(radar_surf, (*C_SCAN, 90), (cx, cy), (ex, ey), 1)

    # Centre dot
    pygame.gfxdraw.filled_circle(radar_surf, cx, cy, 5, (*C_HUD_PRIMARY, 200))
    pygame.gfxdraw.aacircle(radar_surf, cx, cy, 5, (*C_HUD_PRIMARY, 255))

    surface.blit(radar_surf, (0, 0))


def _clip_to_circle(surface: pygame.Surface, cx: int, cy: int, r: int) -> None:
    """
    Erase everything outside the radar circle by drawing the inverse mask.
    Uses the background colour so planes/trails outside are hidden.
    """
    w, h = surface.get_size()
    mask = pygame.Surface((w, h), pygame.SRCALPHA)
    mask.fill((0, 0, 0, 0))

    # Fill entire mask opaque
    mask.fill((*C_BG, 255))

    # Cut out the circle — fill with transparent
    pygame.gfxdraw.filled_circle(mask, cx, cy, r, (0, 0, 0, 0))
    # Small antialiased border ring to soften the edge
    for dr in range(3):
        a = 255 - dr * 80
        pygame.gfxdraw.aacircle(mask, cx, cy, r - dr, (*C_BG, a))

    surface.blit(mask, (0, 0))


# ---------------------------------------------------------------------------
# Left panel
# ---------------------------------------------------------------------------

def _draw_left_panel(
    surface: pygame.Surface,
    font_title: pygame.font.Font,
    font_panel: pygame.font.Font,
    font_dim:   pygame.font.Font,
    flights: list,
    bbox: tuple,
    location_name: str,
    fps: float,
    panel_w: int,
) -> None:
    """Draw the full left panel: title, stats, divider, flight list."""
    h = surface.get_size()[1]
    pad = 22
    line_h = PANEL_FONT_SIZE + 7

    # Panel background
    panel = pygame.Surface((panel_w, h), pygame.SRCALPHA)
    panel.fill((*C_PANEL_BG, 220))
    surface.blit(panel, (0, 0))

    # Right border
    pygame.draw.line(surface, C_PANEL_BORDER, (panel_w - 1, 0), (panel_w - 1, h), 1)
    pygame.draw.line(surface, C_DIVIDER,      (panel_w - 2, 0), (panel_w - 2, h), 1)

    y = pad

    # ── Title ──
    title_surf = font_title.render("FLIGHT", True, C_HUD_PRIMARY)
    surface.blit(title_surf, (pad, y))
    y += HUD_TITLE_SIZE + 2
    title2_surf = font_title.render("RADAR", True, C_HUD_PRIMARY)
    surface.blit(title2_surf, (pad, y))
    y += HUD_TITLE_SIZE + 10

    # Location name
    loc_surf = font_panel.render(location_name, True, C_HUD_MID)
    surface.blit(loc_surf, (pad, y))
    y += line_h + 4

    # ── Divider ──
    pygame.draw.line(surface, C_DIVIDER, (pad, y), (panel_w - pad, y), 1)
    y += 10

    # ── Stats ──
    now = time.strftime("%H:%M:%S UTC", time.gmtime())
    lat_min, lon_min, lat_max, lon_max = bbox

    stats = [
        (f"{len(flights):>3} AIRCRAFT",    C_LABEL_CALL),
        (now,                               C_HUD_DIM),
        (f"LAT  {lat_min:.1f}° – {lat_max:.1f}°", C_HUD_DIM),
        (f"LON  {lon_min:.1f}° – {lon_max:.1f}°", C_HUD_DIM),
        (f"FPS  {fps:>5.1f}",               C_HUD_DIM),
    ]
    for text, col in stats:
        s = font_dim.render(text, True, col)
        surface.blit(s, (pad, y))
        y += line_h

    y += 6
    pygame.draw.line(surface, C_DIVIDER, (pad, y), (panel_w - pad, y), 1)
    y += 10

    # ── Legend ──
    legend_items = [
        ("▸ FAST  >220 m/s", C_PLANE_FAST),
        ("▸ CRUISE",         C_PLANE),
        ("▸ SLOW  <60 m/s",  C_PLANE_SLOW),
    ]
    for text, col in legend_items:
        s = font_dim.render(text, True, col)
        surface.blit(s, (pad, y))
        y += line_h

    y += 6
    pygame.draw.line(surface, C_DIVIDER, (pad, y), (panel_w - pad, y), 1)
    y += 12

    # ── Flight list header ──
    hdr = font_panel.render("CALLSIGN   FL    HDG   SPD", True, C_HUD_MID)
    surface.blit(hdr, (pad, y))
    y += line_h + 2
    pygame.draw.line(surface, C_DIVIDER, (pad, y), (panel_w - pad, y), 1)
    y += 6

    # ── Flight rows ──
    max_rows = (h - y - pad) // line_h
    visible  = flights[:max_rows]

    for f in visible:
        callsign = (f.callsign or f.icao24.upper())[:8].ljust(8)
        alt_ft   = int(f.altitude * 3.28084)
        fl       = f"FL{alt_ft // 100:03d}"
        hdg      = f"{int(f.heading):>3}°"
        spd      = f"{int(f.velocity):>3}"
        row      = f"{callsign}  {fl}  {hdg}  {spd}"
        col      = _plane_colour(f.velocity)
        s        = font_dim.render(row, True, col)
        surface.blit(s, (pad, y))
        y += line_h
        if y + line_h > h - pad:
            # Overflow indicator
            more = font_dim.render(
                f"  +{len(flights) - len(visible)} more...", True, C_HUD_DIM
            )
            surface.blit(more, (pad, y))
            break

    # ── Bottom: location change hint ──
    hint1 = font_dim.render("Change location:", True, C_HUD_DIM)
    hint2 = font_dim.render("set_bbox() or LOCATIONS", True, C_DIVIDER)
    surface.blit(hint1, (pad, h - pad - line_h * 2))
    surface.blit(hint2, (pad, h - pad - line_h))


# ---------------------------------------------------------------------------
# Main Renderer
# ---------------------------------------------------------------------------

class Renderer:
    """
    Split-layout flight radar renderer.

    Left panel  — flight list and stats
    Right area  — circular radar centred slightly right of screen centre

    Change location:
        renderer.set_location("london")
        renderer.set_bbox((lat_min, lon_min, lat_max, lon_max), "MY CITY")
    """

    def __init__(
        self,
        surface: pygame.Surface,
        location: str = DEFAULT_LOCATION,
        show_labels: bool = True,
        show_trails: bool = True,
    ) -> None:
        self.surface     = surface
        self.show_labels = show_labels
        self.show_trails = show_trails

        loc_name, bbox   = LOCATIONS.get(location, LOCATIONS[DEFAULT_LOCATION])
        self.bbox        = bbox
        self.location_name = loc_name

        self.trails      = TrailStore()
        self._scan_angle = 0.0
        self._pulse_t    = 0.0
        self._bg_surf: pygame.Surface | None = None
        self._label_cache: dict = {}
        self._fps_clock  = pygame.time.Clock()
        self._fps        = 0.0

        pygame.font.init()
        mono = pygame.font.match_font(
            "dejavusansmono,liberationmono,ubuntumono,monospace,courier"
        )
        self._font_label = pygame.font.Font(mono, LABEL_FONT_SIZE)
        self._font_hud   = pygame.font.Font(mono, HUD_FONT_SIZE)
        self._font_panel = pygame.font.Font(mono, PANEL_FONT_SIZE)
        self._font_ptitle= pygame.font.Font(mono, PANEL_TITLE_SIZE)
        self._font_title = pygame.font.Font(mono, HUD_TITLE_SIZE)

        self._update_layout()

    # ------------------------------------------------------------------
    # Layout — recalculate radar position/size from surface dimensions
    # ------------------------------------------------------------------

    def _update_layout(self) -> None:
        w, h = self.surface.get_size()
        self._panel_w  = int(w * PANEL_RATIO)
        radar_area_w   = w - self._panel_w
        # Radar circle: use 88% of the smaller of radar area width or height
        self._radar_r  = int(min(radar_area_w, h) * 0.44)
        # Centre: horizontally centred in right area, vertically centred
        self._radar_cx = self._panel_w + radar_area_w // 2
        self._radar_cy = h // 2
        self._proj     = Projector(
            self.bbox, self._radar_cx, self._radar_cy, self._radar_r
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_location(self, name: str) -> None:
        """
        Switch to a named preset location.

        Available: dubai, london, newyork, tokyo, paris, sydney, singapore
        Example:   renderer.set_location("london")
        """
        if name not in LOCATIONS:
            print(f"[renderer] Unknown location '{name}'. Available: {list(LOCATIONS)}")
            return
        loc_name, bbox = LOCATIONS[name]
        self.set_bbox(bbox, loc_name)

    def set_bbox(
        self,
        bbox: tuple[float, float, float, float],
        label: str = "CUSTOM",
    ) -> None:
        """
        Set a custom bounding box.

        bbox format: (lat_min, lon_min, lat_max, lon_max)
        Example: renderer.set_bbox((51.3, -0.6, 51.8, 0.3), "LONDON CLOSE")
        """
        self.bbox          = bbox
        self.location_name = label
        self._update_layout()
        self.trails        = TrailStore()
        self._label_cache.clear()

    def draw(self, flights: list) -> None:
        """Main draw call — once per frame."""
        w, h = self.surface.get_size()
        self._tick_animation()

        # 1 — Background
        self._draw_bg(w, h)

        # 2 — Flight trails (drawn before circle overlay clips them)
        trail_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        active_ids: set[str] = set()

        for flight in flights:
            active_ids.add(flight.icao24)
            self.trails.update(flight.icao24, flight.longitude, flight.latitude)
            if self.show_trails and self._proj.in_radar(flight.longitude, flight.latitude):
                trail_geo = self.trails.get(flight.icao24)
                if len(trail_geo) >= 2:
                    trail_px = [self._proj.project(lon, lat) for lon, lat in trail_geo]
                    _draw_trail(trail_surf, trail_px, C_TRAIL_HEAD, C_TRAIL_TAIL)

        self.surface.blit(trail_surf, (0, 0))

        # 3 — Clip everything to circle (erases trails outside radius)
        _clip_to_circle(self.surface, self._radar_cx, self._radar_cy, self._radar_r)

        # 4 — Radar rings, sweep, pulse (on top of clipped trails)
        _draw_radar(
            self.surface,
            self._radar_cx, self._radar_cy, self._radar_r,
            self._pulse_t, self._scan_angle,
        )

        # 5 — Plane icons + labels (only inside circle)
        label_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        for flight in flights:
            if self._proj.in_radar(flight.longitude, flight.latitude):
                self._draw_flight(label_surf, flight)
        self.surface.blit(label_surf, (0, 0))

        # Prune stale trails
        self.trails.prune(active_ids)

        # 6 — Left panel (drawn last — always on top)
        _draw_left_panel(
            self.surface,
            self._font_title,
            self._font_ptitle,
            self._font_panel,
            flights,
            self.bbox,
            self.location_name,
            self._fps,
            self._panel_w,
        )

        self._fps = self._fps_clock.get_fps()
        self._fps_clock.tick()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _draw_bg(self, w: int, h: int) -> None:
        if self._bg_surf is None or self._bg_surf.get_size() != (w, h):
            self._bg_surf = pygame.Surface((w, h))
            for y in range(h):
                t = y / h
                col = _lerp_colour(C_BG, C_BG2, t)
                pygame.draw.line(self._bg_surf, col, (0, y), (w, y))
        self.surface.blit(self._bg_surf, (0, 0))

    def _tick_animation(self) -> None:
        self._scan_angle = (self._scan_angle + 0.7) % 360
        self._pulse_t    = (self._pulse_t + 0.003) % 1.0

    def _draw_flight(self, label_surf: pygame.Surface, flight) -> None:
        cx, cy = self._proj.project(flight.longitude, flight.latitude)
        colour = _plane_colour(flight.velocity)
        _draw_plane_icon(self.surface, cx, cy, flight.heading, colour)
        if self.show_labels:
            self._draw_label(label_surf, flight, cx, cy, colour)

    def _draw_label(self, surf, flight, cx, cy, colour) -> None:
        if flight.icao24 not in self._label_cache:
            cs  = (flight.callsign or flight.icao24.upper())
            alt = int(flight.altitude * 3.28084)
            cs_s  = self._font_label.render(cs, True, C_LABEL_CALL)
            alt_s = self._font_label.render(f"FL{alt//100:03d}", True, C_LABEL_ALT)
            self._label_cache[flight.icao24] = (cs_s, alt_s)
        cs_s, alt_s = self._label_cache[flight.icao24]
        ox, oy = 10, -16
        surf.blit(cs_s,  (cx + ox, cy + oy))
        surf.blit(alt_s, (cx + ox, cy + oy + LABEL_FONT_SIZE + 2))
        pygame.draw.line(surf, (*colour, 60), (cx, cy), (cx + ox - 2, cy + oy + LABEL_FONT_SIZE), 1)

    def invalidate_label_cache(self) -> None:
        self._label_cache.clear()

    def resize(self, new_w: int, new_h: int) -> None:
        self._bg_surf = None
        self._update_layout()