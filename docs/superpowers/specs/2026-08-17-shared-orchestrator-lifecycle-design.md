# Design: Shared orchestrator lifecycle for autonomous goals and crew delegation

## Goal

Make `/autonomous-goal` and `/orchestrate` follow one durable request-handling and build lifecycle:

```text
intake → classify → retrieve_context → plan → execute_loop ↔ observe_and_verify → policy_gate → respond
```

The design applies to root Pi and Claude Code orchestrator sessions. Pi already discovers the repository's `.claude/skills` through `.pi/settings.json`, so both use the same skill definitions.

## Scope and constraints

- Preserve the existing `/autonomous-goal`, `/orchestrate`, and `/delegate-to-pi` commands and their roles.
- Keep `bin/crew` as the authority for worker lifecycle, worker reuse, fallback, round caps, progress detection, and telemetry.
- Keep judgment with the root orchestrator. Workers produce artifacts; they do not send, publish, deploy, merge, or otherwise perform outward-facing actions.
- Store run records in the target workspace's existing gitignored `.factory/` boundary. Do not create a competing state root.
- Do not add automatic approvals, commits, merges, deployments, publishing, or external communication.

## Architecture

### Shared workflow contract

Create one versioned workflow reference below `.claude/skills/`. It is the normative lifecycle contract referenced by both `/autonomous-goal` and `/orchestrate`.

The contract defines each stage's owner, required inputs, durable output, success condition, allowed next states, and escalation behavior. The two skills retain only their entry-point-specific behavior:

- `/autonomous-goal` always creates a run at intake, writes the plan and acceptance criteria itself, and requires explicit plan approval before work starts.
- `/orchestrate` creates a run when it receives a raw goal. It may instead attach to an explicitly approved existing run and plan, then begins at execution.
- `/delegate-to-pi` stays a compatibility alias that selects the Pi worker/mux configuration and invokes `/orchestrate`.

### Durable run record

Every run lives at `.factory/runs/<run-id>/` in the target workspace. The run directory contains:

| Path | Purpose |
|---|---|
| `run.json` | immutable run metadata: id, timestamps, entry point, workspace, and schema version |
| `intake.md` | normalized user request, constraints, and stated success outcome |
| `classification.json` | domain, tier, ambiguity, sensitivity, and rationale |
| `context.md` | context manifest: files, commands, domain-pack facts, and unknowns retrieved for the decision |
| `plan.md` | orchestrator-authored implementation plan |
| `acceptance.md` | mechanical, sourced, and rubric acceptance criteria |
| `ledger.jsonl` | append-only lifecycle events, transitions, dispatches, observation verdicts, and escalation reasons |
| `evidence/` | immutable captured verification, reviewer, tester, and mutation/control outputs plus metadata |
| `policy.jsonl` | append-only pre-action and pre-delivery policy decisions and human approval results |
| `outcome.json` | terminal outcome: `goal_met`, `blocked`, `escalated`, or `cancelled`, with evidence references |

Existing `.factory/crew/<delegation-id>/` state remains crew-owned. The workflow record references its delegation id rather than copying or modifying crew state.

### Schema helper

Add a small helper exposed through `bin/factory` for run-record creation and validation. It may:

- allocate collision-safe run ids and create the required layout;
- write only new harness-owned artifact paths;
- validate required artifacts, JSON shape, append-only event ordering, terminal outcomes, and evidence references;
- exit non-zero on missing, malformed, contradictory, or placeholder required records.

It must not choose a tier, interpret an artifact, authorize an action, dispatch a worker, or advance a lifecycle stage by itself. Those are orchestrator judgments. `bin/crew` remains the only worker-turn mechanism.

## Lifecycle contract

### 1. Intake

The orchestrator normalizes the request, target workspace, constraints, expected deliverable, and whether an approved plan is supplied. It creates `run.json`, `intake.md`, and the initial ledger event.

### 2. Classify

The orchestrator determines domain, S/M/L tier, ambiguity, sensitivity, and whether reconnaissance is material. The decision and its rationale are recorded in `classification.json`. An L-tier delegation retains its existing explicit confirmation requirement.

### 3. Retrieve context

The orchestrator reads the relevant repository files, current status/diff, domain pack, policy, existing artifacts, and any narrowly scoped reconnaissance result. The resulting facts and material unknowns are recorded in `context.md`.

### 4. Plan

The orchestrator writes `plan.md`, `acceptance.md`, and the tester plan where required. Acceptance criteria remain labelled `mechanical`, `sourced`, or `rubric`; rubric-only work cannot enter an unsupervised stretch without a specific human checkpoint. `/autonomous-goal` presents the plan and waits for explicit approval. `/orchestrate` requires an explicit approved-plan event before dispatch.

### 5. Execute loop

The orchestrator uses `/orchestrate` and `bin/crew` to dispatch bounded work. Every worker prompt includes the relevant plan, acceptance criteria, current artifact state, and a concrete request. Every dispatch, crew state, fallback, and correction request becomes a ledger event.

Before a potentially destructive, protected, risky, or outward-facing action, the orchestrator evaluates `POLICY.md` and the selected domain pack's risk gate. The pre-action decision is appended to `policy.jsonl`; no approval means no action.

### 6. Observe and verify

The orchestrator independently inspects the actual artifact and captures fresh verifier/tester/reviewer output under `evidence/`. A worker self-report is not evidence. Existing review, tester, and counter-mutation requirements remain in force.

The observation has exactly these automatic feedback transitions:

| Observation | Next state | Required record |
|---|---|---|
| Required evidence is absent, stale, or insufficient | `retrieve_context` | missing fact/evidence and retrieval question |
| A failure has a concrete, reversible correction | `execute_loop` | observed defect, requested correction, and prior evidence reference |
| A required action is risky or outward-facing | `human_approval` | action, target, reason, and relevant policy clause |
| The situation cannot be safely diagnosed or the crew cap blocks progress | terminal `escalated` | exact uncertainty/cap and human decision needed |

Retries are bounded by `bin/crew`; retries cannot be vague and cannot bypass policy. The design intentionally does not add an autonomous path for an unknown or unsafe failure.

### 7. Human approval (`human_approval`)

A risky/outbound transition pauses execution. The orchestrator quotes the requested action, target, and reason, then awaits explicit human approval. A denial, unavailable interactive UI, or unresolved request records `blocked` and prevents the action. Plan approval is not risk approval.

### 8. Policy gate and response

After acceptance evidence supports completion, the orchestrator evaluates the pre-delivery policy gate before any merge, PR, send, publish, deployment, payment, filing, or similar outward action. The decision is captured in `policy.jsonl`.

`respond` writes `outcome.json` and reports the goal, artifact inspected, fresh verification output, review/tester evidence, fallbacks, mutation/control evidence where applicable, policy decision, and either the final result or the exact human decision needed. It never claims success without recorded fresh evidence.

## Implementation changes

1. Add the shared lifecycle reference and schema-helper implementation/tests.
2. Update `/autonomous-goal` to create, fill, and validate run records around its existing plan-approval, build, risk, verification, review, and delivery checkpoints.
3. Update `/orchestrate` to attach crew activity and independent observation/verification to the same record, including all feedback transitions.
4. Retain `/delegate-to-pi` as the Pi-specific entry-point alias.
5. Extend the existing mutation-oriented skill tests and add artifact-schema tests.

## Verification plan

Mechanical tests must prove:

- both entry-point skills reference every lifecycle stage and required feedback transition;
- both Pi and Claude discover the shared skills directory without separate behavior definitions;
- a missing-evidence observation records a retrieval transition;
- a diagnosed repairable failure records a defect-specific retry;
- protected, risky, and outward-facing actions block for explicit human approval, and noninteractive/denied paths are terminal `blocked`;
- valid run records validate, while missing artifacts, placeholders, malformed JSON, invalid event order, and missing evidence references fail;
- existing plan-approval, rubric-only, independent verification, review, counter-mutation, crew-cap, fallback, and final-delivery tests continue to pass.

## Non-goals

This is an orchestration contract and evidence harness, not a security sandbox or autonomous workflow engine. It does not replace operating-system isolation, alter model configuration, implement product code, access credentials or production systems, create remote telemetry, or perform outward-facing delivery actions.
