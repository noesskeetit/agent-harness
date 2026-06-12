# T8: два фикса контекст-движка manus-agent

Рабочий репозиторий: `/Users/aogabbasov/Code/manus-agent` (публичный OSS —
аккуратность как в T7: локальный коммит, ПУШИТЬ ЗАПРЕЩЕНО). Репо
swarm-harness в этой задаче не трогается. Оба фикса — из код-ревью
оркестратора, оба проявляются только на длинных ранах.

## Фикс 1: snip должен щадить свежие tool results

`manus/context.py`, `_stage_snip`. Докстринг модуля обещает: «Что НЕ
сжимать: ... последние 3 tool results», но цикл снипует ВСЕ tool-сообщения
длиннее порога — включая то, которое модель запросила последним.

- Реализация: определи индексы tool-сообщений в `self.messages`, исключи
  ПОСЛЕДНИЕ 3 из снипа (именно последние 3 tool-сообщения, не последние 3
  сообщения вообще).
- Тест (поведенческий, в `tests/test_compaction.py` рядом с существующими):
  контекст с 5 длинными tool results → после `_stage_snip` первые 2
  содержат `[snipped`, последние 3 — нетронутый оригинал.

## Фикс 2: невыселяемые пины

`manus/context.py` (`auto_pin`, `pin_fact`, FIFO-кап 30) + `manus/agent.py`.
Сейчас автопины путей больших observations вытесняют по FIFO пин исходной
задачи — на длинном ране агент «забывает» формулировку.

- Реализация: отдельный список `protected_facts: list[str]` в
  `ContextWindow`; `pin_fact(fact, protected=False)` и
  `auto_pin(fact, protected=False)`; FIFO-кап действует только на обычные
  `pinned_facts`; в `assemble` protected рендерятся первыми в том же
  «Pinned facts»-блоке; `to_dict`/`load_dict` сериализуют оба списка,
  `load_dict` обязан переживать старые state.json без ключа
  `protected_facts` (дефолт []).
- `manus/agent.py`: стартовые пины `original task: ...` и `workspace: ...`
  — protected.
- Тесты: (а) 35 обычных пинов + 2 protected → protected целы, обычных ≤30,
  выселены старейшие обычные; (б) `load_dict` со старым словарём без
  `protected_facts` не падает.

## Критерии готовности
1. Собственные тесты manus-agent: `uv run pytest -q` из его корня — зелёные.
2. Один коммит в manus-agent:
   `fix: spare recent tool results from snip, protect critical pins`.
   Без push.
3. Финальное сообщение: полный дифф + вывод pytest.

## Запрещено
Менять другие стадии компакции, переименовывать публичные методы, трогать
swarm-harness, push.
