# T3: Worker backend codex_cli + тул spawn_worker

Контекст: T1-T2 приняты. Драйвер-цикл работает (loop.py). Теперь воркеры:
драйвер должен уметь делегировать подзадачу автономному `codex exec`
сабпроцессу. Перечитай SPEC.md (worker contract).

## Что сделать

### 1. `src/swarm_harness/worker.py`

```python
@dataclass
class WorkerResult:
    worker_id: str
    ok: bool
    message: str        # финальное сообщение воркера ИЛИ честный текст фейла
    files: list[str]    # созданные/изменённые файлы, пути относительно workspace
    workspace: Path

def spawn_codex_worker(
    task: str,
    worker_id: str,
    run_dir: Path,
    config: Config,
    executable: str = "codex",
) -> WorkerResult: ...
```

Механика:
- Workspace: `run_dir/workers/<worker_id>/` (mkdir parents). Служебное —
  в `workspace/.worker/`: `last_message.txt`, `codex_output.log`.
- Записать `task.md` с текстом подзадачи.
- Снять snapshot файлов workspace до запуска (relative path -> mtime+size),
  после завершения собрать `files` как созданные/изменённые, исключая
  `task.md` и `.worker/`.
- Сабпроцесс (cwd=workspace, stdin=task.md):
  `<executable> exec --sandbox workspace-write --skip-git-repo-check
  --output-last-message .worker/last_message.txt -`
  stdout+stderr → `.worker/codex_output.log`.
- env для сабпроцесса: копия текущего; если `config.worker_proxy` непуст —
  добавить `HTTP_PROXY/HTTPS_PROXY/ALL_PROXY/http_proxy/https_proxy/all_proxy`
  = proxy и `NO_PROXY/no_proxy=localhost,127.0.0.1`.
- Таймаут `config.worker_timeout`: по истечении kill всей process group
  (как в `_run_command`), `ok=False`,
  `message="worker timed out after <N>s"` + хвост лога.
- Exit code != 0 → `ok=False`, message = хвост `codex_output.log`
  (последние ~2000 символов).
- Успех → `ok=True`, message = содержимое `last_message.txt` (если файла нет —
  `ok=False` с пояснением).

### 2. Тул `spawn_worker` в loop.py

- Схема: `spawn_worker(task: str, worker_id: str = "")` — описание для модели:
  «делегируй самодостаточную подзадачу автономному воркеру-исполнителю;
  воркер работает в изолированной директории и не видит твой контекст —
  формулируй задачу полностью, включая пути и критерии готовности».
- `worker_id` пустой → автогенерация `worker-01`, `worker-02`, ... по
  существующим директориям в `run_dir/workers/`.
- Результат тула для контекста драйвера (формат):
  ```
  worker=<id> ok=<true|false> workspace=<path>
  files:
  - <relpath>
  message:
  <message>
  ```
- Для передачи `config` в исполнение тулов расширь существующий механизм
  минимально (например, `run_task` уже владеет config — пробрось его в
  `_execute_tool`). Никаких новых классов-контекстов.

### 3. Тесты (`tests/test_worker.py`)

НЕ зови реальный codex в юнитах. Используй `executable=<путь к стабу>` —
исполняемый shell-скрипт, создаваемый тестом в tmp_path (chmod +x). Скрипт
игнорирует аргументы кроме того, что нужно сценарию.
1. Стаб пишет `.worker/last_message.txt` («готово»), создаёт `out.txt` в cwd,
   exit 0 → ok=True, `files == ["out.txt"]`, message == "готово".
2. Стаб пишет в stderr и exit 2 → ok=False, message содержит текст ошибки.
3. Стаб спит 5с, `config.worker_timeout=1` → ok=False, "timed out" в message.
4. Wiring-тест в `tests/test_loop.py`: FakeLLM зовёт spawn_worker, затем
   finish; `spawn_codex_worker` замокан (monkeypatch) на возврат готового
   WorkerResult → tool-сообщение в транскрипте содержит `ok=true` и имя файла.

## Критерии готовности
1. `uv run pytest -q` зелёные, `uv run ruff check src tests` чисто.
2. Живой e2e (это главный milestone): 
   `uv run swarm run "делегируй воркеру подзадачу: создать в его рабочей
   директории файл greeting.txt с текстом 'привет от воркера'. После
   завершения воркера сам проверь содержимое файла и заверши"`.
   В финальном сообщении: фактический stdout, `ls` workspace воркера,
   содержимое greeting.txt. Прокси для воркера уже лежит в `.env`
   (SWARM_WORKER_PROXY).
3. Один коммит `feat: codex_cli worker backend and spawn_worker tool`.

## Запрещено
Параллель (T4), manus-бэкенд (T6), реестры воркеров, schema-валидация
выходов воркера, ретраи воркеров. Новые зависимости. Если живой e2e падает
из-за окружения (прокси/авторизация codex) — доложи с логом, не выдумывай
обходные пути.
