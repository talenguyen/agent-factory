#!/usr/bin/env bash
set -euo pipefail

readonly root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly extension="$root/.pi/extensions/claude-telemetry-compat.ts"

[[ -f "$extension" ]] || {
  printf 'missing extension: %s\n' "$extension" >&2
  exit 1
}
grep -F 'pi.on("session_start"' "$extension"
grep -F 'pi.on("input"' "$extension"
grep -F 'pi.on("tool_execution_end"' "$extension"
grep -F 'pi.on("session_shutdown"' "$extension"
grep -F 'hook_event_name: "SessionStart"' "$extension"
grep -F 'hook_event_name: "UserPromptSubmit"' "$extension"
grep -F 'hook_event_name: "PostToolUse"' "$extension"
grep -F 'hook_event_name: "SessionEnd"' "$extension"
grep -F 'tool_use_succeeded: !event.isError' "$extension"
grep -F 'child.stdin.end(JSON.stringify(payload))' "$extension"
printf '%s\n' 'test-pi-claude-telemetry-extension: PASS'
