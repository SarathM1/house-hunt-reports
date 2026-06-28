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
