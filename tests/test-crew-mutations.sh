#!/usr/bin/env bash
set -euo pipefail

readonly root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT

mutate_core() {
  local name="$1" old="$2" new="$3" check="$4"
  local lib="$scratch/$name/lib/crew"
  mkdir -p "$lib"
  cp "$root/lib/crew/__init__.py" "$root/lib/crew/core.py" "$lib/"
  OLD="$old" NEW="$new" FILE="$lib/core.py" python3 - <<'PY'
import os, pathlib
path = pathlib.Path(os.environ['FILE']); text = path.read_text()
old, new = os.environ['OLD'], os.environ['NEW']
assert text.count(old) == 1, old
path.write_text(text.replace(old, new))
PY
  set +e
  CREW_ROOT="$root" CREW_LIB_ROOT="${lib%/crew}" python3 "$root/tests/test-crew.py" "$check" >/dev/null 2>&1
  local broken=$?
  set -e
  local restored=0
  python3 "$root/tests/test-crew.py" "$check" >/dev/null 2>&1 || restored=$?
  if [[ "$restored" -ne 0 ]]; then
    printf '%s: control failed with exit %s; mutation evidence is invalid\n' "$name" "$restored" >&2
    exit 1
  fi
  if [[ "$broken" -eq 0 ]]; then
    printf '%s: mutation unexpectedly passed\n' "$name" >&2
    exit 1
  fi
  printf '%s: broken_exit=%s restored_exit=%s\n' "$name" "$broken" "$restored"
}

# Break caught: a non-crew role prefix must never be reused after the cutover.
mutate_core crew_role_prefix 'prefix = f"crew-' 'prefix = f"broken-' test_reuse_name_boundary_accepts_variant_not_tier_prefix
# Break caught: a requested nonexistent pack must stop before state creation.
mutate_core missing_domain_pack 'profiles = profile(); domain_pack(domain); delegation = str(uuid.uuid4())' 'profiles = profile(); delegation = str(uuid.uuid4())' test_begin_rejects_a_missing_domain_pack
# Break caught: a comment-only Verify command must never be executed as success.
mutate_core comment_only_verify_guard 'if not any(line.strip() and not line.lstrip().startswith("#") for line in command.splitlines()):' 'if False:' test_verify_cli_rejects_comment_and_blank_only_pack_commands
# Break caught: rejecting comments alone must not silently accept blank commands.
mutate_core blank_only_verify_guard 'if not any(line.strip() and not line.lstrip().startswith("#") for line in command.splitlines()):' 'if any(line.lstrip().startswith("#") for line in command.splitlines()):' test_verify_cli_rejects_comment_and_blank_only_pack_commands
# Break caught: each required pack section must be enforced at the crew begin CLI.
mutate_core required_pack_sections 'markdown_sections(path, ("Workspace layout", "Verify command", "Reviewer rubric", "Risk gate", "Roles", "Definition of done"))' 'markdown_sections(path, ())' test_begin_rejects_each_missing_required_pack_section
# Break caught: the crew verify CLI must remain wired to its executor.
mutate_core verify_cli_wiring 'raise SystemExit(run_verify_command(domain_pack_path(state["domain"])))' 'raise SystemExit(0)' test_verify_cli_executes_multiline_and_comment_prefixed_pack_commands
# Break caught: a valid leading comment must not make a multiline Verify command invalid.
mutate_core comment_prefixed_multiline_verify 'if not any(line.strip() and not line.lstrip().startswith("#") for line in command.splitlines()):' 'if any(line.lstrip().startswith("#") for line in command.splitlines()):' test_verify_cli_executes_multiline_and_comment_prefixed_pack_commands
# Break caught: explicit domain must outrank workspace metadata and defaulting.
mutate_core explicit_domain_precedence 'if explicit: return explicit' 'if explicit: return "research"' test_domain_resolution_prefers_explicit_over_workspace_and_default

printf '%s\n' 'test-crew-mutations: PASS'
