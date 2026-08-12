"""Render aggregate report data as a self-contained static HTML dashboard."""
from __future__ import annotations

from html import escape


def _bar_chart(title: str, data: dict, color: str) -> str:
    if not data:
        return f"<h2>{escape(title)}</h2><p>No data yet.</p>"

    max_value = max(data.values()) or 1
    bar_height = 24
    gap = 8
    label_width = 160
    chart_width = 320
    height = len(data) * (bar_height + gap)

    rows = []
    for index, (label, value) in enumerate(
        sorted(data.items(), key=lambda item: -item[1])
    ):
        y = index * (bar_height + gap)
        width = (value / max_value) * chart_width
        rows.append(
            f'<text x="0" y="{y + bar_height * 0.7:.1f}" font-size="12">{escape(str(label))}</text>'
            f'<rect x="{label_width}" y="{y}" width="{width:.1f}" height="{bar_height}" fill="{color}"/>'
            f'<text x="{label_width + width + 6:.1f}" y="{y + bar_height * 0.7:.1f}" font-size="12">{value}</text>'
        )

    svg = (
        f'<svg width="{label_width + chart_width + 40}" height="{height}">{"".join(rows)}</svg>'
    )
    return f"<h2>{escape(title)}</h2>{svg}"


def render_html(report: dict) -> str:
    sections = [
        _bar_chart("Tool calls", report["tool_call_counts"], "#4f7cac"),
        _bar_chart("Skill invocations", report["skill_call_counts"], "#4f7cac"),
        _bar_chart("Pi tier distribution", report["tier_distribution"], "#c96f4a"),
        _bar_chart("Domain distribution", report["domain_distribution"], "#9b59b6"),
        _bar_chart("Crew rounds by domain", report["rounds_by_domain"], "#9b59b6"),
        _bar_chart("Delegation outcomes", report["outcome_counts"], "#5a9367"),
        _bar_chart(
            "Outcomes by domain",
            {
                f"{domain} / {outcome}": count
                for domain, outcomes in report["outcomes_by_domain"].items()
                for outcome, count in outcomes.items()
            },
            "#5a9367",
        ),
    ]

    summary = (
        f"<p>Fallback used: {report['fallback_count']} &middot; "
        f"Escalated: {report['escalated_count']} &middot; "
        f"Turn cap hit: {report['turn_cap_count']} &middot; "
        f"Total pi cost observed: ${report['total_pi_cost']:.4f}</p>"
    )

    body = "\n".join(sections)

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>software-factory telemetry</title>
<style>
  body {{ font-family: -apple-system, sans-serif; margin: 2rem; color: #1a1a1a; }}
  h1 {{ margin-bottom: 0.25rem; }}
  h2 {{ margin-top: 2rem; }}
  svg text {{ fill: #1a1a1a; }}
</style>
</head>
<body>
<h1>software-factory telemetry</h1>
{summary}
{body}
</body>
</html>
"""
