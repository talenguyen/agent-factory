#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
goal="${GOAL_FILE:-$root/.claude/skills/autonomous-goal/SKILL.md}"
alias="${ALIAS_FILE:-$root/.claude/skills/autonomous-build/SKILL.md}"
source "$root/tests/strip-test-comments.sh"
scratch_dir=$(mktemp -d)
trap 'rm -rf "$scratch_dir"' EXIT
clean_goal="$scratch_dir/goal.md"
clean_alias="$scratch_dir/alias.md"
strip_test_comments "$goal" >"$clean_goal"
strip_test_comments "$alias" >"$clean_alias"

[[ -f "$goal" ]]
goal_description=$(awk '/^description: / { sub(/^description: /, ""); print; exit }' "$clean_goal")
alias_description=$(awk '/^description: / { sub(/^description: /, ""); print; exit }' "$clean_alias")
[[ "$goal_description" == *'Not for small in-flight edits already scoped in the current conversation.'* ]] || { echo 'autonomous-goal description lost negative scope' >&2; exit 1; }
[[ "$alias_description" == *'Software-pinned alias'* ]] || { echo 'autonomous-build description lost software-pinned alias purpose' >&2; exit 1; }
[[ "$alias_description" == *'Not for small in-flight edits already scoped in the current conversation.'* ]] || { echo 'autonomous-build description lost negative scope' >&2; exit 1; }
rg -q 'Use when.*standalone.*goal.*plan approval' "$clean_goal" || { echo 'autonomous-goal lost invocation trigger' >&2; exit 1; }
rg -q 'Use when.*standalone.*build.*Not for small in-flight edits already scoped in the current conversation' "$clean_alias" || { echo 'autonomous-build lost scoped invocation trigger' >&2; exit 1; }
rg -q 'Plan approval' "$clean_goal"; rg -q 'Risk gate' "$clean_goal"; rg -q 'Final delivery' "$clean_goal"
rg -q 'send/publish/submit/file' "$clean_goal"; rg -q 'acceptance spec' "$clean_goal"; rg -q 'rubric-only' "$clean_goal"
rg -q 'Step 0: Clarify' "$clean_goal"; rg -q 'Step 7 — CHECKPOINT: Final delivery' "$clean_goal"
rg -q 'Red flags' "$clean_goal"; rg -q 'Common mistakes' "$clean_goal"; rg -q 'never delegate' "$clean_goal"
for flag in 'plan already implied' 'config or lock file' 'eventually anyway' 'rest of the build was routine'; do rg -qi "$flag" "$clean_goal"; done
for mistake in 'routine mid-build' 'Treating a plan as risk-gate' 'Guessing ambiguity' 'Delegating before plan' 'review approval as the oracle' 'rubric-only deliverable'; do rg -qi "$mistake" "$clean_goal"; done
for rule_element in 'criteria are all \*\*rubric-only\*\*' 'stops at Checkpoint 1' 'add a specific human checkpoint' 'cut it from scope' 'Do not begin an unsupervised stretch otherwise'; do
  rg -q "$rule_element" "$clean_goal" || { echo "missing rubric-only procedure: $rule_element" >&2; exit 1; }
done
rg -q 'DOMAIN=software' "$clean_alias"; rg -q 'autonomous-goal' "$clean_alias"

section_body() {
  local heading="$1"
  awk -v h="$heading" '$0 ~ h {on=1; next} on && /^## / {exit} on {print}' "$clean_goal"
}
require_section_elements() {
  local heading="$1" body element
  shift; body="$(section_body "$heading")"
  for element in "$@"; do
    grep -Fqi -- "$element" <<<"$body" || { echo "missing $heading procedure: $element" >&2; exit 1; }
  done
}
require_section_elements 'Step 0:' \
  'Ask one clarifying question' 'plausible interpretations materially change the deliverable' 'otherwise proceed'
require_section_elements 'Step 1:' \
  'Write the plan and `acceptance.md` yourself' 'never delegate either' 'mechanical' 'sourced' 'rubric' 'rubric-only' 'Checkpoint 1' 'specific human checkpoint' 'cut it from scope' 'Do not begin an unsupervised stretch otherwise'
require_section_elements 'Step 2' \
  'Present the plan and acceptance spec' 'wait for explicit approval' 'Silence' 'is not approval'
require_section_elements 'Step 3:' \
  'Resolve `DOMAIN`' 'fail-loud pack' 'workspace layout' 'required sub-skills' 'roles' 'tester analog' 'Verify command' 'isolated git worktree' 'delegate-to-pi' 'orchestrate' 'bin/crew' 'never implements directly' 'tester plan is written by Claude Code' 'real-world tester analog' 'not merely the diff' 'Iterate ordinary reversible failures without pausing'
require_section_elements 'Step 4' \
  'Never/Off-limits action' 'selected-pack Risk gate action' 'exact action, target, and reason' 'wait for explicit approval' 'blocked question verbatim' 'never resolve it for the worker' 'none authorize skipping this gate'
require_section_elements 'Step 5:' \
  'run the pack Verify command' 'all applicable tests/build checks' 'read fresh output' 'complete'
require_section_elements 'Step 6:' \
  'Request a code review' 'apply its findings' 'surface genuine judgment calls to the user'
require_section_elements 'Step 7' \
  'Before merge/PR or send/publish/submit/file' 'present the final-delivery choice' 'wait' 'crew produces artifacts only' 'never performs outward-facing actions'

if [[ -z ${SKIP_MUTATION_CHECK:-} ]]; then
  for heading in 'Step 0: Clarify only if genuinely ambiguous' 'Step 1: Plan and acceptance spec' 'Step 2 — CHECKPOINT: Plan approval' 'Step 3: Build (unsupervised)' 'Step 4 — CHECKPOINT: Risk gate' 'Step 5: Verify' 'Step 6: Review' 'Step 7 — CHECKPOINT: Final delivery'; do
    for mutation in tbd long_comment keyword_comment; do
      tmp="$scratch_dir/${heading%%:*}-$mutation.md"
      HEADING="$heading" MUTATION="$mutation" python3 - "$goal" "$tmp" <<'PY'
import os, pathlib, re, sys
text = pathlib.Path(sys.argv[1]).read_text(); heading = os.environ['HEADING']; kind = os.environ['MUTATION']
pattern = rf'(## {re.escape(heading)}\n)(.*?)(?=## |\Z)'
def replace(m):
    body = 'TBD.\n' if kind == 'tbd' else ('# ' + ('verbose non-procedural comment ' * 5) + '\n' if kind == 'long_comment' else ''.join('# ' + line + '\n' for line in m.group(2).splitlines()))
    return m.group(1) + body
text, count = re.subn(pattern, replace, text, count=1, flags=re.S); assert count == 1
pathlib.Path(sys.argv[2]).write_text(text)
PY
      set +e
      GOAL_FILE="$tmp" SKIP_MUTATION_CHECK=1 "$0" >/dev/null 2>&1
      broken=$?
      SKIP_MUTATION_CHECK=1 "$0" >/dev/null 2>&1
      restored=$?
      set -e
      if [[ "$restored" -ne 0 ]]; then
        printf '%s %s: control failed with exit %s; mutation evidence is invalid\n' "$heading" "$mutation" "$restored" >&2
        exit 1
      fi
      if [[ "$broken" -eq 0 ]]; then
        printf '%s %s: mutation unexpectedly passed\n' "$heading" "$mutation" >&2
        exit 1
      fi
      printf '%s %s: broken_exit=%s restored_exit=%s\n' "$heading" "$mutation" "$broken" "$restored"
    done
  done
fi
printf '%s\n' 'test-autonomous-goal: PASS'
