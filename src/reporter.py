"""Generate ranked report from scored listings."""
import json
from pathlib import Path

from .config import MIN_SCORE_FOR_REPORT
from .models import ScoredListing


def generate_report(scored_path: Path | str, min_score: int = MIN_SCORE_FOR_REPORT) -> str:
    """Generate markdown report from scored listings."""
    raw = json.loads(Path(scored_path).read_text())
    listings = [ScoredListing(**item) for item in raw]
    listings.sort(key=lambda x: x.total_score, reverse=True)

    lines = [
        f"# House Hunt Report — {Path(scored_path).stem}",
        f"\n**{len(listings)}** listings scored, **{sum(1 for l in listings if l.total_score >= min_score)}** above threshold ({min_score})\n",
        "---\n",
    ]

    for rank, l in enumerate(listings, 1):
        above = "✅" if l.total_score >= min_score else "❌"
        lines.append(f"## #{rank} {above} {l.title}")
        lines.append(f"**Score: {l.total_score:.1f}** (LLM: {l.llm_score} | Peace: {l.peace_score:.1f})\n")
        lines.append(f"| Field | Value |")
        lines.append(f"|-------|-------|")
        lines.append(f"| Rent | ₹{l.rent:,} + ₹{l.maintenance:,} maintenance |")
        lines.append(f"| Deposit | ₹{l.deposit:,} |")
        lines.append(f"| Area | {l.sqft} sqft |")
        lines.append(f"| Walk to PTP | {l.walk_minutes:.1f} min |")
        lines.append(f"| ORR Distance | {l.orr_distance_meters:.0f}m |")
        lines.append(f"| Furnishing | {l.furnishing or 'Unknown'} |")
        lines.append(f"| Floor | {l.floor or 'Unknown'} |")
        lines.append(f"| Power Backup | {l.power_backup or 'Unknown'} |")
        lines.append(f"| Gated Security | {l.gated_security or 'Unknown'} |")
        lines.append(f"\n**LLM Assessment:** {l.llm_reasoning}\n")
        lines.append(f"**Link:** [{l.url}]({l.url})\n")
        lines.append("---\n")

    return "\n".join(lines)


def run(scored_path: Path | str) -> str:
    """Generate and print report."""
    report = generate_report(scored_path)
    print(report)
    return report
