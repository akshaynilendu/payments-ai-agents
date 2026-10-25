"""Model clients for tool use: the real Anthropic client and a scripted fake for tests ($0, no network).
Same design as Project 2's investigator/llm.py."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from . import config


@dataclass(frozen=True)
class AgentResponse:
    blocks: list  # content blocks as plain dicts, echoed back unchanged (thinking blocks included)
    input_tokens: int
    output_tokens: int
    stop_reason: str


class LLMError(Exception):
    """The call itself failed. Messages never contain the key or the prompt."""


class AnthropicClient:
    def __init__(self, model: str = config.CLAUDE_MODEL, env_file: Path = config.ENV_FILE):
        import anthropic
        from dotenv import load_dotenv

        load_dotenv(env_file, override=False)
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise LLMError(f"ANTHROPIC_API_KEY is not set; add it to {env_file.name} (gitignored)")
        self.model = model
        self._settings = config.MODEL_SETTINGS[model]
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(timeout=self._settings.get("timeout_s", config.LLM_TIMEOUT_SECONDS),
                                           max_retries=config.LLM_SDK_RETRIES)

    def chat(self, system: str, messages: list, tools: list) -> AgentResponse:
        kwargs = dict(model=self.model, max_tokens=self._settings["max_tokens"], system=system,
                      messages=messages, tools=tools)
        if "effort" in self._settings:
            kwargs["output_config"] = {"effort": self._settings["effort"]}
        try:
            response = self._client.messages.create(**kwargs)
        except self._anthropic.APIError as e:
            raise LLMError(f"model call failed: {type(e).__name__}") from None
        blocks = [b.model_dump(exclude_none=True) for b in response.content]
        return AgentResponse(blocks, response.usage.input_tokens, response.usage.output_tokens,
                             response.stop_reason or "")


@dataclass
class FakeAgentLLM:
    """Scripted agent turns: each turn is a list of blocks, e.g. [{"type": "tool_use", ...}]."""
    turns: list
    model: str = config.CLAUDE_MODEL
    input_tokens: int = 2000
    output_tokens: int = 200
    calls: list = field(default_factory=list)

    def chat(self, system: str, messages: list, tools: list) -> AgentResponse:
        self.calls.append({"system": system, "messages": json.loads(json.dumps(messages, default=str)),
                           "tools": [t["name"] for t in tools]})
        if len(self.calls) > len(self.turns):
            raise AssertionError(f"FakeAgentLLM called {len(self.calls)} times but scripted {len(self.turns)} turns")
        turn = self.turns[len(self.calls) - 1]
        if isinstance(turn, Exception):
            raise turn
        return AgentResponse(turn, self.input_tokens, self.output_tokens, "tool_use")


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    i, o = config.MODEL_PRICES_PER_MTOK[model]
    return input_tokens * i / 1e6 + output_tokens * o / 1e6
