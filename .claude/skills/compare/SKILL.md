---
name: compare
description: Compare two pipeline runs side-by-side — config diff, shared/unique listings, score changes. Use when the user says "compare", "diff runs", "what changed", or wants to evaluate config experiments.
---

# Run Comparison

## How to run

```bash
cd /Users/sarath.m/Documents/github/house_hunt
.venv/bin/python -c "
from src.reporter import compare_runs
from pathlib import Path
import sys

run_a = Path('data/runs') / sys.argv[1]
run_b = Path('data/runs') / sys.argv[2]
print(compare_runs(run_a, run_b))
" ${RUN_A} ${RUN_B}
```

List available runs with: `ls data/runs/`
