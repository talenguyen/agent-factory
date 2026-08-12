# delegate-to-pi: Claude Code skill for orchestrating `pi` agents via herdr

## Purpose

Give Claude Code a skill that lets it act as a supervisor/orchestrator: instead of
implementing a task itself, it plans the work, then drives one `pi` coding agent
(via the `herdr` terminal-workspace CLI) through spawn/prompt/observe/verify
cycles until the goal is met, escalating to the human only when genuinely
blocked or stuck.

This is a project-scoped skill, living at
`software-factory/.claude/skills/delegate-to-pi/SKILL.md`.

## Background: verified tool behavior

`herdr` (v0.7.3, installed at `/opt/homebrew/bin/herdr`) manages terminal
workspaces/tabs/panes and can start/observe/control coding-agent CLIs running
inside them, including a locally installed `pi` executable, over a local
socket API. Claude Code itself, when launched under herdr, runs with
`HERDR_ENV=1` and can call the `herdr` CLI directly.

The public docs at herdr.dev describe an older/different CLI shape than what's
actually installed (e.g. docs mention `agent start --kind`, `agent prompt
--wait`, `agent wait --until`; the installed binary has none of these). The
design below is based on the installed binary's own `--help` output and a live
end-to-end test against an already-running idle `pi` agent (pane `w1P:p1`,
cwd `~/agentic-loop`), not on the docs prose.

Two load-bearing findings from that live test:

1. **`herdr agent send <target> <text>` only types text into the input box —
   it does not submit.** Submission requires a separate
   `herdr pane send-keys <target> enter`. Skipping this leaves the prompt
   sitting unsent forever.
2. **`herdr wait agent-status <target> --status idle` times out for a
   background/unfocused pane.** herdr's own docs note `idle` means "ready for
   input after its tab has been seen in the focused Herdr UI" — for a pane
   that's never been focused, pi settles into `done` instead. Waiting on
   `idle` for a background delegate would hang until timeout every time.
   `herdr agent get <target>` (polled) reliably reports `done` in this case
   and was confirmed against the live test.

   **Correction (post-implementation):** further live testing during
   implementation found the opposite is just as possible, and detection mode
   is per pi-instance rather than a fixed property of "unfocused panes":
   a hook-authority `pi` instance (status reported via lifecycle hooks, not
   screen-scraping) settles to `idle` and never reports `done` at all, while
   a screen-scraped instance can exhibit the reverse. Neither `idle` nor
   `done` alone is safe to wait on. This finding is superseded — the
   implementation plan and shipped skill were corrected accordingly; treat
   `references/herdr-cli.md`'s "Check an agent's status" section as the
   corrected, authoritative source, not the paragraph above.

## Architecture

### Components

- **`SKILL.md`** — the procedure below, written as instructions for Claude to
  follow with its own Bash tool. Triggers on `/delegate-to-pi <goal>` or
  natural phrasing ("have pi build X", "delegate this to pi").
- **`references/herdr-cli.md`** — condensed, validated command recipes (spawn,
  send+submit, poll, read) so the exact syntax doesn't need to be
  re-discovered each run. Loaded by the skill on demand.

### Flow

1. **Precondition check** — confirm `HERDR_ENV=1` (or `herdr status` shows a
   running server). If not inside a herdr pane, stop and explain; no
   workaround (per user's global "never work around rules indirectly").

2. **Target resolution** — the target cwd is Claude's own current working
   directory (the same project it's already operating in). Run
   `herdr agent list`, filter for `agent == "pi"` and matching `cwd`.
   - If one exists with `agent_status` in `{idle, done}` → reuse it (address
     by its `pane_id`).
   - Otherwise spawn a new one:
     `herdr agent start <name> --cwd <cwd> --split right --no-focus -- pi`
     (kept unfocused so it doesn't steal the user's terminal focus).

3. **Settle detection (poll, not blocking wait)** — after spawn or after
   sending a prompt, poll `herdr agent get <target>` every ~3–5s (bounded by
   an overall timeout) rather than relying on a single blocking
   `wait agent-status` call. This sidesteps the idle-vs-done focus ambiguity
   found above, and gives Claude a natural point to log progress.
   - After spawn: wait until status is anything other than absent/starting
     (i.e. `idle` or `done`) before sending the first prompt.
   - After sending a prompt: wait until status is `done` or `blocked`.

4. **Send prompt** — the validated two-step recipe:
   `herdr agent send <target> "<prompt text>"` then
   `herdr pane send-keys <target> enter`.

5. **Blocked handling** — when status is `blocked`, read the pane
   (`herdr agent read <target> --source visible --lines N`) to get pi's exact
   question. Claude answers on pi's behalf by default — **except** when the
   request matches the user's global CLAUDE.md Never/Off-limits rules
   (destructive git/filesystem operations, secrets/credentials/`.env.keys`,
   production databases/infra/live customer data). Those cases are not
   auto-approved: Claude stops, surfaces the exact question to the human, and
   only relays an answer back to pi once the human has responded. This
   carve-out was explicitly confirmed with the user.

6. **Verification on done** — when status is `done`, Claude does not just
   relay pi's self-report. It independently checks:
   - `git -C <cwd> status --porcelain` / `git -C <cwd> diff` for what actually
     changed.
   - pi's own reported test/build output, visible in the pane read.
   - Whether the result actually satisfies the original goal.
   If unmet, Claude composes a specific follow-up describing what's
   missing/wrong and returns to step 4 (send prompt), incrementing a turn
   counter.

7. **Turn cap** — default max 6 send/observe turns per delegated goal. If the
   cap is hit, or two consecutive turns produce no meaningful diff/progress,
   Claude stops looping and escalates to the human with full context (what
   was asked, what pi did, why it's judged insufficient) rather than looping
   indefinitely.

8. **Reporting** — final summary plus the actual diff is reported to the
   human. Success is never claimed without having examined the diff/test
   output (consistent with `superpowers:verification-before-completion`).

### Error handling

- herdr not running / not in a herdr pane → stop, explain, no workaround.
- `agent start` fails → surface herdr's error output verbatim, stop.
- Overall timeout reached while polling → report last known pane output and
  status to the human; ask whether to keep waiting or abort, rather than
  guessing.
- Blocked on a destructive/off-limits request → escalate per step 5.

## Out of scope (v1)

- Parallel fan-out across multiple concurrent `pi` agents for independent
  subtasks. The primitives here (resolve-or-spawn, send+submit, poll, verify)
  are designed to be reusable per-subtask later, but running several at once
  is not built now — single delegate first, per user's explicit choice.
- Any model/provider flag tuning for `pi` — it launches with its own configured
  defaults; not overridden by this skill.

## Testing plan

Manual dry run against a low-stakes, reversible goal (e.g. "add a comment to a
specific file") in a real project directory, confirming the full loop:
resolve-or-spawn → send+submit → poll → verify via git diff → report. This
mirrors the live validation already performed against pane `w1P:p1` during
design (send-without-enter behavior, done-vs-idle status behavior).
