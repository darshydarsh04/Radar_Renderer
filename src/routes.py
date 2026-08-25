"""
routes.py — Lazy per-callsign route fetcher (OpenSky /routes endpoint).

Fixed: dataclass imported before use, no circular decorator issue.
"""
from __future__ import annotations

import time
import threading
from dataclasses import dataclass
from typing import Optional

import requests

ROUTES_URL          = "https://opensky-network.org/api/routes"
MIN_REQUEST_INTERVAL = 1.2   # seconds between API calls


@dataclass
class Route:
    callsign:    str
    origin:      str   # departure ICAO e.g. "OMDB"
    destination: str   # arrival ICAO   e.g. "EGLL"


class RouteCache:
    """
    Thread-safe lazy route fetcher with in-memory cache.

    - request(callsign)      → queue for background fetch (non-blocking)
    - get(callsign)          → return cached Route or None
    - process_queue()        → fetch one queued item (call from main loop)
    """

    def __init__(self) -> None:
        self._cache: dict[str, Optional[Route]] = {}
        self._queue: list[str] = []
        self._lock  = threading.Lock()
        self._last_fetch = 0.0

    def request(self, callsign: str) -> None:
        """Queue callsign for fetching if not already cached or queued."""
        cs = callsign.strip().upper()
        with self._lock:
            if cs not in self._cache and cs not in self._queue:
                self._queue.append(cs)

    def get(self, callsign: str) -> Optional[Route]:
        """Return cached Route, or None if not yet fetched / not found."""
        return self._cache.get(callsign.strip().upper())

    def process_queue(self) -> None:
        """
        Fetch one queued callsign. Rate-limited internally.
        Call this once per main loop iteration.
        """
        if time.time() - self._last_fetch < MIN_REQUEST_INTERVAL:
            return
        with self._lock:
            if not self._queue:
                return
            callsign = self._queue.pop(0)
        route = self._fetch_one(callsign)
        with self._lock:
            self._cache[callsign] = route
        self._last_fetch = time.time()

    def _fetch_one(self, callsign: str) -> Optional[Route]:
        try:
            resp = requests.get(
                ROUTES_URL, params={"callsign": callsign}, timeout=5
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
            stops = data.get("route", [])
            if len(stops) < 2:
                return None
            return Route(callsign=callsign, origin=stops[0], destination=stops[-1])
        except Exception as e:
            print(f"[routes] {callsign}: {e}")
            return None

    @property
    def queue_size(self) -> int:
        with self._lock:
            return len(self._queue)

    @property
    def cache_size(self) -> int:
        with self._lock:
            return len(self._cache)