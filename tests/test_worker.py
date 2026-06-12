from pathlib import Path

from swarm_harness.config import Config
from swarm_harness.worker import spawn_codex_worker


def _stub(tmp_path: Path, body: str) -> Path:
    script = tmp_path / "codex-stub.sh"
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
