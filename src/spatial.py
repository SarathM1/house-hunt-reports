import json
import math
from pathlib import Path

import httpx

from .config import GOOGLE_MAPS_API_KEY, ORR_REFERENCE_POINTS, RunContext


def geocode_address(address: str, locality: str, api_key: str = "") -> tuple[float, float] | None:
    api_key = api_key or GOOGLE_MAPS_API_KEY
    if not api_key:
        raise RuntimeError("GOOGLE_MAPS_API_KEY not set")
    query = f"{address}, {locality}, Bangalore, Karnataka, India"
    resp = httpx.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        params={"address": query, "key": api_key},
        timeout=10,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        return None
    loc = results[0]["geometry"]["location"]
    return (loc["lat"], loc["lng"])


def get_walk_duration(
    lat: float, lon: float, ptp_coords: tuple[float, float], api_key: str = ""
) -> float | None:
    api_key = api_key or GOOGLE_MAPS_API_KEY
    if not api_key:
        raise RuntimeError("GOOGLE_MAPS_API_KEY not set")
    resp = httpx.get(
        "https://maps.googleapis.com/maps/api/distancematrix/json",
        params={
            "origins": f"{lat},{lon}",
            "destinations": f"{ptp_coords[0]},{ptp_coords[1]}",
            "mode": "walking",
            "key": api_key,
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
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def min_orr_distance(lat: float, lon: float) -> float:
    return min(haversine_meters(lat, lon, rlat, rlon) for rlat, rlon in ORR_REFERENCE_POINTS)


PRIORITY_LOCALITIES = {"kadubeesanahalli"}


def compute_peace_score(orr_distance_m: float, locality: str) -> float:
    if orr_distance_m < 200:
        return 0.0
    if orr_distance_m < 400:
        base = 30 + (orr_distance_m - 200) * (30 / 200)
    else:
        base = 60 + min(20, (orr_distance_m - 400) * (20 / 600))
    bonus = 20 if locality in PRIORITY_LOCALITIES else 0
    return min(100, base + bonus)


def _log(msg: str) -> None:
    print(msg, flush=True)


def run_filter(ctx: RunContext) -> Path:
    config = ctx.config
    raw_path = ctx.path("raw.json")
    raw_data = json.loads(raw_path.read_text())
    passed = []

    _log(f"=== Spatial filter: {len(raw_data)} listings ===")
    for i, entry in enumerate(raw_data):
        summary = entry["summary"]
        title = summary["title"][:50]
        _log(f"[{i + 1}/{len(raw_data)}] {title}...")

        # Title has building name + locality — geocodes better than the messy address field
        geocode_query = summary["title"]
        coords = geocode_address(geocode_query, summary["locality"])
        if not coords:
            _log("  Skipped: geocoding failed")
            continue

        lat, lon = coords
        walk = get_walk_duration(lat, lon, config.ptp_coords)
        if walk is None:
            _log("  Skipped: walk duration unavailable")
            continue
        if walk > config.max_walk_minutes:
            _log(f"  Skipped: {walk:.1f}min walk (max {config.max_walk_minutes})")
            continue

        orr_dist = min_orr_distance(lat, lon)
        if orr_dist < config.min_orr_distance_m:
            _log(f"  Skipped: {orr_dist:.0f}m from ORR (min {config.min_orr_distance_m})")
            continue

        peace = compute_peace_score(orr_dist, summary["locality"])
        passed.append({
            **entry,
            "lat": lat,
            "lon": lon,
            "walk_minutes": round(walk, 1),
            "orr_distance_m": round(orr_dist, 0),
            "peace_score": round(peace, 1),
        })
        _log(f"  ✓ PASSED: {walk:.1f}min, {orr_dist:.0f}m ORR, peace={peace:.0f}")

    _log(f"\n{len(passed)}/{len(raw_data)} passed spatial filter")

    # Phase 2: scrape detail pages for survivors only
    if passed:
        from .scraper import run_scrape_details
        passed = run_scrape_details(ctx, passed)

    out_path = ctx.path("filtered.json")
    out_path.write_text(json.dumps(passed, indent=2))
    _log(f"Saved {len(passed)} listings to {out_path}")
    return out_path
