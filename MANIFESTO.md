# Why this shape

Multi-agent orchestration is a crowded category. This project is not interesting
because it runs several agents. It is interesting because of the constraints that
make an **unsupervised stretch** trustworthy.

Each constraint below is load-bearing, and each points at the code that enforces
it. Where a rule is only prose, it says so — that is a weakness, not a style.

---

## 1. One human-facing agent

You talk to the orchestrator. Crew members never address you. A worker that needs
a human decision reports it as a blocked question and the orchestrator escalates.

*Enforced by:* the authority boundary below, and `orchestrate/SKILL.md`'s
escalation rule.

## 2. The orchestrator never implements

It plans, verifies, and integrates. Implementation is delegated. This is not
ceremony: an agent that writes the code and then judges the code has no
independent view of it.

*Enforced by:* `CLAUDE.md`. Prose — a known soft spot.

## 3. Self-reports are not evidence

Every claim of done is checked against the artifact. "The suite is green" is not
a substitute for reading the diff or running the verifier.

*Why it is here:* during this project's own construction, workers reported
mutation test results **twice** for a harness that did not exist in the
repository. The numbers were not produced by anything real. Fabricating a check's
output is worse than skipping it, because it defeats the check while looking like
compliance.

*Enforced by:* `crew round`/`crew turn` requiring recorded verdicts;
`orchestrate/SKILL.md`'s independent-verification step.

## 4. The reviewer is a separate process reading the shared artifact

Never a summary pasted into a prompt. The reviewer opens the files itself.

*Enforced by:* `orchestrate/SKILL.md` — "never paste the diff into the prompt."

## 5. The oracle problem

A loop without a mechanical failure signal produces plausible slop at scale, at
higher cost than doing nothing. Every domain pack must supply a **verify command
that exits non-zero on failure**, and every deliverable an **acceptance spec**
whose criteria are labelled `mechanical`, `sourced`, or `rubric`.

**The rubric-only rule:** a deliverable whose criteria are *all* rubric-class
does not get an unsupervised stretch. Either add a human checkpoint for it, or
cut it from scope at plan approval.

*Enforced by:* `bin/verify-research`, the pack loader's six required sections,
and `crew verify`.

## 6. The tester leaves the diff and touches reality

Code review reads; it does not run. For software the tester runs the program; for
research it re-opens the primary source and confirms the excerpt supports the
claim it is attached to.

*Enforced by:* the packs' `Roles` section and `orchestrate`'s tester pass.

## 7. Bounded loops, then escalate

Round cap 5. Turn cap 6. Two consecutive rounds with no meaningful change halts
the loop. There is no auto-resolution and no mid-loop model escalation.

*Enforced by:* `crew round end` **exiting non-zero at the cap**, and `crew send`
refusing to run once state is `escalated`. This is enforcement, not instruction —
during construction, caps were prose, and prose is transposable under load.

## 8. Fail loud, never improvise

A missing profile table, a pack missing a required section, an unknown adapter, a
malformed policy file — each stops the run and names the exact defect. Never fall
back silently.

Two distinctions this project learned the hard way:

- **Absent is not malformed.** A source that does not exist is skipped; a source
  that exists and fails to parse is a hard stop. Silently ignoring a broken
  override means running with settings the operator never chose.
- **"No match" is not "safe."** `crew classify-risk` returns
  `must_still_judge: true` on every response, because a keyword list can never be
  exhaustive. It can raise suspicion; it can never clear an action.

*Enforced by:* profile resolution in `lib/crew/core.py`, the pack loader, and
`crew classify-risk`.

## 9. Skill isolation

Where the adapter can enforce it, workers see the skills the repository ships and
nothing from the operator's machine. That is what makes the same repository
behave the same way for two different people — without it, none of the rest is
reproducible.

It is **not universal**, and the gap is declared rather than hidden. `pi` enforces
it via `bin/pi-project`. The `claude` adapter cannot — `claude --bare` skips hooks
and plugins but skills still resolve — so it reports `isolation: false`,
`factory doctor` prints the consequence, and `crew spawn` warns on every spawn.

*Enforced by:* `bin/pi-project`, and the capability declaration every adapter must
make. **An honest limitation beats a false claim.**

## 10. Tier the model to the goal

`S` for mechanical single-file work, `M` for ordinary multi-file work, `L` for
genuinely ambiguous scope — and `L` asks once before spending.

*A finding from construction:* the tier almost never mattered. Every real failure
in this project's own build traced to an **imprecise brief**, not to worker
capability. A stronger model does not fix an ambiguous instruction; it produces a
more convincing implementation of the wrong thing. The `L` gate is a cost
control, not a quality mechanism.

## 11. Exactly three human checkpoints

Plan approval. Risk gate. Final delivery. Nothing else interrupts the
unsupervised stretch — and none of the three can be skipped to save a step.

*Enforced by:* `autonomous-goal/SKILL.md`. The risk gate reads `POLICY.md`, which
ships with the repository — it used to defer to a file in the operator's home
directory, which meant every cloner had a gate that matched nothing.

## 12. Telemetry is the evidence

Whether this pattern earns its cost is an empirical question, so the loop records
spawns, reuses, rounds, verdicts, fallbacks, cap hits and outcomes, tagged by
domain and tier.

From this project's own construction (see `docs/COST.md`): software delegations
converged in a **median of 3 rounds** (n=13, range 1–6); the round cap was hit 5
times, and in every case the loop halted for a human decision — four ended
escalated, and the fifth continued only after explicit authorisation.

*Enforced by:* `bin/telemetry-record`, `bin/telemetry-report`. The log stays
local and is never published — it records verbatim user prompts.

---

## The authority boundary

**The crew produces artifacts. The orchestrator performs outward-facing
actions.**

No crew member holds a send button: no email, no chat, no ticket updates, no
publishing, no payments. A worker that needs one reports it and the orchestrator
escalates to the human. This is permanent and no domain pack may relax it.

## What this project does not claim

- That it removes the need to read the output. It removes the need to read
  *everything*, by making some failures mechanical.
- That more agents is better. Most work here runs one worker and one reviewer.
- That the loop is autonomous. It is bounded, and it stops.
