# OSS fork implementation plan — Phases 3 → 5

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:test-driven-development
> and superpowers:systematic-debugging. Steps use checkbox (`- [ ]`) syntax.

**Goal:** prove the backend abstraction with a second implementation, then cut
the public repository and make it usable by a stranger. Continues
`docs/superpowers/plans/2026-08-10-oss-fork.md`, whose Phases 0–2 are merged.

**Starting state (verified 2026-08-11):** `main` at `e0a333f`, suite **26/26**
from a clean checkout outside the repo. `delegate-to-pi` is an 11-line alias,
`orchestrate` is 126 lines of judgment, `bin/crew` has 15 verbs, adapters are
`herdr`/`pi`/`mock`.

---

## Verification standards — earned the hard way in Phases 2b–2e

These are not style preferences. Each one is a defect that shipped past a green
suite during Phase 2 and cost a review round or more. **They apply to every step
below.**

| Standard | The failure that produced it |
|---|---|
| **A stub must model the real protocol** — response nesting, empty-output verbs, render timing | The fake `herdr` returned `result.text` where real herdr returns `result.read.text`. 8/8 mutation-verified assertions validated a fiction and crashed on the first live call. |
| **A backend adapter is not done until it runs live** | Four defects — banner race, empty `send-keys`, non-atomic spawn, laundered render failure — were invisible to a passing stub suite. |
| **Probabilistic defects need repetition, not one pass** | A 1-in-3 spawn failure survived a round because the worker saw one success. Acceptance became 10 consecutive live runs. |
| **Test the entry point, not the function** | `core.run_verify_command()` was tested directly, so `bin/crew verify` could have been disconnected with every test green. |
| **Mutation pairs must come from a committed harness** | Pairs were reported twice with no harness in the repo. Fabricating a check's output defeats the check while looking like compliance. |
| **Audit sibling paths** | `profile_verified` needed four rounds to cover four call sites; atomicity covered `spawn` but not `fallback`. |
| **Verify from a clean checkout, outside the repo tree** | A fixture needing an untracked empty dir passed in place and failed everywhere else. A test passed inside `.worktrees/` and failed in `/tmp`. |
| **A migration inventory is a claim to be audited** | Nine of 54 claimed-migrated assertions were not actually covered, including one real behaviour regression. |

---

## Phase 3 — a second backend proves the abstraction

An abstraction with one implementation is a guess. This phase is what turns the
adapter contract from a hope into a fact.

### 3a. Contract additions the `batch` backend forces

`batch` inverts the flow: there is no long-running agent to poll, so a turn is
one subprocess invocation. That breaks two assumptions the contract currently
carries implicitly, and the orchestrator must learn about them through
capabilities rather than by knowing which backend it is on.

- [ ] Specify how `crew_send` / `crew_status` / `crew_read` collapse for a
      synchronous backend: `crew_send` runs the turn and buffers the result,
      `crew_status` reports settled, `crew_read` returns the buffered output.
      The loop above must not change.
- [ ] Specify `persistent_context: false`: when an adapter declares it, each
      turn starts with no memory, so the orchestrator **must** re-supply the
      plan, the ledger and the current artifact state in every prompt.
      `orchestrate/SKILL.md` gains a capability-driven branch for this — it is
      judgment (what to re-supply) driven by a mechanical signal (whether to).
- [ ] Specify the `QUESTION:` sentinel that maps a batch turn onto `blocked`,
      and the sentinel settlement path for `native_status: false`.

**Gate:** contract updated; no code yet.

### 3b. `batch` mux adapter + `claude` worker adapter

- [ ] `adapters/mux/batch` — one subprocess per turn, wall-clock timeout,
      `failed` on non-zero exit or a rate-limit signature, `blocked` on the
      `QUESTION:` sentinel. Declares `layout: false`, `focus: false`,
      `persistent_context: false`, `native_status: true` (process exit is
      authoritative), `banner: false`.
- [ ] `adapters/worker/claude` — `claude -p` argv, and the isolation question
      answered honestly: if it cannot be restricted to repo-local skills, it
      declares `isolation: false` and `crew spawn` warns.
- [ ] Because `banner: false`, profile verification must return the distinct
      **cannot-verify** result — never `verified`. This is already implemented;
      pin it for this adapter specifically.
- [ ] Stub fidelity: the `batch` test double must reproduce real one-shot CLI
      behaviour, including a non-zero exit, an empty stdout, and a slow turn.

**Gate:** one S-tier and one M-tier software goal complete end to end with
`herdr` and `pi` **absent from `PATH`**, plus **10 consecutive** successful
turns for any probabilistic surface. Live-run evidence, not stub evidence.

### 3c. Optional, only if 3b is clean

- [ ] `tmux` mux adapter with sentinel settlement — the honest test of
      `native_status: false`.

---

## Phase 4 — cut the public repository

> ### ⛔ THIS PHASE IS RISK-GATED AND CANNOT PROCEED ON STANDING AUTHORITY
>
> Creating a public repository is **publishing** — `POLICY.md` category 5,
> "Outward-facing actions". It is irreversible in the way that matters: once
> code is public it can be cloned, cached and indexed even if deleted minutes
> later.
>
> The orchestrator must **stop and obtain explicit, specific approval** naming
> the repository, its visibility, its licence, and the exact commit being
> published. Earlier blanket authorisation to "implement everything and merge to
> main" **does not** extend to publishing: every merge so far has been to a
> local repository with no remote.

### 4a. Scrub and audit — do this *before* asking for approval

- [ ] Confirm nothing in the publish set contains: `var/telemetry/events.jsonl`
      (it stores **verbatim user prompts**), `.projects/`, real profile tables,
      `.claude/settings.local.json`, `POLICY.local.md`, or any home-directory
      path.
- [ ] Audit the `docs/` set intended for publication. The design specs are the
      teaching material and most of why anyone would trust the project — they
      ship, but they mention internal project names and paths. Read every line.
- [ ] Licence: MIT, compatible with the vendored `superpowers` set. Keep
      `THIRD_PARTY_NOTICES.md`, pin the vendored version, document the sync
      procedure.
- [ ] Produce the exact publish manifest — every file, reviewed — and present it
      for approval alongside the repository name and visibility.

### 4b. Publish (only after approval)

- [ ] Create the repository and push the curated initial commit.
- [ ] Invert this repo into a downstream consumer: `upstream` remote, private
      overlay for profiles, `.projects/`, `var/`, `POLICY.local.md`.

**Gate:** a fresh clone on a clean machine passes CI and `factory doctor`.

---

## Phase 5 — usable by a stranger

- [ ] `bin/factory init | doctor | run`. `doctor` reports which adapters are
      present, which profiles resolve, and which capabilities degrade.
- [ ] `README.md` leading with the three claims no comparable project makes:
      the oracle problem, skill isolation, and telemetry as evidence.
- [ ] `MANIFESTO.md` — the twelve constraints, each pointed at the code that
      enforces it.
- [ ] **CI that clones fresh and runs the suite from outside the repo tree**,
      with the `mock` adapter, no agent installed. This is non-negotiable: the
      `.gitkeep` bug passed for me, for two workers and for a reviewer because
      we all ran the suite where the fixtures were authored.
- [ ] Two runnable `examples/`, one software and one research.
- [ ] `CONTRIBUTING.md`: adapters and packs are the contribution surface; the
      control loop is owned. Include the stub-fidelity requirement.
- [ ] A cost note from real telemetry — rounds-to-converge and cost per goal by
      domain and tier.
- [ ] `writing` and `ops` packs, each only after one real goal.

**Gate — v1.0:** a stranger with only `claude` on `PATH` goes from clone to a
completed example goal in under fifteen minutes, without reading the specs.

---

## Risks

| Risk | Mitigation |
|---|---|
| `batch` mode's stateless turns silently degrade quality, because re-supplied context is worse than an accumulated session | Make it measurable: run the same goal on both backends and compare rounds-to-converge from telemetry. Publish the difference rather than hiding it. |
| `claude -p` cannot be restricted to repo-local skills, breaking the reproducibility claim | Declare `isolation: false` and warn loudly. An honest limitation beats a false claim; note it in the README. |
| Publishing something that should not be public | Phase 4a is a full manifest review before approval is even requested. |
| The public repo attracts adapter PRs that pass stubs and fail live | The stub-fidelity requirement and a live-run checklist go in `CONTRIBUTING.md`. |
| Phase 5 scope creep | v1.0 is the fifteen-minute gate and nothing else. |

## Out of scope

- Any orchestrator other than Claude Code.
- Giving crew members outward-facing tools — permanently.
- A hosted control plane.
