#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
policy="$root/POLICY.md"

[[ -f "$policy" ]] || { echo 'POLICY.md is missing' >&2; exit 1; }
for category in \
  'Destructive git operations' \
  'Destructive filesystem operations' \
  'Secrets and credentials' \
  'Production systems and live customer data' \
  'Outward-facing actions'; do
  rg -Fq -- "$category" "$policy" || { echo "POLICY.md is missing category: $category" >&2; exit 1; }
done
rg -qi 'POLICY\.local\.md.*domain pack.*Risk gate.*may add' "$policy" || { echo 'POLICY.md is missing additive precedence' >&2; exit 1; }
rg -qi 'neither may weaken' "$policy" || { echo 'POLICY.md is missing non-weakening precedence' >&2; exit 1; }
if rg -n -i "user's global .*CLAUDE\.md.*Never/Off-limits|global .*CLAUDE\.md.*Never/Off-limits" "$root/.claude/skills"; then
  echo 'skill risk gate still defers to a global CLAUDE.md' >&2
  exit 1
fi

printf '%s\n' 'test-policy: PASS'
