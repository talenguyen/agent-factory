#!/usr/bin/env bash
set -uo pipefail

# Resolve git metadata from this script's repository, not the caller's cwd.
# git-common-dir keeps linked worktrees on the shared main-checkout log.
readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly project_root="$(cd -- "$script_dir" && cd -- "$(dirname -- "$(git rev-parse --git-common-dir)")" && pwd -P)"
readonly log_dir="${TELEMETRY_LOG_DIR:-$project_root/var/telemetry}"
readonly log_file="$log_dir/events.jsonl"
readonly error_log="$log_dir/errors.log"

mkdir -p "$log_dir" 2>/dev/null || true

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
      record="$(jq -c '{event: "tool_call", ts: (now|todateiso8601), session_id: (.session_id // null), tool_name: (.tool_name // null), success: (.tool_use_succeeded // null), tool_input: (if .tool_name == "Skill" then {skill: (.tool_input.skill // null)} else null end)}' <<<"$payload" 2>/dev/null)"
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
