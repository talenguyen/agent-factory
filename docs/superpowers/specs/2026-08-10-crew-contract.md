# The crew contract — Turn Contract, adapter interface, and `bin/crew`

Phase 2a of `docs/superpowers/plans/2026-08-10-oss-fork.md`. Written by the
orchestrator and **not delegated**: this document *is* the architecture-level
judgment of Phase 2. Everything after it is transcription against this contract.

Stored under `docs/superpowers/specs/` to match the repo's convention; the plan
refers to it as `docs/specs/crew-contract.md`.

## Purpose

`delegate-to-pi/SKILL.md` is **859 lines of prose** across 17 sections. A model
must follow all of it exactly, every delegation. That has three consequences:

1. **Untestable.** No test can assert that a rule is obeyed, only that its text
   is present — and this repo has now been bitten twice by assertions that
   matched text while the behavior drifted (hence §6c).
2. **Unenforced.** Round caps, fallback-once-per-role, and the reuse filter are
   *instructions*. Today the orchestrator recorded a `pi_reuse` event for two
   agents that no longer existed, because §2's "check status, then record"
   ordering is prose a model can transpose under load.
3. **Unportable.** A second backend would mean duplicating all 859 lines.

This contract splits the loop so that mechanism is executed and judgment is
prompted.

## 1. The arbiter rule

> **If a step needs a good model, it stays prose. If a step must be true
> regardless of which model is driving, it becomes a program that exits
> non-zero.**

Apply this rule to settle every future question about what belongs in
`bin/crew`. It is the single test that keeps `bin/crew` from growing into a
shell script that makes decisions, and keeps the skill from re-absorbing
mechanism.

### Classification of every current section

| § | Concern | Disposition |
|---|---|---|
| 0b | Resolve `DOMAIN` (order, fail-loud on six sections) | **mechanism** |
| 0 | Precondition (`HERDR_ENV`, server running) | **mechanism** — becomes `crew doctor` |
| 1 | Classify tier | **judgment** |
| 1 | Profile resolution, 3 sources, absent-vs-malformed | **mechanism** |
| 1 | `DELEGATION_ID` + per-role session ids | **mechanism** |
| 2 / 3 / 3b | Resolve or spawn worker / reviewer / tester, reuse filter, layout, profile verification, spawn+reuse telemetry | **mechanism** |
| 4 | Send prompt; poll to settlement | **mechanism** |
| 4 | *What* the prompt says | **judgment** |
| 5 | Detect `blocked`; detect a `POLICY.md` class | **mechanism** |
| 5 | Answer the question, or escalate | **judgment** |
| 6 | Read output; detect rate-limit signature | **mechanism** |
| 6 | Judge goal met / not met against the artifact | **judgment** |
| 6a | Parse the verdict literal; retry once on non-compliance; count the round | **mechanism** |
| 6a | Compose the review request; decide what to relay | **judgment** |
| 6b | Tester verdict parsing and control flow | **mechanism** |
| 6b | Write the test plan | **judgment** (never delegated) |
| 6c | Detect the trigger (diff touches tests/assertions); record both exit codes | **mechanism** |
| 6c | Choose the mutation; judge whether the gate is satisfied | **judgment** |
| 7 | Fallback: once per role, respawn, re-verify profile, telemetry | **mechanism** |
| 8 / 9 | Round cap 5 / turn cap 6; no-progress detection | **mechanism** |
| 10 | Spawn/close a scout, layout, telemetry | **mechanism** |
| 10 | *Whether* a scout is worth spawning, and its question | **judgment** |
| 11 | Run the pack's verify command | **mechanism** |
| 11 | Read the artifact and form a verdict | **judgment** |
| 12 | Emit `pi_delegation_end`; assemble the facts | **mechanism** |
| 12 | Write the report | **judgment** |

Target: `SKILL.md` under 250 lines, containing only the **judgment** rows plus
the `bin/crew` invocations that carry the mechanism rows.

## 2. The Turn Contract

Every backend maps its native signals onto exactly **four** outcomes. This is
the interface the whole loop is written against.

| Outcome | Meaning |
|---|---|
| `settled` | The agent finished a turn; its output is available |
| `blocked` | The agent is waiting on an answer |
| `failed` | Rate-limit / quota / usage failure, or the process died |
| `timeout` | No settlement inside the budget |

### Backend mappings

| Outcome | `herdr` | `batch` (one-shot subprocess) |
|---|---|---|
| `settled` | `agent_status` ∈ {`idle`,`done`} per §3's debounce | exit 0 |
| `blocked` | `agent_status` = `blocked` | exit 0 **and** output contains the `QUESTION:` sentinel |
| `failed` | output matches the rate-limit signature | non-zero exit, or signature match |
| `timeout` | poll budget exhausted | wall-clock kill |

### Settle detection — preserve exactly

These rules were established live and cost real debugging. `crew wait` must
implement them and a test must pin them.

- **All three** of `idle`, `done`, `blocked` are settled candidates. A
  hook-authority `pi` reports `idle` and never `done`; a screen-scraped one can
  do the reverse. Detection mode is per **process**, not per agent name.
- **Normal path:** after submitting a prompt, observe a **non-settled** status,
  then **3 consecutive** settled readings at a **5s** interval.
- **Escape hatch:** if no non-settled status is ever observed, accept only after
  **60s** of continuously settled readings, and **report that this path was
  taken** so the caller knows freshness was inferred, not observed.
- Default per-turn timeout **600s**, caller-overridable.
- Rationale that must survive in a comment: confirmed live twice, an immediate
  status read after submit returned the *previous* turn's `idle`/`done` while
  the pane showed `Working…`. A single settled reading can therefore surface a
  stale prior response — including a stale reviewer `APPROVED`.

### Rate-limit signature

Case-insensitive substring match on any of: `rate limit`, `429`,
`quota exceeded`, `insufficient_quota`, `usage limit reached`. No other failure
type routes to fallback.

## 3. Mux adapter interface

An adapter is an executable taking the verb as `$1`. All structured output is
JSON on stdout; diagnostics on stderr; non-zero exit means the verb failed.

```
crew_capabilities   -> {"layout":bool,"focus":bool,"persistent_context":bool,
                        "native_status":bool,"banner":bool,"isolation":bool}
crew_list           -> [{"id":str,"name":str|null,"cwd":str,"status":str}]
crew_spawn NAME CWD [--stack-under ID] -- ARGV...   -> {"id":str}
crew_status ID      -> settled|working|blocked|failed|unknown
crew_send ID        (prompt text on stdin)
crew_read ID [--recent|--visible] [--lines N]       -> text on stdout
crew_close ID
crew_verify_profile ID PROVIDER MODEL THINKING      (exit 0 = matched)
```

**Capability degradation is explicit, never silent.** If an adapter reports
`native_status: false`, `crew wait` uses a sentinel marker the orchestrator asks
the agent to emit, and says so in its output. If `banner: false`,
`crew_verify_profile` returns a distinct "cannot verify" exit code and `crew
spawn` warns — it must not silently report a verified profile it never saw.

### Amendment (2026-08-11): synchronous backends

A backend need not host a long-running agent. `batch` runs **one subprocess per
turn**, which the original verb list assumed away. The adaptation is fixed here
so no adapter has to invent it:

- `crew_send` **runs the turn** and buffers its result.
- `crew_status` reports `settled` once that has happened.
- `crew_read` returns the buffered output.

The loop above does not change: it still sends, waits, and reads. Only the
adapter knows the work happened during `crew_send`.

`crew_status` must never report `settled` for a synchronous backend before
`crew_send` has run, or a caller could read a previous turn's buffer — the same
stale-read hazard §2's debounce exists to prevent, in a different costume.

### Amendment (2026-08-11): `persistent_context`

`persistent_context: false` means each turn starts with **no memory of the last
one**. The orchestrator must then re-supply the plan, the ledger and the current
artifact state in **every** prompt.

This is a capability-driven branch in the skill, and it is the right shape under
the arbiter rule: *whether* to re-supply is mechanical — read the capability —
while *what* to re-supply is judgment and stays prose. An orchestrator that
ignores this flag on a stateless backend will send follow-ups referring to
context the agent never had, and the agent will confabulate around the gap
rather than report the loss.

`QUESTION:` is the sentinel that maps a synchronous turn onto `blocked`: exit 0
with that marker in the output means the agent is waiting on an answer. It is
also the marker used for sentinel settlement when `native_status: false`.

### Adapters to ship

- **`herdr`** — reference implementation, today's behavior verbatim.
- **`mock`** — replays scripted outcomes from a fixture. **A deliverable, not a
  test helper:** it is what lets CI exercise the whole loop with no agent and no
  multiplexer installed.
- `tmux`, `zellij`, `batch` — Phase 3 and later.

### `herdr` specifics the adapter owns, and the loop must never see

- Target by **`pane_id`**, never the free-form name: `herdr agent *` tolerates
  names, `herdr pane *` rejects them with `pane_not_found`.
- Send is **two steps** — `agent send` types, `pane send-keys enter` submits.
  Skipping the second leaves the prompt unsent forever.
- Stacking uses **focus → `agent start --split down --no-focus` → restore
  focus**, because `--split` acts on the *focused* pane and `--no-focus` does not
  restore prior focus. Never `pane split` + `pane run`: panes created that way
  never appear in `agent list` at all.
- Profile verification requires **zoom → read → unzoom**, because narrow panes
  truncate the status bar horizontally and `recent-unwrapped` cannot recover it.
- `opencode-go` deepseek models silently run at `high` for any intermediate
  `--thinking` value; only `off` and `high` are honored.

## 4. Worker adapter interface

Separate axis from the mux: *which agent* runs inside the pane or subprocess.

```
worker_argv PROVIDER MODEL THINKING SESSION_ID SKILL_ROOTS -> argv on stdout
worker_banner_pattern                                      -> regex on stdout
worker_capabilities -> {"isolation":bool,"session_resume":bool}
```

`pi` is the reference implementation, wrapping today's `bin/pi-project`.

**The isolation guarantee travels with the adapter.** An adapter that cannot
restrict its agent to repo-local skills must report `isolation: false`, and
`crew spawn` must warn loudly — without it, results stop being reproducible
across machines, which is most of why this pattern is distributable at all.

## 5. `bin/crew` CLI surface

```
crew doctor                                  # §0 precondition + adapter presence
crew begin --tier T --domain D [--goal-file F]    -> {"delegation_id":...}
crew spawn --role worker|reviewer|tester|scout [--stack-under ID]
                                             -> {"id":...,"reused":bool,"profile":{...}}
crew send   --role R                         # prompt on stdin
crew wait   --role R [--timeout S]           -> {"outcome":...,"path":...,"output":...}
crew read   --role R [--recent|--visible] [--lines N]
crew close  --role R
crew fallback --role R                       # enforces once-per-role
crew round  end --verdict approved|changes_requested|tester_pass|tester_bugs
                                             # NON-ZERO at the cap
crew turn   end                              # S-tier; NON-ZERO at the cap
crew ledger append <text>
crew state                                   -> full state JSON (compaction recovery)
crew classify-risk                           # question on stdin -> matched POLICY class or none
crew verify                                  # runs the resolved pack's verify command
crew end    --outcome goal_met|escalated|stuck
```

Roles are addressed by name, not by opaque id — the caller should never handle a
`pane_id`. `crew` resolves role → id from its own state.

### Amendment (2026-08-10): carrying the delegation id

The original surface said nothing about how a later command identifies its
delegation. 2b's first implementation used a single `.factory/crew/current`
pointer, which review correctly rejected because two concurrent delegations in
one repo would clobber each other — a live problem here, not a theoretical one.
Its replacement required an undocumented `FACTORY_CREW_DELEGATION_ID`
environment variable, which `crew begin` never mentioned, so the CLI was
unusable as a sequence.

Settled: **every subcommand accepts `--delegation-id`**, with the environment
variable as a fallback, and `crew begin` states explicitly how to carry the id
forward. State remains addressed per delegation id, never through a shared
mutable pointer.

### Amendment (2026-08-10): adapters must model the real protocol

Phase 2c's stub returned response shapes the real backend does not use. Ten
mutation-verified assertions passed while the adapter crashed on the first live
call. The lesson is now a contract requirement:

- An adapter's test double **must** reproduce the real backend's response
  shapes, including nesting, and its **empty-output** verbs.
- Protocol details discovered live — response nesting, which verbs return no
  output, whether a value is rendered synchronously — belong in the backend's
  reference file the moment they are learned.
- **A stub that lies makes every assertion built on it worthless**, however
  rigorously those assertions are mutation-tested. Mutation testing proves an
  assertion is sensitive to the code; it cannot prove the fixture resembles
  reality. Only a live run does that, which is why §9's mock-only suite is
  necessary but never sufficient for a real backend adapter.

### Amendment (2026-08-10): `crew classify-risk`

Added after Phase 2b's review found that §7's `POLICY.md` invariant had **no
home in this surface** — §1 classifies risk-gate *detection* as mechanism, but
the original CLI listing gave it no verb, so the invariant was unimplementable
as specified. That was a defect in this contract, not in the implementation.

`crew classify-risk` reads a blocked agent's question on stdin and reports which
`POLICY.md` category it matches, if any, additively with the resolved domain
pack's own **Risk gate** section. It **only classifies**. Whether to answer the
question or hand control to the human stays judgment and stays in the skill —
consistent with the arbiter rule in §1.

Wiring it is deferred to the delegation that rewrites the skill (2e), where the
escalation prose lives. Until then, §7's `POLICY.md` row is knowingly unpinned
and must be reported as such rather than quietly dropped.

**Cap enforcement is the point.** `crew round end` at the cap exits non-zero
with an escalation payload. A caller that ignores the exit code cannot silently
continue looping, because `crew send` refuses to run once the state is
`escalated`.

## 6. State

`.factory/crew/<DELEGATION_ID>/state.json`, anchored via
`$(cd -- "$(dirname -- "$(git rev-parse --git-common-dir)")" && pwd -P)` so
linked worktrees share one directory. Sibling `progress.md` remains the
human-readable ledger.

```json
{
  "delegation_id": "…",
  "tier": "S|M|L",
  "domain": "software|research|…",
  "mux": "herdr",
  "worker": "pi",
  "crew_mode": true,
  "round": 2,
  "turn": 0,
  "state": "running|escalated|done",
  "roles": {
    "worker":   {"id": "w1Y:p8", "session_id": "…-worker",   "fallback_used": false},
    "reviewer": {"id": "w1Y:p9", "session_id": "…-reviewer", "fallback_used": false}
  },
  "diff_hashes": ["sha…", "sha…"],
  "last_verdict": "changes_requested"
}
```

`diff_hashes` holds the last two artifact hashes, making §8's "two consecutive
rounds produced no meaningful change" a computed condition rather than a
remembered one. `crew state` replaces the prose instruction to reconstruct
position from the ledger after compaction.

## 7. Invariants that must not regress

Each was established by a specific fix. A test must pin each one.

| Invariant | Origin |
|---|---|
| Linked worktrees share one ledger and one telemetry log | `2431422`, `4111aee` |
| Telemetry sink derives from the **script's** repo, never the caller's cwd | Phase 1d |
| Each role gets its own session id; the scout gets a fresh one **per spawn**; the bare `DELEGATION_ID` is never a session id | `1a1f589`, `9be72d9` |
| Debounced settle detection with the reported escape hatch | `b17c80b`, `11e0721` |
| Reuse only an agent matching role **and** tier **and** cwd, and never an unnamed one | §2 |
| Fallback fires at most once **per role**; roles are independent | §7 |
| Round cap 5, turn cap 6 | §8, §9 |
| Profile resolution: absent → skip, exists-but-malformed → **stop** | Phase 1b |
| Verdict literals are exact; non-compliance retries **once** and does not consume a round | §6a |
| The crew never performs an outward-facing action | authority boundary |
| Risk gate reads from `POLICY.md`; packs and local overlays may add, never weaken | Phase 1a |

## 8. Selection and fail-loud

`FACTORY_MUX` / `FACTORY_WORKER`, defaulting to `herdr` / `pi`. An unknown or
missing adapter, a missing verb, or a malformed capability document **stops and
names the defect**. Never fall back to another adapter; never improvise a
capability.

## 9. Testing the contract

The `mock` adapter must make all of these runnable with no agent installed:

- cap enforcement — `crew round end` non-zero at round 6; turn cap at 7
- no-progress — two identical `diff_hashes` halt the loop
- fallback — once per role; second failure for the same role escalates; a
  different role is unaffected
- reuse — refuses another tier's agent and any unnamed agent
- settle detection — stale-settled status rejected; escape-hatch path reported
- state recovery — `crew state` reports the correct round after an interrupted
  round
- telemetry — all eight events emit, each carrying `domain=`
- selection — unknown adapter fails loudly and names the defect

Per §6c, each of these tests must be shown to **fail** against a mutation of the
rule it protects. A green suite is not evidence.

## 10. Out of scope

- Any behavior change. Phase 2's gate is indistinguishability: the same S- and
  M-tier goals must produce the same panes, ledger, rounds, telemetry and report.
- Adapters beyond `herdr` and `mock` (Phase 3).
- Renaming `pi-isolated-<role>-<TIER>` → `crew-<role>-<TIER>` happens in 2e, and
  invalidates reuse of any agent running under the old name. Report it; do not
  let it be discovered.
- Giving any crew member an outward-facing tool — permanently out of scope.
