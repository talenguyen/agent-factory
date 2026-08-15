# Software domain pack

## Workspace layout
A git repository and its tracked source, tests, and build artifacts constitute the deliverable. Work in an isolated git worktree before starting; never begin implementation on main/master without explicit consent, and preserve the linked worktree through review and final delivery.

## Verify command
```bash
git -C "$(pwd)" status --porcelain
git -C "$(pwd)" diff
```

## Reviewer rubric
`APPROVED` means the current diff satisfies the stated goal, preserves existing behavior where required, and has adequate automated-test coverage. The verdict protocol remains `APPROVED` or `CHANGES REQUESTED:`.

## Risk gate
In addition to, never instead of, `POLICY.md`: destructive git or filesystem operations (including force-push, `reset --hard`, `rm -rf`, deleting files or branches, and discarding uncommitted changes); secrets, credentials, or `.env.keys`; production databases, infrastructure, or live customer data; production deployment; destructive data migration; payments; and any outward-facing action require escalation. No pack grants crew members email, Slack, ticketing, publishing, or payment authority.

## Roles
Worker implements software; reviewer reviews the diff; scout is read-only. For every runnable or interactive CLI, TUI, web app, or game, Claude Code writes a black-box tester plan targeting realistic usage of the real running application or interface (not merely the diff). The tester executes every scenario and returns `NO BUGS FOUND` only when all pass, or `BUGS FOUND:` with exact reproduction steps, commands, and verbatim error output; the tester never fixes findings. Required practices are test-driven development, systematic debugging, and requesting a code review.

For a bug fix, the acceptance spec requires a reproduction command and its failing output captured before the change; the same command's passing output after the change is the proof, not the worker's own claim. For new behavior, the counter-mutation gate on the added test is the required proof that it actually exercises the change, not merely that it passes.

## Definition of done
The required verification and tests are green, review is approved, and final delivery is a user-approved merge or PR. Worktree isolation is required.
