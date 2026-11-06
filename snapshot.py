#!/usr/bin/env python3
"""
snapshot.py: render ONE frame of the flight radar and set it as the GNOME wallpaper.

It fetches live data once, draws a single frame off-screen, saves a PNG,
points GNOME at it, and exits. Nothing stays running between updates, so the
idle cost is zero. Schedule it with install.sh (systemd user timer).

Examples:
    python3 snapshot.py                              # Dubai, 1920x1080
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

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import pygame  # noqa: E402

from src.airports import AirportDB  # noqa: E402
from src.fetcher import fetch_flights  # noqa: E402
from src.renderer import CITY_LOCATIONS, Renderer  # noqa: E402
from src.routes import RouteCache  # noqa: E402

OUT_DIR = Path.home() / ".local" / "share" / "flight-radar"
SCHEMA = "org.gnome.desktop.background"
ROUTE_TIME_BUDGET = 30  # seconds spent on route lookups at most


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Render the flight radar wallpaper once.")
    ap.add_argument("--location", default="dubai", choices=sorted(CITY_LOCATIONS))
    ap.add_argument("--airport", action="store_true", help="airport close-up view")
    ap.add_argument("--size", default="1920x1080", help="WIDTHxHEIGHT of your screen")
    ap.add_argument("--routes", type=int, default=12,
                    help="max route lookups (about 1.2 s each)")
    ap.add_argument("--no-set", action="store_true",
                    help="save the PNG but do not change the wallpaper")
    ap.add_argument("--force", action="store_true",
                    help="render even if no flights came back")
    return ap.parse_args()


def set_wallpaper(path: Path) -> None:
    """Point GNOME at the new image (light and dark theme variants)."""
    uri = path.as_uri()
    for key in ("picture-uri", "picture-uri-dark"):
        subprocess.run(["gsettings", "set", SCHEMA, key, uri], check=True)
    subprocess.run(["gsettings", "set", SCHEMA, "picture-options", "zoom"], check=True)
    print("Wallpaper updated")


def main() -> int:
    args = parse_args()
    try:
        width, height = (int(v) for v in args.size.lower().split("x"))
    except ValueError:
        print("--size must look like 1920x1080")
        return 2

    pygame.init()
    surface = pygame.Surface((width, height))
    renderer = Renderer(surface, location=args.location)
    if args.airport:
        renderer.toggle_airport_mode()

    flights = fetch_flights(renderer.bbox)
    if not flights and not args.force:
        # fetch_flights returns [] on any API error, so keep the old wallpaper.
        print("No flights returned (API error or empty airspace); "
              "keeping the current wallpaper.")
        return 1

    airport_db = AirportDB()
    airport_db.load()
    lat_min, lon_min, lat_max, lon_max = renderer.bbox
    airports = (airport_db.in_bbox(lat_min, lon_min, lat_max, lon_max)
                if airport_db.loaded else [])

    # Routes are rate limited, so only look up the first few flights (the ones
    # at the top of the left panel).
    route_cache = RouteCache()
    for f in flights[: args.routes]:
        if f.callsign:
            route_cache.request(f.callsign)
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
    out = OUT_DIR / f"radar-{int(time.time())}.png"
    tmp = OUT_DIR / "radar-tmp.png"
    pygame.image.save(surface, str(tmp))
    os.replace(tmp, out)
    print(f"Saved {out}")

    if not args.no_set:
        set_wallpaper(out)

    for old in OUT_DIR.glob("radar-*.png"):
        if old != out:
            old.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
