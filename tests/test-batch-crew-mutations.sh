#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT

# Each mutation is made in a disposable full tree so the test drives the same
# bin/crew entry point as its control.  The printed pair is the reportable
# evidence; neither the working tree nor a fixture is altered.
mutate_and_check() {
  local name="$1" file="$2" old="$3" new="$4"
  local copy="$scratch/$name"
  cp -R "$root" "$copy"
  python3 - "$copy/$file" "$old" "$new" <<'PY'
import pathlib, sys
path, old, new = map(str, sys.argv[1:])
text = pathlib.Path(path).read_text()
assert text.count(old) == 1, old
pathlib.Path(path).write_text(text.replace(old, new))
PY
  set +e
  python3 "$copy/tests/test-batch-crew.py" >/dev/null 2>&1
  local broken=$?
  set -e
  python3 "$root/tests/test-batch-crew.py" >/dev/null
  local restored=$?
  if [[ "$restored" -ne 0 ]]; then
    printf '%s: control failed with exit %s; mutation evidence is invalid\n' "$name" "$restored" >&2
    exit 1
  fi
  if [[ "$broken" -eq 0 ]]; then
    printf '%s: mutation unexpectedly passed\n' "$name" >&2
    exit 1
  fi
  printf '%s: mutation_exit=%s control_exit=%s\n' "$name" "$broken" "$restored"
}

mutate_and_check claude_prompt_argv lib/crew/adapters/claude_worker.py \
  'print(json.dumps(["claude", "-p"]))' 'print(json.dumps(["claude"]))'
mutate_and_check pre_send_stale_read lib/crew/adapters/batch_mux.py \
  '"status": "unknown", "output": ""' '"status": "settled", "output": ""'
mutate_and_check noisy_stderr_success lib/crew/adapters/batch_mux.py \
  'if result.returncode or any(signature in output.lower() for signature in RATE_LIMITS):' 'if result.returncode or result.stderr:'
mutate_and_check nonzero_failed lib/crew/adapters/batch_mux.py \
  'if result.returncode or any(signature in output.lower() for signature in RATE_LIMITS):' 'if False:'
mutate_and_check question_blocked lib/crew/adapters/batch_mux.py \
  'elif "QUESTION:" in output:' 'elif False:'
mutate_and_check rate_limit_failed lib/crew/adapters/batch_mux.py \
  'if result.returncode or any(signature in output.lower() for signature in RATE_LIMITS):' 'if result.returncode:'
mutate_and_check wall_clock_timeout lib/crew/adapters/batch_mux.py \
  '"status": "timeout", "output": exc.stdout or ""' '"status": "failed", "output": exc.stdout or ""'
mutate_and_check banner_cannot_verify lib/crew/core.py \
  '            if capabilities("mux")["banner"]:' '            if True:'

printf '%s\n' 'test-batch-crew-mutations: PASS'
