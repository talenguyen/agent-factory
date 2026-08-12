# Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture which prompts, tools, skills, and `pi` tiers get used in this repo's orchestration layer (Claude Code hooks + `delegate-to-pi` instrumentation), and provide a CLI/HTML report to analyze it.

**Architecture:** A single append-only JSONL event log (`var/telemetry/events.jsonl`) fed by two writers — Claude Code hooks (automatic, via a small shell script) and explicit `bin/telemetry-record` calls added to `delegate-to-pi`'s existing procedure. A Python library reads that log plus `pi`'s own pre-existing session transcripts (`~/.pi/agent/sessions/`) to derive per-delegation turn/cost metrics, and `bin/telemetry-report` renders the result as text or a static HTML dashboard.

**Tech Stack:** Bash + `jq` (writers), Python 3 stdlib only (reader/aggregator/CLI — no new pip dependencies), matching this repo's existing test style (plain `assert`-based scripts, no test framework).

## Global Constraints

- No external services, no network calls, no long-running process — everything is local files, read/written on demand.
- Logging must never block or fail real work: `bin/telemetry-record` and `.claude/hooks/telemetry-log.sh` always exit 0, swallowing their own errors into `var/telemetry/errors.log`.
- Follow this repo's existing test convention exactly: standalone executable scripts under `tests/`, `.sh` tests use `set -euo pipefail` and `rg`, `.py` tests use plain `assert` and a final print — no `pytest`, no `unittest`.
- `var/telemetry/` is gitignored (it's local usage data, not source).
- Python code is stdlib-only (`json`, `pathlib`, `argparse`, `webbrowser`, `datetime`, `collections`) — no new dependencies to install.
- Every new bash script resolves the repo root the same way `bin/pi-project` already does: `cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P` (adjust `..` depth for scripts nested deeper, e.g. `.claude/hooks/`).
- Every new bash script's log directory is overridable via a `TELEMETRY_LOG_DIR` environment variable (defaulting to `<repo_root>/var/telemetry`), so tests never touch the real log.

---

### Task 1: `bin/telemetry-record` helper

**Files:**
- Create: `bin/telemetry-record`
- Test: `tests/test-telemetry-record.sh`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `bin/telemetry-record <event> [key=value ...]` — appends one JSON line `{"ts": <iso8601>, "event": "<event>", "<key>": "<value>", ...}` to `$TELEMETRY_LOG_DIR/events.jsonl` (default `<repo_root>/var/telemetry/events.jsonl`). Always exits 0.

- [ ] **Step 1: Add `var/telemetry/` to `.gitignore`**

Add this line to `.gitignore` (alongside the existing entries):

```
var/telemetry/
```

- [ ] **Step 2: Write `bin/telemetry-record`**

```bash
#!/usr/bin/env bash
set -uo pipefail

readonly project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly log_dir="${TELEMETRY_LOG_DIR:-$project_root/var/telemetry}"
readonly log_file="$log_dir/events.jsonl"
readonly error_log="$log_dir/errors.log"

record() {
  local event="$1"
  shift

  mkdir -p "$log_dir"

  local jq_args=(--arg event "$event")
  local jq_filter='{ts: (now | todateiso8601), event: $event}'

  local pair key value arg_name
  for pair in "$@"; do
    if [[ "$pair" != *=* ]]; then
      printf 'bad key=value argument: %s\n' "$pair" >&2
      return 1
    fi
    key="${pair%%=*}"
    value="${pair#*=}"
    arg_name="field_${key}"
    jq_args+=(--arg "$arg_name" "$value")
    jq_filter+=" + {\"${key}\": \$${arg_name}}"
  done

  jq -n "${jq_args[@]}" "$jq_filter" >> "$log_file"
}

if [[ $# -lt 1 ]]; then
  printf 'usage: telemetry-record <event> [key=value ...]\n' >&2
  exit 0
fi

mkdir -p "$log_dir" 2>/dev/null || true

if ! record "$@" 2>>"$error_log"; then
  printf '%s telemetry-record failed for event %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" >>"$error_log" 2>/dev/null || true
fi

exit 0
```

Make it executable: `chmod +x bin/telemetry-record`

- [ ] **Step 3: Write `tests/test-telemetry-record.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

readonly project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly launcher="$project_root/bin/telemetry-record"
readonly temp_dir="$(mktemp -d)"
trap 'rm -rf "$temp_dir"' EXIT

TELEMETRY_LOG_DIR="$temp_dir" "$launcher" pi_spawn trace_id=abc-123 tier=M

readonly log_file="$temp_dir/events.jsonl"
if [[ ! -f "$log_file" ]]; then
  printf 'expected %s to exist\n' "$log_file" >&2
  exit 1
fi

readonly line="$(cat "$log_file")"
event="$(jq -r '.event' <<<"$line")"
trace_id="$(jq -r '.trace_id' <<<"$line")"
tier="$(jq -r '.tier' <<<"$line")"
ts="$(jq -r '.ts' <<<"$line")"

[[ "$event" == "pi_spawn" ]] || { printf 'expected event pi_spawn, got %s\n' "$event" >&2; exit 1; }
[[ "$trace_id" == "abc-123" ]] || { printf 'expected trace_id abc-123, got %s\n' "$trace_id" >&2; exit 1; }
[[ "$tier" == "M" ]] || { printf 'expected tier M, got %s\n' "$tier" >&2; exit 1; }
[[ -n "$ts" && "$ts" != "null" ]] || { printf 'expected a non-null ts\n' >&2; exit 1; }

# A second call appends rather than overwrites.
TELEMETRY_LOG_DIR="$temp_dir" "$launcher" pi_delegation_end trace_id=abc-123 outcome=goal_met
[[ "$(wc -l < "$log_file" | tr -d ' ')" == "2" ]] || { printf 'expected 2 lines after second call\n' >&2; exit 1; }

# Bad input (no key=value form) must still exit 0 and never crash the caller.
set +e
TELEMETRY_LOG_DIR="$temp_dir" "$launcher" pi_spawn not-a-pair
bad_input_exit=$?
set -e
[[ "$bad_input_exit" -eq 0 ]] || { printf 'expected exit 0 after bad input, got %s\n' "$bad_input_exit" >&2; exit 1; }

printf '%s\n' 'test-telemetry-record: PASS'
```

Make it executable: `chmod +x tests/test-telemetry-record.sh`

- [ ] **Step 4: Run the test and verify it passes**

Run: `./tests/test-telemetry-record.sh`
Expected: `test-telemetry-record: PASS` (and `exit code after bad input: 0`)

- [ ] **Step 5: Commit**

```bash
git add bin/telemetry-record tests/test-telemetry-record.sh .gitignore
git commit -m "feat: add telemetry-record helper for appending telemetry events"
```

---

### Task 2: `bin/telemetry-lookup-pi-session` helper

**Files:**
- Create: `bin/telemetry-lookup-pi-session`
- Test: `tests/test-telemetry-lookup-pi-session.sh`

**Interfaces:**
- Consumes: the same `$TELEMETRY_LOG_DIR/events.jsonl` format written by Task 1's `telemetry-record`.
- Produces: `bin/telemetry-lookup-pi-session <herdr_name> <cwd>` — prints the `pi_session_id` of the most recent `pi_spawn` event matching both arguments to stdout and exits 0; exits 1 with no stdout if none found.

- [ ] **Step 1: Write `bin/telemetry-lookup-pi-session`**

```bash
#!/usr/bin/env bash
set -uo pipefail

readonly project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly log_dir="${TELEMETRY_LOG_DIR:-$project_root/var/telemetry}"
readonly log_file="$log_dir/events.jsonl"

if [[ $# -ne 2 ]]; then
  printf 'usage: telemetry-lookup-pi-session <herdr_name> <cwd>\n' >&2
  exit 1
fi

herdr_name="$1"
cwd="$2"

if [[ ! -f "$log_file" ]]; then
  exit 1
fi

result="$(jq -r --arg name "$herdr_name" --arg cwd "$cwd" '
  select(.event == "pi_spawn" and .herdr_name == $name and .cwd == $cwd)
  | .pi_session_id
' "$log_file" 2>/dev/null | tail -n 1)"

if [[ -z "$result" || "$result" == "null" ]]; then
  exit 1
fi

printf '%s\n' "$result"
```

Make it executable: `chmod +x bin/telemetry-lookup-pi-session`

- [ ] **Step 2: Write `tests/test-telemetry-lookup-pi-session.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

readonly project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly launcher="$project_root/bin/telemetry-lookup-pi-session"
readonly temp_dir="$(mktemp -d)"
trap 'rm -rf "$temp_dir"' EXIT

cat > "$temp_dir/events.jsonl" <<'EOF'
{"ts":"2026-01-01T00:00:00Z","event":"pi_spawn","herdr_name":"pi-isolated-worker-M","cwd":"/repo","pi_session_id":"session-old"}
{"ts":"2026-01-01T00:00:00Z","event":"pi_spawn","herdr_name":"pi-isolated-worker-S","cwd":"/repo","pi_session_id":"session-other-tier"}
{"ts":"2026-01-02T00:00:00Z","event":"pi_spawn","herdr_name":"pi-isolated-worker-M","cwd":"/repo","pi_session_id":"session-new"}
EOF

result="$(TELEMETRY_LOG_DIR="$temp_dir" "$launcher" "pi-isolated-worker-M" "/repo")"
[[ "$result" == "session-new" ]] || { printf 'expected session-new, got %s\n' "$result" >&2; exit 1; }

if TELEMETRY_LOG_DIR="$temp_dir" "$launcher" "pi-isolated-worker-L" "/repo" >/dev/null 2>&1; then
  printf 'expected non-zero exit for no match\n' >&2
  exit 1
fi

printf '%s\n' 'test-telemetry-lookup-pi-session: PASS'
```

Make it executable: `chmod +x tests/test-telemetry-lookup-pi-session.sh`

- [ ] **Step 3: Run the test and verify it passes**

Run: `./tests/test-telemetry-lookup-pi-session.sh`
Expected: `test-telemetry-lookup-pi-session: PASS`

- [ ] **Step 4: Commit**

```bash
git add bin/telemetry-lookup-pi-session tests/test-telemetry-lookup-pi-session.sh
git commit -m "feat: add telemetry-lookup-pi-session helper for agent-reuse correlation"
```

---

### Task 3: Claude Code hook script

**Files:**
- Create: `.claude/hooks/telemetry-log.sh`
- Test: `tests/test-telemetry-log-hook.sh`

**Interfaces:**
- Consumes: a Claude Code hook JSON payload on stdin (fields per event: `hook_event_name`, `session_id`, plus `source`/`reason`/`prompt`/`prompt_text`/`tool_name`/`tool_input`/`tool_use_succeeded` depending on event).
- Produces: appends one JSON line to `$TELEMETRY_LOG_DIR/events.jsonl` per the event-type mapping below; always exits 0.

- [ ] **Step 1: Write `.claude/hooks/telemetry-log.sh`**

```bash
#!/usr/bin/env bash
set -uo pipefail

readonly project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
readonly log_dir="${TELEMETRY_LOG_DIR:-$project_root/var/telemetry}"
readonly log_file="$log_dir/events.jsonl"
readonly error_log="$log_dir/errors.log"

main() {
  local payload
  payload="$(cat)"

  mkdir -p "$log_dir"

  local event_name
  event_name="$(jq -r '.hook_event_name // empty' <<<"$payload" 2>/dev/null)"

  local record=""
  case "$event_name" in
    SessionStart)
      record="$(jq -c '{event: "session_start", ts: (now|todateiso8601), session_id: (.session_id // null), source: (.source // null)}' <<<"$payload" 2>/dev/null)"
      ;;
    SessionEnd)
      record="$(jq -c '{event: "session_end", ts: (now|todateiso8601), session_id: (.session_id // null), reason: (.reason // null)}' <<<"$payload" 2>/dev/null)"
      ;;
    UserPromptSubmit)
      record="$(jq -c '{event: "prompt_submitted", ts: (now|todateiso8601), session_id: (.session_id // null), prompt: (.prompt // .prompt_text // null)}' <<<"$payload" 2>/dev/null)"
      ;;
    PostToolUse)
      record="$(jq -c '{event: "tool_call", ts: (now|todateiso8601), session_id: (.session_id // null), tool_name: (.tool_name // null), success: (.tool_use_succeeded // null), tool_input: (.tool_input // null)}' <<<"$payload" 2>/dev/null)"
      ;;
    *)
      return 0
      ;;
  esac

  if [[ -n "$record" ]]; then
    printf '%s\n' "$record" >> "$log_file"
  fi
}

main 2>>"$error_log"
exit 0
```

Make it executable: `chmod +x .claude/hooks/telemetry-log.sh`

- [ ] **Step 2: Write `tests/test-telemetry-log-hook.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

readonly project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly hook="$project_root/.claude/hooks/telemetry-log.sh"
readonly temp_dir="$(mktemp -d)"
trap 'rm -rf "$temp_dir"' EXIT

run_hook() {
  TELEMETRY_LOG_DIR="$temp_dir" "$hook" <<<"$1"
}

run_hook '{"hook_event_name":"SessionStart","session_id":"s1","source":"startup"}'
run_hook '{"hook_event_name":"UserPromptSubmit","session_id":"s1","prompt":"do the thing"}'
run_hook '{"hook_event_name":"PostToolUse","session_id":"s1","tool_name":"Skill","tool_input":{"skill":"delegate-to-pi"},"tool_use_succeeded":true}'
run_hook '{"hook_event_name":"SessionEnd","session_id":"s1","reason":"other"}'
run_hook 'not json at all'
run_hook '{"hook_event_name":"Notification","session_id":"s1"}'

readonly log_file="$temp_dir/events.jsonl"
[[ "$(wc -l < "$log_file" | tr -d ' ')" == "4" ]] || { printf 'expected 4 recorded lines, got:\n%s\n' "$(cat "$log_file")" >&2; exit 1; }

session_start_source="$(jq -r 'select(.event=="session_start").source' "$log_file")"
[[ "$session_start_source" == "startup" ]] || { printf 'expected source startup, got %s\n' "$session_start_source" >&2; exit 1; }

prompt="$(jq -r 'select(.event=="prompt_submitted").prompt' "$log_file")"
[[ "$prompt" == "do the thing" ]] || { printf 'expected prompt text, got %s\n' "$prompt" >&2; exit 1; }

skill_name="$(jq -r 'select(.event=="tool_call").tool_input.skill' "$log_file")"
[[ "$skill_name" == "delegate-to-pi" ]] || { printf 'expected skill delegate-to-pi, got %s\n' "$skill_name" >&2; exit 1; }

reason="$(jq -r 'select(.event=="session_end").reason' "$log_file")"
[[ "$reason" == "other" ]] || { printf 'expected reason other, got %s\n' "$reason" >&2; exit 1; }

printf '%s\n' 'test-telemetry-log-hook: PASS'
```

Make it executable: `chmod +x tests/test-telemetry-log-hook.sh`

- [ ] **Step 3: Run the test and verify it passes**

Run: `./tests/test-telemetry-log-hook.sh`
Expected: `test-telemetry-log-hook: PASS`

- [ ] **Step 4: Commit**

```bash
git add .claude/hooks/telemetry-log.sh tests/test-telemetry-log-hook.sh
git commit -m "feat: add Claude Code hook script for telemetry capture"
```

---

### Task 4: Wire hooks into `.claude/settings.json`

**Files:**
- Modify: `.claude/settings.json`

**Interfaces:**
- Consumes: `.claude/hooks/telemetry-log.sh` from Task 3.

- [ ] **Step 1: Add the `hooks` key**

Modify `.claude/settings.json` to add a `"hooks"` key alongside the existing `enabledPlugins`/`skillOverrides` keys (do not remove or reorder those):

```json
{
  "enabledPlugins": {
    "aws-dev-toolkit@claude-plugins-official": false,
    "codex@openai-codex": false,
    "engineering@knowledge-work-plugins": false,
    "productivity@knowledge-work-plugins": false,
    "sales@knowledge-work-plugins": false,
    "security-guidance@claude-plugins-official": false,
    "superpowers@claude-plugins-official": false,
    "plugin-dev@claude-plugins-official": false
  },
  "skillOverrides": {
    "axi": "off",
    "last30days": "off",
    "learn": "off",
    "no-mistakes": "off",
    "skill-installer": "off",
    "use-railway": "off"
  },
  "hooks": {
    "PostToolUse": [
      { "matcher": "*", "hooks": [{ "type": "command", "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/telemetry-log.sh" }] }
    ],
    "UserPromptSubmit": [
      { "hooks": [{ "type": "command", "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/telemetry-log.sh" }] }
    ],
    "SessionStart": [
      { "hooks": [{ "type": "command", "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/telemetry-log.sh" }] }
    ],
    "SessionEnd": [
      { "hooks": [{ "type": "command", "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/telemetry-log.sh" }] }
    ]
  }
}
```

- [ ] **Step 2: Validate the JSON**

Run: `jq empty .claude/settings.json && echo VALID`
Expected: `VALID` (no parse error)

- [ ] **Step 3: Confirm the hook script is referenced and executable**

Run: `jq -r '.hooks.PostToolUse[0].hooks[0].command' .claude/settings.json`
Expected: `${CLAUDE_PROJECT_DIR}/.claude/hooks/telemetry-log.sh`

Run: `test -x .claude/hooks/telemetry-log.sh && echo EXECUTABLE`
Expected: `EXECUTABLE`

- [ ] **Step 4: Commit**

```bash
git add .claude/settings.json
git commit -m "feat: register telemetry hooks in Claude Code settings"
```

*(Live confirmation that Claude Code actually fires these hooks happens in Task 12's manual end-to-end check — settings.json wiring can't be exercised by an automated test on its own.)*

---

### Task 5: `lib/telemetry/events.py` — event log reader

**Files:**
- Create: `lib/telemetry/__init__.py` (empty)
- Create: `lib/telemetry/events.py`
- Test: `tests/test-telemetry-events.py`

**Interfaces:**
- Produces: `read_events(path: pathlib.Path) -> Iterator[dict]` — yields each valid JSON object from a JSONL file in order; skips and warns (to stderr) on malformed lines; yields nothing if the file doesn't exist.

- [ ] **Step 1: Create the empty package file**

Create `lib/telemetry/__init__.py` with no content.

- [ ] **Step 2: Write the failing test — `tests/test-telemetry-events.py`**

```python
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
```

Make it executable: `chmod +x tests/test-telemetry-events.py`

- [ ] **Step 3: Run it to verify it fails**

Run: `python3 tests/test-telemetry-events.py`
Expected: `ModuleNotFoundError: No module named 'telemetry'`

- [ ] **Step 4: Write `lib/telemetry/events.py`**

```python
"""Read the append-only telemetry event log."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterator


def read_events(path: Path) -> Iterator[dict]:
    """Yield each valid JSON object from a JSONL event log.

    Lines that fail to parse are skipped with a warning printed to
    stderr, rather than aborting the whole read.
    """
    if not path.exists():
        return

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                print(
                    f"telemetry: skipping malformed line {line_number} in {path}: {exc}",
                    file=sys.stderr,
                )
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `python3 tests/test-telemetry-events.py`
Expected: `test-telemetry-events: PASS`

- [ ] **Step 6: Commit**

```bash
git add lib/telemetry/__init__.py lib/telemetry/events.py tests/test-telemetry-events.py
git commit -m "feat: add telemetry event log reader"
```

---

### Task 6: `lib/telemetry/pi_sessions.py` — pi transcript parsing

**Files:**
- Create: `lib/telemetry/pi_sessions.py`
- Test: `tests/test-telemetry-pi-sessions.py`

**Interfaces:**
- Produces:
  - `find_session_file(sessions_root: Path, pi_session_id: str) -> Path | None`
  - `load_session_messages(path: Path) -> list[dict]`
  - `slice_by_window(messages: list[dict], start_ts: str, end_ts: str | None) -> list[dict]`
  - `derive_metrics(messages: list[dict]) -> dict` with keys `turn_count: int`, `tool_call_counts: dict[str, int]`, `total_cost: float`

- [ ] **Step 1: Write the failing test — `tests/test-telemetry-pi-sessions.py`**

```python
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
    '{"type":"message","timestamp":"2026-01-01T00:00:06Z","message":{"role":"assistant","content":[{"type":"toolCall","name":"bash"}]},"usage":{"cost":{"total":0.02}}}',
    '{"type":"message","timestamp":"2026-01-01T00:00:07Z","message":{"role":"user","content":[{"type":"text","text":"again"}]}}',
    '{"type":"message","timestamp":"2026-01-01T00:00:08Z","message":{"role":"assistant","content":[{"type":"toolCall","name":"bash"}]},"usage":{"cost":{"total":0.03}}}',
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
```

Make it executable: `chmod +x tests/test-telemetry-pi-sessions.py`

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 tests/test-telemetry-pi-sessions.py`
Expected: `ModuleNotFoundError: No module named 'telemetry.pi_sessions'` (or ImportError)

- [ ] **Step 3: Write `lib/telemetry/pi_sessions.py`**

```python
"""Parse pi's own session transcripts to derive delegation metrics."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional


def find_session_file(sessions_root: Path, pi_session_id: str) -> Optional[Path]:
    """Find a pi session file whose name contains the given session id."""
    if not sessions_root.exists():
        return None
    matches = sorted(sessions_root.glob(f"**/*{pi_session_id}*.jsonl"))
    return matches[0] if matches else None


def load_session_messages(path: Path) -> list[dict]:
    """Parse every JSON line in a pi session file."""
    messages = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                messages.append(json.loads(line))
    return messages


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def slice_by_window(
    messages: list[dict], start_ts: str, end_ts: Optional[str]
) -> list[dict]:
    """Keep only entries timestamped within [start_ts, end_ts].

    end_ts=None means unbounded (still open / no delegation-end recorded
    yet).
    """
    start = _parse_ts(start_ts)
    end = _parse_ts(end_ts) if end_ts else None

    sliced = []
    for entry in messages:
        raw_ts = entry.get("timestamp")
        if not raw_ts:
            continue
        entry_ts = _parse_ts(raw_ts)
        if entry_ts < start:
            continue
        if end is not None and entry_ts > end:
            continue
        sliced.append(entry)
    return sliced


def derive_metrics(messages: list[dict]) -> dict:
    """Derive turn count, tool-call counts, and total cost from a message slice."""
    turn_count = 0
    tool_call_counts: dict = {}
    total_cost = 0.0

    for entry in messages:
        if entry.get("type") != "message":
            continue
        message = entry.get("message", {})
        role = message.get("role")

        if role == "user":
            turn_count += 1

        if role == "assistant":
            usage = entry.get("usage") or {}
            cost = (usage.get("cost") or {}).get("total")
            if cost:
                total_cost += cost

            for item in message.get("content", []):
                if item.get("type") == "toolCall":
                    name = item.get("name", "unknown")
                    tool_call_counts[name] = tool_call_counts.get(name, 0) + 1

    return {
        "turn_count": turn_count,
        "tool_call_counts": tool_call_counts,
        "total_cost": total_cost,
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 tests/test-telemetry-pi-sessions.py`
Expected: `test-telemetry-pi-sessions: PASS`

- [ ] **Step 5: Commit**

```bash
git add lib/telemetry/pi_sessions.py tests/test-telemetry-pi-sessions.py
git commit -m "feat: add pi session transcript parser for delegation metrics"
```

---

### Task 7: `lib/telemetry/aggregate.py` — combine both sources

**Files:**
- Create: `lib/telemetry/aggregate.py`
- Test: `tests/test-telemetry-aggregate.py`

**Interfaces:**
- Consumes: `read_events` (Task 5); `find_session_file`, `load_session_messages`, `slice_by_window`, `derive_metrics` (Task 6).
- Produces: `DEFAULT_SESSIONS_ROOT: Path` and `build_report(events_path: Path, sessions_root: Path | None = None) -> dict` with keys `tool_call_counts`, `skill_call_counts`, `tier_distribution`, `avg_turns_per_tier`, `outcome_counts`, `fallback_count`, `escalated_count`, `turn_cap_count`, `total_pi_cost`.

- [ ] **Step 1: Write the failing test — `tests/test-telemetry-aggregate.py`**

```python
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
    '{"ts":"2026-01-01T00:10:00Z","event":"pi_delegation_end","trace_id":"t1","outcome":"goal_met"}',
]

SESSION_LINES = [
    '{"type":"message","timestamp":"2026-01-01T00:00:05Z","message":{"role":"user","content":[]}}',
    '{"type":"message","timestamp":"2026-01-01T00:00:06Z","message":{"role":"assistant","content":[{"type":"toolCall","name":"bash"}]},"usage":{"cost":{"total":0.02}}}',
    '{"type":"message","timestamp":"2026-01-01T00:00:07Z","message":{"role":"user","content":[]}}',
    '{"type":"message","timestamp":"2026-01-01T00:00:08Z","message":{"role":"assistant","content":[{"type":"toolCall","name":"bash"}]},"usage":{"cost":{"total":0.03}}}',
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

    report = build_report(events_path, sessions_root)

    assert report["tool_call_counts"] == {"Bash": 2, "Skill": 1}, report
    assert report["skill_call_counts"] == {"delegate-to-pi": 1}, report
    assert report["tier_distribution"] == {"M": 1}, report
    assert report["avg_turns_per_tier"] == {"M": 2.0}, report
    assert report["outcome_counts"] == {"goal_met": 1}, report
    assert report["fallback_count"] == 0, report
    assert report["escalated_count"] == 0, report
    assert report["turn_cap_count"] == 0, report
    assert abs(report["total_pi_cost"] - 0.05) < 1e-9, report

print("test-telemetry-aggregate: PASS")
```

Make it executable: `chmod +x tests/test-telemetry-aggregate.py`

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 tests/test-telemetry-aggregate.py`
Expected: `ModuleNotFoundError: No module named 'telemetry.aggregate'`

- [ ] **Step 3: Write `lib/telemetry/aggregate.py`**

```python
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
        elif kind == "pi_escalated":
            by_trace[trace_id]["escalated"] = True
        elif kind == "pi_turn_cap_hit":
            by_trace[trace_id]["turn_cap_hit"] = True

    tier_distribution: Counter = Counter()
    turns_by_tier: dict = defaultdict(list)
    outcome_counts: Counter = Counter()
    fallback_count = 0
    escalated_count = 0
    turn_cap_count = 0
    total_pi_cost = 0.0

    for info in by_trace.values():
        start = info.get("start")
        if start is None:
            continue

        tier = start.get("tier", "unknown")
        tier_distribution[tier] += 1

        if info.get("fallback"):
            fallback_count += 1
        if info.get("escalated"):
            escalated_count += 1
        if info.get("turn_cap_hit"):
            turn_cap_count += 1

        end = info.get("end")
        if end:
            outcome_counts[end.get("outcome", "unknown")] += 1

        pi_session_id = start.get("pi_session_id")
        if not pi_session_id:
            continue
        session_file = find_session_file(sessions_root, pi_session_id)
        if session_file is None:
            continue

        messages = load_session_messages(session_file)
        sliced = slice_by_window(messages, start["ts"], end["ts"] if end else None)
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
        "fallback_count": fallback_count,
        "escalated_count": escalated_count,
        "turn_cap_count": turn_cap_count,
        "total_pi_cost": total_pi_cost,
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 tests/test-telemetry-aggregate.py`
Expected: `test-telemetry-aggregate: PASS`

- [ ] **Step 5: Commit**

```bash
git add lib/telemetry/aggregate.py tests/test-telemetry-aggregate.py
git commit -m "feat: add telemetry aggregation combining events and pi sessions"
```

---

### Task 8: `lib/telemetry/text_report.py`

**Files:**
- Create: `lib/telemetry/text_report.py`
- Test: `tests/test-telemetry-text-report.py`

**Interfaces:**
- Consumes: a report `dict` shaped exactly like `build_report`'s return value (Task 7).
- Produces: `render_text(report: dict) -> str`

- [ ] **Step 1: Write the failing test — `tests/test-telemetry-text-report.py`**

```python
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
}

text = render_text(REPORT)

assert "Bash: 2" in text, text
assert "delegate-to-pi: 1" in text, text
assert "M: 1, avg turns: 2.0" in text, text
assert "goal_met: 1" in text, text
assert "Total pi cost observed: $0.0500" in text, text

print("test-telemetry-text-report: PASS")
```

Make it executable: `chmod +x tests/test-telemetry-text-report.py`

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 tests/test-telemetry-text-report.py`
Expected: `ModuleNotFoundError: No module named 'telemetry.text_report'`

- [ ] **Step 3: Write `lib/telemetry/text_report.py`**

```python
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
    lines.append("=== Delegation outcomes ===")
    for outcome, count in sorted(report["outcome_counts"].items()):
        lines.append(f"  {outcome}: {count}")
    lines.append(f"  fallback used: {report['fallback_count']}")
    lines.append(f"  escalated: {report['escalated_count']}")
    lines.append(f"  turn cap hit: {report['turn_cap_count']}")

    lines.append("")
    lines.append(f"Total pi cost observed: ${report['total_pi_cost']:.4f}")

    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 tests/test-telemetry-text-report.py`
Expected: `test-telemetry-text-report: PASS`

- [ ] **Step 5: Commit**

```bash
git add lib/telemetry/text_report.py tests/test-telemetry-text-report.py
git commit -m "feat: add plain-text telemetry report renderer"
```

---

### Task 9: `lib/telemetry/dashboard.py`

**Files:**
- Create: `lib/telemetry/dashboard.py`
- Test: `tests/test-telemetry-dashboard.py`

**Interfaces:**
- Consumes: same report `dict` shape as Task 8.
- Produces: `render_html(report: dict) -> str` — a self-contained HTML document (inline CSS + inline SVG bar charts, no external requests).

- [ ] **Step 1: Write the failing test — `tests/test-telemetry-dashboard.py`**

```python
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
}

html = render_html(REPORT)

assert html.startswith("<!doctype html>"), html[:50]
assert "<svg" in html, html
assert "Bash" in html, html
assert "$0.0500" in html, html
assert "http://" not in html and "https://" not in html, "dashboard must be self-contained"
assert "<script" not in html, "no scripting needed for static bar charts"

print("test-telemetry-dashboard: PASS")
```

Make it executable: `chmod +x tests/test-telemetry-dashboard.py`

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 tests/test-telemetry-dashboard.py`
Expected: `ModuleNotFoundError: No module named 'telemetry.dashboard'`

- [ ] **Step 3: Write `lib/telemetry/dashboard.py`**

```python
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
        f'<svg width="{label_width + chart_width + 40}" height="{height}" '
        f'xmlns="http://www.w3.org/2000/svg">{"".join(rows)}</svg>'
    )
    return f"<h2>{escape(title)}</h2>{svg}"


def render_html(report: dict) -> str:
    sections = [
        _bar_chart("Tool calls", report["tool_call_counts"], "#4f7cac"),
        _bar_chart("Skill invocations", report["skill_call_counts"], "#4f7cac"),
        _bar_chart("Pi tier distribution", report["tier_distribution"], "#c96f4a"),
        _bar_chart("Delegation outcomes", report["outcome_counts"], "#5a9367"),
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 tests/test-telemetry-dashboard.py`
Expected: `test-telemetry-dashboard: PASS`

- [ ] **Step 5: Commit**

```bash
git add lib/telemetry/dashboard.py tests/test-telemetry-dashboard.py
git commit -m "feat: add static HTML telemetry dashboard renderer"
```

---

### Task 10: `bin/telemetry-report` CLI

**Files:**
- Create: `bin/telemetry-report`
- Test: `tests/test-telemetry-report-cli.py`

**Interfaces:**
- Consumes: `build_report` + `DEFAULT_SESSIONS_ROOT` (Task 7), `render_text` (Task 8), `render_html` (Task 9).
- Produces: a CLI — `telemetry-report [--events-file PATH] [--sessions-root PATH] [--html] [--out PATH] [--no-open]`.

- [ ] **Step 1: Write the failing test — `tests/test-telemetry-report-cli.py`**

```python
#!/usr/bin/env python3
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

print("test-telemetry-report-cli: PASS")
```

Make it executable: `chmod +x tests/test-telemetry-report-cli.py`

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 tests/test-telemetry-report-cli.py`
Expected: fails because `bin/telemetry-report` doesn't exist yet (`FileNotFoundError` or non-zero exit from `subprocess.run(..., check=True)`)

- [ ] **Step 3: Write `bin/telemetry-report`**

```python
#!/usr/bin/env python3
"""CLI for summarizing software-factory telemetry: text report or static HTML dashboard."""
import argparse
import sys
import webbrowser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "lib"))

from telemetry.aggregate import DEFAULT_SESSIONS_ROOT, build_report
from telemetry.dashboard import render_html
from telemetry.text_report import render_text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--events-file",
        type=Path,
        default=PROJECT_ROOT / "var" / "telemetry" / "events.jsonl",
        help="Path to the telemetry event log (default: var/telemetry/events.jsonl)",
    )
    parser.add_argument(
        "--sessions-root",
        type=Path,
        default=DEFAULT_SESSIONS_ROOT,
        help="Root directory of pi's own session transcripts",
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="Render a static HTML dashboard instead of printing a text summary",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=PROJECT_ROOT / "var" / "telemetry" / "dashboard.html",
        help="Where to write the HTML dashboard (only used with --html)",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Don't open the dashboard in a browser after writing it",
    )
    args = parser.parse_args()

    report = build_report(args.events_file, args.sessions_root)

    if not args.html:
        print(render_text(report), end="")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_html(report), encoding="utf-8")
    print(f"Dashboard written to {args.out}")

    if not args.no_open:
        webbrowser.open(args.out.as_uri())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Make it executable: `chmod +x bin/telemetry-report`

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 tests/test-telemetry-report-cli.py`
Expected: `test-telemetry-report-cli: PASS`

- [ ] **Step 5: Commit**

```bash
git add bin/telemetry-report tests/test-telemetry-report-cli.py
git commit -m "feat: add telemetry-report CLI with text and HTML output"
```

---

### Task 11: Instrument `delegate-to-pi` with telemetry recording

**Files:**
- Modify: `.claude/skills/delegate-to-pi/SKILL.md`
- Test: `tests/test-delegate-to-pi-telemetry.sh`

**Interfaces:**
- Consumes: `bin/telemetry-record` (Task 1), `bin/telemetry-lookup-pi-session` (Task 2).

- [ ] **Step 1: Generate a delegation id in §1**

In `.claude/skills/delegate-to-pi/SKILL.md`, find this paragraph (end of §1):

```
Track two pieces of state for the rest of this delegation: `TIER` (as
settled above) and a `fallback_used` flag, starting `false` — §6 sets it
to `true` the first time it fires, and checks it to decide whether a
repeat failure should retry again or escalate.
```

Add this paragraph immediately after it:

```

Also generate `DELEGATION_ID` now, once — this identifies this delegation
for telemetry and is reused in every `telemetry-record`/
`telemetry-lookup-pi-session` call below; it does not change for the rest
of this delegation.

```bash
DELEGATION_ID="$(uuidgen)"
```
```

- [ ] **Step 2: Record spawn/reuse in §2**

Find this block in §2:

```
- If one is found with `agent_status` in `{idle, done}` → reuse it. Its
  `pane_id` is your `<target>` for every step below.
- If none is found, or the only matches are anything other than `idle`/`done`
  (i.e. `working`, `blocked`, or `unknown`) → spawn a new one, using the
  `provider`/`model`/`thinking` values looked up in §1 for `TIER`:

```bash
herdr agent start pi-isolated-worker-<TIER> --cwd "$(pwd)" --split right --no-focus -- "$(git rev-parse --show-toplevel)/bin/pi-project" --provider <provider> --model <model> --thinking <thinking>
```
```

Replace it with:

```
- If one is found with `agent_status` in `{idle, done}` → reuse it. Its
  `pane_id` is your `<target>` for every step below. Record the reuse for
  telemetry — look up the pi session id this agent was originally spawned
  with, then record the reuse against a fresh delegation id:

  ```bash
  PI_SESSION_ID="$("$(git rev-parse --show-toplevel)/bin/telemetry-lookup-pi-session" "pi-isolated-worker-<TIER>" "$(pwd)")"
  "$(git rev-parse --show-toplevel)/bin/telemetry-record" pi_reuse trace_id="$DELEGATION_ID" pi_session_id="${PI_SESSION_ID:-unknown}" tier="<TIER>" herdr_name="pi-isolated-worker-<TIER>" cwd="$(pwd)"
  ```

- If none is found, or the only matches are anything other than `idle`/`done`
  (i.e. `working`, `blocked`, or `unknown`) → spawn a new one, using the
  `provider`/`model`/`thinking` values looked up in §1 for `TIER`:

```bash
herdr agent start pi-isolated-worker-<TIER> --cwd "$(pwd)" --split right --no-focus -- "$(git rev-parse --show-toplevel)/bin/pi-project" --provider <provider> --model <model> --thinking <thinking> --session-id "$DELEGATION_ID"
```
```

- [ ] **Step 3: Record the fresh spawn after profile verification in §2**

Find this text (end of §2's spawn branch, right before "**Use `pane_id` as `<target>`..."):

```
  If the displayed provider/model/thinking don't match what you requested,
  stop and show the user the mismatch verbatim — do not silently proceed
  with whatever actually launched.
```

Add this paragraph immediately after it:

```

  Once the profile is verified, record the spawn for telemetry — the
  delegation id doubles as the pi session id for a fresh spawn:

  ```bash
  "$(git rev-parse --show-toplevel)/bin/telemetry-record" pi_spawn trace_id="$DELEGATION_ID" pi_session_id="$DELEGATION_ID" tier="<TIER>" provider="<provider>" model="<model>" thinking="<thinking>" herdr_name="pi-isolated-worker-<TIER>" cwd="$(pwd)"
  ```
```

- [ ] **Step 4: Record escalation in §4**

Find this sentence in §4:

```
In that case, stop, show the user pi's exact question verbatim, and wait
for their answer before relaying anything back to pi.
```

Add this paragraph immediately after it:

```

  Record the escalation before stopping:

  ```bash
  "$(git rev-parse --show-toplevel)/bin/telemetry-record" pi_escalated trace_id="$DELEGATION_ID" reason="user_confirmation_required"
  ```
```

- [ ] **Step 5: Record the fallback spawn in §6**

Find steps 4 through 8 of §6's numbered list (the whole tail of the list, so the telemetry additions can be inserted without breaking the numbering):

```
  4. Spawn a replacement, reusing the same name (the original is now
     closed, freeing it):
     ```bash
     herdr agent start pi-isolated-worker-<TIER> --cwd "$(pwd)" --split right --no-focus -- "$(git rev-parse --show-toplevel)/bin/pi-project" --provider <fallback_provider> --model <fallback_model> --thinking <fallback_thinking>
     ```
  5. Update `<target>` to the new `pane_id` from the response.
  6. Verify the fallback profile actually took effect, same as §2's
     post-spawn check: zoom the pane, read its status bar, confirm the
     displayed provider/model/thinking match the fallback entry, un-zoom.
     Stop and show the user a mismatch verbatim rather than proceeding on
     it.
  7. Poll until settled (idle/done/blocked), same as §3.
  8. Resend the exact prompt that triggered this failure (go to §3 with
     that same prompt text — this does not skip the turn-counter increment
     described in §7; re-sending is itself a new turn).
```

Replace it with (adding a fresh session id to the respawn since it's a new `pi` process, a new step 7 to record the fallback, and renumbering the old steps 7/8 to 8/9):

```
  4. Spawn a replacement, reusing the same name (the original is now
     closed, freeing it), using a fresh session id since this is a new
     `pi` process:
     ```bash
     FALLBACK_SESSION_ID="$(uuidgen)"
     herdr agent start pi-isolated-worker-<TIER> --cwd "$(pwd)" --split right --no-focus -- "$(git rev-parse --show-toplevel)/bin/pi-project" --provider <fallback_provider> --model <fallback_model> --thinking <fallback_thinking> --session-id "$FALLBACK_SESSION_ID"
     ```
  5. Update `<target>` to the new `pane_id` from the response.
  6. Verify the fallback profile actually took effect, same as §2's
     post-spawn check: zoom the pane, read its status bar, confirm the
     displayed provider/model/thinking match the fallback entry, un-zoom.
     Stop and show the user a mismatch verbatim rather than proceeding on
     it.
  7. Record the fallback for telemetry:
     ```bash
     "$(git rev-parse --show-toplevel)/bin/telemetry-record" pi_fallback trace_id="$DELEGATION_ID" pi_session_id="$FALLBACK_SESSION_ID" provider="<fallback_provider>" model="<fallback_model>" thinking="<fallback_thinking>"
     ```
  8. Poll until settled (idle/done/blocked), same as §3.
  9. Resend the exact prompt that triggered this failure (go to §3 with
     that same prompt text — this does not skip the turn-counter increment
     described in §7; re-sending is itself a new turn).
```

- [ ] **Step 6: Record the turn-cap hit in §7**

Find this sentence in §7:

```
- If you hit the cap while the goal still isn't met, or two consecutive turns
  produced no meaningful diff/progress, stop iterating. Escalate to the user:
```

Add immediately before it:

```
- Record the turn-cap hit before escalating:

  ```bash
  "$(git rev-parse --show-toplevel)/bin/telemetry-record" pi_turn_cap_hit trace_id="$DELEGATION_ID"
  ```
```

- [ ] **Step 7: Record the outcome in §8**

Find the start of §8:

```
Whether the outcome is success, escalation, or a stuck state, tell the user:
```

Replace it with:

```
Before reporting, record the outcome for telemetry — `outcome` is
`goal_met`, `escalated`, or `stuck`, matching how this delegation actually
settled:

```bash
"$(git rev-parse --show-toplevel)/bin/telemetry-record" pi_delegation_end trace_id="$DELEGATION_ID" outcome="<goal_met|escalated|stuck>"
```

Whether the outcome is success, escalation, or a stuck state, tell the user:
```

- [ ] **Step 8: Write `tests/test-delegate-to-pi-telemetry.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

readonly project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly skill_file="$project_root/.claude/skills/delegate-to-pi/SKILL.md"

for script in bin/telemetry-record bin/telemetry-lookup-pi-session; do
  if [[ ! -x "$project_root/$script" ]]; then
    printf '%s is missing or not executable\n' "$script" >&2
    exit 1
  fi
done

rg -q -- 'DELEGATION_ID="\$\(uuidgen\)"' "$skill_file"
rg -q -- '\-\-session-id "\$DELEGATION_ID"' "$skill_file"
rg -q -- '\-\-session-id "\$FALLBACK_SESSION_ID"' "$skill_file"

for event in pi_spawn pi_reuse pi_fallback pi_escalated pi_turn_cap_hit pi_delegation_end; do
  pattern="telemetry-record\" ${event} "
  if ! rg -q -- "$pattern" "$skill_file"; then
    printf 'missing telemetry-record call for event: %s\n' "$event" >&2
    exit 1
  fi
done

rg -q -- 'telemetry-lookup-pi-session' "$skill_file"

printf '%s\n' 'test-delegate-to-pi-telemetry: PASS'
```

Make it executable: `chmod +x tests/test-delegate-to-pi-telemetry.sh`

- [ ] **Step 9: Run the test and verify it passes**

Run: `./tests/test-delegate-to-pi-telemetry.sh`
Expected: `test-delegate-to-pi-telemetry: PASS`

- [ ] **Step 10: Commit**

```bash
git add .claude/skills/delegate-to-pi/SKILL.md tests/test-delegate-to-pi-telemetry.sh
git commit -m "feat: instrument delegate-to-pi with telemetry recording"
```

---

### Task 12: Manual end-to-end verification

This exercises real Claude Code hook firing and a real (tiny) `delegate-to-pi` delegation — neither can be driven by an automated test in this repo, so this task is a documented manual check, per the spec's Testing section and the `verification-before-completion` skill.

**Files:** none (verification only).

- [ ] **Step 1: Run the full automated test suite first**

```bash
for t in tests/test-*.sh; do "$t"; done
for t in tests/test-*.py; do python3 "$t"; done
```

Expected: every test prints its own `PASS` line and nothing exits non-zero.

- [ ] **Step 2: Confirm hooks fire in a live session**

Start a fresh Claude Code session in this repo (so `SessionStart` fires), run one ordinary tool call (e.g. `ls`) and invoke one skill (e.g. `Skill: brainstorming` on a throwaway topic, or any skill already in use), then end the session. Inspect the log:

```bash
cat var/telemetry/events.jsonl | jq -c .
```

Expected: at least one `session_start`, one `tool_call` (for the `ls`/Bash call), and one `tool_call` with `tool_name == "Skill"`.

- [ ] **Step 3: Confirm a real delegation gets recorded**

Run a small, real `delegate-to-pi` delegation (an S-tier, low-risk goal — e.g. fix a typo or trivial one-line change) inside this repo. After it settles:

```bash
grep -E '"event":"pi_(spawn|delegation_end)"' var/telemetry/events.jsonl | tail -2
```

Expected: a `pi_spawn` event with the chosen tier/profile, and a `pi_delegation_end` event with `outcome: "goal_met"` (assuming the delegation succeeded), sharing the same `trace_id`.

- [ ] **Step 4: Confirm the report reflects it**

```bash
bin/telemetry-report
bin/telemetry-report --html --no-open
open var/telemetry/dashboard.html
```

Expected: the text summary shows the tool/skill calls from Step 2 and the tier/outcome from Step 3; the dashboard opens in a browser and shows matching bar charts.

- [ ] **Step 5: Report results to the user**

Summarize what was verified (which events appeared, whether counts matched expectations) so the user can confirm this before considering the feature done. Do not claim success without having actually looked at the log and report output from Steps 2–4.
