"""Combine the Claude Code event log with pi's own session transcripts
into one aggregate report."""
from __future__ import annotations

import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

from telemetry.events import read_events
from telemetry.pi_sessions import (
    derive_metrics,
    find_session_file,
    load_session_messages,
    slice_by_window,
)

DEFAULT_SESSIONS_ROOT = Path(
    os.environ.get(
        "PI_CODING_AGENT_SESSION_DIR", str(Path.home() / ".pi" / "agent" / "sessions")
    )
)


def build_report(events_path: Path, sessions_root: Optional[Path] = None) -> dict:
    if sessions_root is None:
        sessions_root = DEFAULT_SESSIONS_ROOT

    events = list(read_events(events_path))

    tool_call_counts: Counter = Counter()
    skill_call_counts: Counter = Counter()
    for event in events:
        if event.get("event") != "tool_call":
            continue
        tool_name = event.get("tool_name") or "unknown"
        tool_call_counts[tool_name] += 1
        if tool_name == "Skill":
            skill_name = (event.get("tool_input") or {}).get("skill", "unknown")
            skill_call_counts[skill_name] += 1

    by_trace: dict = defaultdict(dict)
    rounds_by_domain: Counter = Counter()
    for event in events:
        trace_id = event.get("trace_id")
        if not trace_id:
            continue
        kind = event.get("event")
        if kind in ("pi_spawn", "pi_reuse"):
            by_trace[trace_id]["start"] = event
        elif kind == "pi_fallback":
            # A fallback respawns pi under a new session id; later ingestion
            # should target that new session, not the pre-fallback one.
            by_trace[trace_id]["fallback"] = True
            previous_start = by_trace[trace_id].get("start", {})
            by_trace[trace_id]["start"] = {
                **previous_start,
                "pi_session_id": event.get("pi_session_id"),
                "ts": event.get("ts"),
            }
        elif kind == "pi_delegation_end":
            by_trace[trace_id]["end"] = event
        elif kind == "pi_crew_round":
            rounds_by_domain[event.get("domain") or "software"] += 1
        elif kind == "pi_escalated":
            by_trace[trace_id]["escalated"] = True
        elif kind == "pi_turn_cap_hit":
            by_trace[trace_id]["turn_cap_hit"] = True

    tier_distribution: Counter = Counter()
    turns_by_tier: dict = defaultdict(list)
    outcome_counts: Counter = Counter()
    domain_distribution: Counter = Counter()
    outcomes_by_domain: dict = defaultdict(Counter)
    fallback_count = 0
    escalated_count = 0
    turn_cap_count = 0
    total_pi_cost = 0.0

    for info in by_trace.values():
        start = info.get("start")
        if start is None:
            continue

        tier = start.get("tier", "unknown")
        domain = start.get("domain") or "software"
        tier_distribution[tier] += 1
        domain_distribution[domain] += 1

        if info.get("fallback"):
            fallback_count += 1
        if info.get("escalated"):
            escalated_count += 1
        if info.get("turn_cap_hit"):
            turn_cap_count += 1

        end = info.get("end")
        if end:
            outcome = end.get("outcome", "unknown")
            outcome_counts[outcome] += 1
            outcomes_by_domain[domain][outcome] += 1

        pi_session_id = start.get("pi_session_id")
        # "unknown" is the literal placeholder the delegate-to-pi skill records
        # when the session lookup finds no match — never a real session id, and
        # globbing for it could match an unrelated file.
        if not pi_session_id or pi_session_id == "unknown":
            continue
        start_ts = start.get("ts")
        if not start_ts:
            continue
        session_file = find_session_file(sessions_root, pi_session_id)
        if session_file is None:
            continue

        messages = load_session_messages(session_file)
        sliced = slice_by_window(messages, start_ts, end.get("ts") if end else None)
        metrics = derive_metrics(sliced)
        turns_by_tier[tier].append(metrics["turn_count"])
        total_pi_cost += metrics["total_cost"]

    avg_turns_per_tier = {
        tier: sum(turns) / len(turns) for tier, turns in turns_by_tier.items() if turns
    }

    return {
        "tool_call_counts": dict(tool_call_counts),
        "skill_call_counts": dict(skill_call_counts),
        "tier_distribution": dict(tier_distribution),
        "avg_turns_per_tier": avg_turns_per_tier,
        "outcome_counts": dict(outcome_counts),
        "domain_distribution": dict(domain_distribution),
        "outcomes_by_domain": {
            domain: dict(outcomes) for domain, outcomes in outcomes_by_domain.items()
        },
        "rounds_by_domain": dict(rounds_by_domain),
        "fallback_count": fallback_count,
        "escalated_count": escalated_count,
        "turn_cap_count": turn_cap_count,
        "total_pi_cost": total_pi_cost,
    }
