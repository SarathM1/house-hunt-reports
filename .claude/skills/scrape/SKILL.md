---
name: scrape
description: Scrape 2BHK rental listings from NoBroker for all target localities near Prestige Tech Park, Bangalore. Use when the user says "scrape", "fetch listings", "get new listings", "pull from NoBroker", "check for new rentals", or wants fresh property data. Always use this before filtering or scoring if no recent raw data exists in data/raw/.
---

# Scrape NoBroker Listings

Scrape 2BHK rental listings from NoBroker SEO pages via Firecrawl cloud API.

## What it does

1. Hits NoBroker SEO listing pages for each target locality (kadubeesanahalli, bellandur, panathur, marathahalli, doddakannelli)
2. Parses listing summaries from server-rendered markdown (rent, deposit, sqft, address, detail URL)
3. Deduplicates by URL across localities
4. Saves to `data/raw/YYYY-MM-DD.json`

## How to run

```bash
cd /Users/sarath.m/Documents/github/house_hunt
.venv/bin/python -m src.scraper
```

If `.venv` doesn't exist yet, set it up first:
```bash
uv venv .venv
uv pip install requests pydantic python-dotenv anthropic --python .venv/bin/python
```

## Output

JSON array of `ListingSummary` objects in `data/raw/`. Each has: title, url, rent, maintenance, deposit, sqft, address, locality.

## After scraping

Tell the user how many listings were found per locality and total unique count. Suggest running `/filter` next if Google Maps API key is configured, or `/score` to go straight to LLM evaluation (skipping spatial filtering).
