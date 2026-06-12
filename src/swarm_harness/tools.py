"""Тулы драйвера: реализации, OpenAI-схемы и диспатч.

Механика самого цикла — в loop.py; бэкенды воркеров — в worker.py.
"""

import os
import signal
import subprocess
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from swarm_harness.config import Config
from swarm_harness.worker import WorkerResult, spawn_codex_worker, spawn_manus_worker


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
    model: str = "",
    *,
    run_dir: Path,
    config: Config,
) -> str:
    if backend not in {"codex", "manus"}:
        return _unknown_backend_error(backend)
    if model and backend != "manus":
        return "error: параметр model поддерживается только для backend=manus"
    actual_worker_id = worker_id or _next_available_worker_id(
        _existing_worker_ids(run_dir)
    )
    result = _spawn_worker_backend(
        backend,
        task,
        actual_worker_id,
        run_dir,
        config,
        model,
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
                worker_task["model"],
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


def _spawn_worker_backend(
    backend: str,
    task: str,
    worker_id: str,
    run_dir: Path,
    config: Config,
    model: str = "",
) -> WorkerResult:
    if backend == "codex":
        return spawn_codex_worker(task, worker_id, run_dir, config)
    if backend == "manus":
        return spawn_manus_worker(task, worker_id, run_dir, config, model)
    raise ValueError(_unknown_backend_error(backend))


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
        model = item.get("model") or ""
        if model and backend != "manus":
            return [], "error: параметр model поддерживается только для backend=manus"
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
                "model": model,
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


def _unknown_backend_error(backend: str) -> str:
    return f"error: unknown worker backend: {backend}; expected codex or manus"


def _resolve_path(path: str, run_dir: Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return run_dir / candidate


TOOLS: dict[str, Callable[..., str]] = {
    "run_command": _run_command,
    "read_file": _read_file,
    "write_file": _write_file,
    "spawn_worker": _spawn_worker,
    "spawn_workers": _spawn_workers,
    "finish": _finish,
}


def execute_tool(
    name: str,
    arguments: dict[str, Any],
    run_dir: Path,
    command_timeout: int,
    config: Config,
) -> tuple[str, str | None]:
    """Исполнить тул по имени. Возвращает (output, finish_result|None)."""
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


_WORKER_ID_PROPERTY = {
    "type": "string",
    "description": "Необязательный id; пусто для worker-01, worker-02, ...",
}

_BACKEND_PROPERTY = {
    "type": "string",
    "enum": ["codex", "manus"],
    "description": "codex — кодинг-агент; manus — автономный исследовательский агент.",
}

_MODEL_PROPERTY = {
    "type": "string",
    "description": (
        "Только для backend=manus: модель воркера. Пусто — текстовый дефолт "
        "(kimi26). 'qwen35-vlm' — vision-воркер для анализа изображений "
        "(тул image_view; страницы PDF можно рендерить в PNG через pdftoppm)."
    ),
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
                    "worker_id": _WORKER_ID_PROPERTY,
                    "backend": _BACKEND_PROPERTY,
                    "model": _MODEL_PROPERTY,
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
                                "worker_id": _WORKER_ID_PROPERTY,
                                "backend": _BACKEND_PROPERTY,
                                "model": _MODEL_PROPERTY,
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
