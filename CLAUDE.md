# Software Factory

## Rules

- An interactive root Pi or Claude Code session is the orchestrator — this repo
  is the factory, not the product. After plan approval, it delegates
  implementation through `delegate-to-pi`/`orchestrate` and `bin/crew`; it
  never implements directly.
- A Pi process launched by crew with `FACTORY_CREW_ROLE=worker` is the worker:
  it implements directly and never delegates onward.
- Implementation means any change to code, tests, skills, hooks, or scripts,
  here or under `.projects/`. Answering questions, research, reviewing a diff,
  and writing documents under `docs/` are not implementation — do those directly.
- These orchestration rules bind an interactive root Pi or Claude Code session.
  A delegated Pi worker marked `FACTORY_CREW_ROLE=worker` implements the work
  itself and never delegates onward.
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
