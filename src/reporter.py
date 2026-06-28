import json
from pathlib import Path

from .config import RunContext


def generate_report(ctx: RunContext) -> str:
    config = ctx.config
    scored_path = ctx.path("scored.json")
    entries = json.loads(scored_path.read_text())
    entries.sort(key=lambda x: x["final_score"], reverse=True)

    threshold = config.score_threshold
    above = sum(1 for e in entries if e["final_score"] >= threshold and not e["disqualified"])

    lines = [
        f"# House Hunt Report — {ctx.run_id}",
        f"\n**Config:** {config.name} | **Scored:** {len(entries)} | **Above {threshold}:** {above}\n",
        "---\n",
    ]

    for rank, e in enumerate(entries, 1):
        s = e["summary"]
        d = e.get("detail") or {}
        disq = "DISQUALIFIED" if e["disqualified"] else ""
        act = "ACT NOW" if e["final_score"] >= threshold and not e["disqualified"] else ""
        tag = disq or act

        lines.append(f"## #{rank} {s['title']} {tag}")
        lines.append(f"**Score: {e['final_score']}** (LLM: {e['llm_score']} | Peace: {e['peace_score']})\n")
        if e["disqualified"]:
            lines.append(f"**Disqualified:** {e['disqualify_reason']}\n")
        lines.append("| Field | Value |")
        lines.append("|-------|-------|")
        lines.append(f"| Rent | ₹{s['rent']:,} + ₹{s.get('maintenance') or 0:,} maintenance |")
        lines.append(f"| Deposit | ₹{s['deposit']:,} |")
        lines.append(f"| Area | {s['sqft']} sqft |")
        lines.append(f"| Walk to PTP | {e['walk_minutes']} min |")
        lines.append(f"| ORR Distance | {e['orr_distance_m']}m |")
        lines.append(f"| Furnishing | {d.get('furnishing') or 'Unknown'} |")
        lines.append(f"| Floor | {d.get('floor') or 'Unknown'} |")
        lines.append(f"| Power Backup | {d.get('power_backup') or 'Unknown'} |")
        lines.append(f"| Water Supply | {d.get('water_supply') or 'Unknown'} |")
        lines.append(f"| Gated Security | {d.get('gated_security', 'Unknown')} |")
        lines.append(f"\n**Assessment:** {e['llm_reasoning']}\n")
        lines.append(f"**Link:** [{s['detail_url']}]({s['detail_url']})\n")
        lines.append("---\n")

    report = "\n".join(lines)
    ctx.path("report.md").write_text(report)
    print(report)
    return report


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
