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
