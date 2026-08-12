# Project-scoped Pi skill isolation

## Purpose

Ensure every Pi process launched through this repository's supported entry point discovers skills only from this repository. Global skills under `~/.pi/agent/skills`, `~/.agents/skills`, global packages, and other ancestor skill directories must not be loaded.

Pi 0.82.1 has no project setting that disables global skill discovery. Its project `skills` setting can add or filter project resources, but it cannot suppress auto-discovered global skills. Strict isolation therefore requires the CLI combination `--no-skills` plus explicit `--skill` arguments.

## Design

### Project launcher

Add an executable `bin/pi-project` script. It will:

1. Resolve the repository root from the launcher's own location, so it works from any current directory.
2. Resolve the real `pi` executable from `PATH` and fail with a clear message if it is unavailable.
3. Always prepend `--no-skills`.
4. Add `--skill <absolute-path>` only for skill roots that exist directly in this repository:
   - `.pi/skills`
   - `.agents/skills`
   - `.claude/skills`
5. Forward all caller arguments unchanged after the isolation arguments.

Using explicit root paths avoids Pi's normal ancestor traversal. The launcher will not inspect, copy, edit, or pass paths to global skill directories.

### Delegation integration

Update `.claude/skills/delegate-to-pi/SKILL.md` and its Herdr CLI reference so every primary and fallback Herdr spawn invokes `bin/pi-project` instead of bare `pi`. Commands will use an absolute launcher path derived from the target repository, avoiding dependence on the spawned pane's `PATH` or current-directory command lookup.

Existing reusable Pi workers are unsafe because they may have started with global skills. Delegation matching will use new isolation-specific worker names, preventing reuse of older `pi-worker-*` processes.

### Documentation

Expand `README.md` with the supported launch command and state that bare `pi` retains Pi's normal global discovery behavior. Users must restart existing Pi sessions; skills already loaded into a process cannot be unloaded.

A `.pi/settings.json` file will not be added because it cannot enforce this boundary and would create a false sense of isolation.

## Error handling

- Missing system `pi`: print a concise error and exit nonzero.
- No in-repository skill roots: launch successfully with `--no-skills` and no explicit skills.
- Missing optional skill root: skip it without warning.
- Caller-provided `--skill` or `--no-skills`: the launcher contract prohibits bypass flags. It will reject caller-provided `--skill` arguments so callers cannot add paths outside the repository.

## Verification

1. Use a stub `pi` executable to assert that the launcher forwards ordinary model/session arguments while injecting `--no-skills` and only absolute in-repository `--skill` paths.
2. Verify attempts to pass an additional `--skill` fail nonzero.
3. Start Pi in RPC mode without a model call and inspect skill commands, confirming the local `delegate-to-pi` skill is present and known global skill commands are absent.
4. Search delegation files to confirm no Herdr spawn still invokes bare `pi`.
5. Confirm `.claude/settings.json` and all global skill files remain unmodified.

## Scope

This change isolates Pi only. It does not alter Claude Code plugin or skill settings, shell configuration, global Pi settings, or global skill files. The boundary applies to Pi processes launched through `bin/pi-project`; bare system `pi` cannot be made project-isolated through repository settings alone.
