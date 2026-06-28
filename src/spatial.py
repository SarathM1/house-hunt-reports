import json
import math
from pathlib import Path

import httpx

from .config import GOOGLE_MAPS_API_KEY, ORR_REFERENCE_POINTS, RunContext
from .models import PeaceBreakdown


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


def get_travel_duration(
    lat: float, lon: float, ptp_coords: tuple[float, float],
    mode: str = "walking", api_key: str = ""
) -> float | None:
    api_key = api_key or GOOGLE_MAPS_API_KEY
    if not api_key:
        raise RuntimeError("GOOGLE_MAPS_API_KEY not set")
    params = {
        "origins": f"{lat},{lon}",
        "destinations": f"{ptp_coords[0]},{ptp_coords[1]}",
        "mode": mode,
        "key": api_key,
    }
    # For driving mode, use peak hour traffic estimate (9 AM Monday)
    if mode == "driving":
        import calendar, time as _time
        from datetime import datetime, timedelta
        now = datetime.now()
        days_ahead = (0 - now.weekday()) % 7 or 7
        next_monday = now + timedelta(days=days_ahead)
        peak = next_monday.replace(hour=9, minute=0, second=0, microsecond=0)
        params["departure_time"] = int(peak.timestamp())
    resp = httpx.get(
        "https://maps.googleapis.com/maps/api/distancematrix/json",
        params=params,
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    try:
        element = data["rows"][0]["elements"][0]
        if element["status"] != "OK":
            return None
        # Use duration_in_traffic if available (driving mode)
        duration = element.get("duration_in_traffic", element["duration"])
        return duration["value"] / 60.0
    except (KeyError, IndexError):
        return None


# Backward compat
def get_walk_duration(
    lat: float, lon: float, ptp_coords: tuple[float, float], api_key: str = ""
) -> float | None:
    return get_travel_duration(lat, lon, ptp_coords, mode="walking", api_key=api_key)


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

LOCALITY_CENTERS = {
    "kadubeesanahalli": (12.9360, 77.6880),
    "bellandur": (12.9261, 77.6757),
    "panathur": (12.9411, 77.6990),
    "marathahalli": (12.9591, 77.7000),
    "whitefield": (12.9698, 77.7500),
    "harlur": (12.9080, 77.6630),
    "sarjapur": (12.8650, 77.7700),
    "hsr-layout": (12.9116, 77.6389),
    "koramangala": (12.9279, 77.6271),
    "electronic-city": (12.8440, 77.6630),
    "btm-layout": (12.9166, 77.6101),
}

MAX_GEOCODE_DRIFT_M = 10000


def _validate_geocode(lat: float, lon: float, locality: str) -> bool:
    center = LOCALITY_CENTERS.get(locality)
    if not center:
        return True
    return haversine_meters(lat, lon, center[0], center[1]) <= MAX_GEOCODE_DRIFT_M


def compute_peace_score(orr_distance_m: float, locality: str) -> tuple[float, PeaceBreakdown]:
    bonus = 20 if locality in PRIORITY_LOCALITIES else 0
    if orr_distance_m < 200:
        breakdown = PeaceBreakdown(orr_distance_m=orr_distance_m, base_score=0, locality_bonus=0, final=0)
        return 0.0, breakdown
    if orr_distance_m < 400:
        base = 30 + (orr_distance_m - 200) * (30 / 200)
    else:
        base = 60 + min(20, (orr_distance_m - 400) * (20 / 600))
    final = min(100, base + bonus)
    breakdown = PeaceBreakdown(orr_distance_m=orr_distance_m, base_score=round(base, 1), locality_bonus=bonus, final=final)
    return final, breakdown


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

        coords = geocode_address(summary["title"], summary["locality"])
        if coords and not _validate_geocode(coords[0], coords[1], summary["locality"]):
            _log(f"  Geocode drifted, retrying with address...")
            coords = geocode_address(summary["address"], summary["locality"])
        if not coords:
            _log("  Skipped: geocoding failed")
            continue
        if not _validate_geocode(coords[0], coords[1], summary["locality"]):
            _log(f"  Skipped: geocode too far from {summary['locality']}")
            continue

        lat, lon = coords
        mode = getattr(config, "travel_mode", "walking")
        travel = get_travel_duration(lat, lon, config.ptp_coords, mode=mode)
        if travel is None:
            _log(f"  Skipped: {mode} duration unavailable")
            continue
        if travel > config.max_walk_minutes:
            _log(f"  Skipped: {travel:.1f}min {mode} (max {config.max_walk_minutes})")
            continue

        orr_dist = min_orr_distance(lat, lon)
        if orr_dist < config.min_orr_distance_m:
            _log(f"  Skipped: {orr_dist:.0f}m from ORR (min {config.min_orr_distance_m})")
            continue

        peace, peace_breakdown = compute_peace_score(orr_dist, summary["locality"])
        passed.append({
            **entry,
            "lat": lat,
            "lon": lon,
            "walk_minutes": round(travel, 1),
            "orr_distance_m": round(orr_dist, 0),
            "peace_score": round(peace, 1),
            "peace_breakdown": peace_breakdown.model_dump(),
        })
        _log(f"  ✓ PASSED: {travel:.1f}min {mode}, {orr_dist:.0f}m ORR, peace={peace:.0f}")

    _log(f"\n{len(passed)}/{len(raw_data)} passed spatial filter")

    # Phase 2: scrape detail pages for survivors via Playwright (renders SPA)
    if passed:
        from .detail_scraper import scrape_details_playwright
        passed = scrape_details_playwright(passed, with_images=True)

    out_path = ctx.path("filtered.json")
    out_path.write_text(json.dumps(passed, indent=2))
    _log(f"Saved {len(passed)} listings to {out_path}")
    return out_path
