# Open-source fork: a general-purpose agent factory

## Purpose

Extract the working pattern in this repo — **one flagship orchestrator, many
cheap workers, bounded loops, mechanical oracles** — into a public project that
a stranger can install and use, on their own agents, for their own domains.

Four decisions are settled and drive everything below:

| Decision | Choice |
|---|---|
| Scope | Domain-general **and** backend-general |
| Fork model | The public repo is **upstream**; this repo becomes a private downstream overlay |
| In-flight work | Finish and merge `feat/domain-packs` here **first** |
| Dependencies | `pi` and `herdr` are public, so they stay a first-class backend — but not the only one |

Working name: **`agent-factory`** (final naming is a launch-time decision, not a
blocker; every path below uses it as a placeholder).

## The thesis being open-sourced

The differentiator is not "multi-agent orchestration" — that is a crowded
category. It is the set of constraints that make an *unsupervised* stretch
trustworthy. These become the project's `MANIFESTO.md`, and each one is already
load-bearing somewhere in this repo:

1. **One human-facing agent.** The human talks to the orchestrator only. Crew
   members never address the human. (`delegate-to-pi` §5 escalation.)
2. **The orchestrator never implements.** It plans, verifies, integrates.
   (`CLAUDE.md` rule 1.)
3. **Self-reports are not evidence.** Every claim of done is checked against the
   artifact itself. (§6, §11.)
4. **The reviewer is a separate process reading the shared worktree** — never a
   summary pasted into a prompt. (§6a: "never paste the diff into the prompt".)
5. **The oracle problem.** A loop without a mechanical failure signal produces
   plausible slop at scale. Hence the acceptance spec, the per-pack verify
   command, and the **rubric-only rule**. (domain-packs design.)
6. **The tester leaves the diff and touches reality.** Run the program;
   re-open the primary source. (§6b and its research analog.)
7. **Bounded loops, then escalate.** Round caps, turn caps, no-progress
   detection — never infinite retry. (§8, §9.)
8. **Fail loud, never improvise.** Missing profile table or missing pack
   section stops the run and shows the user the exact defect. (§1, pack loader.)
9. **Skill isolation.** Workers see exactly the skills the repo ships and
   nothing from the operator's machine, so the same repo behaves the same way
   for every user. (`bin/pi-project`.) This is what makes the pattern
   *distributable* at all.
10. **Tier the model to the goal**, and confirm once before the top tier.
11. **Exactly three human checkpoints:** plan, risk, delivery.
12. **Telemetry is the evidence** that the pattern earns its cost.

Points 5, 9 and 12 are the ones no comparable project has. They should lead the
README.

## Architecture

### Two axes, not one

Today `delegate-to-pi` hard-codes two independent things into one prose
procedure: *what a good result is* (software-shaped) and *how to drive a worker*
(herdr + pi shaped). The fork separates them:

```
                 orchestrator (Claude Code, flagship, high thinking)
                            judgment: classify, prompt, verify, escalate
                                          │
                 ┌────────────────────────┴────────────────────────┐
                 │                                                 │
          domain pack                                        crew backend
   what "done" and "verified" mean                  how to spawn/send/poll/read
                 │                                                 │
   packs/software.md                                adapters/mux/{herdr,tmux,batch,mock}
   packs/research.md                                adapters/worker/{pi,claude,codex,aider}
   packs/writing.md  packs/ops.md
```

`DOMAIN` and `BACKEND` are both settled once per delegation, are orthogonal to
each other, and are orthogonal to `TIER` (which still selects a model profile
from one table).

### The mechanism/judgment split

**This is the central engineering change and the precondition for everything
else.** The control loop is currently ~730 lines of prose that a model must
follow exactly. That is untestable, unenforceable, and impossible to port to a
second backend without duplicating all of it.

Split it:

| Stays prose (model judgment) | Becomes a program (`bin/crew`) |
|---|---|
| Classify tier and domain | Spawn/reuse by role+tier+cwd |
| Compose the goal and follow-up prompts | Send, poll, settle detection |
| Read the diff and judge goal-met | Round/turn counting and cap enforcement |
| Decide whether a `blocked` question escalates | Ledger writes |
| Decide when a scout is worth spawning | Telemetry emission |
| Write the acceptance spec and test plan | Rate-limit fallback and respawn |
| Report to the human | Pane layout and stacking |

The prose keeps every decision that needs a good model. The program keeps
every rule that should be *enforced* rather than *instructed* — matching the
existing house preference for mechanical enforcement over prose. Target:
`SKILL.md` drops from ~730 lines to under 250.

### The Turn Contract

Every backend maps its native signals onto exactly four turn outcomes. This is
the interface the whole loop is written against:

| Outcome | Meaning | herdr mapping | batch mapping |
|---|---|---|---|
| `settled` | Worker finished a turn; output available | `agent_status` ∈ {idle, done} | process exit 0 |
| `blocked` | Worker is asking a question | `agent_status` = blocked | exit 0 + `QUESTION:` marker |
| `failed` | Usage/rate-limit/crash | output matches §7 signature | non-zero exit, or §7 signature |
| `timeout` | No settlement inside the budget | poll budget exhausted | wall-clock kill |

### The crew backend interface

An adapter is a shell script implementing eight verbs. Anything it cannot do
it declares in `capabilities`, and the loop degrades explicitly rather than
silently:

```
crew_capabilities            -> json: {layout, focus, persistent_context, native_status, banner}
crew_list                    -> json: [{id, name, cwd, status}]
crew_spawn NAME CWD [--stack-under ID] -- ARGV...   -> json: {id}
crew_status ID               -> settled|working|blocked|failed|unknown
crew_send ID <text-on-stdin>
crew_read ID [--recent|--visible] [--lines N]  -> text
crew_close ID
crew_verify_profile ID PROVIDER MODEL THINKING      -> exit 0/1
```

Ship five mux adapters:

- **`herdr`** — today's behavior, verbatim. Persistent context, real panes, the
  human can watch and take over. The premium experience.
- **`tmux`** — same shape, no native agent status: settle detection falls back
  to a sentinel marker the orchestrator asks the worker to emit.
- **`batch`** — **no multiplexer at all.** Each turn is one subprocess
  invocation of a one-shot agent (`claude -p`, `codex exec`, `aider --message`);
  settle = exit. Context is re-supplied from the ledger, plan and diff each
  turn rather than accumulated in a session.
- **`zellij`** — community-shaped, same contract as tmux.
- **`mock`** — scripted responses from a fixture file, so CI exercises the
  entire control loop with **no agent and no multiplexer installed**.

`batch` and `mock` matter more than they look. `batch` is what lets a stranger
try the project in five minutes with only `claude` on PATH. `mock` is what
makes the loop testable at all.

### Worker adapters

Separate from the mux: which agent runs inside the pane or subprocess. Each
supplies its argv (including how to pin provider/model/thinking, how to load
*only* repo-local skills, and how to set a session id) plus the banner regex
`crew_verify_profile` matches. `pi` is the reference implementation and is
exactly today's `bin/pi-project`, generalized.

**The skill-isolation guarantee travels with the adapter.** An adapter that
cannot restrict the worker to repo-local skills must declare
`isolation: false`, and the orchestrator must warn at spawn — because without
it, results stop being reproducible across machines and half the value is gone.

### Domain packs

Adopt the six-section contract from the domain-packs design unchanged
(workspace layout, verify command, reviewer rubric, risk gate, roles,
definition of done), plus the acceptance spec and the rubric-only rule. Two
additions for the public project:

- A machine-checkable front-matter header so `bin/factory doctor` can validate
  a pack without a model reading it.
- `packs/PACK-AUTHORING.md`, since community packs are the natural
  contribution surface and the *only* thing standing between a pack and a slop
  generator is whether its author understood the oracle problem.

Ship `software` and `research` as blessed in v1.0. `writing` and `ops` ship in
v1.1, **after** each has been run on one real goal — the domain-packs design
deliberately deferred them for this reason, and shipping an unproven pack
would contradict the project's own central argument.

### Portability defects to fix before extraction

Three things work here only because of this machine:

1. **`POLICY.md`.** `delegate-to-pi` §5 and `autonomous-build` Step 4 both
   defer to "the user's global CLAUDE.md Never/Off-limits rules". A stranger
   has no such file, so the risk gate silently has no content. The fork needs a
   repo-level `POLICY.md` shipping sane defaults (destructive git/fs ops,
   secrets, production systems, outward-facing sends), which local config may
   extend but never weaken.
2. **Profile table.** `pi-profiles.json` names providers the user happens to
   have. Ship `config/profiles.example.json` plus a documented local-override
   path, and make `factory doctor` report which profiles are actually reachable.
3. **Ledger path.** `.factory/crew/<id>/` borrows a vendored package's
   namespace. Rename to `.factory/crew/<id>/`.

### Authority boundary

Kept verbatim and promoted to a top-level invariant: **the crew produces
artifacts; the orchestrator performs outward-facing actions.** No worker gets
an email, Slack, ticket, publish, or payment tool. In the public project this
also becomes a documented security property, because it is the answer to the
first question any reviewer will ask about running a crew of agents unattended.

## Phased plan

Each phase has a gate. No phase starts before the previous gate is green.

### Phase 0 — land what is in flight (private repo)

- Merge `fix/crew-session-isolation`.
- Finish and merge `feat/domain-packs` (pack loader, `bin/verify-research`,
  `autonomous-goal`, telemetry `domain=` field).
- Execute the domain-packs testing plan, including one real research goal
  end to end.

**Gate:** full existing suite green; one S-tier and one M-tier software goal
and one research goal complete on today's stack.

### Phase 1 — portability surgery (private repo, still)

Fix the three defects above, strip absolute home-directory paths from docs, and
split `.claude/settings.json` into a shippable minimum plus a local overlay.

**Gate:** suite green; no file in the tracked tree contains a home-directory
path or a machine-specific assumption.

### Phase 2 — extract the mechanism

Build `bin/crew` + `lib/crew/` against the Turn Contract, with the `herdr` mux
and `pi` worker adapters as the reference implementation. Add the `mock`
adapter and CI coverage of the loop itself: cap enforcement, no-progress
detection, fallback-once-per-role, verdict-parse retry, ledger recovery after
compaction. Rewrite `delegate-to-pi` as `orchestrate` calling `bin/crew`.

**Gate — behavior preservation:** the same S-tier and M-tier goals from Phase 0
produce indistinguishable panes, ledger, round counts, telemetry and report.
Plus: the loop's cap and fallback rules are now covered by tests that run with
no agent installed.

### Phase 3 — a second backend proves the abstraction

Implement `batch` mux + `claude` worker. An abstraction with one implementation
is a guess.

**Gate:** one S-tier and one M-tier software goal complete end to end with
`herdr` and `pi` **not installed**.

### Phase 4 — cut the public repo

New public repo, MIT (compatible with the vendored superpowers set; keep
`THIRD_PARTY_NOTICES.md` and pin the version with a documented sync procedure).
Initial commit is a curated, sanitized tree — but **ship `docs/specs/`**: the
design documents are the teaching material and are most of why anyone would
trust the project.

Then invert this repo: it becomes a fork of upstream with an `upstream` remote,
holding only `local/` (gitignored profile overrides, `.projects/`, `var/`) and
`POLICY.local.md`. Improvements flow one way — write them upstream, pull down.

**Never leaves this machine:** `var/telemetry/events.jsonl` (it stores verbatim
user prompts), `.projects/`, real profile tables, `.claude/settings.json`
plugin/skill overrides, and the axi/lavish hooks.

**Gate:** a fresh clone on a clean machine passes CI and `factory doctor`.

### Phase 5 — make it usable by a stranger

`bin/factory init|doctor|run`, `README.md`, `MANIFESTO.md`, two runnable
`examples/`, `CONTRIBUTING.md` (adapters and packs are the contribution
surface; the control loop is not), a cost note backed by real telemetry, and
the `writing` + `ops` packs once each has a real goal behind it.

**Gate — v1.0:** a stranger with only `claude` on PATH goes from clone to a
completed example goal in under fifteen minutes, without reading the specs.

## Risks

| Risk | Mitigation |
|---|---|
| **Prose-loop fidelity** — a 730-line procedure is followed approximately, not exactly | Phase 2 is precisely this fix; caps and fallback become enforced, not instructed |
| **Cost** — crew mode burns 2–4 worker sessions per goal | Publish real rounds-to-converge and cost-per-goal from telemetry; keep S-tier single-worker as the default for small work |
| **Slop packs** — a community pack with an all-rubric acceptance spec turns the loop into a confident-nonsense generator | The rubric-only rule is mechanically enforced by `factory doctor`, not just documented; `PACK-AUTHORING.md` leads with the oracle problem |
| **Upstream drift** in `pi` / `herdr` / vendored superpowers | Pin tested versions; `factory doctor` warns on untested versions; adapters absorb CLI changes in one place |
| **Maintenance load** | Contribution surface is adapters and packs only; the control loop stays owned |
| **Naming and endorsement** | "Works with Claude Code"; no Anthropic branding, no implied endorsement |

## Out of scope for v1.0

- Any orchestrator other than Claude Code (the pattern assumes a flagship model
  with high thinking effort doing the judgment; a weaker orchestrator changes
  the safety argument entirely).
- Giving crew members outward-facing tools — permanently out of scope.
- A hosted or multi-machine control plane.
- Cross-domain workspaces; one workspace declares one domain.
