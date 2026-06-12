import os
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path

from swarm_harness.config import Config


LOG_TAIL_CHARS = 2000


@dataclass
class WorkerResult:
    worker_id: str
    ok: bool
    message: str
    files: list[str]
    workspace: Path


def spawn_codex_worker(
    task: str,
    worker_id: str,
    run_dir: Path,
    config: Config,
    executable: str = "codex",
) -> WorkerResult:
    workspace = run_dir / "workers" / worker_id
    worker_dir = workspace / ".worker"
    workspace.mkdir(parents=True, exist_ok=True)
    worker_dir.mkdir(parents=True, exist_ok=True)

    task_path = workspace / "task.md"
    last_message_path = worker_dir / "last_message.txt"
    log_path = worker_dir / "codex_output.log"
    task_path.write_text(task)

    before = _snapshot(workspace)
    command = [
        executable,
        "exec",
        "--sandbox",
        "workspace-write",
        "--skip-git-repo-check",
        "--output-last-message",
        ".worker/last_message.txt",
        "-",
    ]

    returncode = 0
    timed_out = False
    with task_path.open() as stdin_file, log_path.open("w") as log_file:
        process = subprocess.Popen(
            command,
            cwd=workspace,
            env=_worker_env(config),
            stdin=stdin_file,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            returncode = process.wait(timeout=config.worker_timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_process_group(process.pid)
            returncode = process.wait()
        finally:
            log_file.flush()

    files = _changed_files(workspace, before)
    if timed_out:
        return WorkerResult(
            worker_id=worker_id,
            ok=False,
            message=(
                f"worker timed out after {config.worker_timeout}s\n"
                f"{_tail(log_path)}"
            ).rstrip(),
            files=files,
            workspace=workspace,
        )
    if returncode != 0:
        return WorkerResult(
            worker_id=worker_id,
            ok=False,
            message=_tail(log_path),
            files=files,
            workspace=workspace,
        )
    if not last_message_path.exists():
        return WorkerResult(
            worker_id=worker_id,
            ok=False,
            message="worker succeeded but .worker/last_message.txt was not created",
            files=files,
            workspace=workspace,
        )

    return WorkerResult(
        worker_id=worker_id,
        ok=True,
        message=last_message_path.read_text(),
        files=files,
        workspace=workspace,
    )


def _worker_env(config: Config) -> dict[str, str]:
    env = os.environ.copy()
    if config.worker_proxy:
        for key in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        ):
            env[key] = config.worker_proxy
        env["NO_PROXY"] = "localhost,127.0.0.1"
        env["no_proxy"] = "localhost,127.0.0.1"
    return env


def _snapshot(workspace: Path) -> dict[str, tuple[int, int]]:
    snapshot: dict[str, tuple[int, int]] = {}
    for path in workspace.rglob("*"):
        if not path.is_file() or _is_service_path(path, workspace):
            continue
        stat = path.stat()
        snapshot[path.relative_to(workspace).as_posix()] = (
            stat.st_mtime_ns,
            stat.st_size,
        )
    return snapshot


def _changed_files(workspace: Path, before: dict[str, tuple[int, int]]) -> list[str]:
    changed = []
    for path in workspace.rglob("*"):
        if not path.is_file() or _is_service_path(path, workspace):
            continue
        rel_path = path.relative_to(workspace).as_posix()
        stat = path.stat()
        if before.get(rel_path) != (stat.st_mtime_ns, stat.st_size):
            changed.append(rel_path)
    return sorted(changed)


def _is_service_path(path: Path, workspace: Path) -> bool:
    rel_parts = path.relative_to(workspace).parts
    return rel_parts[0] == ".worker" or rel_parts == ("task.md",)


def _tail(path: Path, limit: int = LOG_TAIL_CHARS) -> str:
    if not path.exists():
        return ""
    content = path.read_text(errors="replace")
    return content[-limit:]


def _kill_process_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
