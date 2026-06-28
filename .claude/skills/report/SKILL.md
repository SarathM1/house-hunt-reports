---
name: report
description: Generate a ranked markdown report of scored rental listings with details, scores, and NoBroker links. Use when the user says "report", "show results", "what are the top listings", "rank them", "show me the best ones", or wants to see the final output of the house hunting pipeline.
---

# Report Generator

Generate a ranked markdown report from scored listings.

## What it does

1. Loads scored listings from `data/scored/`
2. Sorts by total_score descending
3. Generates markdown with ranking, scores, key details, LLM reasoning, and NoBroker links
4. Marks listings above/below the threshold (default: 85)

## How to run

```bash
cd /Users/sarath.m/Documents/github/house_hunt
.venv/bin/python -c "from src.reporter import run; run('data/scored/LATEST_FILE.json')"
```

## Output

Prints markdown report to stdout. Each listing shows:
- Rank and pass/fail indicator
- Total score breakdown (LLM + Peace)
- Rent, deposit, area, walk time, ORR distance
- Furnishing, floor, power backup, security
- LLM reasoning
- Direct NoBroker link

## After reporting

Present the top listings to the user. Offer to open specific NoBroker links in the browser for closer inspection.
