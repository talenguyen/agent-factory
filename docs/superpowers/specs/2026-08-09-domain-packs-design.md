# Domain packs: generalizing the factory beyond software

## Purpose

Make the Claude-Code-orchestrates-a-`pi`-crew pattern reusable for
non-software goals, without regressing today's software behavior, and ship
the first non-software pack for **research / analysis** (literature reviews,
market and competitive analysis, due diligence).

The existing skills (`docs/superpowers/specs/2026-08-06-delegate-to-pi-design.md`,
`…-profiles-design.md`, `…-crew-design.md`) already implement a
domain-neutral control loop. This design extracts the four places that hard-code
software assumptions into a **domain pack**, selected by a `DOMAIN` variable
that defaults to `software`.

## Background

### What is already neutral

`bin/pi-project`, `lib/telemetry/`, and the whole of `delegate-to-pi`'s
control machinery — tier classification and profile lookup (§1), spawn/reuse
by name and cwd (§2/§3), send-and-poll-to-settlement (§4), `blocked` handling
and escalation (§5), rate-limit fallback per role (§7), round and turn caps
(§8/§9), the scout (§10), the ledger, the report (§12) — contain nothing
specific to code. So do `autonomous-build`'s three checkpoints.

### What is coupled

| # | Coupling | Location | Assumption |
|---|---|---|---|
| 1 | Verification is `git status` + `git diff` | `delegate-to-pi` §6, §11, §12 | The artifact is a code diff and reading it is sufficient |
| 2 | The tester "runs the real application" | `delegate-to-pi` §3b, §6b | The deliverable is executable |
| 3 | Isolation is a git worktree; done is merge/PR | `autonomous-build` §3, §7 | Delivery is a branch operation |
| 4 | Required sub-skills are TDD and code-review | `autonomous-build` §3, §6 | Correctness is test-shaped |

Only these four change. Everything else is inherited unchanged by every pack.

### Git is kept deliberately

Version control looks like a software artifact but is load-bearing for the
*crew*, not for the code: it is what lets the reviewer read the worker's
output directly from the shared worktree instead of trusting a self-report,
and what makes "two consecutive rounds produced no meaningful diff change"
(§8) a detectable condition. Research reports, source ledgers, models, and
datasets are all files. Packs keep git; they stop calling its contents code.

### The oracle problem

Unsupervised stretches are trustworthy in software because tests fail
mechanically, without a human. Most other domains have no such signal, and
the reviewer `pi` shares the worker's failure modes — a confident, well-formatted,
wrong analysis passes a prose review. Porting the loop without replacing the
oracle converts a build pipeline into a plausible-slop pipeline at higher cost.

This design's answer is the **acceptance spec** (below). It is the core of
the proposal, not an add-on; a pack without one is not approved for
unsupervised stretches.

## Architecture

### `DOMAIN` selection and pack loading

`delegate-to-pi` gains a `DOMAIN` variable, settled once per delegation
alongside `TIER` in §1 and never re-chosen. Resolution order:

1. `WORKSPACE.md` in the target cwd's repo root, if it declares `domain:`.
2. The invoking skill's explicit request (`autonomous-goal` passes it).
3. Default `software`.

The pack lives at `.claude/skills/delegate-to-pi/references/domains/<DOMAIN>.md`
and is read immediately after `pi-profiles.json`, under the same fail-loud
discipline already specified there: if the file is missing, or is missing any
of the six required sections below, **stop and show the user the exact missing
section** — never fall back to another pack, and never improvise the values.

`DOMAIN` is orthogonal to `TIER`. Tier still picks the model profile from the
single `pi-profiles.json` table; the pack never overrides a profile.

### Pack contract — six required sections

Each `<domain>.md` supplies exactly:

1. **Workspace layout** — what files constitute the deliverable and where.
2. **Verify command** — a fenced `bash` block replacing the bare `git diff`
   in §6/§11. Must be runnable and must exit non-zero on failure.
3. **Reviewer rubric** — what `APPROVED` means here; the `APPROVED` /
   `CHANGES REQUESTED:` verdict protocol itself is unchanged.
4. **Risk gate** — the irreversible or outward-facing acts *for this domain*,
   in addition to (never instead of) the user's global Never/Off-limits rules.
5. **Roles** — which of worker / reviewer / tester / scout apply, and what the
   tester analog is.
6. **Definition of done** — what replaces merge/PR at Checkpoint 3.

### The `software` pack

Encodes today's behavior verbatim: `git status --porcelain` + `git diff` as
verification, the §6b running-application tester, worktree isolation,
merge/PR delivery, TDD and code-review as required sub-skills. Extracting it
must be behavior-preserving — see Testing plan step 1.

### The `research` pack

**Workspace layout.** A git repo per investigation:

```
report.md          # the deliverable; every claim carries a citation key
sources.jsonl      # one record per source: key, url, retrieved_at, excerpt, sha256
snapshots/<key>.html   # local copy of each source as retrieved
acceptance.md      # the acceptance spec (below), written at plan time
```

**Verify command.** `bin/verify-research`, new, checks — all mechanically:

- every citation key in `report.md` resolves to a `sources.jsonl` record;
- every record has a URL, a retrieval timestamp, and a verbatim `excerpt`;
- every `excerpt` occurs literally in the corresponding `snapshots/<key>.html`;
- every snapshot's `sha256` matches its record;
- no orphaned records, no duplicate keys, no unreachable snapshot files;
- only an explicit line (optional whitespace and `-` bullet) beginning `Derived:` is a derived claim; its operands are `[@key:figure]`, each figure occurs in that key's snapshot, and its arithmetic re-computes;
- in every cited prose paragraph, each bare number must occur verbatim in a cited snapshot or be restated as an explicit `Derived:` line.

This is the pack's oracle. It cannot tell whether a conclusion is *wise*, but
it makes fabricated sources, drifted quotes, and invented numbers fail loudly
and without a human — which is exactly the property that makes §8's rounds
worth running unsupervised.

**Reviewer rubric.** `APPROVED` requires: every acceptance criterion in
`acceptance.md` met; the verify command green; each conclusion traceable to
cited evidence rather than to the worker's prior; disconfirming evidence
addressed rather than omitted; stated confidence proportionate to source
quality and independence (three outlets reprinting one press release is one
source, not three).

**Risk gate** (added to the global list). Publishing or sending any artifact
outside the workspace; contacting a human source; paying for data or an API;
retrieving anything behind authentication, a paywall, or a ToS prohibition;
storing personal data about identifiable individuals.

**Roles.** Worker = researcher. Reviewer = critic against the rubric. Scout =
unchanged (scoping recon before the first send). Tester analog = **fact-checker**:
independently re-retrieves a random sample of cited sources (minimum 5, or 20%,
whichever is greater) and confirms each excerpt genuinely supports the claim it
is attached to. Verdicts `NO BUGS FOUND` / `BUGS FOUND:` become
`SOURCES VERIFIED` / `SOURCE PROBLEMS:`; §6b's control flow is otherwise
unchanged, including full re-execution after any fix.

This mapping is the general principle for every future pack: the tester role
exists to *leave the diff and touch reality*. In software that is running the
program; in research it is re-opening the primary source.

**Definition of done.** Verify command green, acceptance spec fully met,
fact-checker verdict `SOURCES VERIFIED`, and the human's Checkpoint 3
approval — the report is not sent, published, or filed by the crew.

### The acceptance spec

`autonomous-goal` Step 1 gains a required output, written by Claude Code (never
delegated — same planner/implementer split that already forbids delegating the
§6b test plan). One criterion per deliverable, each labeled with its check class:

- **mechanical** — a command exits 0 (verify script, schema validation, link
  resolution, recomputation).
- **sourced** — the claim carries a citation a reviewer can independently open
  and confirm.
- **rubric** — a reviewer scores it against written criteria.

**The rubric-only rule:** a deliverable whose criteria are *all* rubric-class
does not get an unsupervised stretch. Claude Code must either add a human
checkpoint for that deliverable specifically, or drop it from scope at
Checkpoint 1. This is stated at plan approval so the user is choosing it
knowingly, and it is what stops the pattern degrading into confident output
nobody checked.

### Authority boundary

**The `pi` crew produces artifacts. Claude Code performs outward-facing actions.**

The crew never holds a send button: no email, no Slack, no ticket updates, no
publishing, no payments — those tools live on Claude Code, which is the process
standing at Checkpoint 3 with the user's delegated authority. A crew member that
needs an outward action reports it as a `blocked` question and it is escalated
under §5, never performed by the worker.

This is already the de-facto topology (`bin/pi-project` gives `pi` no such
tools); this design makes it an explicit invariant every pack inherits and no
pack may relax.

### `autonomous-build` → `autonomous-goal`

The three checkpoints survive verbatim. Two generalizations:

- Checkpoint 3 becomes **final delivery**: merge/PR *or* send/publish/submit/file
  — in non-software domains the irreversible outward act is exactly where the
  human belongs, so this is a widening of the gate, not a loosening.
- Step 3's required sub-skills come from the pack, not the skill body.

`autonomous-build` remains as a thin alias pinning `DOMAIN=software`, so
existing muscle memory and `CLAUDE.md` keep working.

### Telemetry

Add `domain=` to `pi_spawn`, `pi_reuse`, `pi_crew_round`, and
`pi_delegation_end`. This makes "which domains actually converge, and in how
many rounds" answerable from `var/telemetry/events.jsonl` — the evidence for
whether a pack earns its keep. Events without the field read as `software`.

## Error handling

- **Missing or malformed pack** — stop, name the missing section, no fallback.
- **Verify command fails** — treated exactly as a failing test today: it is
  worker-fixable within the round budget, never a reason to escalate early.
- **Verify command absent from a pack** — the pack is invalid; §6/§11 must
  never silently degrade to "Claude Code reads it and forms an opinion."
- **Rubric-only deliverable reaching Step 3** — Claude Code stops and returns
  to Checkpoint 1 rather than starting an unsupervised stretch it cannot verify.
- **Round cap, fallback, escalation** — unchanged from the crew design.

## Out of scope

- Any change to tiering, profiles, caps, fallback, ledger, or scout behavior.
- Any change to `S`-tier flow beyond reading its verification command from the pack.
- Packs beyond `software` and `research` (document production, data/modeling,
  and ops/comms are deferred until `research` has been proven on a real goal).
- Giving `pi` crew members any outward-facing tool — explicitly and permanently
  out of scope.
- A cross-domain shared workspace; one workspace declares one domain.

## Testing plan

1. **Behavior preservation first.** **Covered by `tests/test-domain-pack-loader.sh` and the full suite.** Extract the `software` pack and run the
   existing suite (`tests/test-delegate-to-pi-*.sh`, `tests/test-pi-project*`,
   the telemetry tests) unchanged. Then run one real `S`-tier and one real
   `M`-tier software goal end to end and confirm the panes, ledger, rounds, and
   report are indistinguishable from today's. No `research` work begins until
   this is green.
2. **Pack loader failure modes.** **Covered by `tests/test-domain-pack-loader.sh`.** Missing pack file, pack missing each of the
   six sections in turn, pack with a verify command that is not runnable —
   each must stop with the exact missing element named, and none may fall back.
3. **`bin/verify-research` against known-bad inputs.** **Covered by `tests/test-verify-research.py`.** Build fixtures that each
   trip exactly one check: a citation key with no record, a record whose excerpt
   is absent from its snapshot, a mutated snapshot with a stale `sha256`, a
   derived number whose arithmetic does not re-compute. Each must exit non-zero
   and name the offending key. This is the pack's oracle; it is tested before it
   is trusted.
4. **One real research goal end to end**, deliberately chosen to include a claim
   with weak sourcing, and confirm: the reviewer catches it, the fact-checker's
   sample re-retrieval runs against real URLs, `BUGS FOUND`-equivalent findings
   loop back to the worker within the shared round budget, and no crew member
   attempts an outward-facing action.
5. **Rubric-only rule fires.** **Covered by `tests/test-autonomous-goal.sh`.** Give `autonomous-goal` a goal whose deliverable
   admits no mechanical or sourced criterion, and confirm it stops at
   Checkpoint 1 with the scope choice put to the user rather than proceeding.
