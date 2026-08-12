#!/usr/bin/env python3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from telemetry.pi_sessions import (
    derive_metrics,
    find_session_file,
    load_session_messages,
    slice_by_window,
)

SESSION_LINES = [
    '{"type":"session","id":"sess-1","timestamp":"2026-01-01T00:00:00Z"}',
    '{"type":"message","timestamp":"2026-01-01T00:00:05Z","message":{"role":"user","content":[{"type":"text","text":"go"}]}}',
    '{"type":"message","timestamp":"2026-01-01T00:00:06Z","message":{"role":"assistant","content":[{"type":"toolCall","name":"bash"}],"usage":{"cost":{"total":0.02}}}}',
    '{"type":"message","timestamp":"2026-01-01T00:00:07Z","message":{"role":"user","content":[{"type":"text","text":"again"}]}}',
    '{"type":"message","timestamp":"2026-01-01T00:00:08Z","message":{"role":"assistant","content":[{"type":"toolCall","name":"bash"}],"usage":{"cost":{"total":0.03}}}}',
    '{"type":"message","timestamp":"2026-01-01T00:15:00Z","message":{"role":"user","content":[{"type":"text","text":"too late"}]}}',
]

with TemporaryDirectory() as tmp:
    sessions_root = Path(tmp)
    session_dir = sessions_root / "--repo--"
    session_dir.mkdir()
    session_file = session_dir / "2026-01-01T00-00-00-000Z_sess-1.jsonl"
    session_file.write_text("\n".join(SESSION_LINES) + "\n")

    found = find_session_file(sessions_root, "sess-1")
    assert found == session_file, found

    assert find_session_file(sessions_root, "does-not-exist") is None

    messages = load_session_messages(session_file)
    assert len(messages) == 6, messages

    sliced = slice_by_window(messages, "2026-01-01T00:00:00Z", "2026-01-01T00:10:00Z")
    assert len(sliced) == 5, sliced  # excludes the 00:15:00 entry

    metrics = derive_metrics(sliced)
    assert metrics["turn_count"] == 2, metrics
    assert metrics["tool_call_counts"] == {"bash": 2}, metrics
    assert abs(metrics["total_cost"] - 0.05) < 1e-9, metrics

print("test-telemetry-pi-sessions: PASS")
