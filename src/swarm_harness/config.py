import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    api_key: str
    base_url: str = "https://foundation-models.api.cloud.ru/v1"
    model: str = "moonshotai/Kimi-K2.6"
    max_iterations: int = 40
    worker_timeout: int = 1800
    max_parallel_workers: int = 4
    worker_proxy: str = ""

    @classmethod
    def from_env(cls, env_file: str | Path | None = ".env") -> "Config":
        if env_file is not None:
            env_path = Path(env_file)
            if env_path.exists():
                load_dotenv(dotenv_path=env_path)

        api_key = os.getenv("FM_API_KEY", "").strip()
        if not api_key:
            raise ConfigError("FM_API_KEY is required")

        return cls(
            api_key=api_key,
            base_url=os.getenv("SWARM_BASE_URL", cls.base_url),
            model=os.getenv("SWARM_MODEL", cls.model),
            max_iterations=int(
                os.getenv("SWARM_MAX_ITERATIONS", str(cls.max_iterations))
            ),
            worker_timeout=int(
                os.getenv("SWARM_WORKER_TIMEOUT", str(cls.worker_timeout))
            ),
            max_parallel_workers=int(
                os.getenv(
                    "SWARM_MAX_PARALLEL_WORKERS",
                    str(cls.max_parallel_workers),
                )
            ),
            worker_proxy=os.getenv("SWARM_WORKER_PROXY", cls.worker_proxy),
        )
