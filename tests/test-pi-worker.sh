#!/usr/bin/env bash
set -euo pipefail

readonly project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly launcher="$project_root/bin/pi-worker"
readonly temp_dir="$(mktemp -d)"
trap 'rm -rf "$temp_dir"' EXIT

mkdir -p "$temp_dir/fake-bin"
cat > "$temp_dir/fake-bin/pi" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "${FACTORY_CREW_ROLE-}" > "$PI_ROLE_FILE"
printf '%s\n' "$@" > "$PI_ARGS_FILE"
STUB
chmod +x "$temp_dir/fake-bin/pi"

readonly actual_role="$temp_dir/role"
readonly actual_args="$temp_dir/args"
env -u FACTORY_CREW_ROLE PATH="$temp_dir/fake-bin:$PATH" PI_ROLE_FILE="$actual_role" PI_ARGS_FILE="$actual_args" \
  "$launcher" --provider test-provider --model test-model --thinking low --session-id test-session

[[ "$(<"$actual_role")" == worker ]] || { printf 'worker role was not exported\n' >&2; exit 1; }
{
  printf '%s\n' '--no-skills' '--no-extensions'
  for relative_path in .pi/skills .agents/skills .claude/skills; do
    if [[ -d "$project_root/$relative_path" ]]; then
      printf '%s\n' '--skill' "$project_root/$relative_path"
    fi
  done
  printf '%s\n' '--provider' 'test-provider' '--model' 'test-model' '--thinking' 'low' '--session-id' 'test-session'
} > "$temp_dir/expected-args"
diff -u "$temp_dir/expected-args" "$actual_args"

printf '%s\n' 'test-pi-worker: PASS'
