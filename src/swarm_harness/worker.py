import os
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from swarm_harness.config import Config


LOG_TAIL_CHARS = 2000
MANUS_AGENT_PATH = Path.home() / "Code" / "manus-agent"
MANUS_GROUPS = "file,memory,shell,code,todo,skills,lifecycle"
MANUS_SERVICE_PATHS = {
    ("todo.md",),
    ("journal.md",),
    ("session.jsonl",),
    ("state.json",),
    ("summary.md",),
    ("events",),
    ("observations",),
}


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


def spawn_manus_worker(
    task: str,
    worker_id: str,
    run_dir: Path,
    config: Config,
) -> WorkerResult:
    workspace = run_dir / "workers" / worker_id
    worker_dir = workspace / ".worker"
    workspace.mkdir(parents=True, exist_ok=True)
    worker_dir.mkdir(parents=True, exist_ok=True)

    task_path = workspace / "task.md"
    summary_path = workspace / "summary.md"
    log_path = worker_dir / "manus_output.log"
    task_path.write_text(task)

    session_id = _safe_session_id(worker_id)
    home_dir = worker_dir / "home"
    _prepare_manus_home(home_dir, session_id, workspace)

    before = _snapshot(workspace, service_paths=MANUS_SERVICE_PATHS)
    command = [
        "uv",
        "run",
        "manus",
        "run",
        "--model",
        config.manus_model,
        "--summarizer",
        config.manus_model,
        "--groups",
        MANUS_GROUPS,
        "--id",
        session_id,
        _manus_task(task_path),
    ]

    returncode = 0
    timed_out = False
    with log_path.open("w") as log_file:
        try:
            process = subprocess.Popen(
                command,
                cwd=MANUS_AGENT_PATH,
                env=_manus_env(config, home_dir, workspace.parent),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
            returncode = process.wait(timeout=config.worker_timeout)
        except OSError as exc:
            log_file.write(f"failed to start Manus worker: {exc}\n")
            returncode = 1
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_process_group(process.pid)
            returncode = process.wait()
        finally:
            log_file.flush()

    files = _changed_files(
        workspace,
        before,
        service_paths=MANUS_SERVICE_PATHS,
    )
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
    if not summary_path.exists():
        return WorkerResult(
            worker_id=worker_id,
            ok=False,
            message="worker succeeded but summary.md was not created",
            files=files,
            workspace=workspace,
        )

    return WorkerResult(
        worker_id=worker_id,
        ok=True,
        message=summary_path.read_text(),
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


def _manus_env(config: Config, home_dir: Path, workspace_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(home_dir.resolve())
    env["LLM_API_KEY"] = config.api_key
    env["MANUS_CLOUDRU_BASE"] = config.base_url
    env["MANUS_THINKING"] = "off"
    env["MANUS_WORKSPACE_ROOT"] = str(workspace_root.resolve())
    # Воркеры не общаются с человеком напрямую: глушим Telegram явно
    # (фейковый HOME и так прячет ~/.config/manus/secrets.env, но контракт
    # должен быть виден в коде, а не держаться на side effect).
    env["MANUS_TG_BOT_TOKEN"] = ""
    env["MANUS_TG_USER_ID"] = ""
    if config.vlm_base:
        env["MANUS_VLM_BASE"] = config.vlm_base
    env["LLM_BASE_URL"] = config.base_url
    env["OPENAI_BASE_URL"] = config.base_url
    _merge_no_proxy(env, config.base_url)
    return env


def _prepare_manus_home(home_dir: Path, session_id: str, workspace: Path) -> None:
    workspaces_dir = home_dir / "manus" / "workspace"
    workspaces_dir.mkdir(parents=True, exist_ok=True)
    target = workspaces_dir / session_id
    if target.exists() or target.is_symlink():
        return
    target.symlink_to(workspace.resolve(), target_is_directory=True)


def _manus_task(task_path: Path) -> str:
    return (
        "You are running as a swarm-harness Manus worker. "
        f"Read the task from {task_path}. Work inside your active workspace. "
        "Write requested durable files in that workspace. "
        "Write the final worker message to summary.md, then finish with idle()."
    )


def _merge_no_proxy(env: dict[str, str], base_url: str) -> None:
    parsed = urlparse(base_url)
    hosts = {"foundation-models.api.cloud.ru", ".cloud.ru"}
    if parsed.hostname:
        hosts.add(parsed.hostname)
    for key in ("NO_PROXY", "no_proxy"):
        existing = [item.strip() for item in env.get(key, "").split(",") if item.strip()]
        merged = existing + [host for host in sorted(hosts) if host not in existing]
        env[key] = ",".join(merged)


def _snapshot(
    workspace: Path,
    service_paths: set[tuple[str, ...]] | None = None,
) -> dict[str, tuple[int, int]]:
    snapshot: dict[str, tuple[int, int]] = {}
    for path in workspace.rglob("*"):
        if not path.is_file() or _is_service_path(
            path,
            workspace,
            service_paths=service_paths,
        ):
            continue
        stat = path.stat()
        snapshot[path.relative_to(workspace).as_posix()] = (
            stat.st_mtime_ns,
            stat.st_size,
        )
    return snapshot


def _changed_files(
    workspace: Path,
    before: dict[str, tuple[int, int]],
    service_paths: set[tuple[str, ...]] | None = None,
) -> list[str]:
    changed = []
    for path in workspace.rglob("*"):
        if not path.is_file() or _is_service_path(
            path,
            workspace,
            service_paths=service_paths,
        ):
            continue
        rel_path = path.relative_to(workspace).as_posix()
        stat = path.stat()
        if before.get(rel_path) != (stat.st_mtime_ns, stat.st_size):
            changed.append(rel_path)
    return sorted(changed)


def _is_service_path(
    path: Path,
    workspace: Path,
    service_paths: set[tuple[str, ...]] | None = None,
) -> bool:
    rel_parts = path.relative_to(workspace).parts
    if rel_parts[0] == ".worker" or rel_parts == ("task.md",):
        return True
    return any(rel_parts[: len(service_path)] == service_path for service_path in service_paths or set())


def _safe_session_id(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in "._-" else "-" for char in value)
    safe = safe.strip(".-")
    return safe[:96] or "worker"


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
