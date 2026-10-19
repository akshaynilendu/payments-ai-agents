"""Retrieval tests with fake embedders: deterministic, offline, no model download."""

import dataclasses
import json
import shutil

import numpy as np
import pytest

from explainer import knowledge
from explainer.codes import FAILURE_STAGES, Rail, Stage, all_codes
from explainer.embed import FakeEmbedder
from explainer.knowledge import KbRail, Topic, all_passages
from explainer.retrieve import Mode, retrieve

GAP_KEYS = {"timestamp", "code", "rail", "stage", "mode", "threshold", "reason"}
EXPLAINABLE_STAGES = list(FAILURE_STAGES) + [Stage.UNKNOWN]


class CountingFake(FakeEmbedder):
    """Counts passage embeddings separately, to see whether the cache was used."""

    def __init__(self, name="fake-bag-of-words-256"):
        super().__init__(name=name)
        self.passage_calls = 0

    def embed_passages(self, texts):
        self.passage_calls += 1
        return super().embed_passages(texts)


class StubEmbedder:
    """Gives chosen passages a chosen cosine score with every query; others score 0.5."""

    name = "stub"

    def __init__(self, scores_by_id):
        texts = {p.id: p.text for p in all_passages()}
        self.score_by_text = {texts[pid]: s for pid, s in scores_by_id.items()}

    def embed_query(self, text):
        return np.array([1.0, 0.0], dtype=np.float32)

    def embed_passages(self, texts):
        scores = [self.score_by_text.get(t, 0.5) for t in texts]
        # A unit vector at the given cosine to the query vector [1, 0].
        return np.array([[s, np.sqrt(1 - s * s)] for s in scores], dtype=np.float32)


@pytest.fixture
def run(tmp_path):
    """retrieve() with temp cache and gap files, so tests never touch var/. Stage is always explicit."""
    paths = {"cache_path": tmp_path / "embeddings.npz", "gaps_path": tmp_path / "gaps.jsonl"}

    def _run(code, rail, stage, **kwargs):
        kwargs.setdefault("embedder", FakeEmbedder())
        return retrieve(code, rail, stage, **paths, **kwargs)

    _run.gaps = lambda: [json.loads(line) for line in paths["gaps_path"].read_text().splitlines()] \
        if paths["gaps_path"].exists() else []
    _run.paths = paths
    return _run


def _ids(items):
    return [r.passage.id for r in items]


# --- filter -------------------------------------------------------------------

@pytest.mark.parametrize(
    "code, rail, stage, expected_ranked, expected_mandatory",
    [
        # Rejects: only reject advice; the recall passages that used to appear are gone (D10).
        ("AC04", Rail.SEPA_INSTANT, Stage.REJECT, {"KB-SCTI-AC04-01", "KB-SCTI-MS03-01"}, set()),
        ("AC04", Rail.RTP, Stage.REJECT, {"KB-RTP-AC04-01"}, set()),
        ("RR04", Rail.SEPA_DD, Stage.REJECT, {"KB-SDD-RR04-01", "KB-SDD-MS03-01", "KB-ALL-GEN-03"},
         {"KB-ALL-GEN-01"}),
        ("RR04", Rail.UNKNOWN, Stage.REJECT, {"KB-ALL-GEN-03"}, {"KB-ALL-GEN-01"}),
        # Returns and recall stages get their own passages.
        ("AM04", Rail.SEPA_DD, Stage.RETURN, {"KB-SDD-AM04-01", "KB-SDD-MS03-01"}, set()),
        ("MD06", Rail.SEPA_DD, Stage.RETURN, {"KB-SDD-MD06-01", "KB-SDD-GEN-02", "KB-SDD-GEN-03"}, set()),
        ("AC04", Rail.SEPA_INSTANT, Stage.RECALL_ANSWER,
         {"KB-SCTI-AC04-01", "KB-SCTI-GEN-01", "KB-SCTI-GEN-03", "KB-SCTI-GEN-04"}, set()),
        ("AC04", Rail.RTP, Stage.RECALL, {"KB-RTP-GEN-01", "KB-RTP-GEN-02", "KB-RTP-GEN-03"}, set()),
        # Unknown stage: only advice true at every stage.
        ("RR04", Rail.SEPA_DD, Stage.UNKNOWN, {"KB-ALL-GEN-03"}, {"KB-ALL-GEN-01"}),
        ("AC04", Rail.SEPA_INSTANT, Stage.UNKNOWN, set(), set()),
    ],
)
def test_filter_returns_exactly_the_matching_passages(run, code, rail, stage, expected_ranked, expected_mandatory):
    result = run(code, rail, stage, mode=Mode.FILTER_ONLY, k=50)
    assert set(_ids(result.ranked)) == expected_ranked
    assert set(_ids(result.mandatory)) == expected_mandatory


@pytest.mark.parametrize("stage", EXPLAINABLE_STAGES)
@pytest.mark.parametrize("rail", list(Rail))
def test_filter_never_leaks_other_rails_codes_or_stages(run, rail, stage):
    for entry in all_codes():
        result = run(entry.code, rail, stage, mode=Mode.FILTER_ONLY, k=50)
        for item in result.ranked:
            p = item.passage
            assert p.rail is KbRail.ALL or p.rail.value == rail.value, (entry.code, rail, p.id)
            assert entry.code in p.codes or not p.codes, (entry.code, rail, p.id)
            if stage is Stage.UNKNOWN:
                assert set(p.stages) == set(FAILURE_STAGES), (entry.code, rail, p.id)
            else:
                assert stage in p.stages, (entry.code, rail, stage, p.id)


# --- D10: rejects never get recall or return advice ------------------------------

@pytest.mark.parametrize("mode", list(Mode))
@pytest.mark.parametrize("rail", list(Rail))
def test_a_reject_never_receives_a_recall_or_return_passage(run, rail, mode):
    for entry in all_codes():
        for item in run(entry.code, rail, Stage.REJECT, mode=mode, k=50).ranked:
            assert Stage.REJECT in item.passage.stages, (entry.code, rail, item.passage.id)
            assert item.passage.topic is not Topic.RECALL_RETURN, (entry.code, rail, item.passage.id)


def test_frad_at_the_reject_stage_returns_nothing_and_logs_a_gap(run):
    result = run("FRAD", Rail.SEPA_INSTANT, Stage.REJECT)
    assert result.gap and result.all() == ()
    gap = run.gaps()[-1]
    assert (gap["code"], gap["stage"], gap["reason"]) == ("FRAD", "REJECT", "no_passage_matches_filter")


def test_frad_at_the_recall_stage_gets_its_recall_passages(run):
    result = run("FRAD", Rail.SEPA_INSTANT, Stage.RECALL, mode=Mode.FILTER_ONLY, k=50)
    # Its two FRAD passages plus the general SEPA Instant recall passages.
    assert set(_ids(result.ranked)) == {"KB-SCTI-FRAD-01", "KB-SCTI-GEN-02", "KB-SCTI-GEN-01", "KB-SCTI-GEN-04"}


def test_a_return_still_gets_its_next_step(run):
    result = run("AM04", Rail.SEPA_DD, Stage.RETURN)
    assert "KB-SDD-AM04-01" in _ids(result.ranked)


@pytest.mark.parametrize("stage", [Stage.NOT_A_FAILURE, Stage.PENDING])
def test_retrieval_refuses_stages_with_nothing_to_explain(run, stage):
    with pytest.raises(ValueError, match="stop before retrieval"):
        run("AC04", Rail.SEPA_INSTANT, stage)


# --- ranking ------------------------------------------------------------------

def test_ranked_results_are_in_descending_score_order_and_respect_k(run):
    result = run("RR04", Rail.SEPA_DD, Stage.REJECT, k=3)
    scores = [r.score for r in result.ranked]
    assert len(scores) == 3
    assert scores == sorted(scores, reverse=True)


def test_k_one_returns_the_single_best_passage(run):
    stub = StubEmbedder({"KB-SCTI-GEN-04": 0.95, "KB-SCTI-AC04-01": 0.9})
    result = run("AC04", Rail.SEPA_INSTANT, Stage.RECALL_ANSWER, k=1, embedder=stub)
    assert _ids(result.ranked) == ["KB-SCTI-GEN-04"]


# --- mandatory guardrails -------------------------------------------------------

def test_rr04_always_includes_tipping_off_guardrail_even_when_it_scores_lowest(run):
    stub = StubEmbedder({"KB-ALL-GEN-01": -0.99})
    result = run("RR04", Rail.SEPA_INSTANT, Stage.REJECT, k=1, embedder=stub)
    assert _ids(result.mandatory) == ["KB-ALL-GEN-01"]
    assert result.mandatory[0].score == pytest.approx(-0.99, abs=1e-4)
    # In addition to the top k, not instead of it.
    assert len(result.ranked) == 1 and "KB-ALL-GEN-01" not in _ids(result.ranked)
    assert _ids(result.all())[0] == "KB-ALL-GEN-01"


@pytest.mark.parametrize("mode", list(Mode))
@pytest.mark.parametrize("stage", EXPLAINABLE_STAGES)
def test_guardrail_survives_every_stage(run, stage, mode):
    assert _ids(run("RR04", Rail.SEPA_DD, stage, mode=mode).mandatory) == ["KB-ALL-GEN-01"]


def test_guardrail_bypasses_the_stage_filter_in_code_not_just_in_data(run):
    # Even a guardrail mis-tagged with one stage must still be returned at another (D8).
    mistagged = [dataclasses.replace(p, stages=(Stage.REJECT,)) if p.mandatory else p for p in all_passages()]
    result = run("RR04", Rail.SEPA_DD, Stage.RETURN, mode=Mode.FILTER_ONLY, passages=mistagged)
    assert _ids(result.mandatory) == ["KB-ALL-GEN-01"]


def test_guardrail_survives_a_threshold_that_drops_everything_else(run):
    result = run("RR04", Rail.SEPA_DD, Stage.REJECT, threshold=1.01)
    assert result.gap and result.ranked == ()
    assert _ids(result.mandatory) == ["KB-ALL-GEN-01"]


def test_guardrail_is_not_returned_for_other_codes(run):
    assert run("AC04", Rail.SEPA_INSTANT, Stage.REJECT).mandatory == ()


# --- filter_only mode -----------------------------------------------------------

def test_filter_only_never_embeds_and_orders_code_specific_next_steps_first(run):
    fake = FakeEmbedder()
    result = run("AC04", Rail.SEPA_INSTANT, Stage.RECALL_ANSWER, mode=Mode.FILTER_ONLY, k=3, embedder=fake)
    assert fake.calls == 0
    # Code-specific first (next_step before time_limit), then general passages by topic.
    assert _ids(result.ranked) == ["KB-SCTI-AC04-01", "KB-SCTI-GEN-03", "KB-SCTI-GEN-04"]
    assert all(r.score is None for r in result.ranked)


# --- gaps ---------------------------------------------------------------------------

def test_nothing_above_threshold_returns_empty_and_records_one_gap(run):
    result = run("AC04", Rail.SEPA_INSTANT, Stage.REJECT, threshold=1.01)
    assert result.ranked == () and result.gap
    [gap] = run.gaps()
    assert set(gap) == GAP_KEYS
    assert (gap["code"], gap["rail"], gap["stage"], gap["mode"], gap["reason"]) == \
        ("AC04", "SEPA_INSTANT", "REJECT", "filter_rank", "none_above_threshold")


def test_no_matching_passage_records_a_filter_gap(run):
    result = run("AC04", Rail.UNKNOWN, Stage.REJECT)
    assert result.gap
    assert run.gaps()[-1]["reason"] == "no_passage_matches_filter"


def test_unknown_code_records_a_gap_without_embedding(run):
    fake = FakeEmbedder()
    result = run("CNOR", Rail.SEPA_INSTANT, Stage.REJECT, embedder=fake)
    assert result.gap and result.all() == ()
    assert fake.calls == 0
    assert run.gaps()[-1]["reason"] == "unknown_code"


def test_gap_record_never_logs_free_text_as_a_code(run):
    run("Erika Mustermann DE89370400440532013000", Rail.SEPA_INSTANT, Stage.REJECT)
    gap = run.gaps()[-1]
    assert gap["code"] == "INVALID"
    assert "Mustermann" not in json.dumps(gap)


def test_successful_retrieval_records_no_gap(run):
    assert not run("AC04", Rail.SEPA_INSTANT, Stage.REJECT).gap
    assert run.gaps() == []


# --- embedding cache ------------------------------------------------------------

def test_cache_is_reused_when_nothing_changed(run):
    fake = CountingFake()
    run("AC04", Rail.SEPA_INSTANT, Stage.REJECT, embedder=fake)
    run("AM04", Rail.SEPA_DD, Stage.RETURN, embedder=fake)
    assert fake.passage_calls == 1
    assert run.paths["cache_path"].exists()


def test_cache_rebuilds_when_passages_file_changes(run, tmp_path):
    passages_copy = tmp_path / "passages.json"
    shutil.copy(knowledge.DEFAULT_PATH, passages_copy)
    fake = CountingFake()
    run("AC04", Rail.SEPA_INSTANT, Stage.REJECT, embedder=fake, passages_path=passages_copy)
    passages_copy.write_text(passages_copy.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    run("AC04", Rail.SEPA_INSTANT, Stage.REJECT, embedder=fake, passages_path=passages_copy)
    assert fake.passage_calls == 2


def test_cache_rebuilds_when_model_changes(run):
    first, second = CountingFake(name="model-a"), CountingFake(name="model-b")
    run("AC04", Rail.SEPA_INSTANT, Stage.REJECT, embedder=first)
    run("AC04", Rail.SEPA_INSTANT, Stage.REJECT, embedder=second)
    assert (first.passage_calls, second.passage_calls) == (1, 1)


def test_cache_rebuilds_when_passage_set_differs(run):
    fake = CountingFake()
    run("AC04", Rail.SEPA_INSTANT, Stage.REJECT, embedder=fake)
    subset = [p for p in all_passages() if p.rail is KbRail.SEPA_INSTANT]
    run("AC04", Rail.SEPA_INSTANT, Stage.REJECT, embedder=fake, passages=subset)
    assert fake.passage_calls == 2


# --- D18 -------------------------------------------------------------------------------

@pytest.mark.parametrize("rail", list(Rail))
def test_family_passages_never_appear_in_normal_retrieval(run, rail):
    for entry in all_codes():
        for item in run(entry.code, rail, Stage.REJECT, mode=Mode.FILTER_ONLY, k=50).all():
            assert not item.passage.families, (entry.code, rail, item.passage.id)


def test_family_passages_for_codes_outside_the_table():
    from explainer.retrieve import family_passages
    assert [r.passage.id for r in family_passages("CNOR", Stage.REJECT)] == ["KB-ALL-FAM-RT-01"]
    assert [r.passage.id for r in family_passages("SL01", Stage.RETURN)] == ["KB-ALL-FAM-MS-01"]
    assert family_passages("FF01", Stage.REJECT) == []
