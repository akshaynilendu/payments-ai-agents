import json

import pytest
from pydantic import ValidationError

from investigator.schema import CASE_SUMMARY, Assessment, SepaCaseSummary, UkCaseSummary


def test_every_summary_round_trips_through_the_schema(summaries):
    for s in summaries.values():
        again = CASE_SUMMARY.validate_json(s.model_dump_json())
        assert again == s and type(again) is type(s)


def test_every_evidence_item_cites_a_check_result(summaries):
    for s in summaries.values():
        assert set(s.cited_ids()) <= set(s.check_result_ids)
        assert all(i.source_id for i in s.assessment.evidence_for + s.assessment.evidence_against)


def test_an_invented_citation_is_rejected(summaries):
    data = json.loads(next(iter(summaries.values())).model_dump_json())
    data["evidence"]["payee_risk"][0]["source_id"] = "payee_risk:P9999:made_up"
    with pytest.raises(ValidationError, match="not produced by any check"):
        CASE_SUMMARY.validate_python(data)


def test_there_is_no_score_field():
    assert not {"score", "risk_score", "confidence", "probability"} & set(Assessment.model_fields)


def test_unknown_fields_are_rejected(summaries):
    data = json.loads(next(iter(summaries.values())).model_dump_json())
    data["assessment"]["score"] = 0.9
    with pytest.raises(ValidationError):
        CASE_SUMMARY.validate_python(data)


def test_decision_is_left_empty_for_the_human(summaries):
    for s in summaries.values():
        assert s.decision.model_dump() == {"outcome": None, "contacted": None, "final_label": None}


def test_payee_risk_is_always_present(summaries):
    for s in summaries.values():
        assert any(i.source_id.endswith(":name_check") for i in s.evidence.payee_risk)


def test_every_next_step_has_a_reason_and_sources(summaries):
    for s in summaries.values():
        assert s.next_steps and all(n.reason and n.source_ids for n in s.next_steps)
