#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from telemetry.text_report import render_text

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

text = render_text(REPORT)

assert "Bash: 2" in text, text
assert "delegate-to-pi: 1" in text, text
assert "M: 1, avg turns: 2.0" in text, text
assert "goal_met: 1" in text, text
assert "software: 1" in text, text
assert "software / goal_met: 1" in text, text
assert "Crew rounds by domain" in text, text
assert "Total pi cost observed: $0.0500" in text, text

print("test-telemetry-text-report: PASS")
