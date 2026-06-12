# T6b: отдельная модель для Manus-воркеров (follow-up к T6)

Проблема из твоего же отчёта T6: `spawn_manus_worker` выводит модель воркера
из `config.model` (модель ДРАЙВЕРА, Kimi-K2.6), которую upstream Manus не
поддерживает. Модель драйвера и модель Manus-воркера — независимые настройки.

## Что сделать
1. `config.py`: новое поле `manus_model: str = "qwen-coder"`,
   env `SWARM_MANUS_MODEL`. Тест на парсинг/дефолт — в существующем стиле.
2. `worker.py`: `spawn_manus_worker` использует `config.manus_model` как есть
   (без `_manus_model()`-маппинга; удали маппинг и `MANUS_MODEL_ALIASES`,
   если больше нигде не нужны). `--summarizer` — та же модель.
3. Обнови затронутые тесты. Ничего больше не трогай.

## Критерии готовности
1. pytest/ruff зелёные.
2. Живой прогон с ДЕФОЛТНЫМ окружением (без SWARM_MODEL-переопределений):
   `uv run swarm run "делегируй воркеру с backend=manus задачу: создай в
   своей директории файл note.md с тремя фактами о Kaggle. Проверь файл и
   заверши"` — Manus-воркер должен пройти (ok=true, note.md существует),
   драйвер при этом остаётся на Kimi. Факты: stdout + ls workspace + хвост
   manus_output.log в финальное сообщение.
3. Один коммит `fix: separate manus worker model from driver model`.
