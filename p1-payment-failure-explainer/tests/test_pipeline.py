import pytest

from explainer import pipeline
from explainer.codes import Stage
from explainer.embed import FakeEmbedder
from explainer.parse import parse_file, parse_xml
from explainer.pipeline import NO_FAILURE_MESSAGE, PENDING_MESSAGE, Outcome, prepare
from tests.test_parse import SAMPLES_DIR, _with_status


@pytest.fixture
def no_lookup_or_retrieval(monkeypatch):
    """Fails the test if the explainer looks anything up: proof it stopped early."""
    def boom(*args, **kwargs):
        raise AssertionError("lookup or retrieval was called")
    monkeypatch.setattr(pipeline, "lookup", boom)
    monkeypatch.setattr(pipeline, "retrieve", boom)


@pytest.fixture
def offline(tmp_path):
    return {"embedder": FakeEmbedder(), "cache_path": tmp_path / "e.npz", "gaps_path": tmp_path / "g.jsonl"}


@pytest.mark.parametrize("status", ["ACSC", "ACCC", "ACSP", "ACTC"])
def test_success_stops_with_no_failure_before_lookup_or_retrieval(no_lookup_or_retrieval, status):
    prepared = prepare(parse_xml(_with_status(status, keep_reason=False)))
    assert prepared.outcome is Outcome.NOT_A_FAILURE
    assert prepared.message == NO_FAILURE_MESSAGE
    assert prepared.code is None and prepared.retrieval is None


def test_pending_stops_before_lookup_or_retrieval(no_lookup_or_retrieval):
    prepared = prepare(parse_xml(_with_status("PDNG", keep_reason=False)))
    assert prepared.outcome is Outcome.PENDING
    assert prepared.message == PENDING_MESSAGE
    assert "Do not resend" in prepared.message


def test_reject_proceeds_with_code_and_reject_only_passages(offline):
    prepared = prepare(parse_file(SAMPLES_DIR / "rtp_ac06_blocked.xml"), **offline)
    assert prepared.outcome is Outcome.PROCEED
    assert prepared.code.code == "AC06"
    assert all(Stage.REJECT in r.passage.stages for r in prepared.retrieval.ranked)


def test_unknown_code_proceeds_with_no_code_and_a_gap(offline):
    prepared = prepare(parse_file(SAMPLES_DIR / "sct_inst_cnor_unknown.xml"), **offline)
    assert prepared.outcome is Outcome.PROCEED
    assert prepared.code is None and prepared.retrieval.gap
