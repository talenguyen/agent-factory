#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
launcher = project_root / "bin" / "pi-project"

result = subprocess.run(
    [str(launcher), "--mode", "rpc", "--no-session", "--offline"],
    input='{"id":"skills","type":"get_commands"}\n',
    text=True,
    capture_output=True,
    timeout=30,
    check=False,
)
if result.returncode != 0:
    raise AssertionError(
        f"Pi RPC exited {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

records = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
responses = [
    record
    for record in records
    if record.get("type") == "response"
    and record.get("command") == "get_commands"
    and record.get("id") == "skills"
]
assert len(responses) == 1, responses
assert responses[0].get("success") is True, responses[0]

commands = responses[0]["data"]["commands"]
skill_commands = [command for command in commands if command.get("source") == "skill"]
assert any(command.get("name") == "skill:delegate-to-pi" for command in skill_commands)

outside = []
for command in skill_commands:
    source_info = command.get("sourceInfo")
    raw_path = command.get("path")
    if not raw_path and isinstance(source_info, dict):
        raw_path = source_info.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        outside.append(command)
        continue
    try:
        Path(raw_path).resolve().relative_to(project_root)
    except (OSError, ValueError):
        outside.append(command)

assert not outside, f"skills loaded outside project: {outside}"
print("test-pi-project-rpc: PASS")
