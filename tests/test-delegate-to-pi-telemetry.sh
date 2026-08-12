#!/usr/bin/env bash
set -euo pipefail

readonly root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"

# Session derivation and telemetry fields are state-machine behavior, not
# skill prose. The mock adapter exercises persistent role IDs, fresh scouts,
# spawn/reuse/fallback telemetry, and the canonical event set.
for check in \
  test_role_sessions_are_distinct_and_scout_is_fresh \
  test_telemetry_uses_exactly_the_canonical_eight_events \
  test_state_ledger_and_telemetry_are_shared_and_isolated; do
  python3 "$root/tests/test-crew.py" "$check"
done
bash "$root/tests/test-telemetry-lookup-pi-session.sh"

printf '%s\n' 'test-delegate-to-pi-telemetry: PASS'
