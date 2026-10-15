"""Integration test with the real local embedding model. Skipped by default; run: pytest -m integration"""

import pytest

from explainer.codes import Rail, Stage
from explainer.retrieve import retrieve

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "code, rail, stage, expected_top",
    [
        ("AM04", Rail.SEPA_DD, Stage.RETURN, "KB-SDD-AM04-01"),
        ("AC04", Rail.RTP, Stage.REJECT, "KB-RTP-AC04-01"),
    ],
)
def test_real_model_ranks_the_code_specific_next_step_first(tmp_path, code, rail, stage, expected_top):
    result = retrieve(code, rail, stage, cache_path=tmp_path / "embeddings.npz", gaps_path=tmp_path / "gaps.jsonl")
    assert result.ranked[0].passage.id == expected_top
    assert all(-1.0 <= r.score <= 1.0 for r in result.ranked)


def test_real_model_keeps_the_rr04_guardrail(tmp_path):
    result = retrieve("RR04", Rail.SEPA_INSTANT, Stage.REJECT, cache_path=tmp_path / "embeddings.npz",
                      gaps_path=tmp_path / "gaps.jsonl")
    assert [r.passage.id for r in result.mandatory] == ["KB-ALL-GEN-01"]
