import json
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .config import RunContext

TEMPLATE_DIR = Path(__file__).parent
TEMPLATE_FILE = "report_template.html"
INDEX_TEMPLATE_FILE = "index_template.html"
REPO_ROOT = Path(__file__).parent.parent


def generate_report(ctx: RunContext) -> Path:
    config = ctx.config
    scored_path = ctx.path("scored.json")
    entries = json.loads(scored_path.read_text())

    # Load comparative result if exists
    comp_path = ctx.path("comparative.json")
    comparative = json.loads(comp_path.read_text()) if comp_path.exists() else None

    qualified = [e for e in entries if not e["disqualified"]]
    disqualified = [e for e in entries if e["disqualified"]]
    qualified.sort(key=lambda x: x.get("comparative_rank") or 999)
    disqualified.sort(key=lambda x: x["final_score"], reverse=True)
    sorted_entries = qualified + disqualified

    # Compute run averages for comparative context
    if qualified:
        all_criteria: dict[str, list] = {}
        for e in qualified:
            for k, v in e.get("criteria_scores", {}).items():
                all_criteria.setdefault(k, []).append(v["score"])
        criteria_averages = {k: round(sum(v) / len(v), 1) for k, v in all_criteria.items()}
    else:
        criteria_averages = {}

    threshold = config.score_threshold
    above = sum(1 for e in qualified if e["final_score"] >= threshold)

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=False)
    template = env.get_template(TEMPLATE_FILE)
    html = template.render(
        run_id=ctx.run_id,
        config_name=config.name,
        total=len(entries),
        qualified=len(qualified),
        disqualified_count=len(disqualified),
        above_threshold=above,
        threshold=threshold,
        entries=sorted_entries,
        entries_json=json.dumps(sorted_entries),
        criteria_averages_json=json.dumps(criteria_averages),
        comparative_json=json.dumps(comparative) if comparative else "null",
    )

    html_path = ctx.path("report.html")
    html_path.write_text(html)

    reports_dir = REPO_ROOT / "reports" / ctx.run_id
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "index.html").write_text(html)

    _regenerate_index(env)

    # Markdown report with structured data
    md_lines = [
        f"# House Hunt Report — {ctx.run_id}",
        f"\n**Config:** {config.name} | **Scored:** {len(entries)} | **Qualified:** {len(qualified)} | **Above {threshold}:** {above}\n",
    ]
    if comparative:
        md_lines.append(f"## Top Picks\n{comparative['top_3_summary']}\n")
    md_lines.append("---\n")

    for rank, e in enumerate(sorted_entries, 1):
        s = e["summary"]
        d = e.get("detail") or {}
        tag = "DISQUALIFIED" if e["disqualified"] else ("ACT NOW" if e["final_score"] >= threshold else "")
        md_lines.append(f"## #{rank} {s['title']} {tag}")
        md_lines.append(f"**Score: {e['final_score']}** (LLM: {e['llm_score']} | Peace: {e['peace_score']})")

        if e.get("elevator_pitch"):
            md_lines.append(f"*{e['elevator_pitch']}*")

        if e["disqualified"]:
            md_lines.append(f"**Disqualified:** {e['disqualify_reason']}")
        md_lines.append(f"Rent: ₹{s['rent']:,} | Deposit: ₹{s['deposit']:,} | {s['sqft']}sqft | {e['walk_minutes']}min | {d.get('furnishing','?')} | Power: {d.get('power_backup','?')}")

        if e.get("pros"):
            md_lines.append("**Pros:** " + " · ".join(f"✓ {p}" for p in e["pros"]))
        if e.get("cons"):
            md_lines.append("**Cons:** " + " · ".join(f"✗ {c}" for c in e["cons"]))

        if e.get("criteria_scores"):
            scores_str = " | ".join(f"{k}: {v['score']}/{v['max']}" for k, v in e["criteria_scores"].items())
            md_lines.append(f"Criteria: {scores_str}")

        if e.get("peace_breakdown"):
            pb = e["peace_breakdown"]
            md_lines.append(f"Peace: ORR {pb['orr_distance_m']:.0f}m → base {pb['base_score']}, bonus +{pb['locality_bonus']} → {pb['final']}")

        md_lines.append(f"Link: {s['detail_url']}\n---\n")

    md_path = ctx.path("report.md")
    md_path.write_text("\n".join(md_lines))

    print(f"Reports: {html_path} + {md_path}", flush=True)
    print(f"  {len(qualified)} qualified, {above} above {threshold}, {len(disqualified)} disqualified", flush=True)
    return html_path


def _regenerate_index(env: Environment) -> None:
    reports_dir = REPO_ROOT / "reports"
    if not reports_dir.exists():
        return
    runs = []
    for run_dir in sorted(reports_dir.iterdir(), reverse=True):
        config_path = REPO_ROOT / "data" / "runs" / run_dir.name / "config.json"
        if not config_path.exists():
            continue
        config_data = json.loads(config_path.read_text())
        dt = datetime.strptime(run_dir.name, "%Y%m%d_%H%M%S")
        runs.append({
            "run_id": run_dir.name,
            "config_name": config_data.get("name", "default"),
            "date_formatted": dt.strftime("%b %-d, %-I:%M %p"),
        })
    template = env.get_template(INDEX_TEMPLATE_FILE)
    html = template.render(runs=runs)
    (REPO_ROOT / "index.html").write_text(html)


def compare_runs(run_dir_a: Path, run_dir_b: Path) -> str:
    config_a = json.loads((run_dir_a / "config.json").read_text())
    config_b = json.loads((run_dir_b / "config.json").read_text())
    scored_a = json.loads((run_dir_a / "scored.json").read_text())
    scored_b = json.loads((run_dir_b / "scored.json").read_text())

    ids_a = {e["summary"]["property_id"]: e for e in scored_a}
    ids_b = {e["summary"]["property_id"]: e for e in scored_b}
    shared = set(ids_a) & set(ids_b)
    only_a = set(ids_a) - set(ids_b)
    only_b = set(ids_b) - set(ids_a)

    lines = [
        f"# Run Comparison: {run_dir_a.name} vs {run_dir_b.name}\n",
    ]

    config_diffs = []
    all_keys = set(config_a) | set(config_b)
    for k in sorted(all_keys):
        va, vb = config_a.get(k), config_b.get(k)
        if va != vb:
            config_diffs.append(f"| {k} | {va} | {vb} |")
    if config_diffs:
        lines.append("## Config Differences\n")
        lines.append("| Key | Run A | Run B |")
        lines.append("|-----|-------|-------|")
        lines.extend(config_diffs)
        lines.append("")

    if shared:
        lines.append(f"## Shared Listings ({len(shared)})\n")
        lines.append("| ID | Title | Score A | Score B | Delta |")
        lines.append("|----|-------|---------|---------|-------|")
        for pid in sorted(shared):
            ea, eb = ids_a[pid], ids_b[pid]
            delta = eb["final_score"] - ea["final_score"]
            sign = "+" if delta > 0 else ""
            lines.append(
                f"| {pid} | {ea['summary']['title'][:40]} | {ea['final_score']} | {eb['final_score']} | {sign}{delta:.1f} |"
            )
        lines.append("")

    if only_a:
        lines.append(f"## Only in Run A ({len(only_a)})\n")
        for pid in sorted(only_a):
            e = ids_a[pid]
            lines.append(f"- **{e['summary']['title']}** ({pid}, score: {e['final_score']})")
        lines.append("")

    if only_b:
        lines.append(f"## Only in Run B ({len(only_b)})\n")
        for pid in sorted(only_b):
            e = ids_b[pid]
            lines.append(f"- **{e['summary']['title']}** ({pid}, score: {e['final_score']})")
        lines.append("")

    return "\n".join(lines)
