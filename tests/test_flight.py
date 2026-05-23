# tests/test_flight.py
import pytest
from src.flight import Flight

# A realistic OpenSky state row
VALID_STATE = [
    "abc123", "UAE001 ", "United Arab Emirates",
    1700000000, 1700000001,
    55.3657, 25.2048,   # lon, lat (Dubai)
    10000.0, False,
    250.0, 45.0, 0.0,   # velocity, heading, vertical_rate
    None, 10500.0, None, False, 0
]

MISSING_POSITION = list(VALID_STATE)
MISSING_POSITION[5] = None  # no longitude


class TestFlightFromOpensky:
    def test_parses_valid_state(self):
        f = Flight.from_opensky(VALID_STATE)
        assert f is not None
        assert f.icao24 == "abc123"
        assert f.longitude == 55.3657
        assert f.latitude == 25.2048
        assert f.heading == 45.0
        assert f.velocity == 250.0

    def test_strips_callsign_whitespace(self):
        f = Flight.from_opensky(VALID_STATE)
        assert f.callsign == "UAE001"

    def test_returns_none_when_position_missing(self):
        assert Flight.from_opensky(MISSING_POSITION) is None

    def test_null_heading_defaults_to_zero(self):
        state = list(VALID_STATE)
        state[10] = None
        f = Flight.from_opensky(state)
        assert f.heading == 0.0


class TestInterpolation:
    def test_alpha_zero_returns_previous_position(self):
        f = Flight.from_opensky(VALID_STATE)
        f.prev_longitude = 55.0
        f.prev_latitude = 25.0
        lon, lat = f.interpolate(0.0)
        assert lon == pytest.approx(55.0)

    def test_alpha_one_returns_current_position(self):
        f = Flight.from_opensky(VALID_STATE)
        f.prev_longitude = 55.0
        lon, lat = f.interpolate(1.0)
        assert lon == pytest.approx(55.3657)

    def test_alpha_half_is_midpoint(self):
        f = Flight.from_opensky(VALID_STATE)
        f.prev_longitude = 55.0
        lon, _ = f.interpolate(0.5)
        assert lon == pytest.approx(55.0 + (55.3657 - 55.0) / 2)