# Scoring Transparency & Pipeline Rearchitecture

**Date:** 2026-06-28
**Status:** Draft
**Scope:** Structured LLM scoring, report transparency, pipeline hardening

## Problem

LLM judge returns a single score + 2-3 sentence blob. Report shows opaque number. Shared audience (partner/family) can't understand why a listing scored 78 vs 85. No per-criteria breakdown, no pros/cons, no comparison context.

## Design

### 1. Two-Pass Structured Scoring

#### Pass 1 — Independent Structured Evaluation

Each listing scored independently by Claude Code (as LLM judge). Prompted to return structured JSON, validated by Pydantic. On parse failure, retry once with error feedback.

Response schema:

```json
{
  "criteria_scores": {
    "power_backup": {"score": 18, "max": 20, "confidence": "high", "evidence": "Full generator mentioned in description"},
    "noise": {"score": 14, "max": 20, "confidence": "medium", "evidence": "3rd floor, no road-facing info"},
    "internet": {"score": 10, "max": 15, "confidence": "low", "evidence": "No mention of fiber or broadband"},
    "light_ventilation": {"score": 8, "max": 10, "confidence": "medium", "evidence": "East facing, 2 balconies"},
    "water": {"score": 7, "max": 10, "confidence": "high", "evidence": "Corporation + borewell + sump"},
    "maintenance": {"score": 8, "max": 10, "confidence": "high", "evidence": "Gated community, 24/7 security"},
    "wfh_livability": {"score": 7, "max": 10, "confidence": "medium", "evidence": "Semi-furnished, spacious rooms"},
    "value": {"score": 4, "max": 5, "confidence": "high", "evidence": "₹28/sqft, below area average"}
  },
  "pros": ["Full generator backup", "8min walk to PTP", "Gated community with 24/7 security"],
  "cons": ["No fiber internet mentioned", "Semi-furnished only — desk setup needed"],
  "elevator_pitch": "Quiet 3rd-floor gated apartment with full generator, 8min walk to PTP",
  "disqualified": false,
  "disqualify_reason": null
}
```

Fields:
- `criteria_scores`: per-criterion score, max (from config weights), confidence (high/medium/low), evidence (what text drove the score)
- `pros`: 2-5 human-readable green bullets
- `cons`: 1-4 human-readable red bullets
- `elevator_pitch`: 1-line shareable summary
- `disqualified` / `disqualify_reason`: same as current

`llm_score` = sum of all criteria scores (0-100).

#### Pass 2 — Comparative Ranking

After all listings scored independently, one Claude Code call sees all qualified listings and:
- Adjusts scores relative to pool (normalizes grade inflation)
- Flags ties with differentiation notes
- Produces top-3 recommendation with reasoning

Input: all qualified listings with their Pass 1 scores and criteria breakdowns.
Output:

```json
{
  "rankings": [
    {"property_id": "abc123", "rank": 1, "reasoning": "Best overall: strong power backup + closest walk + good value"},
    {"property_id": "def456", "rank": 2, "reasoning": "Quieter location but weaker internet infrastructure"}
  ],
  "top_3_summary": "#1 Green Heights — best all-around for WFH. #2 Salarpuria — quieter but farther. #3 Brigade — best value but partial backup."
}
```

Cost: 1 extra LLM call per run regardless of listing count.

### 2. Report Transparency

#### Criteria Breakdown Per Card
- Horizontal bar chart showing each criterion's score vs max
- Color-coded: green ≥80% of max, yellow 50-80%, red <50%
- Confidence dots next to each bar (●●● high, ●●○ medium, ●○○ low)
- Evidence text as tooltip on hover / expandable on tap

#### Pros/Cons
- Green checkmark bullets for pros, red x bullets for cons
- Displayed between props grid and images
- Collapsible on mobile (show first 2 + "show more")

#### Elevator Pitch
- Bold 1-liner below title, before props grid
- Designed for quick understanding by non-technical audience

#### Comparative Context
- Each criteria bar shows run average as faint marker
- "Standout" tag for criteria ≥90% of max
- "Watch out" tag for criteria <40% of max

#### Top-3 Recommendation Banner
- At top of report before cards
- Shows comparative ranking from Pass 2
- "#1 because X, #2 because Y, #3 because Z"

#### New Sort/Filter Options
- Sort by individual criteria (noise, value, etc.)
- Filter by confidence level

### 3. Pipeline Hardening

#### 3a. Structured Output Validation

Claude Code as judge — no Anthropic API key needed. Prompt returns JSON, validated by Pydantic models. On parse failure, retry once with the Pydantic error message appended to prompt.

#### 3b. Detail Scraper Resilience

- After Playwright scrape, validate critical fields: power_backup, water_supply, furnishing
- If critical fields missing, retry scrape once
- Compute `data_completeness` (0-1) = fraction of fields populated
- Pass to LLM so it calibrates confidence appropriately
- Report shows data completeness indicator per card (full/partial/sparse)

#### 3c. Smart Dedup

- After scoring, group listings by building name: lowercase, strip whitespace/punctuation, compare. Group if normalized names match or one contains the other.
- For groups with >1 listing, LLM call determines if truly same property (same unit vs different units in same building)
- Keep best-scored, mark others as "duplicate of [property_id]"
- Report collapses dupes under primary listing
- Cost: ~0-2 LLM calls per run (only on suspected dupe groups)

#### 3d. Peace Score Transparency

- Report shows formula breakdown: "ORR: 450m → base 60, locality bonus: +20 → peace: 80"
- Peace score rendered as bar in criteria chart alongside LLM criteria

### 4. Data Model Changes

#### New Models

```python
class CriteriaScore(BaseModel):
    score: int
    max: int
    confidence: str  # high/medium/low
    evidence: str

class PeaceBreakdown(BaseModel):
    orr_distance_m: float
    base_score: float
    locality_bonus: float
    final: float

class ComparativeResult(BaseModel):
    rankings: list[dict]  # [{property_id, rank, reasoning}]
    top_3_summary: str
```

#### Updated ScoredListing

```python
class ScoredListing(BaseModel):
    summary: ListingSummary
    detail: ListingDetail
    lat: float
    lon: float
    walk_minutes: float
    orr_distance_m: float
    peace_score: float
    llm_score: float
    final_score: float
    disqualified: bool
    disqualify_reason: str | None = None

    # New structured fields
    criteria_scores: dict[str, CriteriaScore]
    pros: list[str]
    cons: list[str]
    elevator_pitch: str
    data_completeness: float

    # Comparative (filled by Pass 2)
    comparative_rank: int | None = None
    comparative_notes: str | None = None

    # Peace breakdown
    peace_breakdown: PeaceBreakdown | None = None

    # Dedup
    duplicate_of: str | None = None
```

Removed: `llm_reasoning` (replaced by pros/cons/elevator_pitch/criteria_scores).

#### Backward Compatibility

Old `scored.json` files won't render in new template. Acceptable — runs are cheap to re-run. `/compare` updated to handle new fields gracefully.

### 5. Cost & Performance

| Stage | Current | Proposed |
|-------|---------|----------|
| Pass 1 (per listing) | 1 call | 1 call (structured prompt) |
| Pass 2 (comparative) | — | 1 call total |
| Dedup | — | 0-2 calls |
| Detail retry | — | 0-N calls (only on missing fields) |
| **Total (15 listings)** | **15 calls** | **~16-18 calls** |

All calls via Claude Code (Max plan) — no API cost. `scored.json` grows ~3x per listing (criteria + evidence). Trivial.

### 6. Files Changed

| File | Change |
|------|--------|
| `src/models.py` | Add CriteriaScore, PeaceBreakdown, ComparativeResult; update ScoredListing |
| `src/scorer.py` | New structured judge prompt, Pydantic validation + retry, Pass 2 comparative call |
| `src/spatial.py` | Return PeaceBreakdown from compute_peace_score |
| `src/detail_scraper.py` | Add retry logic, compute data_completeness |
| `src/reporter.py` | Pass new fields to template, update markdown report format |
| `src/report_template.html` | Criteria bars, pros/cons, elevator pitch, comparative banner, new filters |
| `src/pdf_report.py` | Handle new template (if PDF rendering affected) |
| `tests/` | Update test fixtures for new model fields |
