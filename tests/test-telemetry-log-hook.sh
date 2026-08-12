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
run_hook '{"hook_event_name":"PostToolUse","session_id":"s1","tool_name":"Bash","tool_input":{"command":"deploy --token hunter2-should-not-be-logged"},"tool_use_succeeded":true}'
run_hook '{"hook_event_name":"SessionEnd","session_id":"s1","reason":"other"}'
run_hook 'not json at all'
run_hook '{"hook_event_name":"Notification","session_id":"s1"}'

readonly log_file="$temp_dir/events.jsonl"
[[ "$(wc -l < "$log_file" | tr -d ' ')" == "5" ]] || { printf 'expected 5 recorded lines, got:\n%s\n' "$(cat "$log_file")" >&2; exit 1; }

session_start_source="$(jq -r 'select(.event=="session_start").source' "$log_file")"
[[ "$session_start_source" == "startup" ]] || { printf 'expected source startup, got %s\n' "$session_start_source" >&2; exit 1; }

prompt="$(jq -r 'select(.event=="prompt_submitted").prompt' "$log_file")"
[[ "$prompt" == "do the thing" ]] || { printf 'expected prompt text, got %s\n' "$prompt" >&2; exit 1; }

skill_name="$(jq -r 'select(.event=="tool_call" and .tool_name=="Skill").tool_input.skill' "$log_file")"
[[ "$skill_name" == "delegate-to-pi" ]] || { printf 'expected skill delegate-to-pi, got %s\n' "$skill_name" >&2; exit 1; }

# A non-Skill tool call must not carry its tool_input into the log at all:
# Bash commands and Write/Edit bodies can contain credentials or file contents.
bash_tool_input="$(jq -r 'select(.event=="tool_call" and .tool_name=="Bash").tool_input' "$log_file")"
[[ "$bash_tool_input" == "null" ]] || { printf 'expected null tool_input for a non-Skill tool call, got %s\n' "$bash_tool_input" >&2; exit 1; }
if grep -q 'hunter2-should-not-be-logged' "$log_file"; then
  printf 'non-Skill tool_input leaked into the log\n' >&2
  exit 1
fi

reason="$(jq -r 'select(.event=="session_end").reason' "$log_file")"
[[ "$reason" == "other" ]] || { printf 'expected reason other, got %s\n' "$reason" >&2; exit 1; }

# Test case: non-existent directory should be created automatically
readonly nonexistent_dir="/tmp/test-telemetry-nonexistent-$$"
rm -rf "$nonexistent_dir"
[[ ! -d "$nonexistent_dir" ]] || { printf 'cleanup failed: directory still exists\n' >&2; exit 1; }

TELEMETRY_LOG_DIR="$nonexistent_dir" "$hook" <<<"$(jq -n '{hook_event_name: "SessionStart", session_id: "s2", source: "test"}')"
readonly nonexistent_log="$nonexistent_dir/events.jsonl"
[[ -f "$nonexistent_log" ]] || { printf 'expected log file to be created at %s\n' "$nonexistent_log" >&2; exit 1; }
[[ "$(wc -l < "$nonexistent_log" | tr -d ' ')" == "1" ]] || { printf 'expected 1 line in newly created log\n' >&2; exit 1; }
rm -rf "$nonexistent_dir"

printf '%s\n' 'test-telemetry-log-hook: PASS'
