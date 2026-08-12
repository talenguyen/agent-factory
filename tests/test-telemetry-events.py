#!/usr/bin/env python3
import io
import sys
from contextlib import redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from telemetry.events import read_events

with TemporaryDirectory() as tmp:
    log_path = Path(tmp) / "events.jsonl"
    log_path.write_text(
        '{"event": "a", "ts": "2026-01-01T00:00:00Z"}\n'
        "not json\n"
        '{"event": "b", "ts": "2026-01-01T00:00:01Z"}\n'
    )

    stderr = io.StringIO()
    with redirect_stderr(stderr):
        events = list(read_events(log_path))

    assert [e["event"] for e in events] == ["a", "b"], events
    assert "malformed line 2" in stderr.getvalue(), stderr.getvalue()

    missing_events = list(read_events(Path(tmp) / "missing.jsonl"))
    assert missing_events == [], missing_events

print("test-telemetry-events: PASS")
