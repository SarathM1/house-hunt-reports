"""LLM-as-a-Judge scoring for qualified listings."""
import json
from datetime import date
from pathlib import Path

import anthropic

from .config import SCORED_DIR, MIN_SCORE_FOR_REPORT
from .models import ListingDetail, ScoredListing

JUDGE_PROMPT = """You are evaluating a rental apartment listing for a hybrid worker who needs:
- 100% power backup (HARD REQUIREMENT - generator, not just inverter)
- Peaceful, quiet environment away from road noise
- Good building maintenance and management
- Suitable for remote work (stable internet likely, quiet during work hours)

Rate this listing from 0-100. Deduct heavily for:
- No mention of power backup or only inverter (-40 points)
- Near highway/main road noise indicators (-20 points)
- Poor maintenance indicators (-15 points)
- Broker listing vs owner listing (-10 points)

Evaluate this listing:

Title: {title}
Address: {address}
Rent: ₹{rent} + ₹{maintenance} maintenance
Deposit: ₹{deposit}
Area: {sqft} sqft
Furnishing: {furnishing}
Floor: {floor}
Building Age: {building_age}
Water Supply: {water_supply}
Gated Security: {gated_security}
Power Backup: {power_backup}
Parking: {parking}
Description: {description}

Walk to Prestige Tech Park: {walk_minutes:.1f} minutes
Distance from Outer Ring Road: {orr_distance:.0f} meters

Respond with ONLY valid JSON:
{{"score": <0-100>, "reasoning": "<2-3 sentence explanation>"}}"""


def score_listing(listing: ListingDetail) -> ScoredListing:
    """Score a single listing using Claude as judge."""
    client = anthropic.Anthropic()

    prompt = JUDGE_PROMPT.format(
        title=listing.title,
        address=listing.address,
        rent=listing.rent,
        maintenance=listing.maintenance,
        deposit=listing.deposit,
        sqft=listing.sqft,
        furnishing=listing.furnishing or "Unknown",
        floor=listing.floor or "Unknown",
        building_age=listing.building_age or "Unknown",
        water_supply=listing.water_supply or "Unknown",
        gated_security=listing.gated_security or "Unknown",
        power_backup=listing.power_backup or "Unknown",
        parking=listing.parking or "Unknown",
        description=listing.description[:500] or "No description",
        walk_minutes=listing.walk_minutes or 0,
        orr_distance=listing.orr_distance_meters or 0,
    )

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    # ponytail: naive JSON parse — add retry/fallback if Claude returns non-JSON
    result = json.loads(text)

    orr_dist = listing.orr_distance_meters or 0
    peace_score = min(10, orr_dist / 100)  # 0-10 scale, 1000m+ = max

    return ScoredListing(
        **listing.model_dump(),
        peace_score=peace_score,
        llm_score=result["score"],
        llm_reasoning=result["reasoning"],
        total_score=result["score"] * 0.7 + peace_score * 3,  # weighted blend
    )


def score_all(listings: list[ListingDetail]) -> list[ScoredListing]:
    """Score all listings."""
    scored = []
    for i, listing in enumerate(listings):
        print(f"[{i+1}/{len(listings)}] Scoring: {listing.title[:60]}...")
        try:
            s = score_listing(listing)
            scored.append(s)
            print(f"  Score: {s.total_score:.1f} (LLM: {s.llm_score}, Peace: {s.peace_score:.1f})")
        except Exception as e:
            print(f"  Error scoring: {e}")
    return scored


def save_scored(listings: list[ScoredListing], tag: str = "") -> Path:
    """Save scored listings to timestamped JSON."""
    SCORED_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{date.today().isoformat()}{'-' + tag if tag else ''}.json"
    path = SCORED_DIR / filename
    path.write_text(json.dumps([l.model_dump() for l in listings], indent=2))
    print(f"Saved {len(listings)} scored listings to {path}")
    return path


def run(filtered_path: Path | str) -> Path | None:
    """Load filtered listings, score, save."""
    raw = json.loads(Path(filtered_path).read_text())
    listings = [ListingDetail(**item) for item in raw]
    scored = score_all(listings)
    if scored:
        return save_scored(scored)
    print("No listings scored.")
    return None
