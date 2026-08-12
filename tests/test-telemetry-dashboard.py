#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from telemetry.dashboard import render_html

REPORT = {
    "tool_call_counts": {"Bash": 2, "Skill": 1},
    "skill_call_counts": {"delegate-to-pi": 1},
    "tier_distribution": {"M": 1},
    "avg_turns_per_tier": {"M": 2.0},
    "outcome_counts": {"goal_met": 1},
    "fallback_count": 0,
    "escalated_count": 0,
    "turn_cap_count": 0,
    "total_pi_cost": 0.05,
    "domain_distribution": {"software": 1},
    "outcomes_by_domain": {"software": {"goal_met": 1}},
    "rounds_by_domain": {"software": 1},
}

html = render_html(REPORT)

assert html.startswith("<!doctype html>"), html[:50]
assert "<svg" in html, html
assert "Bash" in html, html
assert "$0.0500" in html, html
assert "Domain distribution" in html, html
assert "Outcomes by domain" in html, html
assert "Crew rounds by domain" in html, html
assert "http://" not in html and "https://" not in html, "dashboard must be self-contained"
assert "<script" not in html, "no scripting needed for static bar charts"

# Test HTML escaping: verify that labels with HTML-significant characters are escaped
REPORT_WITH_SPECIAL_CHARS = {
    "tool_call_counts": {"<script>alert(1)</script>": 2, "Bash": 1},
    "skill_call_counts": {"test&special": 1},
    "tier_distribution": {"M": 1},
    "avg_turns_per_tier": {"M": 2.0},
    "outcome_counts": {"goal_met": 1},
    "fallback_count": 0,
    "escalated_count": 0,
    "turn_cap_count": 0,
    "total_pi_cost": 0.05,
    "domain_distribution": {"software": 1},
    "outcomes_by_domain": {"software": {"goal_met": 1}},
    "rounds_by_domain": {"software": 1},
}

html_escaped = render_html(REPORT_WITH_SPECIAL_CHARS)

# Verify unescaped malicious strings do NOT appear in output
assert "<script>alert(1)</script>" not in html_escaped, "HTML escaping failed for <script> tag"
assert "test&special" not in html_escaped, "HTML escaping failed for & character"
# Verify escaped versions DO appear
assert "&lt;script&gt;" in html_escaped, "escaped <script> should appear in output"
assert "test&amp;special" in html_escaped, "escaped & should appear in output"

print("test-telemetry-dashboard: PASS")
