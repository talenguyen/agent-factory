#!/usr/bin/env python3
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

project_root = Path(__file__).resolve().parent.parent
launcher = project_root / "bin" / "telemetry-report"

EVENTS = [
    '{"ts":"2026-01-01T00:00:01Z","event":"tool_call","tool_name":"Bash","success":true}',
    '{"ts":"2026-01-01T00:00:00Z","event":"pi_spawn","trace_id":"t1","tier":"M","pi_session_id":"sess-1"}',
    '{"ts":"2026-01-01T00:10:00Z","event":"pi_delegation_end","trace_id":"t1","outcome":"goal_met"}',
]

with TemporaryDirectory() as tmp:
    events_path = Path(tmp) / "events.jsonl"
    events_path.write_text("\n".join(EVENTS) + "\n")

    sessions_root = Path(tmp) / "sessions"
    sessions_root.mkdir()

    text_result = subprocess.run(
        [
            sys.executable,
            str(launcher),
            "--events-file",
            str(events_path),
            "--sessions-root",
            str(sessions_root),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert "Bash: 1" in text_result.stdout, text_result.stdout
    assert "goal_met: 1" in text_result.stdout, text_result.stdout

    out_path = Path(tmp) / "dashboard.html"
    html_result = subprocess.run(
        [
            sys.executable,
            str(launcher),
            "--events-file",
            str(events_path),
            "--sessions-root",
            str(sessions_root),
            "--html",
            "--no-open",
            "--out",
            str(out_path),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert out_path.exists(), html_result.stdout
    assert out_path.read_text().startswith("<!doctype html>")


# The DEFAULT --events-file must resolve to the shared main checkout, not to
# the checkout the script file happens to live in. The writer scripts anchor
# their log to the main checkout, so a report run from a linked worktree that
# resolved its default relative to its own on-disk location would always read
# an empty log.
def git(*args, cwd):
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )


with TemporaryDirectory() as tmp:
    main_root = Path(tmp) / "main"
    (main_root / "bin").mkdir(parents=True)
    shutil.copy(launcher, main_root / "bin" / "telemetry-report")
    # The telemetry package is imported from whichever checkout runs the
    # script, so point both checkouts at this repo's real lib/.
    (main_root / "lib").symlink_to(project_root / "lib")

    git("init", "-q", cwd=main_root)
    git("add", "-A", cwd=main_root)
    git("commit", "-q", "-m", "init", cwd=main_root)
    worktree_root = Path(tmp) / "wt"
    git("worktree", "add", "-q", str(worktree_root), "-b", "wt", cwd=main_root)

    shared_log = main_root / "var" / "telemetry" / "events.jsonl"
    shared_log.parent.mkdir(parents=True)
    shared_log.write_text(
        '{"ts":"2026-01-01T00:00:01Z","event":"tool_call","tool_name":"SharedLogTool"}\n'
    )
    # A decoy in the worktree's own var/telemetry: nothing writes here any
    # more, and the report must not read it.
    decoy_log = worktree_root / "var" / "telemetry" / "events.jsonl"
    decoy_log.parent.mkdir(parents=True)
    decoy_log.write_text(
        '{"ts":"2026-01-01T00:00:01Z","event":"tool_call","tool_name":"WorktreeDecoyTool"}\n'
    )

    empty_sessions = Path(tmp) / "no-sessions"
    empty_sessions.mkdir()

    default_result = subprocess.run(
        [
            sys.executable,
            str(worktree_root / "bin" / "telemetry-report"),
            "--sessions-root",
            str(empty_sessions),
        ],
        cwd=worktree_root,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert "SharedLogTool: 1" in default_result.stdout, default_result.stdout
    assert "WorktreeDecoyTool" not in default_result.stdout, default_result.stdout

print("test-telemetry-report-cli: PASS")
