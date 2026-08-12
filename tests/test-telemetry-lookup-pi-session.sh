#!/usr/bin/env bash
set -euo pipefail

readonly project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly launcher="$project_root/bin/telemetry-lookup-pi-session"
readonly temp_dir="$(mktemp -d)"
trap 'rm -rf "$temp_dir"' EXIT

cat > "$temp_dir/events.jsonl" <<'EOF'
{"ts":"2026-01-01T00:00:00Z","event":"pi_spawn","herdr_name":"crew-worker-M","cwd":"/repo","pi_session_id":"session-old"}
{"ts":"2026-01-01T00:00:00Z","event":"pi_spawn","herdr_name":"crew-worker-S","cwd":"/repo","pi_session_id":"session-other-tier"}
{"ts":"2026-01-02T00:00:00Z","event":"pi_spawn","herdr_name":"crew-worker-M","cwd":"/repo","pi_session_id":"session-new"}
EOF

result="$(TELEMETRY_LOG_DIR="$temp_dir" "$launcher" "crew-worker-M" "/repo")"
[[ "$result" == "session-new" ]] || { printf 'expected session-new, got %s\n' "$result" >&2; exit 1; }

if TELEMETRY_LOG_DIR="$temp_dir" "$launcher" "crew-worker-L" "/repo" >/dev/null 2>&1; then
  printf 'expected non-zero exit for no match\n' >&2
  exit 1
fi

printf '%s\n' 'test-telemetry-lookup-pi-session: PASS'
