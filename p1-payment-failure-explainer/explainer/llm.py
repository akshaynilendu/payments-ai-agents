"""Model clients: an interface, the real Anthropic client, and a scripted fake for tests ($0, no network)."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from explainer import config


@dataclass(frozen=True)
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    # "end_turn" is a normal finish; "max_tokens" or "refusal" mean the text can't be trusted.
    stop_reason: str


class LLMError(Exception):
    """The call itself failed (timeout, network, API error). Messages never contain the key or the prompt."""


class LLMClient(Protocol):
    model: str

    def complete(self, system: str, user: str, schema: dict) -> LLMResponse: ...


class AnthropicClient:
    """Calls Claude with structured output. The key is read from the environment, loaded from .env.server."""

    def __init__(self, model: str = config.CLAUDE_MODEL, env_file: Path = config.ENV_FILE):
        # Imported here so tests, which use FakeLLM, never need the SDK or a key.
        import anthropic
        from dotenv import load_dotenv

        # override=False: a key already exported in the shell wins over the file.
        load_dotenv(env_file, override=False)
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise LLMError(f"ANTHROPIC_API_KEY is not set; add it to {env_file.name} (gitignored)")
        if model not in config.MODEL_SETTINGS:
            # Each model needs its own settings (e.g. Haiku 5.5 rejects temperature 0), so never guess them.
            raise LLMError(f"no settings for model {model!r} in config.MODEL_SETTINGS")
        self.model = model
        self._settings = config.MODEL_SETTINGS[model]
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(timeout=self._settings.get("timeout_s", config.LLM_TIMEOUT_SECONDS),
                                           max_retries=config.LLM_SDK_RETRIES)

    def _request(self, system: str, user: str, schema: dict) -> dict:
        settings = self._settings
        output_config = {"format": {"type": "json_schema", "schema": schema}}
        if "effort" in settings:
            output_config["effort"] = settings["effort"]
        request = dict(model=self.model, max_tokens=settings["max_tokens"], system=system,
                       messages=[{"role": "user", "content": user}], output_config=output_config)
        if "temperature" in settings:
            # SDK 1.x dropped sampling arguments; Haiku 4.5 still honours temperature, so it goes in the body (D5).
            request["extra_body"] = {"temperature": settings["temperature"]}
        return request

    def complete(self, system: str, user: str, schema: dict) -> LLMResponse:
        try:
            response = self._client.messages.create(**self._request(system, user, schema))
        except self._anthropic.APIError as e:
            # Only the error type: the exception text could echo request details.
            raise LLMError(f"model call failed: {type(e).__name__}") from None
        # Read by type: Haiku 5.5 and Sonnet 5.5 may return thinking blocks before the text.
        text = "".join(block.text for block in response.content if block.type == "text")
        return LLMResponse(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=response.stop_reason or "",
        )


@dataclass
class FakeLLM:
    """Returns scripted answers in order and records every prompt, so tests can see exactly what was sent."""

    answers: list
    # The real model name, so cost tests use real prices.
    model: str = config.CLAUDE_MODEL
    input_tokens: int = 1000
    output_tokens: int = 200
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
    """Tokens x price / 1e6. An unpriced model is an error, so cost is never silently reported as $0."""
    if model not in config.MODEL_PRICES_PER_MTOK:
        raise KeyError(f"no price for model {model!r} in config.MODEL_PRICES_PER_MTOK")
    input_price, output_price = config.MODEL_PRICES_PER_MTOK[model]
    return input_tokens * input_price / 1e6 + output_tokens * output_price / 1e6
