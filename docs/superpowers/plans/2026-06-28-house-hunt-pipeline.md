# House Hunt Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 5-stage house hunting pipeline (scrape → filter → score → report → compare) orchestrated by Claude Code skills, with config profiles and run isolation.

**Architecture:** Python modules in `src/` do the work. Claude Code skills in `.claude/skills/` invoke them. Each run gets a timestamped directory under `data/runs/`. Config profiles in `configs/` control thresholds and scoring weights. SQLite tracks seen listings for dedup.

**Tech Stack:** Python 3.11+, Pydantic 2, Firecrawl cloud API, Google Maps APIs (Geocoding + Distance Matrix), Anthropic Claude Sonnet, SQLite, httpx

## Global Constraints

- Python 3.11+ (union types `X | Y`, not `Optional[X]`)
- Use `httpx` for HTTP, not `requests`
- Use `.venv/bin/python` for all commands
- All API keys from `.env` via `python-dotenv`
- `ANTHROPIC_API_KEY` via env var (not .env)
- Pydantic v2 (`BaseModel`, `model_dump()`)
- No type:ignore, no bare except
- Spec: `docs/superpowers/specs/2026-06-28-house-hunt-pipeline-design.md`
- Existing fork code in `src/` — rewrite to match spec, don't preserve fork decisions that conflict

---

### Task 1: Config System + Run Isolation

**Files:**
- Create: `configs/default.json`
- Rewrite: `src/config.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Consumes: `configs/*.json` files, `.env`
- Produces:
  - `load_config(profile: str = "default") -> Config` — returns merged config (default + profile overrides)
  - `Config` — Pydantic model with all fields from spec
  - `create_run(config: Config) -> RunContext` — creates `data/runs/{run_id}/` dir, snapshots config, returns context
  - `RunContext.path(filename: str) -> Path` — resolves `data/runs/{run_id}/{filename}`

- [ ] **Step 1: Write failing test for config loading**

```python
# tests/test_config.py
import json
from pathlib import Path

def test_load_default_config(tmp_path):
    default = {
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
            "power_backup": 20, "noise": 20, "internet": 15,
            "light_ventilation": 10, "water": 10, "maintenance": 10,
            "wfh_livability": 10, "value": 5
        }
    }
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    (configs_dir / "default.json").write_text(json.dumps(default))

    from src.config import load_config
    cfg = load_config("default", configs_dir=configs_dir)
    assert cfg.name == "default"
    assert cfg.max_rent == 50000
    assert cfg.ptp_coords == (12.9420, 77.6905)
    assert cfg.score_weights == {"peace": 0.4, "llm": 0.6}
    assert cfg.llm_weights["power_backup"] == 20


def test_profile_inherits_and_overrides(tmp_path):
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    default = {
        "name": "default",
        "target_localities": ["kadubeesanahalli"],
        "ptp_coords": [12.9420, 77.6905],
        "max_walk_minutes": 12,
        "min_orr_distance_m": 200,
        "max_rent": 50000,
        "score_threshold": 85,
        "bhk": 2,
        "score_weights": {"peace": 0.4, "llm": 0.6},
        "llm_weights": {"power_backup": 20, "noise": 20, "internet": 15,
            "light_ventilation": 10, "water": 10, "maintenance": 10,
            "wfh_livability": 10, "value": 5}
    }
    peaceful = {
        "name": "peaceful",
        "min_orr_distance_m": 300,
        "score_weights": {"peace": 0.5, "llm": 0.5}
    }
    (configs_dir / "default.json").write_text(json.dumps(default))
    (configs_dir / "peaceful.json").write_text(json.dumps(peaceful))

    from src.config import load_config
    cfg = load_config("peaceful", configs_dir=configs_dir)
    assert cfg.name == "peaceful"
    assert cfg.min_orr_distance_m == 300
    assert cfg.score_weights == {"peace": 0.5, "llm": 0.5}
    assert cfg.max_rent == 50000  # inherited from default


def test_create_run(tmp_path):
    from src.config import load_config, create_run, Config
    import json

    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    default = {
        "name": "default", "target_localities": ["kadubeesanahalli"],
        "ptp_coords": [12.9420, 77.6905], "max_walk_minutes": 12,
        "min_orr_distance_m": 200, "max_rent": 50000, "score_threshold": 85,
        "bhk": 2, "score_weights": {"peace": 0.4, "llm": 0.6},
        "llm_weights": {"power_backup": 20, "noise": 20, "internet": 15,
            "light_ventilation": 10, "water": 10, "maintenance": 10,
            "wfh_livability": 10, "value": 5}
    }
    (configs_dir / "default.json").write_text(json.dumps(default))
    cfg = load_config("default", configs_dir=configs_dir)

    data_dir = tmp_path / "data" / "runs"
    ctx = create_run(cfg, data_dir=data_dir)
    assert ctx.run_dir.exists()
    assert (ctx.run_dir / "config.json").exists()
    snapshot = json.loads((ctx.run_dir / "config.json").read_text())
    assert snapshot["name"] == "default"
    assert ctx.path("raw.json").parent == ctx.run_dir
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: FAIL — `load_config` not found

- [ ] **Step 3: Create `configs/default.json`**

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

- [ ] **Step 4: Rewrite `src/config.py`**

```python
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv(Path(__file__).parent.parent / ".env")

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_CONFIGS_DIR = PROJECT_ROOT / "configs"
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "runs"

FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

ORR_REFERENCE_POINTS = [
    (12.9352, 77.6830),
    (12.9340, 77.6870),
    (12.9330, 77.6920),
    (12.9310, 77.6960),
    (12.9280, 77.7000),
]


class Config(BaseModel):
    name: str
    target_localities: list[str]
    ptp_coords: tuple[float, float]
    max_walk_minutes: int
    min_orr_distance_m: int
    max_rent: int
    score_threshold: int
    bhk: int
    score_weights: dict[str, float]
    llm_weights: dict[str, int]


@dataclass
class RunContext:
    run_id: str
    run_dir: Path
    config: Config

    def path(self, filename: str) -> Path:
        return self.run_dir / filename


def load_config(profile: str = "default", configs_dir: Path | None = None) -> Config:
    configs_dir = configs_dir or DEFAULT_CONFIGS_DIR
    default_path = configs_dir / "default.json"
    default_data = json.loads(default_path.read_text())

    if profile != "default":
        profile_path = configs_dir / f"{profile}.json"
        profile_data = json.loads(profile_path.read_text())
        merged = {**default_data, **profile_data}
    else:
        merged = default_data

    return Config(**merged)


def create_run(config: Config, data_dir: Path | None = None) -> RunContext:
    data_dir = data_dir or DEFAULT_DATA_DIR
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = data_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.json").write_text(
        json.dumps(config.model_dump(), indent=2)
    )
    return RunContext(run_id=run_id, run_dir=run_dir, config=config)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: all 3 PASS

- [ ] **Step 6: Commit**

```bash
git add configs/default.json src/config.py tests/test_config.py
git commit -m "feat: config profiles with inheritance and run isolation"
```

---

### Task 2: Pydantic Models

**Files:**
- Rewrite: `src/models.py`
- Create: `tests/test_models.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `ListingSummary(BaseModel)` — fields: `property_id`, `title`, `rent`, `deposit`, `maintenance`, `sqft`, `address`, `locality`, `building_name`, `detail_url`, `available_date`, `image_urls`
  - `ListingDetail(BaseModel)` — fields: `property_id`, `furnishing`, `floor`, `power_backup`, `facing`, `bathrooms`, `balconies`, `parking`, `building_age`, `preferred_tenant`, `water_supply`, `gated_security`, `description`
  - `ScoredListing(BaseModel)` — fields: `summary: ListingSummary`, `detail: ListingDetail`, `lat`, `lon`, `walk_minutes`, `orr_distance_m`, `peace_score`, `llm_score`, `llm_reasoning`, `final_score`, `disqualified`, `disqualify_reason`

- [ ] **Step 1: Write failing test**

```python
# tests/test_models.py
import json

def test_listing_summary_roundtrip():
    from src.models import ListingSummary
    data = {
        "property_id": "abc123",
        "title": "2 BHK in SLS Signature",
        "rent": 35000,
        "deposit": 200000,
        "maintenance": 4200,
        "sqft": 1210,
        "address": "Kaverappa Layout, Kadubeesanahalli",
        "locality": "kadubeesanahalli",
        "building_name": "SLS Signature",
        "detail_url": "https://www.nobroker.in/property/rent/bangalore/abc123/detail",
        "available_date": "2026-07-01",
        "image_urls": ["https://img.nobroker.in/1.jpg"]
    }
    s = ListingSummary(**data)
    assert s.property_id == "abc123"
    assert s.rent == 35000
    dumped = json.loads(s.model_dump_json())
    assert dumped["property_id"] == "abc123"


def test_listing_detail_optional_fields():
    from src.models import ListingDetail
    d = ListingDetail(
        property_id="abc123",
        furnishing="Semi",
        floor="3/4",
        power_backup=None,
        description="Nice flat",
    )
    assert d.power_backup is None
    assert d.bathrooms is None
    assert d.gated_security is None


def test_scored_listing_composition():
    from src.models import ListingSummary, ListingDetail, ScoredListing
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
        peace_score=75.0, llm_score=82.0, llm_reasoning="Good backup",
        final_score=79.2, disqualified=False, disqualify_reason=None
    )
    assert scored.summary.rent == 30000
    assert scored.detail.power_backup == "Full"
    assert scored.disqualified is False
    d = scored.model_dump()
    assert d["summary"]["property_id"] == "abc123"
    assert d["detail"]["furnishing"] == "Fully"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_models.py -v`
Expected: FAIL — old models don't match spec

- [ ] **Step 3: Rewrite `src/models.py`**

```python
from pydantic import BaseModel


class ListingSummary(BaseModel):
    property_id: str
    title: str
    rent: int
    deposit: int
    maintenance: int | None = None
    sqft: int
    address: str
    locality: str
    building_name: str | None = None
    detail_url: str
    available_date: str | None = None
    image_urls: list[str] = []


class ListingDetail(BaseModel):
    property_id: str
    furnishing: str
    floor: str
    power_backup: str | None = None
    facing: str | None = None
    bathrooms: int | None = None
    balconies: int | None = None
    parking: str | None = None
    building_age: str | None = None
    preferred_tenant: str | None = None
    water_supply: str | None = None
    gated_security: bool | None = None
    description: str


class ScoredListing(BaseModel):
    summary: ListingSummary
    detail: ListingDetail
    lat: float
    lon: float
    walk_minutes: float
    orr_distance_m: float
    peace_score: float
    llm_score: float
    llm_reasoning: str
    final_score: float
    disqualified: bool
    disqualify_reason: str | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_models.py -v`
Expected: all 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/models.py tests/test_models.py
git commit -m "feat: pydantic models with composition for scored listings"
```

---

### Task 3: SQLite Dedup

**Files:**
- Create: `src/db.py`
- Create: `tests/test_db.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `Dedup(db_path: Path)` — context manager, creates table if needed
  - `Dedup.is_seen(property_id: str) -> bool`
  - `Dedup.mark_seen(property_id: str, score: float | None = None, disqualified: bool = False) -> None`
  - `Dedup.update_score(property_id: str, score: float, disqualified: bool) -> None`

- [ ] **Step 1: Write failing test**

```python
# tests/test_db.py
from pathlib import Path

def test_dedup_new_listing(tmp_path):
    from src.db import Dedup
    db = Dedup(tmp_path / "test.db")
    assert not db.is_seen("prop_001")
    db.mark_seen("prop_001")
    assert db.is_seen("prop_001")


def test_dedup_update_score(tmp_path):
    from src.db import Dedup
    db = Dedup(tmp_path / "test.db")
    db.mark_seen("prop_002")
    db.update_score("prop_002", score=88.5, disqualified=False)
    db2 = Dedup(tmp_path / "test.db")
    assert db2.is_seen("prop_002")


def test_dedup_persists_across_instances(tmp_path):
    from src.db import Dedup
    db_path = tmp_path / "test.db"
    db1 = Dedup(db_path)
    db1.mark_seen("prop_003")
    del db1
    db2 = Dedup(db_path)
    assert db2.is_seen("prop_003")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_db.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Create `src/db.py`**

```python
import sqlite3
from datetime import datetime
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).parent.parent / "listings.db"


class Dedup:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS seen (
                property_id TEXT PRIMARY KEY,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                score REAL,
                disqualified BOOLEAN DEFAULT 0
            )
        """)
        self.conn.commit()

    def is_seen(self, property_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM seen WHERE property_id = ?", (property_id,)
        ).fetchone()
        return row is not None

    def mark_seen(self, property_id: str, score: float | None = None, disqualified: bool = False) -> None:
        now = datetime.now().isoformat()
        self.conn.execute(
            """INSERT INTO seen (property_id, first_seen, last_seen, score, disqualified)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(property_id) DO UPDATE SET last_seen = ?""",
            (property_id, now, now, score, disqualified, now)
        )
        self.conn.commit()

    def update_score(self, property_id: str, score: float, disqualified: bool) -> None:
        self.conn.execute(
            "UPDATE seen SET score = ?, disqualified = ?, last_seen = ? WHERE property_id = ?",
            (score, disqualified, datetime.now().isoformat(), property_id)
        )
        self.conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_db.py -v`
Expected: all 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/db.py tests/test_db.py
git commit -m "feat: SQLite dedup for tracking seen listings"
```

---

### Task 4: Scraper — Two-Phase NoBroker Scraping

**Files:**
- Rewrite: `src/scraper.py`
- Create: `tests/test_scraper.py`

**Interfaces:**
- Consumes: `Config` from `src/config.py`, `RunContext` from `src/config.py`, `ListingSummary` and `ListingDetail` from `src/models.py`, `Dedup` from `src/db.py`
- Produces:
  - `scrape_seo_page(locality: str, api_key: str) -> str` — returns markdown from Firecrawl
  - `parse_listings_from_markdown(md: str, source_locality: str) -> list[ListingSummary]` — extracts listing summaries
  - `scrape_detail_page(url: str, api_key: str) -> str` — returns detail page markdown
  - `parse_detail_from_markdown(md: str, property_id: str) -> ListingDetail` — extracts detail fields
  - `run_scrape(ctx: RunContext) -> Path` — full scrape: SEO pages → basic filter → dedup → detail pages → save `raw.json`

- [ ] **Step 1: Write failing test for markdown parsing**

```python
# tests/test_scraper.py
SAMPLE_SEO_MARKDOWN = """
# 2 BHK Flats for Rent in Kadubeesanahalli

## [2 BHK Flat In Sls Signature for Rent In Kadubeesanahalli](https://www.nobroker.in/property/rent/bangalore/Kadubeesanahalli/2-bhk-flat-sls-signature-abc123/detail)

₹50,000

₹4,200 Maintenance

₹2,00,000 Deposit

1,210 sqft

Kaverappa Layout, Kadubeesanahalli, Panathur, Bengaluru

Available from 2026-06-25

![image](https://img.nobroker.in/1.jpg)

## [2 BHK In Chourasia Manor](https://www.nobroker.in/property/rent/bangalore/Bellandur/2-bhk-chourasia-def456/detail)

₹35,000

₹3,000 Maintenance

₹1,50,000 Deposit

1,050 sqft

Gear Road, Bhoganhalli, Bengaluru
"""

SAMPLE_DETAIL_MARKDOWN = """
# 2 BHK Flat In Sls Signature for Rent

₹50,000 / month

## Property Details

| Feature | Value |
|---------|-------|
| Furnishing | Semi |
| Facing | West |
| Floor | 3 / 4 |
| Bathrooms | 2 |
| Balconies | 1 |
| Parking | Bike |
| Age of Building | 1-3 Years |
| Preferred Tenant | Family |
| Water Supply | Borewell |
| Gated Security | No |
| Power Backup | Full |

## Description

Spacious 2 BHK with good ventilation. 24x7 power backup with generator. Near Prestige Tech Park.
Close to metro station. ACT fibernet available.
"""


def test_parse_seo_listings():
    from src.scraper import parse_listings_from_markdown
    listings = parse_listings_from_markdown(SAMPLE_SEO_MARKDOWN, "kadubeesanahalli")
    assert len(listings) == 2
    first = listings[0]
    assert first.property_id == "abc123"
    assert first.rent == 50000
    assert first.maintenance == 4200
    assert first.deposit == 200000
    assert first.sqft == 1210
    assert "Kaverappa" in first.address
    assert first.locality == "kadubeesanahalli"
    assert "detail" in first.detail_url
    second = listings[1]
    assert second.rent == 35000
    assert second.property_id == "def456"


def test_parse_detail():
    from src.scraper import parse_detail_from_markdown
    detail = parse_detail_from_markdown(SAMPLE_DETAIL_MARKDOWN, "abc123")
    assert detail.property_id == "abc123"
    assert detail.furnishing == "Semi"
    assert detail.power_backup == "Full"
    assert detail.floor == "3 / 4"
    assert detail.bathrooms == 2
    assert detail.water_supply == "Borewell"
    assert detail.gated_security is False
    assert "power backup" in detail.description.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_scraper.py -v`
Expected: FAIL — new function signatures don't exist

- [ ] **Step 3: Rewrite `src/scraper.py`**

```python
import json
import re
import time
from pathlib import Path

import httpx

from .config import FIRECRAWL_API_KEY, RunContext
from .db import Dedup
from .models import ListingDetail, ListingSummary

FIRECRAWL_URL = "https://api.firecrawl.dev/v1/scrape"
SEO_URL_TEMPLATE = "https://www.nobroker.in/2bhk-flats-for-rent-in-{locality}_bangalore"


def _firecrawl_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def scrape_seo_page(locality: str, api_key: str = "") -> str:
    api_key = api_key or FIRECRAWL_API_KEY
    url = SEO_URL_TEMPLATE.format(locality=locality)
    resp = httpx.post(
        FIRECRAWL_URL,
        headers=_firecrawl_headers(api_key),
        json={"url": url, "formats": ["markdown"], "waitFor": 5000},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"Firecrawl failed for {url}: {data}")
    return data["data"]["markdown"]


def _extract_property_id(url: str) -> str:
    parts = url.rstrip("/").split("/")
    if parts[-1] == "detail":
        return parts[-2].split("-")[-1]
    return parts[-1].split("-")[-1]


def _extract_amount(text: str, pattern: str) -> int:
    match = re.search(pattern, text)
    if not match:
        return 0
    raw = match.group(1) if match.group(1) else "0"
    return int(raw.replace(",", "")) if raw else 0


def parse_listings_from_markdown(md: str, source_locality: str) -> list[ListingSummary]:
    listings = []
    blocks = re.split(r"##\s+\[", md)
    for block in blocks[1:]:
        try:
            title_match = re.match(
                r"(.+?)\]\((https://www\.nobroker\.in/property/[^\)]+)\)", block
            )
            if not title_match:
                continue
            title = title_match.group(1).strip()
            url = title_match.group(2).strip()
            property_id = _extract_property_id(url)
            rent = _extract_amount(block, r"₹\s*([\d,]+)")
            maintenance = _extract_amount(block, r"₹\s*([\d,]+)\s*Maintenance")
            deposit = _extract_amount(block, r"₹\s*([\d,]+)\s*Deposit")
            sqft = _extract_amount(block, r"([\d,]+)\s*sqft")

            address_match = re.search(
                r"(?:Layout|Road|Rd|Cross|Main|Near|Opp|Gear|Sector)[^\n₹]{5,150}",
                block,
            )
            address = address_match.group(0).strip() if address_match else ""

            date_match = re.search(r"(\d{4}-\d{2}-\d{2})", block)
            available_date = date_match.group(1) if date_match else None

            image_urls = re.findall(r"!\[.*?\]\((https://[^\)]+)\)", block)

            listings.append(
                ListingSummary(
                    property_id=property_id,
                    title=title,
                    rent=rent,
                    deposit=deposit,
                    maintenance=maintenance if maintenance else None,
                    sqft=sqft,
                    address=address,
                    locality=source_locality,
                    building_name=None,
                    detail_url=url,
                    available_date=available_date,
                    image_urls=image_urls,
                )
            )
        except Exception:
            continue
    return listings


def scrape_detail_page(url: str, api_key: str = "") -> str:
    api_key = api_key or FIRECRAWL_API_KEY
    resp = httpx.post(
        FIRECRAWL_URL,
        headers=_firecrawl_headers(api_key),
        json={"url": url, "formats": ["markdown"], "waitFor": 5000},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"Firecrawl failed for {url}: {data}")
    return data["data"]["markdown"]


def _extract_table_value(md: str, key: str) -> str | None:
    pattern = rf"\|\s*{re.escape(key)}\s*\|\s*(.+?)\s*\|"
    match = re.search(pattern, md, re.IGNORECASE)
    return match.group(1).strip() if match else None


def parse_detail_from_markdown(md: str, property_id: str) -> ListingDetail:
    furnishing = _extract_table_value(md, "Furnishing") or ""
    floor = _extract_table_value(md, "Floor") or ""
    power_backup = _extract_table_value(md, "Power Backup")
    facing = _extract_table_value(md, "Facing")
    parking = _extract_table_value(md, "Parking")
    building_age = _extract_table_value(md, "Age of Building")
    preferred_tenant = _extract_table_value(md, "Preferred Tenant")
    water_supply = _extract_table_value(md, "Water Supply")

    bathrooms_str = _extract_table_value(md, "Bathrooms")
    bathrooms = int(bathrooms_str) if bathrooms_str and bathrooms_str.isdigit() else None

    balconies_str = _extract_table_value(md, "Balconies")
    balconies = int(balconies_str) if balconies_str and balconies_str.isdigit() else None

    security_str = _extract_table_value(md, "Gated Security")
    gated_security = security_str.lower() == "yes" if security_str else None

    desc_match = re.search(r"##\s*Description\s*\n([\s\S]+?)(?=\n##|\Z)", md)
    description = desc_match.group(1).strip() if desc_match else ""

    return ListingDetail(
        property_id=property_id,
        furnishing=furnishing,
        floor=floor,
        power_backup=power_backup,
        facing=facing,
        bathrooms=bathrooms,
        balconies=balconies,
        parking=parking,
        building_age=building_age,
        preferred_tenant=preferred_tenant,
        water_supply=water_supply,
        gated_security=gated_security,
        description=description,
    )


def run_scrape(ctx: RunContext) -> Path:
    config = ctx.config
    dedup = Dedup()
    all_summaries: list[ListingSummary] = []
    seen_ids: set[str] = set()

    for locality in config.target_localities:
        print(f"Scraping {locality}...")
        try:
            md = scrape_seo_page(locality)
            listings = parse_listings_from_markdown(md, locality)
            for ls in listings:
                if ls.property_id in seen_ids or dedup.is_seen(ls.property_id):
                    continue
                if ls.rent > config.max_rent:
                    continue
                seen_ids.add(ls.property_id)
                all_summaries.append(ls)
            print(f"  {len(listings)} found, {len(seen_ids)} unique passing filters")
            time.sleep(2)
        except Exception as e:
            print(f"  Error: {e}")

    results = []
    for i, summary in enumerate(all_summaries):
        print(f"[{i + 1}/{len(all_summaries)}] Detail: {summary.title[:50]}...")
        try:
            md = scrape_detail_page(summary.detail_url)
            detail = parse_detail_from_markdown(md, summary.property_id)
            dedup.mark_seen(summary.property_id)
            results.append({"summary": summary.model_dump(), "detail": detail.model_dump()})
            time.sleep(2)
        except Exception as e:
            print(f"  Detail scrape failed: {e}")
            results.append({"summary": summary.model_dump(), "detail": None})

    out_path = ctx.path("raw.json")
    out_path.write_text(json.dumps(results, indent=2))
    print(f"Saved {len(results)} listings to {out_path}")
    return out_path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_scraper.py -v`
Expected: both parsing tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/scraper.py tests/test_scraper.py
git commit -m "feat: two-phase NoBroker scraper with dedup and detail parsing"
```

---

### Task 5: Spatial Filter with Peace Score

**Files:**
- Rewrite: `src/spatial.py`
- Create: `tests/test_spatial.py`

**Interfaces:**
- Consumes: `Config`, `RunContext` from `src/config.py`, `ListingSummary`, `ListingDetail` from `src/models.py`, `ORR_REFERENCE_POINTS` from `src/config.py`
- Produces:
  - `geocode_address(address: str, locality: str, api_key: str) -> tuple[float, float] | None`
  - `get_walk_duration(lat: float, lon: float, ptp_coords: tuple[float, float], api_key: str) -> float | None` — minutes
  - `haversine_meters(lat1, lon1, lat2, lon2) -> float`
  - `min_orr_distance(lat: float, lon: float) -> float` — meters
  - `compute_peace_score(orr_distance_m: float, locality: str) -> float` — 0-100
  - `run_filter(ctx: RunContext) -> Path` — reads `raw.json`, filters, writes `filtered.json`

- [ ] **Step 1: Write failing test**

```python
# tests/test_spatial.py
import math

def test_haversine_known_distance():
    from src.spatial import haversine_meters
    # PTP to a point ~500m away
    d = haversine_meters(12.9420, 77.6905, 12.9420, 77.6955)
    assert 400 < d < 600


def test_min_orr_distance():
    from src.spatial import min_orr_distance
    # Point right on ORR reference
    d = min_orr_distance(12.9352, 77.6830)
    assert d < 10


def test_peace_score_close_to_orr():
    from src.spatial import compute_peace_score
    score = compute_peace_score(150, "bellandur")
    assert score == 0  # < 200m = disqualified, score 0


def test_peace_score_far_from_orr():
    from src.spatial import compute_peace_score
    score = compute_peace_score(500, "kadubeesanahalli")
    assert score >= 70  # far + priority locality


def test_peace_score_mid_range():
    from src.spatial import compute_peace_score
    score = compute_peace_score(300, "panathur")
    assert 20 < score < 70
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_spatial.py -v`
Expected: FAIL — `compute_peace_score` not found

- [ ] **Step 3: Rewrite `src/spatial.py`**

```python
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


def run_filter(ctx: RunContext) -> Path:
    config = ctx.config
    raw_path = ctx.path("raw.json")
    raw_data = json.loads(raw_path.read_text())
    passed = []

    for i, entry in enumerate(raw_data):
        summary = entry["summary"]
        detail = entry.get("detail")
        title = summary["title"][:50]
        print(f"[{i + 1}/{len(raw_data)}] Filtering: {title}...")

        coords = geocode_address(summary["address"] or title, summary["locality"])
        if not coords:
            print("  Skipped: geocoding failed")
            continue

        lat, lon = coords
        walk = get_walk_duration(lat, lon, config.ptp_coords)
        if walk is None:
            print("  Skipped: walk duration unavailable")
            continue
        if walk > config.max_walk_minutes:
            print(f"  Skipped: {walk:.1f}min walk (max {config.max_walk_minutes})")
            continue

        orr_dist = min_orr_distance(lat, lon)
        if orr_dist < config.min_orr_distance_m:
            print(f"  Skipped: {orr_dist:.0f}m from ORR (min {config.min_orr_distance_m})")
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
        print(f"  PASSED: {walk:.1f}min, {orr_dist:.0f}m ORR, peace={peace:.0f}")

    out_path = ctx.path("filtered.json")
    out_path.write_text(json.dumps(passed, indent=2))
    print(f"Saved {len(passed)}/{len(raw_data)} listings to {out_path}")
    return out_path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_spatial.py -v`
Expected: all 5 PASS

- [ ] **Step 5: Commit**

```bash
git add src/spatial.py tests/test_spatial.py
git commit -m "feat: spatial filter with peace score and ORR distance"
```

---

### Task 6: LLM Scorer with 8-Criteria Weighted Prompt

**Files:**
- Rewrite: `src/scorer.py`
- Create: `tests/test_scorer.py`

**Interfaces:**
- Consumes: `Config`, `RunContext` from `src/config.py`, `ListingSummary`, `ListingDetail`, `ScoredListing` from `src/models.py`, `Dedup` from `src/db.py`
- Produces:
  - `build_judge_prompt(summary: dict, detail: dict, walk_minutes: float, orr_distance_m: float, llm_weights: dict[str, int]) -> str`
  - `score_listing(summary: dict, detail: dict, spatial: dict, llm_weights: dict[str, int]) -> dict` — returns `{score, reasoning, disqualified, disqualify_reason}`
  - `run_score(ctx: RunContext) -> Path` — reads `filtered.json`, scores, writes `scored.json`

- [ ] **Step 1: Write failing test for prompt building**

```python
# tests/test_scorer.py
import json

def test_build_judge_prompt():
    from src.scorer import build_judge_prompt
    weights = {
        "power_backup": 20, "noise": 20, "internet": 15,
        "light_ventilation": 10, "water": 10, "maintenance": 10,
        "wfh_livability": 10, "value": 5
    }
    prompt = build_judge_prompt(
        summary={"title": "2BHK Test", "rent": 30000, "address": "Test Rd", "sqft": 1000},
        detail={"furnishing": "Semi", "power_backup": "Full", "floor": "3/4",
                "water_supply": "Borewell", "gated_security": True, "description": "Nice flat"},
        walk_minutes=8.5,
        orr_distance_m=350,
        llm_weights=weights,
    )
    assert "20 points" in prompt  # power_backup weight
    assert "15 points" in prompt  # internet weight
    assert "₹30,000" in prompt or "30000" in prompt
    assert "Semi" in prompt
    assert "Full" in prompt  # power backup value
    assert "HARD REQUIREMENT" in prompt
    assert "disqualified" in prompt.lower() or "disqualify" in prompt.lower()


def test_prompt_includes_all_criteria():
    from src.scorer import build_judge_prompt
    weights = {
        "power_backup": 20, "noise": 20, "internet": 15,
        "light_ventilation": 10, "water": 10, "maintenance": 10,
        "wfh_livability": 10, "value": 5
    }
    prompt = build_judge_prompt(
        summary={"title": "Test", "rent": 40000, "address": "Addr", "sqft": 1200},
        detail={"furnishing": "Fully", "power_backup": None, "floor": "2/5",
                "water_supply": "Corporation", "gated_security": False, "description": "Flat"},
        walk_minutes=10, orr_distance_m=500, llm_weights=weights,
    )
    for criterion in ["power_backup", "noise", "internet", "water", "maintenance"]:
        assert criterion.replace("_", " ") in prompt.lower() or criterion in prompt.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_scorer.py -v`
Expected: FAIL — `build_judge_prompt` not found

- [ ] **Step 3: Rewrite `src/scorer.py`**

```python
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
            emoji = "🚫" if item.disqualified else "✓"
            print(f"  {emoji} Score: {final:.1f} (LLM:{llm} Peace:{peace:.0f})")
        except Exception as e:
            print(f"  Error: {e}")

    out_path = ctx.path("scored.json")
    out_path.write_text(json.dumps(scored, indent=2))
    print(f"Saved {len(scored)} scored listings to {out_path}")
    return out_path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_scorer.py -v`
Expected: both PASS

- [ ] **Step 5: Commit**

```bash
git add src/scorer.py tests/test_scorer.py
git commit -m "feat: LLM scorer with 8-criteria weighted prompt and disqualify logic"
```

---

### Task 7: Reporter + Compare

**Files:**
- Rewrite: `src/reporter.py`
- Create: `tests/test_reporter.py`

**Interfaces:**
- Consumes: `Config`, `RunContext` from `src/config.py`, `ScoredListing` from `src/models.py`
- Produces:
  - `generate_report(ctx: RunContext) -> str` — reads `scored.json`, writes `report.md`, returns markdown
  - `compare_runs(run_dir_a: Path, run_dir_b: Path) -> str` — diffs two runs, returns markdown

- [ ] **Step 1: Write failing test**

```python
# tests/test_reporter.py
import json
from pathlib import Path

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
        "peace_score": 70.0, "llm_score": 88.0, "llm_reasoning": "Good backup, quiet area",
        "final_score": 80.8, "disqualified": False, "disqualify_reason": None,
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
        "peace_score": 35.0, "llm_score": 40.0, "llm_reasoning": "No backup mentioned",
        "final_score": 38.0, "disqualified": True, "disqualify_reason": "No power backup",
    },
]


def test_generate_report(tmp_path):
    from src.reporter import generate_report
    from src.config import Config, RunContext

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

    report = generate_report(ctx)
    assert "Great Flat" in report
    assert "#1" in report
    assert "80.8" in report
    assert (run_dir / "report.md").exists()


def test_compare_runs(tmp_path):
    from src.reporter import compare_runs
    import json

    run_a = tmp_path / "run_a"
    run_b = tmp_path / "run_b"
    run_a.mkdir()
    run_b.mkdir()
    (run_a / "config.json").write_text(json.dumps({"name": "default", "min_orr_distance_m": 200}))
    (run_b / "config.json").write_text(json.dumps({"name": "peaceful", "min_orr_distance_m": 300}))
    (run_a / "scored.json").write_text(json.dumps(SCORED_FIXTURE))
    (run_b / "scored.json").write_text(json.dumps([SCORED_FIXTURE[0]]))

    diff = compare_runs(run_a, run_b)
    assert "a1" in diff  # shared listing
    assert "b2" in diff  # only in run A
    assert "config" in diff.lower() or "min_orr" in diff.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_reporter.py -v`
Expected: FAIL — new signatures don't exist

- [ ] **Step 3: Rewrite `src/reporter.py`**

```python
import json
from pathlib import Path

from .config import RunContext


def generate_report(ctx: RunContext) -> str:
    config = ctx.config
    scored_path = ctx.path("scored.json")
    entries = json.loads(scored_path.read_text())
    entries.sort(key=lambda x: x["final_score"], reverse=True)

    threshold = config.score_threshold
    above = sum(1 for e in entries if e["final_score"] >= threshold and not e["disqualified"])

    lines = [
        f"# House Hunt Report — {ctx.run_id}",
        f"\n**Config:** {config.name} | **Scored:** {len(entries)} | **Above {threshold}:** {above}\n",
        "---\n",
    ]

    for rank, e in enumerate(entries, 1):
        s = e["summary"]
        d = e.get("detail") or {}
        disq = "🚫 DISQUALIFIED" if e["disqualified"] else ""
        act = "🔥 ACT NOW" if e["final_score"] >= threshold and not e["disqualified"] else ""
        tag = disq or act

        lines.append(f"## #{rank} {s['title']} {tag}")
        lines.append(f"**Score: {e['final_score']}** (LLM: {e['llm_score']} | Peace: {e['peace_score']})\n")
        if e["disqualified"]:
            lines.append(f"**Disqualified:** {e['disqualify_reason']}\n")
        lines.append("| Field | Value |")
        lines.append("|-------|-------|")
        lines.append(f"| Rent | ₹{s['rent']:,} + ₹{s.get('maintenance') or 0:,} maintenance |")
        lines.append(f"| Deposit | ₹{s['deposit']:,} |")
        lines.append(f"| Area | {s['sqft']} sqft |")
        lines.append(f"| Walk to PTP | {e['walk_minutes']} min |")
        lines.append(f"| ORR Distance | {e['orr_distance_m']}m |")
        lines.append(f"| Furnishing | {d.get('furnishing') or 'Unknown'} |")
        lines.append(f"| Floor | {d.get('floor') or 'Unknown'} |")
        lines.append(f"| Power Backup | {d.get('power_backup') or 'Unknown'} |")
        lines.append(f"| Water Supply | {d.get('water_supply') or 'Unknown'} |")
        lines.append(f"| Gated Security | {d.get('gated_security', 'Unknown')} |")
        lines.append(f"\n**Assessment:** {e['llm_reasoning']}\n")
        lines.append(f"**Link:** [{s['detail_url']}]({s['detail_url']})\n")
        lines.append("---\n")

    report = "\n".join(lines)
    ctx.path("report.md").write_text(report)
    print(report)
    return report


def compare_runs(run_dir_a: Path, run_dir_b: Path) -> str:
    config_a = json.loads((run_dir_a / "config.json").read_text())
    config_b = json.loads((run_dir_b / "config.json").read_text())
    scored_a = json.loads((run_dir_a / "scored.json").read_text())
    scored_b = json.loads((run_dir_b / "scored.json").read_text())

    ids_a = {e["summary"]["property_id"]: e for e in scored_a}
    ids_b = {e["summary"]["property_id"]: e for e in scored_b}
    shared = set(ids_a) & set(ids_b)
    only_a = set(ids_a) - set(ids_b)
    only_b = set(ids_b) - set(ids_a)

    lines = [
        f"# Run Comparison: {run_dir_a.name} vs {run_dir_b.name}\n",
    ]

    # Config diff
    config_diffs = []
    all_keys = set(config_a) | set(config_b)
    for k in sorted(all_keys):
        va, vb = config_a.get(k), config_b.get(k)
        if va != vb:
            config_diffs.append(f"| {k} | {va} | {vb} |")
    if config_diffs:
        lines.append("## Config Differences\n")
        lines.append("| Key | Run A | Run B |")
        lines.append("|-----|-------|-------|")
        lines.extend(config_diffs)
        lines.append("")

    # Shared listings
    if shared:
        lines.append(f"## Shared Listings ({len(shared)})\n")
        lines.append("| ID | Title | Score A | Score B | Delta |")
        lines.append("|----|-------|---------|---------|-------|")
        for pid in sorted(shared):
            ea, eb = ids_a[pid], ids_b[pid]
            delta = eb["final_score"] - ea["final_score"]
            sign = "+" if delta > 0 else ""
            lines.append(
                f"| {pid} | {ea['summary']['title'][:40]} | {ea['final_score']} | {eb['final_score']} | {sign}{delta:.1f} |"
            )
        lines.append("")

    if only_a:
        lines.append(f"## Only in Run A ({len(only_a)})\n")
        for pid in sorted(only_a):
            e = ids_a[pid]
            lines.append(f"- **{e['summary']['title']}** (score: {e['final_score']})")
        lines.append("")

    if only_b:
        lines.append(f"## Only in Run B ({len(only_b)})\n")
        for pid in sorted(only_b):
            e = ids_b[pid]
            lines.append(f"- **{e['summary']['title']}** (score: {e['final_score']})")
        lines.append("")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_reporter.py -v`
Expected: both PASS

- [ ] **Step 5: Commit**

```bash
git add src/reporter.py tests/test_reporter.py
git commit -m "feat: reporter with run-aware output and run comparison"
```

---

### Task 8: Skills + pyproject.toml + CLAUDE.md

**Files:**
- Rewrite: `.claude/skills/scrape/SKILL.md`
- Rewrite: `.claude/skills/filter/SKILL.md`
- Rewrite: `.claude/skills/score/SKILL.md`
- Rewrite: `.claude/skills/report/SKILL.md`
- Rewrite: `.claude/skills/hunt/SKILL.md`
- Create: `.claude/skills/compare/SKILL.md`
- Rewrite: `pyproject.toml`
- Rewrite: `CLAUDE.md`
- Delete: `src/__init__.py` (if empty/unused — check first)

**Interfaces:**
- Consumes: all `src/` modules
- Produces: working `/scrape`, `/filter`, `/score`, `/report`, `/hunt`, `/compare` skills

- [ ] **Step 1: Rewrite all skills**

`.claude/skills/scrape/SKILL.md`:
```markdown
---
name: scrape
description: Scrape 2BHK rental listings from NoBroker for all target localities near Prestige Tech Park. Use when the user says "scrape", "fetch listings", "get new listings", "pull from NoBroker", or wants fresh property data.
---

# Scrape NoBroker Listings

## What it does

Two-phase scrape via Firecrawl cloud API:
1. SEO listing pages for target localities → listing summaries
2. Detail pages for new listings passing rent filter → full listing data
3. SQLite dedup skips already-seen property IDs

## How to run

```bash
cd /Users/sarath.m/Documents/github/house_hunt
.venv/bin/python -c "
from src.config import load_config, create_run
from src.scraper import run_scrape
import sys

profile = sys.argv[1] if len(sys.argv) > 1 else 'default'
cfg = load_config(profile)
ctx = create_run(cfg)
print(f'Run: {ctx.run_id} (config: {cfg.name})')
run_scrape(ctx)
" ${CONFIG:-default}
```

## After scraping

Report listing count per locality and total unique. Suggest `/filter` next (needs GOOGLE_MAPS_API_KEY), or `/score` to skip spatial filtering.
```

`.claude/skills/filter/SKILL.md`:
```markdown
---
name: filter
description: Spatially filter scraped NoBroker listings — geocode, walk distance to PTP (max 12 min), ORR distance (min 200m). Use when the user says "filter", "spatial filter", "check distances", or wants to narrow by location. Requires GOOGLE_MAPS_API_KEY.
---

# Spatial Filter

## What it does

1. Geocodes each listing address → lat/lon
2. Walking distance to PTP main gate (≤ max_walk_minutes from config)
3. Haversine distance from ORR (≥ min_orr_distance_m from config)
4. Computes peace score (0-100)

## How to run

Requires a run_id from a previous `/scrape`. Find latest:
```bash
ls -t data/runs/ | head -1
```

Then run:
```bash
cd /Users/sarath.m/Documents/github/house_hunt
.venv/bin/python -c "
from src.config import load_config, RunContext
from src.spatial import run_filter
from pathlib import Path
import json, sys

run_id = sys.argv[1]
run_dir = Path('data/runs') / run_id
cfg_data = json.loads((run_dir / 'config.json').read_text())
from src.config import Config
cfg = Config(**cfg_data)
ctx = RunContext(run_id=run_id, run_dir=run_dir, config=cfg)
run_filter(ctx)
" ${RUN_ID}
```

## After filtering

Report passed vs dropped count with reasons. Suggest `/score` next.
```

`.claude/skills/score/SKILL.md`:
```markdown
---
name: score
description: Score filtered listings using Claude Sonnet as LLM judge — evaluates power backup (hard req), noise, internet, water, maintenance, WFH livability. Use when the user says "score", "evaluate", "judge", or wants AI assessment.
---

# LLM Scoring

## What it does

1. Sends each listing to Claude Sonnet with 8-criteria weighted prompt
2. Hard disqualify if no 100% power backup
3. Computes final_score = peace_weight * peace_score + llm_weight * llm_score

## How to run

Requires a run_id with `filtered.json`. Then:
```bash
cd /Users/sarath.m/Documents/github/house_hunt
.venv/bin/python -c "
from src.config import Config, RunContext
from src.scorer import run_score
from pathlib import Path
import json, sys

run_id = sys.argv[1]
run_dir = Path('data/runs') / run_id
cfg = Config(**json.loads((run_dir / 'config.json').read_text()))
ctx = RunContext(run_id=run_id, run_dir=run_dir, config=cfg)
run_score(ctx)
" ${RUN_ID}
```

Requires `ANTHROPIC_API_KEY` env var.

## After scoring

Report scores. Suggest `/report` to see ranked output.
```

`.claude/skills/report/SKILL.md`:
```markdown
---
name: report
description: Generate ranked report of scored listings with scores, details, and NoBroker links. Use when the user says "report", "show results", "top listings", "rank them", or wants final output.
---

# Report Generator

## How to run

```bash
cd /Users/sarath.m/Documents/github/house_hunt
.venv/bin/python -c "
from src.config import Config, RunContext
from src.reporter import generate_report
from pathlib import Path
import json, sys

run_id = sys.argv[1]
run_dir = Path('data/runs') / run_id
cfg = Config(**json.loads((run_dir / 'config.json').read_text()))
ctx = RunContext(run_id=run_id, run_dir=run_dir, config=cfg)
generate_report(ctx)
" ${RUN_ID}
```

## After reporting

Present ranked results. Highlight any score ≥ threshold. Offer to open top picks in browser.
```

`.claude/skills/hunt/SKILL.md`:
```markdown
---
name: hunt
description: Full house hunting pipeline — scrape → filter → score → report. Use when the user says "hunt", "find apartments", "run the pipeline", "full search", or wants complete end-to-end workflow.
---

# Full Hunt Pipeline

Runs all stages in sequence. Skips spatial filter if GOOGLE_MAPS_API_KEY not set.

## How to run

```bash
cd /Users/sarath.m/Documents/github/house_hunt
.venv/bin/python -c "
from src.config import load_config, create_run, GOOGLE_MAPS_API_KEY
from src.scraper import run_scrape
from src.spatial import run_filter
from src.scorer import run_score
from src.reporter import generate_report
import sys

profile = sys.argv[1] if len(sys.argv) > 1 else 'default'
cfg = load_config(profile)
ctx = create_run(cfg)
print(f'=== Hunt started: {ctx.run_id} (config: {cfg.name}) ===')

print('\n--- Stage 1: Scrape ---')
run_scrape(ctx)

if GOOGLE_MAPS_API_KEY:
    print('\n--- Stage 2: Filter ---')
    run_filter(ctx)
else:
    print('\n--- Stage 2: SKIPPED (no GOOGLE_MAPS_API_KEY) ---')
    import shutil, json
    from pathlib import Path
    raw = json.loads(ctx.path('raw.json').read_text())
    for e in raw:
        e.update({'lat': 0, 'lon': 0, 'walk_minutes': 0, 'orr_distance_m': 999, 'peace_score': 50})
    ctx.path('filtered.json').write_text(json.dumps(raw, indent=2))

print('\n--- Stage 3: Score ---')
run_score(ctx)

print('\n--- Stage 4: Report ---')
generate_report(ctx)

print(f'\n=== Done: data/runs/{ctx.run_id}/ ===')
" ${CONFIG:-default}
```

## After the hunt

Present ranked report. Highlight top picks. Offer to compare with previous runs via `/compare`.
```

`.claude/skills/compare/SKILL.md`:
```markdown
---
name: compare
description: Compare two pipeline runs side-by-side — config diff, shared/unique listings, score changes. Use when the user says "compare", "diff runs", "what changed", or wants to evaluate config experiments.
---

# Run Comparison

## How to run

```bash
cd /Users/sarath.m/Documents/github/house_hunt
.venv/bin/python -c "
from src.reporter import compare_runs
from pathlib import Path
import sys

run_a = Path('data/runs') / sys.argv[1]
run_b = Path('data/runs') / sys.argv[2]
print(compare_runs(run_a, run_b))
" ${RUN_A} ${RUN_B}
```

List available runs with: `ls data/runs/`
```

- [ ] **Step 2: Rewrite `pyproject.toml`**

```toml
[project]
name = "house-hunt"
version = "0.1.0"
description = "AI-driven house hunting pipeline for Bangalore rentals near Prestige Tech Park"
requires-python = ">=3.11"
dependencies = [
    "httpx",
    "pydantic>=2.0",
    "python-dotenv",
    "anthropic",
    "googlemaps",
]
```

- [ ] **Step 3: Rewrite `CLAUDE.md`**

```markdown
# House Hunt

AI-driven house hunting pipeline for 2BHK rentals near Prestige Tech Park, Bangalore.

## Skills

- `/scrape` — Scrape NoBroker listings via Firecrawl (pass config name as arg: `/scrape peaceful`)
- `/filter` — Spatial filter via Google Maps (walk to PTP, ORR distance, peace score)
- `/score` — LLM-as-judge evaluation (8 weighted criteria, power backup hard requirement)
- `/report` — Ranked markdown report with scores and links
- `/hunt` — Full pipeline end-to-end (pass config name as arg: `/hunt peaceful`)
- `/compare` — Diff two runs (pass two run IDs as args)

## Setup

```bash
uv venv .venv
uv pip install -e . --python .venv/bin/python
```

## Environment Variables

In `.env`:
- `FIRECRAWL_API_KEY` — required for scraping
- `GOOGLE_MAPS_API_KEY` — required for spatial filter (pipeline skips filter if missing)

Set as env var (not in .env):
- `ANTHROPIC_API_KEY` — required for LLM scoring

## Config Profiles

Configs in `configs/`. Non-default profiles inherit from `default.json`, override only what changes.
Usage: `/hunt peaceful` or `/hunt` for default.

## Data

Each pipeline run creates `data/runs/{YYYYMMDD_HHMMSS}/` with:
- `config.json` — frozen config snapshot
- `raw.json` — scrape output
- `filtered.json` — post-spatial filter
- `scored.json` — LLM scored
- `report.md` — ranked report

No data is ever overwritten. Compare runs with `/compare`.

## Running Python directly

Always use `.venv/bin/python`. All modules in `src/`.
```

- [ ] **Step 4: Install updated deps**

Run: `cd /Users/sarath.m/Documents/github/house_hunt && uv pip install -e . --python .venv/bin/python`
Expected: all deps installed including `httpx`, `googlemaps`

- [ ] **Step 5: Run all tests**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/ pyproject.toml CLAUDE.md
git rm -f src/__init__.py 2>/dev/null; true
git commit -m "feat: update skills for config profiles and run isolation, add /compare"
```

---

### Task 9: Integration Smoke Test

**Files:**
- Create: `tests/test_integration.py`

**Interfaces:**
- Consumes: all modules
- Produces: confidence that the pipeline hangs together

- [ ] **Step 1: Write integration test (mocks external APIs)**

```python
# tests/test_integration.py
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from tests.test_scraper import SAMPLE_SEO_MARKDOWN, SAMPLE_DETAIL_MARKDOWN


def test_full_pipeline_mocked(tmp_path):
    """Smoke test: config → scrape (mocked) → filter (mocked) → score (mocked) → report."""
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    default_config = {
        "name": "default",
        "target_localities": ["kadubeesanahalli"],
        "ptp_coords": [12.9420, 77.6905],
        "max_walk_minutes": 12,
        "min_orr_distance_m": 200,
        "max_rent": 50000,
        "score_threshold": 85,
        "bhk": 2,
        "score_weights": {"peace": 0.4, "llm": 0.6},
        "llm_weights": {
            "power_backup": 20, "noise": 20, "internet": 15,
            "light_ventilation": 10, "water": 10, "maintenance": 10,
            "wfh_livability": 10, "value": 5
        }
    }
    (configs_dir / "default.json").write_text(json.dumps(default_config))

    from src.config import load_config, create_run
    cfg = load_config("default", configs_dir=configs_dir)
    data_dir = tmp_path / "data" / "runs"
    ctx = create_run(cfg, data_dir=data_dir)

    # Mock scrape
    with patch("src.scraper.scrape_seo_page", return_value=SAMPLE_SEO_MARKDOWN), \
         patch("src.scraper.scrape_detail_page", return_value=SAMPLE_DETAIL_MARKDOWN), \
         patch("src.scraper.Dedup") as MockDedup:
        MockDedup.return_value.is_seen.return_value = False
        MockDedup.return_value.mark_seen.return_value = None
        from src.scraper import run_scrape
        run_scrape(ctx)

    raw = json.loads(ctx.path("raw.json").read_text())
    assert len(raw) >= 1
    assert raw[0]["summary"]["property_id"]

    # Mock filter — just copy raw to filtered with spatial fields
    filtered = []
    for entry in raw:
        entry["lat"] = 12.94
        entry["lon"] = 77.69
        entry["walk_minutes"] = 8.0
        entry["orr_distance_m"] = 400
        entry["peace_score"] = 70.0
        filtered.append(entry)
    ctx.path("filtered.json").write_text(json.dumps(filtered, indent=2))

    # Mock LLM scorer
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"score": 82, "reasoning": "Good flat", "disqualified": false, "disqualify_reason": null}')]
    with patch("src.scorer.anthropic.Anthropic") as MockClient, \
         patch("src.scorer.Dedup") as MockDedup2:
        MockClient.return_value.messages.create.return_value = mock_response
        MockDedup2.return_value.update_score.return_value = None
        from src.scorer import run_score
        run_score(ctx)

    scored = json.loads(ctx.path("scored.json").read_text())
    assert len(scored) >= 1
    assert "final_score" in scored[0]

    # Report
    from src.reporter import generate_report
    report = generate_report(ctx)
    assert "House Hunt Report" in report
    assert ctx.path("report.md").exists()
```

- [ ] **Step 2: Run integration test**

Run: `.venv/bin/python -m pytest tests/test_integration.py -v`
Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: integration smoke test for full pipeline"
```

- [ ] **Step 5: Init git repo if needed and commit all**

```bash
cd /Users/sarath.m/Documents/github/house_hunt
git init 2>/dev/null
echo -e "__pycache__/\n*.pyc\n.venv/\n*.egg-info/\nlistings.db\ndata/runs/\n.env" > .gitignore
git add .gitignore
git add -A
git commit -m "feat: house hunt pipeline v1 — scrape, filter, score, report, compare"
```
