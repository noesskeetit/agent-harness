# Swarm-harness core — план реализации

> Исполнение: оркестратор (Claude) диспатчит задачи исполнителю (Codex CLI)
> через tmux, по одной, с ревью диффа после каждой. ТЗ задач лежат в
> `tasks/task-NN.md`; этот файл — карта всего плана.

**Goal:** `swarm run "сложная задача"` — драйвер-LLM декомпозирует, делегирует
воркерам, верифицирует исполнением, возвращает результат. 0 вмешательств.

**Architecture:** один агентный цикл (Kimi-K2.6 via Cloud.ru FM API, tool
calling) + воркеры-сабпроцессы (codex exec, позже Manus). Файлы вместо
протоколов, transcript.jsonl вместо state machine. См. SPEC.md.

**Tech Stack:** Python 3.12, uv, openai, python-dotenv, ruff, pytest.

---

## Задачи

- [x] **T1. Scaffold + LLM-клиент + selfcheck** — `tasks/task-01.md` ✅ принято: fe32fcf, selfcheck живой
  pyproject (uv, console script `swarm`), `config.py` (Config.from_env),
  `llm.py` (тонкий клиент chat-with-tools), `cli.py` (`selfcheck` живой,
  `run` заглушка). Done: `uv run swarm selfcheck` живым запросом возвращает
  ответ модели; pytest/ruff зелёные.
- [x] **T2. Driver loop** — `tasks/task-02.md` ✅ принято: 56b2acb, live-прогон с самопроверкой
  `loop.py`: цикл completion→tool→результат, реестр тулов как dict
  name→callable, `transcript.jsonl`, остановка по `finish()` /
  max_iterations (`budget_exceeded`). Тулы этой задачи: `run_command`,
  `read_file`, `write_file`, `finish`. Unit: FakeLLM-сценарии (2-3 шага,
  бюджет, неизвестный тул). Live: `swarm run "посчитай 2+2 и finish"`.
- [x] **T3. Worker backend codex_cli** — `tasks/task-03.md` ✅ принято: b4b6a66, живой e2e драйвер→воркер
  `worker.py`: spawn_worker(task) → workspace `runs/<id>/workers/<wid>/`,
  `task.md`, сабпроцесс `codex exec` (sandbox workspace-write, прокси из
  SWARM_WORKER_PROXY, --output-last-message), таймаут→kill→честный фейл.
  Результат: финальное сообщение + список файлов. Live: воркер создаёт файл.
- [x] **T4. Параллель + лимиты** — `tasks/task-04.md` ✅ принято: 760d03d, live: 1×spawn_workers → 2 параллельных воркера
  `spawn_workers(tasks[])` через ThreadPoolExecutor, cap из env (дефолт 4).
  Усечение больших tool-результатов: в контекст TL;DR + путь к полному файлу.
- [x] **T5. Приёмочные сценарии A1-A3** — `tasks/task-05.md` ✅ принято: 129c782, все три PASS живьём, артефакты перепроверены
  `scenarios/` + чекеры-скрипты по SPEC.md. Гоняются руками/CI с SWARM_LIVE=1.
  Это единственная «приёмка» проекта — никаких smoke-модулей в src.
- [ ] **T6. Manus worker backend** — `tasks/task-06.md`
  Порт минимума из kaggle_grinder `manus/adapter.py` (upstream
  `~/Code/manus-agent`): запуск Manus-воркера сабпроцессом с тем же worker
  contract. Backend выбирается per-spawn аргументом, дефолт codex_cli.

## Порядок и чекпоинты

T1 → T2 → T3 → T5(A1) → T4 → T5(A2,A3) → T6.
После каждой задачи: оркестратор делает ревью диффа + прогон тестов; после
T3 — первый живой end-to-end прогон. Проблемы возвращаются исполнителю
follow-up-сообщением в той же tmux-сессии.
