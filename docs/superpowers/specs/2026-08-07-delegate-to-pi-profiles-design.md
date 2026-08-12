# delegate-to-pi: model/provider/thinking profile selection

## Purpose

Extend the existing `delegate-to-pi` skill (see
`docs/superpowers/specs/2026-08-06-delegate-to-pi-design.md`) so that Claude
picks a `pi` model, provider, and thinking level based on the delegated
task's size, instead of always launching `pi` with its own configured
defaults (the original design's explicit v1 out-of-scope item). This mirrors
a "profile" convention already used in a sibling project
(`config/pi-profiles.json`, `docs/pi-modes.md`), adapted for
`software-factory`.

## Background

`pi` has no native `--profile` flag. An earlier internal tool's "profile" is a
project-local JSON lookup table mapping named tiers to
`{provider, model, thinking, fallbacks}`, manually resolved by the
dispatching agent into `--provider`/`--model`/`--thinking` CLI flags before
launch — not a `pi` feature. There is no automatic model/provider switch on
failure in that project either: fallback is a scoped, manual retry rule
("only for visible usage or rate-limit failures, once, then escalate"), and
its top tier is gated behind explicit per-dispatch human authorization.

This design adopts the same pattern — a project-local profile table plus a
manual, scoped fallback rule — narrowed to three tiers (S/M/L) instead of
four, and ports it into `software-factory`'s `delegate-to-pi` skill rather
than depending on that earlier internal tool existing.

Two things were verified live on this machine while designing this:

1. **The candidate model/provider names actually resolve here.**
   `pi --list-models` confirms `openai-codex/gpt-5.6-luna`,
   `openai-codex/gpt-5.6-terra`, `openai-codex/gpt-5.6-sol`,
   `opencode-go/deepseek-v4-flash`, and `opencode-go/deepseek-v4-pro` are all
   present in the catalog available to this install, so the profile table
   below is not a blind copy of an earlier internal tool's environment-specific strings.
2. **herdr exposes no model/provider/thinking info for a running agent**, so
   there is no way to verify after the fact what profile a given `pi`
   process was launched with — `agent get`/`agent list`/`agent explain` all
   omit it. What *does* persist is the `name` an agent was given at
   `herdr agent start <name>`, confirmed live: an agent spawned via
   `agent start dtp-profile-probe --cwd /private/tmp --no-focus -- pi` shows
   `"name":"dtp-profile-probe"` in both `agent get` and `agent list` output,
   while a pre-existing `pi` agent not started that way (`w1P:p1`) has no
   `name` field at all. This is why profile tracking below is done via the
   spawn name rather than a side-channel state file: it's visible in the
   same `agent list` call §1 already makes, and it costs nothing extra to
   check.

## Architecture

### New component: `references/pi-profiles.json`

A new file alongside `references/herdr-cli.md` in
`.claude/skills/delegate-to-pi/`:

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

Each tier is a single fallback entry (not an ordered list) — the scoped
fallback rule below only ever retries once, so a list longer than one entry
would be dead data.

### Flow changes to `SKILL.md`

**New step, inserted before target resolution (current §1), call it §1
"Choose a tier and profile":**

Classify the delegated goal into a tier using this rubric (ported from
`superpowers:subagent-driven-development`'s own model-selection guidance,
for consistency with the rest of this repo's conventions):

- **S** — single-file or mechanical change with a clear, low-risk spec
  (e.g. fix a typo, adjust a config value, a well-specified one-file bug fix).
- **M** — multi-file coordination or ordinary feature work; the default
  when the goal doesn't clearly match S or L.
- **L** — architecture-level judgment calls, broad or ambiguous scope, or
  anything touching security/production-sensitive surfaces.

Read `references/pi-profiles.json` and look up the chosen tier's
`provider`/`model`/`thinking`.

**Gate on L:** if the chosen tier is `L`, stop and ask the user to confirm
before proceeding — state the goal and why it needs the top tier. This is a
single up-front confirmation for the whole delegation, not a per-turn check.
If the user declines, fall back to `M` for this delegation (their call, not
a fallback-profile trigger — see Error handling below for the distinct
usage/rate-limit fallback). Do not ask again mid-delegation for the same
goal — the tier is fixed once chosen.

**Changes to target resolution (current §1, renumbered §2):**

- Spawn name becomes `pi-worker-<TIER>` (e.g. `pi-worker-M`), not the
  generic `pi-worker` from the original design.
- The `herdr agent list` filter now matches on `cwd` **and** on `name`
  starting with `pi-worker-<TIER>` for the chosen tier — an idle
  `pi-worker-S` agent is never reused for an `M`-tier goal. If no agent
  matches both `cwd` and the tier-specific name, spawn a new one, even if a
  differently-tiered `pi` agent is idle in the same `cwd`. (A stray
  idle lower/higher-tier agent left behind from an earlier delegation is
  expected and harmless — it may get reused later if that same tier is
  chosen again.)
- The spawn command gains the profile's flags:

  ```bash
  herdr agent start pi-worker-<TIER> --cwd "$(pwd)" --split right --no-focus -- pi --provider <provider> --model <model> --thinking <thinking>
  ```

  using the values looked up in the new §1, not `pi`'s own defaults.

**No change** to send/poll/verify/turn-cap steps (§§3–6 in the renumbered
flow) — profile selection only affects which process gets spawned, not the
interaction loop.

## Error handling: scoped fallback

When settled output (in what is now §5, "handle idle/done") or a blocked
question (§4) contains a visible rate-limit or usage-failure signature —
phrases like "rate limit", "429", "quota exceeded", "insufficient_quota", or
"usage limit reached" in the pane text — and only then:

1. Close the current pane (`herdr pane close <target>`).
2. Spawn a replacement using the same tier's `fallback` entry from
   `pi-profiles.json`, reusing the same `pi-worker-<TIER>` name (the
   original is gone).
3. Resend the exact prompt that triggered the failure and resume polling.
4. If the fallback also shows a rate-limit/usage-failure signature,
   escalate to the user immediately with both failures shown verbatim —
   do not try a third variant, and do not fall further down any list (there
   is only one fallback per tier, per the table above).

No other failure type (a genuine bug in pi's output, a blocked question, a
timeout) triggers this fallback path — those are handled by the existing
§3/§4/§5 logic from the base design, unchanged.

## Out of scope

- Automatic, unattended tier escalation mid-delegation (e.g. bumping S to M
  after repeated failed turns) — tier is fixed once chosen for a given
  delegation; if the turn cap is hit, the existing base-design escalation to
  the human applies, and a human can choose to re-delegate at a higher tier.
- A fallback list longer than one entry per tier — the scoped rule this
  design ports over only ever retries once.
- Any change to the earlier internal tool's own profile table or skills — this is a
  separate, adapted table local to `software-factory`.

## Testing plan

Manual dry run extending the original design's test: delegate a low-stakes,
reversible goal once per tier (S, M, L — declining the L gate once to
confirm the fallback-to-M path, then accepting it once to confirm the L
spawn), confirming: correct `--provider`/`--model`/`--thinking` flags reach
the spawned `pi` process (visible via `herdr agent explain <target> --json`
or the pane's own startup banner if it prints one), tier-scoped reuse
(spawn under S, confirm a subsequent M-tier goal in the same cwd spawns a
new agent rather than reusing the S one), and the L gate firing correctly.
The rate-limit fallback path itself is not easily triggerable on demand;
document it as verified by code inspection only unless a real rate-limit is
encountered during testing.
