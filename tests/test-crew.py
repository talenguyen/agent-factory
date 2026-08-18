#!/usr/bin/env python3
"""Contract tests for bin/crew using its mock adapters only."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import uuid
from contextlib import contextmanager

ROOT = pathlib.Path(__file__).resolve().parents[1]
CREW = ROOT / "bin" / "crew"
PROFILE_FILES = (ROOT / "config/profiles.local.json", ROOT / "config/profiles.json")
BUNDLED_PROFILE_FILE = ROOT / ".claude/skills/delegate-to-pi/references/pi-profiles.json"


def bundled_profiles():
    return json.loads(BUNDLED_PROFILE_FILE.read_text())["profiles"]


@contextmanager
def isolated_profiles():
    """Keep profile-sensitive tests from touching the user's profile files."""
    originals = {
        path: path.read_bytes() if path.exists() else None
        for path in PROFILE_FILES
    }
    try:
        for path in PROFILE_FILES:
            path.unlink(missing_ok=True)
        yield
    finally:
        for path, contents in originals.items():
            if contents is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(contents)


def run(args, env, stdin=None, cwd=None):
    # Each contract starts in the project workspace even when its test launcher
    # runs from outside a fresh checkout.
    return subprocess.run([str(CREW), *args], input=stdin, text=True, capture_output=True, env=env, cwd=cwd or ROOT)


def fixture(path, agents=None, statuses=None):
    path.write_text(json.dumps({
        "capabilities": {"layout": False, "focus": False, "persistent_context": True,
                         "native_status": True, "banner": True, "isolation": True},
        "agents": agents or [], "statuses": statuses or {}, "reads": {},
    }))


def environment(tmp, fixture_path):
    return {**os.environ, "FACTORY_MUX": "mock", "FACTORY_WORKER": "mock",
            "FACTORY_MOCK_FIXTURE": str(fixture_path), "FACTORY_MOCK_STATE": str(tmp / "mock-state.json"),
            "TELEMETRY_LOG_DIR": str(tmp / "telemetry"), "CREW_TEST_MARKER": str(uuid.uuid4())}


def begin(tmp, env, tier="M"):
    result = run(["begin", "--tier", tier, "--domain", "software"], env)
    assert result.returncode == 0, result.stderr
    delegation = json.loads(result.stdout)["delegation_id"]
    env["FACTORY_CREW_DELEGATION_ID"] = delegation
    return delegation


def state(env):
    result = run(["state"], env)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_selection_fails_loudly(tmp):
    f = tmp / "fixture.json"; fixture(f)
    env = environment(tmp, f); env["FACTORY_MUX"] = "unknown"
    result = run(["doctor"], env)
    assert result.returncode != 0 and "missing mux adapter: unknown" in result.stderr


def test_malformed_capabilities_fail_loudly(tmp):
    f = tmp / "fixture.json"; fixture(f)
    data = json.loads(f.read_text()); data["capabilities"] = {"layout": "no"}; f.write_text(json.dumps(data))
    result = run(["doctor"], environment(tmp, f))
    assert result.returncode != 0 and "malformed mux capability document" in result.stderr


def test_default_adapters_and_missing_fixture_name_the_adapter_defect(tmp):
    default = run(["doctor"], {**os.environ, "TELEMETRY_LOG_DIR": str(tmp / "telemetry")})
    missing_fixture = run(["doctor"], {**os.environ, "FACTORY_MUX": "mock", "FACTORY_WORKER": "mock"})
    assert default.returncode == 0 and json.loads(default.stdout)["mux"]["native_status"] and missing_fixture.returncode != 0 and "FACTORY_MOCK_FIXTURE is required" in missing_fixture.stderr


def test_named_shell_adapter_executes_its_shebang(tmp):
    adapter = ROOT / "lib" / "crew" / "adapters" / "shell_fixture_mux"
    adapter.write_text("#!/usr/bin/env bash\n[ \"$1\" = crew_capabilities ] && printf '%s\\n' '{\"layout\":false,\"focus\":false,\"persistent_context\":false,\"native_status\":false,\"banner\":false,\"isolation\":false}'\n")
    adapter.chmod(0o755)
    try:
        f = tmp / "fixture.json"; fixture(f)
        env = environment(tmp, f); env["FACTORY_MUX"] = "shell_fixture"
        result = run(["doctor"], env)
        assert result.returncode == 0 and json.loads(result.stdout)["mux"]["native_status"] is False
    finally:
        adapter.unlink(missing_ok=True)


def test_delegation_id_can_follow_the_subcommand_and_begin_explains_it(tmp):
    f = tmp / "fixture.json"; fixture(f)
    env = environment(tmp, f)
    started = run(["begin", "--tier", "M", "--domain", "software"], env)
    delegation = json.loads(started.stdout)["delegation_id"]
    carried = run(["state", "--delegation-id", delegation], environment(tmp, f))
    assert started.returncode == 0 and f"--delegation-id {delegation}" in json.loads(started.stdout)["next"] and carried.returncode == 0 and json.loads(carried.stdout)["delegation_id"] == delegation


def test_spawn_forwards_stack_under_to_mux(tmp):
    f = tmp / "fixture.json"; fixture(f)
    env = environment(tmp, f); begin(tmp, env)
    result = run(["spawn", "--role", "reviewer", "--stack-under", "p-worker"], env)
    saved = json.loads(pathlib.Path(env["FACTORY_MOCK_STATE"]).read_text())
    assert result.returncode == 0 and saved["spawn_argv"][-1][:2] == ["--stack-under", "p-worker"]


def test_spawn_per_role_tier_uses_role_profiles_and_records_tiers(tmp):
    with isolated_profiles():
        f = tmp / "fixture.json"; fixture(f)
        env = environment(tmp, f); begin(tmp, env, "L")
        reviewer = run(["spawn", "--role", "reviewer", "--tier", "M"], env)
        worker = run(["spawn", "--role", "worker"], env)
        mock = json.loads(pathlib.Path(env["FACTORY_MOCK_STATE"]).read_text())
        reviewer_reply, worker_reply = json.loads(reviewer.stdout), json.loads(worker.stdout)
        reviewer_argv, worker_argv = mock["spawn_argv"]
        roles = state(env)["roles"]
        profiles = bundled_profiles()
        m_profile, l_profile = profiles["M"], profiles["L"]
        assert reviewer.returncode == 0 and worker.returncode == 0
        assert reviewer_argv[1:5] == ["mock-worker", m_profile["provider"], m_profile["model"], m_profile["thinking"]]
        assert worker_argv[1:5] == ["mock-worker", l_profile["provider"], l_profile["model"], l_profile["thinking"]]
        assert mock["verify_profiles"][0][1:] == [m_profile["provider"], m_profile["model"], m_profile["thinking"]]
        assert mock["verify_profiles"][1][1:] == [l_profile["provider"], l_profile["model"], l_profile["thinking"]]
        assert reviewer_reply["profile"]["model"] == m_profile["model"] and reviewer_reply["profile"]["thinking"] == m_profile["thinking"]
        assert worker_reply["profile"]["model"] == l_profile["model"] and worker_reply["profile"]["thinking"] == l_profile["thinking"]
        assert roles["reviewer"]["tier"] == "M" and roles["worker"]["tier"] == "L"


def test_spawn_same_role_tier_reuses_but_different_tier_does_not(tmp):
    with isolated_profiles():
        f = tmp / "fixture.json"; fixture(f)
        env = environment(tmp, f); begin(tmp, env, "L")
        first = run(["spawn", "--role", "reviewer", "--tier", "M"], env)
        second = run(["spawn", "--role", "reviewer", "--tier", "M"], env)
        different = run(["spawn", "--role", "reviewer", "--tier", "S"], env)
        first_reply, second_reply, different_reply = (json.loads(result.stdout) for result in (first, second, different))
        assert first.returncode == 0 and second.returncode == 0 and different.returncode == 0
        assert first_reply["reused"] is False and second_reply["reused"] is True and second_reply["id"] == first_reply["id"]
        assert different_reply["reused"] is False and different_reply["id"] != first_reply["id"]
        assert state(env)["roles"]["reviewer"]["tier"] == "S"


def test_fallback_uses_the_role_override_profile(tmp):
    with isolated_profiles():
        f = tmp / "fixture.json"; fixture(f)
        project = ROOT / "config/profiles.json"
        project.write_text(profile_table_with_model("project-model", {"S": "fallback-S", "M": "fallback-M", "L": "fallback-L"}))
        env = environment(tmp, f); begin(tmp, env, "L")
        spawned = run(["spawn", "--role", "reviewer", "--tier", "M"], env)
        fallback = run(["fallback", "--role", "reviewer"], env)
        mock = json.loads(pathlib.Path(env["FACTORY_MOCK_STATE"]).read_text())
        expected_fallback = bundled_profiles()["M"]["fallback"]
        assert spawned.returncode == 0 and fallback.returncode == 0
        assert mock["spawn_argv"][-1][1:5] == ["mock-worker", expected_fallback["provider"], "fallback-M", expected_fallback["thinking"]]
        assert mock["verify_profiles"][-1][1:] == [expected_fallback["provider"], "fallback-M", expected_fallback["thinking"]]


def test_no_tier_spawn_uses_begin_profile_snapshot(tmp):
    with isolated_profiles():
        f = tmp / "fixture.json"; fixture(f)
        project = ROOT / "config/profiles.json"
        project.write_text(profile_table_with_model("original-M"))
        env = environment(tmp, f); begin(tmp, env, "M")
        project.write_text(profile_table_with_model("mutated-M"))
        result = run(["spawn", "--role", "worker"], env)
        mock = json.loads(pathlib.Path(env["FACTORY_MOCK_STATE"]).read_text())
        reply = json.loads(result.stdout)
        expected_profile = bundled_profiles()["M"]
        assert result.returncode == 0
        assert mock["spawn_argv"][-1][1:5] == ["mock-worker", expected_profile["provider"], "original-M", expected_profile["thinking"]]
        assert mock["verify_profiles"][-1][1:] == [expected_profile["provider"], "original-M", expected_profile["thinking"]]
        assert reply["profile"]["model"] == "original-M"


def test_spawn_rejects_an_invalid_tier(tmp):
    f = tmp / "fixture.json"; fixture(f)
    env = environment(tmp, f); begin(tmp, env)
    result = run(["spawn", "--role", "worker", "--tier", "Q"], env)
    assert result.returncode != 0 and "Q" in result.stderr


def test_reuse_requires_role_tier_cwd_and_name(tmp):
    f = tmp / "fixture.json"
    fixture(f, agents=[
        {"id": "busy", "name": "crew-worker-M", "cwd": str(ROOT), "status": "working"},
        {"id": "wrong-tier", "name": "crew-worker-S", "cwd": str(ROOT), "status": "settled"},
        {"id": "unnamed", "name": None, "cwd": str(ROOT), "status": "settled"},
        {"id": "other-cwd", "name": "crew-worker-M", "cwd": "/elsewhere", "status": "settled"},
        {"id": "right", "name": "crew-worker-M", "cwd": str(ROOT), "status": "settled"},
    ])
    env = environment(tmp, f); begin(tmp, env)
    result = run(["spawn", "--role", "worker"], env)
    reply = json.loads(result.stdout)
    assert result.returncode == 0 and reply["id"] == "right" and reply["reused"] and reply["profile"]["model"] == bundled_profiles()["M"]["model"]


def test_banner_false_discovered_reuse_is_unverifiable(tmp):
    f = tmp / "fixture.json"
    fixture(f, agents=[{"id": "existing", "name": "crew-worker-M", "cwd": str(ROOT), "status": "settled"}])
    data = json.loads(f.read_text()); data["capabilities"]["banner"] = False; f.write_text(json.dumps(data))
    env = environment(tmp, f); begin(tmp, env)
    result = run(["spawn", "--role", "worker"], env)
    assert result.returncode == 0 and json.loads(result.stdout)["id"] == "existing" and json.loads(result.stdout)["reused"] and json.loads(result.stdout)["profile_verified"] == "unverifiable" and "cannot verify profile" in result.stderr


def test_reuse_name_boundary_accepts_variant_not_tier_prefix(tmp):
    f = tmp / "fixture.json"
    fixture(f, agents=[{"id": "mm", "name": "crew-worker-MM", "cwd": str(ROOT), "status": "settled"}, {"id": "variant", "name": "crew-worker-M-2", "cwd": str(ROOT), "status": "settled"}])
    env = environment(tmp, f); begin(tmp, env)
    result = run(["spawn", "--role", "worker"], env)
    assert result.returncode == 0 and json.loads(result.stdout)["id"] == "variant"


def test_capability_degradation_uses_sentinel_and_warns_for_no_banner(tmp):
    f = tmp / "fixture.json"; fixture(f, agents=[{"id": "w", "name": "crew-worker-M", "cwd": str(ROOT), "status": "settled"}])
    data = json.loads(f.read_text()); data["capabilities"]["native_status"] = False; data["reads"] = {"w": "done\nCREW_SETTLED"}; f.write_text(json.dumps(data))
    env = environment(tmp, f); begin(tmp, env); run(["spawn", "--role", "worker"], env)
    sentinel = run(["wait", "--role", "worker", "--timeout", "1", "--interval", "0"], env)
    data["capabilities"]["banner"] = False; data["capabilities"]["native_status"] = True; data["agents"] = []; f.write_text(json.dumps(data))
    env2 = environment(tmp, f); env2["FACTORY_MOCK_STATE"] = str(tmp / "banner-mock-state.json"); begin(tmp, env2)
    banner = run(["spawn", "--role", "worker"], env2)
    fallback = run(["fallback", "--role", "worker"], env2)
    assert sentinel.returncode == 0 and json.loads(sentinel.stdout)["path"] == "sentinel_marker" and banner.returncode == 0 and json.loads(banner.stdout)["profile_verified"] == "unverifiable" and fallback.returncode == 0 and json.loads(fallback.stdout)["profile_verified"] == "unverifiable" and "cannot verify profile" in banner.stderr


def test_interrupted_round_state_recovery(tmp):
    f = tmp / "fixture.json"; fixture(f)
    env = environment(tmp, f); delegation = begin(tmp, env)
    assert run(["round", "end", "--verdict", "changes_requested"], env).returncode == 0
    recovered = run(["--delegation-id", delegation, "state"], environment(tmp, f))
    assert recovered.returncode == 0 and json.loads(recovered.stdout)["round"] == 1


def test_profile_resolution_skips_absent_and_stops_malformed(tmp):
    with isolated_profiles():
        f = tmp / "fixture.json"; fixture(f)
        local = ROOT / "config" / "profiles.local.json"
        local.parent.mkdir(exist_ok=True); local.write_text("not json")
        result = run(["begin", "--tier", "M", "--domain", "software"], environment(tmp, f))
        assert result.returncode != 0 and "malformed profile table" in result.stderr


def profile_table_with_model(model, fallback_models=None):
    table = json.loads((ROOT / ".claude/skills/delegate-to-pi/references/pi-profiles.json").read_text())
    table["profiles"]["M"]["model"] = model
    for tier, fallback_model in (fallback_models or {}).items():
        table["profiles"][tier]["fallback"]["model"] = fallback_model
    return json.dumps(table)


def test_profile_local_source_wins_over_project_source(tmp):
    with isolated_profiles():
        f = tmp / "fixture.json"; fixture(f)
        local, project = ROOT / "config/profiles.local.json", ROOT / "config/profiles.json"
        local.parent.mkdir(exist_ok=True); local.write_text(profile_table_with_model("local-model")); project.write_text(profile_table_with_model("project-model"))
        env = environment(tmp, f); begin(tmp, env)
        assert state(env)["profile"]["model"] == "local-model"


def test_profile_project_source_wins_when_local_is_absent(tmp):
    with isolated_profiles():
        f = tmp / "fixture.json"; fixture(f)
        project = ROOT / "config/profiles.json"
        project.parent.mkdir(exist_ok=True); project.write_text(profile_table_with_model("project-model"))
        env = environment(tmp, f); begin(tmp, env)
        assert state(env)["profile"]["model"] == "project-model"


def test_profile_bundled_source_wins_when_local_sources_are_absent(tmp):
    with isolated_profiles():
        f = tmp / "fixture.json"; fixture(f)
        env = environment(tmp, f); begin(tmp, env)
        expected = bundled_profiles()["M"]["model"]
        assert state(env)["profile"]["model"] == expected


def test_isolated_profiles_restores_distinctive_local_sentinel_after_failure(tmp):
    local = ROOT / "config/profiles.local.json"
    sentinel = profile_table_with_model("sentinel-local-model").encode()
    with isolated_profiles():
        local.write_bytes(sentinel)
        test_profile_local_source_wins_over_project_source(tmp)
        assert local.read_bytes() == sentinel
        try:
            with isolated_profiles():
                local.write_bytes(b"mutated by scenario")
                raise AssertionError("exercise restoration on assertion failure")
        except AssertionError:
            pass
        assert local.read_bytes() == sentinel


def pack_root(tmp, command="printf verified"):
    directory = tmp / "packs"; directory.mkdir(parents=True, exist_ok=True)
    sections = {"Workspace layout": "layout", "Verify command": f"```bash\n{command}\n```", "Reviewer rubric": "rubric", "Risk gate": "risk", "Roles": "roles", "Definition of done": "done"}
    (directory / "software.md").write_text("\n".join(f"## {heading}\n{body}" for heading, body in sections.items()) + "\n")
    return directory


def test_domain_resolution_prefers_explicit_over_workspace_and_default(tmp):
    f = tmp / "fixture.json"; fixture(f); packs = pack_root(tmp)
    env = environment(tmp, f); env["FACTORY_DOMAIN_PACK_DIR"] = str(packs)
    workspace = tmp / "workspace"; workspace.mkdir(); (workspace / "WORKSPACE.md").write_text("domain: research\n")
    explicit = run(["begin", "--tier", "M", "--domain", "software"], env, cwd=workspace)
    assert explicit.returncode == 0 and json.loads(explicit.stdout)["delegation_id"]
    (packs / "research.md").write_text((packs / "software.md").read_text())
    from_workspace = run(["begin", "--tier", "M"], env, cwd=workspace)
    assert from_workspace.returncode == 0 and json.loads(run(["state", "--delegation-id", json.loads(from_workspace.stdout)["delegation_id"]], env).stdout)["domain"] == "research"
    (workspace / "WORKSPACE.md").unlink()
    fallback = run(["begin", "--tier", "M"], env, cwd=workspace)
    assert fallback.returncode == 0 and json.loads(run(["state", "--delegation-id", json.loads(fallback.stdout)["delegation_id"]], env).stdout)["domain"] == "software"


def test_begin_rejects_each_missing_required_pack_section(tmp):
    f = tmp / "fixture.json"; fixture(f)
    for section in ("Workspace layout", "Verify command", "Reviewer rubric", "Risk gate", "Roles", "Definition of done"):
        packs = pack_root(tmp / section.replace(" ", "-")); path = packs / "software.md"
        path.write_text(path.read_text().replace(f"## {section}\n", "", 1))
        env = environment(tmp, f); env["FACTORY_DOMAIN_PACK_DIR"] = str(packs)
        result = run(["begin", "--tier", "M", "--domain", "software"], env)
        assert result.returncode != 0 and section in result.stderr


def test_verify_cli_rejects_comment_and_blank_only_pack_commands(tmp):
    for index, content in enumerate(("# documentation only\n\n", "\n", "\n\n")):
        f = tmp / f"fixture-{index}.json"; fixture(f)
        packs = pack_root(tmp / str(index), content)
        env = environment(tmp / str(index), f); env["FACTORY_DOMAIN_PACK_DIR"] = str(packs)
        begin(tmp, env)
        result = run(["verify"], env)
        assert result.returncode != 0 and "missing runnable Verify command" in result.stderr


def test_verify_cli_executes_multiline_and_comment_prefixed_pack_commands(tmp):
    f = tmp / "fixture.json"; fixture(f); marker = tmp / "executed"
    packs = pack_root(tmp, f"# setup note\nprintf first > {marker}\nprintf second >> {marker}")
    env = environment(tmp, f); env["FACTORY_DOMAIN_PACK_DIR"] = str(packs)
    begin(tmp, env)
    result = run(["verify"], env)
    assert result.returncode == 0 and marker.read_text() == "firstsecond"


def test_begin_rejects_a_missing_domain_pack(tmp):
    f = tmp / "fixture.json"; fixture(f)
    result = run(["begin", "--tier", "M", "--domain", "missing-domain"], environment(tmp, f))
    assert result.returncode != 0 and "missing domain pack" in result.stderr


def test_saved_bannerless_reuse_warns_that_profile_is_unverifiable(tmp):
    f = tmp / "fixture.json"
    fixture(f, agents=[{"id": "w", "name": "crew-worker-M", "cwd": str(ROOT), "status": "settled"}])
    data = json.loads(f.read_text()); data["capabilities"]["banner"] = False; f.write_text(json.dumps(data))
    env = environment(tmp, f); begin(tmp, env)
    assert run(["spawn", "--role", "worker"], env).returncode == 0
    result = run(["spawn", "--role", "worker"], env)
    reply = json.loads(result.stdout)
    assert result.returncode == 0 and reply["reused"] and reply["profile_verified"] == "unverifiable" and "cannot verify profile" in result.stderr


def test_reuse_revalidates_saved_agent_status(tmp):
    f = tmp / "fixture.json"
    fixture(f, agents=[{"id": "w", "name": "crew-worker-M", "cwd": str(ROOT), "status": "settled"}])
    env = environment(tmp, f); begin(tmp, env)
    first = run(["spawn", "--role", "worker"], env)
    mock = json.loads(pathlib.Path(env["FACTORY_MOCK_STATE"]).read_text())
    mock["agents"][0]["status"] = "closed"; pathlib.Path(env["FACTORY_MOCK_STATE"]).write_text(json.dumps(mock))
    second = run(["spawn", "--role", "worker"], env)
    assert first.returncode == 0 and json.loads(first.stdout)["reused"] and second.returncode == 0 and not json.loads(second.stdout)["reused"] and json.loads(second.stdout)["id"] != "w"


def test_role_sessions_are_distinct_and_scout_is_fresh(tmp):
    f = tmp / "fixture.json"; fixture(f)
    env = environment(tmp, f); begin(tmp, env)
    for name in ("worker", "reviewer", "scout"):
        assert run(["spawn", "--role", name], env).returncode == 0
    first_scout = state(env)["roles"]["scout"]["session_id"]
    assert run(["spawn", "--role", "scout"], env).returncode == 0
    roles = state(env)["roles"]
    assert len({roles["worker"]["session_id"], roles["reviewer"]["session_id"], roles["scout"]["session_id"]}) == 3 and roles["scout"]["session_id"] != first_scout


def test_wait_routes_rate_limit_output_to_failed(tmp):
    f = tmp / "fixture.json"
    fixture(f, agents=[{"id": "w", "name": "crew-worker-M", "cwd": str(ROOT), "status": "settled"}])
    data = json.loads(f.read_text()); data["reads"] = {"w": "Quota exceeded by provider"}; f.write_text(json.dumps(data))
    env = environment(tmp, f); begin(tmp, env); run(["spawn", "--role", "worker"], env)
    result = run(["wait", "--role", "worker", "--timeout", "61", "--interval", "0"], env)
    assert result.returncode == 0 and json.loads(result.stdout)["outcome"] == "failed" and json.loads(result.stdout)["path"] == "rate_limit"


def test_fallback_is_once_per_role(tmp):
    f = tmp / "fixture.json"; fixture(f)
    env = environment(tmp, f); begin(tmp, env)
    assert run(["spawn", "--role", "worker"], env).returncode == 0
    assert run(["spawn", "--role", "reviewer"], env).returncode == 0
    first = run(["fallback", "--role", "worker"], env)
    other = run(["fallback", "--role", "reviewer"], env)
    second = run(["fallback", "--role", "worker"], env)
    mock = json.loads(pathlib.Path(env["FACTORY_MOCK_STATE"]).read_text())
    fallback_model = bundled_profiles()["M"]["fallback"]["model"]
    assert first.returncode == 0 and other.returncode == 0 and second.returncode != 0 and state(env)["state"] == "escalated" and any(fallback_model in args for args in mock["spawn_argv"]) and len(mock["verify_profiles"]) == 4


def test_round_cap_escalates_and_blocks_send(tmp):
    f = tmp / "fixture.json"; fixture(f)
    env = environment(tmp, f); begin(tmp, env)
    for _ in range(5):
        assert run(["round", "end", "--verdict", "changes_requested"], env).returncode == 0
    cap = run(["round", "end", "--verdict", "changes_requested"], env)
    blocked = run(["send", "--role", "worker"], env, "do not run")
    assert cap.returncode != 0 and json.loads(cap.stdout)["state"] == "escalated" and blocked.returncode != 0


def test_turn_cap_and_no_progress_escalate(tmp):
    f = tmp / "fixture.json"; fixture(f)
    env = environment(tmp, f); begin(tmp, env, "S")
    for _ in range(6):
        assert run(["turn", "end"], env).returncode == 0
    assert run(["turn", "end"], env).returncode != 0
    f2 = tmp / "fixture2.json"; fixture(f2)
    env2 = environment(tmp, f2); begin(tmp, env2)
    assert run(["round", "end", "--verdict", "changes_requested", "--diff-hash", "same"], env2).returncode == 0
    assert run(["round", "end", "--verdict", "changes_requested", "--diff-hash", "same"], env2).returncode != 0


def test_wait_debounces_stale_and_reports_escape_hatch(tmp):
    f = tmp / "fixture.json"
    fixture(f, agents=[{"id": "w", "name": "crew-worker-M", "cwd": str(ROOT), "status": "settled"}],
            statuses={"w": ["settled", "settled", "settled", "working", "settled", "settled", "settled"]})
    env = environment(tmp, f); begin(tmp, env); run(["spawn", "--role", "worker"], env)
    normal = run(["wait", "--role", "worker", "--timeout", "10", "--interval", "0"], env)
    assert normal.returncode == 0 and json.loads(normal.stdout)["path"] == "after_unsettled" and len(json.loads(pathlib.Path(env["FACTORY_MOCK_STATE"]).read_text())["status_reads"]) == 7
    f2 = tmp / "fixture2.json"
    fixture(f2, agents=[{"id": "w", "name": "crew-worker-M", "cwd": str(ROOT), "status": "settled"}], statuses={"w": ["settled"] * 61})
    env2 = environment(tmp, f2); begin(tmp, env2); run(["spawn", "--role", "worker"], env2)
    escape = run(["wait", "--role", "worker", "--timeout", "61", "--interval", "0"], env2)
    assert escape.returncode == 0 and json.loads(escape.stdout)["path"] == "all_settled_escape_hatch" and len(json.loads(pathlib.Path(env2["FACTORY_MOCK_STATE"]).read_text())["status_reads"]) >= 60


def test_factory_anchor_and_concurrent_delegations(tmp):
    f = tmp / "fixture.json"; fixture(f)
    unrelated = tmp / "unrelated"; unrelated.mkdir(); subprocess.run(["git", "init", "-q", str(unrelated)], check=True)
    (unrelated / "config").mkdir(); (unrelated / "config" / "profiles.local.json").write_text("not json")
    first_env, second_env = environment(tmp, f), environment(tmp, f)
    first_result = subprocess.run([str(CREW), "begin", "--tier", "M", "--domain", "software"], text=True, capture_output=True, env=first_env, cwd=unrelated)
    first = json.loads(first_result.stdout)["delegation_id"]
    second = begin(tmp, second_env)
    change = run(["--delegation-id", first, "round", "end", "--verdict", "approved"], first_env)
    untouched = run(["--delegation-id", second, "state"], second_env)
    common = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "--git-common-dir"], text=True).strip()
    common_path = pathlib.Path(common)
    if not common_path.is_absolute(): common_path = ROOT / common_path
    anchored = common_path.resolve().parent / ".factory" / "crew" / first / "state.json"
    assert first_result.returncode == 0 and anchored.exists() and not (unrelated / ".factory").exists() and change.returncode == 0 and json.loads(untouched.stdout)["round"] == 0


def test_telemetry_uses_exactly_the_canonical_eight_events(tmp):
    f = tmp / "fixture.json"; fixture(f)
    env = environment(tmp, f); begin(tmp, env); run(["spawn", "--role", "worker"], env); run(["spawn", "--role", "worker"], env); run(["fallback", "--role", "worker"], env)
    for _ in range(5): run(["round", "end", "--verdict", "approved"], env)
    run(["round", "end", "--verdict", "approved"], env); run(["end", "--outcome", "escalated"], env)
    env2 = environment(tmp, f); env2["TELEMETRY_LOG_DIR"] = env["TELEMETRY_LOG_DIR"]; begin(tmp, env2, "S")
    for _ in range(7): run(["turn", "end"], env2)
    env3 = environment(tmp, f); env3["TELEMETRY_LOG_DIR"] = env["TELEMETRY_LOG_DIR"]; begin(tmp, env3); run(["spawn", "--role", "worker"], env3); run(["fallback", "--role", "worker"], env3); run(["fallback", "--role", "worker"], env3)
    events = {json.loads(line)["event"] for line in (pathlib.Path(env["TELEMETRY_LOG_DIR"]) / "events.jsonl").read_text().splitlines()}
    assert events == {"pi_spawn", "pi_reuse", "pi_fallback", "pi_crew_round", "pi_crew_round_cap_hit", "pi_turn_cap_hit", "pi_escalated", "pi_delegation_end"}


def test_state_ledger_and_telemetry_are_shared_and_isolated(tmp):
    f = tmp / "fixture.json"; fixture(f)
    env = environment(tmp, f); delegation = begin(tmp, env)
    assert run(["spawn", "--role", "worker"], env).returncode == 0
    assert run(["ledger", "append", "Round 1: reviewer APPROVED."], env).returncode == 0
    current = state(env)
    common_dir = pathlib.Path(subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "--git-common-dir"], text=True).strip())
    if not common_dir.is_absolute():
        common_dir = ROOT / common_dir
    ledger = common_dir.resolve().parent / ".factory" / "crew" / delegation / "progress.md"
    events = pathlib.Path(env["TELEMETRY_LOG_DIR"]) / "events.jsonl"
    assert current["round"] == 0 and ledger.read_text() == "Round 1: reviewer APPROVED.\n" and all(json.loads(line)["domain"] == "software" for line in events.read_text().splitlines())


def main():
    checks = (test_selection_fails_loudly, test_malformed_capabilities_fail_loudly, test_default_adapters_and_missing_fixture_name_the_adapter_defect, test_named_shell_adapter_executes_its_shebang, test_delegation_id_can_follow_the_subcommand_and_begin_explains_it, test_spawn_forwards_stack_under_to_mux, test_spawn_per_role_tier_uses_role_profiles_and_records_tiers, test_spawn_same_role_tier_reuses_but_different_tier_does_not, test_fallback_uses_the_role_override_profile, test_no_tier_spawn_uses_begin_profile_snapshot, test_spawn_rejects_an_invalid_tier, test_reuse_requires_role_tier_cwd_and_name, test_banner_false_discovered_reuse_is_unverifiable, test_reuse_name_boundary_accepts_variant_not_tier_prefix, test_capability_degradation_uses_sentinel_and_warns_for_no_banner, test_interrupted_round_state_recovery, test_profile_resolution_skips_absent_and_stops_malformed, test_profile_local_source_wins_over_project_source, test_profile_project_source_wins_when_local_is_absent, test_profile_bundled_source_wins_when_local_sources_are_absent, test_isolated_profiles_restores_distinctive_local_sentinel_after_failure, test_domain_resolution_prefers_explicit_over_workspace_and_default, test_begin_rejects_each_missing_required_pack_section, test_verify_cli_rejects_comment_and_blank_only_pack_commands, test_verify_cli_executes_multiline_and_comment_prefixed_pack_commands, test_begin_rejects_a_missing_domain_pack, test_saved_bannerless_reuse_warns_that_profile_is_unverifiable, test_reuse_revalidates_saved_agent_status, test_role_sessions_are_distinct_and_scout_is_fresh, test_wait_routes_rate_limit_output_to_failed,
              test_fallback_is_once_per_role, test_round_cap_escalates_and_blocks_send,
              test_turn_cap_and_no_progress_escalate, test_wait_debounces_stale_and_reports_escape_hatch,
              test_factory_anchor_and_concurrent_delegations, test_telemetry_uses_exactly_the_canonical_eight_events, test_state_ledger_and_telemetry_are_shared_and_isolated)
    selected = {check.__name__: check for check in checks}
    if len(sys.argv) > 1:
        checks = (selected[sys.argv[1]],)
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        for check in checks:
            case_dir = tmp / check.__name__
            case_dir.mkdir()
            with isolated_profiles():
                check(case_dir)
    print("test-crew: PASS")


if __name__ == "__main__":
    main()
