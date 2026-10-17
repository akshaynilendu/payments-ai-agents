import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from explainer import config
from explainer.explain import OUTPUT_SCHEMA
from explainer.llm import AnthropicClient, FakeLLM, LLMError, cost_usd

FAKE_KEY = "sk-ant-test-not-a-real-key"


def test_cost_is_tokens_times_price():
    assert cost_usd("claude-haiku-4-5-20251001", 2_000, 300) == pytest.approx(0.002 + 0.0015)


def test_unpriced_model_is_an_error_not_zero():
    with pytest.raises(KeyError, match="no price"):
        cost_usd("some-other-model", 100, 100)


def test_fake_llm_refuses_unscripted_calls():
    llm = FakeLLM(["{}"])
    llm.complete("s", "u", {})
    with pytest.raises(AssertionError, match="scripted 1"):
        llm.complete("s", "u", {})


def test_env_server_is_ignored_by_git():
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    path = config.ENV_FILE
    result = subprocess.run(["git", "check-ignore", "-q", str(path)], cwd=path.parent, capture_output=True)
    assert result.returncode == 0, f"{path.name} is NOT gitignored"


@pytest.fixture
def no_key(monkeypatch):
    """Start without a key and restore the environment afterwards, even if load_dotenv sets one."""
    # setenv first so monkeypatch records the variable and removes it again at teardown.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "placeholder")
    monkeypatch.delenv("ANTHROPIC_API_KEY")


def test_missing_key_gives_a_clear_error(no_key, tmp_path):
    with pytest.raises(LLMError, match="ANTHROPIC_API_KEY is not set; add it to .env.server"):
        AnthropicClient(env_file=tmp_path / ".env.server")


def test_key_is_loaded_from_the_env_file(no_key, tmp_path):
    env_file = tmp_path / ".env.server"
    env_file.write_text(f"ANTHROPIC_API_KEY={FAKE_KEY}\n")
    client = AnthropicClient(env_file=env_file)
    assert client.model == config.CLAUDE_MODEL
    assert FAKE_KEY not in repr(client.__dict__)


def test_fake_key_does_not_leak_into_later_tests():
    assert os.environ.get("ANTHROPIC_API_KEY") != FAKE_KEY


@pytest.fixture
def stubbed_client(monkeypatch):
    """A real AnthropicClient whose network call is replaced, to inspect exactly what would be sent."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    client = AnthropicClient(env_file=Path("/nonexistent/.env.server"))
    sent = {}

    def create(**kwargs):
        sent.update(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text='{"ok": 1}')],
                               usage=SimpleNamespace(input_tokens=11, output_tokens=7), stop_reason="end_turn")

    monkeypatch.setattr(client._client, "messages", SimpleNamespace(create=create))
    return client, sent


def test_request_uses_config_and_structured_output(stubbed_client):
    client, sent = stubbed_client
    response = client.complete("SYSTEM", "USER", OUTPUT_SCHEMA)
    assert sent["model"] == "claude-haiku-4-5-20251001"
    assert sent["max_tokens"] == config.LLM_MAX_OUTPUT_TOKENS
    assert sent["extra_body"] == {"temperature": 0}
    assert sent["system"] == "SYSTEM"
    assert sent["messages"] == [{"role": "user", "content": "USER"}]
    assert sent["output_config"] == {"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}}
    assert (response.text, response.input_tokens, response.output_tokens) == ('{"ok": 1}', 11, 7)


def test_client_timeout_and_retries_come_from_config(stubbed_client):
    client, _ = stubbed_client
    assert client._client.timeout == config.LLM_TIMEOUT_SECONDS
    assert client._client.max_retries == config.LLM_SDK_RETRIES


def test_api_errors_become_llm_errors_without_details(stubbed_client, monkeypatch):
    import anthropic
    import httpx2

    client, _ = stubbed_client

    def fail(**kwargs):
        raise anthropic.APIConnectionError(message=f"boom {FAKE_KEY}", request=httpx2.Request("POST", "https://x"))

    monkeypatch.setattr(client._client, "messages", SimpleNamespace(create=fail))
    with pytest.raises(LLMError) as exc_info:
        client.complete("s", "u", OUTPUT_SCHEMA)
    assert str(exc_info.value) == "model call failed: APIConnectionError"
    assert exc_info.value.__cause__ is None  # not chained, so a traceback can't print the original text


# --- per-model settings (piece 4) -----------------------------------------------------

@pytest.fixture
def client_for(monkeypatch):
    def make(model):
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
        client = AnthropicClient(model=model, env_file=Path("/nonexistent/.env.server"))
        sent = {}

        def create(**kwargs):
            sent.update(kwargs)
            # Thinking blocks come first on Haiku 5.5 / Sonnet 5.5; only text blocks are the answer.
            return SimpleNamespace(content=[SimpleNamespace(type="thinking", thinking=""),
                                            SimpleNamespace(type="text", text='{"ok": 1}')],
                                   usage=SimpleNamespace(input_tokens=11, output_tokens=7), stop_reason="end_turn")

        monkeypatch.setattr(client._client, "messages", SimpleNamespace(create=create))
        return client, sent
    return make


def test_haiku55_request_omits_temperature_and_sets_low_effort(client_for):
    client, sent = client_for("claude-haiku-5-5")
    response = client.complete("S", "U", OUTPUT_SCHEMA)
    assert "extra_body" not in sent  # any temperature but 1 is rejected
    assert sent["output_config"] == {"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}, "effort": "low"}
    assert sent["max_tokens"] == 4096  # room for thinking, which counts toward max_tokens
    assert response.text == '{"ok": 1}'


def test_judge_model_settings(client_for):
    client, sent = client_for("claude-sonnet-5-5")
    client.complete("S", "U", OUTPUT_SCHEMA)
    assert "extra_body" not in sent and sent["output_config"]["effort"] == "medium"
    assert client._client.timeout == config.MODEL_SETTINGS["claude-sonnet-5-5"]["timeout_s"]


def test_unknown_model_is_refused(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    with pytest.raises(LLMError, match="no settings"):
        AnthropicClient(model="claude-made-up", env_file=Path("/nonexistent/.env.server"))
