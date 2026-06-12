import json
import time
from dataclasses import dataclass
from typing import Any

from openai import APIConnectionError, APIStatusError, OpenAI, RateLimitError

from swarm_harness.config import Config


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ChatResult:
    text: str
    tool_calls: list[ToolCall]
    raw: Any


class LLMClient:
    def __init__(self, config: Config):
        self._config = config
        self._client = OpenAI(api_key=config.api_key, base_url=config.base_url)

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> ChatResult:
        kwargs: dict[str, Any] = {
            "model": self._config.model,
            "messages": messages,
        }
        if tools is not None:
            kwargs["tools"] = tools

        response = self._create_with_retries(kwargs)
        message = response.choices[0].message
        return ChatResult(
            text=message.content or "",
            tool_calls=[
                ToolCall(
                    id=call.id,
                    name=call.function.name,
                    arguments=_parse_arguments(call.function.arguments or ""),
                )
                for call in (message.tool_calls or [])
            ],
            raw=response,
        )

    def _create_with_retries(self, kwargs: dict[str, Any]) -> Any:
        for attempt in range(3):
            try:
                return self._client.chat.completions.create(**kwargs)
            except (APIConnectionError, RateLimitError):
                if attempt == 2:
                    raise
                time.sleep(2)
            except APIStatusError as exc:
                if exc.status_code < 500 or attempt == 2:
                    raise
                time.sleep(2)

        raise RuntimeError("unreachable")


def _parse_arguments(arguments: str) -> dict:
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError:
        return {"_raw": arguments}

    if isinstance(parsed, dict):
        return parsed
    return {"_raw": arguments}
