"""Read the append-only telemetry event log."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterator


def read_events(path: Path) -> Iterator[dict]:
    """Yield each valid JSON object from a JSONL event log.

    Lines that fail to parse are skipped with a warning printed to
    stderr, rather than aborting the whole read.
    """
    if not path.exists():
        return

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                print(
                    f"telemetry: skipping malformed line {line_number} in {path}: {exc}",
                    file=sys.stderr,
                )
