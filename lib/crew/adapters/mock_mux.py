#!/usr/bin/env python3
"""Fixture-backed mux adapter; usable without herdr or pi."""
import json, os, pathlib, sys

if "FACTORY_MOCK_FIXTURE" not in os.environ: raise SystemExit("mock: FACTORY_MOCK_FIXTURE is required")
if "FACTORY_MOCK_STATE" not in os.environ: raise SystemExit("mock: FACTORY_MOCK_STATE is required")
fixture = pathlib.Path(os.environ["FACTORY_MOCK_FIXTURE"])
state_path = pathlib.Path(os.environ["FACTORY_MOCK_STATE"])
if state_path.exists():
    state = json.loads(state_path.read_text())
else:
    state = json.loads(fixture.read_text())
    state.setdefault("agents", [])
    state.setdefault("statuses", {})
    state.setdefault("reads", {})
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state))

def save():
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state))

def agent(identifier):
    for item in state["agents"]:
        if item["id"] == identifier:
            return item
    raise SystemExit(f"mock: unknown agent {identifier}")

def main():
    if len(sys.argv) < 2: raise SystemExit("mock: missing verb")
    verb, args = sys.argv[1], sys.argv[2:]
    if verb == "crew_capabilities": print(json.dumps(state["capabilities"]))
    elif verb == "crew_list": print(json.dumps(state["agents"]))
    elif verb == "crew_spawn":
        name, cwd = args[0], args[1]
        identifier = f"mock-{len(state['agents']) + 1}"
        state["agents"].append({"id": identifier, "name": name, "cwd": cwd, "status": "settled"})
        state.setdefault("spawn_argv", []).append(args[2:])
        save(); print(json.dumps({"id": identifier}))
    elif verb == "crew_status":
        item = agent(args[0]); seq = state["statuses"].get(item["id"], [])
        if seq: item["status"] = seq.pop(0)
        state.setdefault("status_reads", []).append(item["status"])
        save()
        print(item["status"])
    elif verb == "crew_send": sys.stdin.read(); print(json.dumps({"sent": True}))
    elif verb == "crew_read": print(state["reads"].get(args[0], ""), end="")
    elif verb == "crew_close": agent(args[0])["status"] = "closed"; save()
    elif verb == "crew_verify_profile":
        state.setdefault("verify_profiles", []).append(args)
        save()
        if not state["capabilities"]["banner"]: raise SystemExit(2)
    else: raise SystemExit(f"mock: missing verb {verb}")
if __name__ == "__main__": main()
