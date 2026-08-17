# Pi Claude Telemetry Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a directly launched, trusted Pi session invoke the existing Claude telemetry shell hook for equivalent lifecycle events.

**Architecture:** A project-local TypeScript Pi extension translates Pi lifecycle events into the JSON schema already consumed by `.claude/hooks/telemetry-log.sh`. The extension is auto-discovered under `.pi/extensions`; `.pi/settings.json` continues to expose the existing Claude skill directory to Pi.

**Tech Stack:** Pi extension API, TypeScript executed by Pi/jiti, Node.js `child_process`, Bash tests.

## Global Constraints

- Do not modify `bin/pi-project`; it remains the isolated Pi worker launcher.
- Do not modify `.claude/hooks/telemetry-log.sh`; it remains the sole telemetry persistence and sensitive-input filter.
- The extension is best effort: a missing or failing hook process cannot fail a Pi session.
- The extension sends hook input only through standard input as one JSON payload per event.

---

### Task 1: Add the telemetry compatibility extension and regression test

**Files:**
- Create: `.pi/extensions/claude-telemetry-compat.ts`
- Create: `tests/test-pi-claude-telemetry-extension.sh`
- Modify: `.pi/settings.json` only if it does not already retain `skills: ["../.claude/skills"]` and `enableSkillCommands: true`

**Interfaces:**
- Consumes: Pi `session_start`, `input`, `tool_execution_end`, and `session_shutdown` events; `ctx.cwd`; and `ctx.sessionManager.getSessionId()`.
- Produces: one JSON object on standard input to `.claude/hooks/telemetry-log.sh` with `hook_event_name`, `session_id`, and event-specific fields.

- [ ] **Step 1: Write the failing test**

Create `tests/test-pi-claude-telemetry-extension.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

readonly root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly extension="$root/.pi/extensions/claude-telemetry-compat.ts"

[[ -f "$extension" ]]
grep -F 'pi.on("session_start"' "$extension"
grep -F 'pi.on("input"' "$extension"
grep -F 'pi.on("tool_execution_end"' "$extension"
grep -F 'pi.on("session_shutdown"' "$extension"
grep -F 'hook_event_name: "SessionStart"' "$extension"
grep -F 'hook_event_name: "UserPromptSubmit"' "$extension"
grep -F 'hook_event_name: "PostToolUse"' "$extension"
grep -F 'hook_event_name: "SessionEnd"' "$extension"
grep -F 'tool_use_succeeded: !event.isError' "$extension"
grep -F 'child.stdin.end(JSON.stringify(payload))' "$extension"
printf '%s\n' 'test-pi-claude-telemetry-extension: PASS'
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bash tests/test-pi-claude-telemetry-extension.sh`

Expected: failure at `[[ -f "$extension" ]]` because the extension does not yet exist.

- [ ] **Step 3: Write the minimal extension**

Create `.pi/extensions/claude-telemetry-compat.ts` containing an `emit(cwd, payload)` helper that uses `spawn()` to execute `.claude/hooks/telemetry-log.sh`, writes `JSON.stringify(payload)` to `child.stdin`, and resolves after `error` or `close`.

Register these event handlers:

```ts
pi.on("session_start", async (event, ctx) => {
  await emit(ctx.cwd, {
    hook_event_name: "SessionStart",
    session_id: ctx.sessionManager.getSessionId(),
    source: event.reason,
  });
});

pi.on("input", async (event, ctx) => {
  await emit(ctx.cwd, {
    hook_event_name: "UserPromptSubmit",
    session_id: ctx.sessionManager.getSessionId(),
    prompt: event.text,
  });
});

pi.on("tool_execution_end", async (event, ctx) => {
  await emit(ctx.cwd, {
    hook_event_name: "PostToolUse",
    session_id: ctx.sessionManager.getSessionId(),
    tool_name: event.toolName,
    tool_use_succeeded: !event.isError,
    tool_input: event.args,
  });
});

pi.on("session_shutdown", async (event, ctx) => {
  await emit(ctx.cwd, {
    hook_event_name: "SessionEnd",
    session_id: ctx.sessionManager.getSessionId(),
    reason: event.reason,
  });
});
```

- [ ] **Step 4: Run dedicated tests**

Run:

```bash
bash tests/test-pi-claude-telemetry-extension.sh
bash tests/test-telemetry-log-hook.sh
```

Expected: both commands print their `PASS` lines and exit zero.

- [ ] **Step 5: Run the full repository suite**

Run:

```bash
for t in tests/test-*.sh; do bash "$t" || echo "FAIL $t"; done
for t in tests/test-*.py; do python3 "$t" || echo "FAIL $t"; done
```

Expected: no `FAIL` output.

- [ ] **Step 6: Commit**

```bash
git add .pi/settings.json .pi/extensions/claude-telemetry-compat.ts tests/test-pi-claude-telemetry-extension.sh
git commit -m "Add Pi compatibility for Claude telemetry hooks"
```

## Plan self-review

- Spec coverage: Task 1 creates the extension, retains the project skill configuration, preserves the existing hook script, validates each event mapping, validates the existing sensitive-input filter, and leaves `bin/pi-project` unchanged.
- Placeholder scan: no implementation placeholders remain.
- Interface consistency: every handler passes the JSON keys consumed by the existing hook script.
