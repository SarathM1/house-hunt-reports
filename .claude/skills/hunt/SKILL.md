---
name: hunt
description: Full house hunting pipeline — scrape → filter → score → report. Use when the user says "hunt", "find apartments", "run the pipeline", "full search", or wants complete end-to-end workflow.
---

# Full Hunt Pipeline

Runs all stages in sequence.

## How to run

### Stage 1 & 2: Scrape + Filter (Python)

```bash
cd /Users/sarath.m/Documents/github/house_hunt
.venv/bin/python -c "
from src.config import load_config, create_run, GOOGLE_MAPS_API_KEY
from src.scraper import run_scrape
from src.spatial import run_filter
import sys, json

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
    raw = json.loads(ctx.path('raw.json').read_text())
    for e in raw:
        e.update({'lat': 0, 'lon': 0, 'walk_minutes': 0, 'orr_distance_m': 999, 'peace_score': 50})
    ctx.path('filtered.json').write_text(json.dumps(raw, indent=2))

print(f'\n=== Scrape + Filter done: data/runs/{ctx.run_id}/ ===')
" ${CONFIG:-default}
```

### Stage 3: Score (Claude Code as judge)

After stages 1-2 complete, invoke the `/score` skill with the run_id from above. Claude Code reads filtered.json and scores each listing directly — no API key needed.

### Stage 4: Report

After scoring, invoke the `/report` skill with the same run_id.

## After the hunt

Present ranked report. Highlight top picks. Offer to compare with previous runs via `/compare`.
