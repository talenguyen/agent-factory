#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
temp_dir="$(mktemp -d)"
clone_root="$temp_dir/factory-clone"
linked_worktree="$temp_dir/linked-worktree"
cleanup() {
  git -C "$clone_root" worktree remove --force "$linked_worktree" >/dev/null 2>&1 || true
  rm -rf "$temp_dir"
}
trap cleanup EXIT

# The test's own clone is the factory under test. The real factory log must
# contain no record marked as this test, regardless of concurrent writers.
real_shared_root="$(cd "$root" && cd -- "$(dirname -- "$(git rev-parse --git-common-dir)")" && pwd -P)"
real_factory_log="$real_shared_root/var/telemetry/events.jsonl"
selftest_marker="telemetry-sink-selftest-$(uuidgen)"
git clone --no-hardlinks --local "$root" "$clone_root" >/dev/null
launcher="$clone_root/bin/telemetry-record"
hook="$clone_root/.claude/hooks/telemetry-log.sh"
clone_log="$clone_root/var/telemetry/events.jsonl"

unrelated_repo="$temp_dir/unrelated"
unrelated_trace="$selftest_marker-unrelated"
git init -q "$unrelated_repo"
(
  cd "$unrelated_repo"
  "$launcher" pi_spawn "trace_id=$unrelated_trace"
)
jq -e --arg trace_id "$unrelated_trace" 'select(.event == "pi_spawn" and .trace_id == $trace_id)' "$clone_log" >/dev/null || {
  echo 'telemetry from an unrelated repo did not reach the cloned factory log' >&2
  exit 1
}
[[ ! -e "$unrelated_repo/var" ]] || { echo 'telemetry created var/ in an unrelated repo' >&2; exit 1; }

git -C "$clone_root" worktree add --detach "$linked_worktree" HEAD >/dev/null
linked_trace="$selftest_marker-linked"
(
  cd "$linked_worktree"
  "$linked_worktree/bin/telemetry-record" pi_spawn "trace_id=$linked_trace"
)
jq -e --arg trace_id "$linked_trace" 'select(.event == "pi_spawn" and .trace_id == $trace_id)' "$clone_log" >/dev/null || {
  echo 'telemetry from a linked worktree did not reach the cloned shared log' >&2
  exit 1
}
[[ ! -e "$linked_worktree/var" ]] || { echo 'telemetry created var/ in a linked worktree' >&2; exit 1; }

record_override="$temp_dir/record-override"
TELEMETRY_LOG_DIR="$record_override" "$launcher" pi_spawn "trace_id=$selftest_marker-override"
jq -e --arg trace_id "$selftest_marker-override" 'select(.event == "pi_spawn" and .trace_id == $trace_id)' "$record_override/events.jsonl" >/dev/null || {
  echo 'TELEMETRY_LOG_DIR did not override telemetry-record' >&2
  exit 1
}

hook_override="$temp_dir/hook-override"
TELEMETRY_LOG_DIR="$hook_override" "$hook" <<<"{\"hook_event_name\":\"SessionStart\",\"session_id\":\"$selftest_marker-hook\"}"
jq -e --arg session_id "$selftest_marker-hook" 'select(.event == "session_start" and .session_id == $session_id)' "$hook_override/events.jsonl" >/dev/null || {
  echo 'TELEMETRY_LOG_DIR did not override telemetry-log hook' >&2
  exit 1
}

if [[ -f "$real_factory_log" ]] && rg -Fq "$selftest_marker" "$real_factory_log"; then
  echo 'telemetry-sink test appended a marked record to the real factory log' >&2
  exit 1
fi

printf '%s\n' 'test-telemetry-sink: PASS'
