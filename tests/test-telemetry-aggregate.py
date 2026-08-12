#!/usr/bin/env python3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from telemetry.aggregate import build_report

EVENTS = [
    '{"ts":"2026-01-01T00:00:01Z","event":"tool_call","tool_name":"Bash","success":true}',
    '{"ts":"2026-01-01T00:00:02Z","event":"tool_call","tool_name":"Bash","success":true}',
    '{"ts":"2026-01-01T00:00:03Z","event":"tool_call","tool_name":"Skill","tool_input":{"skill":"delegate-to-pi"}}',
    '{"ts":"2026-01-01T00:00:00Z","event":"pi_spawn","trace_id":"t1","tier":"M","pi_session_id":"sess-1"}',
    '{"ts":"2026-01-01T00:05:00Z","event":"pi_crew_round","trace_id":"t1","round":"1","verdict":"approved"}',
    '{"ts":"2026-01-01T00:10:00Z","event":"pi_delegation_end","trace_id":"t1","outcome":"goal_met"}',
    # t2 exercises the pi_fallback re-targeting path: spawned under sess-2a,
    # then rate-limited and respawned under sess-2b partway through. Ingestion
    # must read sess-2b (post-fallback), not sess-2a (pre-fallback), while
    # still attributing the trace to its original tier "M".
    '{"ts":"2026-01-02T00:00:00Z","event":"pi_spawn","trace_id":"t2","tier":"M","domain":"research","pi_session_id":"sess-2a"}',
    '{"ts":"2026-01-02T00:05:00Z","event":"pi_fallback","trace_id":"t2","pi_session_id":"sess-2b"}',
    '{"ts":"2026-01-02T00:15:00Z","event":"pi_crew_round","trace_id":"t2","round":"1","verdict":"approved","domain":"research"}',
    '{"ts":"2026-01-02T00:20:00Z","event":"pi_delegation_end","trace_id":"t2","outcome":"goal_met"}',
    # t3: a truncated/hand-edited start event with no "ts". It must not crash
    # the report, and must still be counted for tier/outcome — only the pi-side
    # ingestion (which needs a window start) is skipped.
    '{"event":"pi_spawn","trace_id":"t3","tier":"S","pi_session_id":"sess-3"}',
    '{"ts":"2026-01-03T00:20:00Z","event":"pi_delegation_end","trace_id":"t3","outcome":"goal_met"}',
    # t4: the literal "unknown" placeholder the skill records when the session
    # lookup fails. It must never be globbed for.
    '{"ts":"2026-01-04T00:00:00Z","event":"pi_spawn","trace_id":"t4","tier":"S","pi_session_id":"unknown"}',
    # telemetry-record writes an unset DOMAIN as an empty string, so aggregate
    # it to software just as it does an absent domain field.
    '{"ts":"2026-01-05T00:00:00Z","event":"pi_spawn","trace_id":"t5","tier":"S","domain":"","pi_session_id":"unknown"}',
    '{"ts":"2026-01-05T00:05:00Z","event":"pi_crew_round","trace_id":"t5","round":"1","verdict":"approved","domain":""}',
    '{"ts":"2026-01-05T00:10:00Z","event":"pi_delegation_end","trace_id":"t5","outcome":"goal_met"}',
]

SESSION_LINES = [
    '{"type":"message","timestamp":"2026-01-01T00:00:05Z","message":{"role":"user","content":[]}}',
    '{"type":"message","timestamp":"2026-01-01T00:00:06Z","message":{"role":"assistant","content":[{"type":"toolCall","name":"bash"}],"usage":{"cost":{"total":0.02}}}}',
    '{"type":"message","timestamp":"2026-01-01T00:00:07Z","message":{"role":"user","content":[]}}',
    '{"type":"message","timestamp":"2026-01-01T00:00:08Z","message":{"role":"assistant","content":[{"type":"toolCall","name":"bash"}],"usage":{"cost":{"total":0.03}}}}',
]

# Pre-fallback session (sess-2a). Deliberately distinct (1 turn, cost 9.0) so
# that if the fallback re-targeting regressed and this file got read instead
# of sess-2b, the aggregate assertions below would fail loudly.
SESSION_LINES_PRE_FALLBACK = [
    '{"type":"message","timestamp":"2026-01-02T00:01:00Z","message":{"role":"user","content":[]}}',
    '{"type":"message","timestamp":"2026-01-02T00:02:00Z","message":{"role":"assistant","content":[{"type":"toolCall","name":"bash"}],"usage":{"cost":{"total":9.0}}}}',
]

# Post-fallback session (sess-2b). This is the one that should actually be
# ingested for t2.
SESSION_LINES_POST_FALLBACK = [
    '{"type":"message","timestamp":"2026-01-02T00:06:00Z","message":{"role":"user","content":[]}}',
    '{"type":"message","timestamp":"2026-01-02T00:07:00Z","message":{"role":"assistant","content":[{"type":"toolCall","name":"bash"}],"usage":{"cost":{"total":0.11}}}}',
    '{"type":"message","timestamp":"2026-01-02T00:08:00Z","message":{"role":"user","content":[]}}',
    '{"type":"message","timestamp":"2026-01-02T00:09:00Z","message":{"role":"assistant","content":[{"type":"toolCall","name":"bash"}],"usage":{"cost":{"total":0.13}}}}',
    '{"type":"message","timestamp":"2026-01-02T00:10:00Z","message":{"role":"user","content":[]}}',
]

# Decoys for t3 and t4 below. Each is timestamped inside its trace's window
# and carries an outsized cost, so if either guard regressed the file would be
# ingested and blow total_pi_cost past its expected value.
SESSION_LINES_DECOY_T3 = [
    '{"type":"message","timestamp":"2026-01-03T00:01:00Z","message":{"role":"user","content":[]}}',
    '{"type":"message","timestamp":"2026-01-03T00:02:00Z","message":{"role":"assistant","content":[{"type":"toolCall","name":"bash"}],"usage":{"cost":{"total":50.0}}}}',
]

SESSION_LINES_DECOY_T4 = [
    '{"type":"message","timestamp":"2026-01-04T00:01:00Z","message":{"role":"user","content":[]}}',
    '{"type":"message","timestamp":"2026-01-04T00:02:00Z","message":{"role":"assistant","content":[{"type":"toolCall","name":"bash"}],"usage":{"cost":{"total":50.0}}}}',
]

with TemporaryDirectory() as tmp:
    events_path = Path(tmp) / "events.jsonl"
    events_path.write_text("\n".join(EVENTS) + "\n")

    sessions_root = Path(tmp) / "sessions"
    session_dir = sessions_root / "--repo--"
    session_dir.mkdir(parents=True)
    (session_dir / "2026-01-01T00-00-00-000Z_sess-1.jsonl").write_text(
        "\n".join(SESSION_LINES) + "\n"
    )
    (session_dir / "2026-01-02T00-00-00-000Z_sess-2a.jsonl").write_text(
        "\n".join(SESSION_LINES_PRE_FALLBACK) + "\n"
    )
    (session_dir / "2026-01-02T00-05-00-000Z_sess-2b.jsonl").write_text(
        "\n".join(SESSION_LINES_POST_FALLBACK) + "\n"
    )
    # Decoy for t3, whose start event is missing "ts".
    (session_dir / "2026-01-03T00-00-00-000Z_sess-3.jsonl").write_text(
        "\n".join(SESSION_LINES_DECOY_T3) + "\n"
    )
    # Decoy for t4: an unrelated real session whose filename happens to contain
    # the substring "unknown", which a naive glob for the placeholder would hit.
    (session_dir / "2026-01-04T00-00-00-000Z_unknown-session.jsonl").write_text(
        "\n".join(SESSION_LINES_DECOY_T4) + "\n"
    )

    report = build_report(events_path, sessions_root)

    assert report["tool_call_counts"] == {"Bash": 2, "Skill": 1}, report
    assert report["skill_call_counts"] == {"delegate-to-pi": 1}, report
    # Both t1 and t2 are tier M; t2 must be attributed to "M" (its original
    # tier from pi_spawn), not left "unknown" or overwritten by the
    # pi_fallback event (which carries no tier field at all).
    # t3 and t4 are tier S: their pi-side ingestion is skipped, but the traces
    # themselves are still counted for tier/outcome.
    assert report["tier_distribution"] == {"M": 2, "S": 3}, report
    assert report["domain_distribution"] == {"software": 4, "research": 1}, report
    assert report["outcomes_by_domain"] == {
        "software": {"goal_met": 3},
        "research": {"goal_met": 1},
    }, report
    assert report["rounds_by_domain"] == {"software": 2, "research": 1}, report
    # t1 contributes 2 turns (from sess-1); t2 must contribute 3 turns from
    # sess-2b (post-fallback), NOT 1 turn from sess-2a (pre-fallback). Tier S
    # contributes no turns at all, so it must be absent rather than 0.
    assert report["avg_turns_per_tier"] == {"M": 2.5}, report
    assert report["outcome_counts"] == {"goal_met": 4}, report
    assert report["fallback_count"] == 1, report
    assert report["escalated_count"] == 0, report
    assert report["turn_cap_count"] == 0, report
    # t1 cost 0.05 + t2 cost 0.24 (sess-2b). If re-targeting regressed and
    # sess-2a (cost 9.0) were read instead, this would be ~9.05, not ~0.29;
    # if either decoy (cost 50.0) were ingested it would be ~50.29 or ~100.29.
    assert abs(report["total_pi_cost"] - 0.29) < 1e-9, report

print("test-telemetry-aggregate: PASS")
