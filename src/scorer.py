import json
from pathlib import Path

import anthropic

from .config import RunContext
from .db import Dedup
from .models import ComparativeResult, CriteriaScore, RankingEntry, ScoredListing

STRUCTURED_JUDGE_TEMPLATE = """You are evaluating a rental apartment listing for a hybrid worker near Prestige Tech Park, Bangalore.
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
Data Completeness: {data_completeness} (fraction of fields populated)
Description: {description}

HARD REQUIREMENT:
100% power backup (full generator covering entire apartment) is mandatory.
If power backup is missing, unknown, partial, or inverter-only → disqualify immediately.

SCORING CRITERIA — score each independently:
- power_backup (max {w_power_backup} pts): Generator vs inverter, full vs partial, explicit mention
- noise (max {w_noise} pts): Description signals, floor level, facing away from road
- internet (max {w_internet} pts): Fiber-ready, broadband mentions, ACT/Airtel availability
- light_ventilation (max {w_light_ventilation} pts): Facing, balconies, mid-floor (2-4) preference
- water (max {w_water} pts): Corporation + borewell + sump > borewell-only
- maintenance (max {w_maintenance} pts): Gated community, managed maintenance, security staff
- wfh_livability (max {w_wfh_livability} pts): Room for desk, semi/fully furnished, quiet layout
- value (max {w_value} pts): Rent vs sqft vs amenities ratio

CONFIDENCE LEVELS:
- "high": listing explicitly states this info
- "medium": inferred from description or context
- "low": no info available, scoring based on defaults/assumptions

Respond with ONLY valid JSON:
{{
  "criteria_scores": {{
    "power_backup": {{"score": <0-{w_power_backup}>, "max": {w_power_backup}, "confidence": "<high|medium|low>", "evidence": "<what drove this score>"}},
    "noise": {{"score": <0-{w_noise}>, "max": {w_noise}, "confidence": "<high|medium|low>", "evidence": "<what drove this score>"}},
    "internet": {{"score": <0-{w_internet}>, "max": {w_internet}, "confidence": "<high|medium|low>", "evidence": "<what drove this score>"}},
    "light_ventilation": {{"score": <0-{w_light_ventilation}>, "max": {w_light_ventilation}, "confidence": "<high|medium|low>", "evidence": "<what drove this score>"}},
    "water": {{"score": <0-{w_water}>, "max": {w_water}, "confidence": "<high|medium|low>", "evidence": "<what drove this score>"}},
    "maintenance": {{"score": <0-{w_maintenance}>, "max": {w_maintenance}, "confidence": "<high|medium|low>", "evidence": "<what drove this score>"}},
    "wfh_livability": {{"score": <0-{w_wfh_livability}>, "max": {w_wfh_livability}, "confidence": "<high|medium|low>", "evidence": "<what drove this score>"}},
    "value": {{"score": <0-{w_value}>, "max": {w_value}, "confidence": "<high|medium|low>", "evidence": "<what drove this score>"}}
  }},
  "pros": ["<2-5 key strengths>"],
  "cons": ["<1-4 key weaknesses>"],
  "elevator_pitch": "<1-line shareable summary for non-technical reader>",
  "disqualified": <true|false>,
  "disqualify_reason": "<reason or null>"
}}"""


def build_structured_judge_prompt(
    summary: dict,
    detail: dict,
    walk_minutes: float,
    orr_distance_m: float,
    data_completeness: float,
    llm_weights: dict[str, int],
) -> str:
    return STRUCTURED_JUDGE_TEMPLATE.format(
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
        data_completeness=data_completeness,
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


def parse_structured_score(text: str, llm_weights: dict[str, int]) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}")

    for key in llm_weights:
        if key not in data.get("criteria_scores", {}):
            raise ValueError(f"Missing criterion: {key}")
        cs = data["criteria_scores"][key]
        CriteriaScore(**cs)

    if not isinstance(data.get("pros"), list) or not data["pros"]:
        raise ValueError("pros must be a non-empty list")
    if not isinstance(data.get("cons"), list) or not data["cons"]:
        raise ValueError("cons must be a non-empty list")
    if not isinstance(data.get("elevator_pitch"), str) or not data["elevator_pitch"]:
        raise ValueError("elevator_pitch must be a non-empty string")

    return data


def score_listing(
    summary: dict,
    detail: dict,
    spatial: dict,
    llm_weights: dict[str, int],
    data_completeness: float,
) -> dict:
    client = anthropic.Anthropic()
    prompt = build_structured_judge_prompt(
        summary=summary,
        detail=detail or {},
        walk_minutes=spatial["walk_minutes"],
        orr_distance_m=spatial["orr_distance_m"],
        data_completeness=data_completeness,
        llm_weights=llm_weights,
    )
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    try:
        return parse_structured_score(text, llm_weights)
    except ValueError as e:
        retry_prompt = f"{prompt}\n\nYour previous response had an error: {e}\nPlease fix and respond with valid JSON only."
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": retry_prompt}],
        )
        text = response.content[0].text.strip()
        return parse_structured_score(text, llm_weights)


COMPARATIVE_TEMPLATE = """You are comparing rental apartments for a hybrid worker near Prestige Tech Park, Bangalore.

Below are all qualified (non-disqualified) listings with their independent scores.
Review them comparatively and produce a final ranking.

LISTINGS:
{listings_block}

TASK:
1. Rank all listings from best to worst for a WFH-heavy hybrid worker
2. For each listing, explain in 1 sentence why it ranks where it does relative to the others
3. Write a top_3_summary: a shareable 1-line-each summary of the top 3 picks

Respond with ONLY valid JSON:
{{"rankings": [{{"property_id": "<id>", "rank": <1-N>, "reasoning": "<1 sentence vs others>"}}], "top_3_summary": "<#1 Name — why. #2 Name — why. #3 Name — why.>"}}"""


def build_comparative_prompt(scored_listings: list[dict]) -> str:
    lines = []
    for e in scored_listings:
        s = e["summary"]
        lines.append(f"- {s['property_id']}: {s['title']} | ₹{s['rent']:,} | {s.get('sqft', '?')}sqft | Score: {e['final_score']}")
        lines.append(f"  LLM: {e['llm_score']} | Peace: {e['peace_score']}")
        lines.append(f"  Pros: {', '.join(e.get('pros', []))}")
        lines.append(f"  Cons: {', '.join(e.get('cons', []))}")
        if e.get("criteria_scores"):
            scores_str = ", ".join(f"{k}: {v['score']}/{v['max']}" for k, v in e["criteria_scores"].items())
            lines.append(f"  Criteria: {scores_str}")
    return COMPARATIVE_TEMPLATE.format(listings_block="\n".join(lines))


def parse_comparative_result(text: str) -> ComparativeResult:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}")
    rankings = [RankingEntry(**r) for r in data.get("rankings", [])]
    if not rankings:
        raise ValueError("rankings must be non-empty")
    return ComparativeResult(rankings=rankings, top_3_summary=data.get("top_3_summary", ""))


def run_comparative_ranking(scored: list[dict]) -> ComparativeResult | None:
    qualified = [e for e in scored if not e.get("disqualified")]
    if len(qualified) < 2:
        return None
    client = anthropic.Anthropic()
    prompt = build_comparative_prompt(qualified)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    try:
        return parse_comparative_result(text)
    except ValueError as e:
        retry_prompt = f"{prompt}\n\nYour previous response had an error: {e}\nPlease fix and respond with valid JSON only."
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            messages=[{"role": "user", "content": retry_prompt}],
        )
        return parse_comparative_result(response.content[0].text.strip())


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
                data_completeness=entry.get("data_completeness", 0.5),
            )

            llm = sum(cs["score"] for cs in result["criteria_scores"].values())
            peace = entry["peace_score"]
            w = config.score_weights
            final = w["peace"] * peace + w["llm"] * llm

            if not detail or not detail.get("property_id"):
                base = {"property_id": summary["property_id"], "furnishing": "", "floor": "", "description": ""}
                if detail:
                    base.update({k: v for k, v in detail.items() if v is not None})
                detail = base

            criteria_scores = {k: CriteriaScore(**v) for k, v in result["criteria_scores"].items()}

            item = ScoredListing(
                summary=summary,
                detail=detail,
                lat=entry["lat"],
                lon=entry["lon"],
                walk_minutes=entry["walk_minutes"],
                orr_distance_m=entry["orr_distance_m"],
                peace_score=peace,
                llm_score=llm,
                final_score=round(final, 1),
                disqualified=result.get("disqualified", False),
                disqualify_reason=result.get("disqualify_reason"),
                criteria_scores=criteria_scores,
                pros=result["pros"],
                cons=result["cons"],
                elevator_pitch=result["elevator_pitch"],
                data_completeness=entry.get("data_completeness", 0.5),
                peace_breakdown=entry.get("peace_breakdown"),
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

    # Pass 2: Comparative ranking
    comparative = run_comparative_ranking(scored)
    if comparative:
        for ranking in comparative.rankings:
            for entry in scored:
                if entry["summary"]["property_id"] == ranking.property_id:
                    entry["comparative_rank"] = ranking.rank
                    entry["comparative_notes"] = ranking.reasoning
                    break
        out_path.write_text(json.dumps(scored, indent=2))
        print(f"Comparative ranking: {comparative.top_3_summary[:100]}...")

        comp_path = ctx.path("comparative.json")
        comp_path.write_text(json.dumps(comparative.model_dump(), indent=2))

    return out_path
