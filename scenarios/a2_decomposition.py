import json
import subprocess
from pathlib import Path
from typing import Any

from common import count_tool_calls, parse_run_dir, read_transcript, run_swarm, tail


TASK = (
    "Делегируй воркеру создание файла data.json — JSON-массив из 5 "
    "целых чисел на его выбор. После его завершения делегируй ВТОРОМУ "
    "воркеру: передай ему числа и попроси записать их сумму в файл sum.txt "
    "в его директории. Затем сам проверь, что сумма верна, и заверши."
)


def run() -> tuple[bool, str]:
    try:
        process = run_swarm(TASK)
    except subprocess.TimeoutExpired:
        return False, "swarm run timed out"

    if process.returncode != 0:
        return False, f"exit={process.returncode}; stdout tail: {tail(process.stdout)}"
    if "status=completed" not in process.stdout:
        return False, f"status=completed missing; stdout tail: {tail(process.stdout)}"

    try:
        run_dir = parse_run_dir(process.stdout)
    except ValueError as exc:
        return False, f"{exc}; stdout tail: {tail(process.stdout)}"

    workers_dir = run_dir / "workers"
    workspaces = _nonempty_workspaces(workers_dir)
    if len(workspaces) < 2:
        return False, f"expected >=2 nonempty worker workspaces, got {len(workspaces)}"

    data_path = _find_required_file(workers_dir, "data.json")
    if data_path is None:
        return False, "data.json not found under workers/"
    try:
        numbers = json.loads(data_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return False, f"data.json is invalid JSON: {exc}"
    if not _is_five_ints(numbers):
        return False, f"data.json must be an array of 5 int values, got {numbers!r}"

    sum_path = _find_required_file(workers_dir, "sum.txt")
    if sum_path is None:
        return False, "sum.txt not found under workers/"
    try:
        actual_sum = int(sum_path.read_text(encoding="utf-8").strip())
    except ValueError as exc:
        return False, f"sum.txt must contain an int: {exc}"
    if actual_sum != sum(numbers):
        return False, f"sum.txt={actual_sum}, expected {sum(numbers)}"

    try:
        transcript = read_transcript(run_dir)
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"failed to read transcript.jsonl: {exc}"
    counts = count_tool_calls(transcript, {"spawn_worker", "spawn_workers"})
    total_spawns = sum(counts.values())
    if total_spawns < 2:
        return False, f"expected >=2 spawn tool calls, got {counts}"

    return True, f"run_dir={run_dir}"


def _nonempty_workspaces(workers_dir: Path) -> list[Path]:
    if not workers_dir.exists():
        return []
    return [
        path
        for path in workers_dir.iterdir()
        if path.is_dir() and any(child.is_file() for child in path.rglob("*"))
    ]


def _find_required_file(workers_dir: Path, name: str) -> Path | None:
    if not workers_dir.exists():
        return None
    for path in workers_dir.rglob(name):
        if path.is_file() and ".worker" not in path.parts:
            return path
    return None


def _is_five_ints(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 5
        and all(type(item) is int for item in value)
    )


if __name__ == "__main__":
    ok, reason = run()
    print(f"a2_decomposition: {'PASS' if ok else 'FAIL'} {reason}")
    raise SystemExit(0 if ok else 1)
