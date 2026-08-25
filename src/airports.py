"""
airports.py — Airport database loader.

Reads from a local CSV file (OurAirports format) bundled in src/.
Falls back to downloading if the file isn't found.

OurAirports CSV columns (standard):
  id, ident, type, name, latitude_deg, longitude_deg, elevation_ft,
  continent, iso_country, iso_region, municipality, scheduled_service,
  gps_code, iata_code, local_code, home_link, wikipedia_link, keywords

We use: gps_code (4-letter ICAO), name, municipality, iso_country,
        latitude_deg, longitude_deg, type
"""
from __future__ import annotations

import csv
import io
import os
from dataclasses import dataclass
from typing import Optional

import requests

# Path to the CSV bundled in the src/ folder
_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CSV_PATH = os.path.join(_HERE, "airports.csv")
FALLBACK_URL     = "https://ourairports.com/data/airports.csv"

MAJOR_TYPES = {"large_airport", "medium_airport"}


@dataclass
class Airport:
    icao:         str
    name:         str
    municipality: str
    country:      str
    latitude:     float
    longitude:    float
    apt_type:     str   # large_airport / medium_airport / small_airport / heliport

    @property
    def display_name(self) -> str:
        city = self.municipality or self.name
        return f"{self.icao}  {city}"

    @property
    def is_major(self) -> bool:
        return self.apt_type in MAJOR_TYPES


class AirportDB:
    """
    In-memory airport database loaded from a local CSV file.

    Usage:
        db = AirportDB()
        db.load()                              # call once at startup
        apt = db.get("OMDB")                   # Dubai Int'l → Airport or None
        nearby = db.in_bbox(22, 45, 30, 60)    # airports in UAE bbox
    """

    def __init__(self, csv_path: str = DEFAULT_CSV_PATH) -> None:
        self._csv_path = csv_path
        self._db: dict[str, Airport] = {}
        self._loaded = False

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self) -> int:
        """
        Load airports from CSV. Returns number of airports loaded.
        Tries local file first, then downloads as fallback.
        """
        text = self._read_csv_text()
        if not text:
            print("[airports] No CSV data available.")
            return 0

        count = 0
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            apt = self._parse_row(row)
            if apt is not None:
                self._db[apt.icao] = apt
                count += 1

        self._loaded = True
        print(f"[airports] Loaded {count} airports")
        return count

    def _read_csv_text(self) -> Optional[str]:
        # 1 — try local file
        if os.path.isfile(self._csv_path):
            try:
                with open(self._csv_path, encoding="utf-8", errors="replace") as f:
                    text = f.read()
                print(f"[airports] Reading local CSV: {self._csv_path}")
                return text
            except Exception as e:
                print(f"[airports] Could not read local CSV: {e}")

        # 2 — fallback download
        print(f"[airports] Local CSV not found, downloading...")
        try:
            resp = requests.get(FALLBACK_URL, timeout=20)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            print(f"[airports] Download failed: {e}")
            return None

    @staticmethod
    def _parse_row(row: dict) -> Optional[Airport]:
        # Accept both 'gps_code' (OurAirports) and 'icao_code' (alternate)
        icao = (row.get("gps_code") or row.get("icao_code") or "").strip().upper()
        if not icao or len(icao) != 4:
            return None

        try:
            lat = float(row.get("latitude_deg") or row.get("lat") or "")
            lon = float(row.get("longitude_deg") or row.get("lon") or "")
        except (ValueError, TypeError):
            return None

        return Airport(
            icao         = icao,
            name         = (row.get("name") or "").strip(),
            municipality = (row.get("municipality") or "").strip(),
            country      = (row.get("iso_country") or row.get("country") or "").strip(),
            latitude     = lat,
            longitude    = lon,
            apt_type     = (row.get("type") or "").strip(),
        )

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, icao: str) -> Optional[Airport]:
        """Look up airport by 4-letter ICAO code. Returns None if not found."""
        return self._db.get(icao.strip().upper())

    def in_bbox(
        self,
        lat_min: float,
        lon_min: float,
        lat_max: float,
        lon_max: float,
        major_only: bool = True,
    ) -> list[Airport]:
        """
        Return all airports inside the bounding box.
        major_only=True  → only large + medium airports (default)
        major_only=False → all types including small / heliport
        """
        results = []
        for apt in self._db.values():
            if not (lat_min <= apt.latitude <= lat_max):
                continue
            if not (lon_min <= apt.longitude <= lon_max):
                continue
            if major_only and not apt.is_major:
                continue
            results.append(apt)
        return results

    @property
    def loaded(self) -> bool:
        return self._loaded

    def __len__(self) -> int:
        return len(self._db)