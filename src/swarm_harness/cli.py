import argparse
import sys

from openai import OpenAIError

from swarm_harness.config import Config, ConfigError
from swarm_harness.llm import LLMClient
from swarm_harness.loop import run_task


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="swarm")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("selfcheck")

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("task")

    args = parser.parse_args(argv)

    if args.command == "selfcheck":
        return _selfcheck()
    if args.command == "run":
        return _run(args.task)

    parser.error("unknown command")


def _selfcheck() -> int:
    try:
        config = Config.from_env()
        result = LLMClient(config).chat(
            [{"role": "user", "content": "Ответь одним словом: работаешь?"}]
        )
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OpenAIError as exc:
        print(f"api error: {exc}", file=sys.stderr)
        return 1

    print(f"model={config.model} base={config.base_url}")
    print(result.text)
    return 0


def _run(task: str) -> int:
    try:
        config = Config.from_env()
        result = run_task(task, config, LLMClient(config))
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OpenAIError as exc:
        print(f"api error: {exc}", file=sys.stderr)
        return 1

    print(f"status={result.status} run_dir={result.run_dir}")
    print(result.result)
    if result.status == "completed":
        return 0
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
