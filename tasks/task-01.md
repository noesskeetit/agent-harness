# T1: Scaffold + LLM-клиент + selfcheck

Прочитай сначала `SPEC.md` и `AGENTS.md` в корне репозитория — они задают
правила. Это первая задача нового проекта, репозиторий почти пуст.

## Что сделать

### 1. `pyproject.toml`
- Проект `swarm-harness`, пакет `swarm_harness` в `src/`-layout,
  Python `>=3.12`.
- Зависимости: `openai`, `python-dotenv`. Dev-группа: `pytest`, `ruff`.
- Console script: `swarm = "swarm_harness.cli:main"`.
- Менеджер — `uv` (создай uv.lock через `uv sync`).

### 2. `src/swarm_harness/config.py`
```python
@dataclass(frozen=True)
class Config:
    api_key: str
    base_url: str = "https://foundation-models.api.cloud.ru/v1"
    model: str = "moonshotai/Kimi-K2.6"
    max_iterations: int = 40
    worker_timeout: int = 1800
    worker_proxy: str = ""

    @classmethod
    def from_env(cls, env_file: str | Path | None = ".env") -> "Config": ...
```
- `from_env` грузит `.env` через python-dotenv (если файл есть), затем читает
  переменные окружения: `FM_API_KEY` (обязательна — если пусто, raise
  `ConfigError` с понятным текстом), `SWARM_BASE_URL`, `SWARM_MODEL`,
  `SWARM_MAX_ITERATIONS`, `SWARM_WORKER_TIMEOUT`, `SWARM_WORKER_PROXY`.
- `ConfigError(Exception)` определи здесь же.

### 3. `src/swarm_harness/llm.py`
```python
class LLMClient:
    def __init__(self, config: Config): ...
    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> "ChatResult": ...

@dataclass
class ChatResult:
    text: str                      # content ассистента ("" если только tool calls)
    tool_calls: list[ToolCall]     # [] если нет
    raw: Any                       # полный response object

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict  # уже распарсенный JSON; при невалидном JSON -> {"_raw": "<строка>"}
```
- Внутри — официальный `openai` SDK с `base_url` из конфига.
- 2 ретрая с паузой 2с на сетевых/5xx ошибках (`APIConnectionError`,
  `APIStatusError >= 500`, `RateLimitError`). На прочих — пробрасывать.
- Никакого стриминга, никаких обёрток поверх этого.

### 4. `src/swarm_harness/cli.py`
- `argparse`, подкоманды:
  - `swarm selfcheck` — живой вызов: `chat([{"role":"user","content":"Ответь одним словом: работаешь?"}])`,
    напечатать `model=<model> base=<base_url>` и ответ модели. Exit code 0.
    При `ConfigError` или ошибке API — человекочитаемая ошибка в stderr, exit 1.
  - `swarm run <task>` — пока заглушка: печатает `run: not implemented yet`,
    exit 2.

### 5. Тесты (`tests/test_config.py`)
Поведение `Config.from_env` через monkeypatch окружения (без чтения реального
`.env` — передавай `env_file=None`):
- все переменные заданы → поля распарсены, int-поля int;
- отсутствует `FM_API_KEY` → `ConfigError`;
- не заданы опциональные → дефолты из SPEC.
LLM-клиент в этой задаче юнитами не покрывай (его проверит selfcheck живьём).

### 6. `.gitignore`
`.env`, `runs/`, `.agent/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`,
`.venv/`, `*.egg-info/`.

## Критерии готовности
1. `uv run pytest -q` — зелёные.
2. `uv run ruff check src tests` — чисто.
3. `uv run swarm selfcheck` — живой ответ модели (ключ уже лежит в `.env`
   в корне репо). Вставь фактический вывод в финальное сообщение.
4. Один коммит `feat: scaffold, config, llm client, selfcheck CLI`.
   `.env`, `runs/`, `.agent/` в коммит не попадают.

## Запрещено в этой задаче
Driver loop, тулы, воркеры, README, доки, Makefile, CI, докстринги-эссе,
любые файлы сверх перечисленных.
