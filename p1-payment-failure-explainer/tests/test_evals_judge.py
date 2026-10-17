import json

import pytest

from evals.judge import JUDGE_SCHEMA, build_judge_prompt, judge_case, parse_judge
from explainer.llm import FakeLLM, LLMError, LLMResponse

GOOD = {c: {"pass": True, "reason": "Fine."} for c in ("accurate", "actionable", "safe")}
FACTS = ["Reason code: AC04 (Closed Account Number)", "Rail: SEPA Instant", "Stage: REJECT",
         "Route (fixed by the routing table): FIRST_LINE: Platform support resolves it with the customer."]
REFERENCE = [{"id": "KB-SCTI-AC04-01", "label": "Scheme rule", "text": "The account is closed."}]
ANSWER = {"what_happened": "Closed.", "next_step": "Ask for a new account.", "customer_message": None}


def test_parse_accepts_a_complete_grade():
    assert parse_judge(json.dumps(GOOD)) == GOOD


@pytest.mark.parametrize(
    "bad",
    [
        {"accurate": GOOD["accurate"], "actionable": GOOD["actionable"]},
        GOOD | {"clear": GOOD["safe"]},
        GOOD | {"safe": {"pass": "yes", "reason": "Fine."}},
        GOOD | {"safe": {"pass": True, "reason": " "}},
        GOOD | {"safe": "pass"},
    ],
)
def test_parse_rejects_incomplete_or_wrongly_typed_grades(bad):
    with pytest.raises(ValueError):
        parse_judge(json.dumps(bad))


def test_unusable_output_is_an_error_never_a_pass():
    result = judge_case(FakeLLM(["not json"], model="claude-sonnet-5-5"), FACTS, REFERENCE, ANSWER)
    assert result.grades is None and "unusable" in result.error
    assert result.cost_usd > 0  # a failed grade still costs money and is counted


def test_truncated_output_is_an_error():
    truncated = LLMResponse(json.dumps(GOOD), 100, 3000, "max_tokens")
    result = judge_case(FakeLLM([truncated], model="claude-sonnet-5-5"), FACTS, REFERENCE, ANSWER)
    assert result.grades is None and "max_tokens" in result.error


def test_call_failure_is_an_error():
    result = judge_case(FakeLLM([LLMError("timeout")], model="claude-sonnet-5-5"), FACTS, REFERENCE, ANSWER)
    assert result.grades is None and "failed" in result.error


def test_judge_gets_facts_reference_and_answer_with_the_schema():
    llm = FakeLLM([GOOD], model="claude-sonnet-5-5")
    result = judge_case(llm, FACTS, REFERENCE, ANSWER)
    assert result.grades == GOOD
    sent = llm.calls[0]
    assert sent["schema"] == JUDGE_SCHEMA
    for text in ("AC04 (Closed Account Number)", "[KB-SCTI-AC04-01]", "The account is closed.",
                 "Ask for a new account.", "customer_message: (none)"):
        assert text in sent["user"]


def test_prompt_never_names_a_system():
    prompt = build_judge_prompt(FACTS, REFERENCE, ANSWER)
    assert "baseline" not in prompt.lower() and "haiku" not in prompt.lower()
