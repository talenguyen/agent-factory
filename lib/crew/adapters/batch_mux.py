#!/usr/bin/env python3
"""One-subprocess-per-turn implementation of the crew mux boundary."""
import json
import os
import pathlib
import subprocess
import sys
import time
import uuid

RATE_LIMITS = ("rate limit", "429", "quota exceeded", "insufficient_quota", "usage limit reached")


def state_path():
    configured = os.environ.get("FACTORY_BATCH_STATE")
    if configured:
        return pathlib.Path(configured)
    return pathlib.Path.cwd() / ".factory" / "crew" / "batch-mux.json"


def load():
    path = state_path()
    if path.exists():
        return json.loads(path.read_text())
    return {"agents": {}}


def save(state):
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, sort_keys=True) + "\n")


def agent(state, identifier):
    try:
        return state["agents"][identifier]
    except KeyError:
        raise SystemExit(f"batch mux: unknown agent {identifier}")


def main():
    if len(sys.argv) < 2:
        raise SystemExit("batch mux: missing verb")
    verb, args = sys.argv[1], sys.argv[2:]
    if verb == "crew_capabilities":
        print(json.dumps({"layout": False, "focus": False, "persistent_context": False, "native_status": True, "banner": False, "isolation": False}, sort_keys=True))
        return
    state = load()
    if verb == "crew_list":
        print(json.dumps([{"id": identifier, "name": item["name"], "cwd": item["cwd"], "status": item["status"]} for identifier, item in state["agents"].items()]))
    elif verb == "crew_spawn":
        name, cwd, *tail = args
        if "--" not in tail:
            raise SystemExit("batch mux: crew_spawn requires -- ARGV")
        argv = tail[tail.index("--") + 1:]
        if not argv:
            raise SystemExit("batch mux: crew_spawn requires worker argv")
        identifier = f"batch-{uuid.uuid4()}"
        state["agents"][identifier] = {"name": name, "cwd": cwd, "argv": argv, "status": "unknown", "output": ""}
        save(state)
        print(json.dumps({"id": identifier}))
    elif verb == "crew_status":
        print(agent(state, args[0])["status"])
    elif verb == "crew_send":
        item = agent(state, args[0])
        prompt = sys.stdin.read()
        try:
            result = subprocess.run(item["argv"] + [prompt], text=True, capture_output=True, timeout=float(os.environ.get("BATCH_TIMEOUT", "600")), cwd=item["cwd"])
        except subprocess.TimeoutExpired as exc:
            item.update({"status": "timeout", "output": exc.stdout or ""})
        else:
            output = result.stdout
            if result.returncode or any(signature in output.lower() for signature in RATE_LIMITS):
                status = "failed"
            elif "QUESTION:" in output:
                status = "blocked"
            else:
                status = "settled"
            item.update({"status": status, "output": output})
        save(state)
        print(json.dumps({"sent": True}))
    elif verb == "crew_read":
        print(agent(state, args[0])["output"], end="")
    elif verb == "crew_close":
        del state["agents"][args[0]]
        save(state)
    elif verb == "crew_verify_profile":
        raise SystemExit(2)
    else:
        raise SystemExit(f"batch mux: missing verb {verb}")


if __name__ == "__main__":
    main()
