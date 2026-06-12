import os
from pathlib import Path

from swarm_harness.config import Config
from swarm_harness.worker import spawn_codex_worker, spawn_manus_worker


def _stub(tmp_path: Path, body: str) -> Path:
    script = tmp_path / "codex-stub.sh"
    script.write_text(f"#!/bin/sh\nset -eu\n{body}\n")
    script.chmod(0o755)
    return script


def _uv_stub(tmp_path: Path, body: str) -> Path:
    script = tmp_path / "uv"
    script.write_text(f"#!/bin/sh\nset -eu\n{body}\n")
    script.chmod(0o755)
    return script


def test_spawn_codex_worker_returns_message_and_changed_files(tmp_path: Path) -> None:
    executable = _stub(
        tmp_path,
        """
cat >/dev/null
printf 'готово' > .worker/last_message.txt
printf 'content' > out.txt
""",
    )

    result = spawn_codex_worker(
        "сделай файл",
        "worker-01",
        tmp_path / "run",
        Config(api_key="test"),
        executable=str(executable),
    )

    assert result.ok is True
    assert result.message == "готово"
    assert result.files == ["out.txt"]
    assert result.workspace == tmp_path / "run" / "workers" / "worker-01"


def test_spawn_codex_worker_reports_nonzero_exit_tail(tmp_path: Path) -> None:
    executable = _stub(
        tmp_path,
        """
cat >/dev/null
echo 'boom from stderr' >&2
exit 2
""",
    )

    result = spawn_codex_worker(
        "упади",
        "worker-01",
        tmp_path / "run",
        Config(api_key="test"),
        executable=str(executable),
    )

    assert result.ok is False
    assert "boom from stderr" in result.message


def test_spawn_codex_worker_times_out(tmp_path: Path) -> None:
    executable = _stub(tmp_path, "sleep 5")

    result = spawn_codex_worker(
        "зависни",
        "worker-01",
        tmp_path / "run",
        Config(api_key="test", worker_timeout=1),
        executable=str(executable),
    )

    assert result.ok is False
    assert "timed out" in result.message


def test_spawn_manus_worker_returns_summary_and_changed_files(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manus_agent_path = tmp_path / "manus-agent"
    manus_agent_path.mkdir()
    _uv_stub(
        tmp_path,
        """
test "$LLM_API_KEY" = "test-key"
test "$MANUS_CLOUDRU_BASE" = "https://fm.example/v1"
test "$MANUS_THINKING" = "off"
test "$PWD" = "__MANUS_AGENT_PATH__"
model=""
summarizer=""
session=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --model)
      shift
      model="$1"
      ;;
    --summarizer)
      shift
      summarizer="$1"
      ;;
    --id)
      shift
      session="$1"
      ;;
  esac
  shift || true
done
test "$model" = "custom-manus"
test "$summarizer" = "custom-manus"
workspace="$HOME/manus/workspace/$session"
printf 'готово' > "$workspace/summary.md"
printf 'fact one' > "$workspace/note.md"
""".replace("__MANUS_AGENT_PATH__", str(manus_agent_path)),
    )
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(
        "swarm_harness.worker.MANUS_AGENT_PATH",
        manus_agent_path,
    )

    result = spawn_manus_worker(
        "сделай файл",
        "worker-01",
        tmp_path / "run",
        Config(
            api_key="test-key",
            base_url="https://fm.example/v1",
            model="moonshotai/Kimi-K2.6",
            manus_model="custom-manus",
        ),
    )

    assert result.ok is True
    assert result.message == "готово"
    assert result.files == ["note.md"]
    assert result.workspace == tmp_path / "run" / "workers" / "worker-01"
    assert result.workspace.joinpath("task.md").read_text() == "сделай файл"


def test_spawn_manus_worker_reports_missing_summary(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manus_agent_path = tmp_path / "manus-agent"
    manus_agent_path.mkdir()
    _uv_stub(tmp_path, "true")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(
        "swarm_harness.worker.MANUS_AGENT_PATH",
        manus_agent_path,
    )

    result = spawn_manus_worker(
        "не пиши summary",
        "worker-01",
        tmp_path / "run",
        Config(api_key="test", model="Qwen/Qwen3-Coder-Next"),
    )

    assert result.ok is False
    assert "summary.md" in result.message


def test_spawn_manus_worker_times_out(monkeypatch, tmp_path: Path) -> None:
    manus_agent_path = tmp_path / "manus-agent"
    manus_agent_path.mkdir()
    _uv_stub(tmp_path, "sleep 5")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(
        "swarm_harness.worker.MANUS_AGENT_PATH",
        manus_agent_path,
    )

    result = spawn_manus_worker(
        "зависни",
        "worker-01",
        tmp_path / "run",
        Config(api_key="test", model="Qwen/Qwen3-Coder-Next", worker_timeout=1),
    )

    assert result.ok is False
    assert "timed out" in result.message
