"""Spatial filtering via Google Maps APIs."""
import json
import math
from datetime import date
from pathlib import Path

import requests

from .config import (
    FILTERED_DIR,
    GOOGLE_MAPS_API_KEY,
    MAX_WALK_MINUTES,
    MIN_ORR_DISTANCE_METERS,
    ORR_REFERENCE_POINTS,
    PTP_LAT,
    PTP_LON,
)
from .models import ListingDetail, ListingSummary


def geocode_address(address: str, locality: str) -> tuple[float, float] | None:
    """Geocode an address via Google Maps Geocoding API. Returns (lat, lon) or None."""
    if not GOOGLE_MAPS_API_KEY:
        raise RuntimeError("GOOGLE_MAPS_API_KEY not set in .env")

    query = f"{address}, {locality}, Bangalore, Karnataka, India"
    resp = requests.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        params={"address": query, "key": GOOGLE_MAPS_API_KEY},
        timeout=10,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        return None
    loc = results[0]["geometry"]["location"]
    return (loc["lat"], loc["lng"])


def get_walk_duration(lat: float, lon: float) -> float | None:
    """Get walking duration in minutes from coordinates to PTP via Distance Matrix API."""
    if not GOOGLE_MAPS_API_KEY:
        raise RuntimeError("GOOGLE_MAPS_API_KEY not set in .env")

    resp = requests.get(
        "https://maps.googleapis.com/maps/api/distancematrix/json",
        params={
            "origins": f"{lat},{lon}",
            "destinations": f"{PTP_LAT},{PTP_LON}",
            "mode": "walking",
            "key": GOOGLE_MAPS_API_KEY,
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    try:
        element = data["rows"][0]["elements"][0]
        if element["status"] != "OK":
            return None
        return element["duration"]["value"] / 60.0
    except (KeyError, IndexError):
        return None


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in meters between two points."""
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def min_orr_distance(lat: float, lon: float) -> float:
    """Minimum distance in meters from coordinates to ORR reference points."""
    return min(haversine_meters(lat, lon, rlat, rlon) for rlat, rlon in ORR_REFERENCE_POINTS)


def filter_listings(listings: list[ListingSummary]) -> list[ListingDetail]:
    """Geocode, compute distances, filter by walk time and ORR distance."""
    passed = []

    for i, ls in enumerate(listings):
        print(f"[{i+1}/{len(listings)}] Geocoding: {ls.title[:60]}...")
        coords = geocode_address(ls.address or ls.title, ls.locality)
        if not coords:
            print(f"  Skipped: geocoding failed")
            continue

        lat, lon = coords
        walk = get_walk_duration(lat, lon)
        if walk is None:
            print(f"  Skipped: walk duration unavailable")
            continue
        if walk > MAX_WALK_MINUTES:
            print(f"  Skipped: {walk:.1f}min walk (max {MAX_WALK_MINUTES})")
            continue

        orr_dist = min_orr_distance(lat, lon)
        if orr_dist < MIN_ORR_DISTANCE_METERS:
            print(f"  Skipped: {orr_dist:.0f}m from ORR (min {MIN_ORR_DISTANCE_METERS})")
            continue

        detail = ListingDetail(
            **ls.model_dump(),
            latitude=lat,
            longitude=lon,
        )
        detail.source_locality = ls.source_locality
        passed.append(detail)
        print(f"  PASSED: {walk:.1f}min walk, {orr_dist:.0f}m from ORR")

    return passed


def save_filtered(listings: list[ListingDetail], tag: str = "") -> Path:
    """Save filtered listings to timestamped JSON."""
    FILTERED_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{date.today().isoformat()}{'-' + tag if tag else ''}.json"
    path = FILTERED_DIR / filename
    path.write_text(json.dumps([l.model_dump() for l in listings], indent=2))
    print(f"Saved {len(listings)} filtered listings to {path}")
    return path


def run(raw_path: Path | str) -> Path | None:
    """Load raw listings, filter, save."""
    raw = json.loads(Path(raw_path).read_text())
    listings = [ListingSummary(**item) for item in raw]
    filtered = filter_listings(listings)
    if filtered:
        return save_filtered(filtered)
    print("No listings passed spatial filter.")
    return None
