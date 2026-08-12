#!/usr/bin/env python3
"""End-to-end contract tests for the synchronous batch mux via bin/crew."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
CREW = ROOT / "bin" / "crew"


def run(args, env, stdin=None):
    return subprocess.run([str(CREW), *args], input=stdin, text=True, capture_output=True, env=env)


def fake_claude(directory):
    path = directory / "claude"
    path.write_text("""#!/usr/bin/env python3
import sys, time
prompt = sys.argv[-1] if len(sys.argv) > 2 else sys.stdin.read()
if 'FAIL-TURN' in prompt:
    raise SystemExit(7)
if 'SLOW-TURN' in prompt:
    time.sleep(1)
if 'RATE-LIMIT-TURN' in prompt:
    print('rate limit reached')
    print('claude diagnostic noise', file=sys.stderr)
    raise SystemExit(0)
if 'QUESTION-TURN' in prompt:
    print('QUESTION: choose a direction')
else:
    print('OK: ' + prompt)
print('claude diagnostic noise', file=sys.stderr)
""")
    path.chmod(0o755)


def start(env):
    begun = run(["begin", "--tier", "S", "--domain", "software"], env)
    assert begun.returncode == 0, begun.stderr
    env["FACTORY_CREW_DELEGATION_ID"] = json.loads(begun.stdout)["delegation_id"]
    spawned = run(["spawn", "--role", "worker"], env)
    assert spawned.returncode == 0, spawned.stderr
    reply = json.loads(spawned.stdout)
    assert reply["profile_verified"] == "unverifiable"
    assert "cannot verify profile" in spawned.stderr
    assert "cannot provide repo-local skill isolation" in spawned.stderr


def turn(env, prompt, outcome):
    sent = run(["send", "--role", "worker"], env, prompt)
    waited = run(["wait", "--role", "worker", "--timeout", "1", "--interval", "0"], env)
    assert sent.returncode == 0, sent.stderr
    assert waited.returncode == 0, waited.stderr
    reply = json.loads(waited.stdout)
    assert reply["outcome"] == outcome, reply
    return reply


def main():
    with tempfile.TemporaryDirectory() as raw:
        tmp = pathlib.Path(raw); fake_claude(tmp)
        env = {**os.environ, "PATH": f"{tmp}:{os.environ['PATH']}", "FACTORY_MUX": "batch", "FACTORY_WORKER": "claude", "FACTORY_BATCH_STATE": str(tmp / "batch-state.json"), "BATCH_TIMEOUT": "0.7", "TELEMETRY_LOG_DIR": str(tmp / "telemetry")}
        caps = run(["doctor"], env)
        assert caps.returncode == 0, caps.stderr
        assert json.loads(caps.stdout)["mux"] == {"banner": False, "focus": False, "isolation": False, "layout": False, "native_status": True, "persistent_context": False}
        start(env)
        batch_state = json.loads(pathlib.Path(env["FACTORY_BATCH_STATE"]).read_text())
        assert next(iter(batch_state["agents"].values()))["argv"] == ["claude", "-p"]
        # Before a turn, a CLI wait must reject the absent status rather than read a stale buffer.
        pre_send_wait = run(["wait", "--role", "worker", "--timeout", "0", "--interval", "0"], env)
        assert pre_send_wait.returncode != 0 and "wait timed out" in pre_send_wait.stderr
        normal = turn(env, "NORMAL-TURN", "settled")
        assert "OK: NORMAL-TURN" in normal["output"]
        failed = turn(env, "FAIL-TURN", "failed")
        assert failed["output"] == ""
        rate_limited = turn(env, "RATE-LIMIT-TURN", "failed")
        assert "rate limit" in rate_limited["output"]
        question = turn(env, "QUESTION-TURN", "blocked")
        assert "QUESTION:" in question["output"]
        slow_sent = run(["send", "--role", "worker"], env, "SLOW-TURN")
        slow_wait = run(["wait", "--role", "worker", "--timeout", "1", "--interval", "0"], env)
        assert slow_sent.returncode == 0 and slow_wait.returncode == 0
        assert json.loads(slow_wait.stdout)["outcome"] == "timeout"

    print("test-batch-crew: PASS")


if __name__ == "__main__":
    main()
