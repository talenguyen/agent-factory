# Observability for the software-factory orchestration layer

## Problem

There is no visibility into how this repo's own tooling gets used: which
skills get invoked, which tools get called, which `pi` tier/profile gets
spawned by `delegate-to-pi`, and how many turns a delegation takes before
settling. Without this, there's no data to guide improving the skills,
the tier rubric, or the pipeline itself.

## Goals

- Capture, for the software-factory repo specifically (not `.projects/<name>`
  subprojects — those may get their own instrumentation later):
  - Every tool call and skill invocation made in a Claude Code session
    working in this repo.
  - Every prompt submitted to such a session.
  - Session start/end boundaries.
  - For every `delegate-to-pi` delegation: which tier/profile was chosen,
    whether it was a fresh spawn or a reuse, whether a fallback/escalation/
    turn-cap was hit, and the final outcome — plus, derived from `pi`'s own
    session transcript, turn count, tool calls, and token cost for that
    delegation.
- Make the captured data queryable via a CLI summary and a static HTML
  dashboard, both regenerated on demand from the same underlying log.
- Never let telemetry capture interfere with, slow down, or break the
  actual work being observed.

## Non-goals

- Instrumenting Claude Code sessions running inside `.projects/<name>`
  subprojects.
- Exporting to a real OpenTelemetry collector or any external service —
  storage is local files only.
- A live/auto-refreshing dashboard or long-running collector process.
- Modifying `pi`'s own runtime — it already persists rich session
  transcripts to `~/.pi/agent/sessions/`; this design reads those rather
  than re-instrumenting `pi`.

## Data model

A single flat, append-only event log: `var/telemetry/events.jsonl`
(repo-root, gitignored). Every line is one JSON object with common fields
`ts` (ISO 8601, stamped by the writer — never trusted from hook input),
`event` (type, see table), and `session_id` (the Claude Code session that
produced the event, when applicable).

| `event` | Written by | Extra fields |
|---|---|---|
| `session_start` | Claude Code hook (`SessionStart`) | `source` |
| `session_end` | Claude Code hook (`SessionEnd`) | `reason` |
| `prompt_submitted` | Claude Code hook (`UserPromptSubmit`) | `prompt` (text) |
| `tool_call` | Claude Code hook (`PostToolUse`) | `tool_name`, `success`, `tool_input` (kept as-is; for `tool_name == "Skill"` this captures the skill name/args without special-casing) |
| `pi_spawn` | `delegate-to-pi` §2 | `trace_id`, `pi_session_id` (== `trace_id` for a fresh spawn), `tier`, `provider`, `model`, `thinking`, `herdr_name`, `cwd`, `pane_id` |
| `pi_reuse` | `delegate-to-pi` §2 | `trace_id` (fresh), `pi_session_id` (inherited, looked up from the most recent matching `pi_spawn`), `tier`, `herdr_name`, `cwd`, `pane_id` |
| `pi_fallback` | `delegate-to-pi` §6 | `trace_id`, fallback `provider`/`model`/`thinking` |
| `pi_escalated` | `delegate-to-pi` §4/§7 | `trace_id`, `reason` |
| `pi_turn_cap_hit` | `delegate-to-pi` §7 | `trace_id` |
| `pi_delegation_end` | `delegate-to-pi` §8 | `trace_id`, `outcome` (`goal_met` \| `escalated` \| `stuck`) |

`trace_id` is a UUID minted once per `delegate-to-pi` call (in §1, right
after `TIER` is settled) and threaded through every event for that
delegation. On a fresh spawn it doubles as the `--session-id` passed to
`bin/pi-project`, so `pi`'s own session filename already carries it — no
separate mapping table needed. On reuse, the *new* delegation still gets
its own fresh `trace_id` (it's a logically distinct delegation from the
user's perspective), but inherits the underlying `pi_session_id` from the
agent's original spawn.

## Capture layer 1: Claude Code hooks

Four hooks registered in `.claude/settings.json`, all pointing at one
script, `.claude/hooks/telemetry-log.sh`:

```json
{
  "hooks": {
    "PostToolUse": [
      { "matcher": "*", "hooks": [{ "type": "command", "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/telemetry-log.sh" }] }
    ],
    "UserPromptSubmit": [
      { "hooks": [{ "type": "command", "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/telemetry-log.sh" }] }
    ],
    "SessionStart": [
      { "hooks": [{ "type": "command", "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/telemetry-log.sh" }] }
    ],
    "SessionEnd": [
      { "hooks": [{ "type": "command", "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/telemetry-log.sh" }] }
    ]
  }
}
```

`PreToolUse` and `SubagentStop` are deliberately not used: `PostToolUse`
alone (with its `tool_use_succeeded` field) gives call counts and
success/failure without double-logging, and the `Agent` tool's own
`tool_input` already carries `subagent_type` via the `PostToolUse` event,
making a separate subagent event redundant.

`telemetry-log.sh` reads the hook's JSON payload from stdin (via `jq`),
extracts the fields listed in the Data Model table for that
`hook_event_name`, adds `ts`, and appends one line to
`var/telemetry/events.jsonl`. It **always exits 0**: any internal failure
(bad JSON, disk issue, unexpected payload shape) is swallowed so telemetry
can never block, slow down, or corrupt the tool call being observed. A
best-effort note about swallowed failures goes to `var/telemetry/errors.log`
for later debugging.

Note: `UserPromptSubmit`'s prompt-text field name (`prompt` vs
`prompt_text`) is inconsistently documented across sources; the script
probes for both rather than hard-coding one, and this gets confirmed
empirically (dump one real payload) during implementation.

## Capture layer 2: `delegate-to-pi` instrumentation

Small, targeted additions to the existing `delegate-to-pi/SKILL.md`
procedure — no change to its actual delegation logic:

- **§1**, after `TIER` is settled: generate `DELEGATION_ID=$(uuidgen)`,
  tracked as state alongside the existing `TIER`/`fallback_used`.
- **§2**, spawn command: add `--session-id "$DELEGATION_ID"` to the
  `bin/pi-project` invocation; on success, record a `pi_spawn` event.
- **§2**, reuse branch: record a `pi_reuse` event; its `pi_session_id` is
  found by scanning `events.jsonl` for the most recent `pi_spawn` with a
  matching `herdr_name` + `cwd`.
- **§6** (fallback): the replacement spawn gets its own fresh
  `--session-id` (a new UUID — it's physically a new `pi` process); record
  `pi_fallback` right after.
- **§4** (user-escalation branch) and **§7** (turn cap): record
  `pi_escalated` / `pi_turn_cap_hit` at the point each already stops to
  report to the user.
- **§8** (report): record `pi_delegation_end` with the final `outcome`.

All of these go through `bin/telemetry-record <event> key=value...`, a
small helper (bash + `jq`) that builds one JSON line from its arguments
plus a `ts` and appends it — so the skill's procedural text never
hand-assembles JSON inline. It writes to the same `events.jsonl` the hooks
write to; both are append-only, so concurrent writes from the two sources
need no locking (occasional interleaving is fine — each line is
independently valid JSON).

## Ingestion: deriving metrics from `pi`'s own session transcripts

`pi` already persists every message, tool call, token count, and cost to
`~/.pi/agent/sessions/<cwd-encoded>/<timestamp>_<uuid>.jsonl`. Rather than
re-instrumenting `pi`, ingestion happens lazily, only when a report is
generated:

1. For each `trace_id` with a `pi_spawn`/`pi_reuse` event, locate its
   session file by matching `pi_session_id` against the file's UUID.
2. Read it, keeping only messages timestamped between this delegation's
   start event and its `pi_delegation_end` (or "now", if still open).
3. From that slice, derive: turn count (`role: user` message count),
   tool-call counts by name, and total token cost
   (sum of `usage.cost.total` across assistant messages).

Bounding by timestamp window — rather than assuming one session file maps
to exactly one delegation — is what makes agent reuse work correctly: a
reused `pi` process's session file can contain several delegations
back-to-back, and the window cleanly separates them.

## Analysis tooling

- `bin/telemetry-report`: a Python script (the one non-trivial piece here,
  since it joins `events.jsonl` with per-delegation `pi` session data and
  buckets by tier/skill/tool). Run with no flags, it prints a plain-text
  summary to stdout: tool/skill call counts, tier distribution, average
  turns-to-settle per tier, fallback/escalation/turn-cap counts, and total
  observed `pi` cost.
- `bin/telemetry-report --html`: renders the same aggregates as one
  self-contained static HTML file (`var/telemetry/dashboard.html`, inline
  SVG/charts, no CDN, no build step, following the `dataviz` skill's
  guidance at implementation time) and opens it. Regenerated fresh on each
  invocation — not a live/auto-refreshing server.
- Both entry points share one aggregation module so the text and HTML
  views cannot drift out of sync with each other.

## Storage and error handling

`var/telemetry/` (containing `events.jsonl`, `errors.log`, and the
generated `dashboard.html`) is added to `.gitignore` alongside the
existing `.superpowers/`, `.worktrees/`, `.projects/` entries — it's local
usage data, not source.

The hook script and `telemetry-record` never fail loudly: malformed
input, missing `jq`, or disk issues are swallowed and always exit 0 (per
Claude Code's confirmed exit-code semantics, this guarantees telemetry
capture cannot block or alter the tool call it's observing), with a
best-effort note to `errors.log`. `telemetry-report`, being run manually,
is allowed to fail loudly on unexpected input — except a single malformed
JSONL line, which is skipped with a warning rather than aborting the
whole report.

## Testing

- Unit tests (Python, matching the existing `tests/test-pi-project-rpc.py`
  style) for the aggregation module, against fixture `events.jsonl` and
  fixture `pi` session `.jsonl` files, covering: tier distribution counts,
  turn-count derivation from a timestamp-bounded slice, and the
  reuse-lookup logic (a fixture with a `pi_spawn` followed later by a
  `pi_reuse` for the same `herdr_name`).
- A shell test for `telemetry-log.sh` / `telemetry-record`: feed a sample
  hook payload on stdin, assert the correct line lands in the log file,
  and assert a garbage/empty payload still exits 0 without crashing.
- Manual end-to-end verification per `verification-before-completion`: run
  a real tool call, a real skill invocation, and a small real
  `delegate-to-pi` delegation in this repo, then confirm
  `bin/telemetry-report` reflects them.

## Open questions for implementation (not blocking this spec)

- Confirm the exact `UserPromptSubmit` payload field name (`prompt` vs
  `prompt_text`) against a real captured payload before finalizing
  `telemetry-log.sh`.
