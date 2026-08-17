# Shared Orchestrator Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `/autonomous-goal` and `/orchestrate` one durable intake-to-response lifecycle with validated workspace run records and explicit verification/policy feedback transitions.

**Architecture:** Add a small dependency-free `lib/workflow` module exposed through `bin/factory workflow`. It creates and validates `.factory/runs/<run-id>` records but never authorizes work or dispatches crew. A shared lifecycle reference becomes the single behavioral contract cited by both skill entry points; `bin/crew` remains the worker lifecycle authority.

**Tech Stack:** Python 3 standard library, Bash contract/mutation tests, Markdown skills and documentation.

**Spec:** `docs/superpowers/specs/2026-08-17-shared-orchestrator-lifecycle-design.md`

## Global Constraints

- Keep `/autonomous-goal`, `/orchestrate`, and `/delegate-to-pi` as the user-facing entry points.
- Pi and Claude must use the same repository-local `.claude/skills` lifecycle contract.
- Put all workflow state under the target workspace's gitignored `.factory/runs/`; retain `.factory/crew/` ownership in `bin/crew`.
- `bin/factory workflow` validates/persists artifacts only; it must not select a tier, authorize a policy action, spawn/send workers, or advance work by itself.
- Preserve root-orchestrator judgment, explicit plan/risk/final-delivery approval, independent verification, review, counter-mutation, and crew-cap behavior.
- Never auto-approve, commit, merge, deploy, publish, send, file, or access external systems.
- Use `python3` and `bash` explicitly; this repository has no package-manager test runner.

---

## File structure

| Path | Responsibility |
|---|---|
| `lib/workflow/__init__.py` | Marks the dependency-free workflow package. |
| `lib/workflow/runs.py` | Owns run-id allocation, artifact initialization, append-only stream writing, and schema/terminal validation. |
| `bin/factory` | Exposes `factory workflow begin`, `append`, and `validate` while retaining existing `doctor`, `init`, and `run` behavior. |
| `.claude/skills/orchestrate/references/shared-lifecycle.md` | Normative stage, artifact, transition, escalation, and policy contract shared by both entry points. |
| `.claude/skills/autonomous-goal/SKILL.md` | Starts/records an autonomous run; requires plan approval; follows shared lifecycle through response. |
| `.claude/skills/orchestrate/SKILL.md` | Attaches raw or approved-plan delegations to a run; records crew observations and follows feedback transitions. |
| `tests/test-workflow-runs.py` | Standalone Python unit/CLI-facing contract tests for run records and validation failures. |
| `tests/test-factory.sh` | Black-box coverage for `factory workflow` and generated-workspace `.factory/` ignore behavior. |
| `tests/test-autonomous-goal.sh` | Required lifecycle and artifact-contract assertions plus mutations for autonomous-goal prose. |
| `tests/test-orchestrate.sh` | Required lifecycle and feedback-transition assertions plus mutations for orchestrate prose. |
| `README.md` | Explains the shared lifecycle and where a workspace stores inspectable run evidence. |

## Run-record interface

Implement these exact public commands in `bin/factory`:

```bash
bin/factory workflow begin --entry-point autonomous-goal --goal 'Fix the parser'
bin/factory workflow append --run <run-id> --stream ledger --stage classify --event completed --details-json '{"tier":"S"}'
bin/factory workflow append --run <run-id> --stream policy --stage policy_gate --event approval_required --details-json '{"action":"publish","target":"docs"}'
bin/factory workflow validate --run <run-id>
bin/factory workflow validate --run <run-id> --terminal
```

`begin` operates in the current workspace, creates `.factory/runs/<UUID4>/`, writes `run.json`, `intake.md`, empty `policy.jsonl`, and one initial `ledger.jsonl` event, then prints exactly one JSON object with `run_id` and absolute `path`.

`append` assigns the next positive `sequence` and an ISO-8601 UTC `timestamp`; callers supply a known `stage`, `event`, and JSON-object details. The only valid streams are `ledger` and `policy`. A ledger event may reference evidence with a relative `evidence` array in its details. The helper rejects an unknown stream/stage, malformed details JSON, non-object details, an unknown run, and evidence paths that are absolute or escape `evidence/`.

`validate` always checks `run.json`, `intake.md`, append-only stream sequence ordering, known stages, parseable stream lines, and evidence references. `--terminal` additionally requires non-placeholder `classification.json`, `context.md`, `plan.md`, `acceptance.md`, at least one evidence file, a terminal `outcome.json` with one of `goal_met`, `blocked`, `escalated`, or `cancelled`, and a final ledger event at stage `respond`. It rejects `TBD`, `TODO`, `FIXME`, and `TBA` in required text artifacts.

Valid stages are exactly:

```python
STAGES = (
    "intake", "classify", "retrieve_context", "plan", "execute_loop",
    "observe_and_verify", "human_approval", "policy_gate", "respond",
)
```

The validator allows repeated events in a stage and only these stage transitions:

```python
ALLOWED_NEXT = {
    "intake": {"intake", "classify"},
    "classify": {"classify", "retrieve_context"},
    "retrieve_context": {"retrieve_context", "plan"},
    "plan": {"plan", "execute_loop"},
    "execute_loop": {"execute_loop", "observe_and_verify", "policy_gate"},
    "observe_and_verify": {"observe_and_verify", "retrieve_context", "execute_loop", "human_approval", "policy_gate"},
    "human_approval": {"human_approval", "execute_loop", "policy_gate", "respond"},
    "policy_gate": {"policy_gate", "execute_loop", "respond"},
    "respond": {"respond"},
}
```

This permits the three declared observation feedback targets—`observe_and_verify → retrieve_context`, `observe_and_verify → execute_loop`, and `observe_and_verify → human_approval`—and policy checks before guarded execution or before response. It also permits terminal escalation/blocked response events, but rejects a terminal run whose final event is not `respond`.

### Task 1: Create and test the run-record module

**Files:**
- Create: `lib/workflow/__init__.py`
- Create: `lib/workflow/runs.py`
- Create: `tests/test-workflow-runs.py`

**Interfaces:**
- Consumes: a target workspace `pathlib.Path`, an entry point string, and JSON-safe event details.
- Produces: `create_run(workspace: pathlib.Path, entry_point: str, goal: str) -> dict`, `append_event(run_dir: pathlib.Path, stream: str, stage: str, event: str, details: dict) -> dict`, and `validate_run(run_dir: pathlib.Path, terminal: bool = False) -> None`.
- Defines: `WorkflowError(Exception)`, `STAGES`, `TERMINAL_OUTCOMES`, and `SCHEMA_VERSION = 1` for `bin/factory` and tests.

- [ ] **Step 1: Write failing creation and stream tests**

Create `tests/test-workflow-runs.py` with a `tempfile.TemporaryDirectory()` workspace and tests that call the public functions directly:

```python
record = create_run(workspace, "autonomous-goal", "Fix the parser")
run_dir = pathlib.Path(record["path"])
assert run_dir.parent == workspace / ".factory" / "runs"
assert json.loads((run_dir / "run.json").read_text())["entry_point"] == "autonomous-goal"
assert "Fix the parser" in (run_dir / "intake.md").read_text()
first = [json.loads(line) for line in (run_dir / "ledger.jsonl").read_text().splitlines()]
assert first[0]["sequence"] == 1 and first[0]["stage"] == "intake"

entry = append_event(run_dir, "ledger", "classify", "completed", {"tier": "S"})
assert entry["sequence"] == 2
assert [json.loads(line)["sequence"] for line in (run_dir / "ledger.jsonl").read_text().splitlines()] == [1, 2]
```

Also add tests that expect `WorkflowError` for `stream="audit"`, `stage="build"`, non-dict details, invalid JSON passed through the CLI wrapper later, and `{"evidence": ["../secret.log"]}`.

- [ ] **Step 2: Run the focused test and confirm failure**

Run:

```bash
python3 tests/test-workflow-runs.py
```

Expected: non-zero because `lib.workflow.runs` does not exist.

- [ ] **Step 3: Implement minimal creation and append behavior**

Create `lib/workflow/__init__.py` as an empty package marker. In `lib/workflow/runs.py`, use `uuid.uuid4()`, `datetime.now(timezone.utc).isoformat()`, `json.dumps(..., sort_keys=True)`, and `Path.mkdir(parents=True, exist_ok=False)` to implement the three public interfaces. `create_run` must create only its UUID-named directory, never overwrite an existing run, and write:

```json
{"entry_point":"autonomous-goal","run_id":"<uuid>","schema_version":1,"workspace":"<absolute path>","created_at":"<UTC timestamp>"}
```

`append_event` must read the target JSONL stream, verify its existing sequence is `1..n`, assign `n + 1`, and append one newline-delimited object with `sequence`, `timestamp`, `stage`, `event`, and `details`. Validate stream/stage/details/evidence before opening the file for append.

- [ ] **Step 4: Run focused tests and confirm pass**

Run:

```bash
python3 tests/test-workflow-runs.py
```

Expected: PASS output and exit 0 for the creation/append cases; invalid inputs are caught by asserted `WorkflowError` paths.

- [ ] **Step 5: Write failing terminal-validation tests**

Extend `tests/test-workflow-runs.py` with a helper that writes a complete terminal run. It must require all four text artifacts, one `evidence/verify.log`, and `outcome.json`:

```python
(run_dir / "classification.json").write_text(json.dumps({"tier": "S", "domain": "software"}))
for name in ("context.md", "plan.md", "acceptance.md"):
    (run_dir / name).write_text("recorded facts\n")
(run_dir / "evidence").mkdir()
(run_dir / "evidence" / "verify.log").write_text("exit 0\n")
for stage in ("classify", "retrieve_context", "plan", "execute_loop", "observe_and_verify", "policy_gate"):
    append_event(run_dir, "ledger", stage, "completed", {})
append_event(run_dir, "ledger", "respond", "completed", {"evidence": ["evidence/verify.log"]})
(run_dir / "outcome.json").write_text(json.dumps({"outcome": "goal_met", "evidence": ["evidence/verify.log"]}))
validate_run(run_dir, terminal=True)
```

Add independent failing cases for a missing `plan.md`, `TBD` in `context.md`, malformed `outcome.json`, `outcome="success"`, a noncontiguous ledger sequence, a missing referenced evidence file, and a terminal run that ends at `policy_gate` rather than `respond`.

- [ ] **Step 6: Run the focused test and confirm failure**

Run:

```bash
python3 tests/test-workflow-runs.py
```

Expected: non-zero because `validate_run` is absent or does not enforce the terminal contract.

- [ ] **Step 7: Implement terminal validation**

Implement `validate_run`. It must parse `run.json`, verify `schema_version`, UUID-shaped `run_id`, supported entry point, absolute matching workspace, and non-empty intake. Parse each JSONL stream and reject malformed JSON, non-object records, missing required event keys, a sequence other than `1..n`, or a transition absent from `ALLOWED_NEXT`. Verify referenced evidence in event details and `outcome.json` is a normalized relative path below `evidence/` and exists as a file. For `terminal=True`, enforce the required artifacts, placeholder scan, at least one evidence file, a supported `outcome`, a non-empty outcome evidence array, and a final ledger `respond` event. Raise `WorkflowError` with a path-specific message for every failure.

- [ ] **Step 8: Run focused tests and confirm pass**

Run:

```bash
python3 tests/test-workflow-runs.py
```

Expected: PASS output and exit 0, with every invalid fixture rejected by a specific asserted error substring.

- [ ] **Step 9: Commit the self-contained run-record module**

```bash
git add lib/workflow/__init__.py lib/workflow/runs.py tests/test-workflow-runs.py
git commit -m "Add workflow run record validation"
```

### Task 2: Expose the schema helper and workspace ignore through `bin/factory`

**Files:**
- Modify: `bin/factory`
- Modify: `tests/test-factory.sh`

**Interfaces:**
- Consumes: the Task 1 public functions and current working directory as the workspace.
- Produces: `bin/factory workflow begin|append|validate` commands with the exact interface in **Run-record interface**.
- Preserves: `bin/factory doctor`, `init`, and `run`; `run` still prints instructions and does not drive the worker loop.

- [ ] **Step 1: Write failing black-box command tests**

In `tests/test-factory.sh`, after the successful `factory init` assertion, add:

```bash
grep -Fx '.factory/' "$workspace/.gitignore" >/dev/null
(
  cd "$workspace"
  run_factory workflow begin --entry-point autonomous-goal --goal 'Fix parser' >"$scratch/workflow-begin.json"
)
run_id="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["run_id"])' "$scratch/workflow-begin.json")"
[[ -f "$workspace/.factory/runs/$run_id/run.json" ]]
(
  cd "$workspace"
  run_factory workflow append --run "$run_id" --stream ledger --stage classify --event completed --details-json '{"tier":"S"}'
  run_factory workflow validate --run "$run_id"
)
```

Add mutations that must fail: `--entry-point unknown`, malformed `--details-json`, `--stream audit`, and `workflow validate --run missing`.

- [ ] **Step 2: Run the black-box test and confirm failure**

Run:

```bash
bash tests/test-factory.sh
```

Expected: non-zero because the `workflow` subcommand and `.factory/` scaffold ignore do not yet exist.

- [ ] **Step 3: Implement the CLI wiring**

In `bin/factory`, insert `ROOT / "lib"` once as today and import `WorkflowError`, `append_event`, `create_run`, and `validate_run`. Add a `workflow` parser with required nested subcommands:

```python
workflow = commands.add_parser("workflow")
workflow_sub = workflow.add_subparsers(dest="workflow_command", required=True)
begin = workflow_sub.add_parser("begin")
begin.add_argument("--entry-point", choices=("autonomous-goal", "orchestrate"), required=True)
begin.add_argument("--goal", required=True)
append = workflow_sub.add_parser("append")
append.add_argument("--run", required=True)
append.add_argument("--stream", choices=("ledger", "policy"), required=True)
append.add_argument("--stage", required=True)
append.add_argument("--event", required=True)
append.add_argument("--details-json", required=True)
validate = workflow_sub.add_parser("validate")
validate.add_argument("--run", required=True)
validate.add_argument("--terminal", action="store_true")
```

Resolve run ids only as `.factory/runs/<run-id>` under `Path.cwd()`; reject path separators. Print JSON for `begin`/`append`; print a single success line for `validate`. Catch `WorkflowError` beside `CrewError` and preserve the existing `factory: <message>` non-zero failure convention. Change `init`'s generated `.gitignore` content to include both `var/` and `.factory/`.

- [ ] **Step 4: Run the black-box test and confirm pass**

Run:

```bash
bash tests/test-factory.sh
```

Expected: PASS, including existing doctor/init/run/clean-checkout assertions and the new workflow controls and rejection cases.

- [ ] **Step 5: Commit the CLI integration**

```bash
git add bin/factory tests/test-factory.sh
git commit -m "Expose workflow artifact commands"
```

### Task 3: Define the shared lifecycle contract and wire autonomous goals to it

**Files:**
- Create: `.claude/skills/orchestrate/references/shared-lifecycle.md`
- Modify: `.claude/skills/autonomous-goal/SKILL.md`
- Modify: `tests/test-autonomous-goal.sh`

**Interfaces:**
- Consumes: `bin/factory workflow begin|append|validate`, `POLICY.md`, domain packs, and the existing plan/review/verification rules.
- Produces: an `autonomous-goal` run id and complete `.factory/runs/<id>` artifacts before final response.
- Preserves: exactly the existing three human checkpoints; plan approval does not imply risk approval.

- [ ] **Step 1: Write failing skill-contract tests**

Extend `tests/test-autonomous-goal.sh` to require, after stripping comments:

```bash
rg -Fq '.claude/skills/orchestrate/references/shared-lifecycle.md' "$clean_goal"
for phrase in \
  'intake → classify → retrieve_context → plan → execute_loop ↔ observe_and_verify → policy_gate → respond' \
  'bin/factory workflow begin --entry-point autonomous-goal' \
  'bin/factory workflow append' \
  'bin/factory workflow validate --run' \
  'Evidence incomplete' \
  'retrieve_context' \
  'Diagnosed, repairable failure' \
  'human_approval' \
  'denial or unavailable interactive UI' \
  'pre-delivery policy gate'; do
  rg -Fqi "$phrase" "$clean_goal" || exit 1
done
```

Add those phrases to the test's existing mutation target list so replacing each with `TBD` fails while the unmodified control passes.

- [ ] **Step 2: Run the skill test and confirm failure**

Run:

```bash
bash tests/test-autonomous-goal.sh
```

Expected: non-zero because the shared reference and lifecycle artifact instructions are absent.

- [ ] **Step 3: Write the normative lifecycle reference**

Create `.claude/skills/orchestrate/references/shared-lifecycle.md` with all of the following exact operational rules:

- stage order: `intake → classify → retrieve_context → plan → execute_loop ↔ observe_and_verify → policy_gate → respond`;
- run layout and the ownership boundary between `.factory/runs/<run-id>` and `.factory/crew/<delegation-id>`;
- use of `bin/factory workflow begin`, `append`, and terminal `validate`;
- evidence must be fresh and independently observed, never a worker self-report;
- `observe_and_verify → retrieve_context` only for absent/stale/insufficient evidence;
- `observe_and_verify → execute_loop` only for an explicitly diagnosed reversible defect, naming the defect and correction;
- `observe_and_verify → human_approval` for risky/outbound actions; denial or noninteractive operation is `blocked`;
- unknown/unsafe failures and crew-cap exhaustion are terminal `escalated` states;
- `POLICY.md` plus pack risk rules are checked before guarded actions and before delivery actions;
- `respond` names evidence and the actual outcome without claiming unverified success.

- [ ] **Step 4: Update `/autonomous-goal` minimally around existing checkpoints**

Add an initial lifecycle section before current Step 0 that requires starting a run with:

```bash
RUN_JSON="$(bin/factory workflow begin --entry-point autonomous-goal --goal "$GOAL")"
RUN_ID="$(printf '%s' "$RUN_JSON" | jq -r .run_id)"
```

Require the orchestrator to record intake, classification, context, plan approval, each worker dispatch, every observation, captured evidence path, policy decision, and terminal response via `bin/factory workflow append`. Keep current numbered checkpoints and insert the lifecycle reference rather than duplicating its full rules. Before treating delivery as complete, require:

```bash
bin/factory workflow validate --run "$RUN_ID" --terminal
```

Do not instruct workers to manage records or to perform policy-gated actions. Preserve all current wording required by `tests/test-autonomous-goal.sh` unless a replacement test intentionally proves the stronger lifecycle behavior.

- [ ] **Step 5: Run the skill test and confirm pass**

Run:

```bash
bash tests/test-autonomous-goal.sh
```

Expected: PASS with all prior checkpoint and mutation tests plus the new lifecycle contract/mutation checks.

- [ ] **Step 6: Commit the contract and autonomous entry point**

```bash
git add .claude/skills/orchestrate/references/shared-lifecycle.md .claude/skills/autonomous-goal/SKILL.md tests/test-autonomous-goal.sh
git commit -m "Add lifecycle records to autonomous goals"
```

### Task 4: Wire crew orchestration to the shared lifecycle and test feedback paths

**Files:**
- Modify: `.claude/skills/orchestrate/SKILL.md`
- Modify: `tests/test-orchestrate.sh`
- Modify: `README.md`

**Interfaces:**
- Consumes: an existing approved run id/plan or a raw goal requiring intake through plan, the shared lifecycle reference, `bin/crew`, and `bin/factory workflow`.
- Produces: recorded bounded dispatches, observations, evidence references, policy decisions, and a terminal outcome.
- Preserves: `bin/crew` lifecycle commands, direct artifact inspection, independent review/tester behavior, counter-mutation gate, risk authority, and final `crew end` outcome.

- [ ] **Step 1: Write failing orchestrate-contract tests**

Extend `tests/test-orchestrate.sh` to require the shared reference and each behavior phrase:

```bash
for invariant in \
  'shared-lifecycle.md' \
  'bin/factory workflow begin --entry-point orchestrate' \
  'approved existing run and plan' \
  'Evidence incomplete' \
  'retrieve_context' \
  'Diagnosed, repairable failure' \
  'observed defect and the required correction' \
  'human_approval' \
  'denial or unavailable interactive UI' \
  'pre-delivery policy gate' \
  'bin/factory workflow validate --run'; do
  rg -Fqi "$invariant" "$clean" || exit 1
done
```

Add each phrase to the test's mutation target array. Retain the current `<250` line guard by moving shared prose into the reference rather than bloating `SKILL.md`.

- [ ] **Step 2: Run the orchestrate skill test and confirm failure**

Run:

```bash
bash tests/test-orchestrate.sh
```

Expected: non-zero because orchestration does not yet require the lifecycle contract or artifact commands.

- [ ] **Step 3: Update `/orchestrate` without duplicating crew mechanics**

Add a short **Lifecycle record** section before `Start with judgment`. It must tell the root orchestrator to:

1. read the shared reference;
2. create a run for a raw goal with `bin/factory workflow begin --entry-point orchestrate --goal "$GOAL"`, or verify the supplied run has an approved plan before dispatch;
3. append concrete dispatch, state, observation, evidence, and policy events;
4. route missing evidence to context retrieval, only diagnosed reversible defects to a correction dispatch, and risky/outbound action requests to human approval;
5. capture final verification/review/tester/mutation evidence and terminally validate the run before reporting.

Keep all existing `bin/crew` commands and authority instructions intact. Do not move crew retry cap values into prose; continue relying on `bin/crew`. When no safe transition applies, end the crew delegation as escalated and request the exact human decision.

- [ ] **Step 4: Document the operator-visible evidence location**

Add a concise README paragraph after the existing loop description:

```markdown
Every `/autonomous-goal` and `/orchestrate` run records its intake, plan, evidence, policy decisions, and outcome at `.factory/runs/<run-id>/` in the target workspace. `bin/factory workflow validate --run <run-id> --terminal` fails if terminal evidence is incomplete or malformed; it validates records but never drives workers or authorizes actions.
```

- [ ] **Step 5: Run the orchestrate and factory tests and confirm pass**

Run:

```bash
bash tests/test-orchestrate.sh
bash tests/test-factory.sh
```

Expected: both PASS. The orchestrate test must still prove every prior crew command/invariant and the new lifecycle transitions; the factory test must prove schema commands remain black-box usable.

- [ ] **Step 6: Commit the orchestration integration**

```bash
git add .claude/skills/orchestrate/SKILL.md tests/test-orchestrate.sh README.md
git commit -m "Apply shared lifecycle to orchestration"
```

### Task 5: Run the complete mechanical suite and independently review the artifact

**Files:**
- Modify only if a focused test exposes a real contract inconsistency in Tasks 1–4.
- Do not stage unrelated files already present in the root worktree.

**Interfaces:**
- Consumes: all prior implementation artifacts and repository standalone test scripts.
- Produces: fresh evidence that the full factory suite and clean-checkout harness pass, plus a reviewer verdict against the spec.

- [ ] **Step 1: Run every standalone repository test**

Run:

```bash
for t in tests/test-*.sh; do bash "$t" || echo "FAIL $t"; done
for t in tests/test-*.py; do python3 "$t" || echo "FAIL $t"; done
```

Expected: every script exits 0. If any script reports `FAIL`, record the exact command/output in the workflow evidence and return to the applicable task with a defect-specific correction.

- [ ] **Step 2: Run clean-checkout verification**

Run:

```bash
bin/ci-clean-checkout
```

Expected: `ci-clean-checkout: PASS`; this proves the changes do not accidentally depend on ignored/untracked root files or live agents.

- [ ] **Step 3: Inspect scope and run targeted mutation controls**

Run:

```bash
git status --short
git diff --check
git diff -- .claude/skills/autonomous-goal/SKILL.md .claude/skills/orchestrate/SKILL.md .claude/skills/orchestrate/references/shared-lifecycle.md bin/factory lib/workflow tests README.md
bash tests/test-autonomous-goal.sh
bash tests/test-orchestrate.sh
```

Expected: no whitespace errors; only implementation-owned paths are staged/committed; skill mutation/control harnesses pass with the new invariants.

- [ ] **Step 4: Request independent crew review**

Use `/orchestrate` with an M-tier reviewer against the spec and implementation. Require the reviewer to inspect the actual files and return exactly `APPROVED` or `CHANGES REQUESTED:`. The reviewer must verify at minimum: no behavior drift between Pi and Claude skills, no workflow helper authorization/dispatch behavior, terminal validation rejects incomplete evidence, feedback transitions do not permit vague retries, and existing policy/crew boundaries remain intact.

- [ ] **Step 5: Address review findings and re-run affected evidence**

For each `CHANGES REQUESTED:` finding, record it as an observed artifact defect, make the smallest correction, rerun the specific failing test and then the complete suite from Step 1. Escalate genuine policy or design judgment calls rather than changing the approved scope.

- [ ] **Step 6: Commit any review-driven corrections**

```bash
git add .claude/skills/autonomous-goal/SKILL.md .claude/skills/orchestrate/SKILL.md \
  .claude/skills/orchestrate/references/shared-lifecycle.md \
  bin/factory lib/workflow tests/test-workflow-runs.py tests/test-factory.sh \
  tests/test-autonomous-goal.sh tests/test-orchestrate.sh README.md
git commit -m "Address lifecycle review findings"
```

Do not use `git add .`; leave pre-existing unrelated modifications and untracked files untouched.

## Plan self-review

- **Spec coverage:** Task 1 implements durable run schema, append-only records, evidence references, terminal outcomes, and artifact validation. Task 2 exposes the non-authorizing helper and makes generated workspaces ignore `.factory/`. Tasks 3–4 apply the shared flow to both entry points, including explicit feedback transitions, human approval, pre-action/pre-delivery policy gates, and final response evidence. Task 5 preserves and verifies crew/review/mutation constraints.
- **Placeholder scan:** No placeholder instructions are used; every task names paths, interfaces, commands, expected results, and failure conditions.
- **Type consistency:** `create_run`, `append_event`, `validate_run`, `WorkflowError`, `STAGES`, `TERMINAL_OUTCOMES`, and `SCHEMA_VERSION` are defined in Task 1 and consumed consistently by Tasks 2–4.
