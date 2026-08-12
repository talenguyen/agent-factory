# delegate-to-pi Model/Provider/Thinking Profiles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the already-shipped `delegate-to-pi` skill choose a `pi`
model/provider/thinking-level profile based on the delegated task's size
(S/M/L), instead of always launching `pi` with its own defaults.

**Architecture:** A new `references/pi-profiles.json` holds the tier table
(one row per tier: `provider`, `model`, `thinking`, `fallback`). `SKILL.md`
gains a new step (§1) that classifies the goal into a tier, gates the top
tier behind a human confirmation, and looks up the profile; the existing
target-resolution and spawn steps are updated to encode the tier into the
spawn name (`pi-worker-<TIER>`) and pass the profile as `--provider
--model --thinking` flags; a new subroutine section (§6) handles the one
scoped fallback retry on a visible rate-limit/usage failure. All other
sections shift down by section number but are otherwise behaviorally
unchanged.

**Tech Stack:** `herdr` 0.7.3 CLI, `pi` CLI (installed at
`~/.local/bin/pi`), plain JSON config, no test framework (this project has
none — verification is via live `herdr`/`pi`/`git` commands, matching how
the base skill was verified).

## Global Constraints

From `docs/superpowers/specs/2026-08-07-delegate-to-pi-profiles-design.md`:

- Profile table lives at
  `.claude/skills/delegate-to-pi/references/pi-profiles.json`, exactly
  three tiers: `S`, `M`, `L`. Each tier has exactly one `fallback` entry
  (not a list) — the fallback rule only ever retries once.
- Confirmed live on this machine (`pi --list-models`): `openai-codex`
  serves `gpt-5.6-luna`, `gpt-5.6-terra`, `gpt-5.6-sol`; `opencode-go`
  serves `deepseek-v4-flash` and `deepseek-v4-pro`. Use exactly these
  provider/model pairs — do not substitute different model names without
  re-validating against `pi --list-models` on the machine running this.
- Spawn name convention: `pi-worker-<TIER>` (literal tier letter, e.g.
  `pi-worker-M`), replacing the base skill's generic `pi-worker`. Reuse in
  target resolution must filter on this name pattern in addition to `cwd`
  and status — never reuse an agent spawned under a different tier's name.
- Choosing the `L` tier requires one explicit human confirmation before
  dispatch, once per delegation (not per turn). Declining falls back to the
  `M` profile for that delegation.
- The fallback subroutine triggers **only** on a visible rate-limit/usage
  failure signature (substring match, case-insensitive: "rate limit",
  "429", "quota exceeded", "insufficient_quota", "usage limit reached") —
  never on any other failure type. It retries exactly once with the tier's
  configured `fallback` entry, then escalates to the human if that also
  fails.
- No automatic mid-delegation tier escalation — the tier is fixed once
  chosen for a delegation.

Existing base-skill invariants from
`docs/superpowers/specs/2026-08-06-delegate-to-pi-design.md` that this work
must not violate while editing `SKILL.md`: always target herdr `pane`
subcommands by `pane_id`, never a free-form name; treat `idle`, `done`,
**and** `blocked` all as settled when polling (detection mode is
per-instance); verify pi's work independently via `git diff`/`git status`,
never trust its self-report alone; default turn cap is 6, incremented
uniformly at the top of the send step regardless of how a turn settles;
escalate rather than auto-approve destructive/off-limits requests from a
blocked `pi`.

---

### Task 1: Create and validate the profile table

**Files:**
- Create: `.claude/skills/delegate-to-pi/references/pi-profiles.json`

**Interfaces:**
- Produces: a JSON file with top-level keys `default_tier` (string, one of
  `S`/`M`/`L`) and `profiles` (object keyed by tier letter, each value an
  object with string fields `provider`, `model`, `thinking`, and object
  field `fallback` — same three string fields). Task 2 reads this file by
  path; no other interface is exposed.

- [ ] **Step 1: Write the profile table**

Create `.claude/skills/delegate-to-pi/references/pi-profiles.json` with
exactly this content:

```json
{
  "default_tier": "M",
  "profiles": {
    "S": {
      "provider": "openai-codex",
      "model": "gpt-5.6-luna",
      "thinking": "low",
      "fallback": { "provider": "opencode-go", "model": "deepseek-v4-flash", "thinking": "low" }
    },
    "M": {
      "provider": "openai-codex",
      "model": "gpt-5.6-terra",
      "thinking": "medium",
      "fallback": { "provider": "opencode-go", "model": "deepseek-v4-flash", "thinking": "medium" }
    },
    "L": {
      "provider": "openai-codex",
      "model": "gpt-5.6-sol",
      "thinking": "high",
      "fallback": { "provider": "opencode-go", "model": "deepseek-v4-pro", "thinking": "high" }
    }
  }
}
```

- [ ] **Step 2: Verify the JSON parses**

Run:

```bash
python3 -c "import json; json.load(open('.claude/skills/delegate-to-pi/references/pi-profiles.json')); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Verify every provider/model pair actually exists in this machine's pi catalog**

Run:

```bash
~/.local/bin/pi --list-models 2>&1 | grep -E '^(openai-codex\s+gpt-5\.6-(luna|terra|sol)|opencode-go\s+deepseek-v4-(flash|pro))\s'
```

Expected: exactly 5 matching lines — one each for `openai-codex
gpt-5.6-luna`, `openai-codex gpt-5.6-terra`, `openai-codex gpt-5.6-sol`,
`opencode-go deepseek-v4-flash`, `opencode-go deepseek-v4-pro`. If any
model name from the JSON is missing from this output, `pi`'s catalog has
changed since this plan was written — stop and report which name(s) no
longer resolve; do not silently substitute a different model.

- [ ] **Step 4: Live-spawn one tier and confirm the launched pi process shows the expected model**

Confirm the precondition, then spawn a throwaway `pi` process using the
`M` tier's exact flags in a scratch cwd, and read its pane to confirm the
model name is visible on screen:

```bash
echo "HERDR_ENV=$HERDR_ENV"
herdr status
herdr agent start profile-validate-m --cwd /private/tmp --no-focus -- pi --provider openai-codex --model gpt-5.6-terra --thinking medium
```

Note the `pane_id` from the JSON response (e.g. `w1X:pY`), then poll until
settled and read the pane:

```bash
sleep 3
herdr agent get <pane_id>
herdr pane read <pane_id> --source visible --lines 40
```

Expected: `agent_status` is `idle` (or `working` if the model is still
starting — wait a few more seconds and re-check), and the pane's visible
output includes the literal string `gpt-5.6-terra` somewhere in its status
line (this is how the base skill's design doc confirmed model visibility
live — the pane's bottom status bar shows the active model name).

Clean up the throwaway agent:

```bash
herdr pane close <pane_id>
```

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/delegate-to-pi/references/pi-profiles.json
git commit -m "feat: add pi-profiles.json tier table for delegate-to-pi"
```

---

### Task 2: Wire tier selection into the skill procedure

**Files:**
- Modify: `.claude/skills/delegate-to-pi/SKILL.md` (full rewrite of body —
  frontmatter unchanged)
- Modify: `.claude/skills/delegate-to-pi/references/herdr-cli.md` (append
  one new section)

**Interfaces:**
- Consumes: `.claude/skills/delegate-to-pi/references/pi-profiles.json`
  from Task 1 — read by path, top-level keys `default_tier` and
  `profiles.<TIER>.{provider,model,thinking,fallback.{provider,model,thinking}}`.
- Produces: the renumbered `SKILL.md` section scheme (§0 Precondition, §1
  Choose a tier and profile, §2 Resolve the target pi agent, §3 Send the
  goal/poll, §4 Handle blocked, §5 Handle idle/done, §6 Fallback
  subroutine, §7 Turn cap, §8 Report) that any later task or human reading
  this skill relies on for cross-references.

- [ ] **Step 1: Replace `SKILL.md` in full**

Replace the entire contents of
`.claude/skills/delegate-to-pi/SKILL.md` with:

````markdown
---
name: delegate-to-pi
description: Delegate a coding goal to a `pi` agent running under herdr — spawn or reuse it, feed it prompts, observe its interactive session, verify its work against the actual diff, and iterate until the goal is met or escalation is needed. Use when the user asks to delegate to pi, have pi build/fix/implement something, or invokes /delegate-to-pi <goal>.
user-invocable: true
---

# delegate-to-pi

You act as a supervisor: you do not implement the goal yourself. You drive a
`pi` coding agent through herdr until the goal is met, verifying its work
yourself before reporting success.

Read `references/herdr-cli.md` before running any herdr command — it has the
exact validated command syntax and gotchas that will silently break this
procedure if skipped: send-without-submit, pane_id-vs-name targeting, and
settle detection (an agent can settle as `idle`, `done`, or `blocked`
depending on its detection mode — never assume only one will occur).

Read `references/pi-profiles.json` for the tier-to-model/provider/thinking
table used in §1 to pick which `pi` process to launch.

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

Classify using this rubric:

- **S** — single-file or mechanical change with a clear, low-risk spec
  (e.g. fix a typo, adjust a config value, a well-specified one-file bug fix).
- **M** — multi-file coordination or ordinary feature work; this is
  `pi-profiles.json`'s `default_tier` and the tier to use when the goal
  doesn't clearly match S or L.
- **L** — architecture-level judgment calls, broad or ambiguous scope, or
  anything touching security/production-sensitive surfaces.

Read `references/pi-profiles.json` and look up the chosen tier's
`provider`, `model`, and `thinking` values, plus its `fallback` entry (used
later in §6 if needed).

**Gate on L:** if the chosen tier is `L`, stop and ask the user to confirm
before proceeding — state the goal and why it needs the top tier. This is a
single up-front confirmation for the whole delegation, not a per-turn
check. If the user declines, use the `M` tier's profile for this
delegation instead. If they confirm, proceed with `L`. Do not re-ask later
in the same delegation — the tier, once settled here (by classification, or
by the user's answer to this gate), does not change again.

Track two pieces of state for the rest of this delegation: the chosen
`TIER` (S, M, or L) and a `fallback_used` flag, starting `false` — §6 sets
it to `true` the first time it fires, and checks it to decide whether a
repeat failure should retry again or escalate.

## 2. Resolve the target pi agent

"Target cwd" means your own current working directory for the whole
delegation — it is not a variable to assign once and recall later. Each Bash
tool call in a real session is a fresh shell, so nothing you assign in one
call persists to another; every command below that needs the cwd (here and
in §5) computes it fresh with `"$(pwd)"`.

```bash
herdr agent list
```

Filter the returned `agents` for `agent == "pi"`, `cwd` equal to your cwd,
**and `name` starting with `pi-worker-<TIER>`** for the `TIER` chosen in
§1 (e.g. `pi-worker-M`). An idle or done agent under a *different* tier's
name is not a reuse candidate for this delegation — leave it as-is (it's
harmless, and may get reused by a future delegation at that same tier) and
spawn a fresh one below instead.

Note: this name-based filter only works for agents `herdr agent start`
actually launched with a name — an agent attached to a pane some other way
has no `name` field in `agent list`/`agent get` at all and will simply not
match any `pi-worker-*` filter, which is the desired behavior (never reuse
an agent you can't positively identify as this skill's own).

- If one is found with `agent_status` in `{idle, done}` → reuse it. Its
  `pane_id` is your `<target>` for every step below.
- If none is found, or the only matches are anything other than `idle`/`done`
  (i.e. `working`, `blocked`, or `unknown`) → spawn a new one, using the
  `provider`/`model`/`thinking` values looked up in §1 for `TIER`:

```bash
herdr agent start pi-worker-<TIER> --cwd "$(pwd)" --split right --no-focus -- pi --provider <provider> --model <model> --thinking <thinking>
```

  (Substitute the literal tier letter for `<TIER>` in the name, e.g.
  `pi-worker-M`, and the profile's actual values for `<provider>`,
  `<model>`, `<thinking>`. If `pi-worker-<TIER>` is already taken by another
  active agent, pick a variant name like `pi-worker-<TIER>-2`.) The
  response's `pane_id` field is your `<target>`. Poll (`herdr agent get
  <target>`, see §3) until its status is `idle` or `done` before sending
  anything — a freshly spawned `pi` needs a moment to start.

  If `agent start` fails for any other reason (no workspace, `pi` not on
  PATH in the spawned pane, socket error, etc.), show the user herdr's error
  output verbatim and stop — do not attempt a workaround.

**Use `pane_id` as `<target>` everywhere below, never the free-form name.**
`herdr agent *` calls tolerate the name; `herdr pane *` calls (used for
`send-keys` in §3) reject it outright with `pane_not_found`. Resolving once
here and reusing that value avoids the mismatch entirely.

## 3. Send the goal, then poll to settlement

Before sending, increment your turn counter (see §7) — every pass through
this section counts as one turn against the cap, regardless of how it
eventually settles (`blocked`-then-answered, goal met, or goal not met). The
very first send (the initial goal prompt) is turn 1.

Send using the two-step recipe (§ "Send a prompt" in the reference file):

```bash
herdr agent send <target> "<goal or follow-up prompt>"
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
what pi's screen currently looks like, and ask whether to keep waiting or
abort. Don't guess.

## 4. Handle `blocked`

Read the pane to see pi's exact question:

```bash
herdr agent read <target> --source visible --lines 200
```

**First, check for a rate-limit or usage-failure signature** (see §6 for
the exact phrases and what to do) before treating this as an ordinary
question. If the pane text matches, go to §6 instead of the steps below.

Otherwise, decide how to answer:

- **Default: answer it yourself** and continue the loop (go to §3 with your
  answer as the next prompt) — most blocks are ordinary clarifications or
  confirmations of reversible steps. Going back to §3 begins a new turn (you
  already incremented the counter when you sent this cycle's prompt — see
  §7), so a `pi` agent that repeatedly blocks without making real progress
  still trips the cap instead of looping indefinitely for free.
- **Escalate to the user instead of auto-answering** when the question is
  asking you to approve something that falls under the user's global
  CLAUDE.md Never/Off-limits rules: destructive git or filesystem operations
  (including but not limited to force-push, `reset --hard`, `rm -rf`,
  deleting files/branches, discarding uncommitted changes), touching
  secrets/credentials/`.env.keys`, or production databases/infrastructure/live
  customer data. In that case, stop, show the user pi's exact question
  verbatim, and wait for their answer before relaying anything back to pi.
  Do not resolve the blocking question yourself by implementing or approving
  the risky step in pi's place — escalating means handing control to the
  user, not working around the block.

## 5. Handle `idle`/`done` (settled): verify, don't just relay

When status is `idle` or `done` (both mean pi has settled — see §3), read
the full output:

```bash
herdr agent read <target> --source recent-unwrapped --lines 200
```

**First, check for a rate-limit or usage-failure signature** (see §6) in
that output before doing anything else. If it matches, go to §6 instead of
the steps below — do not interpret a rate-limited/quota-exhausted response
as "goal met" or "goal not met".

Otherwise, independently check what actually happened — do not trust pi's
self-report on its own:

```bash
git -C "$(pwd)" status --porcelain
git -C "$(pwd)" diff
```

Compare the diff and any test/build output pi already reported against the
original goal. Two outcomes:

- **Goal met** → go to §8 (report).
- **Goal not met / partially met** → compose a specific follow-up prompt
  describing exactly what's missing or wrong (reference the actual diff, not
  a vague "try again") and go back to §3 (which begins a new counted turn —
  see §7).

## 6. Fallback on rate-limit or usage failure

This section is a subroutine referenced from §4 and §5 — it only runs when
one of them detects a visible rate-limit or usage-failure signature in
pi's output: phrases like "rate limit", "429", "quota exceeded",
"insufficient_quota", or "usage limit reached" (case-insensitive; check
the substring, not an exact phrase match). No other failure type (a bug in
pi's own output, an ordinary blocked question, a poll timeout) reaches this
section — those stay in §3/§4/§5/§7's existing handling.

- **If `fallback_used` is still `false`:**
  1. Set `fallback_used = true`.
  2. Close the current pane: `herdr pane close <target>`.
  3. Look up `TIER`'s `fallback` entry in `references/pi-profiles.json`
     (`provider`, `model`, `thinking`).
  4. Spawn a replacement, reusing the same name (the original is now
     closed, freeing it):
     ```bash
     herdr agent start pi-worker-<TIER> --cwd "$(pwd)" --split right --no-focus -- pi --provider <fallback_provider> --model <fallback_model> --thinking <fallback_thinking>
     ```
  5. Update `<target>` to the new `pane_id` from the response.
  6. Poll until settled (idle/done/blocked), same as §3.
  7. Resend the exact prompt that triggered this failure (go to §3 with
     that same prompt text — this does not skip the turn-counter increment
     described in §7; re-sending is itself a new turn).
- **If `fallback_used` is already `true`:** the fallback has already been
  tried once this delegation and it also hit a rate-limit/usage-failure
  signature. Do not try a third variant — escalate to the user immediately:
  show both failures (the original profile's and the fallback profile's)
  verbatim, state the goal and tier chosen, and stop. Do not keep looping.

## 7. Turn cap

Track turns: one turn = one pass through §3 (send + poll to settlement),
counted at the moment you send, before you know how it will settle. This
covers every cycle uniformly — whether it settles as `blocked`-then-answered
(§4), goal met, or goal not met (§5) — so repeated blocking questions count
against the cap exactly like unproductive work attempts do; nothing loops for
free. A resend after a fallback respawn (§6) is also a turn, not a free
retry. The initial goal prompt is turn 1. Default cap: 6 turns.

- If you hit the cap while the goal still isn't met, or two consecutive turns
  produced no meaningful diff/progress, stop iterating. Escalate to the user:
  state the original goal, what pi actually did across turns, and why you
  judge it insufficient. Do not keep looping past this point, and do not
  implement or fix the remaining work yourself — escalating means stopping
  and handing control back to the user, not quietly finishing the job in
  pi's place.

## 8. Report

Whether the outcome is success, escalation, or a stuck state, tell the user:

- The original goal.
- The tier (`S`/`M`/`L`) and profile chosen in §1, and whether a fallback
  (§6) was used during this delegation.
- The actual diff (or a summary of it if large) — never claim success
  without having looked at it.
- Any test/build results observed.
- If escalated: exactly what you need from them to continue.
````

- [ ] **Step 2: Append the agent-name-persistence finding to `herdr-cli.md`**

In `.claude/skills/delegate-to-pi/references/herdr-cli.md`, insert the
following new section immediately after the existing "Find an existing pi
agent for a cwd" section and before the existing "Spawn a new pi agent"
section:

```markdown
## Agent names persist only when spawned via `agent start`

The `<name>` given to `herdr agent start <name>` is echoed back in that
call's own response, and — confirmed live — also persists afterward in both
`herdr agent get <pane_id>` and `herdr agent list`, as a `name` field on
that agent's entry. An agent whose pane was never launched via
`herdr agent start` (attached some other way) has **no** `name` field at
all in either call.

Confirmed live: spawning `dtp-profile-probe` via `agent start` and then
calling `agent get w1T:pF` on its pane showed `"name":"dtp-profile-probe"`
in the response; a separate, longer-running `pi` agent not started that
way (`w1P:p1`) showed no `name` key whatsoever in the same call.

herdr exposes no other way to discover what model/provider/thinking a
running agent process was launched with — `agent get`, `agent list`, and
`agent explain --json` all omit it. Anything that needs to tell agent
instances apart by launch configuration (not just by cwd/status) has to
encode that information into the spawn `name` itself and filter on it later
— there is no other persisted signal to check.
```

- [ ] **Step 3: Verify internal `§N` cross-references are consistent**

Run:

```bash
grep -n '§[0-9]' .claude/skills/delegate-to-pi/SKILL.md
grep -n '^## [0-9]' .claude/skills/delegate-to-pi/SKILL.md
```

Manually confirm every `§N` mentioned in the first command's output refers
to a heading number that actually exists in the second command's output
(headings run `0` through `8`). Fix any mismatch before continuing.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/delegate-to-pi/SKILL.md .claude/skills/delegate-to-pi/references/herdr-cli.md
git commit -m "feat: add tier-based model/provider/thinking selection to delegate-to-pi"
```

---

### Task 3: End-to-end dry run

**Files:** none created or modified by this task itself — it exercises
Tasks 1–2's output and fixes forward if something's broken (see Step 6).

**Interfaces:**
- Consumes: `references/pi-profiles.json` and the renumbered `SKILL.md`
  from Tasks 1–2.

- [ ] **Step 1: Set up a scratch repo**

```bash
rm -rf /private/tmp/delegate-to-pi-profiles-e2e
mkdir -p /private/tmp/delegate-to-pi-profiles-e2e
cd /private/tmp/delegate-to-pi-profiles-e2e
git init -q
echo "placeholder" > notes.txt
git add notes.txt
git commit -q -m "initial scratch commit"
```

- [ ] **Step 2: Run a real S-tier delegation end-to-end**

Follow `SKILL.md` yourself, acting as the delegate-to-pi skill, for the
goal: *"Add a one-line comment `# scratch note` to the top of notes.txt."*
in cwd `/private/tmp/delegate-to-pi-profiles-e2e`.

- §1: classify as `S` (single-file, mechanical, low-risk). Read
  `pi-profiles.json`, confirm the looked-up values are
  `provider=openai-codex`, `model=gpt-5.6-luna`, `thinking=low`.
- §2: `herdr agent list`, confirm no `pi-worker-S` exists yet for this cwd,
  spawn with:
  ```bash
  herdr agent start pi-worker-S --cwd /private/tmp/delegate-to-pi-profiles-e2e --split right --no-focus -- pi --provider openai-codex --model gpt-5.6-luna --thinking low
  ```
  Poll until settled.
- §3: send the goal, poll to settlement.
- §5: read output, run `git -C /private/tmp/delegate-to-pi-profiles-e2e
  status --porcelain` and `git ... diff`, confirm the comment was actually
  added. If not met, follow the documented follow-up-prompt path (§3
  again) until it is, or until you judge it genuinely stuck (report as
  such rather than forcing success).
- §8: write out the report exactly as the skill specifies (goal, tier +
  profile, diff, test/build output, none needed here since there's no
  test/build for a scratch text file).

Record: did the spawn command produce a running `pi` process showing
`gpt-5.6-luna` in its pane (check with `herdr pane read <target> --source
visible --lines 40`)? Did the diff match the goal?

- [ ] **Step 3: Confirm tier-scoped reuse does not cross tiers**

Without closing the `pi-worker-S` agent from Step 2, run §1–§2 again for a
*different*, M-tier goal in the **same** cwd (e.g. *"Add a second line `#
second scratch note` to notes.txt"*, classified `M` since it's still
simple but treat it as M for this check regardless of how trivial it is —
the point of this step is exercising the tier filter, not re-judging the
rubric).

- §1: tier = `M`. Profile = `provider=openai-codex`, `model=gpt-5.6-terra`,
  `thinking=medium`.
- §2: run `herdr agent list`, filter for `cwd ==
  /private/tmp/delegate-to-pi-profiles-e2e` and name starting
  `pi-worker-M`. Confirm **no match** (only `pi-worker-S` exists in that
  cwd) → spawn a new `pi-worker-M` agent with the M profile's flags.

Record: after this spawn, `herdr agent list` filtered to this cwd should
show **two** `pi` agents — one named `pi-worker-S`, one named
`pi-worker-M` — confirming the S-tier agent was correctly left alone
rather than reused for the M-tier goal. Send the goal, poll, verify via
diff, report, same as Step 2.

- [ ] **Step 4: Review (not live-execute) the L-tier gate and fallback subroutine**

The `L` gate (§1) and the fallback subroutine (§6) both require either a
real human decision or a real rate-limit failure to exercise end-to-end —
neither is something this dry run should simulate by answering on the
user's behalf (that would defeat the point of a gate meant for a real
human, and a real rate-limit isn't reliably reproducible on demand).
Instead:

- Re-read §1's gate paragraph in the `SKILL.md` you just wrote in Task 2.
  Confirm it unambiguously says to *stop* and *ask the user* before
  proceeding with `L`, and that declining falls back to `M` — not silently
  proceeding with `L` regardless of an answer.
- Re-read §6. Confirm the two branches (`fallback_used` false vs. true)
  are mutually exclusive and that the "already true" branch escalates
  instead of looping — i.e., there's no path where a third attempt could
  occur.

Record in your report which document sections you re-read and that both
read as designed. This is a structural review, not a passed/failed test —
say so plainly rather than implying a live test occurred.

- [ ] **Step 5: Clean up**

```bash
herdr agent list 2>&1 | python3 -c "
import json, sys
d = json.load(sys.stdin)
for a in d['result']['agents']:
    if a.get('cwd') == '/private/tmp/delegate-to-pi-profiles-e2e':
        print(a['pane_id'], a.get('name'))
"
```

Close every `pane_id` printed above:

```bash
herdr pane close <pane_id>
```

Then remove the scratch repo:

```bash
rm -rf /private/tmp/delegate-to-pi-profiles-e2e
```

- [ ] **Step 6: Fix forward if anything broke**

If any step above surfaced a real defect in `SKILL.md`,
`herdr-cli.md`, or `pi-profiles.json` (wrong flag, wrong section number,
wrong reuse behavior), fix it directly in this task, re-run the specific
step that failed to confirm the fix, then commit:

```bash
git add .claude/skills/delegate-to-pi
git commit -m "fix: correct issue found during delegate-to-pi profiles dry run"
```

If nothing broke, skip this step — no empty commit.

- [ ] **Step 7: Write the report**

Include: the exact commands run for Steps 2–3, the confirmed model names
seen in each pane, the `agent list` output showing both differently-tiered
agents coexisting in Step 3, and the structural-review notes from Step 4.

---

### Task 4: Skill quality review

**Files:** none created — this task dispatches a review and applies any
resulting fixes to the files from Tasks 1–3.

**Interfaces:** none new.

- [ ] **Step 1: Dispatch `plugin-dev:skill-reviewer`**

Dispatch the `plugin-dev:skill-reviewer` agent against
`.claude/skills/delegate-to-pi/` (all three files: `SKILL.md`,
`references/herdr-cli.md`, `references/pi-profiles.json`), asking it to
review the whole skill directory as it now stands (not just this plan's
diff) for triggering-description quality, internal consistency, and
adherence to good skill-authoring practice.

- [ ] **Step 2: Apply findings**

For each finding the reviewer reports: fix genuine defects directly in the
relevant file. For anything you judge a false positive or out of scope for
this plan, note why in your task report rather than silently dropping it.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/delegate-to-pi
git commit -m "polish: address skill-reviewer findings for delegate-to-pi profiles"
```

If the reviewer found nothing worth changing, skip this step — no empty
commit, but still report that the review ran clean.
