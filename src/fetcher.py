"""
fetcher.py — OpenSky API flight fetcher.

fetch_flights(bbox) now takes the bbox as an argument so it always
fetches the correct region when the user switches location.
"""
from __future__ import annotations

import requests
from typing import Optional

from src.flight import Flight

OPENSKY_URL = "https://opensky-network.org/api/states/all"


def fetch_flights(
    bbox: tuple[float, float, float, float] = (22.0, 45.0, 30.0, 60.0)
) -> list[Flight]:
    """
    Fetch live flights from OpenSky for the given bounding box.

    bbox: (lat_min, lon_min, lat_max, lon_max)
    Returns a list of Flight objects, empty list on any error.
    """
    lat_min, lon_min, lat_max, lon_max = bbox
    params = dict(lamin=lat_min, lomin=lon_min, lamax=lat_max, lomax=lon_max)
    try:
        resp = requests.get(OPENSKY_URL, params=params, timeout=8)
        resp.raise_for_status()
        states = resp.json().get("states") or []
        flights = [Flight.from_opensky(s) for s in states]
        return [f for f in flights if f is not None]
    except Exception as e:
        print(f"[fetcher] API error: {e}")
        return []