---
name: report
description: Generate ranked report of scored listings — interactive HTML + shareable PDF with photos and NoBroker links. Use when the user says "report", "show results", "top listings", "rank them", "generate PDF", "share report", or wants final output.
---

# Report Generator

Generates both HTML (interactive, for Mac) and PDF (shareable via WhatsApp/AirDrop).

## How to run

```bash
cd /Users/sarath.m/Documents/github/house_hunt
.venv/bin/python -c "
from src.config import Config, RunContext
from src.reporter import generate_report
from src.pdf_report import generate_pdf
from pathlib import Path
import json, sys

run_id = sys.argv[1]
run_dir = Path('data/runs') / run_id
cfg = Config(**json.loads((run_dir / 'config.json').read_text()))
ctx = RunContext(run_id=run_id, run_dir=run_dir, config=cfg)

# Interactive HTML
generate_report(ctx)

# Shareable PDF (top listings only)
generate_pdf(run_dir / 'scored.json', run_dir / 'report.pdf', threshold=cfg.score_threshold)
" ${RUN_ID}
```

## Outputs

- `data/runs/{RUN_ID}/report.html` — interactive with filters, sort, image gallery, clickable links
- `data/runs/{RUN_ID}/report.md` — plain text for LLM consumption
- `data/runs/{RUN_ID}/report.pdf` — shareable PDF with top listings + photos

## After reporting

- Open HTML in browser: `open data/runs/{RUN_ID}/report.html`
- Share PDF: `open data/runs/{RUN_ID}/report.pdf` → AirDrop → WhatsApp
- For encrypted sharing: use `src/encrypt_report.py` to wrap HTML with passphrase
