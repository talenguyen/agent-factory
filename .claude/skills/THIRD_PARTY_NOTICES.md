# Vendored skills

The following skill directories are vendored, unmodified, from the
`superpowers` plugin (https://github.com/obra/superpowers), version 6.2.0,
under the MIT License (see `LICENSE-superpowers.txt` in this directory):

- brainstorming
- dispatching-parallel-agents
- executing-plans
- finishing-a-development-branch
- receiving-code-review
- requesting-code-review
- subagent-driven-development
- systematic-debugging
- test-driven-development
- using-git-worktrees
- using-superpowers
- verification-before-completion
- writing-plans
- writing-skills

They are vendored here so `bin/pi-project` (which loads skills only from
`.pi/skills`, `.agents/skills`, and `.claude/skills` inside this repository)
can make them available to delegated Pi workers.

Only the `skills/` contents are vendored. The upstream package's Pi
extension (`.pi/extensions/superpowers.ts`), which auto-discovers the skills
directory and injects a forceful "you have superpowers" bootstrap message at
session start, is intentionally NOT vendored — `bin/pi-project` always passes
`--no-extensions` and rejects caller-supplied `--extension` paths, and that
isolation boundary is out of scope here. Under this launcher, these skills
are discoverable and invocable like any other project skill (e.g.
`delegate-to-pi`), but nothing forces a Pi worker to consult them.

`delegate-to-pi` is this project's own skill, not part of the vendored set.

To update: replace these directories with the contents of a newer
`superpowers` release's `skills/` folder and update the version above.
