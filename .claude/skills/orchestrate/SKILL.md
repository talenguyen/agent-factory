---
name: orchestrate
description: Use when the user asks to delegate a coding goal to Pi agents, have Pi build, fix, or implement work, or needs a worker-and-reviewer crew managed to a verified outcome.
user-invocable: true
---

# Orchestrate a crew

`bin/crew` owns the turn machinery. The orchestrator owns the judgment: choose
what to ask, inspect the artifact, decide whether it meets the goal, and report.
Use repository-local `bin/crew`, never a similarly named global command.

## Authority and escalation

The crew produces artifacts; the orchestrator performs outward-facing actions.
No crew member gets a send button.

MUST read POLICY.md itself and judge every blocked question against it.
`classify-risk` is an ADVISORY HINT: it can raise suspicion, can never CLEAR an action, and is never the gate. Its no-match result means no keyword matched; you must still judge the question itself. Keyword coverage is best-effort, never exhaustive.
Read the blocked question and its result. Answer only ordinary,
reversible clarification. For a risk match or uncertainty, hand control to the
human: quote the question and state the action, target, and reason.
Never resolve the risky step in the agent's place, work around it, or quietly finish it yourself.

## Lifecycle record

Read `references/shared-lifecycle.md`. For a raw goal, create a record with `bin/factory workflow begin --entry-point orchestrate --goal "$GOAL"`; for an approved existing run and plan, verify the approved-plan event before dispatch. Append concrete dispatch, crew state, observation, evidence, and policy events. Treat Evidence incomplete as `retrieve_context`, and only a Diagnosed, repairable failure with the observed defect and the required correction as a correction dispatch. Risky or outbound requests go to `human_approval`; denial or unavailable interactive UI is blocked. Capture final verification, review, tester, and mutation evidence, then run `bin/factory workflow validate --run "$RUN_ID" --terminal` before reporting. When no safe transition applies, end the crew delegation as escalated and request the exact human decision.

## Start with judgment

1. Resolve the domain and read its pack. Classify the goal as S, M, or L using
   scope, ambiguity, and sensitivity. Ask for explicit confirmation before an
   L-tier delegation. Write the acceptance spec and the §6b tester plan yourself;
   neither is delegated.
2. Decide whether reconnaissance would remove a material unknown. If so, give a
   scout a focused read-only question; otherwise do not spawn one.
3. Compose the worker prompt: goal, constraints, acceptance criteria, domain, worktree, and the requested artifact. Every follow-up names the observed artifact defect and the required correction; never use a vague retry.
4. Check the runtime and begin the delegation. For the `herdr` mux, fail loud
   when `HERDR_PANE_ID` is unset: the first spawn must anchor under the
   orchestrator's own pane, not whichever pane the operator focused. `bin/crew`
   captures the operator's current pane, focuses `HERDR_PANE_ID`, starts the
   first worker with `--no-focus`, then restores the operator's focus; later
   crew spawns stack beneath a crew pane and restore the operator's focus too.
   Carry the returned id in every later command. If the resolved mux declares `persistent_context: false`,
   every prompt must re-supply the plan, the ledger, and the current artifact state; choose those details from the actual work, not stale references.

```bash
bin/crew doctor
bin/crew begin --tier "$TIER" --domain "$DOMAIN" --goal-file acceptance.md
# export FACTORY_CREW_DELEGATION_ID from begin's delegation_id
bin/crew spawn --role worker
bin/crew spawn --role reviewer --stack-under "$WORKER_ID" # M/L only
bin/crew spawn --role tester --stack-under "$BOTTOM_ID"   # only when requested
```

## Drive turns through crew

Send the prompt and let crew report the outcome. `crew` enforces settlement,
role lifecycle, reuse, fallback, progress limits, telemetry, and recovery; do
not duplicate those rules here.

```bash
printf '%s' "$PROMPT" | bin/crew send --role worker
bin/crew wait --role worker
bin/crew read --role worker --recent --lines 200
bin/crew state
```

On `blocked`, classify the exact question before making the judgment in
[Authority and escalation](#authority-and-escalation):

```bash
printf '%s' "$QUESTION" | bin/crew classify-risk
```

On `failed`, ask crew to apply its permitted fallback; if it refuses or the
artifact cannot progress, hand control to the human. Use the state and ledger
as facts, not a substitute for judgment.

```bash
bin/crew fallback --role worker
bin/crew ledger append 'Round: observed result and decision.'
bin/crew round end --verdict changes_requested --diff-hash "$DIFF_HASH" # M/L
bin/crew turn end                                                   # S only
```

## Inspect and review the artifact

Read changed files for software and other code artifacts, then run the pack
verification yourself. **For research, do not read the whole diff:** run the
pack verifier and inspect its output; the report artifact is judged through
that domain's mechanical verifier. Verification before reporting success is mandatory; a worker's self-report is not evidence.

For M/L, compose a review request against the acceptance spec. The reviewer
reads the artifact itself from the shared worktree; never paste a diff into a
prompt. Require exactly `APPROVED` or exactly `CHANGES REQUESTED:` followed by
findings. Interpret its returned verdict literally through crew; retry once on a noncompliant verdict, then decide what finding to relay in the next worker prompt. A tester follows the orchestrator's
written black-box plan and reports findings, never fixes them.

```bash
printf '%s' "$REVIEW_REQUEST" | bin/crew send --role reviewer
bin/crew wait --role reviewer
bin/crew read --role reviewer --recent --lines 200
bin/crew verify
```

If tests, assertions, or guards were added or changed, added or changed tests, assertions, or guards require a counter-mutation gate: choose a mutation for each assertion. Break the protected behavior in a scratch copy or detached worktree, record its non-zero mutation exit, restore it, and record the zero control exit. Report both mutation and control exit codes. Judge whether those pairs prove each assertion rather than merely matching text. A failed gate is a finding to relay, not a reason to declare success.

Close short-lived scouts when their report has been judged:

```bash
bin/crew close --role scout
```

## Finish and report

Only after inspecting the artifact, verification output, review/tester result,
and applicable mutation pairs, decide goal met. End with the actual outcome;
escalation is a valid outcome, never an invitation to continue autonomously.

```bash
bin/crew end --outcome goal_met
# or: bin/crew end --outcome escalated
```

Report the goal, tier/domain, artifact inspected, verification output, reviewer
and tester facts, fallbacks, mutation/control exit-code pairs, and either the
result or the exact human decision needed next.

## Common mistakes

- Repeating adapter or lifecycle instructions instead of invoking `bin/crew`.
- Treating a policy classification as authorization rather than escalating.
- Trusting an agent verdict without reading the artifact and verifying it.
- Writing the acceptance spec or tester plan through a crew member.
- Calling an outward-facing tool from a crew prompt.
