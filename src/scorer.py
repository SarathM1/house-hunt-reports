import json
from pathlib import Path

import anthropic

from .config import RunContext
from .db import Dedup
from .models import ScoredListing

JUDGE_TEMPLATE = """You are evaluating a rental apartment listing for a hybrid worker near Prestige Tech Park, Bangalore.
The tenant works remotely ~22 days/month from home, commutes to office only ~8 days/month.

LISTING:
Title: {title}
Address: {address}
Rent: ₹{rent:,}/month | Area: {sqft} sqft
Furnishing: {furnishing} | Floor: {floor}
Power Backup: {power_backup}
Water Supply: {water_supply}
Gated Security: {gated_security}
Walking to PTP: {walk_minutes:.1f} minutes
Distance from ORR: {orr_distance_m:.0f} meters
Description: {description}

HARD REQUIREMENT:
100% power backup (full generator covering entire apartment) is mandatory.
If power backup is missing, unknown, partial, or inverter-only → disqualify immediately.

SCORING CRITERIA (rate 0-100 total):
- Power backup quality & coverage: {w_power_backup} points — Generator vs inverter, full vs partial, explicit mention
- Noise insulation / peaceful environment: {w_noise} points — Description signals, floor level, facing away from road
- Internet/connectivity infrastructure: {w_internet} points — Fiber-ready, broadband mentions, ACT/Airtel availability
- Natural light, ventilation, floor level: {w_light_ventilation} points — Facing, balconies, mid-floor (2-4) preference
- Water supply reliability: {w_water} points — Corporation + borewell + sump > borewell-only
- Building maintenance & security: {w_maintenance} points — Gated community, managed maintenance, security staff
- WFH livability (space, furnishing): {w_wfh_livability} points — Room for desk, semi/fully furnished, quiet layout
- Value for money: {w_value} points — Rent vs sqft vs amenities ratio

Respond with ONLY valid JSON:
{{"score": <0-100>, "reasoning": "<2-3 sentences>", "disqualified": <true|false>, "disqualify_reason": "<reason or null>"}}"""


def build_judge_prompt(
    summary: dict,
    detail: dict,
    walk_minutes: float,
    orr_distance_m: float,
    llm_weights: dict[str, int],
) -> str:
    return JUDGE_TEMPLATE.format(
        title=summary.get("title", "Unknown"),
        address=summary.get("address", "Unknown"),
        rent=summary.get("rent", 0),
        sqft=summary.get("sqft", 0),
        furnishing=detail.get("furnishing") or "Unknown",
        floor=detail.get("floor") or "Unknown",
        power_backup=detail.get("power_backup") or "Unknown",
        water_supply=detail.get("water_supply") or "Unknown",
        gated_security=detail.get("gated_security", "Unknown"),
        walk_minutes=walk_minutes,
        orr_distance_m=orr_distance_m,
        description=(detail.get("description") or "No description")[:500],
        w_power_backup=llm_weights.get("power_backup", 20),
        w_noise=llm_weights.get("noise", 20),
        w_internet=llm_weights.get("internet", 15),
        w_light_ventilation=llm_weights.get("light_ventilation", 10),
        w_water=llm_weights.get("water", 10),
        w_maintenance=llm_weights.get("maintenance", 10),
        w_wfh_livability=llm_weights.get("wfh_livability", 10),
        w_value=llm_weights.get("value", 5),
    )


def score_listing(
    summary: dict,
    detail: dict,
    spatial: dict,
    llm_weights: dict[str, int],
) -> dict:
    client = anthropic.Anthropic()
    prompt = build_judge_prompt(
        summary=summary,
        detail=detail or {},
        walk_minutes=spatial["walk_minutes"],
        orr_distance_m=spatial["orr_distance_m"],
        llm_weights=llm_weights,
    )
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(text)


def run_score(ctx: RunContext) -> Path:
    config = ctx.config
    filtered_path = ctx.path("filtered.json")
    entries = json.loads(filtered_path.read_text())
    dedup = Dedup()
    scored = []

    for i, entry in enumerate(entries):
        summary = entry["summary"]
        detail = entry.get("detail") or {}
        title = summary["title"][:50]
        print(f"[{i + 1}/{len(entries)}] Scoring: {title}...")

        try:
            result = score_listing(
                summary=summary,
                detail=detail,
                spatial={"walk_minutes": entry["walk_minutes"], "orr_distance_m": entry["orr_distance_m"]},
                llm_weights=config.llm_weights,
            )

            peace = entry["peace_score"]
            llm = result["score"]
            w = config.score_weights
            final = w["peace"] * peace + w["llm"] * llm

            item = ScoredListing(
                summary=summary,
                detail=detail,
                lat=entry["lat"],
                lon=entry["lon"],
                walk_minutes=entry["walk_minutes"],
                orr_distance_m=entry["orr_distance_m"],
                peace_score=peace,
                llm_score=llm,
                llm_reasoning=result["reasoning"],
                final_score=round(final, 1),
                disqualified=result.get("disqualified", False),
                disqualify_reason=result.get("disqualify_reason"),
            )
            scored.append(item.model_dump())
            dedup.update_score(summary["property_id"], final, result.get("disqualified", False))
            status = "DISQ" if item.disqualified else "OK"
            print(f"  [{status}] Score: {final:.1f} (LLM:{llm} Peace:{peace:.0f})")
        except Exception as e:
            print(f"  Error: {e}")

    out_path = ctx.path("scored.json")
    out_path.write_text(json.dumps(scored, indent=2))
    print(f"Saved {len(scored)} scored listings to {out_path}")
    return out_path
