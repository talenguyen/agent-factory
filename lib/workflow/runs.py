"""Dependency-free durable records for the shared orchestrator lifecycle."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
STAGES = (
    "intake", "classify", "retrieve_context", "plan", "execute_loop",
    "observe_and_verify", "human_approval", "policy_gate", "respond",
)
TERMINAL_OUTCOMES = ("goal_met", "blocked", "escalated", "cancelled")
ALLOWED_NEXT = {
    "intake": {"intake", "classify"},
    "classify": {"classify", "retrieve_context"},
    "retrieve_context": {"retrieve_context", "plan"},
    "plan": {"plan", "execute_loop"},
    "execute_loop": {"execute_loop", "observe_and_verify", "policy_gate"},
    "observe_and_verify": {"observe_and_verify", "retrieve_context", "execute_loop", "human_approval", "policy_gate"},
    "human_approval": {"human_approval", "execute_loop", "policy_gate", "respond"},
    "policy_gate": {"policy_gate", "execute_loop", "respond"},
    "respond": {"respond"},
}

class WorkflowError(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stream_path(run_dir: Path, stream: str) -> Path:
    if stream not in ("ledger", "policy"):
        raise WorkflowError(f"{run_dir}: unknown stream {stream}")
    return run_dir / f"{stream}.jsonl"


def _resolved_evidence_path(run_dir: Path, value: str) -> Path:
    """Return a contained evidence path, including symlink resolution."""
    evidence_dir = run_dir / "evidence"
    if evidence_dir.is_symlink() or not evidence_dir.is_dir():
        raise WorkflowError(f"{run_dir}: evidence directory must be a real directory")
    root = evidence_dir.resolve()
    candidate = (run_dir / value).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise WorkflowError(f"{run_dir}: evidence target outside evidence: {value}") from exc
    return candidate


def _check_details(details: object, run_dir: Path) -> dict:
    if not isinstance(details, dict):
        raise WorkflowError(f"{run_dir}: event details must be an object")
    evidence = details.get("evidence", [])
    if evidence is not None and (not isinstance(evidence, list) or any(not isinstance(p, str) for p in evidence)):
        raise WorkflowError(f"{run_dir}: evidence must be an array of paths")
    for value in evidence or []:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts or not (path.parts and (path.parts[0] == "evidence" or value.startswith("evidence/"))):
            raise WorkflowError(f"{run_dir}: invalid evidence path {value}")
        _resolved_evidence_path(run_dir, value)
    return details


def create_run(workspace: Path, entry_point: str, goal: str) -> dict:
    workspace = Path(workspace).resolve()
    if entry_point not in ("autonomous-goal", "orchestrate"):
        raise WorkflowError(f"entry point is unsupported: {entry_point}")
    if not isinstance(goal, str) or not goal.strip():
        raise WorkflowError("goal must be non-empty")
    root = workspace / ".factory" / "runs"
    root.mkdir(parents=True, exist_ok=True)
    run_id = str(uuid.uuid4())
    run_dir = root / run_id
    run_dir.mkdir(exist_ok=False)
    (run_dir / "evidence").mkdir()
    metadata = {"entry_point": entry_point, "run_id": run_id, "schema_version": SCHEMA_VERSION,
                "workspace": str(workspace), "created_at": _now()}
    (run_dir / "run.json").write_text(json.dumps(metadata, sort_keys=True) + "\n")
    (run_dir / "intake.md").write_text(f"# Intake\n\n{goal.strip()}\n")
    (run_dir / "policy.jsonl").write_text("")
    append_event(run_dir, "ledger", "intake", "created", {"goal": goal.strip()})
    return {"run_id": run_id, "path": str(run_dir)}


def _read_events(path: Path, validate_transitions: bool = False) -> list[dict]:
    if not path.exists():
        raise WorkflowError(f"{path}: missing stream")
    events = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        try: record = json.loads(line)
        except json.JSONDecodeError as exc: raise WorkflowError(f"{path}:{number}: malformed JSON") from exc
        if not isinstance(record, dict) or not all(key in record for key in ("sequence", "timestamp", "stage", "event", "details")):
            raise WorkflowError(f"{path}:{number}: malformed event")
        if record["sequence"] != number:
            raise WorkflowError(f"{path}:{number}: sequence must be {number}")
        if record["stage"] not in STAGES:
            raise WorkflowError(f"{path}:{number}: unknown stage {record['stage']}")
        _check_details(record["details"], path.parent)
        for evidence in record["details"].get("evidence", []) or []:
            evidence_path = _resolved_evidence_path(path.parent, evidence)
            if not evidence_path.is_file():
                raise WorkflowError(f"{path}:{number}: missing evidence {evidence}")
        if validate_transitions and events and record["stage"] not in ALLOWED_NEXT[events[-1]["stage"]]:
            raise WorkflowError(f"{path}:{number}: invalid transition to {record['stage']}")
        events.append(record)
    return events


def append_event(run_dir: Path, stream: str, stage: str, event: str, details: dict) -> dict:
    run_dir = Path(run_dir)
    path = _stream_path(run_dir, stream)
    if not run_dir.is_dir():
        raise WorkflowError(f"unknown run: {run_dir}")
    if stage not in STAGES:
        raise WorkflowError(f"{run_dir}: unknown stage {stage}")
    details = _check_details(details, run_dir)
    prior = _read_events(path) if path.exists() else []
    entry = {"sequence": len(prior) + 1, "timestamp": _now(), "stage": stage, "event": event, "details": details}
    with path.open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def _check_evidence(run_dir: Path, values: object) -> None:
    if not isinstance(values, list) or not values:
        raise WorkflowError(f"{run_dir / 'outcome.json'}: evidence must be non-empty")
    _check_details({"evidence": values}, run_dir)
    for value in values:
        path = _resolved_evidence_path(run_dir, value)
        if not path.is_file():
            raise WorkflowError(f"{run_dir}: missing evidence {value}")


def validate_run(run_dir: Path, terminal: bool = False) -> None:
    run_dir = Path(run_dir)
    metadata_path = run_dir / "run.json"
    try: metadata = json.loads(metadata_path.read_text())
    except (OSError, json.JSONDecodeError) as exc: raise WorkflowError(f"{metadata_path}: invalid JSON") from exc
    if metadata.get("schema_version") != SCHEMA_VERSION or metadata.get("entry_point") not in ("autonomous-goal", "orchestrate"):
        raise WorkflowError(f"{metadata_path}: unsupported schema or entry point")
    run_id = metadata.get("run_id", "")
    try:
        parsed_id = uuid.UUID(str(run_id))
    except (ValueError, AttributeError) as exc:
        raise WorkflowError(f"{metadata_path}: invalid run_id") from exc
    if str(parsed_id) != str(run_id).lower() or run_dir.name != str(run_id):
        raise WorkflowError(f"{metadata_path}: invalid run_id")
    if metadata.get("workspace") != str(run_dir.parents[2].resolve()):
        raise WorkflowError(f"{metadata_path}: workspace does not match run location")
    intake = run_dir / "intake.md"
    if not intake.is_file() or not intake.read_text().strip():
        raise WorkflowError(f"{intake}: missing or empty")
    ledger = _read_events(run_dir / "ledger.jsonl", True)
    _read_events(run_dir / "policy.jsonl")
    if not terminal:
        return
    required = ("classification.json", "context.md", "plan.md", "acceptance.md")
    for name in required:
        path = run_dir / name
        if not path.is_file() or not path.read_text().strip():
            raise WorkflowError(f"{path}: missing or empty")
        if any(token in path.read_text() for token in ("TBD", "TODO", "FIXME", "TBA")):
            raise WorkflowError(f"{path}: placeholder content")
        if name == "classification.json":
            try: classification = json.loads(path.read_text())
            except json.JSONDecodeError as exc: raise WorkflowError(f"{path}: invalid JSON") from exc
            if not isinstance(classification, dict) or not classification:
                raise WorkflowError(f"{path}: invalid classification")
    evidence_dir = run_dir / "evidence"
    if not any(p.is_file() for p in evidence_dir.rglob("*")):
        raise WorkflowError(f"{evidence_dir}: no evidence files")
    outcome_path = run_dir / "outcome.json"
    try: outcome = json.loads(outcome_path.read_text())
    except (OSError, json.JSONDecodeError) as exc: raise WorkflowError(f"{outcome_path}: invalid JSON") from exc
    if not isinstance(outcome, dict) or outcome.get("outcome") not in TERMINAL_OUTCOMES:
        raise WorkflowError(f"{outcome_path}: invalid terminal outcome")
    _check_evidence(run_dir, outcome.get("evidence"))
    if not ledger or ledger[-1]["stage"] != "respond":
        raise WorkflowError(f"{run_dir / 'ledger.jsonl'}: terminal ledger must end at respond")
    correspondence = {
        "goal_met": "completed",
        "blocked": "blocked",
        "escalated": "escalated",
        "cancelled": "cancelled",
    }
    if ledger[-1]["event"] != correspondence[outcome["outcome"]]:
        raise WorkflowError(f"{outcome_path}: contradictory outcome and final respond event")
    if outcome["outcome"] == "goal_met" and not any(
        entry["stage"] == "observe_and_verify"
        and entry["event"] == "completed"
        and isinstance(entry["details"].get("evidence"), list)
        and bool(entry["details"]["evidence"])
        for entry in ledger
    ):
        raise WorkflowError(f"{outcome_path}: goal_met requires observe_and_verify evidence")
