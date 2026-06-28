# House Hunt

AI-driven house hunting pipeline for 2BHK rentals near Prestige Tech Park, Bangalore.

## Project Skills

- `/scrape` — Scrape NoBroker listings via Firecrawl
- `/filter` — Spatial filter via Google Maps (walk to PTP, ORR distance)
- `/score` — LLM-as-judge evaluation (power backup, noise, maintenance)
- `/report` — Ranked markdown report
- `/hunt` — Full pipeline end-to-end

## Setup

```bash
uv venv .venv
uv pip install -e . --python .venv/bin/python
```

## Environment Variables

In `.env`:
- `FIRECRAWL_API_KEY` — required for scraping
- `GOOGLE_MAPS_API_KEY` — required for spatial filter, optional for rest of pipeline

`ANTHROPIC_API_KEY` must be set as env var (not in .env) for LLM scoring.

## Data Flow

```
data/raw/      ← scraper output (all listings)
data/filtered/ ← post spatial filter (walkable + quiet)
data/scored/   ← LLM scored + ranked
```

## Running

Use the project skills (`/scrape`, `/filter`, `/score`, `/report`) individually or `/hunt` for full pipeline. Each stage reads the previous stage's output from `data/`.
