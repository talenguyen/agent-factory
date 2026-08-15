---
name: autonomous-goal
description: Use when starting a standalone goal from an idea, feature, or bug that requires plan approval, a risk gate, and final delivery. Not for small in-flight edits already scoped in the current conversation.
user-invocable: true
---

# autonomous-goal

## Overview
Runs an approved goal through exactly three human checkpoints — plan approval, risk gate, and final delivery — with no routine mid-build confirmations. Domain packs generalize artifact verification, roles, isolation, required sub-skills, and delivery without weakening the checkpoints.

## The three checkpoints
| # | Checkpoint | Fires | Why it cannot be skipped |
|---|---|---|---|
| 1 | Plan approval | After planning, before work | The user approves the actual scope and acceptance oracle |
| 2 | Risk gate | Before irreversible, off-limits, or pack-risk action | No plan or pack overrides user authority |
| 3 | Final delivery | Before merge/PR or send/publish/submit/file | Delivery is the user's decision |

## Step 0: Clarify only if genuinely ambiguous
Ask one clarifying question only when plausible interpretations materially change the deliverable; otherwise proceed.

## Step 1: Plan and acceptance spec
Write the plan and `acceptance.md` yourself, never delegate either. Each deliverable has one or more criteria labelled `mechanical`, `sourced`, or `rubric`. A deliverable whose criteria are all **rubric-only** stops at Checkpoint 1: ask the user to add a specific human checkpoint or cut it from scope. Do not begin an unsupervised stretch otherwise.

## Step 2 — CHECKPOINT: Plan approval
Present the plan and acceptance spec and wait for explicit approval. Silence or an unrelated “sounds good” is not approval.

## Step 3: Build (unsupervised)
Resolve `DOMAIN` and read its fail-loud pack. Use the pack's workspace layout, required sub-skills, roles, tester analog, and Verify command. Work in an isolated git worktree when required; use `orchestrate` for implementation. Claude Code plans, reviews, and delivers; it never implements directly. The tester plan is written by Claude Code and exercises the pack's real-world tester analog, not merely the diff. Iterate ordinary reversible failures without pausing.

## Step 4 — CHECKPOINT: Risk gate
Stop before every **POLICY.md** Never/Off-limits action and every selected-pack Risk gate action. State the exact action, target, and reason; wait for explicit approval. Relay a worker's blocked question verbatim; never resolve it for the worker.

**Red flags — none authorize skipping this gate:**
- “The plan already implied this action.”
- “It is just a config or lock file, not real data.”
- “We will need to do this eventually anyway.”
- “The rest of the build was routine, so this probably is too.”

## Step 5: Verify
Run the pack Verify command and all applicable tests/build checks; read fresh output before treating the goal as complete.

## Step 6: Review
Request a code review of the artifact; apply its findings, or surface genuine judgment calls to the user.

## Step 7 — CHECKPOINT: Final delivery
Before merge/PR or send/publish/submit/file, present the final-delivery choice and wait. The crew produces artifacts only and never performs outward-facing actions.

## Common mistakes
| Mistake | Reality |
|---|---|
| Asking routine mid-build confirmation | Only the three checkpoints interrupt the unsupervised stretch |
| Treating a plan as risk-gate approval | Plan approval and risk approval are separate |
| Guessing ambiguity | Clarify in Step 0 before an unsupervised stretch |
| Delegating before plan approval | Step 1/2 always precede implementation |
| Treating review approval as the oracle | Run the pack Verify command and tester analog |
| Letting a rubric-only deliverable proceed | Add a human checkpoint or cut scope at Checkpoint 1 |
