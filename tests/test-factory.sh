#!/usr/bin/env bash
# Black-box contract and mutation/control harness for bin/factory.
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
factory="$root/bin/factory"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT

fixture="$scratch/mock.json"
printf '%s\n' '{"capabilities":{"layout":false,"focus":false,"persistent_context":false,"native_status":true,"banner":false,"isolation":true},"agents":[],"statuses":{},"reads":{}}' >"$fixture"
base_env=("CREW_ROOT=$root" "FACTORY_MUX=mock" "FACTORY_WORKER=mock" "FACTORY_MOCK_FIXTURE=$fixture" "FACTORY_MOCK_STATE=$scratch/mock-state.json" "TELEMETRY_LOG_DIR=$scratch/telemetry")
run_factory() { env -u FACTORY_CREW_DELEGATION_ID "${base_env[@]}" "$factory" "$@"; }
[[ ${FACTORY_DOMAIN_PACK_DIR:-} != /definitely-not-a-domain-pack-dir ]] || {
  echo 'CI leaked FACTORY_DOMAIN_PACK_DIR into a test process' >&2; exit 1;
}

# Control: discoverable mock adapters and a valid profile/policy let doctor succeed.
run_factory doctor >"$scratch/doctor.out"
grep -F 'mux adapter: mock (available)' "$scratch/doctor.out" >/dev/null
grep -F 'persistent_context: unavailable — context is re-supplied every turn' "$scratch/doctor.out" >/dev/null
grep -F 'banner: unavailable — profiles cannot be verified' "$scratch/doctor.out" >/dev/null
grep -F 'POLICY.md: present and parseable' "$scratch/doctor.out" >/dev/null
# Mutation: selecting an absent mux must be reported and fail rather than being claimed available.
if env -u FACTORY_CREW_DELEGATION_ID "${base_env[@]}" FACTORY_MUX=missing "$factory" doctor >"$scratch/missing.out" 2>&1; then
  echo 'missing adapter mutation unexpectedly passed' >&2; exit 1
fi
grep -F 'mux adapter: missing (missing)' "$scratch/missing.out" >/dev/null

# Broken prerequisites have a non-zero doctor exit.
make_doctor_root() {
  local target="$1"
  mkdir -p "$target"
  cp -R "$root/lib" "$root/config" "$root/.claude" "$target/"
  cp "$root/POLICY.md" "$target/"
}
expect_doctor_exit() {
  local expected="$1" label="$2"
  shift 2
  set +e
  "$@" >"$scratch/$label.out" 2>&1
  local actual=$?
  set -e
  if [[ "$actual" -ne "$expected" ]]; then
    printf '%s: expected doctor exit %s, got %s\n' "$label" "$expected" "$actual" >&2
    cat "$scratch/$label.out" >&2
    exit 1
  fi
}
profile_root="$scratch/no-profiles"
make_doctor_root "$profile_root"
rm "$profile_root/.claude/skills/delegate-to-pi/references/pi-profiles.json"
policy_root="$scratch/no-policy"
make_doctor_root "$policy_root"
rm "$policy_root/POLICY.md"
missing_doctor=(env -u FACTORY_CREW_DELEGATION_ID "${base_env[@]}" FACTORY_MUX=missing "$factory" doctor)
profile_doctor=(env -u FACTORY_CREW_DELEGATION_ID CREW_ROOT="$profile_root" FACTORY_MUX=mock FACTORY_WORKER=mock FACTORY_MOCK_FIXTURE="$fixture" FACTORY_MOCK_STATE="$scratch/profile-state.json" "$factory" doctor)
policy_doctor=(env -u FACTORY_CREW_DELEGATION_ID CREW_ROOT="$policy_root" FACTORY_MUX=mock FACTORY_WORKER=mock FACTORY_MOCK_FIXTURE="$fixture" FACTORY_MOCK_STATE="$scratch/policy-state.json" "$factory" doctor)
expect_doctor_exit 1 missing-adapter "${missing_doctor[@]}"
expect_doctor_exit 1 missing-profile-table "${profile_doctor[@]}"
expect_doctor_exit 1 missing-policy "${policy_doctor[@]}"
# Counter-mutation runs the complete black-box harness. Its unmutated control
# must exit zero before the pair is evidence.
if [[ ${SKIP_FACTORY_COUNTER_MUTATION:-} != 1 ]]; then
mutant_root="$scratch/factory-success-mutant"
git clone --quiet --no-local "$root" "$mutant_root"
python3 - "$mutant_root/bin/factory" <<'PY'
import pathlib, sys
path = pathlib.Path(sys.argv[1])
text = path.read_text()
old = "return 1 if broken else 0"
assert text.count(old) == 1
path.write_text(text.replace(old, "return 0"))
PY
set +e
FACTORY_CI_INNER=1 SKIP_FACTORY_COUNTER_MUTATION=1 bash "$mutant_root/tests/test-factory.sh" >/dev/null 2>&1
broken=$?
FACTORY_CI_INNER=1 SKIP_FACTORY_COUNTER_MUTATION=1 bash "$root/tests/test-factory.sh" >/dev/null 2>&1
restored=$?
set -e
if [[ "$restored" -ne 0 ]]; then
  printf 'doctor_exit_status: control failed with exit %s; mutation evidence is invalid\n' "$restored" >&2
  exit 1
fi
if [[ "$broken" -eq 0 ]]; then
  printf 'doctor_exit_status: mutation unexpectedly passed\n' >&2
  exit 1
fi
printf 'doctor_exit_status: broken_exit=%s restored_exit=%s\n' "$broken" "$restored"
fi

# Control: a known software pack scaffolds all operator workspace files.
workspace="$scratch/software-workspace"
run_factory init "$workspace" --domain software
[[ -f "$workspace/WORKSPACE.md" && -f "$workspace/acceptance.md" && -f "$workspace/.gitignore" ]]
grep -Fx 'var/' "$workspace/.gitignore" >/dev/null
grep -F 'rubric-only' "$workspace/acceptance.md" >/dev/null
# Mutation: an unknown domain cannot silently create an unusable workspace.
if run_factory init "$scratch/unknown-workspace" --domain unknown >"$scratch/unknown.out" 2>&1; then
  echo 'unknown domain mutation unexpectedly passed' >&2; exit 1
fi
grep -F 'missing domain pack' "$scratch/unknown.out" >/dev/null

# Control: a scaffolded workspace resolves every run prerequisite and prints, rather than runs, crew.
(
  cd "$workspace"
  run_factory run >"$scratch/run.out"
)
grep -F "$root/bin/crew begin --domain software --tier M" "$scratch/run.out" >/dev/null
grep -F 'does not drive the loop' "$scratch/run.out" >/dev/null
# The printed absolute invocation works from the initialized external workspace.
(
  cd "$workspace"
  env -u FACTORY_CREW_DELEGATION_ID "${base_env[@]}" "$root/bin/crew" begin --domain software --tier M >/dev/null
)

# Adapter files alone are not usable backends: absent herdr/pi/claude binaries
# are broken, while a discoverable claude permits batch's degraded mode.
expect_doctor_exit 1 no-herdr-or-pi env PATH=/usr/bin:/bin "$factory" doctor
 grep -F 'mux adapter: herdr (present; backend unavailable: herdr)' "$scratch/no-herdr-or-pi.out" >/dev/null
 grep -F 'worker adapter: pi (present; backend unavailable: pi)' "$scratch/no-herdr-or-pi.out" >/dev/null
if (cd "$workspace" && env PATH=/usr/bin:/bin FACTORY_MUX=batch FACTORY_WORKER=claude "$factory" run >"$scratch/no-claude.out" 2>&1); then
  echo 'batch+claude without claude unexpectedly passed' >&2; exit 1
fi
grep -F 'backend unavailable: claude' "$scratch/no-claude.out" >/dev/null
fake_bin="$scratch/fake-bin"
mkdir "$fake_bin"
printf '#!/usr/bin/env bash\nexit 0\n' >"$fake_bin/claude"
chmod +x "$fake_bin/claude"
env PATH="$fake_bin:/usr/bin:/bin" FACTORY_MUX=batch FACTORY_WORKER=claude "$factory" doctor >"$scratch/degraded.out"
grep -F 'persistent_context: unavailable — context is re-supplied every turn' "$scratch/degraded.out" >/dev/null
grep -F 'banner: unavailable — profiles cannot be verified' "$scratch/degraded.out" >/dev/null
grep -F 'isolation: unavailable — results are not reproducible across machines' "$scratch/degraded.out" >/dev/null

# HERDR_PANE_ID is required only for focus-relative herdr crew spawns.
printf '#!/usr/bin/env bash\nexit 0\n' >"$fake_bin/herdr"
printf '#!/usr/bin/env bash\nexit 0\n' >"$fake_bin/pi"
chmod +x "$fake_bin/herdr" "$fake_bin/pi"
if env -u HERDR_PANE_ID PATH="$fake_bin:/usr/bin:/bin" FACTORY_MUX=herdr FACTORY_WORKER=pi "$factory" doctor >"$scratch/herdr-unanchored.out" 2>&1; then
  echo 'herdr doctor without HERDR_PANE_ID unexpectedly passed' >&2; exit 1
fi
grep -F 'HERDR_PANE_ID: unset (crew spawning is unsafe)' "$scratch/herdr-unanchored.out" >/dev/null
env HERDR_PANE_ID=p-orchestrator PATH="$fake_bin:/usr/bin:/bin" FACTORY_MUX=herdr FACTORY_WORKER=pi "$factory" doctor >"$scratch/herdr-anchored.out"
grep -F 'HERDR_PANE_ID: set (crew spawning safely anchored)' "$scratch/herdr-anchored.out" >/dev/null
# Batch never uses pane focus and must not require HERDR_PANE_ID.
env -u HERDR_PANE_ID PATH="$fake_bin:/usr/bin:/bin" FACTORY_MUX=batch FACTORY_WORKER=claude "$factory" doctor >"$scratch/batch-unanchored.out"
! grep -Fq 'HERDR_PANE_ID' "$scratch/batch-unanchored.out"

# Mutation: no WORKSPACE.md is a refusal, not a guessed default domain.
if (cd "$scratch" && run_factory run >"$scratch/no-workspace.out" 2>&1); then
  echo 'missing workspace mutation unexpectedly passed' >&2; exit 1
fi
grep -F 'missing WORKSPACE.md' "$scratch/no-workspace.out" >/dev/null

# Control/mutation audit: the root licence is MIT and the private project name is absent from tracked content.
grep -F 'MIT License' "$root/LICENSE" >/dev/null
grep -F 'Copyright (c) 2026 Giang Nguyen' "$root/LICENSE" >/dev/null
if git -C "$root" grep -n -i 'firstagent' -- . ':!tests/test-factory.sh'; then
  echo 'private project name remains in tracked content' >&2; exit 1
fi

# Control: the committed clean-checkout harness runs every test outside its clone.
# FACTORY_CI_INNER prevents this assertion recursively invoking the harness.
if [[ ${FACTORY_CI_INNER:-} != 1 ]]; then
  "$root/bin/ci-clean-checkout" >"$scratch/ci.out"
  grep -F 'ci-clean-checkout: PASS (agent shims never invoked; ran ' "$scratch/ci.out" >/dev/null
  grep -F 'skipped 2 requiring a real agent' "$scratch/ci.out" >/dev/null
  grep -F 'tests/test-pi-project-rpc.py' "$scratch/ci.out" >/dev/null
  grep -F 'tests/test-crew.py::test_default_adapters_and_missing_fixture_name_the_adapter_defect' "$scratch/ci.out" >/dev/null
fi

printf '%s\n' 'test-factory: PASS'
