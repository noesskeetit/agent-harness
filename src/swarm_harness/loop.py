import json
import os
import secrets
import signal
import subprocess
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from swarm_harness.config import Config
from swarm_harness.worker import WorkerResult, spawn_codex_worker, spawn_manus_worker


DRIVER_SYSTEM = """Ты драйвер-оркестратор swarm-harness.
Разбери задачу пользователя на конкретные действия.
Действуй через доступные тулы, а не длинными рассуждениями.
Создавай и читай файлы только когда это нужно для результата.
Команды запускай через run_command и проверяй результат исполнением.
После каждого шага смотри на вывод тула и решай следующий шаг.
Если команда или тул упали, попробуй исправить причину в рамках задачи.
Не выдумывай успех: проверяй созданные файлы и команды.
Директории воркеров в runs/ никогда не удаляются: пути из workspace= и
files: результата spawn_worker используй буквально.
Не нашёл файл по ожидаемому пути — ищи через ls/find, а не предполагай.
Если проверить результат не удалось, напиши об этом в finish(result) прямо;
выдумывать причины недоступности запрещено.
Не пиши эссе и не описывай планы без действия.
Когда работа завершена, обязательно вызови finish(result).
В result кратко укажи, что сделано и как проверено."""

MAX_TOOL_OUTPUT_CHARS = 8000


@dataclass
class RunResult:
    status: str
    result: str
    iterations: int
    run_dir: Path


def _run_command(
    cmd: str,
    cwd: str = "",
    *,
    run_dir: Path,
    command_timeout: int,
) -> str:
    command_cwd = _resolve_path(cwd, run_dir) if cwd else run_dir
    process = subprocess.Popen(
        cmd,
        cwd=command_cwd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        output, _ = process.communicate(timeout=command_timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        output, _ = process.communicate()
        return (
            f"exit=-1\ncommand timed out after {command_timeout}s\n"
            f"{output or ''}"
        )
    return f"exit={process.returncode}\n{output or ''}"


def _read_file(path: str, *, run_dir: Path) -> str:
    return _resolve_path(path, run_dir).read_text()


def _write_file(path: str, content: str, *, run_dir: Path) -> str:
    target = _resolve_path(path, run_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return f"wrote {target}"


def _finish(result: str) -> str:
    return result


def _spawn_worker(
    task: str,
    worker_id: str = "",
    backend: str = "codex",
    *,
    run_dir: Path,
    config: Config,
) -> str:
    if backend not in {"codex", "manus"}:
        return _unknown_backend_error(backend)
    actual_worker_id = worker_id or _next_worker_id(run_dir)
    result = _spawn_worker_backend(
        backend,
        task,
        actual_worker_id,
        run_dir,
        config,
    )
    return _format_worker_result(result)


def _spawn_workers(
    tasks: list[dict[str, str]],
    *,
    run_dir: Path,
    config: Config,
) -> str:
    worker_tasks, error = _assign_worker_ids(tasks, run_dir)
    if error:
        return error

    blocks: list[str] = []
    with ThreadPoolExecutor(max_workers=config.max_parallel_workers) as executor:
        futures = [
            executor.submit(
                _spawn_worker_backend,
                worker_task["backend"],
                worker_task["task"],
                worker_task["worker_id"],
                run_dir,
                config,
            )
            for worker_task in worker_tasks
        ]
        for worker_task, future in zip(worker_tasks, futures, strict=True):
            try:
                blocks.append(_format_worker_result(future.result()))
            except Exception as exc:
                blocks.append(
                    _format_worker_error(
                        worker_task["worker_id"],
                        run_dir,
                        exc,
                    )
                )

    return "\n---\n".join(blocks)


TOOLS: dict[str, Callable[..., str]] = {
    "run_command": _run_command,
    "read_file": _read_file,
    "write_file": _write_file,
    "spawn_worker": _spawn_worker,
    "spawn_workers": _spawn_workers,
    "finish": _finish,
}

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Исполнить shell-команду и вернуть exit code и вывод.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cmd": {"type": "string"},
                    "cwd": {
                        "type": "string",
                        "description": "Рабочая директория, по умолчанию run_dir.",
                    },
                },
                "required": ["cmd"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Прочитать файл. Относительные пути считаются от run_dir.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Записать файл. Родительские директории создаются.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "spawn_worker",
            "description": (
                "Делегируй самодостаточную подзадачу автономному "
                "воркеру-исполнителю; воркер работает в изолированной "
                "директории и не видит твой контекст — формулируй задачу "
                "полностью, включая пути и критерии готовности."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string"},
                    "worker_id": {
                        "type": "string",
                        "description": "Необязательный id; пусто для worker-01, worker-02, ...",
                    },
                    "backend": {
                        "type": "string",
                        "enum": ["codex", "manus"],
                        "description": (
                            "codex — кодинг-агент; manus — автономный "
                            "исследовательский агент."
                        ),
                    },
                },
                "required": ["task"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "spawn_workers",
            "description": (
                "Запусти НЕЗАВИСИМЫЕ подзадачи параллельно; не используй "
                "для подзадач, где одна зависит от результата другой — "
                "для них последовательные spawn_worker."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tasks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "task": {"type": "string"},
                                "worker_id": {
                                    "type": "string",
                                    "description": (
                                        "Необязательный id; пусто для "
                                        "worker-01, worker-02, ..."
                                    ),
                                },
                                "backend": {
                                    "type": "string",
                                    "enum": ["codex", "manus"],
                                    "description": (
                                        "codex — кодинг-агент; manus — "
                                        "автономный исследовательский агент."
                                    ),
                                },
                            },
                            "required": ["task"],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["tasks"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "Завершить ран и вернуть итог пользователю.",
            "parameters": {
                "type": "object",
                "properties": {"result": {"type": "string"}},
                "required": ["result"],
                "additionalProperties": False,
            },
        },
    },
]


def run_task(
    task: str,
    config: Config,
    llm,
    run_dir: Path | None = None,
    command_timeout: int = 300,
) -> RunResult:
    actual_run_dir = run_dir or _new_run_dir()
    actual_run_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = actual_run_dir / "transcript.jsonl"

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": DRIVER_SYSTEM},
        {"role": "user", "content": task},
    ]
    for message in messages:
        _append_message(transcript_path, message)

    last_assistant_text = ""
    for iteration in range(1, config.max_iterations + 1):
        response = llm.chat(messages, tools=TOOL_SCHEMAS)
        last_assistant_text = response.text
        assistant_message = _assistant_message(response)
        messages.append(assistant_message)
        _append_message(transcript_path, assistant_message)

        if response.tool_calls:
            for call in response.tool_calls:
                output, finish_result = _execute_tool(
                    call.name,
                    call.arguments,
                    actual_run_dir,
                    command_timeout,
                    config,
                )
                limited_output = _limit_tool_output(
                    output,
                    actual_run_dir,
                    iteration,
                    call.name,
                )
                tool_message = {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": limited_output,
                }
                messages.append(tool_message)
                _append_message(transcript_path, tool_message)

                if finish_result is not None:
                    (actual_run_dir / "result.md").write_text(finish_result)
                    return RunResult(
                        status="completed",
                        result=finish_result,
                        iterations=iteration,
                        run_dir=actual_run_dir,
                    )
        else:
            reminder = {
                "role": "user",
                "content": "Заверши работу вызовом finish или продолжай тулами.",
            }
            messages.append(reminder)
            _append_message(transcript_path, reminder)

    explanation = "budget_exceeded: достигнут лимит итераций"
    if last_assistant_text:
        explanation = f"{explanation}. Последний ответ ассистента: {last_assistant_text}"
    return RunResult(
        status="budget_exceeded",
        result=explanation,
        iterations=config.max_iterations,
        run_dir=actual_run_dir,
    )


def _execute_tool(
    name: str,
    arguments: dict[str, Any],
    run_dir: Path,
    command_timeout: int,
    config: Config,
) -> tuple[str, str | None]:
    tool = TOOLS.get(name)
    if tool is None:
        return f"error: unknown tool: {name}", None

    try:
        if name == "run_command":
            output = tool(
                run_dir=run_dir,
                command_timeout=command_timeout,
                **arguments,
            )
            return output, None
        if name in {"read_file", "write_file"}:
            output = tool(run_dir=run_dir, **arguments)
            return output, None
        if name in {"spawn_worker", "spawn_workers"}:
            output = tool(run_dir=run_dir, config=config, **arguments)
            return output, None
        output = tool(**arguments)
    except Exception as exc:
        return f"error: {type(exc).__name__}: {exc}", None

    if name == "finish":
        return output, output
    return output, None


def _assistant_message(response) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": response.text}
    if response.tool_calls:
        message["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(
                        call.arguments,
                        ensure_ascii=False,
                    ),
                },
            }
            for call in response.tool_calls
        ]
    return message


def _append_message(transcript_path: Path, message: dict[str, Any]) -> None:
    with transcript_path.open("a", encoding="utf-8") as file:
        json.dump(message, file, ensure_ascii=False)
        file.write("\n")


def _limit_tool_output(
    output: str,
    run_dir: Path,
    iteration: int,
    tool_name: str,
) -> str:
    if len(output) <= MAX_TOOL_OUTPUT_CHARS:
        return output

    output_dir = run_dir / "tool_outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{iteration}-{_safe_tool_name(tool_name)}.txt"
    output_path.write_text(output)
    marker = f"\n[truncated, full output: {output_path}]"
    keep = max(0, MAX_TOOL_OUTPUT_CHARS - len(marker))
    return f"{output[:keep]}{marker}"


def _safe_tool_name(tool_name: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in tool_name)


def _next_worker_id(run_dir: Path) -> str:
    workers_dir = run_dir / "workers"
    index = 1
    while (workers_dir / f"worker-{index:02d}").exists():
        index += 1
    return f"worker-{index:02d}"


def _assign_worker_ids(
    tasks: list[dict[str, str]],
    run_dir: Path,
) -> tuple[list[dict[str, str]], str | None]:
    occupied = _existing_worker_ids(run_dir)
    batch_ids: set[str] = set()
    assigned = []

    for item in tasks:
        backend = item.get("backend") or "codex"
        if backend not in {"codex", "manus"}:
            return [], _unknown_backend_error(backend)
        worker_id = item.get("worker_id") or _next_available_worker_id(
            occupied | batch_ids
        )
        if worker_id in batch_ids:
            return [], f"error: duplicate worker_id in spawn_workers batch: {worker_id}"
        batch_ids.add(worker_id)
        assigned.append(
            {
                "task": item["task"],
                "worker_id": worker_id,
                "backend": backend,
            }
        )

    return assigned, None


def _existing_worker_ids(run_dir: Path) -> set[str]:
    workers_dir = run_dir / "workers"
    if not workers_dir.exists():
        return set()
    return {path.name for path in workers_dir.iterdir() if path.is_dir()}


def _next_available_worker_id(occupied: set[str]) -> str:
    index = 1
    while f"worker-{index:02d}" in occupied:
        index += 1
    return f"worker-{index:02d}"


def _format_worker_result(result: WorkerResult) -> str:
    workspace_abs = result.workspace.resolve()
    files = "\n".join(
        f"- {path} -> {workspace_abs / path}" for path in result.files
    )
    return (
        f"worker={result.worker_id} ok={str(result.ok).lower()} "
        f"workspace={workspace_abs}\n"
        f"files:\n{files}\n"
        f"message:\n{result.message}"
    )


def _spawn_worker_backend(
    backend: str,
    task: str,
    worker_id: str,
    run_dir: Path,
    config: Config,
) -> WorkerResult:
    if backend == "codex":
        return spawn_codex_worker(task, worker_id, run_dir, config)
    if backend == "manus":
        return spawn_manus_worker(task, worker_id, run_dir, config)
    raise ValueError(_unknown_backend_error(backend))


def _unknown_backend_error(backend: str) -> str:
    return f"error: unknown worker backend: {backend}; expected codex or manus"


def _format_worker_error(worker_id: str, run_dir: Path, exc: Exception) -> str:
    return _format_worker_result(
        WorkerResult(
            worker_id=worker_id,
            ok=False,
            message=f"{type(exc).__name__}: {exc}",
            files=[],
            workspace=run_dir / "workers" / worker_id,
        )
    )


def _resolve_path(path: str, run_dir: Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return run_dir / candidate


def _new_run_dir() -> Path:
    run_id = f"{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(4)}"
    return Path("runs") / run_id
