"""
airports.py — Airport database loader and lookup.

Downloads OurAirports CSV once per session, caches in memory.
Provides fast ICAO → Airport lookup.
"""
from __future__ import annotations
import csv, io, time
from dataclasses import dataclass
from typing import Optional
import requests

AIRPORTS_URL = "https://ourairports.com/data/airports.csv"

@dataclass
class Airport:
    icao: str
    name: str
    municipality: str    # city name
    country: str
    latitude: float
    longitude: float
    airport_type: str    # large_airport, medium_airport, small_airport, etc.

    @property
    def label(self) -> str:
        """Short display label: ICAO + city."""
        city = self.municipality or self.country
        return f"{self.icao} {city}"


class AirportDB:
    """
    In-memory airport database.

    Usage:
        db = AirportDB()
        db.load()                        # fetches CSV (~5MB, once)
        airport = db.get("OMDB")         # Dubai Int'l
        airports_in_bbox = db.in_bbox(22, 45, 30, 60)
    """

    def __init__(self) -> None:
        self._db: dict[str, Airport] = {}
        self._loaded = False

    def load(self) -> int:
        """Fetch and parse the airports CSV. Returns count loaded."""
        try:
            resp = requests.get(AIRPORTS_URL, timeout=15)
            resp.raise_for_status()
            reader = csv.DictReader(io.StringIO(resp.text))
            count = 0
            for row in reader:
                icao = row.get("gps_code", "").strip()
                if not icao or len(icao) != 4:
                    continue           # skip airports without 4-letter ICAO
                try:
                    lat = float(row["latitude_deg"])
                    lon = float(row["longitude_deg"])
                except (ValueError, KeyError):
                    continue
                self._db[icao] = Airport(
                    icao         = icao,
                    name         = row.get("name", ""),
                    municipality = row.get("municipality", ""),
                    country      = row.get("iso_country", ""),
                    latitude     = lat,
                    longitude    = lon,
                    airport_type = row.get("type", ""),
                )
                count += 1
            self._loaded = True
            print(f"[airports] Loaded {count} airports")
            return count
        except Exception as e:
            print(f"[airports] Failed to load: {e}")
            return 0

    def get(self, icao: str) -> Optional[Airport]:
        return self._db.get(icao.upper())

    def in_bbox(
        self,
        lat_min: float, lon_min: float,
        lat_max: float, lon_max: float,
        types: set[str] | None = None,
    ) -> list[Airport]:
        """Return airports within a bounding box, optionally filtered by type."""
        types = types or {"large_airport", "medium_airport"}
        return [
            a for a in self._db.values()
            if lat_min <= a.latitude  <= lat_max
            and lon_min <= a.longitude <= lon_max
            and a.airport_type in types
        ]

    @property
    def loaded(self) -> bool:
        return self._loaded