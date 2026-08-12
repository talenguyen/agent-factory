#!/usr/bin/env bash
set -euo pipefail

readonly root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
alias="$root/.claude/skills/delegate-to-pi/SKILL.md"

# Compatibility selection remains prose; all launch and reuse mechanics are
# executed by the crew contract tests below.
rg -q '^name: delegate-to-pi$' "$alias"
rg -q 'Delegate a coding goal to a `pi` agent running under herdr' "$alias"
rg -q 'FACTORY_MUX=herdr' "$alias"
rg -q 'FACTORY_WORKER=pi' "$alias"
rg -q '`orchestrate`' "$alias"

# Breaks caught: bypassing pi-project, accepting legacy/tier-prefix names, or
# losing cwd/role filtering. These run the committed mock-backed crew harness.
python3 "$root/tests/test-crew.py" test_reuse_requires_role_tier_cwd_and_name
python3 "$root/tests/test-crew.py" test_reuse_name_boundary_accepts_variant_not_tier_prefix
bash "$root/tests/test-crew-adapters.sh"

printf '%s\n' 'test-delegate-to-pi-isolation: PASS'
