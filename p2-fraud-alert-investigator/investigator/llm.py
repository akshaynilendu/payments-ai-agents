"""Model clients: an interface, the real Anthropic client, and a scripted fake for tests ($0, no network).
Same design as Project 1's explainer/llm.py."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from investigator import config


@dataclass(frozen=True)
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    stop_reason: str  # "end_turn" is normal; "max_tokens" or "refusal" mean the text can't be trusted


class LLMError(Exception):
    """The call itself failed. Messages never contain the key or the prompt."""


class LLMClient(Protocol):
    model: str

    def complete(self, system: str, user: str, schema: dict) -> LLMResponse: ...


class AnthropicClient:
    def __init__(self, model: str = config.CLAUDE_MODEL, env_file: Path = config.ENV_FILE):
        import anthropic
        from dotenv import load_dotenv

        load_dotenv(env_file, override=False)
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise LLMError(f"ANTHROPIC_API_KEY is not set; add it to {env_file.name} (gitignored)")
        if model not in config.MODEL_SETTINGS:
            raise LLMError(f"no settings for model {model!r} in config.MODEL_SETTINGS")
        self.model = model
        self._settings = config.MODEL_SETTINGS[model]
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(timeout=self._settings.get("timeout_s", config.LLM_TIMEOUT_SECONDS),
                                           max_retries=config.LLM_SDK_RETRIES)

    def complete(self, system: str, user: str, schema: dict) -> LLMResponse:
        output_config = {"format": {"type": "json_schema", "schema": schema}}
        if "effort" in self._settings:
            output_config["effort"] = self._settings["effort"]
        try:
            response = self._client.messages.create(
                model=self.model, max_tokens=self._settings["max_tokens"], system=system,
                messages=[{"role": "user", "content": user}], output_config=output_config)
        except self._anthropic.APIError as e:
            raise LLMError(f"model call failed: {type(e).__name__}") from None
        text = "".join(block.text for block in response.content if block.type == "text")
        return LLMResponse(text, response.usage.input_tokens, response.usage.output_tokens,
                           response.stop_reason or "")


@dataclass
class FakeLLM:
    """Returns scripted answers in order and records every prompt."""
    answers: list
    model: str = config.CLAUDE_MODEL
    input_tokens: int = 1500
    output_tokens: int = 300
    calls: list = field(default_factory=list)

    def complete(self, system: str, user: str, schema: dict) -> LLMResponse:
        self.calls.append({"system": system, "user": user, "schema": schema})
        if len(self.calls) > len(self.answers):
            raise AssertionError(f"FakeLLM called {len(self.calls)} times but scripted {len(self.answers)} answers")
        answer = self.answers[len(self.calls) - 1]
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, LLMResponse):
            return answer
        text = answer if isinstance(answer, str) else json.dumps(answer)
        return LLMResponse(text, self.input_tokens, self.output_tokens, "end_turn")


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    if model not in config.MODEL_PRICES_PER_MTOK:
        raise KeyError(f"no price for model {model!r} in config.MODEL_PRICES_PER_MTOK")
    i, o = config.MODEL_PRICES_PER_MTOK[model]
    return input_tokens * i / 1e6 + output_tokens * o / 1e6
