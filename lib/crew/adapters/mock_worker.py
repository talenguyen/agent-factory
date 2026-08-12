#!/usr/bin/env python3
"""Trivial worker adapter for fixture-only crew runs."""
import json, sys
verb = sys.argv[1] if len(sys.argv) > 1 else ""
if verb == "worker_argv": print(json.dumps(["mock-worker", *sys.argv[2:]]))
elif verb == "worker_banner_pattern": print("mock")
elif verb == "worker_capabilities": print(json.dumps({"isolation": True, "session_resume": True}))
else: raise SystemExit(f"mock worker: missing verb {verb}")
