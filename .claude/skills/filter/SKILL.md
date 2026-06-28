---
name: filter
description: Spatially filter scraped NoBroker listings using Google Maps APIs — geocode addresses, compute walking distance to Prestige Tech Park (max 12 min), and distance from Outer Ring Road (min 200m for noise). Use when the user says "filter", "spatial filter", "check distances", "which ones are walkable", or wants to narrow listings by location. Requires GOOGLE_MAPS_API_KEY in .env.
---

# Spatial Filter

Filter scraped listings by walking distance to Prestige Tech Park and distance from Outer Ring Road.

## Prerequisites

- `GOOGLE_MAPS_API_KEY` must be set in `.env` with Distance Matrix and Geocoding APIs enabled
- Raw listings must exist in `data/raw/` (run `/scrape` first if not)

## What it does

1. Geocodes each listing's address via Google Geocoding API
2. Computes walking duration to PTP main gate via Distance Matrix API (threshold: ≤12 minutes)
3. Computes haversine distance from ORR reference points (threshold: ≥200 meters)
4. Drops listings that fail either threshold
5. Saves to `data/filtered/YYYY-MM-DD.json`

## How to run

```bash
cd /Users/sarath.m/Documents/github/house_hunt
.venv/bin/python -c "from src.spatial import run; run('data/raw/LATEST_FILE.json')"
```

Replace `LATEST_FILE.json` with the most recent file in `data/raw/`.

## Thresholds (in src/config.py)

- `MAX_WALK_MINUTES = 12`
- `MIN_ORR_DISTANCE_METERS = 200`

## After filtering

Report how many listings passed vs dropped, with reasons. Suggest `/score` next.
