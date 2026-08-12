# Project-Scoped Pi Skill Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide a repository launcher that starts Pi with only skills stored directly inside this project and make all delegated Pi workers use it.

**Architecture:** An executable Bash launcher injects `--no-skills` and explicit absolute paths for existing repository skill roots, rejects caller-supplied skill paths, and forwards all other Pi arguments. Delegation documentation invokes that launcher under isolation-specific worker names, while shell and RPC tests verify both argument construction and the effective loaded skill commands.

**Tech Stack:** Bash 3.2-compatible shell, Python 3 standard library, Pi 0.82.1 RPC JSONL, Herdr CLI, ripgrep, Git.

## Global Constraints

- Do not modify `.claude/settings.json`.
- Do not read, copy, edit, or pass any global skill directory to Pi.
- Supported repository skill roots are exactly `.pi/skills`, `.agents/skills`, and `.claude/skills` under the launcher's repository root.
- Bare `pi` is outside the isolation boundary; all supported project launches use `bin/pi-project`.
- Existing `pi-worker-*` processes must never be reused by the isolated delegation flow.
- Do not add `.pi/settings.json`; project settings cannot disable global skill discovery.

---

### Task 1: Isolated Pi launcher

**Files:**
- Create: `bin/pi-project`
- Create: `tests/test-pi-project.sh`

**Interfaces:**
- Consumes: a system `pi` executable discoverable through `PATH`; arbitrary ordinary Pi CLI arguments.
- Produces: executable command `bin/pi-project [pi arguments...]`; exit `64` for caller-supplied `--skill`; exit `127` when system Pi is absent.

- [ ] **Step 1: Write the launcher behavior test**

Create `tests/test-pi-project.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

readonly project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly launcher="$project_root/bin/pi-project"
readonly temp_dir="$(mktemp -d)"
trap 'rm -rf "$temp_dir"' EXIT

mkdir -p "$temp_dir/fake-bin"
cat > "$temp_dir/fake-bin/pi" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$PI_ARGS_FILE"
STUB
chmod +x "$temp_dir/fake-bin/pi"

readonly actual_args="$temp_dir/actual-args"
PATH="$temp_dir/fake-bin:$PATH" PI_ARGS_FILE="$actual_args" \
  "$launcher" --provider test-provider --model test-model --thinking low

{
  printf '%s\n' '--no-skills'
  for relative_path in .pi/skills .agents/skills .claude/skills; do
    if [[ -d "$project_root/$relative_path" ]]; then
      printf '%s\n' '--skill' "$project_root/$relative_path"
    fi
  done
  printf '%s\n' '--provider' 'test-provider' '--model' 'test-model' '--thinking' 'low'
} > "$temp_dir/expected-args"

diff -u "$temp_dir/expected-args" "$actual_args"

rm -f "$actual_args"
set +e
PATH="$temp_dir/fake-bin:$PATH" PI_ARGS_FILE="$actual_args" \
  "$launcher" --skill /tmp/outside-skill >"$temp_dir/reject.out" 2>"$temp_dir/reject.err"
readonly reject_status=$?
set -e
[[ "$reject_status" -eq 64 ]]
grep -F 'caller-supplied --skill paths are not allowed' "$temp_dir/reject.err"
[[ ! -e "$actual_args" ]]

mkdir -p "$temp_dir/no-pi-bin"
ln -s "$(command -v bash)" "$temp_dir/no-pi-bin/bash"
ln -s "$(command -v dirname)" "$temp_dir/no-pi-bin/dirname"
set +e
PATH="$temp_dir/no-pi-bin" "$launcher" >"$temp_dir/missing.out" 2>"$temp_dir/missing.err"
readonly missing_status=$?
set -e
[[ "$missing_status" -eq 127 ]]
grep -F 'pi executable not found on PATH' "$temp_dir/missing.err"

printf '%s\n' 'test-pi-project: PASS'
```

Make the test executable:

```bash
chmod +x tests/test-pi-project.sh
```

- [ ] **Step 2: Run the test and confirm the launcher is missing**

Run:

```bash
bash tests/test-pi-project.sh
```

Expected: nonzero exit because `bin/pi-project` does not exist.

- [ ] **Step 3: Implement the minimal isolated launcher**

Create `bin/pi-project`:

```bash
#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly project_root="$(cd -- "$script_dir/.." && pwd -P)"

for argument in "$@"; do
  case "$argument" in
    --skill|--skill=*)
      printf '%s\n' \
        'pi-project: caller-supplied --skill paths are not allowed' >&2
      exit 64
      ;;
  esac
done

if ! pi_bin="$(command -v pi)"; then
  printf '%s\n' 'pi-project: pi executable not found on PATH' >&2
  exit 127
fi
readonly pi_bin

skill_arguments=(--no-skills)
for relative_path in .pi/skills .agents/skills .claude/skills; do
  skill_path="$project_root/$relative_path"
  if [[ -d "$skill_path" ]]; then
    skill_arguments+=(--skill "$skill_path")
  fi
done

exec "$pi_bin" "${skill_arguments[@]}" "$@"
```

Make it executable:

```bash
chmod +x bin/pi-project
```

- [ ] **Step 4: Run the launcher test**

Run:

```bash
bash tests/test-pi-project.sh
```

Expected: `test-pi-project: PASS` and exit `0`.

- [ ] **Step 5: Review the launcher for repository-only path construction**

Run:

```bash
rg -n 'skills|--skill|pi_bin' bin/pi-project tests/test-pi-project.sh
git diff --check -- bin/pi-project tests/test-pi-project.sh
```

Expected: all constructed skill paths begin with `project_root`; no home-directory or parent-ancestor skill path appears; `git diff --check` exits `0`.

- [ ] **Step 6: Commit the launcher and its test**

```bash
git add bin/pi-project tests/test-pi-project.sh
git commit -m "Add project-isolated Pi launcher"
```

### Task 2: Force delegated workers through the launcher

**Files:**
- Create: `tests/test-delegate-to-pi-isolation.sh`
- Modify: `.claude/skills/delegate-to-pi/SKILL.md:88-153,251-280`
- Modify: `.claude/skills/delegate-to-pi/references/herdr-cli.md:15-123`

**Interfaces:**
- Consumes: executable `bin/pi-project` from Task 1 and the existing S/M/L profile arguments.
- Produces: Herdr spawn commands using `"$(git rev-parse --show-toplevel)/bin/pi-project"`; reusable worker names prefixed `pi-isolated-worker-<TIER>`.

- [ ] **Step 1: Write a failing static integration test**

Create `tests/test-delegate-to-pi-isolation.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

readonly project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly skill_file="$project_root/.claude/skills/delegate-to-pi/SKILL.md"
readonly reference_file="$project_root/.claude/skills/delegate-to-pi/references/herdr-cli.md"

for file in "$skill_file" "$reference_file"; do
  if rg -n -- 'herdr agent start .* -- pi(?: |$)' "$file"; then
    printf 'bare pi spawn remains in %s\n' "$file" >&2
    exit 1
  fi

  if rg -n -- 'pi-worker-' "$file"; then
    printf 'legacy reusable worker name remains in %s\n' "$file" >&2
    exit 1
  fi

  launcher_mentions="$(rg -c -- 'bin/pi-project' "$file")"
  if (( launcher_mentions < 2 )); then
    printf 'expected at least two launcher examples in %s\n' "$file" >&2
    exit 1
  fi
done

rg -q -- 'pi-isolated-worker-<TIER>' "$skill_file"
rg -q -- 'git rev-parse --show-toplevel.*bin/pi-project' "$skill_file"
rg -q -- 'git rev-parse --show-toplevel.*bin/pi-project' "$reference_file"

printf '%s\n' 'test-delegate-to-pi-isolation: PASS'
```

Make it executable:

```bash
chmod +x tests/test-delegate-to-pi-isolation.sh
```

- [ ] **Step 2: Run the static test and verify existing bare Pi spawns fail it**

Run:

```bash
bash tests/test-delegate-to-pi-isolation.sh
```

Expected: nonzero exit showing a bare `-- pi` spawn or legacy `pi-worker-` name.

- [ ] **Step 3: Update the delegation skill's worker identity and spawn commands**

In `.claude/skills/delegate-to-pi/SKILL.md`, make these exact conceptual replacements everywhere, including prose, examples, reuse filters, primary spawn, and fallback spawn:

```text
pi-worker-<TIER>       -> pi-isolated-worker-<TIER>
pi-worker-M            -> pi-isolated-worker-M
pi-worker-<TIER>-2     -> pi-isolated-worker-<TIER>-2
```

Replace each primary or fallback executable segment:

```bash
-- pi --provider <provider> --model <model> --thinking <thinking>
```

with:

```bash
-- "$(git rev-parse --show-toplevel)/bin/pi-project" --provider <provider> --model <model> --thinking <thinking>
```

Use the same replacement for fallback placeholders (`<fallback_provider>`, `<fallback_model>`, and `<fallback_thinking>`). Add one sentence before target reuse explaining that the isolation-specific name prevents reuse of workers launched before this boundary existed.

- [ ] **Step 4: Update the Herdr CLI reference consistently**

In `.claude/skills/delegate-to-pi/references/herdr-cli.md`:

- Replace every `pi-worker-*` example with `pi-isolated-worker-*`.
- Replace every Herdr spawn's bare `pi` executable with `"$(git rev-parse --show-toplevel)/bin/pi-project"`.
- State that this repository deliberately uses the launcher rather than bare Pi so global skills cannot enter delegated workers.
- Keep all existing provider/model/thinking flags after the launcher path.

The primary profile example must have this form:

```bash
herdr agent start pi-isolated-worker-M --cwd <target_cwd> --split right --no-focus -- "$(git rev-parse --show-toplevel)/bin/pi-project" --provider openai-codex --model gpt-5.6-terra --thinking medium
```

- [ ] **Step 5: Run static isolation and existing launcher tests**

Run:

```bash
bash tests/test-pi-project.sh
bash tests/test-delegate-to-pi-isolation.sh
```

Expected: both scripts print `PASS` and exit `0`.

- [ ] **Step 6: Inspect all remaining Pi launch references**

Run:

```bash
rg -n 'herdr agent start|pi-worker-|pi-isolated-worker-|bin/pi-project' \
  .claude/skills/delegate-to-pi
```

Expected: Herdr spawn commands use `bin/pi-project`; no `pi-worker-` match remains; isolation-specific names are used consistently.

- [ ] **Step 7: Commit delegation integration**

```bash
git add \
  .claude/skills/delegate-to-pi/SKILL.md \
  .claude/skills/delegate-to-pi/references/herdr-cli.md \
  tests/test-delegate-to-pi-isolation.sh
git commit -m "Route delegated Pi workers through isolated launcher"
```

### Task 3: Document and verify effective skill loading

**Files:**
- Create: `tests/test-pi-project-rpc.py`
- Modify: `README.md:1`

**Interfaces:**
- Consumes: `bin/pi-project` and Pi's `get_commands` RPC request.
- Produces: user-facing isolated launch instructions and an end-to-end assertion that every loaded skill command resolves inside the repository.

- [ ] **Step 1: Write the RPC isolation test**

Create `tests/test-pi-project-rpc.py`:

```python
#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
launcher = project_root / "bin" / "pi-project"

result = subprocess.run(
    [str(launcher), "--mode", "rpc", "--no-session", "--offline"],
    input='{"id":"skills","type":"get_commands"}\n',
    text=True,
    capture_output=True,
    timeout=30,
    check=False,
)
if result.returncode != 0:
    raise AssertionError(
        f"Pi RPC exited {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

records = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
responses = [
    record
    for record in records
    if record.get("type") == "response"
    and record.get("command") == "get_commands"
    and record.get("id") == "skills"
]
assert len(responses) == 1, responses
assert responses[0].get("success") is True, responses[0]

commands = responses[0]["data"]["commands"]
skill_commands = [command for command in commands if command.get("source") == "skill"]
assert any(command.get("name") == "skill:delegate-to-pi" for command in skill_commands)

outside = []
for command in skill_commands:
    raw_path = command.get("path")
    if not raw_path:
        outside.append(command)
        continue
    try:
        Path(raw_path).resolve().relative_to(project_root)
    except ValueError:
        outside.append(command)

assert not outside, f"skills loaded outside project: {outside}"
print("test-pi-project-rpc: PASS")
```

Make it executable:

```bash
chmod +x tests/test-pi-project-rpc.py
```

- [ ] **Step 2: Run the RPC test before documentation changes**

Run:

```bash
python3 tests/test-pi-project-rpc.py
```

Expected: `test-pi-project-rpc: PASS`. If it reports an outside skill, stop and investigate the loader source before changing the test; do not allowlist a global path.

- [ ] **Step 3: Replace the placeholder README with isolated launch guidance**

Replace `README.md` with:

````markdown
# Software Factory

## Run Pi with project skills only

Start Pi through the repository launcher:

```bash
./bin/pi-project
```

The launcher disables normal skill discovery and explicitly loads only skill roots that exist directly in this repository: `.pi/skills`, `.agents/skills`, and `.claude/skills`. It works from any current directory and forwards ordinary Pi options, for example:

```bash
./bin/pi-project --provider openai-codex --model gpt-5.6-terra --thinking medium
```

Do not use bare `pi` for project work: Pi has no project setting that can disable global skill discovery. Restart any existing Pi or delegated worker session before relying on this boundary because already-loaded skills cannot be unloaded.
````

- [ ] **Step 4: Run the complete verification suite**

Run:

```bash
bash tests/test-pi-project.sh
bash tests/test-delegate-to-pi-isolation.sh
python3 tests/test-pi-project-rpc.py
git diff --check
```

Expected: three `PASS` lines and `git diff --check` exits `0`.

- [ ] **Step 5: Verify changed paths stay inside approved scope**

Run:

```bash
git status --short
git diff --name-only HEAD
```

Expected implementation paths are only `README.md`, `bin/pi-project`, `tests/`, `.claude/skills/delegate-to-pi/SKILL.md`, and `.claude/skills/delegate-to-pi/references/herdr-cli.md`. `.claude/settings.json` may still show the user's pre-existing unstaged modification but must not be staged or included in an implementation commit.

- [ ] **Step 6: Commit documentation and RPC verification**

```bash
git add README.md tests/test-pi-project-rpc.py
git commit -m "Document project-isolated Pi usage"
```

- [ ] **Step 7: Perform final clean-room verification**

Run:

```bash
bash tests/test-pi-project.sh && \
bash tests/test-delegate-to-pi-isolation.sh && \
python3 tests/test-pi-project-rpc.py && \
git log --oneline -4 && \
git status --short
```

Expected: all tests pass; the three implementation commits and this plan/spec history are visible; only the user's pre-existing `.claude/settings.json` modification remains unstaged.
