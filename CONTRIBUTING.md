# Contributing

Two contribution surfaces are open, and one is closed.

**Open: domain packs.** A pack teaches the loop what "done" and "verified" mean
for a new kind of work.

**Open: backend adapters.** An adapter teaches the loop how to drive a different
agent or multiplexer.

**Closed: the control loop.** `bin/crew`, `orchestrate/SKILL.md` and the crew
contract are owned. Issues and findings are very welcome; PRs that restructure
the loop generally are not, because its invariants were each paid for by a
specific bug and the reasoning lives in `docs/superpowers/specs/`.

---

## Writing a domain pack — read this part twice

**A pack without a real oracle makes this project worse, not better.** The loop
will happily run five unsupervised rounds producing confident, well-formatted,
wrong output. The only thing standing between a pack and a slop generator is
whether its verify command can actually fail.

So before anything else, answer: **what command exits non-zero when the work is
wrong, without a human in the loop?**

If the answer is "a reviewer reads it and forms an opinion", you do not have a
pack yet. That is not a rejection — it is the rubric-only rule, and the honest
response is to add a human checkpoint for that deliverable rather than pretend
it is verifiable.

Worked example: the `research` pack's deliverable is prose, which sounds
unverifiable. Its oracle checks that every citation key resolves, every excerpt
occurs **verbatim** in a stored snapshot, every snapshot hash matches, and every
derived number recomputes from cited figures. It cannot tell whether a conclusion
is wise. It makes fabricated sources, drifted quotes and invented arithmetic fail
mechanically — and that is enough to make the unsupervised rounds worth running.

A pack supplies six sections: workspace layout, verify command, reviewer rubric,
risk gate (additive to `POLICY.md`, never weakening it), roles including the
tester analog, and definition of done. The loader is fail-loud: a missing section
stops the run and names it.

The tester analog deserves thought. Its job is to **leave the artifact and touch
reality** — in software that is running the program, in research it is
re-opening the primary source. If your tester only re-reads what the worker
wrote, you have a second reviewer, not a tester.

## Writing an adapter — the one rule that matters

**Your test double must model the real protocol, or your tests are worthless.**

This is not hypothetical. The `herdr` adapter shipped with 8 mutation-verified
assertions and crashed on its first real call, because the fake returned
`result.text` where real herdr returns `result.read.text`. Every assertion was
rigorously validating a fiction.

So your stub must reproduce:

- the real **response shapes**, including nesting;
- verbs that return **no output at all** (`herdr pane send-keys` returns nothing;
  parsing it unconditionally turned a success into a reported failure);
- **noise on stderr during success** (`claude -p` writes ~157 bytes to stderr and
  exits 0; treating stderr as failure breaks everything);
- **timing** — a value that is not rendered yet is not a value that is wrong.
  Profile verification read a pane before the agent had drawn its status bar and
  reported a *mismatch* instead of *not ready*.

Mutation testing proves an assertion is sensitive to the code. It cannot prove
your fixture resembles reality. **Only a live run does that**, so a backend
adapter PR must include live-run evidence, and for anything probabilistic,
**repetition** — a 1-in-3 failure survived a review round because one success was
mistaken for proof.

Adapters are executables taking the verb as `$1`, JSON on stdout, diagnostics on
stderr. Declare capabilities honestly: if you cannot restrict your agent to
repo-local skills, say `isolation: false`. If you cannot read a profile banner,
say `banner: false` and let verification return **cannot-verify** — never
`verified`.

Full contract: `docs/superpowers/specs/2026-08-10-crew-contract.md`.

## Testing rules that apply to everything

No package manager, no test runner. Tests are standalone scripts:

```bash
for t in tests/test-*.sh; do bash "$t" || echo "FAIL $t"; done
for t in tests/test-*.py; do python3 "$t" || echo "FAIL $t"; done
```

1. **Run the suite from outside the repository tree**, not just in place. A
   fixture that needed an untracked empty directory passed for the author, two
   workers and a reviewer — and failed in every clean checkout, because git
   cannot store an empty directory.
2. **Test the entry point, not the function.** An assertion that calls into
   `lib/crew` directly leaves the CLI verb free to disconnect from its
   implementation with every test still green.
3. **Every new assertion must fail under mutation.** Break the behaviour it
   protects, record the non-zero exit, restore, confirm zero. A test that passes
   both before and after is a defect, not coverage. The harness must exist in
   committed code — reporting pairs you did not run defeats the check while
   looking like compliance.
4. **Never assert on the shared telemetry log's line count.** Other sessions
   write to it concurrently. Tag your records with a per-run marker and assert
   none of yours leak into the real log.
5. **Run with a clean environment.** No inherited `FACTORY_*` variables; they
   change adapter selection and will make a green suite look red.

## Reporting a finding

The most valuable issues name a **specific defect and how to reproduce it**. The
findings that improved this project most were of exactly that shape: "this
assertion still passes when I remove the behaviour it protects", "this returns
no-match for `drop the production users table`", "this reports `reused: true` for
an agent I deleted".

## Not accepted

Giving crew members outward-facing tools — email, chat, tickets, publishing,
payments. The crew produces artifacts; the orchestrator acts. This is permanent.
