#!/usr/bin/env python3
import json
import pathlib
import tempfile
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
        append_event(run, "ledger", stage, "completed", {})
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
        for name in ("plan.md", "context.md"):
            original = (run / name).read_text()
            (run / name).unlink(); raises(lambda: validate_run(run, terminal=True), name)
            (run / name).write_text(original)
        (run / "context.md").write_text("TBD")
        raises(lambda: validate_run(run, terminal=True), "placeholder")
        (run / "context.md").write_text("recorded")
        (run / "outcome.json").write_text('{')
        raises(lambda: validate_run(run, terminal=True), "outcome.json")
    print("test-workflow-runs: PASS")

if __name__ == "__main__": main()
