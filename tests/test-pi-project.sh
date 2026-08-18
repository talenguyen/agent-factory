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

cd "$project_root"
unset FACTORY_CREW_ROLE
readonly actual_args="$temp_dir/actual-args"
PATH="$temp_dir/fake-bin:$PATH" PI_ARGS_FILE="$actual_args" \
  "$launcher" --provider test-provider --model test-model --thinking low

{
  printf '%s\n' '--no-skills' '--no-extensions'
  for relative_path in .pi/skills .agents/skills .claude/skills; do
    if [[ -d "$project_root/$relative_path" ]]; then
      printf '%s\n' '--skill' "$project_root/$relative_path"
    fi
  done
  printf '%s\n' '--provider' 'test-provider' '--model' 'test-model' '--thinking' 'low'
} > "$temp_dir/expected-args"

diff -u "$temp_dir/expected-args" "$actual_args"

worker_args="$temp_dir/worker-args"
env FACTORY_CREW_ROLE=worker PATH="$temp_dir/fake-bin:$PATH" PI_ARGS_FILE="$worker_args" \
  "$launcher"
if grep -F -- "$project_root/.claude/skills" "$worker_args"; then
  printf 'test-pi-project: .claude/skills leaked into worker skill_arguments\n' >&2
  exit 1
fi
for relative_path in .pi/skills .agents/skills; do
  if [[ -d "$project_root/$relative_path" ]]; then
    grep -F -- "$project_root/$relative_path" "$worker_args"
  fi
done

other_project="$temp_dir/other-project"
mkdir -p "$other_project/.pi/skills"
other_project="$(cd -- "$other_project" && pwd -P)"
other_args="$temp_dir/other-args"
(
  cd "$other_project"
  PATH="$temp_dir/fake-bin:$PATH" PI_ARGS_FILE="$other_args" "$launcher"
)
grep -Fx -- '--skill' "$other_args"
grep -Fx -- "$other_project/.pi/skills" "$other_args"
for relative_path in .pi/skills .agents/skills .claude/skills; do
  if grep -F -- "$project_root/$relative_path" "$other_args"; then
    printf 'test-pi-project: agent-factory skills leaked into other project\n' >&2
    exit 1
  fi
done

assert_rejected_without_invoking_pi() {
  local expected_error="$1"
  shift

  rm -f "$actual_args"
  set +e
  PATH="$temp_dir/fake-bin:$PATH" PI_ARGS_FILE="$actual_args" \
    "$launcher" "$@" >"$temp_dir/reject.out" 2>"$temp_dir/reject.err"
  local reject_status=$?
  set -e
  [[ "$reject_status" -eq 64 ]]
  grep -F "$expected_error" "$temp_dir/reject.err"
  [[ ! -e "$actual_args" ]]
}

assert_rejected_without_invoking_pi \
  'caller-supplied --skill paths are not allowed' \
  --skill /tmp/outside-skill
assert_rejected_without_invoking_pi \
  'caller-supplied extension paths are not allowed' \
  --extension /tmp/outside-extension
assert_rejected_without_invoking_pi \
  'caller-supplied extension paths are not allowed' \
  -e /tmp/outside-extension

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
