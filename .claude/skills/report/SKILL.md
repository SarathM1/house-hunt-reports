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
