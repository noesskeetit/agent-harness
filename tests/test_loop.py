import json
from pathlib import Path

from swarm_harness import cli
from swarm_harness.config import Config
from swarm_harness.llm import ChatResult, ToolCall
from swarm_harness.loop import RunResult, run_task


class FakeLLM:
    def __init__(self, responses: list[ChatResult], repeat_last: bool = False):
        self._responses = responses
        self._repeat_last = repeat_last
        self._index = 0
        self.messages_seen: list[list[dict]] = []

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> ChatResult:
        self.messages_seen.append(messages)
        if self._index < len(self._responses):
            response = self._responses[self._index]
            self._index += 1
            return response
        if self._repeat_last:
            return self._responses[-1]
        raise AssertionError("FakeLLM has no response left")


def tool_call(call_id: str, name: str, arguments: dict) -> ToolCall:
    return ToolCall(id=call_id, name=name, arguments=arguments)


def chat_with_tools(*calls: ToolCall) -> ChatResult:
    return ChatResult(text="", tool_calls=list(calls), raw=None)


def test_write_file_then_finish_creates_file_and_jsonl_transcript(tmp_path: Path) -> None:
    fake_llm = FakeLLM(
        [
            chat_with_tools(
                tool_call(
                    "call_write",
                    "write_file",
                    {"path": "answer.txt", "content": "4\n"},
                )
            ),
            chat_with_tools(
                tool_call("call_finish", "finish", {"result": "answer is 4"})
            ),
        ]
    )

    result = run_task(
        "create answer",
        Config(api_key="test", max_iterations=5),
        fake_llm,
        run_dir=tmp_path,
    )

    assert result.status == "completed"
    assert result.result == "answer is 4"
    assert (tmp_path / "answer.txt").read_text() == "4\n"
    assert (tmp_path / "result.md").read_text() == "answer is 4"

    transcript = tmp_path / "transcript.jsonl"
    assert transcript.exists()
    for line in transcript.read_text().splitlines():
        json.loads(line)


def test_run_task_stops_after_max_iterations(tmp_path: Path) -> None:
    fake_llm = FakeLLM(
        [
            chat_with_tools(
                tool_call("call_run", "run_command", {"cmd": "echo x"})
            )
        ],
        repeat_last=True,
    )

    result = run_task(
        "loop forever",
        Config(api_key="test", max_iterations=2),
        fake_llm,
        run_dir=tmp_path,
    )

    assert result.status == "budget_exceeded"
    assert result.iterations == 2


def test_unknown_tool_does_not_abort_run(tmp_path: Path) -> None:
    fake_llm = FakeLLM(
        [
            chat_with_tools(tool_call("call_bad", "missing_tool", {})),
            chat_with_tools(tool_call("call_finish", "finish", {"result": "done"})),
        ]
    )

    result = run_task(
        "call a missing tool",
        Config(api_key="test", max_iterations=5),
        fake_llm,
        run_dir=tmp_path,
    )

    assert result.status == "completed"
    assert result.result == "done"


def test_run_command_timeout_is_reported_and_run_can_finish(tmp_path: Path) -> None:
    fake_llm = FakeLLM(
        [
            chat_with_tools(
                tool_call("call_sleep", "run_command", {"cmd": "sleep 5"})
            ),
            chat_with_tools(
                tool_call("call_finish", "finish", {"result": "timed out handled"})
            ),
        ]
    )

    result = run_task(
        "handle timeout",
        Config(api_key="test", max_iterations=5),
        fake_llm,
        run_dir=tmp_path,
        command_timeout=1,
    )

    transcript_text = (tmp_path / "transcript.jsonl").read_text()
    assert result.status == "completed"
    assert "timed out" in transcript_text


def test_cli_run_prints_status_result_and_exit_code(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    config = Config(api_key="test")
    fake_result = RunResult(
        status="budget_exceeded",
        result="partial",
        iterations=2,
        run_dir=tmp_path,
    )

    class FakeClient:
        def __init__(self, received_config: Config):
            self.received_config = received_config

    class FakeConfig:
        @classmethod
        def from_env(cls) -> Config:
            return config

    def fake_run_task(task: str, received_config: Config, llm) -> RunResult:
        assert task == "do work"
        assert received_config is config
        assert isinstance(llm, FakeClient)
        return fake_result

    monkeypatch.setattr(cli, "Config", FakeConfig)
    monkeypatch.setattr(cli, "LLMClient", FakeClient)
    monkeypatch.setattr(cli, "run_task", fake_run_task)

    exit_code = cli.main(["run", "do work"])

    captured = capsys.readouterr()
    assert exit_code == 3
    assert f"status=budget_exceeded run_dir={tmp_path}" in captured.out
    assert "partial" in captured.out
