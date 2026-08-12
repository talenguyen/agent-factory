#!/usr/bin/env python3
"""Contract tests for crew classify-risk."""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(os.environ.get("CLASSIFIER_ROOT", pathlib.Path(__file__).resolve().parents[1]))
CREW = ROOT / "bin" / "crew"


def run(question, root=ROOT):
    with tempfile.TemporaryDirectory() as directory:
        fixture = pathlib.Path(directory) / "fixture.json"
        fixture.write_text(json.dumps({"capabilities": {"layout": False, "focus": False,
                           "persistent_context": True, "native_status": True, "banner": True,
                           "isolation": True}, "agents": [], "statuses": {}, "reads": {}}))
        env = {**os.environ, "CREW_LIB_ROOT": str(root / "lib"), "FACTORY_MUX": "mock",
               "FACTORY_WORKER": "mock", "FACTORY_MOCK_FIXTURE": str(fixture),
               "FACTORY_MOCK_STATE": str(pathlib.Path(directory) / "mock-state.json"),
               "TELEMETRY_LOG_DIR": str(pathlib.Path(directory) / "telemetry")}
        begun = subprocess.run([str(root / "bin" / "crew"), "begin", "--tier", "M", "--domain", "software"],
                               text=True, capture_output=True, env=env)
        if begun.returncode:
            return begun
        env["FACTORY_CREW_DELEGATION_ID"] = json.loads(begun.stdout)["delegation_id"]
        return subprocess.run([str(root / "bin" / "crew"), "classify-risk"], input=question,
                              text=True, capture_output=True, env=env)


def policy_paraphrases_are_caught():
    cases = {
        "Destructive git operations": ("May I force-push this branch?", "Can I rewrite the commit history?"),
        "Destructive filesystem operations": ("Can I run rm -rf on the generated directory?", "May I delete these generated files?"),
        "Secrets and credentials": ("Please read the API token from .env.keys.", "May I reveal a credential?"),
        "Production systems and live customer data": ("Can I query the production database?", "Should I drop the production users table?"),
        "Outward-facing actions": ("Can I email the finished report to the client?", "May I pay for the API access?"),
    }
    for category, questions in cases.items():
        for question in questions:
            result = run(question)
            assert result.returncode == 0, result.stderr
            assert json.loads(result.stdout)["matches"] == [category]


def reviewer_gap_paraphrases_are_caught():
    cases = {
        "Can I erase the commit graph?": "Destructive git operations",
        "Can I unlink this file?": "Destructive filesystem operations",
        "May I expose the database password in the report?": "Secrets and credentials",
        "Should I open a pull request for this change?": "Outward-facing actions",
    }
    for question, category in cases.items():
        result = run(question)
        assert result.returncode == 0, result.stderr
        assert category in json.loads(result.stdout)["matches"]


def pack_prohibition_and_no_match():
    pack = run("Can I deploy to production?")
    harmless = run("What test command should I run?")
    assert pack.returncode == 0 and "software Risk gate" in json.loads(pack.stdout)["matches"]
    reply = json.loads(harmless.stdout)
    assert harmless.returncode == 0 and reply["matches"] == [] and not reply["keyword_match"] and reply["must_still_judge"]


def local_overlay_adds_a_prohibition():
    with tempfile.TemporaryDirectory() as directory:
        copy = pathlib.Path(directory) / "factory"
        shutil.copytree(ROOT / "bin", copy / "bin")
        shutil.copytree(ROOT / "lib", copy / "lib")
        shutil.copytree(ROOT / ".claude", copy / ".claude")
        shutil.copy2(ROOT / "POLICY.md", copy / "POLICY.md")
        (copy / "POLICY.local.md").write_text("# Local policy\n\n## Moonbeam operations\nDo not use the moonbeam protocol without approval.\n")
        subprocess.run(["git", "init", "-q", str(copy)], check=True)
        result = run("May I use the moonbeam protocol?", copy)
    assert result.returncode == 0 and "Moonbeam operations" in json.loads(result.stdout)["matches"]


def missing_policy_is_named_failure():
    with tempfile.TemporaryDirectory() as directory:
        copy = pathlib.Path(directory) / "factory"
        shutil.copytree(ROOT / "bin", copy / "bin")
        shutil.copytree(ROOT / "lib", copy / "lib")
        shutil.copytree(ROOT / ".claude", copy / ".claude")
        subprocess.run(["git", "init", "-q", str(copy)], check=True)
        result = run("May I force-push?", copy)
    assert result.returncode != 0 and "POLICY.md" in result.stderr


def mutation_harness():
    mutations = {
        "policy_category_terms": (
            '        terms |= RISK_HINTS.get(heading, set())',
            '        terms = set()',
        ),
        "must_still_judge": ('"must_still_judge": True', '"must_still_judge": False'),
        "missing_policy_no_match": (
            'if not path.exists(): raise CrewError(f"missing policy file: {path}")',
            'if not path.exists(): return {name: "" for name in POLICY_CATEGORIES}',
        ),
    }
    with tempfile.TemporaryDirectory() as directory:
        for name, (old, new) in mutations.items():
            mutant = pathlib.Path(directory) / name
            shutil.copytree(ROOT, mutant, ignore=shutil.ignore_patterns(".git", ".factory", "var"))
            subprocess.run(["git", "init", "-q", str(mutant)], check=True)
            core = mutant / "lib" / "crew" / "core.py"
            text = core.read_text()
            assert text.count(old) == 1, (name, text.count(old))
            core.write_text(text.replace(old, new))
            env = {**os.environ, "CLASSIFIER_ROOT": str(mutant), "SKIP_MUTATION_CHECK": "1"}
            broken = subprocess.run([sys.executable, str(mutant / "tests" / "test-crew-classify-risk.py")], env=env)
            restored = subprocess.run([sys.executable, str(ROOT / "tests" / "test-crew-classify-risk.py")],
                                     env={**os.environ, "SKIP_MUTATION_CHECK": "1"})
            if restored.returncode != 0:
                raise AssertionError(f"{name}: control failed with exit {restored.returncode}; mutation evidence is invalid")
            if broken.returncode == 0:
                raise AssertionError(f"{name}: mutation unexpectedly passed")
            print(f"{name}: broken_exit={broken.returncode} restored_exit={restored.returncode}")


def main():
    policy_paraphrases_are_caught()
    reviewer_gap_paraphrases_are_caught()
    pack_prohibition_and_no_match()
    local_overlay_adds_a_prohibition()
    missing_policy_is_named_failure()
    if not os.environ.get("SKIP_MUTATION_CHECK"):
        mutation_harness()
    print("test-crew-classify-risk: PASS")


if __name__ == "__main__":
    main()
