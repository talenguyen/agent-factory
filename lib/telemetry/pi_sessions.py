"""Parse pi's own session transcripts to derive delegation metrics."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional


def find_session_file(sessions_root: Path, pi_session_id: str) -> Optional[Path]:
    """Find a pi session file whose name contains the given session id."""
    if not sessions_root.exists():
        return None
    matches = sorted(sessions_root.glob(f"**/*{pi_session_id}*.jsonl"))
    return matches[0] if matches else None


def load_session_messages(path: Path) -> list[dict]:
    """Parse every JSON line in a pi session file."""
    messages = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                messages.append(json.loads(line))
    return messages


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def slice_by_window(
    messages: list[dict], start_ts: str, end_ts: Optional[str]
) -> list[dict]:
    """Keep only entries timestamped within [start_ts, end_ts].

    end_ts=None means unbounded (still open / no delegation-end recorded
    yet).
    """
    start = _parse_ts(start_ts)
    end = _parse_ts(end_ts) if end_ts else None

    sliced = []
    for entry in messages:
        raw_ts = entry.get("timestamp")
        if not raw_ts:
            continue
        entry_ts = _parse_ts(raw_ts)
        if entry_ts < start:
            continue
        if end is not None and entry_ts > end:
            continue
        sliced.append(entry)
    return sliced


def derive_metrics(messages: list[dict]) -> dict:
    """Derive turn count, tool-call counts, and total cost from a message slice."""
    turn_count = 0
    tool_call_counts: dict = {}
    total_cost = 0.0

    for entry in messages:
        if entry.get("type") != "message":
            continue
        message = entry.get("message", {})
        role = message.get("role")

        if role == "user":
            turn_count += 1

        if role == "assistant":
            # Current pi versions nest usage inside the message; older ones
            # put it alongside the message at the top level of the entry.
            usage = message.get("usage") or entry.get("usage") or {}
            cost = (usage.get("cost") or {}).get("total")
            if cost:
                total_cost += cost

            for item in message.get("content", []):
                if item.get("type") == "toolCall":
                    name = item.get("name", "unknown")
                    tool_call_counts[name] = tool_call_counts.get(name, 0) + 1

    return {
        "turn_count": turn_count,
        "tool_call_counts": tool_call_counts,
        "total_cost": total_cost,
    }
