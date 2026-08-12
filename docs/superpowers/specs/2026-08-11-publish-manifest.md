# Publish manifest and pre-publication audit (Phase 4a)

**Status: NOT APPROVED FOR PUBLICATION. Nothing has been published.** This
document is the audit that makes the publish decision informed. Publishing is
`POLICY.md` category 5 and requires explicit approval naming the repository, its
visibility, its licence, and the exact commit.

Audited at `main` = `7d2ce2a`, 249 tracked files, suite 29/29 from a clean
checkout outside the repo.

## Verdict summary

| Check | Result |
|---|---|
| Home-directory paths in tracked files | **clean** — none |
| Never-publish paths tracked | **clean** — none of them are tracked |
| `.gitignore` covers the never-publish set | **clean** — all nine entries present |
| Real secrets / credentials | **clean** — see note below |
| Operator or employer identifiers | **clean** — no `giangnguyen`, `mepplatform`, `uplive` |
| Real user prompts or telemetry contents in docs | **clean** — only field names in design docs |
| Vendored third-party licensing | **clean** — pinned, with licence and notices |
| Internal project name leakage | **1 blocker** — private project reference |
| Root `LICENSE` | **1 blocker** — missing |
| Unreviewed shippable content | **1 open question** — `docs/guides/` |

## Never-publish set — confirmed untracked and gitignored

`var/telemetry/events.jsonl` (**stores verbatim user prompts** via the
`UserPromptSubmit` hook), `.projects/`, `.claude/settings.local.json`,
`POLICY.local.md`, `config/profiles.local.json`, `.factory/`, `.superpowers/`,
`.worktrees/`, `__pycache__/`.

## Note on the "secret" scan hit

`lib/crew/core.py` matches `secret`, `token`, `password`, `key`. These are the
**risk classifier's detection vocabulary** — the words `crew classify-risk`
looks for when deciding whether a question touches `POLICY.md`'s
"Secrets and credentials" category. No credential values are present. Benign,
and the scan finding it is the classifier working.

## Blockers — must be resolved before publication

### 1. Private project reference — an unrelated private project is named 4 times

`docs/superpowers/specs/2026-08-07-delegate-to-pi-profiles-design.md`, lines 16,
28, 37, 168. The profile-tier design credits its origin to another private
project by name. Publishing discloses that project's existence and some of its
internals.

**Fix:** replace with a neutral description — "an earlier internal tool" — with
no loss of meaning; the design rationale does not depend on the name.

### 2. No root `LICENSE`

Only the vendored `LICENSE-superpowers.txt` exists. MIT is the intended licence
and is compatible with the vendored `superpowers` v6.2.0 set.

**Fix:** add MIT `LICENSE` at the root before the initial public commit.

## Open question — `docs/guides/agent-instruction-engineering.md`

751 lines, added by a concurrent session, on writing `CLAUDE.md` files and
deriving specialist personas, citing Anthropic's published guidance. It is
plausibly valuable public material and contains no obvious leakage, but **I have
not read all 751 lines**, and I will not put my name to publishing content I
have not fully reviewed.

Three options: read it in full and include it; exclude it from the initial
publish set; or leave it for its author to clear. **Excluding it is the cheapest
safe default** — it is not load-bearing for the project.

## What ships, if approved

| Area | Files | Notes |
|---|---|---|
| `tests/` | 144 | includes research fixtures; the coverage that protects the loop |
| `.claude/skills/` vendored | 52 | `superpowers` v6.2.0, unmodified, MIT, notices retained |
| `docs/` | 17 | the design specs — **the teaching material, and most of why anyone would trust this** |
| `lib/` | 14 | `crew` core + adapters, `telemetry` |
| `.claude/skills/` ours | 8 | `orchestrate`, `delegate-to-pi` alias, `autonomous-goal`, `autonomous-build` alias |
| `bin/` | 7 | `crew`, `pi-project`, `verify-research`, telemetry tools |
| root | 4 | `README.md`, `CLAUDE.md`, `POLICY.md`, `.gitignore` |
| `.claude/` | 2 | shippable `settings.json` (hooks only) + telemetry hook |
| `config/` | 1 | `profiles.example.json` |

## Why the docs ship despite naming internal conventions

Several specs reference `.projects/` and `.superpowers/`. These are **this
project's own directory conventions**, documented in `CLAUDE.md` — not client or
employer identifiers. They are part of what a reader needs in order to follow
the design. Keeping them is correct; the private-project reference is different in
kind, because it names a separate private project.

## Remaining gate before any publish request

Phase 5 must land first, because the v1.0 promise is that a stranger gets from
clone to a completed goal in fifteen minutes. Publishing before `bin/factory`,
the README rewrite, and clean-clone CI exist would publish something that cannot
be run by the audience it is for.
