# Software Factory

One flagship orchestrator, a small crew of cheap workers, bounded loops, and a
**mechanical failure signal** for every deliverable.

You talk to one agent. It plans with you, delegates the work to a crew, verifies
the result against something that can actually fail, and comes back when it is
done or genuinely stuck. It never implements the work itself, and it never
reports success it has not checked.

Works with [Claude Code](https://claude.com/claude-code) as the orchestrator.
Not affiliated with or endorsed by Anthropic.

---

## The three claims worth reading

**1. Unsupervised loops need an oracle.** An agent loop with no mechanical
failure signal produces confident, well-formatted, wrong output — at scale, at
cost. So every domain pack must supply a **verify command that exits non-zero on
failure**, and every deliverable an acceptance spec whose criteria are labelled
`mechanical`, `sourced`, or `rubric`. A deliverable whose criteria are *all*
rubric-class **does not get an unsupervised stretch** — you add a human
checkpoint or cut it from scope. That rule is the difference between a build
pipeline and a slop pipeline.

**2. Workers see only the skills this repository ships — where the adapter can
enforce it.** Not what happens to be installed on your machine. That is what makes
the same repository behave the same way for two different people.

It is not universal, and the gap is declared rather than hidden: the `pi` adapter
enforces isolation via `bin/pi-project`; the `claude` adapter **cannot** — `claude
--bare` skips hooks and plugins but skills still resolve — so it reports
`isolation: false`, `factory doctor` prints "results are not reproducible across
machines", and `crew spawn` warns every time. Claiming isolation you cannot
provide is worse than documenting the gap.

**3. Whether this earns its cost is measured, not asserted.** The loop records
spawns, rounds, verdicts, cap hits and outcomes by domain and tier. Numbers from
this project building itself are in [`docs/COST.md`](docs/COST.md) — software
work converged in a median of 3 rounds, and the round cap fired 5 times — every
one halting the loop for a human decision rather than grinding on.

The reasoning behind all of it is in [`MANIFESTO.md`](MANIFESTO.md).

## Quickstart

```bash
git clone <this repo> && cd software-factory
bin/factory doctor          # what is available, and what degrades
```

`doctor` tells you which adapters it can find, which profile table resolves, and
**which capabilities are missing** — not a green checkmark that hides a gap.

Then scaffold a workspace and start a goal. Note the `cd` — `factory run`
inspects the **current directory**, so it must be run from inside the workspace,
using an absolute path to `factory`:

```bash
FACTORY=$PWD/bin/factory
$FACTORY init ../my-goal --domain software   # WORKSPACE.md, acceptance.md, .gitignore
cd ../my-goal
$FACTORY run                                  # validates, then prints what to invoke
```

`run` deliberately does **not** drive the loop. It checks that the workspace,
pack, adapters and profile table are all usable, then hands you the exact
command. The loop belongs to the `orchestrate` skill and `bin/crew`.

The loop itself runs as a Claude Code skill: `/orchestrate <goal>` for a single
delegation, or `/autonomous-goal <idea>` to go from idea to delivery with three
human checkpoints — plan approval, risk gate, final delivery — and nothing else
interrupting.

## What you need

| | |
|---|---|
| **Orchestrator** | Claude Code |
| **Workers** | any of: `pi` (reference), `claude` |
| **Multiplexer** | `herdr` for live panes you can watch, or **none at all** |
| **Runtime** | Python 3.9+, `git`, `jq`, `rg` |

The `batch` backend needs no multiplexer: each turn is one subprocess. That is
the five-minute path — `claude` on your `PATH` and nothing else. `herdr` + `pi`
is the richer experience, where every crew member is a live pane you can watch
and take over.

## How it fits together

```
              you
               │
        orchestrator  (Claude Code — plans, judges, escalates, reports)
               │
     ┌─────────┴─────────┐
 domain pack          bin/crew
 what "done" and      spawn · send · wait · caps · ledger · telemetry
 "verified" mean      (enforced: exits non-zero, not "please remember")
                          │
                    ┌─────┴─────┐
                  mux         worker
              herdr│batch    pi│claude│mock
```

Two independent axes. A **domain pack** decides what a good result is —
`software` and `research` ship. A **backend** decides how a worker is driven.
Neither knows about the other.

The split that matters is inside the orchestrator: judgment stays prose, and
mechanism is a program that exits non-zero. Caps, reuse rules and settle
detection used to be instructions in an 859-line document; they are now
`bin/crew`, and the document is 126 lines of the decisions that actually need a
good model.

## Domains

| Pack | Deliverable | Oracle |
|---|---|---|
| `software` | code | your tests, plus a tester that runs the program |
| `research` | a report | `bin/verify-research` — every claim's citation resolves, every excerpt occurs verbatim in a stored snapshot, every snapshot hash matches, every derived number recomputes |

`research` is the interesting one, because it shows the pattern working where
there is no test suite: fabricated sources, drifted quotes and invented
arithmetic fail **mechanically, without a human**.

Writing your own pack is the main extension point — see
[`CONTRIBUTING.md`](CONTRIBUTING.md), which leads with the oracle problem because
a pack without a real verify command turns this into a very expensive way to
generate plausible text.

## The boundary

**The crew produces artifacts. The orchestrator performs outward-facing
actions.** No worker gets email, chat, tickets, publishing or payments. One
worker needing an outward action reports it and a human decides.

`POLICY.md` ships with the repository and defines the risk gate. A local
`POLICY.local.md` and a pack's own risk gate may **add** prohibitions; neither
can weaken one.

## Status

Honest about maturity: the control loop, both domain packs, four backends and the
test suite are real and used daily. Rough edges: `n` is small in `docs/COST.md`,
the `claude` worker cannot provide skill isolation, and `tmux`/`zellij` adapters
are unwritten.

## Licence

MIT. Bundles the [`superpowers`](https://github.com/obra/superpowers) skill set
(v6.2.0, MIT, unmodified) — see `.claude/skills/THIRD_PARTY_NOTICES.md`.
