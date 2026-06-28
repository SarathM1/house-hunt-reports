# Scoring Transparency & Pipeline Rearchitecture — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace opaque LLM scoring blob with structured per-criteria scores, pros/cons, confidence levels, and comparative rankings — rendered transparently in the HTML report.

**Architecture:** Two-pass scoring (independent structured eval per listing → comparative ranking across all qualified). Pipeline hardening: detail scraper retry + data completeness, smart dedup, peace score breakdown. Claude Code as judge (no API key). HTML report shows criteria bar charts, pros/cons bullets, elevator pitch, comparative banner.

**Tech Stack:** Python 3.12, Pydantic, Jinja2, Playwright (detail scraper), vanilla JS/CSS in HTML template.

## Global Constraints

- Python venv: `.venv/bin/python`
- Run tests: `.venv/bin/python -m pytest tests/ -v`
- No new dependencies unless explicitly approved
- No PDF generation (out of scope)
- Claude Code is the LLM judge — no Anthropic API key needed
- All data in `data/runs/{timestamp}/` — never overwrite existing runs

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/models.py` | Modify | Add CriteriaScore, PeaceBreakdown, ComparativeResult, RankingEntry; update ScoredListing |
| `src/scorer.py` | Modify | New structured judge prompt, Pydantic validation + retry, Pass 2 comparative |
| `src/spatial.py` | Modify | Return PeaceBreakdown from compute_peace_score |
| `src/detail_scraper.py` | Modify | Retry logic for missing critical fields, compute data_completeness |
| `src/reporter.py` | Modify | Pass new fields to template, update markdown report, update compare_runs |
| `src/report_template.html` | Rewrite | Criteria bars, pros/cons, elevator pitch, comparative banner, new filters/sorts |
| `.claude/skills/score/SKILL.md` | Modify | Update scored.json schema for Claude Code judge |
| `tests/test_models.py` | Modify | Tests for new models |
| `tests/test_scorer.py` | Modify | Tests for new prompt builder + parse/validate |
| `tests/test_spatial.py` | Modify | Test peace score breakdown |
| `tests/test_detail_scraper.py` | Create | Test data_completeness + retry logic |
| `tests/test_reporter.py` | Modify | Update fixtures for new ScoredListing shape |

---

### Task 1: Data Models — CriteriaScore, PeaceBreakdown, ComparativeResult, Updated ScoredListing

**Files:**
- Modify: `src/models.py`
- Modify: `tests/test_models.py`

**Interfaces:**
- Consumes: nothing (foundation task)
- Produces: `CriteriaScore(score: int, max: int, confidence: str, evidence: str)`, `PeaceBreakdown(orr_distance_m: float, base_score: float, locality_bonus: float, final: float)`, `RankingEntry(property_id: str, rank: int, reasoning: str)`, `ComparativeResult(rankings: list[RankingEntry], top_3_summary: str)`, updated `ScoredListing` with new fields

- [ ] **Step 1: Write failing tests for new models**

```python
# tests/test_models.py — add these tests

def test_criteria_score():
    from src.models import CriteriaScore
    cs = CriteriaScore(score=18, max=20, confidence="high", evidence="Full generator mentioned")
    assert cs.score == 18
    assert cs.max == 20
    assert cs.confidence == "high"
    d = cs.model_dump()
    assert d["evidence"] == "Full generator mentioned"


def test_criteria_score_validation():
    from src.models import CriteriaScore
    import pytest
    with pytest.raises(Exception):
        CriteriaScore(score=18, max=20, confidence="invalid", evidence="test")


def test_peace_breakdown():
    from src.models import PeaceBreakdown
    pb = PeaceBreakdown(orr_distance_m=450, base_score=60, locality_bonus=20, final=80)
    assert pb.final == 80
    assert pb.locality_bonus == 20


def test_ranking_entry():
    from src.models import RankingEntry
    re = RankingEntry(property_id="abc123", rank=1, reasoning="Best overall")
    assert re.rank == 1


def test_comparative_result():
    from src.models import ComparativeResult, RankingEntry
    cr = ComparativeResult(
        rankings=[RankingEntry(property_id="abc", rank=1, reasoning="Best")],
        top_3_summary="#1 abc — best overall"
    )
    assert len(cr.rankings) == 1
    assert cr.top_3_summary.startswith("#1")


def test_scored_listing_new_fields():
    from src.models import ListingSummary, ListingDetail, ScoredListing, CriteriaScore, PeaceBreakdown
    summary = ListingSummary(
        property_id="abc123", title="Test", rent=30000, deposit=100000,
        maintenance=None, sqft=1000, address="Test addr",
        locality="bellandur", building_name=None,
        detail_url="https://example.com", available_date=None, image_urls=[]
    )
    detail = ListingDetail(
        property_id="abc123", furnishing="Fully", floor="2/5",
        power_backup="Full", description="Great flat"
    )
    scored = ScoredListing(
        summary=summary, detail=detail,
        lat=12.94, lon=77.69, walk_minutes=8.5, orr_distance_m=350,
        peace_score=75.0, llm_score=82.0,
        final_score=79.2, disqualified=False, disqualify_reason=None,
        criteria_scores={
            "power_backup": CriteriaScore(score=18, max=20, confidence="high", evidence="Full generator"),
            "noise": CriteriaScore(score=14, max=20, confidence="medium", evidence="3rd floor"),
        },
        pros=["Full generator backup", "Gated community"],
        cons=["No fiber mentioned"],
        elevator_pitch="Quiet gated flat with full generator",
        data_completeness=0.85,
        peace_breakdown=PeaceBreakdown(orr_distance_m=350, base_score=52.5, locality_bonus=0, final=52.5),
    )
    assert scored.elevator_pitch == "Quiet gated flat with full generator"
    assert scored.criteria_scores["power_backup"].score == 18
    assert scored.data_completeness == 0.85
    assert scored.comparative_rank is None
    assert scored.duplicate_of is None
    d = scored.model_dump()
    assert "criteria_scores" in d
    assert "pros" in d
    assert "peace_breakdown" in d
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_models.py -v`
Expected: FAIL — `CriteriaScore`, `PeaceBreakdown`, etc. not defined

- [ ] **Step 3: Implement new models in src/models.py**

Add after `ListingDetail` class, before `ScoredListing`:

```python
from typing import Literal


class CriteriaScore(BaseModel):
    score: int
    max: int
    confidence: Literal["high", "medium", "low"]
    evidence: str


class PeaceBreakdown(BaseModel):
    orr_distance_m: float
    base_score: float
    locality_bonus: float
    final: float


class RankingEntry(BaseModel):
    property_id: str
    rank: int
    reasoning: str


class ComparativeResult(BaseModel):
    rankings: list[RankingEntry]
    top_3_summary: str
```

Update `ScoredListing` — remove `llm_reasoning`, add new fields:

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

    # Structured scoring
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

- [ ] **Step 4: Update existing test_scored_listing_composition**

The existing test uses `llm_reasoning=` which no longer exists. Update it:

```python
def test_scored_listing_composition():
    from src.models import ListingSummary, ListingDetail, ScoredListing, CriteriaScore
    summary = ListingSummary(
        property_id="abc123", title="Test", rent=30000, deposit=100000,
        maintenance=None, sqft=1000, address="Test addr",
        locality="bellandur", building_name=None,
        detail_url="https://example.com", available_date=None, image_urls=[]
    )
    detail = ListingDetail(
        property_id="abc123", furnishing="Fully", floor="2/5",
        power_backup="Full", description="Great flat"
    )
    scored = ScoredListing(
        summary=summary, detail=detail,
        lat=12.94, lon=77.69, walk_minutes=8.5, orr_distance_m=350,
        peace_score=75.0, llm_score=82.0,
        final_score=79.2, disqualified=False, disqualify_reason=None,
        criteria_scores={
            "power_backup": CriteriaScore(score=18, max=20, confidence="high", evidence="Full generator"),
        },
        pros=["Good backup"], cons=["No fiber"], elevator_pitch="Nice flat",
        data_completeness=0.8,
    )
    assert scored.summary.rent == 30000
    assert scored.detail.power_backup == "Full"
    assert scored.disqualified is False
    d = scored.model_dump()
    assert d["summary"]["property_id"] == "abc123"
    assert d["detail"]["furnishing"] == "Fully"
```

- [ ] **Step 5: Run all model tests**

Run: `.venv/bin/python -m pytest tests/test_models.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/models.py tests/test_models.py
git commit -m "feat: add structured scoring models (CriteriaScore, PeaceBreakdown, ComparativeResult)"
```

---

### Task 2: Peace Score Breakdown in spatial.py

**Files:**
- Modify: `src/spatial.py`
- Modify: `tests/test_spatial.py`

**Interfaces:**
- Consumes: `PeaceBreakdown` from `src/models.py` (Task 1)
- Produces: `compute_peace_score(orr_distance_m, locality) -> tuple[float, PeaceBreakdown]` (changed return type)

- [ ] **Step 1: Write failing tests for peace breakdown**

```python
# tests/test_spatial.py — add these tests

def test_peace_score_returns_breakdown():
    from src.spatial import compute_peace_score
    score, breakdown = compute_peace_score(450, "kadubeesanahalli")
    assert breakdown.orr_distance_m == 450
    assert breakdown.locality_bonus == 20  # priority locality
    assert breakdown.final == score
    assert breakdown.base_score > 0


def test_peace_breakdown_no_bonus():
    from src.spatial import compute_peace_score
    score, breakdown = compute_peace_score(500, "bellandur")
    assert breakdown.locality_bonus == 0
    assert breakdown.final == score


def test_peace_breakdown_close_to_orr():
    from src.spatial import compute_peace_score
    score, breakdown = compute_peace_score(150, "bellandur")
    assert score == 0
    assert breakdown.final == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_spatial.py::test_peace_score_returns_breakdown -v`
Expected: FAIL — returns float, not tuple

- [ ] **Step 3: Update compute_peace_score to return breakdown**

```python
from .models import PeaceBreakdown

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
```

- [ ] **Step 4: Update existing peace score tests**

All existing tests call `compute_peace_score(...)` and compare result to a number. They now get a tuple. Update each to unpack:

```python
def test_peace_score_close_to_orr():
    from src.spatial import compute_peace_score
    score, _ = compute_peace_score(150, "bellandur")
    assert score == 0

def test_peace_score_far_from_orr():
    from src.spatial import compute_peace_score
    score, _ = compute_peace_score(500, "kadubeesanahalli")
    assert score >= 70

def test_peace_score_mid_range():
    from src.spatial import compute_peace_score
    score, _ = compute_peace_score(300, "panathur")
    assert 20 < score < 70
```

- [ ] **Step 5: Update caller in run_filter (spatial.py)**

In `run_filter`, the call `peace = compute_peace_score(orr_dist, summary["locality"])` must unpack:

```python
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
```

- [ ] **Step 6: Run all spatial tests**

Run: `.venv/bin/python -m pytest tests/test_spatial.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add src/spatial.py tests/test_spatial.py
git commit -m "feat: peace score returns structured breakdown"
```

---

### Task 3: Detail Scraper Resilience — Retry + Data Completeness

**Files:**
- Modify: `src/detail_scraper.py`
- Create: `tests/test_detail_scraper.py`

**Interfaces:**
- Consumes: `ListingDetail` from `src/models.py`
- Produces: `compute_data_completeness(detail: dict) -> float`, updated `scrape_details_playwright()` that adds `data_completeness` to each entry and retries on missing critical fields

- [ ] **Step 1: Write tests for data_completeness**

```python
# tests/test_detail_scraper.py

def test_data_completeness_full():
    from src.detail_scraper import compute_data_completeness
    detail = {
        "property_id": "abc", "furnishing": "Semi", "floor": "3/5",
        "power_backup": "Full", "water_supply": "Corporation",
        "gated_security": True, "facing": "East", "bathrooms": 2,
        "balconies": 1, "parking": "Car", "building_age": "1-3 Years",
        "preferred_tenant": "Family", "description": "Nice flat"
    }
    score = compute_data_completeness(detail)
    assert score == 1.0


def test_data_completeness_partial():
    from src.detail_scraper import compute_data_completeness
    detail = {
        "property_id": "abc", "furnishing": "Semi", "floor": "3/5",
        "power_backup": None, "water_supply": None,
        "gated_security": None, "facing": None, "bathrooms": None,
        "balconies": None, "parking": None, "building_age": None,
        "preferred_tenant": None, "description": "Nice flat"
    }
    score = compute_data_completeness(detail)
    assert 0.2 < score < 0.5


def test_data_completeness_empty():
    from src.detail_scraper import compute_data_completeness
    detail = {
        "property_id": "abc", "furnishing": "", "floor": "",
        "power_backup": None, "water_supply": None,
        "gated_security": None, "facing": None, "bathrooms": None,
        "balconies": None, "parking": None, "building_age": None,
        "preferred_tenant": None, "description": ""
    }
    score = compute_data_completeness(detail)
    assert score == 0.0


def test_needs_retry_missing_critical():
    from src.detail_scraper import needs_retry
    detail = {"power_backup": None, "water_supply": "Corp", "furnishing": "Semi"}
    assert needs_retry(detail) is True


def test_needs_retry_all_present():
    from src.detail_scraper import needs_retry
    detail = {"power_backup": "Full", "water_supply": "Corp", "furnishing": "Semi"}
    assert needs_retry(detail) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_detail_scraper.py -v`
Expected: FAIL — functions not defined

- [ ] **Step 3: Implement compute_data_completeness and needs_retry**

Add to `src/detail_scraper.py`:

```python
COMPLETENESS_FIELDS = [
    "furnishing", "floor", "power_backup", "facing", "bathrooms",
    "balconies", "parking", "building_age", "preferred_tenant",
    "water_supply", "gated_security", "description",
]

CRITICAL_FIELDS = ["power_backup", "water_supply", "furnishing"]


def compute_data_completeness(detail: dict) -> float:
    filled = sum(1 for f in COMPLETENESS_FIELDS if detail.get(f) not in (None, "", 0))
    return round(filled / len(COMPLETENESS_FIELDS), 2)


def needs_retry(detail: dict) -> bool:
    return any(detail.get(f) in (None, "") for f in CRITICAL_FIELDS)
```

- [ ] **Step 4: Add retry logic to _scrape_one**

In `_scrape_one`, after parsing detail, check `needs_retry`. If true and this is the first attempt, reload the page and re-parse:

```python
async def _scrape_one(context, url: str, property_id: str, idx: int, total: int, sem: asyncio.Semaphore, scrape_images: bool = False) -> tuple[str, ListingDetail | None, list[str]]:
    async with sem:
        _log(f"  [{idx+1}/{total}] {property_id}...")
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            text = await page.inner_text("body")
            detail = _parse_detail_from_text(text, property_id)

            if needs_retry(detail.model_dump()):
                _log(f"  ↻ {property_id}: missing critical fields, retrying...")
                await page.reload(wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(4000)
                text = await page.inner_text("body")
                detail = _parse_detail_from_text(text, property_id)

            images = await _scrape_images(page) if scrape_images else []
            _log(f"  ✓ {property_id}: furnishing={detail.furnishing}, power={detail.power_backup}, floor={detail.floor}, images={len(images)}")
            return property_id, detail, images
        except Exception as e:
            _log(f"  ✗ {property_id}: {e}")
            return property_id, None, []
        finally:
            await page.close()
```

- [ ] **Step 5: Add data_completeness to scrape_details_playwright output**

In `scrape_details_playwright`, after setting `entry["detail"]`, also set `entry["data_completeness"]`:

```python
if pid in results:
    detail, images = results[pid]
    detail_dict = detail.model_dump()
    entry["detail"] = detail_dict
    entry["data_completeness"] = compute_data_completeness(detail_dict)
    if images:
        entry["summary"]["image_urls"] = images
else:
    entry["data_completeness"] = compute_data_completeness(entry.get("detail") or {})
```

- [ ] **Step 6: Run tests**

Run: `.venv/bin/python -m pytest tests/test_detail_scraper.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add src/detail_scraper.py tests/test_detail_scraper.py
git commit -m "feat: detail scraper retry on missing critical fields + data completeness"
```

---

### Task 4: Structured Scorer — Pass 1 (Per-Listing Evaluation)

**Files:**
- Modify: `src/scorer.py`
- Modify: `tests/test_scorer.py`

**Interfaces:**
- Consumes: `CriteriaScore`, `ScoredListing`, `PeaceBreakdown` from `src/models.py` (Task 1); `peace_breakdown` in filtered.json (Task 2); `data_completeness` in filtered.json (Task 3)
- Produces: `build_structured_judge_prompt(summary, detail, walk_minutes, orr_distance_m, data_completeness, llm_weights) -> str`, `parse_structured_score(text: str, llm_weights: dict) -> dict` (validates with Pydantic, returns dict), updated `run_score()` that writes new ScoredListing shape

- [ ] **Step 1: Write failing tests for new prompt builder**

```python
# tests/test_scorer.py — replace existing tests

def test_build_structured_judge_prompt():
    from src.scorer import build_structured_judge_prompt
    weights = {
        "power_backup": 20, "noise": 20, "internet": 15,
        "light_ventilation": 10, "water": 10, "maintenance": 10,
        "wfh_livability": 10, "value": 5
    }
    prompt = build_structured_judge_prompt(
        summary={"title": "2BHK Test", "rent": 30000, "address": "Test Rd", "sqft": 1000},
        detail={"furnishing": "Semi", "power_backup": "Full", "floor": "3/4",
                "water_supply": "Borewell", "gated_security": True, "description": "Nice flat"},
        walk_minutes=8.5,
        orr_distance_m=350,
        data_completeness=0.85,
        llm_weights=weights,
    )
    assert "criteria_scores" in prompt
    assert "pros" in prompt
    assert "cons" in prompt
    assert "elevator_pitch" in prompt
    assert "confidence" in prompt
    assert "evidence" in prompt
    assert "HARD REQUIREMENT" in prompt
    assert "data_completeness" in prompt.lower() or "0.85" in prompt


def test_structured_prompt_includes_all_criteria():
    from src.scorer import build_structured_judge_prompt
    weights = {
        "power_backup": 20, "noise": 20, "internet": 15,
        "light_ventilation": 10, "water": 10, "maintenance": 10,
        "wfh_livability": 10, "value": 5
    }
    prompt = build_structured_judge_prompt(
        summary={"title": "Test", "rent": 40000, "address": "Addr", "sqft": 1200},
        detail={"furnishing": "Fully", "power_backup": None, "floor": "2/5",
                "water_supply": "Corporation", "gated_security": False, "description": "Flat"},
        walk_minutes=10, orr_distance_m=500, data_completeness=0.6, llm_weights=weights,
    )
    for criterion in weights:
        assert criterion in prompt


def test_parse_structured_score_valid():
    from src.scorer import parse_structured_score
    weights = {"power_backup": 20, "noise": 20, "internet": 15,
               "light_ventilation": 10, "water": 10, "maintenance": 10,
               "wfh_livability": 10, "value": 5}
    raw = '''{
        "criteria_scores": {
            "power_backup": {"score": 18, "max": 20, "confidence": "high", "evidence": "Full gen"},
            "noise": {"score": 14, "max": 20, "confidence": "medium", "evidence": "3rd floor"},
            "internet": {"score": 10, "max": 15, "confidence": "low", "evidence": "No mention"},
            "light_ventilation": {"score": 8, "max": 10, "confidence": "medium", "evidence": "East"},
            "water": {"score": 7, "max": 10, "confidence": "high", "evidence": "Corp+bore"},
            "maintenance": {"score": 8, "max": 10, "confidence": "high", "evidence": "Gated"},
            "wfh_livability": {"score": 7, "max": 10, "confidence": "medium", "evidence": "Semi"},
            "value": {"score": 4, "max": 5, "confidence": "high", "evidence": "28/sqft"}
        },
        "pros": ["Full generator", "Gated community"],
        "cons": ["No fiber mentioned"],
        "elevator_pitch": "Quiet gated flat with generator",
        "disqualified": false,
        "disqualify_reason": null
    }'''
    result = parse_structured_score(raw, weights)
    assert result["criteria_scores"]["power_backup"]["score"] == 18
    assert len(result["pros"]) == 2
    assert result["disqualified"] is False


def test_parse_structured_score_with_markdown_fences():
    from src.scorer import parse_structured_score
    weights = {"power_backup": 20, "noise": 20, "internet": 15,
               "light_ventilation": 10, "water": 10, "maintenance": 10,
               "wfh_livability": 10, "value": 5}
    raw = '```json\n{"criteria_scores": {"power_backup": {"score": 18, "max": 20, "confidence": "high", "evidence": "Gen"}, "noise": {"score": 14, "max": 20, "confidence": "medium", "evidence": "OK"}, "internet": {"score": 10, "max": 15, "confidence": "low", "evidence": "?"}, "light_ventilation": {"score": 8, "max": 10, "confidence": "medium", "evidence": "OK"}, "water": {"score": 7, "max": 10, "confidence": "high", "evidence": "OK"}, "maintenance": {"score": 8, "max": 10, "confidence": "high", "evidence": "OK"}, "wfh_livability": {"score": 7, "max": 10, "confidence": "medium", "evidence": "OK"}, "value": {"score": 4, "max": 5, "confidence": "high", "evidence": "OK"}}, "pros": ["A"], "cons": ["B"], "elevator_pitch": "OK flat", "disqualified": false, "disqualify_reason": null}\n```'
    result = parse_structured_score(raw, weights)
    assert result["criteria_scores"]["power_backup"]["score"] == 18


def test_parse_structured_score_invalid():
    from src.scorer import parse_structured_score
    import pytest
    weights = {"power_backup": 20}
    with pytest.raises(ValueError):
        parse_structured_score("not json at all", weights)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_scorer.py -v`
Expected: FAIL — functions not defined

- [ ] **Step 3: Implement new structured judge prompt and parser**

Replace `JUDGE_TEMPLATE` and `build_judge_prompt` in `src/scorer.py`:

```python
import json
import re
from pathlib import Path

from pydantic import ValidationError

from .config import RunContext
from .db import Dedup
from .models import CriteriaScore, ScoredListing

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
Data Completeness: {data_completeness:.0%} of fields populated
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
```

- [ ] **Step 4: Update run_score to use new prompt and produce new ScoredListing**

Replace the `score_listing` and `run_score` functions:

```python
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
        # Retry once with error feedback
        retry_prompt = f"{prompt}\n\nYour previous response had an error: {e}\nPlease fix and respond with valid JSON only."
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": retry_prompt}],
        )
        text = response.content[0].text.strip()
        return parse_structured_score(text, llm_weights)


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
    return out_path
```

- [ ] **Step 5: Remove old build_judge_prompt and JUDGE_TEMPLATE**

Delete the old `JUDGE_TEMPLATE` string and `build_judge_prompt` function from `src/scorer.py`. They are fully replaced by `STRUCTURED_JUDGE_TEMPLATE` and `build_structured_judge_prompt`.

- [ ] **Step 6: Run scorer tests**

Run: `.venv/bin/python -m pytest tests/test_scorer.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add src/scorer.py tests/test_scorer.py
git commit -m "feat: structured per-criteria scoring with confidence and evidence"
```

---

### Task 5: Scorer — Pass 2 (Comparative Ranking)

**Files:**
- Modify: `src/scorer.py`
- Modify: `tests/test_scorer.py`

**Interfaces:**
- Consumes: scored listings from Pass 1 (list of dicts with `criteria_scores`, `summary`, etc.)
- Produces: `build_comparative_prompt(scored_listings: list[dict]) -> str`, `parse_comparative_result(text: str) -> ComparativeResult`, `run_comparative_ranking(scored: list[dict]) -> ComparativeResult`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_scorer.py — add these

def test_build_comparative_prompt():
    from src.scorer import build_comparative_prompt
    listings = [
        {"summary": {"property_id": "a1", "title": "Flat A", "rent": 30000, "sqft": 1000},
         "llm_score": 82, "peace_score": 70, "final_score": 75,
         "criteria_scores": {"power_backup": {"score": 18, "max": 20, "confidence": "high", "evidence": "Gen"}},
         "pros": ["Good backup"], "cons": ["No fiber"], "disqualified": False},
        {"summary": {"property_id": "b2", "title": "Flat B", "rent": 25000, "sqft": 900},
         "llm_score": 75, "peace_score": 80, "final_score": 78,
         "criteria_scores": {"power_backup": {"score": 15, "max": 20, "confidence": "medium", "evidence": "Partial"}},
         "pros": ["Quiet area"], "cons": ["Smaller"], "disqualified": False},
    ]
    prompt = build_comparative_prompt(listings)
    assert "a1" in prompt
    assert "b2" in prompt
    assert "rank" in prompt.lower()
    assert "top_3_summary" in prompt


def test_parse_comparative_result_valid():
    from src.scorer import parse_comparative_result
    raw = '{"rankings": [{"property_id": "a1", "rank": 1, "reasoning": "Best overall"}, {"property_id": "b2", "rank": 2, "reasoning": "Quieter"}], "top_3_summary": "#1 Flat A — best. #2 Flat B — quieter."}'
    result = parse_comparative_result(raw)
    assert len(result.rankings) == 2
    assert result.rankings[0].rank == 1
    assert result.top_3_summary.startswith("#1")


def test_parse_comparative_result_invalid():
    from src.scorer import parse_comparative_result
    import pytest
    with pytest.raises(ValueError):
        parse_comparative_result("not json")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_scorer.py::test_build_comparative_prompt -v`
Expected: FAIL

- [ ] **Step 3: Implement comparative ranking**

Add to `src/scorer.py`:

```python
from .models import ComparativeResult, RankingEntry

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
```

- [ ] **Step 4: Integrate Pass 2 into run_score**

At the end of `run_score`, after writing `scored.json`, add:

```python
    # Pass 2: Comparative ranking
    comparative = run_comparative_ranking(scored)
    if comparative:
        for ranking in comparative.rankings:
            for entry in scored:
                if entry["summary"]["property_id"] == ranking.property_id:
                    entry["comparative_rank"] = ranking.rank
                    entry["comparative_notes"] = ranking.reasoning
                    break
        # Re-write with comparative data
        out_path.write_text(json.dumps(scored, indent=2))
        print(f"Comparative ranking: {comparative.top_3_summary[:100]}...")

        # Save comparative result separately for report banner
        comp_path = ctx.path("comparative.json")
        comp_path.write_text(json.dumps(comparative.model_dump(), indent=2))
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest tests/test_scorer.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/scorer.py tests/test_scorer.py
git commit -m "feat: Pass 2 comparative ranking across qualified listings"
```

---

### Task 6: Smart Dedup

**Files:**
- Modify: `src/scorer.py`
- Modify: `tests/test_scorer.py`

**Interfaces:**
- Consumes: scored listings with `summary.building_name`
- Produces: `normalize_building_name(name: str) -> str`, `find_dupe_groups(scored: list[dict]) -> list[list[int]]`, entries with `duplicate_of` field set

- [ ] **Step 1: Write failing tests**

```python
# tests/test_scorer.py — add these

def test_normalize_building_name():
    from src.scorer import normalize_building_name
    assert normalize_building_name("SLS Signature") == "sls signature"
    assert normalize_building_name("  SLS  Signature  ") == "sls signature"
    assert normalize_building_name("SLS-Signature (Phase 2)") == "sls signature phase 2"


def test_find_dupe_groups():
    from src.scorer import find_dupe_groups
    scored = [
        {"summary": {"property_id": "a1", "building_name": "SLS Signature"}, "final_score": 80},
        {"summary": {"property_id": "a2", "building_name": "SLS Signature"}, "final_score": 75},
        {"summary": {"property_id": "b1", "building_name": "Brigade Lakefront"}, "final_score": 70},
    ]
    groups = find_dupe_groups(scored)
    assert len(groups) == 1
    assert set(groups[0]) == {0, 1}


def test_find_dupe_groups_contains_match():
    from src.scorer import find_dupe_groups
    scored = [
        {"summary": {"property_id": "a1", "building_name": "SLS Signature Tower A"}, "final_score": 80},
        {"summary": {"property_id": "a2", "building_name": "SLS Signature"}, "final_score": 75},
    ]
    groups = find_dupe_groups(scored)
    assert len(groups) == 1


def test_find_dupe_groups_no_building_name():
    from src.scorer import find_dupe_groups
    scored = [
        {"summary": {"property_id": "a1", "building_name": None}, "final_score": 80},
        {"summary": {"property_id": "a2", "building_name": None}, "final_score": 75},
    ]
    groups = find_dupe_groups(scored)
    assert len(groups) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_scorer.py::test_normalize_building_name -v`
Expected: FAIL

- [ ] **Step 3: Implement dedup functions**

Add to `src/scorer.py`:

```python
def normalize_building_name(name: str) -> str:
    name = re.sub(r"[^\w\s]", " ", name.lower())
    return " ".join(name.split())


def find_dupe_groups(scored: list[dict]) -> list[list[int]]:
    named = []
    for i, entry in enumerate(scored):
        bname = entry.get("summary", {}).get("building_name")
        if bname:
            named.append((i, normalize_building_name(bname)))

    groups = []
    used = set()
    for i, (idx_a, name_a) in enumerate(named):
        if idx_a in used:
            continue
        group = [idx_a]
        for j in range(i + 1, len(named)):
            idx_b, name_b = named[j]
            if idx_b in used:
                continue
            if name_a == name_b or name_a in name_b or name_b in name_a:
                group.append(idx_b)
                used.add(idx_b)
        if len(group) > 1:
            groups.append(group)
            used.add(idx_a)
    return groups


def mark_duplicates(scored: list[dict]) -> list[dict]:
    groups = find_dupe_groups(scored)
    for group in groups:
        best_idx = max(group, key=lambda i: scored[i].get("final_score", 0))
        best_pid = scored[best_idx]["summary"]["property_id"]
        for idx in group:
            if idx != best_idx:
                scored[idx]["duplicate_of"] = best_pid
    return scored
```

- [ ] **Step 4: Integrate into run_score**

After comparative ranking block, before final write, add:

```python
    scored = mark_duplicates(scored)
    out_path.write_text(json.dumps(scored, indent=2))
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest tests/test_scorer.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/scorer.py tests/test_scorer.py
git commit -m "feat: smart dedup by normalized building name"
```

---

### Task 7: Reporter — Updated Markdown + Template Data

**Files:**
- Modify: `src/reporter.py`
- Modify: `tests/test_reporter.py`

**Interfaces:**
- Consumes: new `ScoredListing` shape from `scored.json`, `comparative.json`
- Produces: updated `generate_report()` that passes structured data to template and writes updated markdown

- [ ] **Step 1: Update test fixture to new ScoredListing shape**

Replace `SCORED_FIXTURE` in `tests/test_reporter.py`:

```python
SCORED_FIXTURE = [
    {
        "summary": {"property_id": "a1", "title": "Great Flat", "rent": 35000, "deposit": 100000,
            "maintenance": 3000, "sqft": 1100, "address": "Test Rd", "locality": "kadubeesanahalli",
            "building_name": "SLS", "detail_url": "https://nobroker.in/a1", "available_date": None, "image_urls": []},
        "detail": {"property_id": "a1", "furnishing": "Semi", "floor": "3/5", "power_backup": "Full",
            "facing": "West", "bathrooms": 2, "balconies": 1, "parking": "Car", "building_age": "1-3 Years",
            "preferred_tenant": "Family", "water_supply": "Corporation", "gated_security": True,
            "description": "Nice flat"},
        "lat": 12.94, "lon": 77.69, "walk_minutes": 8.0, "orr_distance_m": 400,
        "peace_score": 70.0, "llm_score": 88.0,
        "final_score": 80.8, "disqualified": False, "disqualify_reason": None,
        "criteria_scores": {
            "power_backup": {"score": 18, "max": 20, "confidence": "high", "evidence": "Full generator"},
            "noise": {"score": 16, "max": 20, "confidence": "medium", "evidence": "3rd floor"},
            "internet": {"score": 12, "max": 15, "confidence": "low", "evidence": "No mention"},
            "light_ventilation": {"score": 8, "max": 10, "confidence": "medium", "evidence": "West facing"},
            "water": {"score": 9, "max": 10, "confidence": "high", "evidence": "Corporation supply"},
            "maintenance": {"score": 9, "max": 10, "confidence": "high", "evidence": "Gated"},
            "wfh_livability": {"score": 8, "max": 10, "confidence": "medium", "evidence": "Semi furnished"},
            "value": {"score": 4, "max": 5, "confidence": "high", "evidence": "Reasonable"},
        },
        "pros": ["Full generator backup", "Gated community", "Good water supply"],
        "cons": ["No fiber internet mentioned", "Semi-furnished only"],
        "elevator_pitch": "Quiet gated apartment with full generator, 8min walk to PTP",
        "data_completeness": 0.85,
        "peace_breakdown": {"orr_distance_m": 400, "base_score": 60, "locality_bonus": 20, "final": 70},
        "comparative_rank": 1, "comparative_notes": "Best overall",
        "duplicate_of": None,
    },
    {
        "summary": {"property_id": "b2", "title": "OK Flat", "rent": 25000, "deposit": 75000,
            "maintenance": None, "sqft": 900, "address": "Other Rd", "locality": "bellandur",
            "building_name": None, "detail_url": "https://nobroker.in/b2", "available_date": None, "image_urls": []},
        "detail": {"property_id": "b2", "furnishing": "Unfurnished", "floor": "1/3", "power_backup": None,
            "facing": None, "bathrooms": 1, "balconies": 0, "parking": None, "building_age": None,
            "preferred_tenant": None, "water_supply": "Borewell", "gated_security": False,
            "description": "Basic flat"},
        "lat": 12.93, "lon": 77.68, "walk_minutes": 11.0, "orr_distance_m": 250,
        "peace_score": 35.0, "llm_score": 40.0,
        "final_score": 38.0, "disqualified": True, "disqualify_reason": "No power backup",
        "criteria_scores": {
            "power_backup": {"score": 0, "max": 20, "confidence": "high", "evidence": "Not mentioned"},
            "noise": {"score": 6, "max": 20, "confidence": "low", "evidence": "Ground floor"},
            "internet": {"score": 5, "max": 15, "confidence": "low", "evidence": "No info"},
            "light_ventilation": {"score": 4, "max": 10, "confidence": "low", "evidence": "No info"},
            "water": {"score": 5, "max": 10, "confidence": "medium", "evidence": "Borewell only"},
            "maintenance": {"score": 3, "max": 10, "confidence": "medium", "evidence": "Not gated"},
            "wfh_livability": {"score": 4, "max": 10, "confidence": "low", "evidence": "Unfurnished"},
            "value": {"score": 3, "max": 5, "confidence": "medium", "evidence": "Cheap but basic"},
        },
        "pros": ["Low rent"],
        "cons": ["No power backup", "Not gated", "Unfurnished", "Borewell only"],
        "elevator_pitch": "Budget flat, but no power backup — disqualified",
        "data_completeness": 0.35,
        "peace_breakdown": {"orr_distance_m": 250, "base_score": 37.5, "locality_bonus": 0, "final": 35},
        "comparative_rank": None, "comparative_notes": None,
        "duplicate_of": None,
    },
]
```

- [ ] **Step 2: Update test assertions**

```python
def test_generate_report(tmp_path):
    from src.reporter import generate_report
    from src.config import Config, RunContext
    import json

    cfg = Config(
        name="default", target_localities=["kadubeesanahalli"], ptp_coords=(12.942, 77.6905),
        max_walk_minutes=12, min_orr_distance_m=200, max_rent=50000, score_threshold=85,
        bhk=2, score_weights={"peace": 0.4, "llm": 0.6},
        llm_weights={"power_backup": 20, "noise": 20, "internet": 15, "light_ventilation": 10,
            "water": 10, "maintenance": 10, "wfh_livability": 10, "value": 5}
    )
    run_dir = tmp_path / "test_run"
    run_dir.mkdir()
    (run_dir / "scored.json").write_text(json.dumps(SCORED_FIXTURE))
    (run_dir / "config.json").write_text(cfg.model_dump_json())
    ctx = RunContext(run_id="test", run_dir=run_dir, config=cfg)

    html_path = generate_report(ctx)
    assert html_path.exists()
    html = html_path.read_text()
    assert "Great Flat" in html
    assert "80.8" in html
    assert "elevator_pitch" in html or "elevator-pitch" in html or "Quiet gated apartment" in html
    assert "criteria" in html.lower() or "power_backup" in html
    md = (run_dir / "report.md").read_text()
    assert "Great Flat" in md
    assert "Full generator" in md  # pros
    assert "No fiber" in md  # cons
```

- [ ] **Step 3: Update generate_report in src/reporter.py**

Update markdown generation to include pros/cons/elevator_pitch/criteria:

```python
def generate_report(ctx: RunContext) -> Path:
    config = ctx.config
    scored_path = ctx.path("scored.json")
    entries = json.loads(scored_path.read_text())

    # Load comparative result if exists
    comp_path = ctx.path("comparative.json")
    comparative = json.loads(comp_path.read_text()) if comp_path.exists() else None

    qualified = [e for e in entries if not e["disqualified"]]
    disqualified = [e for e in entries if e["disqualified"]]
    qualified.sort(key=lambda x: x.get("comparative_rank") or 999)
    disqualified.sort(key=lambda x: x["final_score"], reverse=True)
    sorted_entries = qualified + disqualified

    # Compute run averages for comparative context
    if qualified:
        all_criteria = {}
        for e in qualified:
            for k, v in e.get("criteria_scores", {}).items():
                all_criteria.setdefault(k, []).append(v["score"])
        criteria_averages = {k: round(sum(v) / len(v), 1) for k, v in all_criteria.items()}
    else:
        criteria_averages = {}

    threshold = config.score_threshold
    above = sum(1 for e in qualified if e["final_score"] >= threshold)

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=False)
    template = env.get_template(TEMPLATE_FILE)
    html = template.render(
        run_id=ctx.run_id,
        config_name=config.name,
        total=len(entries),
        qualified=len(qualified),
        disqualified_count=len(disqualified),
        above_threshold=above,
        threshold=threshold,
        entries=sorted_entries,
        entries_json=json.dumps(sorted_entries),
        criteria_averages_json=json.dumps(criteria_averages),
        comparative_json=json.dumps(comparative) if comparative else "null",
    )

    html_path = ctx.path("report.html")
    html_path.write_text(html)

    reports_dir = REPO_ROOT / "reports" / ctx.run_id
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "index.html").write_text(html)

    _regenerate_index(env)

    # Markdown report with structured data
    md_lines = [
        f"# House Hunt Report — {ctx.run_id}",
        f"\n**Config:** {config.name} | **Scored:** {len(entries)} | **Qualified:** {len(qualified)} | **Above {threshold}:** {above}\n",
    ]
    if comparative:
        md_lines.append(f"## Top Picks\n{comparative['top_3_summary']}\n")
    md_lines.append("---\n")

    for rank, e in enumerate(sorted_entries, 1):
        s = e["summary"]
        d = e.get("detail") or {}
        tag = "DISQUALIFIED" if e["disqualified"] else ("ACT NOW" if e["final_score"] >= threshold else "")
        md_lines.append(f"## #{rank} {s['title']} {tag}")
        md_lines.append(f"**Score: {e['final_score']}** (LLM: {e['llm_score']} | Peace: {e['peace_score']})")

        if e.get("elevator_pitch"):
            md_lines.append(f"*{e['elevator_pitch']}*")

        if e["disqualified"]:
            md_lines.append(f"**Disqualified:** {e['disqualify_reason']}")
        md_lines.append(f"Rent: ₹{s['rent']:,} | Deposit: ₹{s['deposit']:,} | {s['sqft']}sqft | {e['walk_minutes']}min | {d.get('furnishing','?')} | Power: {d.get('power_backup','?')}")

        if e.get("pros"):
            md_lines.append("**Pros:** " + " · ".join(f"✓ {p}" for p in e["pros"]))
        if e.get("cons"):
            md_lines.append("**Cons:** " + " · ".join(f"✗ {c}" for c in e["cons"]))

        if e.get("criteria_scores"):
            scores_str = " | ".join(f"{k}: {v['score']}/{v['max']}" for k, v in e["criteria_scores"].items())
            md_lines.append(f"Criteria: {scores_str}")

        if e.get("peace_breakdown"):
            pb = e["peace_breakdown"]
            md_lines.append(f"Peace: ORR {pb['orr_distance_m']:.0f}m → base {pb['base_score']}, bonus +{pb['locality_bonus']} → {pb['final']}")

        md_lines.append(f"Link: {s['detail_url']}\n---\n")

    md_path = ctx.path("report.md")
    md_path.write_text("\n".join(md_lines))

    print(f"Reports: {html_path} + {md_path}", flush=True)
    print(f"  {len(qualified)} qualified, {above} above {threshold}, {len(disqualified)} disqualified", flush=True)
    return html_path
```

- [ ] **Step 4: Run reporter tests**

Run: `.venv/bin/python -m pytest tests/test_reporter.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/reporter.py tests/test_reporter.py
git commit -m "feat: reporter passes structured scoring data to template and markdown"
```

---

### Task 8: HTML Report Template — Full Rewrite

**Files:**
- Rewrite: `src/report_template.html`

**Interfaces:**
- Consumes: `entries_json` (new ScoredListing shape), `criteria_averages_json`, `comparative_json`, `threshold`
- Produces: interactive HTML report with criteria bars, pros/cons, elevator pitch, comparative banner, new sort/filter options

This is the largest task. The template is self-contained HTML/CSS/JS — no external dependencies.

- [ ] **Step 1: Rewrite report_template.html**

The full template is large. Key sections to implement:

**Top banner (comparative):**
```html
<div class="comparative-banner" id="comp-banner"></div>
```

**Per-card additions (inside makeCard JS):**
1. Elevator pitch line below title
2. Criteria bar chart (horizontal bars with color + confidence dots + average marker)
3. Pros/cons bullets (green ✓ / red ✗)
4. Peace breakdown text
5. Data completeness indicator
6. Duplicate indicator

**New controls:**
- Sort by individual criteria: add options to sort dropdown for each criterion
- Filter by confidence: add "Min confidence" dropdown (any/medium/high)
- Hide duplicates toggle

**CSS additions:**
- `.elevator-pitch` — bold italic 1-liner
- `.criteria-chart` — horizontal bars container
- `.criteria-bar` — individual bar with fill, average marker, confidence dots
- `.bar-fill.green` / `.yellow` / `.red` — color coding
- `.confidence` — dots display
- `.pros-cons` — two-column layout
- `.pro` / `.con` — green/red bullets
- `.peace-detail` — small text showing formula
- `.data-completeness` — indicator badge
- `.dupe-badge` — "Duplicate of #X" badge
- `.comp-banner` — top recommendation banner

**JS additions:**
- `renderComparativeBanner()` — reads `COMPARATIVE` global, renders top-3
- `renderCriteriaChart(criteria_scores, averages)` — generates bar HTML
- Sort functions for each criterion
- Confidence filter logic
- Duplicate hide/show toggle

Here is the complete template:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>House Hunt Report — {{ run_id }}</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; color: #333; overflow-x: hidden; }

  .top-bar { background: #1a1a2e; color: #fff; padding: 16px 20px; }
  .top-bar h1 { font-size: 18px; margin-bottom: 4px; }
  .top-bar .meta { font-size: 12px; color: #aaa; }
  .top-bar .meta span { color: #4ecdc4; font-weight: 600; }

  .comp-banner { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: #fff; padding: 16px 20px; display: none; }
  .comp-banner.visible { display: block; }
  .comp-banner h2 { font-size: 15px; margin-bottom: 8px; color: #4ecdc4; }
  .comp-banner .pick { font-size: 13px; line-height: 1.6; color: #ddd; }
  .comp-banner .pick strong { color: #fff; }

  .controls { background: #fff; padding: 12px 20px; border-bottom: 1px solid #e0e0e0; position: sticky; top: 0; z-index: 99; display: flex; flex-wrap: wrap; gap: 10px; align-items: end; }
  .control-group { display: flex; flex-direction: column; gap: 2px; }
  .control-group label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: #888; font-weight: 600; }
  .control-group select, .control-group input { padding: 6px 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 13px; background: #fff; }
  .control-group input[type=range] { width: 140px; }
  .range-val { font-size: 12px; color: #555; font-weight: 500; min-width: 50px; }
  .toggle { display: flex; gap: 6px; align-items: center; }
  .toggle input[type=checkbox] { width: 16px; height: 16px; }
  .toggle label { font-size: 13px; cursor: pointer; }
  .result-count { font-size: 13px; color: #888; margin-left: auto; padding: 6px 0; }

  .container { max-width: 100%; padding: 16px 20px; }

  .cards { display: grid; grid-template-columns: minmax(0, 1fr); gap: 12px; }
  .card { background: #fff; border-radius: 10px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); border-left: 4px solid #ddd; transition: opacity 0.2s; min-width: 0; }
  .card.qualified { border-left-color: #4ecdc4; }
  .card.act-now { border-left-color: #ff6b6b; }
  .card.disqualified { border-left-color: #ccc; opacity: 0.5; }
  .card.hidden { display: none; }

  .card-top { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 4px; min-width: 0; }
  .card-top h2 { font-size: 15px; flex: 1; line-height: 1.3; min-width: 0; }
  .card-top h2 a { color: #1a1a2e; text-decoration: none; overflow-wrap: break-word; }
  .card-top h2 a:hover { color: #4ecdc4; }
  .rank { color: #aaa; font-size: 13px; margin-right: 6px; }
  .score { background: #1a1a2e; color: #fff; padding: 3px 10px; border-radius: 16px; font-size: 13px; font-weight: 600; white-space: nowrap; margin-left: 10px; flex-shrink: 0; }
  .score.high { background: #ff6b6b; }
  .score.disq { background: #999; }
  .tag { display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 10px; font-weight: 700; text-transform: uppercase; margin-left: 6px; vertical-align: middle; }
  .tag.act { background: #ffe0e0; color: #d32f2f; }
  .tag.disq { background: #eee; color: #888; }
  .tag.dupe { background: #fff3e0; color: #e65100; }

  .elevator-pitch { font-size: 13px; font-style: italic; color: #555; margin-bottom: 10px; font-weight: 500; }

  .badges { display: flex; gap: 6px; margin-bottom: 8px; flex-wrap: wrap; }
  .badge { font-size: 10px; padding: 2px 8px; border-radius: 10px; font-weight: 600; }
  .badge.completeness-full { background: #e8f5e9; color: #2e7d32; }
  .badge.completeness-partial { background: #fff8e1; color: #f57f17; }
  .badge.completeness-sparse { background: #fce4ec; color: #c62828; }
  .badge.standout { background: #e8f5e9; color: #2e7d32; }
  .badge.watchout { background: #fce4ec; color: #c62828; }

  .props { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 6px 16px; margin-bottom: 8px; }
  .prop { font-size: 12px; }
  .prop .k { color: #999; }
  .prop .v { font-weight: 500; }

  .criteria-chart { margin: 10px 0; }
  .criteria-row { display: flex; align-items: center; margin-bottom: 4px; font-size: 12px; }
  .criteria-label { width: 110px; color: #666; flex-shrink: 0; text-transform: capitalize; }
  .criteria-bar-container { flex: 1; height: 16px; background: #f0f0f0; border-radius: 8px; position: relative; margin: 0 8px; }
  .criteria-bar-fill { height: 100%; border-radius: 8px; transition: width 0.3s; }
  .criteria-bar-fill.green { background: #4ecdc4; }
  .criteria-bar-fill.yellow { background: #ffd93d; }
  .criteria-bar-fill.red { background: #ff6b6b; }
  .criteria-avg-marker { position: absolute; top: -2px; bottom: -2px; width: 2px; background: rgba(0,0,0,0.25); border-radius: 1px; }
  .criteria-score-text { width: 45px; text-align: right; font-weight: 600; flex-shrink: 0; }
  .criteria-confidence { width: 36px; text-align: center; flex-shrink: 0; font-size: 10px; letter-spacing: -1px; }
  .criteria-evidence { display: none; font-size: 11px; color: #888; padding: 2px 0 2px 118px; }
  .criteria-row:hover + .criteria-evidence, .criteria-evidence:hover { display: block; }
  .criteria-row.expandable { cursor: pointer; }

  .pros-cons { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 10px 0; }
  .pros-cons ul { list-style: none; padding: 0; }
  .pros-cons li { font-size: 12px; padding: 2px 0; line-height: 1.4; }
  .pros-cons .pro-list li::before { content: "✓ "; color: #2e7d32; font-weight: bold; }
  .pros-cons .con-list li::before { content: "✗ "; color: #c62828; font-weight: bold; }
  .pros-cons h4 { font-size: 11px; text-transform: uppercase; color: #888; margin-bottom: 4px; letter-spacing: 0.5px; }

  .peace-detail { font-size: 11px; color: #888; margin: 4px 0; }

  .images { display: flex; gap: 6px; overflow-x: auto; margin-top: 8px; padding-bottom: 4px; -webkit-overflow-scrolling: touch; }
  .images img { height: 120px; border-radius: 6px; object-fit: cover; cursor: pointer; flex-shrink: 0; }
  .images img:hover { opacity: 0.8; }
  .disq-reason { color: #d32f2f; font-weight: 500; font-size: 12px; margin-bottom: 6px; }
  .lightbox { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.9); z-index: 1000; justify-content: center; align-items: center; cursor: pointer; }
  .lightbox.active { display: flex; }
  .lightbox img { max-width: 90%; max-height: 90%; object-fit: contain; border-radius: 8px; }

  .filter-toggle { display: none; }

  @media (max-width: 600px) {
    .top-bar { padding: 12px 16px; }
    .top-bar h1 { font-size: 16px; }
    .filter-toggle { display: flex; align-items: center; justify-content: space-between; background: #fff; padding: 10px 16px; border-bottom: 1px solid #e0e0e0; position: sticky; top: 0; z-index: 100; cursor: pointer; -webkit-tap-highlight-color: transparent; }
    .filter-toggle .ft-label { font-size: 13px; font-weight: 600; color: #555; }
    .filter-toggle .ft-count { font-size: 13px; color: #888; }
    .filter-toggle .ft-arrow { font-size: 12px; color: #888; transition: transform 0.2s; }
    .filter-toggle.open .ft-arrow { transform: rotate(180deg); }
    .controls { padding: 10px 16px; gap: 6px; flex-direction: column; align-items: stretch; position: sticky; top: 42px; max-height: 0; overflow: hidden; padding: 0 16px; border-bottom: none; transition: max-height 0.25s ease, padding 0.25s ease; }
    .controls.open { max-height: 600px; padding: 10px 16px; border-bottom: 1px solid #e0e0e0; }
    .control-group { width: 100%; }
    .control-group input[type=range] { flex: 1; width: auto; }
    .toggle { justify-content: flex-start; }
    .container { padding: 12px 10px; }
    .card { padding: 14px; }
    .card-top { flex-direction: column; gap: 6px; }
    .score { align-self: flex-start; margin-left: 0; }
    .props { grid-template-columns: 1fr 1fr; gap: 4px 10px; }
    .pros-cons { grid-template-columns: 1fr; }
    .criteria-label { width: 80px; font-size: 11px; }
    .images img { height: 100px; }
    .result-count { margin-left: 0; }
    .toggle label { font-size: 14px; }
  }
</style>
</head>
<body>

<div class="top-bar">
  <h1>House Hunt Report</h1>
  <div class="meta">
    Run: <span>{{ run_id }}</span> &middot;
    Config: <span>{{ config_name }}</span> &middot;
    Total: <span>{{ total }}</span>
  </div>
</div>

<div class="comp-banner" id="comp-banner"></div>

<div class="filter-toggle" id="filter-toggle" onclick="this.classList.toggle('open');document.getElementById('controls').classList.toggle('open')">
  <span class="ft-label">Filters</span>
  <span class="ft-count" id="ft-count"></span>
  <span class="ft-arrow">&#9660;</span>
</div>
<div class="controls" id="controls">
  <div class="control-group">
    <label>Max Rent</label>
    <div style="display:flex;align-items:center;gap:6px;">
      <input type="range" id="f-rent" min="5000" max="100000" step="1000" value="100000">
      <span class="range-val" id="f-rent-val">₹1L</span>
    </div>
  </div>
  <div class="control-group">
    <label>Max Travel (min)</label>
    <div style="display:flex;align-items:center;gap:6px;">
      <input type="range" id="f-travel" min="5" max="120" step="5" value="120">
      <span class="range-val" id="f-travel-val">120</span>
    </div>
  </div>
  <div class="control-group">
    <label>Min Area (sqft)</label>
    <div style="display:flex;align-items:center;gap:6px;">
      <input type="range" id="f-sqft" min="0" max="2000" step="50" value="0">
      <span class="range-val" id="f-sqft-val">Any</span>
    </div>
  </div>
  <div class="control-group">
    <label>Furnishing</label>
    <select id="f-furn">
      <option value="all">All</option>
      <option value="Full">Full</option>
      <option value="Semi">Semi</option>
    </select>
  </div>
  <div class="control-group">
    <label>Sort By</label>
    <select id="f-sort">
      <option value="score">Final Score</option>
      <option value="rank">Comparative Rank</option>
      <option value="rent">Rent (low)</option>
      <option value="travel">Travel (short)</option>
      <option value="sqft">Area (big)</option>
      <option value="value">₹/sqft (low)</option>
      <option value="power_backup">Power Backup</option>
      <option value="noise">Noise/Peace</option>
      <option value="internet">Internet</option>
      <option value="wfh_livability">WFH Livability</option>
      <option value="water">Water Supply</option>
    </select>
  </div>
  <div class="control-group">
    <label>Min Confidence</label>
    <select id="f-confidence">
      <option value="any">Any</option>
      <option value="medium">Medium+</option>
      <option value="high">High only</option>
    </select>
  </div>
  <div class="control-group toggle">
    <input type="checkbox" id="f-power" checked>
    <label for="f-power">Power backup only</label>
  </div>
  <div class="control-group toggle">
    <input type="checkbox" id="f-gated">
    <label for="f-gated">Gated only</label>
  </div>
  <div class="control-group toggle">
    <input type="checkbox" id="f-hide-disq" checked>
    <label for="f-hide-disq">Hide disqualified</label>
  </div>
  <div class="control-group toggle">
    <input type="checkbox" id="f-hide-dupes" checked>
    <label for="f-hide-dupes">Hide duplicates</label>
  </div>
  <div class="result-count" id="result-count"></div>
</div>

<div class="container">
  <div class="cards" id="cards"></div>
</div>

<div class="lightbox" id="lightbox" onclick="this.classList.remove('active')">
  <img id="lightbox-img" src="">
</div>

<script>
const DATA = {{ entries_json }};
const THRESHOLD = {{ threshold }};
const CRITERIA_AVERAGES = {{ criteria_averages_json }};
const COMPARATIVE = {{ comparative_json }};

function esc(s) { return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

const CONF_ORDER = {high: 3, medium: 2, low: 1};
const CONF_DOTS = {high: '●●●', medium: '●●○', low: '●○○'};
const CONF_COLORS = {high: '#2e7d32', medium: '#f57f17', low: '#999'};

function barColor(score, max) {
  const pct = score / max;
  if (pct >= 0.8) return 'green';
  if (pct >= 0.5) return 'yellow';
  return 'red';
}

function completenessLabel(dc) {
  if (dc >= 0.7) return {cls: 'full', text: 'Full data'};
  if (dc >= 0.4) return {cls: 'partial', text: 'Partial data'};
  return {cls: 'sparse', text: 'Sparse data'};
}

function criteriaChart(cs, avgs) {
  if (!cs) return '';
  let rows = '';
  for (const [key, val] of Object.entries(cs)) {
    const pct = (val.score / val.max * 100).toFixed(0);
    const color = barColor(val.score, val.max);
    const avg = avgs[key];
    const avgPct = avg ? (avg / val.max * 100).toFixed(0) : null;
    const avgMarker = avgPct ? `<div class="criteria-avg-marker" style="left:${avgPct}%" title="Avg: ${avg}"></div>` : '';
    const label = key.replace(/_/g, ' ');
    rows += `<div class="criteria-row expandable">
      <span class="criteria-label">${label}</span>
      <div class="criteria-bar-container">
        <div class="criteria-bar-fill ${color}" style="width:${pct}%"></div>
        ${avgMarker}
      </div>
      <span class="criteria-score-text">${val.score}/${val.max}</span>
      <span class="criteria-confidence" style="color:${CONF_COLORS[val.confidence]}" title="${val.confidence} confidence">${CONF_DOTS[val.confidence]}</span>
    </div>
    <div class="criteria-evidence">${esc(val.evidence)}</div>`;
  }
  return `<div class="criteria-chart">${rows}</div>`;
}

function prosCons(pros, cons) {
  if ((!pros || !pros.length) && (!cons || !cons.length)) return '';
  const proHtml = pros && pros.length ? `<div class="pro-list"><h4>Strengths</h4><ul>${pros.map(p => `<li>${esc(p)}</li>`).join('')}</ul></div>` : '';
  const conHtml = cons && cons.length ? `<div class="con-list"><h4>Weaknesses</h4><ul>${cons.map(c => `<li>${esc(c)}</li>`).join('')}</ul></div>` : '';
  return `<div class="pros-cons">${proHtml}${conHtml}</div>`;
}

function badgesHtml(e) {
  let html = '';
  const dc = e.data_completeness;
  if (dc != null) {
    const cl = completenessLabel(dc);
    html += `<span class="badge completeness-${cl.cls}">${cl.text} (${Math.round(dc*100)}%)</span>`;
  }
  if (e.criteria_scores) {
    for (const [key, val] of Object.entries(e.criteria_scores)) {
      const pct = val.score / val.max;
      if (pct >= 0.9) html += `<span class="badge standout">★ ${key.replace(/_/g,' ')}</span>`;
      else if (pct < 0.4) html += `<span class="badge watchout">⚠ ${key.replace(/_/g,' ')}</span>`;
    }
  }
  return html ? `<div class="badges">${html}</div>` : '';
}

function peaceDetail(pb) {
  if (!pb) return '';
  const bonus = pb.locality_bonus > 0 ? ` + bonus ${pb.locality_bonus}` : '';
  return `<div class="peace-detail">Peace: ORR ${Math.round(pb.orr_distance_m)}m → base ${pb.base_score}${bonus} → ${pb.final}</div>`;
}

function makeCard(e, rank) {
  const s = e.summary, d = e.detail || {};
  const isDisq = e.disqualified;
  const isDupe = !!e.duplicate_of;
  const isAct = e.final_score >= THRESHOLD && !isDisq;
  const cls = isAct ? 'act-now' : (isDisq ? 'disqualified' : 'qualified');
  let tagHtml = isAct ? '<span class="tag act">Act Now</span>' : (isDisq ? '<span class="tag disq">DQ</span>' : '');
  if (isDupe) tagHtml += `<span class="tag dupe">Duplicate</span>`;
  if (e.comparative_rank && e.comparative_rank <= 3) tagHtml += `<span class="tag act">#${e.comparative_rank} Pick</span>`;
  const scoreClass = isAct ? 'high' : (isDisq ? 'disq' : '');
  const totalRent = s.rent + (s.maintenance || 0);

  const minConf = Math.min(...Object.values(e.criteria_scores || {}).map(v => CONF_ORDER[v.confidence] || 0));

  return `<div class="card ${cls}" data-rent="${totalRent}" data-travel="${e.walk_minutes}" data-sqft="${s.sqft}" data-score="${e.final_score}" data-furn="${d.furnishing || ''}" data-power="${d.power_backup || ''}" data-gated="${d.gated_security}" data-disq="${isDisq}" data-dupe="${isDupe}" data-value="${s.sqft > 0 ? (totalRent/s.sqft).toFixed(1) : 999}" data-rank="${e.comparative_rank || 999}" data-min-conf="${minConf}" ${Object.entries(e.criteria_scores||{}).map(([k,v]) => `data-cs-${k}="${v.score}"`).join(' ')}>
    <div class="card-top">
      <h2><span class="rank">#${rank}</span><a href="${s.detail_url}" target="_blank">${esc(s.title)}</a>${tagHtml}</h2>
      <span class="score ${scoreClass}">${e.final_score}</span>
    </div>
    ${e.elevator_pitch ? `<div class="elevator-pitch">${esc(e.elevator_pitch)}</div>` : ''}
    ${isDisq ? `<div class="disq-reason">${esc(e.disqualify_reason)}</div>` : ''}
    ${badgesHtml(e)}
    <div class="props">
      <div class="prop"><span class="k">Rent </span><span class="v">₹${totalRent.toLocaleString('en-IN')}</span></div>
      <div class="prop"><span class="k">Deposit </span><span class="v">₹${s.deposit.toLocaleString('en-IN')}</span></div>
      <div class="prop"><span class="k">Area </span><span class="v">${s.sqft} sqft</span></div>
      <div class="prop"><span class="k">Travel </span><span class="v">${e.walk_minutes} min</span></div>
      <div class="prop"><span class="k">ORR </span><span class="v">${Math.round(e.orr_distance_m)}m</span></div>
      <div class="prop"><span class="k">Furnishing </span><span class="v">${d.furnishing || '?'}</span></div>
      <div class="prop"><span class="k">Floor </span><span class="v">${d.floor || '?'}</span></div>
      <div class="prop"><span class="k">Power </span><span class="v">${d.power_backup || '?'}</span></div>
      <div class="prop"><span class="k">Water </span><span class="v">${d.water_supply || '?'}</span></div>
      <div class="prop"><span class="k">Security </span><span class="v">${d.gated_security === true ? 'Yes' : (d.gated_security === false ? 'No' : '?')}</span></div>
      <div class="prop"><span class="k">₹/sqft </span><span class="v">${s.sqft > 0 ? (totalRent/s.sqft).toFixed(0) : '?'}</span></div>
      <div class="prop"><span class="k">LLM </span><span class="v">${e.llm_score}</span></div>
      <div class="prop"><span class="k">Peace </span><span class="v">${e.peace_score}</span></div>
    </div>
    ${criteriaChart(e.criteria_scores, CRITERIA_AVERAGES)}
    ${prosCons(e.pros, e.cons)}
    ${peaceDetail(e.peace_breakdown)}
    ${e.comparative_notes ? `<div class="peace-detail"><strong>vs others:</strong> ${esc(e.comparative_notes)}</div>` : ''}
    ${s.image_urls && s.image_urls.length > 0 && s.image_urls[0].includes('images.nobroker.in') ? `<div class="images">${s.image_urls.map(u => `<img src="${u}" loading="lazy" onclick="event.stopPropagation();document.getElementById('lightbox-img').src='${u}';document.getElementById('lightbox').classList.add('active')">`).join('')}</div>` : ''}
  </div>`;
}

function renderBanner() {
  const el = document.getElementById('comp-banner');
  if (!COMPARATIVE || !COMPARATIVE.top_3_summary) return;
  el.innerHTML = `<h2>Top Picks</h2><div class="pick">${esc(COMPARATIVE.top_3_summary).replace(/#(\d)/g, '<strong>#$1</strong>')}</div>`;
  el.classList.add('visible');
}

function render() {
  const maxRent = +document.getElementById('f-rent').value;
  const maxTravel = +document.getElementById('f-travel').value;
  const minSqft = +document.getElementById('f-sqft').value;
  const furn = document.getElementById('f-furn').value;
  const powerOnly = document.getElementById('f-power').checked;
  const gatedOnly = document.getElementById('f-gated').checked;
  const hideDisq = document.getElementById('f-hide-disq').checked;
  const hideDupes = document.getElementById('f-hide-dupes').checked;
  const sortBy = document.getElementById('f-sort').value;
  const minConf = document.getElementById('f-confidence').value;

  document.getElementById('f-rent-val').textContent = maxRent >= 100000 ? '₹1L+' : `₹${(maxRent/1000).toFixed(0)}K`;
  document.getElementById('f-travel-val').textContent = maxTravel;
  document.getElementById('f-sqft-val').textContent = minSqft === 0 ? 'Any' : minSqft;

  const confMin = minConf === 'high' ? 3 : (minConf === 'medium' ? 2 : 0);

  let filtered = DATA.filter(e => {
    const s = e.summary, d = e.detail || {};
    const totalRent = s.rent + (s.maintenance || 0);
    if (hideDisq && e.disqualified) return false;
    if (hideDupes && e.duplicate_of) return false;
    if (totalRent > maxRent && maxRent < 100000) return false;
    if (e.walk_minutes > maxTravel) return false;
    if (s.sqft < minSqft) return false;
    if (furn !== 'all' && (d.furnishing || '') !== furn) return false;
    if (powerOnly && !d.power_backup) return false;
    if (gatedOnly && d.gated_security !== true) return false;
    if (confMin > 0 && e.criteria_scores) {
      const worst = Math.min(...Object.values(e.criteria_scores).map(v => CONF_ORDER[v.confidence] || 0));
      if (worst < confMin) return false;
    }
    return true;
  });

  const csSort = (key) => (a, b) => {
    const sa = a.criteria_scores && a.criteria_scores[key] ? a.criteria_scores[key].score : 0;
    const sb = b.criteria_scores && b.criteria_scores[key] ? b.criteria_scores[key].score : 0;
    return sb - sa;
  };
  const sorters = {
    score: (a, b) => b.final_score - a.final_score,
    rank: (a, b) => (a.comparative_rank || 999) - (b.comparative_rank || 999),
    rent: (a, b) => (a.summary.rent + (a.summary.maintenance||0)) - (b.summary.rent + (b.summary.maintenance||0)),
    travel: (a, b) => a.walk_minutes - b.walk_minutes,
    sqft: (a, b) => b.summary.sqft - a.summary.sqft,
    value: (a, b) => {
      const va = a.summary.sqft > 0 ? (a.summary.rent + (a.summary.maintenance||0))/a.summary.sqft : 999;
      const vb = b.summary.sqft > 0 ? (b.summary.rent + (b.summary.maintenance||0))/b.summary.sqft : 999;
      return va - vb;
    },
    power_backup: csSort('power_backup'),
    noise: csSort('noise'),
    internet: csSort('internet'),
    wfh_livability: csSort('wfh_livability'),
    water: csSort('water'),
  };
  filtered.sort(sorters[sortBy] || sorters.score);

  document.getElementById('cards').innerHTML = filtered.map((e, i) => makeCard(e, i + 1)).join('');
  const countText = `${filtered.length} / ${DATA.length} listings`;
  document.getElementById('result-count').textContent = countText;
  const ftCount = document.getElementById('ft-count');
  if (ftCount) ftCount.textContent = countText;
}

document.getElementById('controls').addEventListener('input', render);
document.getElementById('controls').addEventListener('change', render);
renderBanner();
render();
</script>
</body>
</html>
```

- [ ] **Step 2: Run reporter tests to verify template renders**

Run: `.venv/bin/python -m pytest tests/test_reporter.py -v`
Expected: ALL PASS (tests from Task 7 verify new template renders correctly)

- [ ] **Step 3: Commit**

```bash
git add src/report_template.html
git commit -m "feat: HTML report with criteria bars, pros/cons, elevator pitch, comparative banner"
```

---

### Task 9: Update Score Skill for Claude Code Judge

**Files:**
- Modify: `.claude/skills/score/SKILL.md`

**Interfaces:**
- Consumes: new `ScoredListing` schema
- Produces: updated skill instructions so Claude Code writes correct `scored.json` format

- [ ] **Step 1: Update SKILL.md with new schema**

Replace the scored.json output format in the skill to match new `ScoredListing` fields:

```markdown
---
name: score
description: Score filtered listings as LLM judge — per-criteria structured evaluation with confidence, evidence, pros/cons, and elevator pitch.
---

# LLM Scoring (Claude Code as Judge)

Score listings directly in Claude Code — no API key needed, uses your Max plan.

## How to run

1. Find the latest run:
\`\`\`bash
ls -t data/runs/ | head -1
\`\`\`

2. Read the filtered listings:
\`\`\`bash
cat data/runs/{RUN_ID}/filtered.json
\`\`\`

3. Read the config to get scoring weights:
\`\`\`bash
cat data/runs/{RUN_ID}/config.json
\`\`\`

4. For EACH listing in `filtered.json`, evaluate against these criteria:

**HARD REQUIREMENT — 100% power backup:**
If `detail.power_backup` is missing, null, "None", "No", partial, or inverter-only → `disqualified: true`.

**Scoring criteria — score each independently:**

| Criteria | Max Points | What to check |
|----------|-----------|---------------|
| power_backup | `llm_weights.power_backup` | Generator vs inverter, full vs partial, explicit mention |
| noise | `llm_weights.noise` | Description signals, floor level, facing away from road |
| internet | `llm_weights.internet` | Fiber-ready, broadband mentions, ACT/Airtel |
| light_ventilation | `llm_weights.light_ventilation` | Facing, balconies, mid-floor (2-4) preference |
| water | `llm_weights.water` | Corporation + borewell + sump > borewell-only |
| maintenance | `llm_weights.maintenance` | Gated community, managed maintenance, security |
| wfh_livability | `llm_weights.wfh_livability` | Room for desk, semi/fully furnished, quiet layout |
| value | `llm_weights.value` | Rent vs sqft vs amenities ratio |

**Confidence per criterion:**
- `high`: listing explicitly states this info
- `medium`: inferred from description or context
- `low`: no info available, scoring on defaults

5. Compute scores:
\`\`\`
llm_score = sum of all criteria scores
final_score = (config.score_weights.peace * peace_score) + (config.score_weights.llm * llm_score)
\`\`\`

6. Write results to `data/runs/{RUN_ID}/scored.json` as a JSON array. Each entry:
\`\`\`json
{
  "summary": { ... },
  "detail": { ... },
  "lat": ..., "lon": ...,
  "walk_minutes": ..., "orr_distance_m": ...,
  "peace_score": ...,
  "llm_score": "<sum of criteria scores, 0-100>",
  "final_score": "<weighted combo>",
  "disqualified": "<true|false>",
  "disqualify_reason": "<reason or null>",
  "criteria_scores": {
    "<criterion>": {"score": "<0-max>", "max": "<from config>", "confidence": "<high|medium|low>", "evidence": "<what drove this score>"}
  },
  "pros": ["<2-5 key strengths>"],
  "cons": ["<1-4 key weaknesses>"],
  "elevator_pitch": "<1-line shareable summary>",
  "data_completeness": "<from filtered.json or estimate 0-1>",
  "peace_breakdown": "<from filtered.json if available>",
  "comparative_rank": null,
  "comparative_notes": null,
  "duplicate_of": null
}
\`\`\`

Write the file using the Write tool — do NOT use Python scripts or API calls.

## After scoring — Comparative Pass

After scoring all listings, do a comparative pass:

1. Review all qualified (non-disqualified) listings together
2. Rank them from best to worst for a WFH-heavy hybrid worker
3. For each listing, write 1 sentence explaining its rank relative to others
4. Update each listing's `comparative_rank` and `comparative_notes` in scored.json
5. Write `data/runs/{RUN_ID}/comparative.json`:
\`\`\`json
{
  "rankings": [{"property_id": "<id>", "rank": 1, "reasoning": "<vs others>"}],
  "top_3_summary": "#1 Name — why. #2 Name — why. #3 Name — why."
}
\`\`\`

## After scoring

Present scores to user. Run `/report` to generate ranked report.
```

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/score/SKILL.md
git commit -m "docs: update score skill for structured scoring schema"
```

---

### Task 10: Integration Test — Full Pipeline Dry Run

**Files:**
- Modify: `tests/test_integration.py` (if exists)

**Interfaces:**
- Consumes: all prior tasks
- Produces: verification that `scored.json` → `generate_report()` → valid HTML with all new elements

- [ ] **Step 1: Write integration test**

```python
# tests/test_integration.py — add or update

import json

def test_full_report_pipeline_with_structured_scoring(tmp_path):
    """Verify scored.json with new schema produces complete HTML report."""
    from src.reporter import generate_report
    from src.config import Config, RunContext

    cfg = Config(
        name="test", target_localities=["kadubeesanahalli"], ptp_coords=(12.942, 77.6905),
        max_walk_minutes=30, min_orr_distance_m=200, max_rent=60000, score_threshold=75,
        bhk=2, score_weights={"peace": 0.4, "llm": 0.6},
        llm_weights={"power_backup": 20, "noise": 20, "internet": 15, "light_ventilation": 10,
            "water": 10, "maintenance": 10, "wfh_livability": 10, "value": 5}
    )

    scored = [{
        "summary": {"property_id": "int1", "title": "Integration Test Flat", "rent": 30000,
            "deposit": 100000, "maintenance": 3000, "sqft": 1100, "address": "Test Rd",
            "locality": "kadubeesanahalli", "building_name": "Test Heights",
            "detail_url": "https://nobroker.in/int1", "available_date": None, "image_urls": []},
        "detail": {"property_id": "int1", "furnishing": "Semi", "floor": "3/5",
            "power_backup": "Full Generator", "facing": "East", "bathrooms": 2, "balconies": 1,
            "parking": "Car", "building_age": "1-3", "preferred_tenant": "Family",
            "water_supply": "Corporation + Borewell", "gated_security": True, "description": "Nice flat"},
        "lat": 12.94, "lon": 77.69, "walk_minutes": 8.0, "orr_distance_m": 450,
        "peace_score": 80.0, "llm_score": 86.0, "final_score": 83.6,
        "disqualified": False, "disqualify_reason": None,
        "criteria_scores": {
            "power_backup": {"score": 19, "max": 20, "confidence": "high", "evidence": "Full gen mentioned"},
            "noise": {"score": 16, "max": 20, "confidence": "medium", "evidence": "3rd floor, east"},
            "internet": {"score": 10, "max": 15, "confidence": "low", "evidence": "No fiber info"},
            "light_ventilation": {"score": 9, "max": 10, "confidence": "high", "evidence": "East, 1 balcony"},
            "water": {"score": 9, "max": 10, "confidence": "high", "evidence": "Corp + borewell"},
            "maintenance": {"score": 9, "max": 10, "confidence": "high", "evidence": "Gated, security"},
            "wfh_livability": {"score": 8, "max": 10, "confidence": "medium", "evidence": "Semi, spacious"},
            "value": {"score": 4, "max": 5, "confidence": "high", "evidence": "30/sqft reasonable"},
        },
        "pros": ["Full generator", "Gated community", "Good water", "Close to PTP"],
        "cons": ["No fiber internet info", "Semi-furnished"],
        "elevator_pitch": "Gated 3rd-floor flat, full generator, 8min walk to PTP",
        "data_completeness": 0.92,
        "peace_breakdown": {"orr_distance_m": 450, "base_score": 61.7, "locality_bonus": 20, "final": 80},
        "comparative_rank": 1, "comparative_notes": "Best overall for WFH",
        "duplicate_of": None,
    }]

    comparative = {
        "rankings": [{"property_id": "int1", "rank": 1, "reasoning": "Best overall"}],
        "top_3_summary": "#1 Integration Test Flat — best overall for WFH."
    }

    run_dir = tmp_path / "int_run"
    run_dir.mkdir()
    (run_dir / "scored.json").write_text(json.dumps(scored))
    (run_dir / "config.json").write_text(cfg.model_dump_json())
    (run_dir / "comparative.json").write_text(json.dumps(comparative))
    ctx = RunContext(run_id="test_int", run_dir=run_dir, config=cfg)

    html_path = generate_report(ctx)
    html = html_path.read_text()

    # Verify all new sections present
    assert "elevator-pitch" in html or "Gated 3rd-floor flat" in html
    assert "criteria-chart" in html or "criteria-bar" in html
    assert "pro-list" in html or "Strengths" in html
    assert "con-list" in html or "Weaknesses" in html
    assert "comp-banner" in html
    assert "Top Picks" in html or "top_3_summary" in html
    assert "power_backup" in html or "power backup" in html
    assert "confidence" in html.lower() or "●●●" in html

    # Verify markdown
    md = (run_dir / "report.md").read_text()
    assert "Full generator" in md
    assert "No fiber" in md
    assert "Gated 3rd-floor flat" in md
    assert "Top Picks" in md
```

- [ ] **Step 2: Run integration test**

Run: `.venv/bin/python -m pytest tests/test_integration.py -v`
Expected: ALL PASS

- [ ] **Step 3: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: integration test for structured scoring pipeline"
```

---

## Task Dependency Graph

```
Task 1 (Models) ──┬──> Task 2 (Peace Breakdown)
                  ├──> Task 3 (Detail Scraper)
                  ├──> Task 4 (Pass 1 Scorer) ──> Task 5 (Pass 2 Comparative)
                  │                                        │
                  └──> Task 6 (Smart Dedup) <──────────────┘
                                │
                  Task 7 (Reporter) <── Tasks 1-6
                                │
                  Task 8 (HTML Template) <── Task 7
                                │
                  Task 9 (Score Skill) ── independent
                                │
                  Task 10 (Integration) <── all
```

Tasks 2, 3, 4, 9 can run in parallel after Task 1. Tasks 5 and 6 after Task 4. Tasks 7 and 8 sequential. Task 10 last.
