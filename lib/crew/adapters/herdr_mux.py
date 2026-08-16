#!/usr/bin/env python3
"""herdr implementation of the crew mux boundary."""
import json
import os
import re
import subprocess
import sys
import time


def call(*args, allow_empty=False):
    try:
        result = subprocess.run(["herdr", *args], text=True, capture_output=True)
    except FileNotFoundError:
        raise SystemExit("herdr mux: herdr executable not found")
    if result.returncode:
        raise SystemExit(result.stderr.strip() or f"herdr {' '.join(args)} failed")
    if allow_empty and not result.stdout.strip(): return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"herdr returned malformed JSON: {exc}")


def result_value(reply, *keys):
    value = reply.get("result", {})
    try:
        for key in keys:
            value = value[key]
    except (KeyError, TypeError):
        raise SystemExit(f"herdr mux: malformed response; missing result.{'.'.join(keys)}")
    return value


def status(value):
    return {"idle": "settled", "done": "settled", "blocked": "blocked", "working": "working"}.get(value, "unknown")


def profile_banner_matches(provider, model, thinking, text):
    pattern = rf"(?:\({re.escape(provider)}\)\s+)?{re.escape(model)}\s+•\s+{re.escape(thinking)}"
    return re.search(pattern, text) is not None


def main():
    if len(sys.argv) < 2:
        raise SystemExit("herdr mux: missing verb")
    verb, args = sys.argv[1], sys.argv[2:]
    if verb == "crew_capabilities":
        print(json.dumps({"layout": True, "focus": True, "persistent_context": True, "native_status": True, "banner": True, "isolation": True}, sort_keys=True))
    elif verb == "crew_list":
        agents = result_value(call("agent", "list"), "agents")
        print(json.dumps([{"id": agent["pane_id"], "name": agent.get("name"), "cwd": agent["cwd"], "status": status(agent.get("agent_status"))} for agent in agents]))
    elif verb == "crew_spawn":
        name, cwd, *tail = args
        stack_under = None
        if len(tail) >= 2 and tail[0] == "--stack-under":
            stack_under, tail = tail[1], tail[2:]
        if not tail or tail[0] != "--":
            raise SystemExit("herdr mux: crew_spawn requires -- ARGV")
        argv = tail[1:]
        if stack_under:
            target, direction = stack_under, "down"
        else:
            target = os.environ.get("HERDR_PANE_ID")
            if not target:
                raise SystemExit("herdr mux: HERDR_PANE_ID is unset; cannot safely anchor first crew spawn")
            direction = "right"
        current = result_value(call("pane", "current"), "pane", "pane_id")
        call("agent", "focus", target)
        try:
            reply = call("agent", "start", name, "--cwd", cwd, "--split", direction, "--no-focus", "--", *argv)
        finally:
            call("agent", "focus", current)
        identifier = result_value(reply, "agent", "pane_id")
        print(json.dumps({"id": identifier}))
    elif verb == "crew_status":
        print(status(result_value(call("agent", "get", args[0]), "agent", "agent_status")))
    elif verb == "crew_send":
        prompt = sys.stdin.read()
        call("agent", "send", args[0], prompt)
        call("pane", "send-keys", args[0], "enter", allow_empty=True)
        print(json.dumps({"sent": True}))
    elif verb == "crew_read":
        identifier = args[0]
        source = "recent-unwrapped" if "--recent" in args else "visible"
        command = ["agent", "read", identifier, "--source", source]
        if "--lines" in args:
            command.extend(["--lines", args[args.index("--lines") + 1]])
        reply = call(*command)
        print(result_value(reply, "read", "text"), end="")
    elif verb == "crew_close":
        call("pane", "close", args[0])
    elif verb == "crew_verify_profile":
        identifier, provider, model, thinking = args
        call("pane", "zoom", identifier, "--on")
        try:
            text = ""
            render_deadline = time.monotonic() + float(os.environ.get("HERDR_RENDER_TIMEOUT", "8"))
            while True:
                text = result_value(call("agent", "read", identifier, "--source", "visible", "--lines", "200"), "read", "text")
                if text.strip() or time.monotonic() >= render_deadline: break
                time.sleep(float(os.environ.get("HERDR_RENDER_INTERVAL", "0.5")))
        finally:
            call("pane", "zoom", identifier, "--off")
        if not text.strip(): raise SystemExit("herdr mux: profile banner failed to render")
        if not profile_banner_matches(provider, model, thinking, text):
            raise SystemExit("herdr mux: profile banner did not match")
    else:
        raise SystemExit(f"herdr mux: missing verb {verb}")


if __name__ == "__main__":
    main()
