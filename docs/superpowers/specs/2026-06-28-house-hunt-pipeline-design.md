# House Hunt Pipeline — Design Spec

## Overview

Autonomous house-hunting pipeline for 2BHK rentals near Prestige Tech Park (PTP), Kadubeesanahalli, Bangalore. Optimized for a hybrid worker (8 days/month in office, rest WFH). Scrapes NoBroker, applies spatial and semantic filtering, outputs ranked JSON reports.

## Constraints

- 2BHK only
- Rent ≤ ₹50,000/month
- Walking distance to PTP ≤ 12 minutes
- ≥ 200m from Outer Ring Road (noise insulation)
- 100% power backup — non-negotiable hard requirement
- Peaceful, quiet residential environment

## Architecture

Claude Code skills orchestrate modular Python modules. Each pipeline stage is independently runnable via a skill. JSON files at stage boundaries for debuggability.

### Project Structure

```
house_hunt/
├── .claude/skills/
│   ├── scrape/SKILL.md     # /scrape — Firecrawl on NoBroker
│   ├── filter/SKILL.md     # /filter — geocode + spatial filtering
│   ├── score/SKILL.md      # /score — LLM-as-judge evaluation
│   ├── report/SKILL.md     # /report — ranked JSON output
│   ├── hunt/SKILL.md       # /hunt — full pipeline
│   └── compare/SKILL.md    # /compare — diff two runs
├── src/
│   ├── scraper.py           # Firecrawl API + markdown parsing
│   ├── models.py            # Pydantic schemas
│   ├── spatial.py           # Google Maps geocoding + distance
│   ├── scorer.py            # Claude Sonnet judge
│   ├── reporter.py          # Output formatting
│   ├── config.py            # Config loader (profiles + defaults)
│   └── db.py                # SQLite dedup
├── configs/
│   └── default.json         # Baseline config profile
├── data/
│   └── runs/                # One directory per pipeline run
│       └── {run_id}/        # e.g. 20260628_143022
│           ├── config.json  # Frozen config snapshot
│           ├── raw.json
│           ├── filtered.json
│           ├── scored.json
│           └── report.md
├── .env                     # API keys
└── pyproject.toml
```

### Dependencies

- `firecrawl-py` — NoBroker scraping
- `pydantic` — schema validation
- `anthropic` — Claude Sonnet judge
- `googlemaps` — geocoding + distance matrix
- `httpx` — HTTP client

## Pipeline Stages

### Stage 1: Scrape (`/scrape`)

**Two-phase scrape of NoBroker via Firecrawl cloud API.**

Phase 1 — SEO listing pages (4 Firecrawl calls):
- `/2bhk-flats-for-rent-in-kadubeesanahalli_bangalore`
- `/2bhk-flats-for-rent-in-bellandur_bangalore`
- `/2bhk-flats-for-rent-in-panathur_bangalore`
- `/2bhk-flats-for-rent-in-marathahalli_bangalore`

Each returns ~25 listings with: title, rent, deposit, maintenance, sqft, address, building name, detail URL, available date, image URLs.

Phase 2 — Detail pages for new listings passing basic filters (rent ≤ 50K, 2BHK). Adds: furnishing, floor, power backup, description, water supply, gated security, facing, bathrooms, balconies, parking, building age, preferred tenant.

SQLite dedup: skip already-seen property IDs.

Output: `data/runs/{run_id}/raw.json`

### Stage 2: Spatial Filter (`/filter`)

For each listing:
1. Google Geocoding API: address string → lat/lon
2. Google Distance Matrix API: walking route to PTP main gate (12.9420°N, 77.6905°E)
3. Drop if walk time > 12 minutes
4. Calculate straight-line distance to ORR centerline
5. Assign peace score:
   - < 200m from ORR → disqualify (severe noise)
   - 200-400m → peace_score penalty
   - > 400m or inner layout → peace_score bonus
   - Bhoganhalli/Gear Road area → highest priority bonus

Output: `data/runs/{run_id}/filtered.json`

### Stage 3: LLM Score (`/score`)

Each surviving listing evaluated by Claude Sonnet (`claude-sonnet-4-20250514`).

**Hard requirement:** 100% power backup. Missing = instant disqualify.

**Scoring criteria (0-100):**

| Criteria | Weight | What LLM checks |
|----------|--------|-----------------|
| Power backup quality & coverage | 20 pts | Generator vs inverter, full vs partial, explicit mention |
| Noise insulation / peaceful environment | 20 pts | Description signals, floor level, facing away from road |
| Internet/connectivity infrastructure | 15 pts | Fiber-ready, broadband mentions, ACT/Airtel availability |
| Natural light, ventilation, floor level | 10 pts | Facing, balconies, mid-floor preference (2-4), window mentions |
| Water supply reliability | 10 pts | Corporation + borewell + sump > borewell-only |
| Building maintenance & security | 10 pts | Gated community, managed maintenance, security staff |
| WFH livability (space, furnishing) | 10 pts | Room for desk, semi/fully furnished, quiet internal layout |
| Value for money | 5 pts | Rent vs sqft vs amenities ratio |

**Prompt structure:** Listing JSON + structured criteria → returns `{score, reasoning, disqualified, disqualify_reason}`

One API call per listing. Expected: 5-15 Sonnet calls per run.

Output: `data/runs/{run_id}/scored.json`

### Stage 4: Report (`/report`)

- Read scored JSON, sort by `final_score` descending
- `final_score = (peace_weight * peace_score) + (llm_weight * llm_score)` (weights from config)
- Flag listings with final_score ≥ threshold as "act now"
- Print ranked table + detail cards with NoBroker links
- Output: `data/runs/{run_id}/report.md`

### Compare (`/compare`)

Diff two runs side-by-side:
- Which listings appear in both, only in run A, only in run B
- Score changes for shared listings (did config change help?)
- Config diff — what parameters changed between runs
- Usage: `/compare 20260628_143022 20260628_160455`

## Data Models

```python
class ListingSummary(BaseModel):
    property_id: str
    title: str
    rent: int                    # monthly in ₹
    deposit: int
    maintenance: int | None
    sqft: int
    address: str
    locality: str
    building_name: str | None
    detail_url: str
    available_date: str | None
    image_urls: list[str]

class ListingDetail(BaseModel):
    property_id: str
    furnishing: str              # "Fully", "Semi", "Unfurnished"
    floor: str                   # "3/4"
    power_backup: str | None     # "Full", "Partial", "None", None
    facing: str | None
    bathrooms: int | None
    balconies: int | None
    parking: str | None
    building_age: str | None
    preferred_tenant: str | None
    water_supply: str | None
    gated_security: bool | None
    description: str

class ScoredListing(BaseModel):
    summary: ListingSummary
    detail: ListingDetail
    lat: float
    lon: float
    walk_minutes: float
    orr_distance_m: float
    peace_score: float           # 0-100
    llm_score: float             # 0-100
    llm_reasoning: str
    final_score: float           # weighted combo
    disqualified: bool
    disqualify_reason: str | None
```

## Configuration & Experiment Tracking

### Config Profiles

Named JSON files in `configs/`. Each run snapshots the active config into `data/runs/{run_id}/config.json` for reproducibility.

**`configs/default.json`:**
```json
{
  "name": "default",
  "target_localities": ["kadubeesanahalli", "bellandur", "panathur", "marathahalli"],
  "ptp_coords": [12.9420, 77.6905],
  "max_walk_minutes": 12,
  "min_orr_distance_m": 200,
  "max_rent": 50000,
  "score_threshold": 85,
  "bhk": 2,
  "score_weights": {"peace": 0.4, "llm": 0.6},
  "llm_weights": {
    "power_backup": 20,
    "noise": 20,
    "internet": 15,
    "light_ventilation": 10,
    "water": 10,
    "maintenance": 10,
    "wfh_livability": 10,
    "value": 5
  }
}
```

**Example `configs/peaceful.json`** (tighter noise constraints):
```json
{
  "name": "peaceful",
  "min_orr_distance_m": 300,
  "score_weights": {"peace": 0.5, "llm": 0.5},
  "llm_weights": {"noise": 25, "power_backup": 20, "internet": 15, "light_ventilation": 10, "water": 10, "maintenance": 10, "wfh_livability": 5, "value": 5}
}
```

Non-default profiles inherit from `default.json` — only override what changes.

**Usage:** `/hunt --config peaceful` or `/hunt` for default.

### Run Isolation

Each pipeline run gets a unique ID (`YYYYMMDD_HHMMSS`) and its own directory:
```
data/runs/20260628_143022/
├── config.json   # frozen snapshot of config used
├── raw.json      # scrape output
├── filtered.json # post-spatial
├── scored.json   # LLM scores
└── report.md     # ranked report
```

No data is ever overwritten. All runs preserved for comparison.

## External API Setup

### Firecrawl (ready)
- Cloud API, key in `.env`
- ~8 calls per run (4 listing pages + ~4 detail pages)
- Free tier: 500 scrapes/month

### Google Maps Platform (needs setup)
1. Create project at console.cloud.google.com
2. Enable: Geocoding API, Distance Matrix API
3. Create API key, restrict to these 2 APIs
4. Add `GOOGLE_MAPS_API_KEY` to `.env`
5. $200/month free credit covers personal volume

### Anthropic (needs key)
- Claude Sonnet for LLM judge
- Add `ANTHROPIC_API_KEY` to `.env`
- ~5-15 calls per run, minimal cost

## Dedup Strategy

SQLite `listings.db`:
```sql
CREATE TABLE seen (
    property_id TEXT PRIMARY KEY,
    first_seen TEXT,
    last_seen TEXT,
    score REAL,
    disqualified BOOLEAN
);
```

Re-runs only process new listings. Score history preserved.

## Target Micro-Markets

| Cluster | NoBroker Locality | Priority |
|---------|-------------------|----------|
| Bhoganhalli / Gear Road | kadubeesanahalli | Highest — rear gate PTP access, insulated from ORR |
| Kaverappa Layout / Inner Lanes | bellandur | Medium — buffer zone behind commercial corridor |
| Kariyammana Agrahara | panathur | Medium — acceptable if deep inner pockets |
| Doddakannelli overflow | marathahalli | Lower — only inner roads away from flyover |

## Out of Scope

- Telegram notifications (add later)
- Other portals (Housing.com, 99acres block crawling)
- Purchase/buy listings
- Cron scheduling (manual CLI trigger)
- Facebook/Telegram group scraping
