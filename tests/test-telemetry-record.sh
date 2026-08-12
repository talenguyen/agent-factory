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
