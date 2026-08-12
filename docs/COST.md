# What this costs, measured

Every number here comes from `var/telemetry/events.jsonl` recorded while this
project built itself — the orchestrator driving Pi crews through Phases 0–5.
**The log is local-only and gitignored**, so `var/telemetry/events.jsonl` does
not exist in a fresh clone. The command below runs against *your own* log once
you have used the factory — it will not reproduce these exact numbers, which are
from this project's build.

`bin/telemetry-report` gives the event summary, but it does **not** compute
medians, maxima, or cap-hit counts. Those were derived directly from the event
log, and this is the exact command that produces the tables below:

```bash
python3 - <<'PY'
import json, collections
rounds = collections.defaultdict(list); outcomes = collections.Counter()
dom = {}; per = collections.defaultdict(int); caps = set(); ends = {}
for line in open('var/telemetry/events.jsonl'):
    line = line.strip()
    if not line: continue
    try: r = json.loads(line)
    except ValueError: continue
    e, t, d = r.get('event'), r.get('trace_id'), r.get('domain')
    if e == 'pi_crew_round_cap_hit': caps.add(t)
    if not t: continue
    if d: dom[t] = d
    if e == 'pi_crew_round':
        per[t] = max(per[t], int(r.get('round') or 0))
    if e == 'pi_delegation_end':
        outcomes[(dom.get(t, '?'), r.get('outcome'))] += 1
        ends[t] = r.get('outcome')
for t, n in per.items(): rounds[dom.get(t, '?')].append(n)
for d, v in sorted(rounds.items()):
    v = sorted(x for x in v if x)
    if v: print(d, 'n=%d min=%d median=%d max=%d' % (len(v), v[0], v[len(v)//2], v[-1]))
for k, n in sorted(outcomes.items()): print(k, n)
print('cap hits:', len(caps))
for tid in caps: print('  cap-hit delegation ended:', ends.get(tid, '(none)'))
PY
```

Making `bin/telemetry-report` compute these directly is an open task; until it
does, the command above is the reproduction path.

The log itself is never published; it records verbatim user prompts.

## Rounds to converge

A *round* is one worker turn plus one reviewer verdict. Crew mode caps at 5.

Snapshot taken 2026-08-12. The log grows with every delegation, so re-running the
command above will show a larger `n` than the table — that is expected, and the
table is a point-in-time figure rather than a live one.

| Domain | Delegations | Min | Median | Max |
|---|---|---|---|---|
| software | 13 | 1 | **3** | 6 |
| research | 1 | 4 | 4 | 4 |

## Outcomes

| Domain | `goal_met` | `escalated` | `stuck` |
|---|---|---|---|
| software | 54 | 3 | 3 |
| research | 1 | 0 | 0 |

The round cap was hit **5 times**. Four of those delegations ended `escalated`.
The fifth also stopped and escalated, was then given explicit human authorisation
for one further round, and completed — so its recorded outcome is `goal_met`.

That is the cap working, not failing: in every case the loop halted and a human
decided whether to continue. Note the distinction, because the recorded outcome
alone does not tell you a cap was hit — you have to join `pi_crew_round_cap_hit`
to `pi_delegation_end` by `trace_id`, which the command above does.

## What that means in practice

- **Budget 3 rounds for ordinary multi-file work**, and expect the occasional 6.
  A single-round delegation is a well-specified one; a 5-round delegation almost
  always means the brief was ambiguous, not that the work was hard.
- **Crew mode roughly triples per-goal agent cost** versus a single worker: a
  worker, a reviewer, and the orchestrator's own verification. `S`-tier skips the
  reviewer for exactly this reason — do not pay for crew mode on a typo.
- **The reviewer earns its cost.** In this project's build the reviewer caught,
  among others: a shared-authorship claim that invalidated a source-independence
  argument, a test that passed both before and after the behaviour it protected
  was broken, nine assertions claimed as migrated that were not, and a risk
  classifier that confidently cleared "drop the production users table."

## The honest caveat

`n` is small, it is one operator on one codebase, and the domain distribution is
lopsided — 13 software delegations against 1 research. Treat the software median
as a planning figure and the research number as a single data point.

The reason the numbers are published at all is that the alternative — asserting
that an agent crew is worth its cost — is exactly the kind of unfalsifiable claim
this project's own oracle rule exists to reject.
