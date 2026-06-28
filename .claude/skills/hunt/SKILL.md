---
name: hunt
description: Run the full house hunting pipeline end-to-end — scrape NoBroker listings, spatially filter via Google Maps, score with LLM judge, and generate ranked report. Use when the user says "hunt", "find apartments", "run the pipeline", "search for houses", "full search", or wants the complete automated house hunting workflow in one shot.
---

# Full Hunt Pipeline

Run the entire house hunting pipeline: scrape → filter → score → report.

## What it does

1. **Scrape** — Fetch 2BHK listings from NoBroker for all target localities
2. **Filter** — Geocode + walking distance to PTP + ORR distance check (skip if no GOOGLE_MAPS_API_KEY)
3. **Score** — LLM judge evaluates power backup, noise, maintenance
4. **Report** — Ranked markdown output of all scored listings

## How to run

```bash
cd /Users/sarath.m/Documents/github/house_hunt
.venv/bin/python -c "
from src.scraper import run as scrape
from src.spatial import run as spatial_filter
from src.scorer import run as score
from src.reporter import run as report

raw_path = scrape()
if raw_path:
    # Skip spatial filter if no Google Maps key configured
    from src.config import GOOGLE_MAPS_API_KEY
    if GOOGLE_MAPS_API_KEY:
        filtered_path = spatial_filter(raw_path)
        input_path = filtered_path or raw_path
    else:
        print('No GOOGLE_MAPS_API_KEY — skipping spatial filter')
        input_path = raw_path
    scored_path = score(input_path)
    if scored_path:
        report(scored_path)
"
```

## Prerequisites

- `.env` with `FIRECRAWL_API_KEY` (required)
- `.env` with `GOOGLE_MAPS_API_KEY` (optional, skips spatial filter if missing)
- `ANTHROPIC_API_KEY` env var for LLM scoring
- Python venv with: requests, pydantic, python-dotenv, anthropic

## After the hunt

Present the ranked report to the user. Highlight any listings scoring ≥85. Offer to open top picks in the browser.
