#!/usr/bin/env python3
"""
snapshot.py: render ONE frame of the flight radar and set it as the GNOME wallpaper.

It fetches live data once, draws a single frame off-screen, saves a PNG,
points GNOME at it, deletes the previous image, and exits. Nothing stays
running between updates, so the idle cost is zero.

The view (location, zoom, map, airports...) comes from the saved settings that
radar_ctl.py edits. Command-line options override them for this run only.

Examples:
    python3 snapshot.py                              # use the saved settings
    python3 snapshot.py --location london
    python3 snapshot.py --airport --location dubai
    python3 snapshot.py --size 2560x1440 --no-set    # only save the PNG
"""
from __future__ import annotations

import os

# Must be set before pygame is imported: render without any window or display server.
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import pygame  # noqa: E402

from src import settings as st  # noqa: E402
from src.airports import AirportDB  # noqa: E402
from src.fetcher import fetch_flights  # noqa: E402
from src.renderer import CITY_LOCATIONS, Renderer  # noqa: E402
from src.routes import RouteCache  # noqa: E402

OUT_DIR = Path.home() / ".local" / "share" / "flight-radar"
SCHEMA = "org.gnome.desktop.background"
ROUTE_TIME_BUDGET = 30  # seconds spent on route lookups at most


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

def build_renderer(settings: dict) -> Renderer:
    """Create an off-screen Renderer that matches the saved settings."""
    width, height = st.parse_size(settings["size"])
    renderer = Renderer(
        pygame.Surface((width, height)),
        location=settings["location"],
        show_airports=settings["show_airports"],
        show_routes=settings["routes"] > 0,
        show_silhouette=settings["show_map"],
    )
    if settings["airport_mode"]:
        renderer.toggle_airport_mode()
    if settings["bbox"]:
        renderer.bbox = tuple(settings["bbox"])
        if settings["label"]:
            renderer.location_name = settings["label"]
        renderer._zoom_level = st.zoom_level(settings)
        renderer._update_layout()
    if settings["custom"]:
        renderer._current_key = "custom"   # no preset skyline for an arbitrary place
    return renderer


def set_wallpaper(path: Path) -> None:
    """Point GNOME at the image (light and dark variants). Raises RuntimeError on failure."""
    uri = path.as_uri()
    try:
        for key in ("picture-uri", "picture-uri-dark"):
            subprocess.run(["gsettings", "set", SCHEMA, key, uri],
                           check=True, capture_output=True, text=True)
        subprocess.run(["gsettings", "set", SCHEMA, "picture-options", "zoom"],
                       check=True, capture_output=True, text=True)
    except FileNotFoundError:
        raise RuntimeError("gsettings not found (this needs GNOME)") from None
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"gsettings failed: {exc.stderr.strip() or exc}") from exc


def remove_old_images(keep: Path) -> int:
    """Delete every earlier radar image except `keep`. Returns how many were removed."""
    removed = 0
    for old in OUT_DIR.glob("radar-*.png"):
        if old != keep:
            old.unlink(missing_ok=True)
            removed += 1
    return removed


def render_wallpaper(
    settings: dict,
    *,
    set_it: bool = True,
    force: bool = False,
    log: Callable[[str], None] = print,
) -> Optional[Path]:
    """
    Fetch data, render one frame, save it and (optionally) make it the wallpaper.

    Returns the new image path, or None if nothing was rendered because no
    flights came back (pass force=True to render anyway).
    Raises RuntimeError if the image was saved but GNOME could not be updated;
    in that case the old images are left alone.
    """
    pygame.init()
    renderer = build_renderer(settings)

    log("Fetching flights...")
    flights = fetch_flights(renderer.bbox)
    if not flights and not force:
        # fetch_flights returns [] on any API error, so keep the old wallpaper.
        log("No flights returned (API error or empty airspace); "
            "keeping the current wallpaper.")
        return None
    log(f"{len(flights)} aircraft in view")

    airports, airport_db = [], None
    if settings["show_airports"] or settings["routes"] > 0:
        airport_db = AirportDB()
        airport_db.load()
        if settings["show_airports"] and airport_db.loaded:
            lat_min, lon_min, lat_max, lon_max = renderer.bbox
            airports = airport_db.in_bbox(lat_min, lon_min, lat_max, lon_max)

    route_cache = RouteCache() if settings["routes"] > 0 else None
    if route_cache is not None:
        # Routes are rate limited, so only look up the first few flights (the
        # ones at the top of the left panel).
        for flight in flights[: settings["routes"]]:
            if flight.callsign:
                route_cache.request(flight.callsign)
        if route_cache.queue_size:
            log(f"Looking up routes for up to {settings['routes']} flights...")
        deadline = time.time() + ROUTE_TIME_BUDGET
        while route_cache.queue_size and time.time() < deadline:
            route_cache.process_queue()
            time.sleep(0.3)

    # Freeze the animation on a pleasant frame.
    renderer._scan_angle = 40.0
    renderer._pulse_t = 0.35
    renderer.draw(flights, airports, route_cache, airport_db)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # A fresh filename each time forces GNOME to reload the image.
    out = OUT_DIR / f"radar-{int(time.time() * 1000)}.png"
    tmp = OUT_DIR / "radar-tmp.png"
    pygame.image.save(renderer.surface, str(tmp))
    os.replace(tmp, out)
    log(f"Saved {out}")

    if set_it:
        set_wallpaper(out)            # raises before anything is deleted
        removed = remove_old_images(keep=out)
        log("Wallpaper updated" + (f", removed {removed} old image(s)" if removed else ""))
    else:
        log("Wallpaper not changed; older images were kept because one may still be in use.")
    return out


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Render the flight radar wallpaper once, using the saved settings.")
    ap.add_argument("--location", choices=sorted(CITY_LOCATIONS))
    ap.add_argument("--airport", action="store_true", help="airport close-up view")
    ap.add_argument("--size", help="WIDTHxHEIGHT of your screen, e.g. 1920x1080")
    ap.add_argument("--routes", type=int, help="max route lookups (0 = off)")
    ap.add_argument("--no-set", action="store_true",
                    help="save the PNG but do not change the wallpaper")
    ap.add_argument("--force", action="store_true",
                    help="render even if no flights came back")
    return ap.parse_args()


def apply_cli(settings: dict, args: argparse.Namespace) -> Optional[str]:
    """Apply command-line overrides to this run's settings. Returns an error message or None."""
    if args.location:
        st.set_location(settings, args.location)
    if args.airport:
        st.set_mode(settings, True)
    if args.size:
        if st.parse_size(args.size) is None:
            return "--size must look like 1920x1080 (at least 640x480)"
        settings["size"] = args.size
    if args.routes is not None:
        settings["routes"] = max(0, args.routes)
    return None


def main() -> int:
    args = parse_args()
    settings = st.load_settings()
    error = apply_cli(settings, args)
    if error:
        print(error)
        return 2
    try:
        out = render_wallpaper(settings, set_it=not args.no_set, force=args.force)
    except RuntimeError as exc:
        print(f"Image saved but the wallpaper was not changed: {exc}")
        return 1
    return 0 if out else 1


if __name__ == "__main__":
    sys.exit(main())