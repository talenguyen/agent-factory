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
is `idle` or `done`. Treat `working`/`blocked` as busy — don't reuse. (This
reuse-eligibility check is narrower than, and distinct from, the
settled/available check used later for detecting when a turn has ended —
see "Check an agent's status" below: a `blocked` agent counts as settled for
polling purposes, but not as free-to-reuse here, since it's mid-task waiting
on input for that specific task.)

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

## Spawn a new pi agent

```bash
herdr agent start <name> --cwd <target_cwd> --split right --no-focus -- "$(git rev-parse --show-toplevel)/bin/pi-project"
```

`<name>` is a free-form label (must be unique among active agents), e.g.
`crew-worker`. `--no-focus` keeps it in the background so it doesn't steal
terminal focus from the user. This repository deliberately uses the launcher
rather than bare Pi so global skills cannot enter delegated workers. Everything
after `--` is passed to the launched program unchanged. The response is
`{"result":{"agent":{"pane_id":"w1T:pB",...}}}` — save
`result.agent.pane_id`.

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

## Spawning with a specific provider/model/thinking level

The project launcher accepts `--provider <name> --model <id> --thinking
<level>` after the `--` separator, e.g.:

```bash
herdr agent start crew-worker-M --cwd <target_cwd> --split right --no-focus -- "$(git rev-parse --show-toplevel)/bin/pi-project" --provider openai-codex --model gpt-5.6-terra --thinking medium
```

Confirmed live: zooming the resulting pane (see "Read output" below) and
reading its status bar showed `(openai-codex) gpt-5.6-terra • medium` —
the requested provider, model, and thinking level all took effect exactly
as passed.

**`opencode-go` deepseek models do not honor intermediate `--thinking`
values.** Confirmed live across four separate spawns: `--provider
opencode-go --model deepseek-v4-flash` (and separately `deepseek-v4-pro`)
with `--thinking low` or `--thinking medium` both displayed `• high` in the
status bar instead of the requested level; only `--thinking off` displayed
correctly (`• thinking off`). This reproduced in a fresh cwd/session each
time, so it is not a session-resumption artifact — it is a real quirk of
how this provider/model combination handles thinking levels through `pi`.
**Do not configure a fallback profile for these models with anything other
than `off` or `high` for `thinking` — the other values will silently run
at `high` instead of what was requested.** Re-verify with a fresh
zoomed-pane read (see "Spawning" example above) if you add a new
provider/model combination to `pi-profiles.json`, rather than assuming any
requested thinking level takes effect as written.

Since herdr exposes no persisted way to query a running agent's
model/provider/thinking after the fact (see "Agent names persist..."
above), the zoomed-pane read immediately after spawn is the only way to
confirm a profile actually took effect — always do it once per spawn
rather than trusting the flags alone.

**Closing a pane frees its agent name for immediate reuse.** Confirmed
live: `herdr pane close <pane_id>` on an agent named `pi-close-reuse-probe`
succeeded, and an immediate `herdr agent start pi-close-reuse-probe ...`
with different `--provider`/`--model` flags succeeded too, spawning under
the same name with a new `pane_id` and the newly-requested model visible
on screen. There is no cooldown or lingering reservation on the name.

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

`HERDR_PANE_ID` is the authoritative identity of the orchestrator's own pane;
it is exported to every herdr-managed process. Before the **first** crew spawn,
never guess from the currently focused pane: capture the operator's focus,
focus `HERDR_PANE_ID`, start the worker, then restore the operator exactly:

```bash
CURRENT_PANE="$(herdr pane current | python3 -c 'import json,sys;print(json.load(sys.stdin)["result"]["pane"]["pane_id"])')"
herdr agent focus "$HERDR_PANE_ID"
herdr agent start <name> --cwd <target_cwd> --split right --no-focus -- <argv...>
herdr agent focus "$CURRENT_PANE"
```

If `HERDR_PANE_ID` is unset, fail loud and do not spawn. Falling back to the
currently focused pane can place a crew in another operator workspace.
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

## Check an agent's status

```bash
herdr agent get <target>
```

`<target>` here is the `pane_id` you captured (e.g. `w1P:p1`) — see the
targeting rule above. Returns `agent_status`: `idle | working | blocked |
done | unknown`.

**The idle-vs-done split described in herdr's public docs did not reproduce
for the `pi` build installed on this machine.** herdr's docs state `idle`
means "ready for input after its tab has been seen in the focused Herdr UI",
implying an unfocused pane that finishes work instead reports `done`. Live
testing (herdr 0.7.3) found the opposite: a `pi` agent spawned with
`--no-focus` and kept unfocused for its entire lifetime correctly reported
`working` while a task ran and `idle` — never `done` — once it finished.
This held even for `herdr wait agent-status <target> --status idle --timeout
30000` issued mid-task: it returned the moment the task actually completed,
rather than hanging to the timeout.

The reason, visible via `herdr agent explain <target> --json`: this instance
had `"screen_detection_skipped": true` with `"screen_detection_skip_reason":
"full_lifecycle_hook_authority"` — this `pi` build reports its own status to
herdr through lifecycle hooks instead of herdr screen-scraping the pane's
visible content, so its status stays accurate regardless of focus. A
separate, longer-lived `pi` agent already running on the same machine showed
`"screen_detection_skipped": false` (screen-scraped, manifest-based
detection) instead, so the detection mode is per agent *instance/process*,
not guaranteed by the agent name alone — a different `pi` build or an agent
still on screen-scraped detection could still exhibit the docs' idle/done
split.

**Practical guidance:** poll `herdr agent get <target>` on an interval
rather than relying on a single blocking wait call, and treat `idle`,
`done`, and `blocked` all as settled candidates. After submitting a prompt,
do **not** trust even one such candidate: confirmed live twice, an immediate
`agent get` returned the previous turn's `idle`/`done` while the pane visibly
showed `Working...`. The normal post-submit path must observe a
non-settled status and then three consecutive settled readings before reading
output; otherwise a stale prior response — including a reviewer `APPROVED` —
can be mistaken for the current turn's result. A separate, explicitly reported
60-second all-settled escape hatch handles a turn that completed before the
first poll, so that legitimate fast work does not wait for the full timeout.
To check which detection mode is active for a given target, run `herdr agent
explain <target> --json` and read `screen_detection_skip_reason`.

## Send a prompt (two steps — do both, in order)

```bash
herdr agent send <target> "<prompt text>"
herdr pane send-keys <target> enter
```

`agent send` only types the text into the input box. It does **not** submit.
`pane send-keys` succeeds with a completely empty response body in herdr 0.7.3;
treat only that known empty body as success. A non-empty unparseable body remains
a protocol error.
Skipping the `send-keys enter` step leaves the prompt sitting unsent
indefinitely. Confirmed live: after `agent send` alone, `agent_status`
stayed unchanged and the text was visible above the prompt divider,
unsubmitted; after `send-keys enter`, status flipped to `working`.

## Response nesting (adapter boundary)

These are the exact response paths validated against herdr 0.7.3. The adapter,
not `lib/crew/core.py`, owns these details:

| Command | Response path |
|---|---|
| `agent list` | `result.agents` |
| `agent start` | `result.agent.pane_id` |
| `agent get` | `result.agent.agent_status` |
| `agent send`, `agent focus` | `result.type` |
| `agent read` | `result.read.text` |
| `pane current` | `result.pane.pane_id` |
| `pane send-keys` | **empty body on success** (not JSON) |
| `pane zoom`, `pane close` | `result.type` |

## Read output

```bash
herdr agent read <target> --source visible --lines 200
```

`--source visible` shows the current screen. Use `recent-unwrapped` for more
scrollback if `visible` truncates ("... (N earlier lines, ctrl+o to expand)").

**Narrow panes truncate long status-bar text horizontally, not just
vertically.** Confirmed live: a `pi` agent spawned into a 39-column split
pane showed only `gpt-5` in its bottom status bar, with the rest of
`(openai-codex) gpt-5.6-terra • medium` cut off mid-word — `--source
recent-unwrapped` did not recover it, since the text was genuinely never
rendered past the pane's width, not merely scrolled off. Temporarily
widening the pane (`herdr pane zoom <pane_id> --on`, read, then
`herdr pane zoom <pane_id> --off`) revealed the full line. If you need to
confirm exact model/provider/thinking text from a pane's own display
(e.g. to verify a profile actually took effect) rather than just watching
for status changes, zoom first.

## Poll loop (settle detection)

Bash sketch for waiting after a prompt until an agent is `idle`, `done`,
or `blocked`, polling instead of using a single blocking wait call. All three
must be treated as settled candidates: as confirmed above, a hook-authority
`pi` agent goes straight back to `idle` and may never report `done` at all,
so a loop that only checks for `done`/`blocked` would hang until timeout;
conversely, a loop that only checks for `idle`/`done` would hang on an agent
genuinely waiting on user input. There are two acceptance paths:

1. **Normal path:** observe a non-settled status after submission, then three
   consecutive settled readings. This rejects a prior turn's stale settled
   status while its new turn begins.
2. **Fast-turn escape hatch:** if no non-settled status was ever observed,
   accept only after 60 seconds of continuously settled readings. At the
   five-second poll interval below this is 13 readings (from 0 through 60
   seconds), substantially longer than the observed status lag. The loop
   reports this path explicitly so the supervisor knows freshness was
   inferred from the bounded delay rather than observed directly.

The normal path remains three readings; the much longer escape hatch exists
only because a genuinely fast turn can begin and finish between polls:

```bash
target="w1P:p1"
timeout_s=600
interval_s=5
required_settled_polls=3
all_settled_escape_s=60
elapsed=0
settled_streak=0
saw_unsettled=false
while (( elapsed < timeout_s )); do
  agent_status=$(herdr agent get "$target" | python3 -c 'import json,sys;print(json.load(sys.stdin)["result"]["agent"]["agent_status"])')
  # (any JSON tool works here — e.g. `jq -r '.result.agent.agent_status'` if python3 isn't available)
  if [[ "$agent_status" == "idle" || "$agent_status" == "done" || "$agent_status" == "blocked" ]]; then
    settled_streak=$((settled_streak + 1))
    if [[ "$saw_unsettled" == true ]] && (( settled_streak >= required_settled_polls )); then
      echo "settled:$agent_status:after-unsettled"
      break
    elif [[ "$saw_unsettled" == false ]] && (( (settled_streak - 1) * interval_s >= all_settled_escape_s )); then
      echo "settled:$agent_status:all-settled-escape-hatch"
      break
    fi
  else
    saw_unsettled=true
    settled_streak=0
  fi
  sleep "$interval_s"
  elapsed=$((elapsed + interval_s))
done
```

Note: don't name the variable `status` — in zsh (this environment's default shell)
`status` is a read-only special variable (an alias for `$?`), and assigning to it
fails with `read-only variable: status`. Confirmed live while dry-running this
procedure. Use `agent_status` or similar instead.
