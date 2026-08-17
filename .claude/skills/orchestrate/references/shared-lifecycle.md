# Shared orchestrator lifecycle

The normative lifecycle is:

`intake → classify → retrieve_context → plan → execute_loop ↔ observe_and_verify → policy_gate → respond`

Both `/autonomous-goal` and `/orchestrate` are root-orchestrator entry points. The root owns judgment and records artifacts in `.factory/runs/<run-id>/`; `bin/crew` alone owns `.factory/crew/<delegation-id>/`, worker reuse, fallback, caps, and turns. Workers produce artifacts only and never send, publish, deploy, merge, or otherwise act outwardly.

## Records

A raw request starts with `bin/factory workflow begin --entry-point <autonomous-goal|orchestrate> --goal "$GOAL"`. The helper creates `run.json`, `intake.md`, `ledger.jsonl`, `policy.jsonl`, and `evidence/`. Record classification, retrieved context and unknowns, the orchestrator-authored `plan.md` and `acceptance.md`, every dispatch and crew state, observation, evidence path, policy decision, and outcome with `bin/factory workflow append`. Use only the lifecycle stages in the contract. Do not copy or modify crew state.

`/autonomous-goal` writes and presents its plan and waits for explicit plan approval. `/orchestrate` either creates intake for a raw goal or attaches to an explicitly approved existing run and plan. Plan approval is not risk approval.

## Observe and feedback

Evidence must be fresh and independently observed; a worker self-report is never sufficient. If evidence is absent, stale, or insufficient, record **Evidence incomplete** and transition `observe_and_verify → retrieve_context` with the missing fact and retrieval question. A **Diagnosed, repairable failure** may transition `observe_and_verify → execute_loop` only when the observed defect and the required correction are recorded. A risky, protected, or outward-facing request transitions to `human_approval`; denial or unavailable interactive UI is terminal `blocked`. Unknown or unsafe failures, and crew-cap exhaustion, are terminal `escalated` states. Retries are concrete and bounded by `bin/crew`, never vague.

Before guarded actions and before the pre-delivery policy gate, read `POLICY.md` and the selected domain pack risk rules. Append the pre-action or pre-delivery decision to `policy.jsonl`; no approval means no action. `/autonomous-goal` and `/orchestrate` must run `bin/factory workflow validate --run "$RUN_ID" --terminal` before reporting completion. `respond` names the inspected artifacts, fresh verification output, review/tester/mutation evidence, actual outcome, and exact human decision needed; it never claims unverified success.
