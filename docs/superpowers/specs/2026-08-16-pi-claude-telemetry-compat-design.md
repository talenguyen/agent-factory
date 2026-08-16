# Pi compatibility for the existing Claude telemetry hook

## Goal

When this repository is launched with Pi directly, Pi loads the project’s
existing Claude skills and records the same telemetry lifecycle events as the
current `.claude/settings.json` hook configuration. The existing Pi worker
launcher, `bin/pi-project`, is unchanged.

## Scope

- Keep `.pi/settings.json` loading `../.claude/skills` and skill commands.
- Add a project-local Pi extension at
  `.pi/extensions/claude-telemetry-compat.ts`.
- The extension invokes the existing executable
  `.claude/hooks/telemetry-log.sh` with JSON on standard input.
- Add a shell test that statically verifies the extension maps all four
  required Pi lifecycle events and preserves the hook payload shape.

The work does not modify the Pi worker launcher, worker profiles, the Claude
hook script, or telemetry aggregation.

## Event mapping

| Pi event | Hook payload |
| --- | --- |
| `session_start` | `SessionStart`, session id, startup reason as source |
| `input` | `UserPromptSubmit`, session id, submitted prompt |
| `tool_execution_end` | `PostToolUse`, session id, tool name, success flag, tool arguments |
| `session_shutdown` | `SessionEnd`, session id, shutdown reason |

The compatibility extension delegates persistence and sensitive-input
filtering to `telemetry-log.sh`. That script already retains an input payload
only for a `Skill` tool call; it discards Bash, Write, and Edit bodies.

## Error handling

Telemetry is best effort. A missing or failed hook process must not block an
interactive Pi session; the extension resolves the hook invocation after a
spawn error or process exit.

## Validation

1. Add the test before the extension and run it to show the expected failure.
2. Add the smallest extension that makes the test pass.
3. Run the dedicated compatibility test and the existing telemetry-hook test.
4. Run the repository test suite specified in `CLAUDE.md`.
