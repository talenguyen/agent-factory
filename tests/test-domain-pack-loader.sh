#!/usr/bin/env bash
set -euo pipefail

readonly project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly pack_file="${PACK_FILE:-$project_root/.claude/skills/delegate-to-pi/references/domains/software.md}"
source "$project_root/tests/strip-test-comments.sh"
scratch_dir=$(mktemp -d)
trap 'rm -rf "$scratch_dir"' EXIT
clean_pack="$scratch_dir/pack.md"
strip_test_comments "$pack_file" >"$clean_pack"

[[ -f "$pack_file" ]] || { printf 'software domain pack is missing\n' >&2; exit 1; }
# Domain resolution and fail-loud pack validation are executable begin-time
# behavior. Its regression and mutation checks live in test-crew.py and
# test-crew-mutations.sh, rather than in the retired supervisor prose.
python3 "$project_root/tests/test-crew.py" test_begin_rejects_a_missing_domain_pack
python3 "$project_root/tests/test-crew.py" test_domain_resolution_prefers_explicit_over_workspace_and_default
python3 "$project_root/tests/test-crew.py" test_verify_cli_rejects_comment_and_blank_only_pack_commands
python3 "$project_root/tests/test-crew.py" test_begin_rejects_each_missing_required_pack_section
python3 "$project_root/tests/test-crew.py" test_verify_cli_executes_multiline_and_comment_prefixed_pack_commands

section_body() {
  local section="$1"
  awk -v h="## $section" '$0==h {on=1; next} on && /^## / {exit} on {print}' "$clean_pack"
}
require_section_elements() {
  local section="$1" body element
  shift; body="$(section_body "$section")"
  for element in "$@"; do
    grep -Fqi -- "$element" <<<"$body" || { echo "missing $section section element: $element" >&2; exit 1; }
  done
}
require_section_elements 'Workspace layout' \
  'git repository' 'tracked source, tests, and build artifacts' 'using-git-worktrees' 'main/master'
require_section_elements 'Verify command' \
  'git -C "$(pwd)" status --porcelain' 'git -C "$(pwd)" diff'
require_section_elements 'Reviewer rubric' \
  'APPROVED' 'satisfies the stated goal' 'adequate automated-test coverage' 'CHANGES REQUESTED:'
require_section_elements 'Risk gate' \
  'destructive git or filesystem operations' '.env.keys' 'production databases' 'outward-facing action'
require_section_elements 'Roles' \
  'Worker implements software' 'reviewer reviews the diff' 'scout is read-only' 'real running application or interface' 'exact reproduction steps' 'test-driven-development'
require_section_elements 'Definition of done' \
  'verification and tests are green' 'review is approved' 'user-approved merge or PR' 'Worktree isolation is required'

if [[ -z ${SKIP_MUTATION_CHECK:-} ]]; then
  for section in 'Workspace layout' 'Verify command' 'Reviewer rubric' 'Risk gate' 'Roles' 'Definition of done'; do
    for mutation in tbd long_comment keyword_comment; do
      tmp="$scratch_dir/${section// /-}-$mutation.md"
      SECTION="$section" MUTATION="$mutation" python3 - "$pack_file" "$tmp" <<'PY'
import os, pathlib, re, sys
text = pathlib.Path(sys.argv[1]).read_text(); section = os.environ['SECTION']; kind = os.environ['MUTATION']
pattern = rf'(## {re.escape(section)}\n)(.*?)(?=## |\Z)'
def replace(m):
    body = 'TBD.\n' if kind == 'tbd' else ('# ' + ('verbose non-procedural comment ' * 5) + '\n' if kind == 'long_comment' else ''.join('# ' + line + '\n' for line in m.group(2).splitlines()))
    return m.group(1) + body
text, count = re.subn(pattern, replace, text, count=1, flags=re.S); assert count == 1
pathlib.Path(sys.argv[2]).write_text(text)
PY
      set +e
      PACK_FILE="$tmp" SKIP_MUTATION_CHECK=1 "$0" >/dev/null 2>&1
      broken=$?
      SKIP_MUTATION_CHECK=1 "$0" >/dev/null 2>&1
      restored=$?
      set -e
      if [[ "$restored" -ne 0 ]]; then
        printf '%s %s: control failed with exit %s; mutation evidence is invalid\n' "$section" "$mutation" "$restored" >&2
        exit 1
      fi
      if [[ "$broken" -eq 0 ]]; then
        printf '%s %s: mutation unexpectedly passed\n' "$section" "$mutation" >&2
        exit 1
      fi
      printf '%s %s: broken_exit=%s restored_exit=%s\n' "$section" "$mutation" "$broken" "$restored"
    done
  done
fi
printf '%s\n' 'test-domain-pack-loader: PASS'
