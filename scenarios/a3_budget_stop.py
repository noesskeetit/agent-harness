import subprocess

from common import parse_run_dir, tail
from common import run_swarm as common_run_swarm


TASK = (
    "Напиши полноценный статический генератор сайтов: парсер markdown, "
    "шаблонизатор, инкрементальная сборка, CLI, тесты на всё."
)


def run() -> tuple[bool, str]:
    try:
        process = common_run_swarm(
            TASK,
            env_overrides={"SWARM_MAX_ITERATIONS": "3"},
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return False, "завис"

    if process.returncode != 3:
        return False, f"exit={process.returncode}, expected 3; stdout tail: {tail(process.stdout)}"
    if "status=budget_exceeded" not in process.stdout:
        return (
            False,
            f"status=budget_exceeded missing; stdout tail: {tail(process.stdout)}",
        )

    try:
        run_dir = parse_run_dir(process.stdout)
    except ValueError as exc:
        return False, f"{exc}; stdout tail: {tail(process.stdout)}"

    transcript_path = run_dir / "transcript.jsonl"
    try:
        line_count = len(transcript_path.read_text(encoding="utf-8").splitlines())
    except OSError as exc:
        return False, f"failed to read transcript.jsonl: {exc}"
    if line_count > 25:
        return False, f"transcript.jsonl has {line_count} lines, expected <=25"

    return True, f"run_dir={run_dir}"


if __name__ == "__main__":
    ok, reason = run()
    print(f"a3_budget_stop: {'PASS' if ok else 'FAIL'} {reason}")
    raise SystemExit(0 if ok else 1)
