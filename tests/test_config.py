import pytest

from swarm_harness.config import Config, ConfigError


ENV_KEYS = [
    "FM_API_KEY",
    "SWARM_BASE_URL",
    "SWARM_MODEL",
    "SWARM_MAX_ITERATIONS",
    "SWARM_WORKER_TIMEOUT",
    "SWARM_WORKER_PROXY",
]


def clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_from_env_parses_all_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_env(monkeypatch)
    monkeypatch.setenv("FM_API_KEY", "secret")
    monkeypatch.setenv("SWARM_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("SWARM_MODEL", "test-model")
    monkeypatch.setenv("SWARM_MAX_ITERATIONS", "7")
    monkeypatch.setenv("SWARM_WORKER_TIMEOUT", "90")
    monkeypatch.setenv("SWARM_WORKER_PROXY", "http://proxy.test:8080")

    config = Config.from_env(env_file=None)

    assert config.api_key == "secret"
    assert config.base_url == "https://example.test/v1"
    assert config.model == "test-model"
    assert config.max_iterations == 7
    assert isinstance(config.max_iterations, int)
    assert config.worker_timeout == 90
    assert isinstance(config.worker_timeout, int)
    assert config.worker_proxy == "http://proxy.test:8080"


def test_from_env_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_env(monkeypatch)

    with pytest.raises(ConfigError, match="FM_API_KEY"):
        Config.from_env(env_file=None)


def test_from_env_uses_defaults_for_optional_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_env(monkeypatch)
    monkeypatch.setenv("FM_API_KEY", "secret")

    config = Config.from_env(env_file=None)

    assert config == Config(api_key="secret")
