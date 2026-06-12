"""Цикл драйвера: completion → tool → результат, транскрипт, бюджет.

Реализации тулов и их схемы — в tools.py; бэкенды воркеров — в worker.py.
"""

import json
import secrets
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from swarm_harness.config import Config
from swarm_harness.tools import TOOL_SCHEMAS, execute_tool


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
                output, finish_result = execute_tool(
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


def _new_run_dir() -> Path:
    run_id = f"{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(4)}"
    return Path("runs") / run_id
