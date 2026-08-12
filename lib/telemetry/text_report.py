"""Render aggregate report data as a plain-text summary."""
from __future__ import annotations


def render_text(report: dict) -> str:
    lines = []

    lines.append("=== Tool & skill usage ===")
    for tool_name, count in sorted(
        report["tool_call_counts"].items(), key=lambda item: -item[1]
    ):
        lines.append(f"  {tool_name}: {count}")
    if report["skill_call_counts"]:
        lines.append("  -- skills --")
        for skill_name, count in sorted(
            report["skill_call_counts"].items(), key=lambda item: -item[1]
        ):
            lines.append(f"  {skill_name}: {count}")

    lines.append("")
    lines.append("=== Pi tier distribution ===")
    for tier, count in sorted(report["tier_distribution"].items()):
        avg_turns = report["avg_turns_per_tier"].get(tier)
        avg_text = f", avg turns: {avg_turns:.1f}" if avg_turns is not None else ""
        lines.append(f"  {tier}: {count}{avg_text}")

    lines.append("")
    lines.append("=== Domain distribution ===")
    for domain, count in sorted(report["domain_distribution"].items()):
        lines.append(f"  {domain}: {count}")

    lines.append("")
    lines.append("=== Crew rounds by domain ===")
    for domain, count in sorted(report["rounds_by_domain"].items()):
        lines.append(f"  {domain}: {count}")

    lines.append("")
    lines.append("=== Delegation outcomes ===")
    for outcome, count in sorted(report["outcome_counts"].items()):
        lines.append(f"  {outcome}: {count}")
    lines.append(f"  fallback used: {report['fallback_count']}")
    lines.append(f"  escalated: {report['escalated_count']}")
    lines.append(f"  turn cap hit: {report['turn_cap_count']}")

    lines.append("")
    lines.append("=== Outcomes by domain ===")
    for domain, outcomes in sorted(report["outcomes_by_domain"].items()):
        for outcome, count in sorted(outcomes.items()):
            lines.append(f"  {domain} / {outcome}: {count}")

    lines.append("")
    lines.append(f"Total pi cost observed: ${report['total_pi_cost']:.4f}")

    return "\n".join(lines) + "\n"
