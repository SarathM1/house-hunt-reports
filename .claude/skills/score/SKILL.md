---
name: score
description: Score filtered listings as LLM judge — evaluates power backup (hard req), noise, internet, water, maintenance, WFH livability. Use when the user says "score", "evaluate", "judge", or wants AI assessment.
---

# LLM Scoring (Claude Code as Judge)

Score listings directly in Claude Code — no API key needed, uses your Max plan.

## How to run

1. Find the latest run:
```bash
ls -t data/runs/ | head -1
```

2. Read the filtered listings:
```bash
cat data/runs/{RUN_ID}/filtered.json
```

3. Read the config to get scoring weights:
```bash
cat data/runs/{RUN_ID}/config.json
```

4. For EACH listing in `filtered.json`, evaluate against these criteria and produce a score:

**HARD REQUIREMENT — 100% power backup:**
If `detail.power_backup` is missing, null, "None", "No", partial, or inverter-only → `disqualified: true`.

**Scoring criteria (0-100 total):**

| Criteria | Weight | What to check |
|----------|--------|---------------|
| Power backup quality & coverage | `llm_weights.power_backup` pts | Generator vs inverter, full vs partial, explicit mention in description |
| Noise insulation / peaceful environment | `llm_weights.noise` pts | Description signals, floor level, facing away from road, inner layout |
| Internet/connectivity infrastructure | `llm_weights.internet` pts | Fiber-ready, broadband mentions, ACT/Airtel in description |
| Natural light, ventilation, floor level | `llm_weights.light_ventilation` pts | Facing, balconies count, mid-floor (2-4) preference |
| Water supply reliability | `llm_weights.water` pts | Corporation + borewell + sump > borewell-only |
| Building maintenance & security | `llm_weights.maintenance` pts | Gated community, managed maintenance, security staff |
| WFH livability (space, furnishing) | `llm_weights.wfh_livability` pts | Room for desk, semi/fully furnished, quiet layout |
| Value for money | `llm_weights.value` pts | Rent vs sqft vs amenities ratio |

5. Compute final score:
```
final_score = (config.score_weights.peace * peace_score) + (config.score_weights.llm * llm_score)
```

6. Write results to `data/runs/{RUN_ID}/scored.json` as a JSON array. Each entry:
```json
{
  "summary": { ... },
  "detail": { ... },
  "lat": ..., "lon": ...,
  "walk_minutes": ..., "orr_distance_m": ...,
  "peace_score": ...,
  "llm_score": <your 0-100 score>,
  "llm_reasoning": "<2-3 sentence explanation>",
  "final_score": <weighted combo>,
  "disqualified": <true|false>,
  "disqualify_reason": "<reason or null>"
}
```

Write the file using the Write tool — do NOT use Python scripts or API calls.

## After scoring

Present scores to user. Run `/report` to generate ranked report.
