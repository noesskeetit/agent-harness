# T2: Driver loop + базовые тулы

Контекст: T1 принят (config.py, llm.py, cli.py). Перечитай `SPEC.md` —
особенно анти-bloat правила и запреты на тесты-театр.

## Что сделать

### 1. `src/swarm_harness/loop.py`

```python
@dataclass
class RunResult:
    status: str        # "completed" | "budget_exceeded"
    result: str        # аргумент finish() либо пояснение при budget_exceeded
    iterations: int
    run_dir: Path

def run_task(
    task: str,
    config: Config,
    llm,                          # LLMClient или объект с тем же .chat()
    run_dir: Path | None = None,  # None -> runs/<YYYYMMDD-HHMMSS>-<8 hex>/
    command_timeout: int = 300,
) -> RunResult: ...
```

Механика цикла:
- messages = [system (см. ниже), user=task]; цикл до `finish()` или
  `config.max_iterations`.
- Каждую итерацию: `llm.chat(messages, tools=TOOL_SCHEMAS)`. Если есть
  tool_calls — исполнить КАЖДЫЙ по порядку, добавить assistant-сообщение и
  tool-результаты в messages (формат OpenAI: role="tool",
  tool_call_id=...). Если tool_calls нет — добавить assistant-текст и
  user-напоминание «заверши работу вызовом finish или продолжай тулами».
- `transcript.jsonl` в run_dir: append-only, по одной JSON-строке на каждое
  добавленное сообщение (и system, и user, и assistant, и tool). Пиши сразу,
  не буферизуй — транскрипт должен быть полон при любом обрыве.
- Достигнут max_iterations без finish → status="budget_exceeded",
  result = краткое пояснение + последний assistant-текст.
- finish(result) → status="completed", result в `run_dir/result.md` и в
  RunResult.

System prompt (константа `DRIVER_SYSTEM` в loop.py, кратко, по-русски):
роль «драйвер-оркестратор: разбирай задачу, действуй тулами, проверяй
результат исполнением, по завершении обязательно вызови finish(result)».
Не пиши эссе — 10-15 строк максимум.

### 2. Тулы (в loop.py, реестр `TOOLS: dict[str, callable]` + `TOOL_SCHEMAS`)

- `run_command(cmd: str, cwd: str = "")` — subprocess через shell,
  cwd по умолчанию run_dir, timeout=command_timeout (по истечении — kill и
  текст "command timed out after Ns"). Возврат: `exit=<code>\n<stdout+stderr>`.
- `read_file(path: str)` — относительные пути от run_dir, абсолютные как есть.
- `write_file(path: str, content: str)` — то же правило путей, создаёт
  родительские директории.
- `finish(result: str)` — завершает ран.
- Любой tool-результат перед попаданием в messages усекается до 8000 символов
  с пометкой `[truncated, full output: <path>]`, полный текст — в
  `run_dir/tool_outputs/<iteration>-<tool>.txt` (только когда было усечение).
- Вызов неизвестного тула или исключение в туле → tool-результат с текстом
  ошибки, цикл продолжается (не падает).

### 3. CLI

`swarm run <task>`: `Config.from_env()` → `run_task(...)` → печать
`status=<...> run_dir=<...>` и result. Exit: 0 при completed, 3 при
budget_exceeded.

### 4. Тесты (`tests/test_loop.py`)

FakeLLM: объект с `.chat(messages, tools=None) -> ChatResult`, отдающий
заранее заданный список ChatResult по очереди. Сценарии (поведение, не
пересказ реализации):
1. write_file → finish: файл реально создан с нужным содержимым,
   status="completed", result совпадает, transcript.jsonl существует и каждая
   строка парсится как JSON.
2. max_iterations=2, FakeLLM бесконечно зовёт run_command("echo x") →
   status="budget_exceeded", iterations == 2.
3. Вызов неизвестного тула, затем finish → status="completed" (цикл пережил
   ошибку).
4. run_command с command_timeout=1 и `cmd="sleep 5"` → tool-результат
   содержит "timed out", ран завершается дальше нормально (FakeLLM затем
   зовёт finish).

## Критерии готовности
1. `uv run pytest -q` зелёные; `uv run ruff check src tests` чисто.
2. Живой прогон: `uv run swarm run "создай файл answer.txt с результатом
   выражения 2+2 и заверши"` — в финальном сообщении: фактический stdout,
   содержимое answer.txt из run_dir и 3-4 строки из transcript.jsonl.
3. Один коммит `feat: driver loop with core tools`.

## Запрещено
Воркеры, параллель, новые зависимости, новые файлы сверх loop.py и
test_loop.py, изменения llm.py/config.py (если что-то мешает — доложи, не
правь сам).
