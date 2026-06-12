# T7: Kimi K2.6 для Manus-воркеров (два репо)

Цель оператора: «везде Kimi, не Qwen». Драйвер уже на Kimi-K2.6. Manus-воркеры
сейчас на qwen-coder, потому что upstream-реестр моделей не знает Kimi.
Задача в двух частях, по коммиту в каждом репо.

## Часть A: `/Users/aogabbasov/Code/manus-agent` (публичный OSS репозиторий!)

1. В `manus/config.py` в dict `MODELS` добавь профиль (это проверенный спек
   из vendored-копии `/Users/aogabbasov/kaggle_grinder/vendor/manus-agent/`,
   перенеси дословно, поправив только переменную base, как она называется
   в upstream):
   ```python
   "kimi26": ModelSpec(
       id="moonshotai/Kimi-K2.6",
       short="kimi26",
       api_base=_CLOUDRU_BASE,
       api_key_env="LLM_API_KEY",
       context_window=262_144,
       supports_tool_calling=True,
       notes="Cloud.ru FM API Kimi K2.6 profile for long-context executor workers.",
   ),
   ```
2. Дефолты upstream (executor=qwen-coder и т.д.) НЕ меняй — только регистрация.
3. Прогони его собственные тесты: `uv run pytest -q` из корня manus-agent —
   зелёные.
4. Коммит в manus-agent: `feat: add Cloud.ru Kimi K2.6 model profile`.
   ПУШИТЬ ЗАПРЕЩЕНО — оператор отревьюит и запушит сам.

## Часть B: `/Users/aogabbasov/swarm-harness`

1. `config.py`: дефолт `manus_model` → `"kimi26"`. Обнови тест дефолтов.
2. Живой прогон с дефолтным окружением (без SWARM_MANUS_MODEL):
   `uv run swarm run "делегируй воркеру с backend=manus задачу: создай в своей
   директории файл check.md с двумя предложениями о Cloud.ru. Проверь файл и
   заверши"`.
   Критично: в `.worker/manus_output.log` должно быть
   `Executor: kimi26 (moonshotai/Kimi-K2.6)` и `Final state: done`.
3. Коммит в swarm-harness: `feat: default manus workers to Kimi K2.6`.

## Критерии готовности
1. Оба pytest зелёные (manus-agent и swarm-harness), ruff в swarm-harness чисто.
2. В финальном сообщении: дифф части A (полностью), хвост manus_output.log
   с Executor-строкой, stdout живого прогона.
3. Два коммита, по одному в каждом репо. Никакого push нигде.

## Запрещено
Менять дефолты/код upstream сверх добавления одного ModelSpec; добавлять
другие модели (deepseek и пр.) — только kimi26; трогать worker.py.
Если живой прогон покажет, что Kimi на manus-пути ведёт себя плохо
(зацикливание, кривые tool calls) — доложи с логом, не маскируй.
