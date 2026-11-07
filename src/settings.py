"""
settings.py: view settings shared by snapshot.py and radar_ctl.py.

The settings live in ~/.config/flight-radar/settings.json, so whatever you pick
in the terminal controller is also what the scheduled refresh renders.
Everything here is plain Python (no display needed), which keeps it easy to test.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Optional

from src.renderer import AIRPORT_LOCATIONS, CITY_LOCATIONS

SETTINGS_PATH = Path.home() / ".config" / "flight-radar" / "settings.json"

# Half-span limits in degrees. These are deliberately independent of the
# renderer's own zoom() limits, which are too coarse for airport close-ups.
MIN_HALF_SPAN = 0.05
MAX_HALF_SPAN = 45.0

DEFAULT_ZOOM_STEP = 1.33
DEFAULT_PAN_STEP = 0.2
DEFAULT_ROUTES = 12

BBox = tuple[float, float, float, float]  # (lat_min, lon_min, lat_max, lon_max)

DEFAULTS: dict = {
    "location": "dubai",        # key in CITY_LOCATIONS
    "airport_mode": False,      # True = airport close-up preset for that location
    "custom": False,            # True = the view came from `goto`, not a preset
    "label": None,              # panel title override (used by `goto`)
    "bbox": None,               # None = use the preset's bounding box
    "show_map": True,           # city skyline background
    "show_airports": True,
    "routes": DEFAULT_ROUTES,   # max route lookups per render, 0 = routes off
    "size": "1920x1080",
}


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------

def parse_size(text) -> Optional[tuple[int, int]]:
    """'1920x1080' -> (1920, 1080), or None if it is not a sensible size."""
    try:
        width, height = (int(v) for v in str(text).lower().split("x"))
    except ValueError:
        return None
    return (width, height) if width >= 640 and height >= 480 else None


def _valid_bbox(value) -> Optional[BBox]:
    try:
        lat_min, lon_min, lat_max, lon_max = (float(v) for v in value)
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat_min < lat_max <= 90 and -180 <= lon_min < lon_max <= 180):
        return None
    return (lat_min, lon_min, lat_max, lon_max)


def _sanitise(s: dict) -> dict:
    """Repair anything hand-edited or corrupt so rendering never crashes."""
    if s["location"] not in CITY_LOCATIONS:
        s["location"] = DEFAULTS["location"]
    for key in ("airport_mode", "custom", "show_map", "show_airports"):
        s[key] = bool(s[key])
    try:
        s["routes"] = max(0, int(s["routes"]))
    except (TypeError, ValueError):
        s["routes"] = DEFAULTS["routes"]
    if parse_size(s["size"]) is None:
        s["size"] = DEFAULTS["size"]
    s["bbox"] = _valid_bbox(s["bbox"])
    s["label"] = s["label"] if isinstance(s["label"], str) and s["label"] else None
    if s["bbox"] is None:
        s["custom"], s["label"] = False, None
    return s


def load_settings(path: Path = SETTINGS_PATH) -> dict:
    settings = dict(DEFAULTS)
    try:
        saved = json.loads(path.read_text())
    except (OSError, ValueError):
        return settings
    if isinstance(saved, dict):
        for key in DEFAULTS:
            if key in saved:
                settings[key] = saved[key]
    return _sanitise(settings)


def save_settings(settings: dict, path: Path = SETTINGS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(settings, indent=2))
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Reading the current view
# ---------------------------------------------------------------------------

def _preset(settings: dict) -> tuple[str, BBox]:
    table = AIRPORT_LOCATIONS if settings["airport_mode"] else CITY_LOCATIONS
    key = settings["location"] if settings["location"] in table else next(iter(table))
    return table[key]


def preset_bbox(settings: dict) -> BBox:
    return _preset(settings)[1]


def current_bbox(settings: dict) -> BBox:
    return tuple(settings["bbox"]) if settings["bbox"] else preset_bbox(settings)


def display_name(settings: dict) -> str:
    return settings["label"] or _preset(settings)[0]


def zoom_level(settings: dict) -> float:
    """How much closer than the preset view we are (1.0 = preset). Custom views report 1.0."""
    if settings["custom"]:
        return 1.0
    base, cur = preset_bbox(settings), current_bbox(settings)
    return (base[2] - base[0]) / (cur[2] - cur[0])


# ---------------------------------------------------------------------------
# Changing the view (these mutate the dict in place)
# ---------------------------------------------------------------------------

def _round(bbox: BBox) -> BBox:
    return tuple(round(v, 5) for v in bbox)


def _shift_into(lo: float, hi: float, limit: float) -> tuple[float, float]:
    """Slide [lo, hi] inside [-limit, limit] without changing its width."""
    if hi > limit:
        lo, hi = lo - (hi - limit), limit
    if lo < -limit:
        lo, hi = -limit, min(limit, hi + (-limit - lo))
    return lo, hi


def _fit(bbox: BBox) -> BBox:
    """Keep the box inside valid lat/lon ranges (OpenSky rejects anything else)."""
    lat_min, lon_min, lat_max, lon_max = bbox
    lat_min, lat_max = _shift_into(lat_min, lat_max, 90.0)
    lon_min, lon_max = _shift_into(lon_min, lon_max, 180.0)
    return _round((lat_min, lon_min, lat_max, lon_max))


def _clamp_half(new: float, current: float) -> float:
    floor = min(MIN_HALF_SPAN, current)   # zooming in must never enlarge a tiny preset
    return max(floor, min(MAX_HALF_SPAN, new))


def set_location(settings: dict, key: str) -> None:
    if key not in CITY_LOCATIONS:
        raise ValueError(f"unknown location {key!r}")
    settings.update(location=key, airport_mode=False, custom=False, label=None, bbox=None)


def set_mode(settings: dict, airport: bool) -> None:
    settings.update(airport_mode=airport, custom=False, label=None, bbox=None)


def reset_view(settings: dict) -> None:
    """Back to the preset for the current location and mode."""
    settings.update(custom=False, label=None, bbox=None)


def zoom(settings: dict, factor: float) -> None:
    """factor < 1 zooms in (smaller area), factor > 1 zooms out. Keeps the centre."""
    if factor <= 0:
        raise ValueError("zoom factor must be greater than 0")
    lat_min, lon_min, lat_max, lon_max = current_bbox(settings)
    mid_lat, mid_lon = (lat_min + lat_max) / 2, (lon_min + lon_max) / 2
    half_lat_now, half_lon_now = (lat_max - lat_min) / 2, (lon_max - lon_min) / 2
    half_lat = _clamp_half(half_lat_now * factor, half_lat_now)
    half_lon = _clamp_half(half_lon_now * factor, half_lon_now)
    settings["bbox"] = _fit((mid_lat - half_lat, mid_lon - half_lon,
                             mid_lat + half_lat, mid_lon + half_lon))


def pan(settings: dict, north: float = 0.0, east: float = 0.0) -> None:
    """Move the view by a fraction of what is currently visible (negative = south/west)."""
    lat_min, lon_min, lat_max, lon_max = current_bbox(settings)
    dlat = north * (lat_max - lat_min)
    dlon = east * (lon_max - lon_min)
    settings["bbox"] = _fit((lat_min + dlat, lon_min + dlon, lat_max + dlat, lon_max + dlon))


def goto(settings: dict, lat: float, lon: float, radius: float = 3.0) -> None:
    """Centre on any coordinates. radius = degrees of latitude shown either side."""
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("latitude must be -90..90 and longitude -180..180")
    if radius <= 0:
        raise ValueError("radius must be greater than 0")
    half_lat = _clamp_half(radius, MAX_HALF_SPAN)
    # Widen longitude away from the equator so the map is not squashed.
    squash = max(math.cos(math.radians(min(abs(lat), 80.0))), 0.2)
    half_lon = _clamp_half(half_lat / squash, MAX_HALF_SPAN)
    settings.update(
        custom=True,
        airport_mode=False,
        label=f"CUSTOM {lat:.2f},{lon:.2f}",
        bbox=_fit((lat - half_lat, lon - half_lon, lat + half_lat, lon + half_lon)),
    )
