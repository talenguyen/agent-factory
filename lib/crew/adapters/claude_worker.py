#!/usr/bin/env python3
"""Claude implementation of the crew worker boundary."""
import json
import sys


def main():
    if len(sys.argv) < 2:
        raise SystemExit("claude worker: missing verb")
    verb = sys.argv[1]
    if verb == "worker_argv":
        print(json.dumps(["claude", "-p"]))
    elif verb == "worker_banner_pattern":
        print("")
    elif verb == "worker_capabilities":
        print(json.dumps({"isolation": False, "session_resume": False}, sort_keys=True))
    else:
        raise SystemExit(f"claude worker: missing verb {verb}")


if __name__ == "__main__":
    main()
