"""
renderer.py — Flight Wallpaper Renderer

Layout:
  LEFT PANEL (32% width) — flight list, route info, stats, legend, key hints
  RIGHT AREA (68% width) — circular radar with city silhouette background

Features:
  - zoom() / pan()     — zoom and pan the bbox
  - City silhouette    — rough polygon skyline behind radar circle
  - Compass rose       — N/S/E/W inside the radar circle
  - 0-key toggle       — switches between city/regional and airport close-up presets

Layers (bottom → top):
  1.  Background gradient
  2.  City silhouette      (inside radar circle only)
  3.  Flight trails        (clipped to radar circle)
  4.  Circle clip mask     (erase outside circle)
  5.  Radar rings/sweep/pulse
  6.  Compass rose
  7.  Route lines
  8.  Airport icons + labels
  9.  Plane icons + labels
  10. Left panel
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Optional

import pygame
import pygame.gfxdraw


# ---------------------------------------------------------------------------
# Location presets — two tiers toggled by 0 key
# ---------------------------------------------------------------------------

CITY_LOCATIONS: dict[str, tuple[str, tuple[float, float, float, float]]] = {
    "dubai":     ("DUBAI / UAE",        (22.0,  45.0,  30.0,  60.0)),
    "london":    ("LONDON / UK",        (49.0,  -6.0,  53.5,   3.0)),
    "newyork":   ("NEW YORK / USA",     (39.0, -76.0,  42.5, -71.0)),
    "tokyo":     ("TOKYO / JAPAN",      (33.0, 136.0,  37.0, 142.0)),
    "paris":     ("PARIS / FRANCE",     (47.0,   0.5,  50.0,   5.5)),
    "sydney":    ("SYDNEY / AUSTRALIA", (-36.0,148.0, -31.0, 153.0)),
    "singapore": ("SINGAPORE",          (  1.0, 102.0,  2.5, 105.0)),
}

AIRPORT_LOCATIONS: dict[str, tuple[str, tuple[float, float, float, float]]] = {
    "dubai":     ("DUBAI INT'L — OMDB",    (25.10, 55.20, 25.45, 55.55)),
    "london":    ("HEATHROW — EGLL",       (51.42, -0.52, 51.60, -0.28)),
    "newyork":   ("JFK — KJFK",            (40.60,-73.92, 40.78,-73.72)),
    "tokyo":     ("NARITA — RJAA",         (35.72,140.33, 35.88,140.52)),
    "paris":     ("PARIS CDG — LFPG",      (48.96,  2.44, 49.08,  2.62)),
    "sydney":    ("SYDNEY — YSSY",         (-34.00,150.98,-33.88,151.26)),
    "singapore": ("CHANGI — WSSS",         (  1.32,103.96,  1.40,104.00)),
}

DEFAULT_LOCATION = "dubai"

# Unified dict for convenience — renderer uses CITY_LOCATIONS and AIRPORT_LOCATIONS
LOCATIONS = CITY_LOCATIONS


# ---------------------------------------------------------------------------
# City silhouette data
# Stored as relative (x, y) coordinates in range -1..1 (unit circle space)
# These are rough skyline polygons — buildings + ground line
# Each entry: list of (nx, ny) where nx=-1=west, nx=1=east, ny=-1=south, ny=1=north
# ---------------------------------------------------------------------------

CITY_SILHOUETTES: dict[str, list[tuple[float, float]]] = {
    "dubai": [
        # Ground line + Burj Khalifa silhouette area (rough)
        (-1.0, -0.85),
        (-0.85,-0.85),(-0.85,-0.70),(-0.80,-0.70),(-0.80,-0.60),
        (-0.72,-0.60),(-0.72,-0.50),(-0.65,-0.50),(-0.65,-0.65),
        (-0.55,-0.65),(-0.55,-0.72),(-0.40,-0.72),(-0.40,-0.55),
        (-0.28,-0.55),(-0.28,-0.45),(-0.18,-0.45),(-0.18,-0.35),
        (-0.12,-0.35),(-0.12,-0.20),(-0.08,-0.20),(-0.08,-0.05),  # Burj Khalifa
        (-0.06,-0.05),(-0.06,-0.25),
        ( 0.00,-0.25),( 0.00,-0.50),
        ( 0.08,-0.50),( 0.08,-0.38),
        ( 0.18,-0.38),( 0.18,-0.55),
        ( 0.30,-0.55),( 0.30,-0.62),
        ( 0.45,-0.62),( 0.45,-0.70),
        ( 0.60,-0.70),( 0.60,-0.75),
        ( 0.75,-0.75),( 0.75,-0.80),
        ( 1.00,-0.80),(1.00,-0.85),
    ],
    "london": [
        (-1.0, -0.85),
        (-0.80,-0.85),(-0.80,-0.75),(-0.70,-0.75),(-0.70,-0.65),
        (-0.60,-0.65),(-0.60,-0.55),(-0.50,-0.55),(-0.50,-0.60),
        (-0.40,-0.60),(-0.40,-0.40),  # The Shard area
        (-0.35,-0.40),(-0.35,-0.15),(-0.32,-0.15),(-0.32,-0.05),  # Shard spike
        (-0.30,-0.05),(-0.30,-0.35),
        (-0.20,-0.35),(-0.20,-0.50),
        (-0.10,-0.50),(-0.10,-0.42),
        ( 0.00,-0.42),( 0.00,-0.60),
        ( 0.12,-0.60),( 0.12,-0.50),  # Gherkin
        ( 0.16,-0.50),( 0.16,-0.30),
        ( 0.18,-0.30),( 0.18,-0.52),
        ( 0.28,-0.52),( 0.28,-0.65),
        ( 0.45,-0.65),( 0.45,-0.70),
        ( 0.65,-0.70),( 0.65,-0.78),
        ( 1.00,-0.78),(1.00,-0.85),
    ],
    "newyork": [
        (-1.0, -0.85),
        (-0.70,-0.85),(-0.70,-0.65),
        (-0.60,-0.65),(-0.60,-0.40),(-0.56,-0.40),(-0.56,-0.20),  # Empire State
        (-0.54,-0.20),(-0.54,-0.40),
        (-0.45,-0.40),(-0.45,-0.50),
        (-0.35,-0.50),(-0.35,-0.30),
        (-0.28,-0.30),(-0.28,-0.45),
        (-0.18,-0.45),(-0.18,-0.25),
        (-0.12,-0.25),(-0.12,-0.42),
        (-0.02,-0.42),(-0.02,-0.35),
        ( 0.06,-0.35),( 0.06,-0.22),  # One WTC
        ( 0.09,-0.22),( 0.09,-0.40),
        ( 0.18,-0.40),( 0.18,-0.52),
        ( 0.30,-0.52),( 0.30,-0.45),
        ( 0.42,-0.45),( 0.42,-0.60),
        ( 0.58,-0.60),( 0.58,-0.70),
        ( 1.00,-0.70),(1.00,-0.85),
    ],
    "tokyo": [
        (-1.0, -0.85),
        (-0.75,-0.85),(-0.75,-0.72),(-0.60,-0.72),(-0.60,-0.60),
        (-0.48,-0.60),(-0.48,-0.50),(-0.38,-0.50),(-0.38,-0.35),
        (-0.30,-0.35),(-0.30,-0.15),(-0.27,-0.15),(-0.27, 0.10),  # Tokyo Tower/Skytree
        (-0.25, 0.10),(-0.25,-0.20),
        (-0.18,-0.20),(-0.18,-0.40),
        (-0.08,-0.40),(-0.08,-0.30),
        ( 0.02,-0.30),( 0.02,-0.45),
        ( 0.12,-0.45),( 0.12,-0.35),
        ( 0.22,-0.35),( 0.22,-0.55),
        ( 0.35,-0.55),( 0.35,-0.65),
        ( 0.55,-0.65),( 0.55,-0.72),
        ( 0.75,-0.72),( 0.75,-0.78),
        ( 1.00,-0.78),(1.00,-0.85),
    ],
    "paris": [
        (-1.0, -0.85),
        (-0.70,-0.85),(-0.70,-0.72),(-0.55,-0.72),(-0.55,-0.60),
        (-0.42,-0.60),(-0.42,-0.55),
        (-0.30,-0.55),(-0.30,-0.35),(-0.26,-0.35),(-0.26,-0.10),  # Eiffel area
        (-0.24,-0.10),(-0.24, 0.05),(-0.22, 0.05),(-0.22,-0.10),
        (-0.20,-0.10),(-0.20,-0.38),
        (-0.10,-0.38),(-0.10,-0.50),
        ( 0.00,-0.50),( 0.00,-0.42),
        ( 0.10,-0.42),( 0.10,-0.32),
        ( 0.18,-0.32),( 0.18,-0.48),
        ( 0.30,-0.48),( 0.30,-0.58),
        ( 0.50,-0.58),( 0.50,-0.68),
        ( 0.70,-0.68),( 0.70,-0.75),
        ( 1.00,-0.75),(1.00,-0.85),
    ],
    "sydney": [
        (-1.0, -0.85),
        (-0.65,-0.85),(-0.65,-0.72),(-0.50,-0.72),(-0.50,-0.62),
        (-0.38,-0.62),(-0.38,-0.50),(-0.28,-0.50),(-0.28,-0.38),
        (-0.18,-0.38),(-0.18,-0.28),(-0.12,-0.28),(-0.12,-0.18),  # Sydney Tower
        (-0.10,-0.18),(-0.10,-0.30),
        (-0.02,-0.30),(-0.02,-0.42),
        ( 0.08,-0.42),( 0.08,-0.52),
        ( 0.20,-0.52),( 0.20,-0.45),  # Opera House silhouette
        ( 0.26,-0.45),( 0.26,-0.38),
        ( 0.32,-0.38),( 0.32,-0.48),
        ( 0.45,-0.48),( 0.45,-0.60),
        ( 0.65,-0.60),( 0.65,-0.72),
        ( 1.00,-0.72),(1.00,-0.85),
    ],
    "singapore": [
        (-1.0, -0.85),
        (-0.65,-0.85),(-0.65,-0.70),(-0.50,-0.70),(-0.50,-0.55),
        (-0.38,-0.55),(-0.38,-0.40),(-0.28,-0.40),(-0.28,-0.28),
        (-0.18,-0.28),(-0.18,-0.18),  # Marina Bay Sands
        (-0.06,-0.18),(-0.06,-0.30),  # flat top roof
        ( 0.06,-0.30),( 0.06,-0.18),
        ( 0.18,-0.18),( 0.18,-0.30),
        ( 0.28,-0.30),( 0.28,-0.42),
        ( 0.38,-0.42),( 0.38,-0.55),
        ( 0.52,-0.55),( 0.52,-0.65),
        ( 0.70,-0.65),( 0.70,-0.75),
        ( 1.00,-0.75),(1.00,-0.85),
    ],
}
# Fallback silhouette for unknown cities
_DEFAULT_SILHOUETTE = [
    (-1.0,-0.85),(-0.8,-0.85),(-0.8,-0.65),(-0.6,-0.65),(-0.6,-0.50),
    (-0.4,-0.50),(-0.4,-0.40),(-0.2,-0.40),(-0.2,-0.30),(0.0,-0.30),
    (0.0,-0.50),(0.2,-0.50),(0.2,-0.42),(0.4,-0.42),(0.4,-0.55),
    (0.6,-0.55),(0.6,-0.68),(0.8,-0.68),(0.8,-0.78),(1.0,-0.78),(1.0,-0.85),
]


# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------

C_BG             = (4,   8,  24)
C_BG2            = (8,  18,  40)
C_PANEL_BG       = (5,  11,  28)
C_PANEL_BORDER   = (20,  55,  95)
C_DIVIDER        = (16,  42,  72)
C_GRID           = (14,  34,  62)
C_RING           = (16,  44,  82)
C_RING_BRIGHT    = ( 0,  80, 140)
C_PULSE          = ( 0, 160, 220)
C_SCAN           = ( 0, 180, 255)
C_TRAIL_HEAD     = ( 0, 220, 180)
C_TRAIL_TAIL     = ( 0,  50,  40)
C_PLANE          = ( 0, 220, 255)
C_PLANE_FAST     = (80, 255, 180)
C_PLANE_SLOW     = (255, 180,  40)
C_LABEL_CALL     = (160, 230, 255)
C_LABEL_ALT      = ( 70, 150, 130)
C_HUD_PRIMARY    = ( 0, 200, 255)
C_HUD_MID        = ( 80, 160, 180)
C_HUD_DIM        = ( 40, 100, 130)
C_AIRPORT_LARGE  = (255, 200,  60)
C_AIRPORT_MED    = (180, 140,  40)
C_AIRPORT_LABEL  = (200, 160,  40)
C_ROUTE_FLOWN    = ( 80,  80, 160)
C_ROUTE_AHEAD    = (160, 160, 255)
C_ORIGIN_DOT     = ( 80, 255, 120)
C_DEST_DOT       = (255,  80,  80)
C_SILHOUETTE     = (18,  45,  90)   # city building fill — visible against dark bg
C_SILHOUETTE_TOP = (40,  90, 160)   # bright blue-grey top edge
C_COMPASS        = ( 0, 160, 220)   # compass ring + tick marks
C_COMPASS_N      = (255,  80,  80)  # North label (red)
C_COMPASS_LABEL  = (120, 190, 220)  # S/E/W labels

# Sizing
TRAIL_LENGTH     = 20
TRAIL_MIN_DIST   = 0.0005
LABEL_FONT_SIZE  = 10
PANEL_FONT_SIZE  = 11
PANEL_TITLE_SIZE = 13
HUD_TITLE_SIZE   = 22
PANEL_RATIO      = 0.32
SPEED_FAST       = 220
SPEED_SLOW       = 60
MIN_ZOOM_SPAN    = 0.4    # degrees — minimum bbox half-span
MAX_ZOOM_SPAN    = 45.0   # degrees — maximum bbox half-span


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
            if math.hypot(lon - trail[-1][0], lat - trail[-1][1]) < TRAIL_MIN_DIST:
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
# Projector
# ---------------------------------------------------------------------------

class Projector:
    def __init__(
        self,
        bbox: tuple[float, float, float, float],
        radar_cx: int, radar_cy: int, radar_r: int,
    ) -> None:
        self.lat_min, self.lon_min, self.lat_max, self.lon_max = bbox
        self.radar_cx = radar_cx
        self.radar_cy = radar_cy
        self.radar_r  = radar_r
        self._mid_lon  = (self.lon_min + self.lon_max) / 2
        self._mid_lat  = (self.lat_min + self.lat_max) / 2
        self._span_lon = (self.lon_max - self.lon_min) / 2
        self._span_lat = (self.lat_max - self.lat_min) / 2

    def project(self, lon: float, lat: float) -> tuple[int, int]:
        nx = (lon - self._mid_lon) / self._span_lon
        ny = (lat - self._mid_lat) / self._span_lat
        return (
            self.radar_cx + int(nx * self.radar_r),
            self.radar_cy - int(ny * self.radar_r),
        )

    def in_radar(self, lon: float, lat: float) -> bool:
        x, y = self.project(lon, lat)
        return math.hypot(x - self.radar_cx, y - self.radar_cy) <= self.radar_r

    def centre(self) -> tuple[int, int]:
        return self.radar_cx, self.radar_cy


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

def _lerp_colour(c1, c2, t):
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def _plane_colour(velocity: float):
    if velocity >= SPEED_FAST: return C_PLANE_FAST
    if velocity <= SPEED_SLOW: return C_PLANE_SLOW
    return C_PLANE


# ---------------------------------------------------------------------------
# City silhouette
# ---------------------------------------------------------------------------

def _draw_city_silhouette(
    surface: pygame.Surface,
    cx: int, cy: int, r: int,
    city_key: str,
) -> None:
    """
    Draw a rough polygon city skyline clipped inside the radar circle.
    Coordinates are normalised -1..1 in unit circle space.
    The polygon is drawn onto a temp surface, then a circular mask is applied
    so nothing shows outside the radar circle edge.
    """
    raw = CITY_SILHOUETTES.get(city_key, _DEFAULT_SILHOUETTE)

    # Close polygon: extend down past bottom of circle
    pts_raw = raw + [(raw[-1][0], -1.1), (-1.1, -1.1)]

    # Convert unit-circle coords to pixel coords
    pts = [(cx + int(nx * r), cy - int(ny * r)) for nx, ny in pts_raw]
    outline_pts = [(cx + int(nx * r), cy - int(ny * r)) for nx, ny in raw]

    w, h = surface.get_size()

    # Draw silhouette onto its own surface
    sil_surf = pygame.Surface((w, h), pygame.SRCALPHA)
    sil_surf.fill((0, 0, 0, 0))
    if len(pts) >= 3:
        pygame.draw.polygon(sil_surf, (*C_SILHOUETTE, 200), pts)
    if len(outline_pts) >= 2:
        pygame.draw.lines(sil_surf, (*C_SILHOUETTE_TOP, 230), False, outline_pts, 2)

    # Circular clip mask — keep only what is inside the radar circle
    mask_surf = pygame.Surface((w, h), pygame.SRCALPHA)
    mask_surf.fill((0, 0, 0, 0))
    pygame.gfxdraw.filled_circle(mask_surf, cx, cy, r - 1, (255, 255, 255, 255))

    # Apply mask: zero out pixels outside circle
    sil_surf.blit(mask_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)

    surface.blit(sil_surf, (0, 0))


# ---------------------------------------------------------------------------
# Compass rose
# ---------------------------------------------------------------------------

def _draw_compass(
    surface: pygame.Surface,
    cx: int, cy: int, r: int,
    font: pygame.font.Font,
) -> None:
    """
    Draw a compass rose around the outer edge of the radar circle.
    N is red, S/E/W are dim cyan. Tick marks at every 30°.
    """
    compass_surf = pygame.Surface(surface.get_size(), pygame.SRCALPHA)

    outer = r - 4
    inner = r - 14
    label_r = r - 24

    # Tick marks at every 30°, longer ticks at N/S/E/W
    for deg in range(0, 360, 30):
        rad   = math.radians(deg)
        sin_a = math.sin(rad)
        cos_a = math.cos(rad)
        is_cardinal = (deg % 90 == 0)
        tick_in = inner - (6 if is_cardinal else 0)
        alpha   = 200 if is_cardinal else 80

        x1 = cx + int(outer * sin_a)
        y1 = cy - int(outer * cos_a)
        x2 = cx + int(tick_in * sin_a)
        y2 = cy - int(tick_in * cos_a)
        pygame.draw.line(compass_surf, (*C_COMPASS, alpha), (x1, y1), (x2, y2),
                         2 if is_cardinal else 1)

    # Cardinal labels
    labels = {0: ("N", C_COMPASS_N), 90: ("E", C_COMPASS_LABEL),
              180: ("S", C_COMPASS_LABEL), 270: ("W", C_COMPASS_LABEL)}
    for deg, (text, col) in labels.items():
        rad  = math.radians(deg)
        lx   = cx + int(label_r * math.sin(rad))
        ly   = cy - int(label_r * math.cos(rad))
        surf = font.render(text, True, col)
        rx   = lx - surf.get_width()  // 2
        ry   = ly - surf.get_height() // 2
        compass_surf.blit(surf, (rx, ry))

    # Small centre arrow pointing north
    arrow_len = min(r // 6, 28)
    tip_x = cx
    tip_y = cy - arrow_len
    base_l = (cx - 4, cy + 6)
    base_r = (cx + 4, cy + 6)
    pygame.draw.polygon(compass_surf, (*C_COMPASS_N, 180), [(tip_x, tip_y), base_l, base_r])
    pygame.draw.polygon(compass_surf, (*C_COMPASS_N, 100), [(tip_x, tip_y), base_l, base_r], 1)

    surface.blit(compass_surf, (0, 0))


# ---------------------------------------------------------------------------
# Plane icon
# ---------------------------------------------------------------------------

def _draw_plane_icon(surface, cx, cy, heading_deg, colour, size=7):
    half  = size
    tip   = (0, -half * 1.6)
    lwing = (-half, half * 0.4)
    tail  = (0,  half * 0.6)
    rwing = ( half, half * 0.4)
    rad   = math.radians(heading_deg)
    ca, sa = math.cos(rad), math.sin(rad)

    def rot(px, py):
        return int(cx + px*ca - py*sa), int(cy + px*sa + py*ca)

    pts = [rot(*tip), rot(*lwing), rot(*tail), rot(*rwing)]
    pygame.draw.polygon(surface, colour, pts)
    pygame.draw.polygon(surface, _lerp_colour(colour, (255,255,255), 0.4), pts, 1)
    nx, ny = rot(*tip)
    pygame.gfxdraw.filled_circle(surface, nx, ny, 2, (*colour, 200))


# ---------------------------------------------------------------------------
# Trail
# ---------------------------------------------------------------------------

def _draw_trail(surface, points, c_head, c_tail):
    n = len(points)
    if n < 2:
        return
    for i in range(1, n):
        t   = i / (n - 1)
        col = _lerp_colour(c_tail, c_head, t)
        pygame.draw.line(surface, (*col, int(30 + 170*t)), points[i-1], points[i], 1)


# ---------------------------------------------------------------------------
# Radar circle decoration
# ---------------------------------------------------------------------------

def _draw_radar(surface, cx, cy, r, pulse_t, scan_angle):
    w, h = surface.get_size()
    s = pygame.Surface((w, h), pygame.SRCALPHA)

    for i in range(1, 5):
        rr = int(r * i / 4)
        pygame.gfxdraw.aacircle(s, cx, cy, rr, (*C_RING, 25 + i*12))
    pygame.gfxdraw.aacircle(s, cx, cy, r,     (*C_RING_BRIGHT, 180))
    pygame.gfxdraw.aacircle(s, cx, cy, r - 1, (*C_RING_BRIGHT,  60))

    pygame.draw.line(s, (*C_GRID, 50), (cx-r, cy), (cx+r, cy), 1)
    pygame.draw.line(s, (*C_GRID, 50), (cx, cy-r), (cx, cy+r), 1)
    d = int(r * 0.707)
    pygame.draw.line(s, (*C_GRID, 22), (cx-d,cy-d),(cx+d,cy+d), 1)
    pygame.draw.line(s, (*C_GRID, 22), (cx+d,cy-d),(cx-d,cy+d), 1)

    pr = int(r * 0.1 + pulse_t * r * 0.9)
    pa = int((1 - pulse_t) * 90)
    if pa > 0:
        pygame.gfxdraw.aacircle(s, cx, cy, pr, (*C_PULSE, pa))

    for i in range(40):
        t   = i / 40
        deg = scan_angle - t * 70
        rad = math.radians(deg)
        ex  = cx + int(r * math.sin(rad))
        ey  = cy - int(r * math.cos(rad))
        a   = int((1 - t) * 32)
        if a > 0:
            pygame.draw.line(s, (*C_SCAN, a), (cx, cy), (ex, ey), 2)

    rad = math.radians(scan_angle)
    pygame.draw.line(
        s, (*C_SCAN, 85), (cx, cy),
        (cx + int(r*math.sin(rad)), cy - int(r*math.cos(rad))), 1
    )
    pygame.gfxdraw.filled_circle(s, cx, cy, 5, (*C_HUD_PRIMARY, 200))
    pygame.gfxdraw.aacircle(s, cx, cy, 5, (*C_HUD_PRIMARY, 255))

    surface.blit(s, (0, 0))


# ---------------------------------------------------------------------------
# Circle clip mask
# ---------------------------------------------------------------------------

def _clip_to_circle(surface, cx, cy, r):
    w, h = surface.get_size()
    mask = pygame.Surface((w, h), pygame.SRCALPHA)
    mask.fill((*C_BG, 255))
    pygame.gfxdraw.filled_circle(mask, cx, cy, r, (0, 0, 0, 0))
    for dr in range(3):
        pygame.gfxdraw.aacircle(mask, cx, cy, r-dr, (*C_BG, 255-dr*80))
    surface.blit(mask, (0, 0))


# ---------------------------------------------------------------------------
# Airport icons
# ---------------------------------------------------------------------------

def _draw_airports(surface, proj, airports, font):
    s = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    for apt in airports:
        if not proj.in_radar(apt.longitude, apt.latitude):
            continue
        cx, cy = proj.project(apt.longitude, apt.latitude)
        col    = C_AIRPORT_LARGE if apt.is_major else C_AIRPORT_MED
        rr     = 5 if apt.is_major else 3
        pygame.gfxdraw.aacircle(s, cx, cy, rr+2, (*col, 100))
        pygame.gfxdraw.filled_circle(s, cx, cy, rr, (*col, 200))
        pygame.gfxdraw.aacircle(s, cx, cy, rr, (*col, 255))
        label = font.render(apt.icao, True, C_AIRPORT_LABEL)
        s.blit(label, (cx + rr + 4, cy - 5))
    surface.blit(s, (0, 0))


# ---------------------------------------------------------------------------
# Route lines
# ---------------------------------------------------------------------------

def _draw_route_line(surface, proj, flight_lon, flight_lat,
                     origin_icao, dest_icao, airport_db):
    w, h = surface.get_size()
    s    = pygame.Surface((w, h), pygame.SRCALPHA)
    fx, fy = proj.project(flight_lon, flight_lat)
    cx, cy = proj.centre()
    r      = proj.radar_r

    def clamp(x, y):
        dx, dy = x - cx, y - cy
        dist   = math.hypot(dx, dy)
        if dist <= r:
            return x, y
        sc = (r - 2) / dist
        return int(cx + dx*sc), int(cy + dy*sc)

    origin = airport_db.get(origin_icao) if airport_db else None
    dest   = airport_db.get(dest_icao)   if airport_db else None

    if origin:
        ox, oy = clamp(*proj.project(origin.longitude, origin.latitude))
        pygame.draw.line(s, (*C_ROUTE_FLOWN, 50), (ox, oy), (fx, fy), 1)
        pygame.gfxdraw.filled_circle(s, ox, oy, 4, (*C_ORIGIN_DOT, 180))
        pygame.gfxdraw.aacircle(s, ox, oy, 4,     (*C_ORIGIN_DOT, 220))

    if dest:
        dx2, dy2 = clamp(*proj.project(dest.longitude, dest.latitude))
        pygame.draw.line(s, (*C_ROUTE_AHEAD, 70), (fx, fy), (dx2, dy2), 1)
        pygame.gfxdraw.filled_circle(s, dx2, dy2, 4, (*C_DEST_DOT, 180))
        pygame.gfxdraw.aacircle(s, dx2, dy2, 4,     (*C_DEST_DOT, 220))

    surface.blit(s, (0, 0))


# ---------------------------------------------------------------------------
# Left panel
# ---------------------------------------------------------------------------

def _draw_left_panel(surface, font_title, font_panel, font_dim,
                     flights, bbox, location_name, fps,
                     panel_w, route_cache, airport_db,
                     airport_mode: bool, zoom_level: float):
    h      = surface.get_size()[1]
    pad    = 20
    line_h = PANEL_FONT_SIZE + 7
    lat_min, lon_min, lat_max, lon_max = bbox

    bg = pygame.Surface((panel_w, h), pygame.SRCALPHA)
    bg.fill((*C_PANEL_BG, 225))
    surface.blit(bg, (0, 0))
    pygame.draw.line(surface, C_PANEL_BORDER, (panel_w-1, 0), (panel_w-1, h), 1)
    pygame.draw.line(surface, C_DIVIDER,      (panel_w-2, 0), (panel_w-2, h), 1)

    y = pad

    for word in ("FLIGHT", "RADAR"):
        s = font_title.render(word, True, C_HUD_PRIMARY)
        surface.blit(s, (pad, y))
        y += HUD_TITLE_SIZE + 3
    y += 4

    surface.blit(font_panel.render(location_name, True, C_HUD_MID), (pad, y))
    y += line_h

    mode_str = "MODE: AIRPORT" if airport_mode else "MODE: CITY"
    mode_col = C_AIRPORT_LARGE if airport_mode else C_HUD_DIM
    surface.blit(font_dim.render(mode_str, True, mode_col), (pad, y))
    y += line_h

    zoom_str = f"ZOOM: {zoom_level:.1f}x"
    surface.blit(font_dim.render(zoom_str, True, C_HUD_DIM), (pad, y))
    y += line_h + 4

    pygame.draw.line(surface, C_DIVIDER, (pad, y), (panel_w-pad, y), 1)
    y += 10

    now = time.strftime("%H:%M:%S UTC", time.gmtime())
    for text, col in [
        (f"{len(flights):>3} AIRCRAFT", C_LABEL_CALL),
        (now,                           C_HUD_DIM),
        (f"LAT {lat_min:.2f}°–{lat_max:.2f}°", C_HUD_DIM),
        (f"LON {lon_min:.2f}°–{lon_max:.2f}°", C_HUD_DIM),
        (f"FPS {fps:>5.1f}",            C_HUD_DIM),
    ]:
        surface.blit(font_dim.render(text, True, col), (pad, y))
        y += line_h

    y += 4
    pygame.draw.line(surface, C_DIVIDER, (pad, y), (panel_w-pad, y), 1)
    y += 10

    for text, col in [
        ("▸ FAST  >220 m/s", C_PLANE_FAST),
        ("▸ CRUISE",         C_PLANE),
        ("▸ SLOW  <60 m/s",  C_PLANE_SLOW),
        ("◉ LARGE AIRPORT",  C_AIRPORT_LARGE),
        ("── FLOWN",         C_ROUTE_FLOWN),
        ("── AHEAD",         C_ROUTE_AHEAD),
    ]:
        surface.blit(font_dim.render(text, True, col), (pad, y))
        y += line_h

    y += 4
    pygame.draw.line(surface, C_DIVIDER, (pad, y), (panel_w-pad, y), 1)
    y += 10

    surface.blit(font_panel.render("CALLSIGN  ROUTE       FL   SPD", True, C_HUD_MID), (pad, y))
    y += line_h
    pygame.draw.line(surface, C_DIVIDER, (pad, y), (panel_w-pad, y), 1)
    y += 6

    max_rows = (h - y - pad - line_h * 3) // line_h
    shown    = flights[:max_rows]
    for f in shown:
        cs        = (f.callsign or f.icao24.upper())[:8].ljust(8)
        alt       = int(f.altitude * 3.28084)
        fl        = f"FL{alt//100:03d}"
        spd       = f"{int(f.velocity):>3}"
        route_str = "???  →???  "
        if f.callsign and route_cache:
            route = route_cache.get(f.callsign)
            if route:
                route_str = f"{route.origin}→{route.destination}"
        row = f"{cs}  {route_str:<11} {fl} {spd}"
        surface.blit(font_dim.render(row, True, _plane_colour(f.velocity)), (pad, y))
        y += line_h
        if y + line_h > h - pad - line_h * 3:
            rem = len(flights) - len(shown)
            if rem > 0:
                surface.blit(font_dim.render(f"  +{rem} more...", True, C_HUD_DIM), (pad, y))
            break

    # Key hints at bottom
    hints = [
        "+/- or scroll: zoom",
        "arrows: pan   0: toggle mode",
        "1-7: region   ESC: exit",
    ]
    yb = h - pad - len(hints) * line_h
    for hint in hints:
        surface.blit(font_dim.render(hint, True, C_DIVIDER), (pad, yb))
        yb += line_h


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

class Renderer:
    """
    Split-layout radar renderer with zoom, pan, city silhouette, compass.

    Key controls (handled in main.py, applied via methods here):
        zoom(factor)          — 0.8 = in, 1.25 = out
        pan(delta_lat, dlon)  — shift bbox centre
        set_location(name)    — jump to named city preset
        toggle_airport_mode() — switch between city and airport-close-up presets
    """

    def __init__(
        self,
        surface: pygame.Surface,
        location: str = DEFAULT_LOCATION,
        show_labels:   bool = True,
        show_trails:   bool = True,
        show_airports: bool = True,
        show_routes:   bool = True,
        show_silhouette: bool = True,
        show_compass:  bool = True,
    ) -> None:
        self.surface         = surface
        self.show_labels     = show_labels
        self.show_trails     = show_trails
        self.show_airports   = show_airports
        self.show_routes     = show_routes
        self.show_silhouette = show_silhouette
        self.show_compass    = show_compass

        self._current_key    = location     # e.g. "dubai"
        self._airport_mode   = False        # False = city, True = airport close-up
        self._base_span: Optional[tuple[float, float]] = None  # original half-spans for zoom reset

        loc_name, bbox       = CITY_LOCATIONS.get(location, list(CITY_LOCATIONS.values())[0])
        self.bbox            = bbox
        self.location_name   = loc_name
        self._zoom_level     = 1.0

        self.trails          = TrailStore()
        self._scan_angle     = 0.0
        self._pulse_t        = 0.0
        self._bg_surf: Optional[pygame.Surface] = None
        self._label_cache:   dict = {}
        self._fps_clock      = pygame.time.Clock()
        self._fps            = 0.0

        pygame.font.init()
        mono = pygame.font.match_font(
            "dejavusansmono,liberationmono,ubuntumono,monospace,courier"
        )
        self._font_label  = pygame.font.Font(mono, LABEL_FONT_SIZE)
        self._font_panel  = pygame.font.Font(mono, PANEL_FONT_SIZE)
        self._font_ptitle = pygame.font.Font(mono, PANEL_TITLE_SIZE)
        self._font_title  = pygame.font.Font(mono, HUD_TITLE_SIZE)
        self._font_compass= pygame.font.Font(mono, 11)

        self._update_layout()
        self._store_base_span()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _update_layout(self) -> None:
        w, h          = self.surface.get_size()
        self._panel_w = int(w * PANEL_RATIO)
        radar_area_w  = w - self._panel_w
        self._radar_r  = int(min(radar_area_w, h) * 0.44)
        self._radar_cx = self._panel_w + radar_area_w // 2
        self._radar_cy = h // 2
        self._proj     = Projector(
            self.bbox, self._radar_cx, self._radar_cy, self._radar_r
        )

    def _store_base_span(self) -> None:
        lat_min, lon_min, lat_max, lon_max = self.bbox
        self._base_span = (
            (lat_max - lat_min) / 2,
            (lon_max - lon_min) / 2,
        )
        self._zoom_level = 1.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_location(self, key: str) -> None:
        """Jump to a named city/region preset. Resets zoom and mode."""
        self._current_key  = key
        self._airport_mode = False
        table              = CITY_LOCATIONS
        if key not in table:
            print(f"[renderer] Unknown location '{key}'")
            return
        loc_name, bbox     = table[key]
        self.bbox          = bbox
        self.location_name = loc_name
        self._update_layout()
        self._store_base_span()
        self.trails        = TrailStore()
        self._label_cache.clear()

    def toggle_airport_mode(self) -> None:
        """
        Toggle between city/regional view and airport close-up view.
        Press 0 to switch back and forth.
        """
        self._airport_mode = not self._airport_mode
        key   = self._current_key
        table = AIRPORT_LOCATIONS if self._airport_mode else CITY_LOCATIONS

        # Fall back to first entry if key not in table
        if key not in table:
            key = list(table.keys())[0]

        loc_name, bbox     = table[key]
        self.bbox          = bbox
        self.location_name = loc_name
        self._update_layout()
        self._store_base_span()
        self.trails        = TrailStore()
        self._label_cache.clear()

    def zoom(self, factor: float) -> None:
        """
        Zoom in (factor < 1.0) or out (factor > 1.0) around bbox centre.
        Example: zoom(0.8) → 20% closer, zoom(1.25) → 25% wider.
        """
        lat_min, lon_min, lat_max, lon_max = self.bbox
        mid_lat = (lat_min + lat_max) / 2
        mid_lon = (lon_min + lon_max) / 2

        half_lat = (lat_max - lat_min) / 2 * factor
        half_lon = (lon_max - lon_min) / 2 * factor

        half_lat = max(MIN_ZOOM_SPAN, min(MAX_ZOOM_SPAN, half_lat))
        half_lon = max(MIN_ZOOM_SPAN, min(MAX_ZOOM_SPAN, half_lon))

        self.bbox = (
            mid_lat - half_lat,
            mid_lon - half_lon,
            mid_lat + half_lat,
            mid_lon + half_lon,
        )

        # Track zoom level relative to base span
        if self._base_span and self._base_span[0] > 0:
            self._zoom_level = self._base_span[0] / half_lat
        else:
            self._zoom_level = 1.0

        self._update_layout()
        self._label_cache.clear()
        # Don't clear trails on zoom — they stay valid

    def pan(self, delta_lat: float, delta_lon: float) -> None:
        """
        Shift the view centre. delta values are in degrees.
        Example: pan(0.5, 0) → move north by 0.5°.
        """
        lat_min, lon_min, lat_max, lon_max = self.bbox
        self.bbox = (
            lat_min + delta_lat,
            lon_min + delta_lon,
            lat_max + delta_lat,
            lon_max + delta_lon,
        )
        self._update_layout()
        self._label_cache.clear()

    def reset_zoom(self) -> None:
        """Reset zoom and pan back to the current location's default view."""
        self.set_location(self._current_key)

    def draw(
        self,
        flights: list,
        airports: Optional[list] = None,
        route_cache=None,
        airport_db=None,
    ) -> None:
        w, h     = self.surface.get_size()
        airports = airports or []
        self._tick_animation()

        # 1 — Background
        self._draw_bg(w, h)

        # 2 — City silhouette (inside circle, before clip)
        if self.show_silhouette:
            city_key = self._current_key
            _draw_city_silhouette(
                self.surface,
                self._radar_cx, self._radar_cy, self._radar_r,
                city_key,
            )

        # 3 — Trails
        if self.show_trails:
            trail_surf = pygame.Surface((w, h), pygame.SRCALPHA)
            for flight in flights:
                self.trails.update(flight.icao24, flight.longitude, flight.latitude)
                if self._proj.in_radar(flight.longitude, flight.latitude):
                    geo = self.trails.get(flight.icao24)
                    if len(geo) >= 2:
                        px = [self._proj.project(lo, la) for lo, la in geo]
                        _draw_trail(trail_surf, px, C_TRAIL_HEAD, C_TRAIL_TAIL)
            self.surface.blit(trail_surf, (0, 0))
        else:
            for flight in flights:
                self.trails.update(flight.icao24, flight.longitude, flight.latitude)

        # 4 — Clip to circle
        _clip_to_circle(self.surface, self._radar_cx, self._radar_cy, self._radar_r)

        # 5 — Radar rings, sweep, pulse
        _draw_radar(
            self.surface,
            self._radar_cx, self._radar_cy, self._radar_r,
            self._pulse_t, self._scan_angle,
        )

        # 6 — Compass
        if self.show_compass:
            _draw_compass(
                self.surface,
                self._radar_cx, self._radar_cy, self._radar_r,
                self._font_compass,
            )

        # 7 — Route lines
        if self.show_routes and route_cache and airport_db:
            for flight in flights:
                if not self._proj.in_radar(flight.longitude, flight.latitude):
                    continue
                cs = (flight.callsign or "").strip().upper()
                if not cs:
                    continue
                route = route_cache.get(cs)
                if route:
                    _draw_route_line(
                        self.surface, self._proj,
                        flight.longitude, flight.latitude,
                        route.origin, route.destination,
                        airport_db,
                    )

        # 8 — Airport icons
        if self.show_airports and airports:
            _draw_airports(self.surface, self._proj, airports, self._font_label)

        # 9 — Plane icons + labels
        label_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        active_ids: set[str] = set()
        for flight in flights:
            active_ids.add(flight.icao24)
            if self._proj.in_radar(flight.longitude, flight.latitude):
                self._draw_flight(label_surf, flight)
        self.surface.blit(label_surf, (0, 0))
        self.trails.prune(active_ids)

        # 10 — Left panel
        _draw_left_panel(
            self.surface,
            self._font_title, self._font_ptitle, self._font_panel,
            flights, self.bbox, self.location_name, self._fps,
            self._panel_w, route_cache, airport_db,
            self._airport_mode, self._zoom_level,
        )

        self._fps = self._fps_clock.get_fps()
        self._fps_clock.tick()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _draw_bg(self, w, h):
        if self._bg_surf is None or self._bg_surf.get_size() != (w, h):
            self._bg_surf = pygame.Surface((w, h))
            for y in range(h):
                pygame.draw.line(self._bg_surf, _lerp_colour(C_BG, C_BG2, y/h), (0, y), (w, y))
        self.surface.blit(self._bg_surf, (0, 0))

    def _tick_animation(self):
        self._scan_angle = (self._scan_angle + 0.7) % 360
        self._pulse_t    = (self._pulse_t + 0.003) % 1.0

    def _draw_flight(self, label_surf, flight):
        cx, cy = self._proj.project(flight.longitude, flight.latitude)
        colour = _plane_colour(flight.velocity)
        _draw_plane_icon(self.surface, cx, cy, flight.heading, colour)
        if self.show_labels:
            self._draw_label(label_surf, flight, cx, cy, colour)

    def _draw_label(self, surf, flight, cx, cy, colour):
        if flight.icao24 not in self._label_cache:
            cs    = (flight.callsign or flight.icao24.upper())
            alt   = int(flight.altitude * 3.28084)
            cs_s  = self._font_label.render(cs, True, C_LABEL_CALL)
            alt_s = self._font_label.render(f"FL{alt//100:03d}", True, C_LABEL_ALT)
            self._label_cache[flight.icao24] = (cs_s, alt_s)
        cs_s, alt_s = self._label_cache[flight.icao24]
        ox, oy = 10, -16
        surf.blit(cs_s,  (cx+ox, cy+oy))
        surf.blit(alt_s, (cx+ox, cy+oy+LABEL_FONT_SIZE+2))
        pygame.draw.line(surf, (*colour, 55), (cx, cy), (cx+ox-2, cy+oy+LABEL_FONT_SIZE), 1)

    def invalidate_label_cache(self):
        self._label_cache.clear()

    def resize(self, new_w, new_h):
        self._bg_surf = None
        self._update_layout()