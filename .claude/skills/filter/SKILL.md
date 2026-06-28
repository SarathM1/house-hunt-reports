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
