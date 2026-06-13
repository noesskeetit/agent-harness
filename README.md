# swarm-harness

Тонкий harness в духе Claude Code dynamic workflows / Kimi agent swarm:
даёшь одну сложную задачу одной командой — LLM-драйвер сам раскладывает её,
делегирует воркерам, проверяет результат исполнением и возвращает ответ.

```bash
uv run swarm run "создай python-пакет с тестами и прогони их"
```

Интеллект — в модели, harness — тупой и маленький (ядро ≤1500 строк).
Никаких message-протоколов, schema-валидаторов выходов, review-gate'ов и
lease-леджеров: механизмы недоверия добавляются только после реально
наблюдавшегося инцидента (см. `docs/incidents.md`). Верификация — исполнением
(запустить код, прогнать тесты, дать критику-воркеру прочитать по существу),
а не проверкой формы JSON.

## Архитектура

```
swarm run "task"
  └─ Driver loop (одна LLM: Kimi-K2.6 через Cloud.ru FM API, tool calling)
       тулы: spawn_worker / spawn_workers / run_command /
             read_file / write_file / finish
       └─ воркеры-сабпроцессы в изолированных workspace:
            codex_cli  — кодинг-агент (codex exec)
            manus      — автономный агент (vendor: github.com/noesskeetit/manus-agent)
```

- Состояние рана — файлы в `runs/<id>/`: `transcript.jsonl` (append-only),
  `result.md`, `workers/<id>/`. Resume = перечитать транскрипт. Никаких
  state machine.
- Драйвер сам решает, какой воркер и какую модель запускать под подзадачу
  (текстовый kimi26 по умолчанию; `qwen35-vlm` — vision-воркер для картинок).

## Установка

```bash
uv sync
cp .env.example .env   # вписать FM_API_KEY (Cloud.ru FM API)
uv run swarm selfcheck # проверка связи с моделью
```

## Конфигурация (env)

| Переменная | Дефолт | Что |
|---|---|---|
| `FM_API_KEY` | — (обязательна) | ключ Cloud.ru FM API |
| `SWARM_MODEL` | `moonshotai/Kimi-K2.6` | модель драйвера |
| `SWARM_MANUS_MODEL` | `kimi26` | модель manus-воркеров |
| `SWARM_MAX_ITERATIONS` | `40` | бюджет цикла драйвера |
| `SWARM_WORKER_TIMEOUT` | `1800` | таймаут воркера, сек |
| `SWARM_MAX_PARALLEL_WORKERS` | `4` | лимит параллели |
| `SWARM_WORKER_PROXY` | пусто | прокси для codex-воркеров |
| `SWARM_VLM_BASE` | пусто | endpoint vision-модели (ML Inference) |

## Приёмка

```bash
uv run python scenarios/run_all.py   # три живых поведенческих сценария
uv run pytest -q                     # юнит-тесты механики
```

Дизайн-контракт и анти-bloat правила — в `SPEC.md`.
