# Software Factory

## Rules

- Claude Code never implements directly — this repo is the factory, not the
  product, and the delegation loop is the thing being built. Always delegate
  implementation to a Pi worker via `delegate-to-pi`, launched through
  `./bin/pi-project` — never bare `pi`.
- Implementation means any change to code, tests, skills, hooks, or scripts,
  here or under `.projects/`. Answering questions, research, reviewing a diff,
  and writing documents under `docs/` are not implementation — do those directly.
- This rule binds the orchestrating Claude Code session only. A delegated Pi
  worker reading this file IS the delegate: it implements the work itself and
  never delegates onward.
- Every new project goes under `.projects/<name>/` as its own independent git
  repo. Never commit project code into this repo's history (`.projects/` is
  gitignored).

## Commands

No package manager and no test runner. Tests are standalone scripts — always
call the interpreter explicitly:

- Full suite:
  `for t in tests/test-*.sh; do bash "$t" || echo "FAIL $t"; done; for t in tests/test-*.py; do python3 "$t" || echo "FAIL $t"; done`
- Single test: `bash tests/test-domain-pack-loader.sh`, `python3 tests/test-verify-research.py`
- Research verifier: `bin/verify-research --workspace <path>`
- Telemetry: `bin/telemetry-report` (`--html` for the dashboard)

## Working here

- For a standalone build from an idea, feature, or bug (not a small in-flight
  edit already scoped in conversation), use the `autonomous-goal` skill
  (`/autonomous-goal <idea>`). `/autonomous-build` still works as the
  software-pinned alias. It runs plan approval, risk gate, and final delivery,
  and delegates implementation to Pi.
