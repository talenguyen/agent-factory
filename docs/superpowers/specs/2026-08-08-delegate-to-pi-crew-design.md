# delegate-to-pi: worker + reviewer pi crew for M/L-tier delegations

## Purpose

Extend the existing `delegate-to-pi` skill (see
`docs/superpowers/specs/2026-08-06-delegate-to-pi-design.md` and
`docs/superpowers/specs/2026-08-07-delegate-to-pi-profiles-design.md`) so
that, for goals classified `M` or `L` by the profile design's tier rubric,
review is done by a second `pi` agent running in its own herdr pane instead
of by Claude Code reading the diff itself. `S`-tier goals are unaffected —
they keep today's single-worker, Claude-reviews-itself flow unchanged.

This replaces today's single-worker flow as the *entry point* for M/L-tier
delegations (there is no separate skill to remember to invoke), but is not a
uniform default: whether a reviewer pane is spawned at all is decided by the
tier already computed in §1 of the profiles design, exactly as `S` vs `M`/`L`
already decides which model/provider profile to use.

## Background

`superpowers:subagent-driven-development` already implements the shape this
design borrows: dispatch an implementer, review its diff, loop fixes against
the reviewer's findings until clean, escalate to the human when a finding is
load-bearing and unresolved. That skill does it with in-process Claude
subagents (the `Agent` tool). This design ports the same *shape* — worker,
reviewer, fix loop, escalation — onto `pi` agents running in herdr panes,
because the worker in `delegate-to-pi` is already a `pi` process, not an
Agent-tool subagent, and the user wants to watch both roles work as visible
panes rather than have Claude Code silently review in-process.

Two things distinguish this from a direct port of `subagent-driven-development`,
both deliberate simplifications the user chose after discussing the
trade-offs:

1. **No severity tagging, no mid-loop model escalation, no formal
   adjudication.** `subagent-driven-development`'s Critical/Important/Minor
   tagging and round-4/5 model escalation add real engineering surface. This
   design uses a flat round cap instead — see "Round cap" below.
2. **Reviewer is a persistent, reused pi agent for the life of one
   delegation**, not a freshly dispatched subagent per round — mirroring how
   the worker itself is already reused when idle/done (profiles design §2).
   This lets the reviewer's own pi session accumulate context across rounds
   instead of needing the full history re-supplied each time.

## Architecture

### Tier gating (unchanged trigger, new branch)

The tier is classified exactly as in the profiles design (§1 there). What's
new is what tier drives:

- **`S`** → today's flow, verbatim: one worker, Claude Code reads the diff
  itself in what is currently §5, no reviewer pane, no ledger.
- **`M` / `L`** → crew mode, described below.

### Layout

Confirmed today's behavior: `herdr agent start ... --split right` places the
worker pane beside Claude Code's own pane (Claude Code's pane is the left
column; this is not new layout work). Crew mode adds the reviewer (and, when
triggered, the scout) to the *same* right-hand column by splitting down from
an existing pane in that column rather than right again:

```bash
# worker — unchanged from today
herdr agent start pi-isolated-worker-<TIER> --cwd "$(pwd)" --split right --no-focus -- \
  "$(git rev-parse --show-toplevel)/bin/pi-project" --provider <p> --model <m> --thinking <t> --session-id "$DELEGATION_ID"

# reviewer — new: stacks under the worker pane
herdr agent start pi-isolated-reviewer-<TIER> --cwd "$(pwd)" --split down --no-focus -- \
  "$(git rev-parse --show-toplevel)/bin/pi-project" --provider <p> --model <m> --thinking <t> --session-id "$DELEGATION_ID"

# scout — new: only spawned when triggered (see Roles below), stacks under whichever
# pane is targeted at spawn time
herdr agent start pi-isolated-scout-<TIER> --cwd "$(pwd)" --split down --no-focus -- \
  "$(git rev-parse --show-toplevel)/bin/pi-project" --provider <p> --model <m> --thinking <t> --session-id "$DELEGATION_ID"
```

Result: left column = Claude Code (planner); right column = worker on top,
reviewer below it, scout appearing below that only while active.

**Open technical risk, to verify live before this is trusted as fact (same
"confirmed live" discipline `references/herdr-cli.md` already holds
everywhere else):** `--split down` on `agent start` is only confirmed against
the *currently focused* pane in existing testing; it is not yet confirmed
whether it can target a specific existing `pane_id` (the worker's) rather
than whichever pane last had focus. `herdr pane split <pane_id> --direction
down` looks like the correct primitive if `agent start --split` turns out to
be focus-relative only. Resolving this is the first implementation step, not
an assumption baked into the skill text — see Testing plan.

### Roles

- **Worker** (`pi-isolated-worker-<TIER>`) — unchanged: spawn/reuse,
  profile verification, and rate-limit fallback are exactly the existing
  §2/§6 of the base + profiles design.
- **Reviewer** (`pi-isolated-reviewer-<TIER>`) — new. Spawned once per
  crew delegation, reused across rounds within that delegation via the same
  idle/done reuse check the worker already uses (`herdr agent list`,
  filtered on `cwd` and name prefix). Given the plan/goal text once at
  spawn; on each round it re-reads the current diff directly from the same
  worktree (it is a separate `pi` process with its own filesystem access —
  nothing is pasted through Claude Code). Must end every review with an
  explicit, machine-parseable verdict line:
  - `APPROVED`, or
  - `CHANGES REQUESTED:` followed by a plain-text list of findings.

  This exact-string convention is what lets the planner branch
  programmatically without re-interpreting free-form prose each round.
- **Scout** (`pi-isolated-scout-<TIER>`) — new, spawned on demand only,
  never persistent, strictly read-only (investigates and reports; never
  edits). Two trigger points:
  1. **Pre-work**: before the worker's first send, when the plan flags
     unknowns or edge cases worth checking first.
  2. **Mid-loop rescue**: when the round cap (below) is approaching and the
     same finding keeps recurring, or the worker hits something visibly
     outside the plan's scope — planner spawns scout to investigate and
     report back before deciding how to adjust the worker's next prompt or
     whether to escalate to the user.

  A scout pane is closed (`herdr pane close`) once it reports back — it
  does not linger stacked in the layout after its investigation is done.

### Per-round protocol (M/L only)

1. Planner sends the goal/plan to the worker, polls to settlement — today's
   existing send/poll logic, unchanged.
2. On worker settle (`idle`/`done` — `blocked` is still handled by the
   existing escalation-eligible flow, unchanged): planner asks the reviewer
   to review the current diff against the plan, and polls the reviewer to
   its own settlement the same way.
3. Read the reviewer's verdict line.
   - **`APPROVED`** → exit the loop, proceed to Final review below.
   - **`CHANGES REQUESTED: ...`** → append one line to the round ledger
     (see below), relay the reviewer's findings verbatim to the worker as
     its next prompt, and go back to step 1.
4. A `blocked` status from either worker or reviewer is handled exactly as
   today's escalation rule: the planner answers ordinary questions itself;
   any question touching the user's global Never/Off-limits rules (destructive
   git ops, secrets, production) stops and escalates to the user verbatim,
   unchanged from the base design.

### Ledger-lite

One file per delegation, at
`.factory/crew/<delegation-id>/progress.md` (gitignored scratch,
mirroring `subagent-driven-development`'s per-plan workspace convention —
nothing here is ever committed). One line appended per round:

```
Round 1: reviewer requested changes — <one-line summary>; worker replied.
Round 2: reviewer requested changes — <one-line summary>; worker replied.
Round 3: reviewer APPROVED.
```

Purpose: if this session is compacted mid-loop, re-reading this file plus
`git status`/`git diff` on the worktree is enough to recover exactly which
round the delegation is on and what has already been tried, without
re-querying the crew from scratch or risking a duplicate round.

### Round cap

**5 rounds**, matching `subagent-driven-development`'s existing round-cap
convention rather than inventing a new number (that skill's cap is on fix
rounds per task; this is the closest existing precedent in this repo). If
round 5 still ends `CHANGES REQUESTED`, or two consecutive rounds produce no
meaningful diff change, the planner stops looping — no auto-adjudication, no
model escalation. It shows the user the ledger and the reviewer's outstanding
comments and asks how to proceed. This mirrors the base design's existing
"no free looping" principle for its own turn cap, just applied to the
worker+reviewer round instead of a single worker turn.

### Final review

Once the reviewer approves, Claude Code (the planner) still performs one
final read of the whole diff before reporting the delegation done — this
folds today's base-design §5 verification into a single end-of-delegation
step (run once, not after every worker turn, since per-round verification is
now the reviewer's job during the loop).

## Error handling

- **Rate-limit/usage-failure fallback**: unchanged from the base design's
  §6 — applies independently to the worker and to the reviewer, since both
  are `pi` processes that can hit the same failure signature. Each gets its
  own `fallback_used` flag; a fallback exhausted on one role does not affect
  the other's fallback eligibility.
- **Escalation to the user**: unchanged trigger (a Never/Off-limits-eligible
  question from worker, reviewer, or scout). Everything else — ordinary
  clarifications, review disagreements below the round cap — the planner
  resolves itself.
- **Round cap hit**: see above — stop, show ledger + outstanding findings,
  ask the user; do not keep looping, do not auto-resolve.

## Out of scope

- Severity tagging (Critical/Important/Minor) of reviewer findings.
- Mid-loop model/profile escalation on later rounds (distinct from the
  existing rate-limit fallback, which is unaffected).
- Formal adjudication of parked/contested findings at the cap — the human
  decides directly instead.
- Any change to `S`-tier behavior — it keeps today's single-worker,
  Claude-reviews-itself flow verbatim.
- A scout role that edits code — it is read-only by design in this version.

## Testing plan

1. **Resolve the layout risk first**, live against the installed herdr
   0.7.3: spawn a throwaway worker + reviewer pair in a scratch cwd, confirm
   whether `agent start --split down` targets the worker's specific pane_id
   or only the currently focused pane, and confirm the resulting layout
   visually (zoom each pane) before writing the final spawn commands into
   `SKILL.md` as fact. Fall back to `herdr pane split <pane_id> --direction
   down` if `agent start --split` proves focus-relative only.
2. **Dry run on one real M-tier goal** end to end: confirm the ledger file
   is created and appended correctly each round, the reviewer's verdict line
   is parsed correctly in both branches (`APPROVED` and `CHANGES
   REQUESTED`), and the round cap fires and escalates correctly if forced
   (e.g. by giving the worker an intentionally incomplete goal).
3. **Confirm `S`-tier is unaffected**: run one S-tier goal through the same
   skill and confirm no reviewer pane is spawned and no ledger file is
   created — the branch must be tier-driven, not accidentally always-on.
4. Rate-limit fallback path itself is not easily triggerable on demand, same
   caveat as the profiles design — verified by code inspection unless a real
   rate-limit is encountered during testing.
