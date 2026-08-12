# delegate-to-pi Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `delegate-to-pi` Claude Code skill that supervises a `pi`
agent through `herdr` — spawn/reuse, prompt, poll, verify, iterate, escalate —
so Claude can delegate implementation work instead of doing it directly.

**Architecture:** A markdown skill (`SKILL.md`) plus a supporting CLI cheat
sheet (`references/herdr-cli.md`), both project-scoped under
`software-factory/.claude/skills/delegate-to-pi/`. No executable scripts —
every step is a plain `herdr`/`git` CLI call Claude runs itself via Bash.

**Tech Stack:** `herdr` 0.7.3 (installed at `/opt/homebrew/bin/herdr`), `pi`
CLI (installed at `~/.local/bin/pi`), bash, git.

## Global Constraints

- Skill is project-scoped: lives under `software-factory/.claude/skills/delegate-to-pi/`, not `~/.claude/skills/`.
- Command syntax must match the **installed** `herdr` 0.7.3 binary's own `--help` output and live-tested behavior — not the herdr.dev docs prose, which describes a different/older CLI shape.
- `herdr agent send` never submits by itself — every send must be followed by `herdr pane send-keys <target> enter`.
- Never rely on a single blocking wait call for settle detection — poll `herdr agent get` on an interval instead and treat `idle`, `done`, **and** `blocked` as settled/available. Detection mode is per agent-instance (`herdr agent explain <target> --json` → `screen_detection_skip_reason`): a hook-authority `pi` instance reports `idle` and never `done`; a screen-scraped instance can report `done` for an unfocused pane instead of `idle`. Never assume only one of the two will occur.
- Always target by `pane_id`, never by the free-form agent name — `herdr agent *` resolves names fine, but `herdr pane *` (used by `send-keys`/`close`) rejects them with `pane_not_found`. Resolve `pane_id` once and reuse it for every subsequent command.
- Blocked-question auto-answering has a mandatory carve-out: destructive git/filesystem ops, secrets/credentials/`.env.keys`, and production databases/infra/live customer data are never auto-approved — always escalate to the human.
- Default turn cap: 6 send/observe cycles per delegated goal before escalating as stuck.
- No parallel fan-out, no model/provider flag overrides for `pi` — out of scope for this plan (see spec).

---

### Task 1: herdr CLI reference + live validation

**Files:**
- Create: `software-factory/.claude/skills/delegate-to-pi/references/herdr-cli.md`

**Interfaces:**
- Produces: the canonical command recipes `SKILL.md` (Task 2) will point to — spawn (`herdr agent start <name> --cwd <cwd> --split right --no-focus -- pi`), status check (`herdr agent get <target>`), send+submit (`herdr agent send` then `herdr pane send-keys <target> enter`), read (`herdr agent read <target> --source visible|recent-unwrapped --lines N`), and the settle-poll loop pattern.

- [ ] **Step 1: Write the reference file**

Note: the outer fence below uses four backticks because the file's own
content contains three-backtick ```bash fences — a three-backtick outer
fence would close early at the first inner one.

````markdown
# herdr CLI reference for delegate-to-pi

Validated against herdr 0.7.3 and the installed `pi` CLI. The public docs at
herdr.dev describe a different/older CLI shape (`--kind`, `agent prompt
--wait`, `agent wait --until`) — none of that exists in this version. Use only
the commands below.

## Precondition

```bash
echo "$HERDR_ENV"   # must be 1
herdr status         # server.status must be "running"
```

## Find an existing pi agent for a cwd

```bash
herdr agent list
```

Returns JSON: `{"result":{"agents":[{"agent":"pi","agent_status":"idle|working|blocked|done|unknown","cwd":"...","pane_id":"w1P:p1", ...}]}}`.
Filter for `agent == "pi"` and `cwd == <target_cwd>`. Reuse if `agent_status`
is `idle` or `done`. Treat `working`/`blocked` as busy — don't reuse.

## Spawn a new pi agent

```bash
herdr agent start <name> --cwd <target_cwd> --split right --no-focus -- pi
```

`<name>` is a free-form label (must be unique among active agents), e.g.
`pi-worker`. `--no-focus` keeps it in the background so it doesn't steal
terminal focus from the user. Everything after `--` is passed to the
launched program unchanged. The response includes `pane_id` (e.g. `w1T:pB`)
— save it.

**Always target by `pane_id` from here on — never by the free-form name.**
`herdr agent *` subcommands (`send`, `get`, `read`) resolve a free-form agent
name fine, but `herdr pane *` subcommands (`send-keys`, `close`, etc.) do
**not** — they require the literal `pane_id`. Confirmed live:

```
$ herdr agent send dtp-probe2 "say hi"      # name — works
{"result":{"type":"ok"}}
$ herdr pane send-keys dtp-probe2 enter     # name — fails
{"error":{"code":"pane_not_found","message":"pane dtp-probe2 not found"}}
$ herdr pane send-keys w1T:pC enter         # pane_id — works, status -> working
```

Since every delegation turn mixes an `agent` call and a `pane` call, using
the name for one and forgetting to switch for the other is a real footgun.
The only safe rule: capture `pane_id` once (from `agent start`'s response,
`herdr agent get <name>`, or `herdr agent list`), then use that `pane_id` as
`<target>` for **every** command below — `agent` and `pane` alike — and never
pass the free-form name to anything again.

## Check an agent's status

```bash
herdr agent get <target>
```

`<target>` here is the `pane_id` you captured (e.g. `w1P:p1`) — see the
targeting rule above. Returns `agent_status`: `idle | working | blocked |
done | unknown`.

**Do not rely on `herdr wait agent-status --status idle` for a background
(unfocused) pane.** herdr's docs state `idle` means "ready for input after
its tab has been seen in the focused Herdr UI" — an unfocused pane that has
finished work reports `done`, not `idle`, and a wait on `idle` will hang until
timeout. Poll `herdr agent get <target>` on an interval instead, and treat
both `idle` and `done` as "settled/available".

## Send a prompt (two steps — do both, in order)

```bash
herdr agent send <target> "<prompt text>"
herdr pane send-keys <target> enter
```

`agent send` only types the text into the input box. It does **not** submit.
Skipping the `send-keys enter` step leaves the prompt sitting unsent
indefinitely. Confirmed live: after `agent send` alone, `agent_status`
stayed unchanged and the text was visible above the prompt divider,
unsubmitted; after `send-keys enter`, status flipped to `working`.

## Read output

```bash
herdr agent read <target> --source visible --lines 200
```

`--source visible` shows the current screen. Use `recent-unwrapped` for more
scrollback if `visible` truncates ("... (N earlier lines, ctrl+o to expand)").

## Poll loop (settle detection)

Bash sketch for waiting until an agent is `done` or `blocked`, polling
instead of using a single blocking wait call:

```bash
target="w1P:p1"
timeout_s=600
interval_s=5
elapsed=0
while (( elapsed < timeout_s )); do
  status=$(herdr agent get "$target" | python3 -c 'import json,sys;print(json.load(sys.stdin)["result"]["agent"]["agent_status"])')
  if [[ "$status" == "done" || "$status" == "blocked" ]]; then
    echo "$status"
    break
  fi
  sleep "$interval_s"
  elapsed=$((elapsed + interval_s))
done
```
````

- [ ] **Step 2: Validate the recipe live against a disposable test agent**

Use a scratch directory so this doesn't touch any real project or the user's
existing `pi` agents:

```bash
mkdir -p /tmp/delegate-to-pi-validate
herdr agent start pi-validate-task1 --cwd /tmp/delegate-to-pi-validate --split right --no-focus -- pi
```

Capture `pane_id` from the JSON response (e.g. `"pane_id":"w1T:pC"`) and use
that value — not the name `pi-validate-task1` — for every command below.
Substitute `<pane_id>` with the actual value you got back.

Poll until settled (expect `idle` or `done` within ~30s):

```bash
for i in $(seq 1 10); do
  herdr agent get <pane_id>
  sleep 3
done
```

Confirm the send-without-submit behavior documented above:

```bash
herdr agent send <pane_id> "reply with just the word pong, nothing else"
herdr agent get <pane_id>   # expect status still NOT "working" yet
herdr agent read <pane_id> --source visible --lines 10   # expect the text visible, unsubmitted
```

Expected: the sent text appears in the pane output but `agent_status` has not
changed to `working` — proving `agent send` alone doesn't submit.

Then submit and confirm it runs. This step also validates the pane-targeting
rule itself: `<pane_id>` must be the literal id (e.g. `w1T:pC`), not the name
`pi-validate-task1` — `herdr pane send-keys` rejects names with
`pane_not_found`.

```bash
herdr pane send-keys <pane_id> enter
herdr agent get <pane_id>   # expect "working"
```

- [ ] **Step 3: Confirm the done-vs-idle gotcha reproduces**

```bash
sleep 15
herdr agent get <pane_id>   # expect "done" (not "idle"), since the pane is unfocused
```

Expected: `agent_status` is `done`. If it instead shows `idle`, note the
discrepancy and update the reference file's wording before continuing — the
plan's later tasks depend on this behavior being accurate.

- [ ] **Step 4: Clean up the test agent**

```bash
herdr pane close <pane_id>
```

- [ ] **Step 5: Commit**

```bash
git add software-factory/.claude/skills/delegate-to-pi/references/herdr-cli.md
git commit -m "docs: add validated herdr CLI reference for delegate-to-pi"
```

---

### Task 2: SKILL.md procedure and safety policy

**Files:**
- Create: `software-factory/.claude/skills/delegate-to-pi/SKILL.md`

**Interfaces:**
- Consumes: the command recipes from `references/herdr-cli.md` (Task 1) — spawn, `agent get`, send+submit, read, poll loop.
- Produces: the full delegate-to-pi procedure other tasks (and future users) invoke via `/delegate-to-pi <goal>` or matching natural-language phrasing.

- [ ] **Step 1: Write SKILL.md**

Note: the outer fence below uses four backticks for the same reason as
Task 1 — the file's own content contains three-backtick ```bash fences.

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
settle detection (an agent can settle as `idle` or `done` depending on its
detection mode — never assume only one will occur).

## 0. Precondition

Confirm you're running inside a herdr pane:

```bash
test "$HERDR_ENV" = "1" && herdr status
```

If `HERDR_ENV` isn't `1`, or `herdr status` doesn't show `server.status:
running`, stop and tell the user this skill only works inside a herdr-managed
session — do not attempt any workaround.

## 1. Resolve the target pi agent

Target cwd = your own current working directory.

```bash
herdr agent list
```

Filter the returned `agents` for `agent == "pi"` and `cwd` equal to your cwd.

- If one is found with `agent_status` in `{idle, done}` → reuse it. Its
  `pane_id` is your `<target>` for every step below.
- If none is found, or the only matches are `working`/`blocked` → spawn a new
  one:

```bash
herdr agent start pi-worker --cwd "$(pwd)" --split right --no-focus -- pi
```

  (If `pi-worker` is already taken by another active agent, pick a variant
  name like `pi-worker-2`.) The response's `pane_id` field is your `<target>`.
  Poll (`herdr agent get <target>`, see §2) until its status is `idle` or
  `done` before sending anything — a freshly spawned `pi` needs a moment to
  start.

**Use `pane_id` as `<target>` everywhere below, never the free-form name.**
`herdr agent *` calls tolerate the name; `herdr pane *` calls (used for
`send-keys` in §2) reject it outright with `pane_not_found`. Resolving once
here and reusing that value avoids the mismatch entirely.

## 2. Send the goal, then poll to settlement

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

## 3. Handle `blocked`

Read the pane to see pi's exact question:

```bash
herdr agent read <target> --source visible --lines 200
```

Decide how to answer:

- **Default: answer it yourself** and continue the loop (go to §2 with your
  answer as the next prompt) — most blocks are ordinary clarifications or
  confirmations of reversible steps.
- **Escalate to the user instead of auto-answering** when the question is
  asking you to approve something that falls under the user's global
  CLAUDE.md Never/Off-limits rules: destructive git or filesystem operations
  (force-push, `reset --hard`, `rm -rf`, discarding uncommitted changes),
  touching secrets/credentials/`.env.keys`, or production
  databases/infrastructure/live customer data. In that case, stop, show the
  user pi's exact question verbatim, and wait for their answer before
  relaying anything back to pi.

## 4. Handle `idle`/`done` (settled): verify, don't just relay

When status is `idle` or `done` (both mean pi has settled — see §2), read
the full output:

```bash
herdr agent read <target> --source recent-unwrapped --lines 200
```

Then independently check what actually happened — do not trust pi's
self-report on its own:

```bash
git -C <target_cwd> status --porcelain
git -C <target_cwd> diff
```

Compare the diff and any test/build output pi already reported against the
original goal. Two outcomes:

- **Goal met** → go to §5 (report).
- **Goal not met / partially met** → compose a specific follow-up prompt
  describing exactly what's missing or wrong (reference the actual diff, not
  a vague "try again"), increment your turn counter, and go back to §2.

## 5. Turn cap

Track turns (one turn = one send-and-settle cycle in §2–4) starting from 1
for the initial goal prompt. Default cap: 6 turns.

- If you hit the cap while the goal still isn't met, or two consecutive turns
  produced no meaningful diff/progress, stop iterating. Escalate to the user:
  state the original goal, what pi actually did across turns, and why you
  judge it insufficient. Do not keep looping past this point.

## 6. Report

Whether the outcome is success, escalation, or a stuck state, tell the user:

- The original goal.
- The actual diff (or a summary of it if large) — never claim success
  without having looked at it.
- Any test/build results observed.
- If escalated: exactly what you need from them to continue.
````

- [ ] **Step 2: Verify structure by hand**

Check off each of these against the file you just wrote:
- Frontmatter has `name: delegate-to-pi`, `description:` containing the
  trigger phrases "delegate to pi" and "/delegate-to-pi", and
  `user-invocable: true`.
- Section 3 explicitly lists all four escalation categories from Global
  Constraints (destructive git/fs ops, secrets/`.env.keys`, production
  db/infra, live customer data).
- Section 5 states the default turn cap as 6.
- Every herdr command shown matches a recipe already present in
  `references/herdr-cli.md` (no invented flags).

- [ ] **Step 3: Commit**

```bash
git add software-factory/.claude/skills/delegate-to-pi/SKILL.md
git commit -m "feat: add delegate-to-pi skill procedure"
```

---

### Task 3: End-to-end dry run

**Files:**
- None created — this task exercises Tasks 1–2's output against a real, disposable target repo.

**Interfaces:**
- Consumes: the full `SKILL.md` procedure (Task 2) and `references/herdr-cli.md` (Task 1).

- [ ] **Step 1: Create a disposable target repo with a trivial, verifiable goal**

```bash
rm -rf /tmp/delegate-to-pi-e2e
mkdir -p /tmp/delegate-to-pi-e2e
cd /tmp/delegate-to-pi-e2e
git init
printf 'def add(a, b):\n    return a + b\n' > math_utils.py
git add math_utils.py
git commit -m "initial"
```

- [ ] **Step 2: Follow SKILL.md §0–1 by hand to resolve/spawn a pi agent for this cwd**

```bash
test "$HERDR_ENV" = "1" && herdr status
herdr agent list   # confirm no existing pi agent at /tmp/delegate-to-pi-e2e
herdr agent start pi-e2e-test --cwd /tmp/delegate-to-pi-e2e --split right --no-focus -- pi
```

Capture `pane_id` from the response and use it as `<pane_id>` below — per the
targeting rule in the reference file, `pane send-keys`/`pane close` reject
the name `pi-e2e-test` and require the literal id.

Poll per §1/§2 until `idle`/`done`.

- [ ] **Step 3: Send the goal per §2**

```bash
herdr agent send <pane_id> "In math_utils.py, add a function subtract(a, b) that returns a - b. Do not touch anything else."
herdr pane send-keys <pane_id> enter
```

Poll `herdr agent get <pane_id>` until `idle`, `done`, or `blocked` (expect
`idle` or `done` for a goal this small, depending on this agent's detection
mode — check `herdr agent explain <pane_id> --json` if curious which one).

- [ ] **Step 4: Verify per §4**

```bash
git -C /tmp/delegate-to-pi-e2e diff
git -C /tmp/delegate-to-pi-e2e status --porcelain
```

Expected: diff shows a new `subtract(a, b)` function in `math_utils.py` and
nothing else changed. If it's missing or wrong, this is exactly the "goal not
met" branch of §4 — compose the follow-up prompt described there and repeat
from Step 3 once, to confirm the iterate-on-failure path also works.

- [ ] **Step 5: Report per §6**

Write out, as you would to the user: the original goal, the actual diff, and
the outcome (met on turn N). This confirms §6 produces something concrete,
not a placeholder summary.

- [ ] **Step 6: Clean up**

```bash
herdr pane close <pane_id>
rm -rf /tmp/delegate-to-pi-e2e /tmp/delegate-to-pi-validate
```

- [ ] **Step 7: Commit a note of the dry run**

If the dry run required any correction to `SKILL.md` or the reference file,
those edits were already committed in their respective steps above. If no
corrections were needed, there is nothing new to commit for this task —
proceed to Task 4.

---

### Task 4: Skill quality review

**Files:**
- Modify: `software-factory/.claude/skills/delegate-to-pi/SKILL.md` (if the reviewer finds issues)
- Modify: `software-factory/.claude/skills/delegate-to-pi/references/herdr-cli.md` (if the reviewer finds issues)

**Interfaces:**
- Consumes: the finished skill from Tasks 1–3.

- [ ] **Step 1: Run the skill reviewer**

Dispatch the `plugin-dev:skill-reviewer` agent against
`software-factory/.claude/skills/delegate-to-pi/` and ask it to check the
skill's description quality (will it actually trigger on "delegate to pi" /
"/delegate-to-pi" phrasing?), structure, and whether any instructions are
vague enough that a fresh Claude session could misinterpret them.

- [ ] **Step 2: Address findings**

Apply any concrete fixes the reviewer surfaces directly to `SKILL.md` or the
reference file. Skip suggestions that would reintroduce scope this plan
explicitly excluded (parallel fan-out, model/provider flags) — note in your
response why they're deferred.

- [ ] **Step 3: Commit**

```bash
git add software-factory/.claude/skills/delegate-to-pi/
git commit -m "polish: address skill-reviewer findings for delegate-to-pi"
```
