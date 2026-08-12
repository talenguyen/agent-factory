#!/usr/bin/env bash
set -euo pipefail

readonly root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"

# Mechanism assertions retired from delegate-to-pi are executable crew
# contracts: profile fail-loudness, ledger anchoring, stale-status debounce,
# exact caps, fallback isolation, and literal verdict accounting.
for check in \
  test_profile_resolution_skips_absent_and_stops_malformed \
  test_profile_local_source_wins_over_project_source \
  test_profile_project_source_wins_when_local_is_absent \
  test_profile_bundled_source_wins_when_local_sources_are_absent \
  test_begin_rejects_a_missing_domain_pack \
  test_wait_debounces_stale_and_reports_escape_hatch \
  test_fallback_is_once_per_role \
  test_round_cap_escalates_and_blocks_send \
  test_turn_cap_and_no_progress_escalate \
  test_interrupted_round_state_recovery \
  test_factory_anchor_and_concurrent_delegations; do
  python3 "$root/tests/test-crew.py" "$check"
done

# Judgment survives in orchestrate; its dedicated mutation harness verifies
# the prose's crew invocations, authority boundary, risk escalation, and
# independent artifact review.
bash "$root/tests/test-orchestrate.sh"

printf '%s\n' 'test-delegate-to-pi-orchestration: PASS'
