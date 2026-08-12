<!-- Canonical human-approved §6c wording. Regenerate intentionally with
`bin/regenerate-delegate-to-pi-6c-fixture`; the resulting fixture diff makes
the wording change visible for review and is not an automatic approval. -->

**Trigger:** the delegation's diff adds or modifies any test, assertion, or
guard.

**Requirement:** before the work is treated as done, the test must be shown
to FAIL against a mutation of the behavior it claims to protect. A test that
passes both before and after that behavior is broken is not evidence — it is
a defect, and it is reported as one.

**Procedure.** For each added or changed assertion:

1. Copy the file the assertion protects to a scratch path. **Never mutate a
   tracked file** — use the test's own path-override variable if it has one,
   or a detached worktree (`git worktree add --detach <tmp> "$(git rev-parse HEAD)"`).
2. Break the specific behavior the assertion claims to protect.
3. Run the test. Record the exit code. It must be non-zero.
4. Restore, re-run, and confirm the control still exits 0.

Both exit codes go in the §12 report. "The suite is green" is not an
acceptable substitute for either of them.

**Mutations that must be tried**, because each has defeated a real assertion
in this repo:

| Mutation | Catches |
|---|---|
| Replace the guarded body with a short placeholder | Presence-only checks |
| Replace it with a long comment | Checks that infer content from length |
| Wrap the **real** body in a comment | Scanners that don't strip comments |
| Comment out the line that actually *executes* something | Guards that check a command exists but never runs |
| Point one role/branch at another's value | Assertions satisfied by prose elsewhere in the document |

**If the gate is not demonstrated**, treat the round as `CHANGES REQUESTED:`
regardless of the reviewer's verdict, and relay the missing demonstration as
the finding.

**Prefer executing the guarded logic over matching text.** The worked example
is `tests/test-delegate-to-pi-orchestration.sh`, which extracts the poll loop
out of the reference file and runs it against scripted inputs — so a change to
the loop's semantics fails the test, which no `rg` pattern over the same file
can achieve.

**Red flags — none of these satisfy the gate:**
- "The full suite is green."
- "The assertion matches the required string."
- "The reviewer confirmed the text is present."
- "It's a documentation change, so there's no behavior to mutate."
