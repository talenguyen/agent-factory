#!/usr/bin/env bash
set -euo pipefail

readonly root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly instructions="$root/CLAUDE.md"

rg -Fqi 'interactive root Pi or Claude Code session is the orchestrator' "$instructions"
rg -Fqi 'after plan approval' "$instructions"
rg -Fq 'delegate-to-pi' "$instructions"
rg -Fq 'orchestrate' "$instructions"
rg -Fq 'bin/crew' "$instructions"
rg -Fq 'FACTORY_CREW_ROLE=worker' "$instructions"
rg -Fqi 'implements directly and never delegates onward' "$instructions"

printf '%s\n' 'test-orchestrator-role: PASS'
