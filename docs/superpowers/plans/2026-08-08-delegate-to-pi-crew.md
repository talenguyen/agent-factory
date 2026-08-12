# delegate-to-pi Worker+Reviewer Crew Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the already-shipped `delegate-to-pi` skill so that `M`- and
`L`-tier delegations spawn a second `pi` agent as an independent reviewer
(stacked in its own herdr pane under the worker), loop worker↔reviewer fixes
until the reviewer approves, and can spawn a read-only scout on demand.
`S`-tier delegations are unaffected — they keep today's single-worker,
Claude-reviews-itself flow verbatim.

**Architecture:** `SKILL.md` gains a tier branch at the point where it
resolves agents and verifies work. `S` keeps every existing section
unchanged. `M`/`L` gain: a new §3 that resolves/spawns a reviewer pi agent,
stacked under the worker's pane using a focus→split-down→refocus sequence
(confirmed live against herdr 0.7.3 — plain `agent start --split down`
splits whichever pane is currently *focused*, not a chosen target, so the
worker's pane must be focused immediately before the reviewer spawn and
Claude Code's own pane refocused immediately after); a new §6a that asks the
reviewer for an `APPROVED`/`CHANGES REQUESTED:` verdict on each worker
settle and relays findings back to the worker; a ledger-lite progress file
per delegation for compaction survival; a round cap of 5 (worker+reviewer
pairs) that replaces the plain turn cap for crew mode; and an on-demand,
read-only scout role (§10) for pre-work recon or mid-loop rescue.
`references/herdr-cli.md` gains one new section documenting the confirmed
pane-targeting mechanic and a confirmed-bad alternative to avoid
(`pane split` + `pane run` produces an untrackable pane with no `name` or
`agent_status`).

**Tech Stack:** `herdr` 0.7.3 CLI, `pi` CLI via `bin/pi-project`, plain JSON
config, no test framework (this project has none — verification is via live
`herdr`/`pi`/`git` commands, matching how the base skill and its profiles
extension were both verified).

## Global Constraints

From `docs/superpowers/specs/2026-08-08-delegate-to-pi-crew-design.md`:

- Tier gating is the only entry-point switch: `S` never spawns a reviewer or
  scout and never touches the ledger — it is byte-for-byte today's flow.
  `M`/`L` always run crew mode. There is no separate skill to invoke.
- Reviewer name: `pi-isolated-reviewer-<TIER>`, reused across rounds within
  one delegation via the same idle/done reuse check §2 already uses for the
  worker (filter `agent list` on `cwd` + name prefix).
- Scout name: `pi-isolated-scout-<TIER>`, spawned only at its two trigger
  points (pre-work recon, mid-loop rescue), never persistent, strictly
  read-only, closed (`herdr pane close`) immediately after it reports back.
- Layout: the worker keeps spawning via today's `--split right` (this
  places it beside Claude Code's own pane, unchanged). The reviewer and any
  scout stack *under* an existing crew pane using: capture the current
  focused pane_id, `herdr agent focus <target-to-split>`, `herdr agent start
  ... --split down --no-focus -- ...`, then `herdr agent focus
  <captured-pane-id>` to restore focus. **Never** use `herdr pane split
  <pane_id> --direction down` followed by `herdr pane run` as a shortcut —
  confirmed live, a pane created that way has no `name` and no
  `agent_status` in `agent list`/`agent get`, silently breaking every reuse
  and poll step that follows.
- Reviewer verdict protocol: the reviewer's response must end with the
  literal line `APPROVED` or the literal line `CHANGES REQUESTED:` followed
  by plain text. The planner parses for these exact strings — no severity
  tags, no other verdict shapes.
- Ledger-lite: one file per delegation at
  `.factory/crew/<delegation-id>/progress.md` (`.superpowers/` is
  already gitignored — never commit it), one appended line per round. No
  severity tagging, no per-finding tracking beyond a one-line summary.
- Round cap: 5, crew mode only (one round = one worker turn + one reviewer
  verdict). This *replaces* the existing turn cap of 6 for `M`/`L` — it does
  not stack with it. `S`-tier keeps the existing turn-of-6 cap unchanged.
- Explicitly out of scope (do not build): severity tagging
  (Critical/Important/Minor) of reviewer findings, mid-loop model/profile
  escalation on later rounds, formal adjudication of parked findings at the
  cap, a scout that edits code.
- Existing base-skill invariants this work must not violate: always target
  herdr `pane` subcommands by `pane_id`, never a free-form name; treat
  `idle`, `done`, and `blocked` all as settled when polling; verify a pi
  agent's work independently via `git diff`/`git status`, never trust its
  self-report alone; escalate rather than auto-approve destructive/off-limits
  requests from any blocked crew member (worker, reviewer, or scout).

---

### Task 1: Document the confirmed pane-targeting mechanic in `herdr-cli.md`

**Files:**
- Modify: `.claude/skills/delegate-to-pi/references/herdr-cli.md`

**Interfaces:**
- Produces: a new section other tasks' `SKILL.md` text will point readers
  to for the exact focus→split-down→refocus command sequence, and the
  confirmed-bad `pane split`+`pane run` alternative to avoid. No code
  interface — this is documentation only.

- [ ] **Step 1: Insert the new section**

In `.claude/skills/delegate-to-pi/references/herdr-cli.md`, insert the
following new section immediately after the existing "Spawning with a
specific provider/model/thinking level" section and before the existing
"Check an agent's status" section:

````markdown
## Stacking a second pane under an existing one, not beside Claude Code's own pane

`herdr agent start <name> --split right|down` always splits whichever pane
is **currently focused** at the moment the command runs — it has no way to
target a specific existing pane_id. Confirmed live against herdr 0.7.3:
with Claude Code's own pane (`w1X:p1`) focused throughout, spawning one
agent with `--split right --no-focus` correctly placed it beside `w1X:p1`
(`w1X:p2`); spawning a second agent immediately after with `--split down
--no-focus`, focus still resting on `w1X:p1`, split `w1X:p1` itself — not
the just-spawned first agent's pane — producing a pane stacked under Claude
Code's own pane, not under the first agent.

**`--no-focus` only stops the newly created pane from stealing focus. It
does not restore whatever was focused before you last changed it.**
Confirmed live: after manually focusing an existing pane with `herdr agent
focus <target>` and then spawning with `--split down --no-focus`, focus
remained on the pane that had been manually focused (not the new pane, but
also not wherever focus had been before that manual step).

**To stack a new pane under a specific existing one** (e.g. a reviewer
under a worker, or a scout under whichever crew pane is currently at the
bottom of the column), focus that pane immediately before spawning, then
restore focus to wherever it should end up immediately after:

```bash
CURRENT_PANE="$(herdr pane current | python3 -c 'import json,sys;print(json.load(sys.stdin)["result"]["pane"]["pane_id"])')"
herdr agent focus <target-pane-to-split-under>
herdr agent start <new-name> --cwd <cwd> --split down --no-focus -- <argv...>
herdr agent focus "$CURRENT_PANE"
```

Confirmed live: this sequence produced the intended stacked layout (target
pane on top, new pane below it, both still full width of that column) and
left focus back on the original pane afterward, with no visible flicker in
the underlying layout beyond the brief focus change itself.

**Do not use `herdr pane split <pane_id> --direction down` plus `herdr pane
run <pane_id> <command>` as a shortcut for this**, even though `pane split`
does accept an explicit target `pane_id` (unlike `agent start --split`,
which is focus-relative only). Confirmed live: a pane created via `pane
split` — with or without a subsequent `pane run` into it — never appears in
`herdr agent list` or `herdr agent get` at all: no `name` field, no
`agent_status` field, nothing to poll or filter on. Only `agent start`
produces a pane that this skill's reuse/poll/status logic can see.
````

- [ ] **Step 2: Verify the doc renders and cross-references stay sane**

Run:

```bash
grep -n '^## ' .claude/skills/delegate-to-pi/references/herdr-cli.md
```

Expected: the new section title appears once, between "Spawning with a
specific provider/model/thinking level" and "Check an agent's status", and
no other section title was accidentally duplicated or removed.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/delegate-to-pi/references/herdr-cli.md
git commit -m "docs: confirm herdr pane-stacking mechanic for delegate-to-pi crew mode"
```

---

### Task 2: Rewrite `SKILL.md` with the tier-gated crew loop

**Files:**
- Modify: `.claude/skills/delegate-to-pi/SKILL.md` (full rewrite of body —
  frontmatter description updated, structure renumbered)

**Interfaces:**
- Consumes: `references/pi-profiles.json` (unchanged, read by tier letter
  exactly as today — the reviewer and scout use the same tier's profile as
  the worker, no separate table) and the new herdr-cli.md section from
  Task 1 (referenced by name, not duplicated inline).
- Produces: the renumbered section scheme every later task and any future
  edit relies on: §0 Precondition, §1 Choose a tier and profile, §2 Resolve
  the target pi agent (worker), §3 Resolve the reviewer agent (crew mode
  only), §4 Send the goal/poll, §5 Handle blocked, §6 Handle idle/done (with
  §6a Ask the reviewer, crew mode only), §7 Fallback on rate-limit/usage
  failure, §8 Round cap (crew mode only), §9 Turn cap (S-tier only), §10
  Scout (crew mode only), §11 Final review (crew mode only), §12 Report.

- [ ] **Step 1: Replace `SKILL.md` in full**

Replace the entire contents of `.claude/skills/delegate-to-pi/SKILL.md`
with:

`````markdown
---
name: delegate-to-pi
description: Delegate a coding goal to a `pi` agent running under herdr — spawn or reuse it, feed it prompts, observe its interactive session, verify its work against the actual diff, and iterate until the goal is met or escalation is needed. Automatically sizes the model/thinking profile to the goal, confirming once before using the most capable tier; for `M`/`L`-tier goals, also spawns a second `pi` agent as an independent reviewer, stacked in its own herdr pane, and loops fixes between worker and reviewer until the reviewer approves. Use when the user asks to delegate to pi, have pi build/fix/implement something, or invokes /delegate-to-pi <goal>.
user-invocable: true
---

# delegate-to-pi

You act as a supervisor — and, for `M`/`L`-tier goals, as the planner
orchestrating a small crew. You do not implement the goal yourself. You
drive one or more `pi` coding agents through herdr until the goal is met,
verifying the work yourself (directly for `S`-tier, via a reviewer pi agent
for `M`/`L`-tier) before reporting success.

Read `references/herdr-cli.md` before running any herdr command — it has
the exact validated command syntax and gotchas that will silently break
this procedure if skipped: send-without-submit, pane_id-vs-name targeting,
settle detection (an agent can settle as `idle`, `done`, or `blocked`
depending on its detection mode — never assume only one will occur), and how
to stack a second or third pane under an existing one rather than beside
Claude Code's own pane.

Read `references/pi-profiles.json` for the tier-to-model/provider/thinking
table used in §1 to pick which `pi` process to launch. The same table
serves every role — worker, reviewer, and scout all use the tier's one
profile; there is no separate table per role.

## 0. Precondition

Confirm you're running inside a herdr pane:

```bash
echo "HERDR_ENV=$HERDR_ENV"
herdr status
```

If `HERDR_ENV` isn't `1`, or `herdr status` doesn't show `server.status:
running`, stop and tell the user this skill only works inside a herdr-managed
session — do not attempt any workaround.

## 1. Choose a tier and profile

Before resolving or spawning any `pi` agent, classify the delegated goal
into a size tier and look up its model/provider/thinking profile. Do this
once per delegation — the tier is fixed for the whole delegation, not
re-chosen each turn.

Read `references/pi-profiles.json` first. If it's missing, fails to parse,
or is missing the `default_tier` field or any of the `S`/`M`/`L` entries
under `profiles`, stop and tell the user the profile table is broken and
show them the parse error or missing field — do not guess at
provider/model/thinking values or fall back to `pi`'s own defaults
silently.

Classify the goal using this rubric:

- **S** — single-file or mechanical change with a clear, low-risk spec
  (e.g. fix a typo, adjust a config value, a well-specified one-file bug fix).
- **M** — multi-file coordination or ordinary feature work; use
  `pi-profiles.json`'s `default_tier` field (read it — don't assume it's
  always `"M"`) for goals that don't clearly match S or L.
- **L** — architecture-level judgment calls, broad or ambiguous scope, or
  anything touching security/production-sensitive surfaces.

Set `TIER` to the classified letter, and look up that tier's `provider`,
`model`, and `thinking` values, plus its `fallback` entry (used later in
§7 if needed).

**`TIER` also decides whether this delegation runs in crew mode.** `S`
never does — skip §3 entirely, skip §6a and the ledger, skip §8 and §10 and
§11, and use §9's plain turn cap, exactly as this skill worked before this
crew extension existed. `M` and `L` always run in crew mode — use §3, loop
through §6a on every worker settle, use §8's round cap instead of §9's turn
cap, and spawn §10's scout if one of its two triggers fires.

**Gate on L:** if `TIER` is `L`, stop and ask the user to confirm before
proceeding — state the goal and why it needs the top tier. This is a
single up-front confirmation for the whole delegation, not a per-turn
check.

- If the user confirms, keep `TIER = L` and proceed.
- If the user declines, **reassign `TIER = default_tier`** (the value read
  from `pi-profiles.json`, ordinarily `M`) for the rest of this delegation
  — not just "use its profile for this send." Every later step that reads
  `TIER` (the §2/§3 spawn names, the §2/§3/§7 profile lookups, and the §12
  report) must see and use this reassigned value, exactly as if the goal had
  originally been classified at that tier. There is no separate
  "declined-L" state — after this reassignment, the rest of the procedure
  cannot tell the difference between a goal classified `M` from the start
  and one that started as `L` and was declined down to `M`. `TIER` remains
  `M`/`L`-tier (crew mode) after this reassignment — it is never reassigned
  to `S`.

Do not re-ask later in the same delegation — `TIER`, once settled here (by
classification, or by the user's answer to this gate), does not change
again.

Track state for the rest of this delegation: `TIER` (as settled above), and
one `fallback_used` flag per crew role that gets spawned —
`fallback_used_worker` always, and, crew mode only,
`fallback_used_reviewer` and `fallback_used_scout` — each starting `false`.
§7 sets a role's flag to `true` the first time its fallback fires for that
role, and checks it to decide whether a repeat failure for that same role
should retry again or escalate. The flags are independent per role — a
worker fallback being exhausted does not affect the reviewer's or scout's
own fallback eligibility.

Also generate `DELEGATION_ID` now, once — this identifies this delegation
for telemetry (and, in crew mode, doubles as the ledger directory name and
the `--session-id` passed to every crew member's `pi-project` invocation)
and is reused in every `telemetry-record`/`telemetry-lookup-pi-session` call
below; it does not change for the rest of this delegation.

```bash
DELEGATION_ID="$(uuidgen)"
```

## 2. Resolve the target pi agent (worker)

"Target cwd" means your own current working directory for the whole
delegation — it is not a variable to assign once and recall later. Each Bash
tool call in a real session is a fresh shell, so nothing you assign in one
call persists to another; every command below that needs the cwd (here and
in §6) computes it fresh with `"$(pwd)"`.

```bash
herdr agent list
```

The isolation-specific name prevents reuse of workers launched before this boundary existed.

Filter the returned `agents` for `agent == "pi"`, `cwd` equal to your cwd,
**and `name` starting with `pi-isolated-worker-<TIER>`** for the `TIER` chosen in
§1 (e.g. `pi-isolated-worker-M`). An idle or done agent under a *different* tier's
name is not a reuse candidate for this delegation — leave it as-is (it's
harmless, and may get reused by a future delegation at that same tier) and
spawn a fresh one below instead.

Note: this name-based filter only works for agents `herdr agent start`
actually launched with a name — an agent attached to a pane some other way
has no `name` field in `agent list`/`agent get` at all and will simply not
match any `pi-isolated-worker-*` filter, which is the desired behavior (never reuse
an agent you can't positively identify as this skill's own).

- If one is found with `agent_status` in `{idle, done}` → reuse it. Its
  `pane_id` is your `<target>` for every step below. Record the reuse for
  telemetry — look up the pi session id this agent was originally spawned
  with, then record the reuse against a fresh delegation id:

  ```bash
  PI_SESSION_ID="$("$(git rev-parse --show-toplevel)/bin/telemetry-lookup-pi-session" "pi-isolated-worker-<TIER>" "$(pwd)")"
  "$(git rev-parse --show-toplevel)/bin/telemetry-record" pi_reuse trace_id="$DELEGATION_ID" pi_session_id="${PI_SESSION_ID:-unknown}" tier="<TIER>" herdr_name="pi-isolated-worker-<TIER>" cwd="$(pwd)"
  ```

- If none is found, or the only matches are anything other than `idle`/`done`
  (i.e. `working`, `blocked`, or `unknown`) → spawn a new one, using the
  `provider`/`model`/`thinking` values looked up in §1 for `TIER`:

```bash
herdr agent start pi-isolated-worker-<TIER> --cwd "$(pwd)" --split right --no-focus -- "$(git rev-parse --show-toplevel)/bin/pi-project" --provider <provider> --model <model> --thinking <thinking> --session-id "$DELEGATION_ID"
```

  (Substitute the literal tier letter for `<TIER>` in the name, e.g.
  `pi-isolated-worker-M`, and the profile's actual values for `<provider>`,
  `<model>`, `<thinking>`. If `pi-isolated-worker-<TIER>` is already taken by another
  active agent, pick a variant name like `pi-isolated-worker-<TIER>-2`.) The
  response's `pane_id` field is your `<target>`. Poll (`herdr agent get
  <target>`, see §4) until its status is `idle` or `done` before sending
  anything — a freshly spawned `pi` needs a moment to start.

  If `agent start` fails for any other reason (no workspace, `pi` not on
  PATH in the spawned pane, socket error, etc.), show the user herdr's error
  output verbatim and stop — do not attempt a workaround.

  **Verify the profile actually took effect** before sending anything:
  herdr has no way to query a running agent's launch configuration after
  the fact (see `references/herdr-cli.md`'s "Agent names persist..."
  section), so a wrong or ignored flag would otherwise go undetected. Zoom
  the pane, read its status bar, and confirm the provider/model/thinking
  shown match what you requested, then un-zoom:

  ```bash
  herdr pane zoom <target> --on
  herdr pane read <target> --source visible --lines 10
  herdr pane zoom <target> --off
  ```

  If the displayed provider/model/thinking don't match what you requested,
  stop and show the user the mismatch verbatim — do not silently proceed
  with whatever actually launched.

  Once the profile is verified, record the spawn for telemetry — the
  delegation id doubles as the pi session id for a fresh spawn:

  ```bash
  "$(git rev-parse --show-toplevel)/bin/telemetry-record" pi_spawn trace_id="$DELEGATION_ID" pi_session_id="$DELEGATION_ID" tier="<TIER>" provider="<provider>" model="<model>" thinking="<thinking>" herdr_name="pi-isolated-worker-<TIER>" cwd="$(pwd)"
  ```

**Use `pane_id` as `<target>` everywhere below, never the free-form name.**
`herdr agent *` calls tolerate the name; `herdr pane *` calls (used for
`send-keys` in §4) reject it outright with `pane_not_found`. Resolving once
here and reusing that value avoids the mismatch entirely.

## 3. Resolve the reviewer agent (crew mode only)

**Skip this section entirely when `TIER` is `S`** — go straight to §4 using
only the worker resolved in §2, exactly as this skill worked before crew
mode existed.

For `TIER` `M` or `L`, resolve a reviewer the same way §2 resolved the
worker — reuse an idle/done one if a match exists, otherwise spawn a fresh
one:

```bash
herdr agent list
```

Filter for `agent == "pi"`, `cwd` equal to your cwd, and `name` starting
with `pi-isolated-reviewer-<TIER>`.

- If one is found with `agent_status` in `{idle, done}` → reuse it. Its
  `pane_id` is your `<reviewer_target>`. Record the reuse for telemetry,
  same pattern as §2:

  ```bash
  PI_SESSION_ID="$("$(git rev-parse --show-toplevel)/bin/telemetry-lookup-pi-session" "pi-isolated-reviewer-<TIER>" "$(pwd)")"
  "$(git rev-parse --show-toplevel)/bin/telemetry-record" pi_reuse trace_id="$DELEGATION_ID" pi_session_id="${PI_SESSION_ID:-unknown}" tier="<TIER>" herdr_name="pi-isolated-reviewer-<TIER>" cwd="$(pwd)"
  ```

- If none is found, spawn one. **Unlike the worker, the reviewer must land
  in the same right-hand column, stacked under the worker's pane, not beside
  Claude Code's own pane.** `agent start --split` always splits whichever
  pane is currently *focused*, not a chosen target (see
  `references/herdr-cli.md`'s "Stacking a second pane under an existing
  one" section — confirmed live against herdr 0.7.3). Achieving the
  intended layout requires focusing the worker's pane immediately before
  the reviewer spawn, then restoring focus to Claude Code's own pane
  immediately after — `--no-focus` on the spawn only stops the *new* pane
  from stealing focus; it does not restore whatever was focused before you
  last changed it:

  ```bash
  CURRENT_PANE="$(herdr pane current | python3 -c 'import json,sys;print(json.load(sys.stdin)["result"]["pane"]["pane_id"])')"
  herdr agent focus <worker_target>
  herdr agent start pi-isolated-reviewer-<TIER> --cwd "$(pwd)" --split down --no-focus -- "$(git rev-parse --show-toplevel)/bin/pi-project" --provider <provider> --model <model> --thinking <thinking> --session-id "$DELEGATION_ID"
  herdr agent focus "$CURRENT_PANE"
  ```

  (Same `provider`/`model`/`thinking` as the worker's own `TIER` profile —
  the reviewer uses the identical tier's values from `pi-profiles.json`,
  never a separate table.) The response's `pane_id` field is your
  `<reviewer_target>`. Poll it (`herdr agent get <reviewer_target>`) until
  `idle`/`done` before using it, same as §2.

  **Do not use `herdr pane split <pane_id> --direction down` plus `herdr
  pane run` as a shortcut for this** — confirmed live, a pane created that
  way never appears in `herdr agent list`/`agent get` at all (no `name`, no
  `agent_status`), which silently breaks every later reuse and polling step
  in this skill. Only `agent start` produces a trackable agent.

  Verify the reviewer's profile the same way §2 does for the worker (zoom
  the pane, read its status bar, confirm provider/model/thinking match,
  un-zoom; stop and show the user a mismatch verbatim rather than proceeding
  on it), then record the spawn for telemetry:

  ```bash
  "$(git rev-parse --show-toplevel)/bin/telemetry-record" pi_spawn trace_id="$DELEGATION_ID" pi_session_id="$DELEGATION_ID" tier="<TIER>" provider="<provider>" model="<model>" thinking="<thinking>" herdr_name="pi-isolated-reviewer-<TIER>" cwd="$(pwd)"
  ```

When a scout is spawned later (§10), stack it under whichever crew pane is
currently at the bottom of the right-hand column using this same focus →
split down → refocus sequence, targeting that pane instead of the worker's.

## 4. Send the goal, then poll to settlement

This section is used whenever any crew member (worker, reviewer, or scout)
needs a prompt sent and a response awaited — the `<target>` varies by which
role's turn it is.

For `TIER` `S`: before sending to the worker, increment your turn counter
(see §9) — every pass through this section for the worker counts as one
turn against that cap, regardless of how it eventually settles
(`blocked`-then-answered, goal met, or goal not met). The very first send
(the initial goal prompt) is turn 1.

For `TIER` `M`/`L`: sending to the worker as part of a round does not get
its own counter — the round (§8) is counted once per full worker+reviewer
pass, not per send. Sending to the reviewer (§6a) or to a scout (§10) never
counts against any cap.

Send using the two-step recipe (§ "Send a prompt" in the reference file):

```bash
herdr agent send <target> "<prompt text>"
herdr pane send-keys <target> enter
```

Then poll `herdr agent get <target>` on an interval (e.g. every 5s) until
`agent_status` is `idle`, `done`, or `blocked`, up to an overall timeout
(default 10 minutes per turn; use your judgment for larger goals). Treat all
three as settled — see the reference file for why: detection mode is
per-instance, and a hook-authority `pi` agent reports `idle` and never
`done`, while a screen-scraped one can do the reverse. Do not assume only one
of `idle`/`done` will ever occur.

If the timeout is reached with no settlement: read the pane
(`herdr agent read <target> --source visible --lines 200`), show the user
what the agent's screen currently looks like, and ask whether to keep
waiting or abort. Don't guess.

## 5. Handle `blocked`

This applies uniformly to whichever crew member (worker, reviewer, or
scout) reports `blocked`. Read the pane to see its exact question:

```bash
herdr agent read <target> --source visible --lines 200
```

**First, check for a rate-limit or usage-failure signature** (see §7 for
the exact phrases and what to do) before treating this as an ordinary
question. If the pane text matches, go to §7 instead of the steps below.

Otherwise, decide how to answer:

- **Default: answer it yourself** and continue the loop (go to §4 with your
  answer as the next prompt) — most blocks are ordinary clarifications or
  confirmations of reversible steps. For the worker under `TIER` `S`,
  going back to §4 begins a new turn (you already incremented the counter
  when you sent this cycle's prompt — see §9), so an agent that repeatedly
  blocks without making real progress still trips the cap instead of
  looping indefinitely for free.
- **Escalate to the user instead of auto-answering** when the question is
  asking you to approve something that falls under the user's global
  CLAUDE.md Never/Off-limits rules: destructive git or filesystem operations
  (including but not limited to force-push, `reset --hard`, `rm -rf`,
  deleting files/branches, discarding uncommitted changes), touching
  secrets/credentials/`.env.keys`, or production databases/infrastructure/live
  customer data. In that case, stop, show the user the agent's exact question
  verbatim, and wait for their answer before relaying anything back to it.

  Record the escalation before stopping:

  ```bash
  "$(git rev-parse --show-toplevel)/bin/telemetry-record" pi_escalated trace_id="$DELEGATION_ID" reason="user_confirmation_required"
  ```

  Do not resolve the blocking question yourself by implementing or approving
  the risky step in the agent's place — escalating means handing control to
  the user, not working around the block.

## 6. Handle `idle`/`done`: the worker settles

When the worker's status is `idle` or `done` (both mean it has settled —
see §4), read the full output:

```bash
herdr agent read <target> --source recent-unwrapped --lines 200
```

**First, check for a rate-limit or usage-failure signature** (see §7) in
that output before doing anything else. If it matches, go to §7 instead of
the steps below — do not interpret a rate-limited/quota-exhausted response
as "goal met" or "goal not met".

Otherwise, branch on `TIER`:

- **`TIER` is `S`:** independently check what actually happened — do not
  trust the worker's self-report on its own:

  ```bash
  git -C "$(pwd)" status --porcelain
  git -C "$(pwd)" diff
  ```

  Compare the diff and any test/build output the worker already reported
  against the original goal.

  - **Goal met** → go to §12 (report).
  - **Goal not met / partially met** → compose a specific follow-up prompt
    describing exactly what's missing or wrong (reference the actual diff,
    not a vague "try again") and go back to §4 (which begins a new counted
    turn — see §9).

- **`TIER` is `M` or `L`:** do not verify yourself — go to §6a to get the
  reviewer's verdict on the worker's current diff.

### 6a. Ask the reviewer (crew mode only)

Send the reviewer a prompt describing the goal/plan and asking it to review
the current diff, ending its response with exactly one of two verdict
lines. The reviewer reads the diff itself directly from the shared
worktree — it is a separate `pi` process with its own filesystem access, so
never paste the diff into the prompt:

```bash
herdr agent send <reviewer_target> "<goal/plan text> — review the current diff in this worktree against the above. End your response with exactly 'APPROVED' if it fully satisfies the goal, or exactly 'CHANGES REQUESTED:' followed by a plain list of what's wrong, if it doesn't."
herdr pane send-keys <reviewer_target> enter
```

Poll `<reviewer_target>` to settlement (§4). Read its output:

```bash
herdr agent read <reviewer_target> --source recent-unwrapped --lines 200
```

Check, in order:

1. **Rate-limit/usage-failure signature** (§7's phrases) → go to §7 instead
   of the steps below.
2. **Literal `APPROVED` present** → append a ledger line recording the
   approval (see "Ledger" below), record the round for telemetry:

   ```bash
   "$(git rev-parse --show-toplevel)/bin/telemetry-record" pi_crew_round trace_id="$DELEGATION_ID" round="$ROUND" verdict="approved"
   ```

   then go to §11 (final review) followed by §12 (report).
3. **Literal `CHANGES REQUESTED:` present** → append a ledger line (below),
   record the round for telemetry:

   ```bash
   "$(git rev-parse --show-toplevel)/bin/telemetry-record" pi_crew_round trace_id="$DELEGATION_ID" round="$ROUND" verdict="changes_requested"
   ```

   relay the text following the literal marker to the worker verbatim as
   its next prompt, increment `ROUND`, and go back to §4 for the worker —
   this counts as one round against §8's cap.
4. **Neither literal found** → the reviewer didn't follow the verdict
   format. Resend the same review request once more, explicitly reminding
   it of the required exact verdict line. If it still doesn't comply, show
   the user its raw output and ask how to proceed — do not guess which
   verdict was intended, and do not count this retry as a round.

**Ledger.** Each crew-mode delegation keeps a small progress file:
`.factory/crew/$DELEGATION_ID/progress.md` (gitignored scratch —
`.superpowers/` is already in `.gitignore`; never commit it). Create the
directory and file before the first round (`ROUND=1`), and append one line
after every reviewer verdict:

```bash
mkdir -p ".factory/crew/$DELEGATION_ID"
if [ "$VERDICT" = approved ]; then
  printf 'Round %d: reviewer APPROVED.\n' "$ROUND" >> ".factory/crew/$DELEGATION_ID/progress.md"
else
  printf 'Round %d: reviewer requested changes — %s; worker replied.\n' "$ROUND" "$SUMMARY" >> ".factory/crew/$DELEGATION_ID/progress.md"
fi
```

Purpose: if this session is compacted mid-loop, re-reading this file plus
`git status`/`git diff` on the worktree recovers exactly which round the
delegation is on and what's already been tried, without re-querying the
crew from scratch or risking a duplicate round.

## 7. Fallback on rate-limit or usage failure

This section is a subroutine referenced from §5 and §6/§6a — it only runs
when one of them detects a visible rate-limit or usage-failure signature in
an agent's output: phrases like "rate limit", "429", "quota exceeded",
"insufficient_quota", or "usage limit reached" (case-insensitive; check the
substring, not an exact phrase match). No other failure type (a bug in the
agent's own output, an ordinary blocked question, a poll timeout) reaches
this section — those stay in §4/§5/§6/§6a/§8/§9's existing handling.

This applies independently per role — the worker, reviewer, and scout each
have their own `fallback_used_<role>` flag (from §1); a fallback exhausted
for one role does not affect another role's fallback eligibility.

- **If the affected role's `fallback_used_<role>` is still `false`:**
  1. Set `fallback_used_<role> = true`.
  2. Close the current pane: `herdr pane close <target>`. If this itself
     fails (herdr returns an error rather than confirming the close),
     stop and show the user the error verbatim — do not assume the name
     is free and attempt the respawn below anyway.
  3. Look up `TIER`'s `fallback` entry in `references/pi-profiles.json`
     (`provider`, `model`, `thinking`) — the same entry regardless of role.
  4. Spawn a replacement, reusing the same name (the original is now
     closed, freeing it), using a fresh session id since this is a new
     `pi` process. For the **worker**, spawn exactly as in §2 (`--split
     right`):
     ```bash
     FALLBACK_SESSION_ID="$(uuidgen)"
     herdr agent start pi-isolated-worker-<TIER> --cwd "$(pwd)" --split right --no-focus -- "$(git rev-parse --show-toplevel)/bin/pi-project" --provider <fallback_provider> --model <fallback_model> --thinking <fallback_thinking> --session-id "$FALLBACK_SESSION_ID"
     ```
     For the **reviewer** or a **scout**, respawning creates a brand-new
     pane with no inherited position, so redo the full focus →
     split-down → refocus sequence from §3, targeting whichever pane it
     should stack under:
     ```bash
     FALLBACK_SESSION_ID="$(uuidgen)"
     CURRENT_PANE="$(herdr pane current | python3 -c 'import json,sys;print(json.load(sys.stdin)["result"]["pane"]["pane_id"])')"
     herdr agent focus <pane-to-stack-under>
     herdr agent start pi-isolated-<role>-<TIER> --cwd "$(pwd)" --split down --no-focus -- "$(git rev-parse --show-toplevel)/bin/pi-project" --provider <fallback_provider> --model <fallback_model> --thinking <fallback_thinking> --session-id "$FALLBACK_SESSION_ID"
     herdr agent focus "$CURRENT_PANE"
     ```
  5. Update `<target>` (or `<reviewer_target>`) to the new `pane_id` from
     the response.
  6. Verify the fallback profile actually took effect, same as §2's/§3's
     post-spawn check: zoom the pane, read its status bar, confirm the
     displayed provider/model/thinking match the fallback entry, un-zoom.
     Stop and show the user a mismatch verbatim rather than proceeding on
     it.
  7. Record the fallback for telemetry:
     ```bash
     "$(git rev-parse --show-toplevel)/bin/telemetry-record" pi_fallback trace_id="$DELEGATION_ID" pi_session_id="$FALLBACK_SESSION_ID" provider="<fallback_provider>" model="<fallback_model>" thinking="<fallback_thinking>" herdr_name="pi-isolated-<role>-<TIER>"
     ```
  8. Poll until settled (idle/done/blocked), same as §4.
  9. Resend the exact prompt that triggered this failure (go to §4 with
     that same prompt text — for the worker under `TIER` `S`, this does not
     skip the turn-counter increment described in §9; re-sending is itself
     a new turn. For crew mode, a fallback mid-round does not itself
     consume a round — only a completed worker-turn-then-reviewer-verdict
     pair does, per §8).
- **If the affected role's `fallback_used_<role>` is already `true`:** the
  fallback has already been tried once this delegation for this role and it
  also hit a rate-limit/usage-failure signature. Do not try a third variant
  — escalate to the user immediately: show both failures (the original
  profile's and the fallback profile's) verbatim, state the goal, tier, and
  role, record the escalation:

  ```bash
  "$(git rev-parse --show-toplevel)/bin/telemetry-record" pi_escalated trace_id="$DELEGATION_ID" reason="fallback_exhausted"
  ```

  and stop. Do not keep looping.

## 8. Round cap (crew mode only)

**Skip this section when `TIER` is `S`** — use §9's turn cap instead.

For `TIER` `M`/`L`, one round = one full pass through §4 (worker turn) plus
§6a (reviewer verdict), counted once the reviewer's verdict is read —
whether that verdict is `APPROVED` or `CHANGES REQUESTED:`. Default cap: 5
rounds, matching this repo's existing `subagent-driven-development`
fix-round convention rather than inventing a new number.

- If round 5 still ends `CHANGES REQUESTED:`, or two consecutive rounds
  produce no meaningful diff change, stop looping — no auto-resolution, no
  mid-loop model escalation. Record the round-cap hit, then escalate to the
  user:

  ```bash
  "$(git rev-parse --show-toplevel)/bin/telemetry-record" pi_crew_round_cap_hit trace_id="$DELEGATION_ID"
  ```

  Show the user the ledger (`.factory/crew/$DELEGATION_ID/progress.md`)
  and the reviewer's outstanding comments from the last round, state the
  original goal and tier, and ask how to proceed. Do not keep looping past
  this point, and do not implement or fix the remaining work yourself —
  escalating means stopping and handing control back to the user.

## 9. Turn cap (S-tier only)

**Skip this section when `TIER` is `M` or `L`** — use §8's round cap
instead.

Track turns: one turn = one pass through §4 (send + poll to settlement),
counted at the moment you send, before you know how it will settle. This
covers every cycle uniformly — whether it settles as `blocked`-then-answered
(§5), goal met, or goal not met (§6) — so repeated blocking questions count
against the cap exactly like unproductive work attempts do; nothing loops for
free. A resend after a fallback respawn (§7) is also a turn, not a free
retry. The initial goal prompt is turn 1. Default cap: 6 turns.

- If you hit the cap while the goal still isn't met, or two consecutive turns
  produced no meaningful diff/progress, stop iterating. Record the turn-cap
  hit, then escalate to the user:

  ```bash
  "$(git rev-parse --show-toplevel)/bin/telemetry-record" pi_turn_cap_hit trace_id="$DELEGATION_ID"
  ```

  State the original goal, what the worker actually did across turns, and
  why you judge it insufficient. Do not keep looping past this point, and
  do not implement or fix the remaining work yourself — escalating means
  stopping and handing control back to the user, not quietly finishing the
  job in the worker's place.

## 10. Scout (on demand, crew mode only)

The scout is read-only: it investigates and reports; it never edits
anything. It is never persistent — spawn it only at the two trigger points
below, and close its pane (`herdr pane close <scout_target>`) as soon as it
reports back.

**Trigger 1 — pre-work reconnaissance:** before the worker's first send
(§4) in a crew-mode delegation, if the plan/goal flags unknowns or edge
cases worth checking first, spawn a scout to investigate and report before
sending the worker anything.

**Trigger 2 — mid-loop rescue:** if the same reviewer finding keeps
recurring across rounds, or the worker's diff shows it drifting outside the
plan's scope, spawn a scout to investigate before composing the next
follow-up to the worker.

Spawn using the same focus → split down → refocus sequence as §3 (targeting
whichever crew pane currently sits at the bottom of the right-hand column),
naming it `pi-isolated-scout-<TIER>`, same profile as the worker/reviewer
for this `TIER`:

```bash
CURRENT_PANE="$(herdr pane current | python3 -c 'import json,sys;print(json.load(sys.stdin)["result"]["pane"]["pane_id"])')"
herdr agent focus <bottom-crew-pane>
herdr agent start pi-isolated-scout-<TIER> --cwd "$(pwd)" --split down --no-focus -- "$(git rev-parse --show-toplevel)/bin/pi-project" --provider <provider> --model <model> --thinking <thinking> --session-id "$DELEGATION_ID"
herdr agent focus "$CURRENT_PANE"
```

Give it a specific, scoped investigation question — never "fix this," since
it must not edit. Send it (§4), poll it to settlement, and when reading its
output, check for a rate-limit/usage-failure signature (§7) exactly as any
other crew member before treating its report as final. Then close its pane:

```bash
herdr pane close <scout_target>
```

Use its findings to decide the next worker prompt or whether to escalate to
the user — the scout's own output is never relayed to the worker verbatim
without you first deciding it's relevant.

## 11. Final review (crew mode only)

**Skip this section when `TIER` is `S`** — its equivalent (independent
verification against the diff) already happened inline in §6 for every
worker turn.

Once the reviewer's verdict is `APPROVED` (§6a), Claude Code still reads the
whole diff once itself before reporting done:

```bash
git -C "$(pwd)" status --porcelain
git -C "$(pwd)" diff
```

This is the same independent-verification step §6 performs for every turn
under `S`-tier, run here exactly once at the end of the loop instead of
after every worker turn, since per-round verification was the reviewer's
job during the loop.

## 12. Report

Before reporting, record the outcome for telemetry — `outcome` is
`goal_met`, `escalated`, or `stuck`, matching how this delegation actually
settled:

```bash
"$(git rev-parse --show-toplevel)/bin/telemetry-record" pi_delegation_end trace_id="$DELEGATION_ID" outcome="<goal_met|escalated|stuck>"
```

Whether the outcome is success, escalation, or a stuck state, tell the user:

- The original goal.
- The tier (`S`/`M`/`L`) and profile chosen in §1, and whether a fallback
  (§7) was used during this delegation, and for which role.
- The actual diff (or a summary of it if large) — never claim success
  without having looked at it.
- Any test/build results observed.
- For crew-mode delegations: how many rounds it took and the ledger path
  (`.factory/crew/$DELEGATION_ID/progress.md`).
- If escalated: exactly what you need from them to continue.
`````

- [ ] **Step 2: Verify internal `§N` cross-references are consistent**

Run:

```bash
grep -n '§[0-9]' .claude/skills/delegate-to-pi/SKILL.md
grep -n '^## [0-9]' .claude/skills/delegate-to-pi/SKILL.md
```

Manually confirm every `§N` mentioned in the first command's output refers
to a heading number that actually exists in the second command's output
(headings run `0` through `12`, plus `6a` as a subsection under `6`). Fix
any mismatch before continuing.

- [ ] **Step 3: Verify the JSON profile table is still read correctly (unchanged, but confirm no accidental edit)**

```bash
python3 -c "import json; json.load(open('.claude/skills/delegate-to-pi/references/pi-profiles.json')); print('OK')"
```

Expected: `OK`. This task does not modify `pi-profiles.json` — this step
just confirms it wasn't accidentally touched while editing the skill
directory.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/delegate-to-pi/SKILL.md
git commit -m "feat: add worker+reviewer pi crew mode to delegate-to-pi for M/L tiers"
```

---

### Task 3: End-to-end dry run

**Files:** none created or modified by this task itself — it exercises
Tasks 1–2's output and fixes forward if something's broken (see Step 6).

**Interfaces:**
- Consumes: `references/pi-profiles.json` (unchanged) and the renumbered
  `SKILL.md` from Task 2.

- [ ] **Step 1: Set up a scratch repo**

```bash
rm -rf /private/tmp/delegate-to-pi-crew-e2e
mkdir -p /private/tmp/delegate-to-pi-crew-e2e
cd /private/tmp/delegate-to-pi-crew-e2e
git init -q
printf 'line one\n' > notes.txt
git add notes.txt
git commit -q -m "initial scratch commit"
```

- [ ] **Step 2: Run a real S-tier delegation and confirm it is byte-for-byte unaffected**

Follow `SKILL.md` yourself, acting as the delegate-to-pi skill, for the
goal: *"Add a line 'line two' to the end of notes.txt."* in cwd
`/private/tmp/delegate-to-pi-crew-e2e`.

- §1: classify as `S`. Confirm the crew-mode note is followed: skip §3, §6a,
  §8, §10, §11 entirely.
- §2: spawn/reuse the worker, verify profile, send goal, poll to
  settlement.
- §6: `S`-tier branch — verify via `git diff` yourself, no reviewer
  involved.
- §9: turn cap applies (should not be hit for this trivial goal).
- §12: report.

Record: after this run, confirm via `herdr agent list` filtered to this cwd
that **no** `pi-isolated-reviewer-S` or `pi-isolated-scout-S` agent exists —
only the worker. Confirm no `.factory/crew/` directory was created
under `/private/tmp/delegate-to-pi-crew-e2e`. This is the check that crew
mode is genuinely tier-gated, not accidentally always-on.

- [ ] **Step 3: Run a real M-tier delegation exercising the full crew loop**

In the same scratch repo, run a goal designed to need at least one review
round, e.g.: *"Add a function `greet(name)` to a new file `greet.py` that
returns `f'Hello, {name}!'`, and add a docstring to it."* (deliberately
under-specified so a reviewer has something plausible to comment on, e.g.
missing a trailing newline convention or an example usage — do not coach
the reviewer to manufacture a finding; let it review honestly).

- §1: classify as `M`.
- §2: resolve/spawn the worker.
- §3: resolve/spawn the reviewer. **Confirm the layout**: run
  `herdr pane layout --current` and confirm the reviewer's pane is stacked
  under the worker's pane (same x-position/width, contiguous y-ranges), not
  beside Claude Code's own pane.
- §4/§6/§6a: send the goal to the worker, poll, then loop through the
  reviewer verdict cycle. Confirm the ledger file
  `.factory/crew/$DELEGATION_ID/progress.md` is created and gains
  one line per round, in the documented format.
- Continue until the reviewer's verdict is `APPROVED` (or until you judge
  it genuinely stuck — report as such rather than forcing an approval).
- §11: perform the final review read yourself.
- §12: report, including round count and ledger path.

Record: the exact `herdr pane layout` output confirming the stacked
position, the full ledger file contents, and the reviewer's final verdict
text.

- [ ] **Step 4: Force the round cap and confirm it escalates correctly**

In the same scratch repo, run a goal you deliberately keep incomplete no
matter what the worker sends back — e.g. *"Add a function `broken()` to
`greet.py` that must satisfy a made-up spec you will describe differently
each round, never actually satisfiable, so the reviewer never approves."*
Alternatively, simulate this more cheaply without burning 5 real rounds of
model calls: read §8 and confirm by inspection that (a) the round counter
increments only on a completed worker-turn+reviewer-verdict pair, (b) the
cap fires at exactly round 5 with a `CHANGES REQUESTED:` verdict still
open, (c) the telemetry call and escalation message are present and
correctly reference the ledger path. If you do run it live, record the
actual round count at which it stopped and confirm it matches 5.

- [ ] **Step 5: Structural review of the L-tier gate and fallback subroutine**

Same rationale as this skill's original profiles dry run: the `L` gate
(§1) and the fallback subroutine (§7) both require either a real human
decision or a real rate-limit failure to exercise end-to-end. Instead:

- Re-read §1's gate paragraph. Confirm it unambiguously says to stop and
  ask the user before proceeding with `L`, and that declining reassigns
  `TIER` to `default_tier` while keeping crew mode active (never dropping
  to `S`).
- Re-read §7. Confirm the per-role `fallback_used_<role>` flags are
  independent, and that the reviewer/scout fallback branch redoes the
  focus→split-down→refocus sequence rather than assuming the old pane's
  position carries over.

Record which sections you re-read and that both read as designed — this is
a structural review, not a passed/failed test.

- [ ] **Step 6: Clean up**

```bash
herdr agent list 2>&1 | python3 -c "
import json, sys
d = json.load(sys.stdin)
for a in d['result']['agents']:
    if a.get('cwd') == '/private/tmp/delegate-to-pi-crew-e2e':
        print(a['pane_id'], a.get('name'))
"
```

Close every `pane_id` printed above:

```bash
herdr pane close <pane_id>
```

Then remove the scratch repo:

```bash
rm -rf /private/tmp/delegate-to-pi-crew-e2e
```

- [ ] **Step 7: Fix forward if anything broke**

If any step above surfaced a real defect in `SKILL.md` or `herdr-cli.md`
(wrong flag, wrong section number, wrong reuse behavior, layout not
actually stacked as documented), fix it directly in this task, re-run the
specific step that failed to confirm the fix, then commit:

```bash
git add .claude/skills/delegate-to-pi
git commit -m "fix: correct issue found during delegate-to-pi crew dry run"
```

If nothing broke, skip this step — no empty commit.

- [ ] **Step 8: Write the report**

Include: the S-tier non-interference confirmation from Step 2, the layout
confirmation and ledger contents from Step 3, the round-cap behavior from
Step 4, and the structural-review notes from Step 5.

---

### Task 4: Skill quality review

**Files:** none created — this task dispatches a review and applies any
resulting fixes to the files from Tasks 1–3.

**Interfaces:** none new.

- [ ] **Step 1: Dispatch `plugin-dev:skill-reviewer`**

Dispatch the `plugin-dev:skill-reviewer` agent against
`.claude/skills/delegate-to-pi/` (all files: `SKILL.md`,
`references/herdr-cli.md`, `references/pi-profiles.json`), asking it to
review the whole skill directory as it now stands (not just this plan's
diff) for triggering-description quality, internal consistency (especially
the new tier-gated branching and renumbered cross-references), and
adherence to good skill-authoring practice.

If `plugin-dev:skill-reviewer` is not available in this environment, skip
this dispatch and instead perform the same review yourself by re-reading
the whole skill directory once with fresh eyes, focused specifically on:
does every `§N` cross-reference resolve, does the `S`-tier path ever
accidentally touch crew-mode-only state (ledger, reviewer, scout), and is
the triggering `description` in the frontmatter still accurate given the
new capability. Note in your report which path you took.

- [ ] **Step 2: Apply findings**

For each finding the reviewer reports: fix genuine defects directly in the
relevant file. For anything you judge a false positive or out of scope for
this plan, note why in your task report rather than silently dropping it.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/delegate-to-pi
git commit -m "polish: address skill-reviewer findings for delegate-to-pi crew mode"
```

If the reviewer found nothing worth changing, skip this step — no empty
commit, but still report that the review ran clean.
