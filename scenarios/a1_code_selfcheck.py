import subprocess

from common import parse_run_dir, run_swarm, tail


TASK = (
    "Создай python-пакет strcalc: модуль с функцией "
    "evaluate(expr: str) -> float, которая безопасно вычисляет "
    "арифметические выражения вроде '2+3*4' (должно дать 14). "
    "Напиши pytest-тесты минимум на 4 случая включая приоритет "
    "операций и деление. Прогони тесты и убедись, что они зелёные, "
    "прежде чем завершать."
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

    pytest_process = subprocess.run(
        ["python3", "-m", "pytest", "-q"],
        cwd=run_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=300,
        check=False,
    )
    if pytest_process.returncode != 0:
        return (
            False,
            f"pytest exit={pytest_process.returncode}; "
            f"output tail: {tail(pytest_process.stdout)}",
        )

    eval_process = subprocess.run(
        [
            "python3",
            "-c",
            (
                "from strcalc import evaluate; "
                "result = evaluate('2+3*4'); "
                "assert result == 14.0, result"
            ),
        ],
        cwd=run_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=60,
        check=False,
    )
    if eval_process.returncode != 0:
        return (
            False,
            f"evaluate check exit={eval_process.returncode}; "
            f"output tail: {tail(eval_process.stdout)}",
        )

    return True, f"run_dir={run_dir}"


if __name__ == "__main__":
    ok, reason = run()
    print(f"a1_code_selfcheck: {'PASS' if ok else 'FAIL'} {reason}")
    raise SystemExit(0 if ok else 1)
