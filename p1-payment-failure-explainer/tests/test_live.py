"""Live test against the real Claude API. Skipped by default; run: pytest -m live (costs about $0.004)."""

import os

import pytest

from explainer import config
from explainer.codes import Route
from explainer.llm import AnthropicClient
from explainer.parse import parse_file
from explainer.pipeline import CaseOutcome, explain_case
from tests.test_parse import SAMPLES_DIR

pytestmark = pytest.mark.live


def test_live_sample_explains_within_the_d4_bar(tmp_path):
    if not (os.environ.get("ANTHROPIC_API_KEY") or config.ENV_FILE.exists()):
        pytest.skip("no API key: add ANTHROPIC_API_KEY to .env.server")
    status = parse_file(SAMPLES_DIR / "sct_inst_ac04_closed.xml")
    result = explain_case(status, AnthropicClient(), log_path=tmp_path / "explain.jsonl",
                          cache_path=tmp_path / "e.npz", gaps_path=tmp_path / "g.jsonl")
    assert result.outcome in (CaseOutcome.AI_OK, CaseOutcome.AI_RETRY_OK), result.failures
    assert result.route is Route.FIRST_LINE
    assert result.citations
    assert result.cost_usd < 0.10  # D4 bar; target is well under $0.01
