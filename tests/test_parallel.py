import time
from pathlib import Path

from swarm_harness.config import Config
from swarm_harness.tools import execute_tool
from swarm_harness.worker import WorkerResult


def test_spawn_workers_obeys_parallel_worker_cap(monkeypatch, tmp_path: Path) -> None:
    def fake_spawn_codex_worker(
        task: str,
        worker_id: str,
        run_dir: Path,
        config: Config,
    ) -> WorkerResult:
        time.sleep(0.3)
        return WorkerResult(
            worker_id=worker_id,
            ok=True,
            message=task,
            files=[],
            workspace=run_dir / "workers" / worker_id,
        )

    monkeypatch.setattr(
        "swarm_harness.tools.spawn_codex_worker",
        fake_spawn_codex_worker,
    )
    tasks = [{"task": "a"}, {"task": "b"}, {"task": "c"}]

    started = time.perf_counter()
    execute_tool(
        "spawn_workers",
        {"tasks": tasks},
        tmp_path / "parallel",
        300,
        Config(api_key="test", max_parallel_workers=4),
    )
    parallel_elapsed = time.perf_counter() - started

    started = time.perf_counter()
    execute_tool(
        "spawn_workers",
        {"tasks": tasks},
        tmp_path / "serial",
        300,
        Config(api_key="test", max_parallel_workers=1),
    )
    serial_elapsed = time.perf_counter() - started

    assert parallel_elapsed < 0.7
    assert serial_elapsed >= 0.9


def test_spawn_workers_autonumbers_after_existing_workers(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (tmp_path / "workers" / "worker-01").mkdir(parents=True)

    def fake_spawn_codex_worker(
        task: str,
        worker_id: str,
        run_dir: Path,
        config: Config,
    ) -> WorkerResult:
        return WorkerResult(
            worker_id=worker_id,
            ok=True,
            message=task,
            files=[],
            workspace=run_dir / "workers" / worker_id,
        )

    monkeypatch.setattr(
        "swarm_harness.tools.spawn_codex_worker",
        fake_spawn_codex_worker,
    )

    output, finish_result = execute_tool(
        "spawn_workers",
        {"tasks": [{"task": "a"}, {"task": "b"}]},
        tmp_path,
        300,
        Config(api_key="test"),
    )

    assert finish_result is None
    assert "worker=worker-02 ok=true" in output
    assert "worker=worker-03 ok=true" in output


def test_spawn_workers_rejects_duplicate_worker_id_in_batch(tmp_path: Path) -> None:
    output, finish_result = execute_tool(
        "spawn_workers",
        {
            "tasks": [
                {"task": "a", "worker_id": "same"},
                {"task": "b", "worker_id": "same"},
            ]
        },
        tmp_path,
        300,
        Config(api_key="test"),
    )

    assert finish_result is None
    assert "duplicate worker_id" in output
    assert "same" in output


def test_spawn_workers_returns_blocks_in_input_order(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def fake_spawn_codex_worker(
        task: str,
        worker_id: str,
        run_dir: Path,
        config: Config,
    ) -> WorkerResult:
        if task == "slow":
            time.sleep(0.3)
        return WorkerResult(
            worker_id=worker_id,
            ok=True,
            message=task,
            files=[],
            workspace=run_dir / "workers" / worker_id,
        )

    monkeypatch.setattr(
        "swarm_harness.tools.spawn_codex_worker",
        fake_spawn_codex_worker,
    )

    output, _ = execute_tool(
        "spawn_workers",
        {
            "tasks": [
                {"task": "slow", "worker_id": "first"},
                {"task": "fast", "worker_id": "second"},
            ]
        },
        tmp_path,
        300,
        Config(api_key="test"),
    )

    assert output.split("\n---\n")[0].startswith("worker=first ok=true")
    assert output.split("\n---\n")[1].startswith("worker=second ok=true")


def test_spawn_workers_reports_one_exception_without_aborting_batch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def fake_spawn_codex_worker(
        task: str,
        worker_id: str,
        run_dir: Path,
        config: Config,
    ) -> WorkerResult:
        if task == "bad":
            raise RuntimeError("boom")
        return WorkerResult(
            worker_id=worker_id,
            ok=True,
            message=task,
            files=[],
            workspace=run_dir / "workers" / worker_id,
        )

    monkeypatch.setattr(
        "swarm_harness.tools.spawn_codex_worker",
        fake_spawn_codex_worker,
    )

    output, finish_result = execute_tool(
        "spawn_workers",
        {
            "tasks": [
                {"task": "ok", "worker_id": "good"},
                {"task": "bad", "worker_id": "bad"},
                {"task": "ok2", "worker_id": "other"},
            ]
        },
        tmp_path,
        300,
        Config(api_key="test"),
    )

    assert finish_result is None
    assert "worker=good ok=true" in output
    assert "worker=bad ok=false" in output
    assert "RuntimeError: boom" in output
    assert "worker=other ok=true" in output


def test_spawn_workers_routes_manus_backend(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def fake_spawn_manus_worker(
        task: str,
        worker_id: str,
        run_dir: Path,
        config: Config,
        model: str = "",
    ) -> WorkerResult:
        return WorkerResult(
            worker_id=worker_id,
            ok=True,
            message=f"manus:{task}",
            files=["note.md"],
            workspace=run_dir / "workers" / worker_id,
        )

    monkeypatch.setattr(
        "swarm_harness.tools.spawn_manus_worker",
        fake_spawn_manus_worker,
    )

    output, finish_result = execute_tool(
        "spawn_workers",
        {"tasks": [{"task": "research", "backend": "manus"}]},
        tmp_path,
        300,
        Config(api_key="test"),
    )

    assert finish_result is None
    assert "worker=worker-01 ok=true" in output
    assert "note.md" in output
    assert "manus:research" in output
