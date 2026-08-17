#!/usr/bin/env python3
import json
import pathlib
import tempfile
import os
import shutil
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
from workflow.runs import WorkflowError, append_event, create_run, validate_run


def raises(fn, text=None):
    try: fn()
    except WorkflowError as exc:
        if text: assert text in str(exc), str(exc)
    else: raise AssertionError("expected WorkflowError")


def complete(run):
    (run / "classification.json").write_text(json.dumps({"tier": "S", "domain": "software"}))
    for name in ("context.md", "plan.md", "acceptance.md"):
        (run / name).write_text("recorded facts\n")
    (run / "evidence" / "verify.log").write_text("exit 0\n")
    for stage in ("classify", "retrieve_context", "plan", "execute_loop", "observe_and_verify", "policy_gate"):
        details = {"evidence": ["evidence/verify.log"]} if stage == "observe_and_verify" else {}
        append_event(run, "ledger", stage, "completed", details)
    append_event(run, "ledger", "respond", "completed", {"evidence": ["evidence/verify.log"]})
    (run / "outcome.json").write_text(json.dumps({"outcome": "goal_met", "evidence": ["evidence/verify.log"]}))


def main():
    with tempfile.TemporaryDirectory() as tmp:
        workspace = pathlib.Path(tmp).resolve()
        record = create_run(workspace, "autonomous-goal", "Fix the parser")
        run = pathlib.Path(record["path"])
        assert run.parent == workspace / ".factory" / "runs"
        assert json.loads((run / "run.json").read_text())["entry_point"] == "autonomous-goal"
        assert "Fix the parser" in (run / "intake.md").read_text()
        assert json.loads((run / "ledger.jsonl").read_text().splitlines()[0])["sequence"] == 1
        assert append_event(run, "ledger", "classify", "completed", {"tier": "S"})["sequence"] == 2
        raises(lambda: append_event(run, "audit", "classify", "x", {}))
        raises(lambda: append_event(run, "ledger", "build", "x", {}))
        raises(lambda: append_event(run, "ledger", "plan", "x", []))
        raises(lambda: append_event(run, "ledger", "plan", "x", {"evidence": ["../secret.log"]}))
        validate_run(run)
        complete(run)
        validate_run(run, terminal=True)
        valid_ledger = (run / "ledger.jsonl").read_text()
        # Each terminal outcome has one exact final respond event.
        for terminal_outcome, terminal_event in (("goal_met", "completed"), ("blocked", "blocked"), ("escalated", "escalated"), ("cancelled", "cancelled")):
            lines = valid_ledger.splitlines(); final = json.loads(lines[-1]); final["event"] = terminal_event
            lines[-1] = json.dumps(final); (run / "ledger.jsonl").write_text("\n".join(lines) + "\n")
            (run / "outcome.json").write_text(json.dumps({"outcome": terminal_outcome, "evidence": ["evidence/verify.log"]}))
            validate_run(run, terminal=True)
        (run / "ledger.jsonl").write_text(valid_ledger)
        (run / "outcome.json").write_text(json.dumps({"outcome": "goal_met", "evidence": ["evidence/verify.log"]}))
        lines = [json.loads(line) for line in valid_ledger.splitlines()]
        for entry in lines:
            if entry["stage"] == "observe_and_verify": entry["details"] = {}
        (run / "ledger.jsonl").write_text("\n".join(json.dumps(entry) for entry in lines) + "\n")
        raises(lambda: validate_run(run, terminal=True), "observe_and_verify evidence")
        (run / "ledger.jsonl").write_text(valid_ledger)
        for name in ("plan.md", "context.md"):
            original = (run / name).read_text()
            (run / name).unlink(); raises(lambda: validate_run(run, terminal=True), name)
            (run / name).write_text(original)
        (run / "context.md").write_text("TBD")
        raises(lambda: validate_run(run, terminal=True), "placeholder")
        (run / "context.md").write_text("recorded")
        (run / "outcome.json").write_text('{')
        raises(lambda: validate_run(run, terminal=True), "outcome.json")

        # Terminal status must agree with the final respond event.
        (run / "outcome.json").write_text(json.dumps({"outcome": "goal_met", "evidence": ["evidence/verify.log"]}))
        ledger = (run / "ledger.jsonl").read_text().splitlines()
        final = json.loads(ledger[-1]); final["event"] = "blocked"
        ledger[-1] = json.dumps(final); (run / "ledger.jsonl").write_text("\n".join(ledger) + "\n")
        raises(lambda: validate_run(run, terminal=True), "contradictory")

        # A skipped lifecycle stage and invalid run metadata are rejected.
        ledger[-1] = json.dumps({**final, "event": "completed", "sequence": 2})
        ledger = [ledger[0], ledger[-1]]
        (run / "ledger.jsonl").write_text("\n".join(ledger) + "\n")
        raises(lambda: validate_run(run, terminal=True), "transition")
        (run / "ledger.jsonl").write_text("\n".join([json.dumps(json.loads(line)) for line in ledger]) + "\n")
        metadata_path = run / "run.json"
        metadata = json.loads(metadata_path.read_text()); metadata["run_id"] = "not-a-uuid"
        metadata_path.write_text(json.dumps(metadata))
        raises(lambda: validate_run(run), "run_id")

        # Evidence references must not escape through symlinks.
        metadata["run_id"] = run.name; metadata_path.write_text(json.dumps(metadata))
        (run / "ledger.jsonl").write_text(valid_ledger)
        # Restore the valid terminal outcome after the mutations above.
        (run / "outcome.json").write_text(json.dumps({"outcome": "goal_met", "evidence": ["evidence/verify.log"]}))
        outside = workspace / "outside.log"; outside.write_text("secret")
        link = run / "evidence" / "linked.log"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            pass
        else:
            final = json.loads((run / "ledger.jsonl").read_text().splitlines()[-1])
            final["details"] = {"evidence": ["evidence/linked.log"]}
            lines = (run / "ledger.jsonl").read_text().splitlines(); lines[-1] = json.dumps(final)
            (run / "ledger.jsonl").write_text("\n".join(lines) + "\n")
            raises(lambda: validate_run(run), "outside")
        link.unlink(missing_ok=True)
        (run / "ledger.jsonl").write_text(valid_ledger)

        # The evidence root itself cannot be a symlink.
        outside_dir = workspace / "outside-evidence"; outside_dir.mkdir()
        outside_file = outside_dir / "verify.log"; outside_file.write_text("secret")
        evidence_root = run / "evidence"; real_evidence = run / "evidence-real"
        evidence_root.rename(real_evidence); evidence_root.symlink_to(outside_dir, target_is_directory=True)
        raises(lambda: validate_run(run, terminal=True), "evidence directory")
        evidence_root.unlink(); real_evidence.rename(evidence_root)

        # A goal_met record must include completed independent observation.
        lines = [json.loads(line) for line in valid_ledger.splitlines()]
        lines = [entry for entry in lines if entry["stage"] != "observe_and_verify"]
        for sequence, entry in enumerate(lines, 1): entry["sequence"] = sequence
        (run / "ledger.jsonl").write_text("\n".join(json.dumps(entry) for entry in lines) + "\n")
        raises(lambda: validate_run(run, terminal=True), "observe_and_verify")
    print("test-workflow-runs: PASS")

if __name__ == "__main__": main()
