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
