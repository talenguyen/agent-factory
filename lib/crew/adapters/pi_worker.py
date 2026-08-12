#!/usr/bin/env python3
"""pi implementation of the crew worker boundary."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]


def main():
    if len(sys.argv) < 2:
        raise SystemExit("pi worker: missing verb")
    verb, args = sys.argv[1], sys.argv[2:]
    if verb == "worker_argv":
        provider, model, thinking, session_id, _skill_roots = args
        # opencode-go deepseek honors only off/high; intermediate thinking silently becomes high.
        print(json.dumps([str(ROOT / "bin" / "pi-project"), "--provider", provider, "--model", model, "--thinking", thinking, "--session-id", session_id]))
    elif verb == "worker_banner_pattern":
        print(r"\((?:openai-codex|opencode-go)\)\s+(?:gpt-5\.6-(?:terra|luna)|deepseek-v4-(?:flash|pro))\s+•\s+(?:thinking\s+off|low|medium|high)")
    elif verb == "worker_capabilities":
        print(json.dumps({"isolation": True, "session_resume": True}, sort_keys=True))
    else:
        raise SystemExit(f"pi worker: missing verb {verb}")


if __name__ == "__main__":
    main()
