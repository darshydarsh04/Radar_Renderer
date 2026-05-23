# src/flight.py
from dataclasses import dataclass, field
from typing import Optional
import time

@dataclass
class Flight:
    icao24: str
    callsign: Optional[str]
    longitude: float
    latitude: float
    heading: float          # degrees, 0 = north
    altitude: float         # metres
    velocity: float         # m/s
    last_updated: float = field(default_factory=time.time)

    # For smooth animation between API polls
    prev_longitude: float = 0.0
    prev_latitude: float = 0.0

    @classmethod
    def from_opensky(cls, state: list) -> Optional["Flight"]:
        """Parse one row from OpenSky states array."""
        # OpenSky columns: [icao24, callsign, origin_country, time_position,
        #   last_contact, longitude, lat, baro_altitude, on_ground,
        #   velocity, true_track, vertical_rate, sensors, geo_altitude, ...]
        if state[5] is None or state[6] is None:
            return None   # no position data
        return cls(
            icao24=state[0],
            callsign=(state[1] or "").strip() or None,
            longitude=state[5],
            latitude=state[6],
            heading=state[10] or 0.0,
            altitude=state[7] or 0.0,
            velocity=state[9] or 0.0,
        )

    def interpolate(self, alpha: float) -> tuple[float, float]:
        """Return smoothed position. alpha=0 → prev, alpha=1 → current."""
        lon = self.prev_longitude + (self.longitude - self.prev_longitude) * alpha
        lat = self.prev_latitude  + (self.latitude  - self.latitude)  * alpha
        return lon, lat