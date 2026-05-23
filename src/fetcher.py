# src/fetcher.py
import requests
from src.config import BBOX, POLL_INTERVAL
from src.flight import Flight

OPENSKY_URL = "https://opensky-network.org/api/states/all"

def fetch_flights() -> list[Flight]:
    lat_min, lon_min, lat_max, lon_max = BBOX
    params = dict(lamin=lat_min, lomin=lon_min, lamax=lat_max, lomax=lon_max)
    try:
        resp = requests.get(OPENSKY_URL, params=params, timeout=8)
        resp.raise_for_status()
        states = resp.json().get("states") or []
        flights = [Flight.from_opensky(s) for s in states]
        return [f for f in flights if f is not None]
    except requests.RequestException as e:
        print(f"[fetcher] API error: {e}")
        return []   # graceful degradation — don't crash the wallpaper