# Domain Packs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development and superpowers:systematic-debugging while implementing. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement
`docs/superpowers/specs/2026-08-09-domain-packs-design.md` in full —
`DOMAIN` selection and pack loading, a `software` pack that preserves
today's behavior exactly, a `research` pack, `bin/verify-research`,
acceptance-spec enforcement, the `autonomous-build` → `autonomous-goal`
rename, and the telemetry `domain` field.

**Architecture:** `delegate-to-pi/SKILL.md` gains a `DOMAIN` variable
settled once in §1 alongside `TIER`, and replaces four hard-coded
software assumptions (§6/§11 `git diff` verification, §3b/§6b's
"run the real application" tester, §3's worktree isolation, §6's required
sub-skills) with lookups into
`references/domains/<DOMAIN>.md`. `autonomous-build` is renamed
`autonomous-goal` with a thin `autonomous-build` alias retained so
`CLAUDE.md` and existing muscle memory keep working. `bin/verify-research`
is a new standalone CLI — the `research` pack's mechanical oracle.

**Tech Stack:** Bash + Python 3 (matching `bin/` and `lib/telemetry/`),
`rg` for the existing grep-assertion test style, `jq` (already a
`telemetry-record` dependency), no new runtime dependencies.

## Global Constraints

From the design spec:

- `DOMAIN` is orthogonal to `TIER`. A pack **never** overrides a
  model/provider/thinking profile — `pi-profiles.json` remains the single
  source for those.
- Pack loading is **fail-loud**, matching `pi-profiles.json`'s existing
  discipline: a missing pack file, or a pack missing any of the six
  required sections, stops the delegation and names the exact missing
  element. Never fall back to another pack. Never improvise values.
- The `software` pack must be **behavior-preserving**. Phase 1 is not done
  until the entire existing test suite passes unchanged and one real
  `S`-tier and one real `M`-tier delegation are indistinguishable from
  today's.
- **Authority boundary is absolute:** no pack may grant a `pi` crew member
  any outward-facing tool (email, Slack, tickets, publishing, payments).
  A crew member needing such an action reports it as `blocked` and it
  escalates under §5.
- Crew role names (`pi-isolated-<role>-<TIER>`) are **unchanged** — renaming
  them would break agent reuse and `tests/test-delegate-to-pi-isolation.sh`.
- `.superpowers/` and `var/telemetry/` stay gitignored; nothing there is
  ever committed.

## Decisions taken (not open questions)

1. **Snapshot capture / JS rendering.** `snapshots/<key>.html` stores the
   **raw HTTP response body** verbatim — no headless browser, no new
   dependency. A source whose content requires JS rendering is recorded
   with `"render_required": true` in `sources.jsonl`; `bin/verify-research`
   then **skips only the excerpt-occurrence check** for that record (still
   enforcing url, timestamp, excerpt presence, and sha256), and the record
   is **force-included** in the fact-checker's sample rather than left to
   chance. This keeps the oracle mechanical for the common case and routes
   the hard case to a human-shaped check instead of silently passing it.
2. **`WORKSPACE.md`.** Implemented as a domain declaration the loader reads
   (`domain: <name>` line). The `.projects/` → workspaces rename is
   explicitly **not** done — out of scope in the spec and unnecessary for
   the loader.
3. **`autonomous-build` retained as an alias** that pins `DOMAIN=software`
   and delegates to `autonomous-goal`, so `CLAUDE.md`'s existing instruction
   keeps working without a same-night edit to muscle memory.
4. **Test style.** New skill-text assertions follow the existing
   `rg`-based pattern in `tests/test-delegate-to-pi-*.sh`.
   `bin/verify-research` gets real fixture-driven tests (not grep
   assertions) because it is executable code with an actual contract.

## Phase 0 — Isolation

- [ ] Create branch `feat/domain-packs` and a linked worktree under
      `.worktrees/domain-packs` (`.worktrees/` is gitignored).
- [ ] Commit the untracked spec
      (`docs/superpowers/specs/2026-08-09-domain-packs-design.md`) on the
      branch as its first commit, so the branch carries its own rationale.
- [ ] Confirm `main` is left untouched.

## Phase 1 — Pack loader + `software` pack + telemetry (behavior-preserving)

- [x] Create `.claude/skills/delegate-to-pi/references/domains/software.md`
      with the six required sections, encoding today's behavior verbatim:
      `git status --porcelain` + `git diff` verification; the §6b
      running-application tester with `NO BUGS FOUND` / `BUGS FOUND:`;
      worktree isolation; merge/PR delivery; TDD + code-review sub-skills;
      the existing global risk-gate list.
- [x] Add §0b "Resolve `DOMAIN`" to `delegate-to-pi/SKILL.md`: resolution
      order `WORKSPACE.md` → caller-supplied → default `software`; settled
      once per delegation; fail-loud validation of the six sections.
- [x] Replace the hard-coded `git status`/`git diff` blocks in §6 and §11
      with the pack's **Verify command**, and the §3b/§6b tester wording
      with the pack's **Roles** tester analog and its verdict pair.
- [x] Add `domain="$DOMAIN"` to the `pi_spawn`, `pi_reuse`,
      `pi_crew_round`, and `pi_delegation_end` `telemetry-record` calls.
      (`bin/telemetry-record` takes arbitrary `key=value` — no change
      needed to the recorder itself.)
- [x] Teach `lib/telemetry/aggregate.py` to carry `domain` through, and
      `text_report.py`/`dashboard.py` to break rounds and outcomes down by
      it. Events without the field read as `software`.
- [x] Add `tests/test-domain-pack-loader.sh`: asserts the skill text
      documents the resolution order, the six required sections, and the
      fail-loud rule; asserts `software.md` exists and has all six.
- [x] Extend `tests/test-delegate-to-pi-telemetry.sh` to require
      `domain=` on the four events above.
- [x] **Gate:** run the full existing suite (all of `tests/`) and confirm
      green before any Phase 2 work begins.

## Phase 2 — `research` pack + `bin/verify-research`

- [x] Write `bin/verify-research` (Python 3, executable, `--workspace <dir>`,
      exit 0 clean / non-zero with the offending citation key named).
      Checks, per the spec: citation keys resolve; records carry url +
      `retrieved_at` + verbatim `excerpt`; excerpt occurs literally in
      `snapshots/<key>.html` (skipped for `render_required`); sha256
      matches; no orphaned records, duplicate keys, or missing snapshots;
      derived numeric claims re-compute from cited figures.
- [x] Build known-bad fixtures under `tests/fixtures/research/`, one per
      failure mode: unresolved citation key; excerpt absent from snapshot;
      mutated snapshot with stale sha256; derived number that does not
      re-compute; duplicate key; orphaned record.
- [x] Add `tests/test-verify-research.py`: one clean fixture exits 0; each
      known-bad fixture exits non-zero **and names the offending key**.
      Write these tests before the implementation (TDD).
- [x] Create `references/domains/research.md` with all six sections:
      workspace layout (`report.md`, `sources.jsonl`, `snapshots/`,
      `acceptance.md`); verify command (`bin/verify-research`); reviewer
      rubric (acceptance criteria met, verify green, conclusions traceable,
      disconfirming evidence addressed, confidence proportionate to source
      independence); risk gate (publishing/sending, contacting a human
      source, paid data/APIs, auth/paywall/ToS-restricted retrieval,
      personal data); roles (worker=researcher, reviewer=critic,
      scout unchanged, tester analog = **fact-checker** re-retrieving
      max(5, 20%) of sources with `SOURCES VERIFIED` /
      `SOURCE PROBLEMS:` verdicts, plus all `render_required` records);
      definition of done.
- [x] **Gate:** full suite green.

## Phase 3 — `autonomous-goal` + acceptance-spec enforcement

- [x] Create `.claude/skills/autonomous-goal/SKILL.md` from
      `autonomous-build`: three checkpoints verbatim; Checkpoint 3
      generalized to **final delivery** (merge/PR *or*
      send/publish/submit/file); Step 3's required sub-skills read from the
      pack instead of being hard-coded.
- [x] Add the **acceptance spec** as a required Step 1 output: written by
      Claude Code, never delegated; one criterion per deliverable labeled
      `mechanical` / `sourced` / `rubric`.
- [x] Implement the **rubric-only rule**: a deliverable whose criteria are
      all rubric-class stops at Checkpoint 1 with the choice (add a human
      checkpoint, or cut scope) put to the user.
- [x] Reduce `autonomous-build/SKILL.md` to a thin alias pinning
      `DOMAIN=software` and pointing at `autonomous-goal`.
- [x] Add `tests/test-autonomous-goal.sh`: asserts the three checkpoints
      survive, Checkpoint 3 covers the non-merge delivery verbs, the
      acceptance spec is required, the rubric-only rule is present, and the
      `autonomous-build` alias still resolves.
- [x] **Gate:** full suite green.

## Phase 4 — Docs

- [x] Update `README.md`: a "Domains" section describing pack selection,
      the two shipped packs, and the authority boundary.
- [x] Update `CLAUDE.md`: point "Working here" at `/autonomous-goal`, noting
      `/autonomous-build` still works as the software-pinned alias.
- [x] Mark the spec's own Testing plan steps 1–3 and 5 as covered by the
      test files above; leave step 4 (a real end-to-end research goal) for
      the human, since it requires live network retrieval and a real topic.

## Risks

- **Highest: `software` pack extraction silently changes behavior.**
  `tests/test-delegate-to-pi-isolation.sh` and `-telemetry.sh` assert on
  literal strings inside `SKILL.md`; moving text into a pack can make them
  pass while the *skill* has actually drifted. Mitigation: Phase 1's gate
  requires a real `S`-tier and a real `M`-tier delegation, not just green
  greps.
- **Derived-number re-computation is the weakest check** in
  `verify-research` — it depends on the worker annotating arithmetic
  honestly. It catches drift and typos, not deliberate fabrication. Do not
  oversell it in the pack's prose.
- **Phase 3 rewrites two skill files committed today** (`d697784`). Keep
  those edits reviewable as their own commits, separate from Phase 1/2.
- **Round budget:** this is a large goal for one delegation. If the round
  cap is hit, escalate per §8 rather than expanding scope — do not attempt
  Phase 3 if Phase 1's gate is not green.

## Out of scope

- The `.projects/` → workspaces rename.
- Packs beyond `software` and `research`.
- Any push, PR, merge, or branch deletion (Checkpoint 3 — the human's call).
- Any outward-facing tool for `pi` crew members.
