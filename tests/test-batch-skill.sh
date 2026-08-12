#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
skill="${SKILL_FILE:-$root/.claude/skills/orchestrate/SKILL.md}"
for requirement in 'persistent_context: false' 'every prompt must re-supply' 'plan, the ledger, and the current artifact'; do
  rg -Fq "$requirement" "$skill" || { echo "missing batch skill requirement: $requirement" >&2; exit 1; }
done

if [[ -z ${SKIP_MUTATION_CHECK:-} ]]; then
  scratch="$(mktemp -d)"; trap 'rm -rf "$scratch"' EXIT
  for requirement in 'persistent_context: false' 'every prompt must re-supply' 'plan, the ledger, and the current artifact'; do
    mutated="$scratch/skill.md"
    python3 - "$skill" "$mutated" "$requirement" <<'PY'
import pathlib, sys
source, target, requirement = map(pathlib.Path if False else str, sys.argv[1:])
text = pathlib.Path(source).read_text()
assert text.count(requirement) == 1
pathlib.Path(target).write_text(text.replace(requirement, "TBD"))
PY
    set +e
    SKILL_FILE="$mutated" SKIP_MUTATION_CHECK=1 bash "$0" >/dev/null 2>&1
    broken=$?
    SKIP_MUTATION_CHECK=1 bash "$0" >/dev/null 2>&1
    control=$?
    set -e
    if [[ "$control" -ne 0 ]]; then
      printf '%s: control failed with exit %s; mutation evidence is invalid\n' "$requirement" "$control" >&2
      exit 1
    fi
    if [[ "$broken" -eq 0 ]]; then
      printf '%s: mutation unexpectedly passed\n' "$requirement" >&2
      exit 1
    fi
    printf '%s: mutation_exit=%s control_exit=%s\n' "$requirement" "$broken" "$control"
  done
fi
printf '%s\n' 'test-batch-skill: PASS'
