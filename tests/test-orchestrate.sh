#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
skill="${SKILL_FILE:-$root/.claude/skills/orchestrate/SKILL.md}"
reference="${HERDR_REFERENCE_FILE:-$root/.claude/skills/delegate-to-pi/references/herdr-cli.md}"
source "$root/tests/strip-test-comments.sh"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
clean="$scratch/orchestrate.md"
strip_test_comments "$skill" >"$clean"

[[ -f "$skill" ]] || { echo 'orchestrate skill is missing' >&2; exit 1; }
[[ "$(wc -l <"$skill")" -lt 250 ]] || { echo 'orchestrate skill exceeds 250 lines' >&2; exit 1; }
rg -q '^name: orchestrate$' "$clean"
rg -q '^description: Use when' "$clean"
for command in doctor begin spawn send wait read classify-risk fallback round turn ledger state verify end close; do
  rg -q "bin/crew $command" "$clean" || { echo "missing crew mechanism: $command" >&2; exit 1; }
done
for invariant in \
  'crew produces artifacts' \
  'orchestrator performs outward-facing actions' \
  'hand control to the human' \
  'never resolve the risky step' \
  'verification before reporting success' \
  'reads the artifact itself from the shared worktree' \
  'never paste a diff' \
  'can never CLEAR an action' \
  'must still judge the question itself' \
  'MUST read POLICY.md itself' \
  'ADVISORY HINT' \
  'never the gate' \
  'For research, do not read the whole diff' \
  'pack verifier and inspect its output' \
  'exactly `APPROVED`' \
  'exactly `CHANGES REQUESTED:`' \
  'retry once on a noncompliant verdict' \
  'observed artifact defect' \
  'changed tests, assertions, or guards require a counter-mutation gate' \
  'mutation and control exit codes'; do
  rg -Fqi -- "$invariant" "$clean" || { echo "missing invariant: $invariant" >&2; exit 1; }
done
for document in "$clean" "$reference"; do
  rg -Fq 'HERDR_PANE_ID' "$document" || { echo "missing HERDR_PANE_ID: $document" >&2; exit 1; }
done
rg -Fqi 'fail loud' "$clean" || { echo 'missing first-spawn anchor failure policy' >&2; exit 1; }
rg -Fq 'restore the operator' "$clean" || { echo 'missing first-spawn focus restoration policy' >&2; exit 1; }
rg -Fq 'herdr agent focus "$HERDR_PANE_ID"' "$reference" || { echo 'missing authoritative anchor command' >&2; exit 1; }
rg -Fq 'herdr agent focus "$CURRENT_PANE"' "$reference" || { echo 'missing operator focus restore command' >&2; exit 1; }
for forbidden in '3 consecutive' '60s' 'round cap 5' 'turn cap 6' 'every 5s'; do
  if rg -Fqi -- "$forbidden" "$clean"; then echo "mechanism leaked into prose: $forbidden" >&2; exit 1; fi
done

if [[ -z ${SKIP_MUTATION_CHECK:-} ]]; then
  targets=(
    'bin/crew doctor' 'bin/crew begin' 'bin/crew spawn' 'bin/crew send'
    'bin/crew wait' 'bin/crew read' 'bin/crew classify-risk' 'bin/crew fallback'
    'bin/crew round' 'bin/crew turn' 'bin/crew ledger' 'bin/crew state'
    'bin/crew verify' 'bin/crew end' 'bin/crew close'
    'crew produces artifacts' 'orchestrator performs outward-facing actions'
    'hand control to the human' 'Never resolve the risky step'
    'Verification before reporting success' 'reads the artifact itself from the shared worktree'
    'never paste a diff' 'can never CLEAR an action'
    'must still judge the question itself' 'MUST read POLICY.md itself'
    'ADVISORY HINT' 'never the gate'
    'For research, do not read the whole diff' 'pack verifier and inspect its output'
    'exactly `APPROVED`' 'exactly `CHANGES REQUESTED:`' 'retry once on a noncompliant verdict'
    'observed artifact defect' 'changed tests, assertions, or guards require a counter-mutation gate'
    'mutation and control exit codes'
    'HERDR_PANE_ID' 'fail loud' 'restore the operator'
  )
  for target in "${targets[@]}"; do
    mutated="$scratch/$(printf '%s' "$target" | tr -cs '[:alnum:]' _).md"
    TARGET="$target" SKILL="$skill" OUT="$mutated" python3 - <<'PY'
import os, pathlib
text = pathlib.Path(os.environ['SKILL']).read_text(); target = os.environ['TARGET']
assert target in text
pathlib.Path(os.environ['OUT']).write_text(text.replace(target, 'TBD'))
PY
    set +e
    SKILL_FILE="$mutated" SKIP_MUTATION_CHECK=1 bash "$0" >/dev/null 2>&1
    broken=$?
    SKIP_MUTATION_CHECK=1 bash "$0" >/dev/null 2>&1
    restored=$?
    set -e
    if [[ "$restored" -ne 0 ]]; then
      printf '%s: control failed with exit %s; mutation evidence is invalid\n' "$target" "$restored" >&2
      exit 1
    fi
    if [[ "$broken" -eq 0 ]]; then
      printf '%s: mutation unexpectedly passed\n' "$target" >&2
      exit 1
    fi
    printf '%s: broken_exit=%s restored_exit=%s\n' "$target" "$broken" "$restored"
  done
  for target in 'HERDR_PANE_ID' 'herdr agent focus "$HERDR_PANE_ID"' 'herdr agent focus "$CURRENT_PANE"'; do
    mutated="$scratch/reference-$(printf '%s' "$target" | tr -cs '[:alnum:]' _).md"
    TARGET="$target" REFERENCE="$reference" OUT="$mutated" python3 - <<'PY'
import os, pathlib
text = pathlib.Path(os.environ['REFERENCE']).read_text(); target = os.environ['TARGET']
assert target in text
pathlib.Path(os.environ['OUT']).write_text(text.replace(target, 'TBD'))
PY
    set +e
    HERDR_REFERENCE_FILE="$mutated" SKIP_MUTATION_CHECK=1 bash "$0" >/dev/null 2>&1
    broken=$?
    SKIP_MUTATION_CHECK=1 bash "$0" >/dev/null 2>&1
    restored=$?
    set -e
    if [[ "$restored" -ne 0 ]]; then
      printf 'reference %s: control failed with exit %s; mutation evidence is invalid\n' "$target" "$restored" >&2
      exit 1
    fi
    if [[ "$broken" -eq 0 ]]; then
      printf 'reference %s: mutation unexpectedly passed\n' "$target" >&2
      exit 1
    fi
    printf 'reference %s: broken_exit=%s restored_exit=%s\n' "$target" "$broken" "$restored"
  done
fi
printf '%s\n' 'test-orchestrate: PASS'
