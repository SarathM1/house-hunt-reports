"""Verify Google Maps API key works for Geocoding and Distance Matrix."""
import os

import httpx
import pytest
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")
PTP_COORDS = (12.9420, 77.6905)


@pytest.fixture
def api_key():
    if not API_KEY:
        pytest.skip("GOOGLE_MAPS_API_KEY not set")
    return API_KEY


def test_geocoding_kaverappa_layout(api_key):
    resp = httpx.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        params={"address": "Kaverappa Layout, Kadubeesanahalli, Bangalore", "key": api_key},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    assert data["status"] == "OK"
    loc = data["results"][0]["geometry"]["location"]
    assert 12.9 < loc["lat"] < 13.0
    assert 77.6 < loc["lng"] < 77.8


def test_distance_matrix_walking_to_ptp(api_key):
    origin = "12.9400,77.6900"
    dest = f"{PTP_COORDS[0]},{PTP_COORDS[1]}"
    resp = httpx.get(
        "https://maps.googleapis.com/maps/api/distancematrix/json",
        params={"origins": origin, "destinations": dest, "mode": "walking", "key": api_key},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    element = data["rows"][0]["elements"][0]
    assert element["status"] == "OK"
    walk_minutes = element["duration"]["value"] / 60.0
    assert 0 < walk_minutes < 30
