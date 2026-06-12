# T9: актуализация upstream manus-agent из vendored-копии

Контекст: vendored-копия `/Users/aogabbasov/kaggle_grinder/vendor/manus-agent`
уехала вперёд upstream `/Users/aogabbasov/Code/manus-agent` за время
kaggle_grinder-разработки. Цель: upstream становится строгим супермножеством
vendored (плюс уже принятые T7 kimi26 и T8 context-фиксы). Рабочий репо —
upstream, публичный OSS: локальные коммиты, ПУШИТЬ ЗАПРЕЩЕНО.

## Что перенести (по файлам, сверяйся диффом с vendored)

1. **`manus/config.py` — реестр моделей**: объедини MODELS до супермножества
   (deepseek-v4-pro, minimax25, glm51, gpt54, claude-opus46, qwen-варианты и
   все остальные vendored-профили). kimi26 уже есть после T7 — не дублируй.
   Сохрани upstream-дефолты executor/planner/summarizer как есть.
2. **`manus/llm.py` — thinking levels**: vendored-логика `MANUS_THINKING`
   (off/none/low/medium/high), `reasoning_effort` для FM API,
   `chat_template_kwargs.enable_thinking` для vLLM, strict-валидация
   значения, поведение при BadRequest (ретрай без extra_body только при
   thinking=off). Перенеси дословно с веткой стрипа reasoning_content.
3. **`manus/agent.py` — два независимых улучшения**:
   - opt-in hard tool mask (`MANUS_HARD_TOOL_MASK`, `_tool_specs()`,
     пересчёт specs в `set_active_groups`);
   - guard от пере-дампа больших выводов `read_observation` в
     `_maybe_dump_observation`.
   ВНИМАНИЕ: T8 уже изменил agent.py (protected pins) — переноси правки
   поверх текущего состояния, не затирай T8.
4. **`manus/tools/shell.py` — workspace isolation**: vendored-логика
   `_workspace_root`/`_is_relative_to`/`_default_shell_cwd` (+ что там ещё
   по диффу) — запрет cwd вне workspace root.

НЕ переноси: `__pycache__`, `.venv`, kaggle/харнесс-специфичное (если
встретишь упоминания task_packet/bridge — это не для upstream, доложи).

## Тесты
- Собственные тесты upstream: `uv run pytest -q` — зелёные.
- Добавь минимум по одному поведенческому тесту на: thinking mapping
  (off → reasoning_effort=none для FM-профиля), hard mask (включён →
  specs только активных групп), shell cwd isolation (cwd вне root →
  ошибка). В существующие test-файлы, без новых фреймворков.

## Критерии готовности
1. `diff -r` между vendored/manus и upstream/manus (без __pycache__) после
   переноса: расхождения только там, где upstream НОВЕЕ (T8-фиксы, иные
   дефолты). Вставь итоговый дифф-обзор в финальное сообщение.
2. pytest upstream зелёный.
3. Один коммит: `feat: port Cloud.ru model registry, thinking levels, hard
   tool mask, shell isolation from downstream`. Без push.

## Запрещено
Менять vendored-копию и kaggle_grinder; push; менять upstream-дефолты
моделей; «улучшать» переносимый код сверх дословного порта.
