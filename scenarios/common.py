import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RUN_DIR_RE = re.compile(r"\brun_dir=(?P<run_dir>\S+)")


def run_swarm(
    task: str,
    env_overrides: dict[str, str] | None = None,
    timeout: int = 1800,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        ["uv", "run", "swarm", "run", task],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
        check=False,
    )


def parse_run_dir(stdout: str) -> Path:
    match = RUN_DIR_RE.search(stdout)
    if match is None:
        raise ValueError("run_dir= not found in stdout")

    run_dir = Path(match.group("run_dir"))
    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir
    return run_dir


def read_transcript(run_dir: Path) -> list[dict[str, Any]]:
    transcript_path = run_dir / "transcript.jsonl"
    return [
        json.loads(line)
        for line in transcript_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def count_tool_calls(
    transcript: list[dict[str, Any]],
    names: set[str],
) -> dict[str, int]:
    counts = {name: 0 for name in names}
    for message in transcript:
        for call in message.get("tool_calls", []):
            name = call.get("function", {}).get("name")
            if name in counts:
                counts[name] += 1
    return counts


def tail(text: str, limit: int = 1200) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]
