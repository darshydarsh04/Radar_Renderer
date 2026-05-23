# tests/test_fetcher.py
import json, pytest
from unittest.mock import patch, MagicMock
from src.fetcher import fetch_flights

# Load a saved real API response (record once, reuse forever)
with open("tests/fixtures/opensky_response.json") as f:
    FIXTURE = json.load(f)


class TestFetchFlights:
    @patch("src.fetcher.requests.get")
    def test_returns_flight_list_on_success(self, mock_get):
        mock_get.return_value = MagicMock(
            ok=True,
            json=lambda: FIXTURE,
            raise_for_status=lambda: None
        )
        flights = fetch_flights()
        assert isinstance(flights, list)
        assert len(flights) > 0

    @patch("src.fetcher.requests.get")
    def test_filters_flights_with_no_position(self, mock_get):
        payload = {"states": [
            ["aaa", "FL001", "UAE", 0, 0, 55.0, 25.0, 5000.0,
             False, 200.0, 90.0, 0.0, None, 5500.0, None, False, 0],
            ["bbb", "FL002", "UAE", 0, 0, None, None, 5000.0,   # no position
             False, 200.0, 90.0, 0.0, None, 5500.0, None, False, 0],
        ]}
        mock_get.return_value = MagicMock(
            ok=True, json=lambda: payload, raise_for_status=lambda: None
        )
        flights = fetch_flights()
        assert len(flights) == 1
        assert flights[0].icao24 == "aaa"

    @patch("src.fetcher.requests.get", side_effect=Exception("timeout"))
    def test_returns_empty_list_on_network_error(self, _):
        flights = fetch_flights()
        assert flights == []

    @patch("src.fetcher.requests.get")
    def test_returns_empty_on_null_states(self, mock_get):
        mock_get.return_value = MagicMock(
            ok=True, json=lambda: {"states": None}, raise_for_status=lambda: None
        )
        assert fetch_flights() == []