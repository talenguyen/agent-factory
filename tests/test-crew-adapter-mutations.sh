#!/usr/bin/env bash
set -euo pipefail

readonly project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly adapter_test="$project_root/tests/test-crew-adapters.sh"
scratch_dir="$(mktemp -d)"
trap 'rm -rf "$scratch_dir"' EXIT

# Each mutation breaks exactly one contract behavior in a scratch copy; tracked
# adapters are never modified.  A non-zero exit proves the corresponding
# boundary assertion is live, then the unmodified adapter is the restoration.
mutate_and_check() {
  local name="$1" file="$2" old="$3" new="$4"
  local copy="$scratch_dir/$name.py"
  cp "$project_root/$file" "$copy"
  python3 - "$copy" "$old" "$new" <<'PY'
import pathlib, sys
path, old, new = map(pathlib.Path if False else str, sys.argv[1:])
text = pathlib.Path(path).read_text()
assert text.count(old) == 1, old
pathlib.Path(path).write_text(text.replace(old, new))
PY
  chmod +x "$copy"
  set +e
  if [[ "$file" == *worker* ]]; then
    PI_WORKER_ADAPTER="$copy" bash "$adapter_test" >/dev/null 2>&1
  else
    HERDR_MUX_ADAPTER="$copy" bash "$adapter_test" >/dev/null 2>&1
  fi
  local broken=$?
  set -e
  local restored
  if bash "$adapter_test" >/dev/null 2>&1; then restored=0; else restored=$?; fi
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

# Break caught: saved-role reuse previously returned "unverifiable" silently.
residual_lib="$scratch_dir/residual-lib"
mkdir -p "$residual_lib/crew"
cp "$project_root/lib/crew/__init__.py" "$project_root/lib/crew/core.py" "$residual_lib/crew/"
python3 - "$residual_lib/crew/core.py" <<'PY'
import pathlib, sys
path = pathlib.Path(sys.argv[1])
old = '            if profile_verified == "unverifiable": print("crew: warning: cannot verify profile; adapter reports banner=false", file=sys.stderr)\n            event("pi_reuse", state, role=name)'
text = path.read_text()
assert text.count(old) == 1
path.write_text(text.replace(old, '            event("pi_reuse", state, role=name)'))
PY
set +e
CREW_LIB_ROOT="$residual_lib" python3 "$project_root/tests/test-crew.py" test_saved_bannerless_reuse_warns_that_profile_is_unverifiable >/dev/null 2>&1
broken=$?
set -e
if python3 "$project_root/tests/test-crew.py" test_saved_bannerless_reuse_warns_that_profile_is_unverifiable >/dev/null 2>&1; then restored=0; else restored=$?; fi
if [[ "$restored" -ne 0 ]]; then
  printf 'saved_reuse_warning: control failed with exit %s; mutation evidence is invalid\n' "$restored" >&2
  exit 1
fi
if [[ "$broken" -eq 0 ]]; then
  printf 'saved_reuse_warning: mutation unexpectedly passed\n' >&2
  exit 1
fi
printf '%s: broken_exit=%s restored_exit=%s\n' saved_reuse_warning "$broken" "$restored"

mutate_and_check send_submit lib/crew/adapters/herdr_mux.py \
  '        call("pane", "send-keys", args[0], "enter", allow_empty=True)' '        pass'
mutate_and_check empty_send_keys lib/crew/adapters/herdr_mux.py \
  'allow_empty=True' 'allow_empty=False'
mutate_and_check malformed_send_keys lib/crew/adapters/herdr_mux.py \
  'if allow_empty and not result.stdout.strip(): return {}' 'if allow_empty: return {}'
mutate_and_check pane_id lib/crew/adapters/herdr_mux.py \
  '        call("pane", "send-keys", args[0], "enter", allow_empty=True)' '        call("pane", "send-keys", "worker", "enter", allow_empty=True)'
mutate_and_check first_spawn_anchor lib/crew/adapters/herdr_mux.py \
  'target = os.environ.get("HERDR_PANE_ID")' 'target = os.environ.get("HERDR_OTHER_PANE_ID")'
mutate_and_check spawn_focus_restore lib/crew/adapters/herdr_mux.py \
  '            call("agent", "focus", current)' '            pass'
mutate_and_check stack_focus lib/crew/adapters/herdr_mux.py \
  '            target, direction = stack_under, "down"' '            target, direction = "p-current", "down"'
mutate_and_check no_pane_split lib/crew/adapters/herdr_mux.py \
  'current = result_value(call("pane", "current"), "pane", "pane_id")' 'call("pane", "split", stack_under, "--direction", "down")\n        current = result_value(call("pane", "current"), "pane", "pane_id")'
mutate_and_check recent_source lib/crew/adapters/herdr_mux.py \
  'source = "recent-unwrapped" if "--recent" in args else "visible"' 'source = "visible"'
mutate_and_check verify_zoom lib/crew/adapters/herdr_mux.py \
  '        call("pane", "zoom", identifier, "--on")' '        pass'
mutate_and_check render_budget lib/crew/adapters/herdr_mux.py \
  'render_deadline = time.monotonic() + float(os.environ.get("HERDR_RENDER_TIMEOUT", "8"))' 'render_deadline = time.monotonic()'
mutate_and_check empty_banner_failure lib/crew/adapters/herdr_mux.py \
  'if not text.strip(): raise SystemExit("herdr mux: profile banner failed to render")' 'if not text.strip(): return'
mutate_and_check profile_mismatch lib/crew/adapters/herdr_mux.py \
  '            raise SystemExit("herdr mux: profile banner did not match")' '            pass'
mutate_and_check blocked_status lib/crew/adapters/herdr_mux.py \
  '"blocked": "blocked"' '"blocked": "settled"'
mutate_and_check worker_launcher lib/crew/adapters/pi_worker.py \
  'str(ROOT / "bin" / "pi-worker")' '"pi"'
mutate_and_check worker_thinking lib/crew/adapters/pi_worker.py \
  '"--thinking", thinking' '"--thinking", "medium"'
mutate_and_check worker_banner_pattern lib/crew/adapters/pi_worker.py \
  '        print(r"\((?:openai-codex|opencode-go)' '        print(r".*") #'

printf '%s\n' 'test-crew-adapter-mutations: PASS'
