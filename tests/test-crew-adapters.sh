#!/usr/bin/env bash
set -euo pipefail

readonly project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly mux_adapter="${HERDR_MUX_ADAPTER:-$project_root/lib/crew/adapters/herdr_mux.py}"
readonly worker_adapter="${PI_WORKER_ADAPTER:-$project_root/lib/crew/adapters/pi_worker.py}"
scratch_dir="$(mktemp -d)"
trap 'rm -rf "$scratch_dir"' EXIT

# The real herdr process is the external boundary.  This executable records
# exactly what the adapter sends while returning the documented response shape.
cat > "$scratch_dir/herdr" <<'HERDR'
#!/usr/bin/env python3
import json, os, sys
with open(os.environ["HERDR_LOG"], "a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\n")
args = sys.argv[1:]
if args == ["pane", "current"]:
    print('{"result":{"pane":{"pane_id":"p-current"}}}')
elif args[:2] == ["agent", "start"]:
    print('{"result":{"agent":{"pane_id":"p-new"}}}')
elif args == ["agent", "list"]:
    print('{"result":{"agents":[{"pane_id":"p-idle","name":"worker","cwd":"/repo","agent_status":"idle"},{"pane_id":"p-blocked","name":"blocked","cwd":"/repo","agent_status":"blocked"}]}}')
elif args[:2] == ["agent", "get"]:
    print(json.dumps({"result":{"agent":{"agent_status":os.environ.get("HERDR_STATUS", "idle")}}}))
elif args[:2] == ["agent", "read"]:
    reads = os.environ.get("HERDR_READS", os.environ.get("HERDR_READ", "(openai-codex) gpt-5.6-terra • medium")).split("|")
    counter = os.environ.get("HERDR_READ_COUNTER")
    index = int(open(counter).read()) if counter and os.path.exists(counter) else 0
    if counter: open(counter, "w").write(str(index + 1))
    print(json.dumps({"result":{"read":{"text":reads[min(index, len(reads) - 1)]}}}))
elif args[:2] == ["pane", "send-keys"]:
    if os.environ.get("HERDR_BAD_SEND_KEYS"): print("not json")
else:
    print('{"result":{"type":"ok"}}')
HERDR
chmod +x "$scratch_dir/herdr"

run_mux() { PATH="$scratch_dir:$PATH" HERDR_LOG="$scratch_dir/calls.jsonl" HERDR_RENDER_TIMEOUT=1 HERDR_RENDER_INTERVAL=0.01 "$mux_adapter" "$@"; }
run_worker() { "$worker_adapter" "$@"; }

[[ "$(run_mux crew_capabilities)" == '{"banner": true, "focus": true, "isolation": true, "layout": true, "native_status": true, "persistent_context": true}' ]]
list="$(run_mux crew_list)"
set +e
HERDR_PANE_ID= run_mux crew_spawn worker /repo -- /repo/bin/pi-project --provider openai-codex >/dev/null 2>"$scratch_dir/missing-anchor.err"
missing_anchor=$?
set -e
if [[ "$missing_anchor" -eq 0 ]]; then echo 'unanchored first spawn unexpectedly succeeded' >&2; exit 1; fi
grep -F 'HERDR_PANE_ID is unset; cannot safely anchor first crew spawn' "$scratch_dir/missing-anchor.err" >/dev/null
HERDR_PANE_ID=p-orchestrator run_mux crew_spawn worker /repo -- /repo/bin/pi-project --provider openai-codex >/dev/null
run_mux crew_spawn reviewer /repo --stack-under p-worker -- /repo/bin/pi-project --provider openai-codex >/dev/null
# Real herdr returns an empty body from pane send-keys; that is successful submission.
printf 'hello crew' | run_mux crew_send p-new >/dev/null
set +e
printf 'hello crew' | HERDR_BAD_SEND_KEYS=1 run_mux crew_send p-new >/dev/null 2>"$scratch_dir/bad-send.err"
bad_send=$?
set -e
if [[ "$bad_send" -eq 0 ]]; then echo 'non-empty send-keys response unexpectedly succeeded' >&2; exit 1; fi
grep -F 'herdr returned malformed JSON' "$scratch_dir/bad-send.err" >/dev/null
run_mux crew_read p-new --recent --lines 55 >/dev/null
run_mux crew_close p-new >/dev/null
HERDR_READ='(openai-codex) gpt-5.6-terra • medium' run_mux crew_verify_profile p-new openai-codex gpt-5.6-terra medium
# A pi pane can be settled before its status bar renders; success on the third
# read proves verification polls beyond a one-read race.
HERDR_READS='|||(openai-codex) gpt-5.6-terra • medium' HERDR_READ_COUNTER="$scratch_dir/reads" run_mux crew_verify_profile p-new openai-codex gpt-5.6-terra medium
set +e
HERDR_READ='(openai-codex) wrong-model • medium' run_mux crew_verify_profile p-new openai-codex gpt-5.6-terra medium >/dev/null 2>&1
wrong_banner=$?
set -e
if [[ "$wrong_banner" -eq 0 ]]; then echo 'wrong profile banner unexpectedly verified' >&2; exit 1; fi
set +e
HERDR_READ='' run_mux crew_verify_profile p-new openai-codex gpt-5.6-terra medium >/dev/null 2>"$scratch_dir/empty-banner.err"
empty_banner=$?
set -e
if [[ "$empty_banner" -eq 0 ]]; then echo 'empty profile banner unexpectedly verified' >&2; exit 1; fi
grep -F 'profile banner failed to render' "$scratch_dir/empty-banner.err" >/dev/null
for pair in 'idle settled' 'done settled' 'blocked blocked' 'working working' 'mystery unknown'; do
  set -- $pair
  actual="$(HERDR_STATUS="$1" run_mux crew_status p-new)"
  [[ "$actual" == "$2" ]]
done
argv="$(run_worker worker_argv openai-codex gpt-5.6-terra low session-42 ignored)"
pattern="$(run_worker worker_banner_pattern)"
caps="$(run_worker worker_capabilities)"

python3 - "$scratch_dir/calls.jsonl" "$list" "$argv" "$pattern" "$caps" <<'PY'
import json, re, sys
calls = [json.loads(line) for line in open(sys.argv[1])]
listed = json.loads(sys.argv[2])
argv, pattern, caps = json.loads(sys.argv[3]), sys.argv[4], json.loads(sys.argv[5])
assert listed == [{"id":"p-idle","name":"worker","cwd":"/repo","status":"settled"}, {"id":"p-blocked","name":"blocked","cwd":"/repo","status":"blocked"}]
# Break caught: omitting Enter leaves a typed prompt unsent forever.
send = calls.index(["agent", "send", "p-new", "hello crew"])
assert calls[send + 1] == ["pane", "send-keys", "p-new", "enter"]
# Break caught: a free-form name works for agent verbs but fails on pane verbs.
for call in calls:
    if call[0] == "pane" and call[1] != "current":
        assert call[2].startswith("p-"), call
# Break caught: the first split must anchor under this crew's own pane, then restore the operator's focus.
worker_start = next(i for i, call in enumerate(calls) if call[:2] == ["agent", "start"] and call[2] == "worker")
assert calls[worker_start - 2:worker_start + 2] == [["pane", "current"], ["agent", "focus", "p-orchestrator"], ["agent", "start", "worker", "--cwd", "/repo", "--split", "right", "--no-focus", "--", "/repo/bin/pi-project", "--provider", "openai-codex"], ["agent", "focus", "p-current"]]
# Break caught: later spawns stack under the previous crew pane and restore focus.
reviewer_start = next(i for i, call in enumerate(calls) if call[:2] == ["agent", "start"] and call[2] == "reviewer")
assert calls[reviewer_start - 2:reviewer_start + 2] == [["pane", "current"], ["agent", "focus", "p-worker"], ["agent", "start", "reviewer", "--cwd", "/repo", "--split", "down", "--no-focus", "--", "/repo/bin/pi-project", "--provider", "openai-codex"], ["agent", "focus", "p-current"]]
# Break caught: pane-created workers cannot appear in agent list for polling or reuse.
assert not any(call[:2] in (["pane", "split"], ["pane", "run"]) for call in calls)
# Break caught: --recent must request unwrapped scrollback, not visible output.
assert ["agent", "read", "p-new", "--source", "recent-unwrapped", "--lines", "55"] in calls
# Break caught: narrow pane status text is horizontally truncated without zoom.
read_index = next(i for i, call in enumerate(calls) if call[:2] == ["agent", "read"] and call[-2:] == ["--lines", "200"])
assert calls[read_index - 1] == ["pane", "zoom", "p-new", "--on"]
assert calls[read_index + 1] == ["pane", "zoom", "p-new", "--off"]
# Break caught: blocked settles polling but is busy and therefore must not be reusable.
assert listed[0]["status"] == "settled" and listed[1]["status"] == "blocked"
# Break caught: invoking bare pi bypasses the repository isolation launcher.
assert argv[0].endswith("/bin/pi-project") and argv[1:] == ["--provider", "openai-codex", "--model", "gpt-5.6-terra", "--thinking", "low", "--session-id", "session-42"]
assert "pi" not in argv[0].split("/")[-1] or argv[0].endswith("pi-project")
assert re.search(pattern, "(openai-codex) gpt-5.6-terra • medium")
assert not any(re.search(pattern, value) for value in ("", "$ ", "(other-provider) other-model • high"))
assert caps == {"isolation": True, "session_resume": True}
PY

printf '%s\n' 'test-crew-adapters: PASS'
