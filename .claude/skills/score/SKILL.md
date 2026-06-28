---
name: score
description: Score filtered rental listings using Claude as an LLM judge — evaluates power backup (hard requirement), noise environment, building maintenance, and remote work suitability. Use when the user says "score", "evaluate", "rank listings", "judge these", or wants AI assessment of listing quality. Runs after /filter (or directly on raw data if skipping spatial filter).
---

# LLM Scoring

Use Claude (claude-sonnet-4-20250514) as a judge to score each listing on suitability for a hybrid remote worker.

## What it does

1. Loads filtered (or raw) listings
2. Sends each to Claude with a structured judge prompt evaluating:
   - Power backup (hard requirement: generator, not just inverter) — up to -40 points
   - Noise/peace indicators — up to -20 points
   - Building maintenance quality — up to -15 points
   - Owner vs broker listing — up to -10 points
3. Combines LLM score (70% weight) with peace score from ORR distance (30% weight)
4. Saves to `data/scored/YYYY-MM-DD.json`

## How to run

```bash
cd /Users/sarath.m/Documents/github/house_hunt
.venv/bin/python -c "from src.scorer import run; run('data/filtered/LATEST_FILE.json')"
```

## Dependencies

Uses `ANTHROPIC_API_KEY` env var (standard Claude auth). If on Claude Max Plan, this is covered.

## After scoring

Report scores and suggest `/report` to generate the ranked output.
