---
name: score
description: Score filtered listings using Claude Sonnet as LLM judge — evaluates power backup (hard req), noise, internet, water, maintenance, WFH livability. Use when the user says "score", "evaluate", "judge", or wants AI assessment.
---

# LLM Scoring

## What it does

1. Sends each listing to Claude Sonnet with 8-criteria weighted prompt
2. Hard disqualify if no 100% power backup
3. Computes final_score = peace_weight * peace_score + llm_weight * llm_score

## How to run

Requires a run_id with `filtered.json`. Then:
```bash
cd /Users/sarath.m/Documents/github/house_hunt
.venv/bin/python -c "
from src.config import Config, RunContext
from src.scorer import run_score
from pathlib import Path
import json, sys

run_id = sys.argv[1]
run_dir = Path('data/runs') / run_id
cfg = Config(**json.loads((run_dir / 'config.json').read_text()))
ctx = RunContext(run_id=run_id, run_dir=run_dir, config=cfg)
run_score(ctx)
" ${RUN_ID}
```

Requires `ANTHROPIC_API_KEY` env var.

## After scoring

Report scores. Suggest `/report` to see ranked output.
