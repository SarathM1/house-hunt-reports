---
name: score
description: Score filtered listings as LLM judge — per-criteria structured evaluation with confidence, evidence, pros/cons, and elevator pitch.
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

4. For EACH listing in `filtered.json`, evaluate against these criteria:

**HARD REQUIREMENT — 100% power backup:**
If `detail.power_backup` is missing, null, "None", "No", partial, or inverter-only → `disqualified: true`.

**Scoring criteria — score each independently:**

| Criteria | Max Points | What to check |
|----------|-----------|---------------|
| power_backup | `llm_weights.power_backup` | Generator vs inverter, full vs partial, explicit mention |
| noise | `llm_weights.noise` | Description signals, floor level, facing away from road |
| internet | `llm_weights.internet` | Fiber-ready, broadband mentions, ACT/Airtel |
| light_ventilation | `llm_weights.light_ventilation` | Facing, balconies, mid-floor (2-4) preference |
| water | `llm_weights.water` | Corporation + borewell + sump > borewell-only |
| maintenance | `llm_weights.maintenance` | Gated community, managed maintenance, security |
| wfh_livability | `llm_weights.wfh_livability` | Room for desk, semi/fully furnished, quiet layout |
| value | `llm_weights.value` | Rent vs sqft vs amenities ratio |

**Confidence per criterion:**
- `high`: listing explicitly states this info
- `medium`: inferred from description or context
- `low`: no info available, scoring on defaults

5. Compute scores:
```
llm_score = sum of all criteria scores
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
  "llm_score": "<sum of criteria scores, 0-100>",
  "final_score": "<weighted combo>",
  "disqualified": "<true|false>",
  "disqualify_reason": "<reason or null>",
  "criteria_scores": {
    "<criterion>": {"score": "<0-max>", "max": "<from config>", "confidence": "<high|medium|low>", "evidence": "<what drove this score>"}
  },
  "pros": ["<2-5 key strengths>"],
  "cons": ["<1-4 key weaknesses>"],
  "elevator_pitch": "<1-line shareable summary>",
  "data_completeness": "<from filtered.json or estimate 0-1>",
  "peace_breakdown": "<from filtered.json if available>",
  "comparative_rank": null,
  "comparative_notes": null,
  "duplicate_of": null
}
```

Write the file using the Write tool — do NOT use Python scripts or API calls.

## After scoring — Comparative Pass

After scoring all listings, do a comparative pass:

1. Review all qualified (non-disqualified) listings together
2. Rank them from best to worst for a WFH-heavy hybrid worker
3. For each listing, write 1 sentence explaining its rank relative to others
4. Update each listing's `comparative_rank` and `comparative_notes` in scored.json
5. Write `data/runs/{RUN_ID}/comparative.json`:
```json
{
  "rankings": [{"property_id": "<id>", "rank": 1, "reasoning": "<vs others>"}],
  "top_3_summary": "#1 Name — why. #2 Name — why. #3 Name — why."
}
```

## After scoring

Present scores to user. Run `/report` to generate ranked report.
