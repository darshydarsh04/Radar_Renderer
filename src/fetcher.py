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


credits_remaining = None   # updated on every fetch

def fetch_flights(bbox=(22.0, 45.0, 30.0, 60.0)):
    global credits_remaining
    lat_min, lon_min, lat_max, lon_max = bbox
    params = dict(lamin=lat_min, lomin=lon_min, lamax=lat_max, lomax=lon_max)
    try:
        resp = requests.get(OPENSKY_URL, params=params, timeout=8)
        if resp.status_code == 429:
            credits_remaining = 0
            retry = resp.headers.get("X-Rate-Limit-Retry-After-Seconds", "?")
            print(f"[fetcher] out of credits, retry in {retry}s")
            return []
        try:
            credits_remaining = int(resp.headers["X-Rate-Limit-Remaining"])
        except (KeyError, TypeError, ValueError):
            pass
        print(f"[fetcher] credits remaining: {credits_remaining}")
        resp.raise_for_status()
        ...  # rest unchanged
    except Exception as e:
        print(f"[fetcher] API error: {e}")
        return []