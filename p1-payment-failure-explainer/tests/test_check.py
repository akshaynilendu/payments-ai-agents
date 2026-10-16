import json

import pytest

from explainer.check import LENGTH_LIMITS, MAX_CITATIONS, check
from explainer.codes import Route

ALLOWED = {"KB-SCTI-AC04-01", "KB-SCTI-MS03-01"}


def answer(**overrides):
    base = {
        "what_happened": "The beneficiary's account is closed, so the payment was rejected.",
        "next_step": "Ask the customer to get the beneficiary's new account details.",
        "customer_message": "Your payment could not be completed because the recipient's account is closed.",
        "citations": ["KB-SCTI-AC04-01"],
    }
    return json.dumps(base | overrides)


def names(result):
    return [f.name for f in result.failures]


def test_valid_answer_passes():
    result = check(answer(), allowed_citations=ALLOWED, route=Route.FIRST_LINE)
    assert result.ok and result.answer["citations"] == ["KB-SCTI-AC04-01"]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("not json", "invalid_json"),
        ("[1, 2]", "schema_invalid"),
        (json.dumps({"what_happened": "x"}), "schema_invalid"),
        (answer(route="FIRST_LINE"), "schema_invalid"),
        (answer(confidence=0.9), "schema_invalid"),
        (answer(what_happened=42), "schema_invalid"),
        (answer(citations="KB-SCTI-AC04-01"), "schema_invalid"),
        (answer(customer_message=["x"]), "schema_invalid"),
    ],
)
def test_malformed_answers_are_named(text, expected):
    assert expected in names(check(text, allowed_citations=ALLOWED, route=Route.FIRST_LINE))


def test_extra_route_field_is_reported_as_unexpected():
    result = check(answer(route="FIRST_LINE"), allowed_citations=ALLOWED, route=Route.COMPLIANCE)
    assert "unexpected route" in str(result.failures[0])


@pytest.mark.parametrize(
    "overrides, expected",
    [
        ({"what_happened": "  "}, "empty_field"),
        ({"next_step": ""}, "empty_field"),
        ({"customer_message": ""}, "empty_field"),
        ({"citations": []}, "no_citation"),
        ({"citations": ["KB-INVENTED-01"]}, "unknown_citation"),
        ({"citations": ["KB-SCTI-AC04-01"] * (MAX_CITATIONS + 1)}, "too_long"),
        ({"what_happened": "x" * (LENGTH_LIMITS["what_happened"] + 1)}, "too_long"),
        ({"customer_message": "x" * (LENGTH_LIMITS["customer_message"] + 1)}, "too_long"),
    ],
)
def test_field_failures_are_named(overrides, expected):
    assert expected in names(check(answer(**overrides), allowed_citations=ALLOWED, route=Route.FIRST_LINE))


def test_unknown_citation_names_the_invented_id():
    result = check(answer(citations=["KB-SCTI-AC04-01", "KB-INVENTED-01"]), allowed_citations=ALLOWED,
                   route=Route.FIRST_LINE)
    assert [str(f) for f in result.failures] == ["unknown_citation (KB-INVENTED-01)"]


def test_compliance_blocks_any_customer_message():
    assert "compliance_customer_message" in names(
        check(answer(), allowed_citations=ALLOWED, route=Route.COMPLIANCE))
    assert check(answer(customer_message=None), allowed_citations=ALLOWED, route=Route.COMPLIANCE).ok


@pytest.mark.parametrize(
    "message",
    [
        "Your money will be refunded.",
        "The funds will be returned to you.",
        "This will be resolved within 2 days.",
        "Please allow 3 business days.",
        "We guarantee the payment goes through next time.",
        "You will receive the funds by tomorrow.",
        "We will contact you shortly.",
        "We will fix this as soon as possible.",
    ],
)
def test_promise_phrases_in_customer_message_are_blocked(message):
    result = check(answer(customer_message=message), allowed_citations=ALLOWED, route=Route.FIRST_LINE)
    assert "promise_phrase" in names(result)


def test_rule_deadlines_are_allowed_in_ops_text():
    # Ops may quote scheme deadlines from a passage; only the customer text is promise-checked (D2c).
    text = answer(next_step="The beneficiary bank must answer within 15 banking business days.")
    assert check(text, allowed_citations=ALLOWED, route=Route.FIRST_LINE).ok


def test_neutral_customer_message_passes():
    message = "Your payment was declined by the other party. Please contact them to agree how to complete it."
    assert check(answer(customer_message=message), allowed_citations=ALLOWED, route=Route.FIRST_LINE).ok


@pytest.mark.parametrize("stop_reason", ["max_tokens", "refusal"])
def test_truncated_or_refused_answer_fails_even_if_json_parses(stop_reason):
    result = check(answer(), allowed_citations=ALLOWED, route=Route.FIRST_LINE, stop_reason=stop_reason)
    assert names(result) == ["truncated_or_refused"]


# --- D12: no customer-contact instruction on COMPLIANCE --------------------------------------------

@pytest.mark.parametrize(
    "next_step",
    [
        "Advise the customer to discuss the regulatory concern with the beneficiary.",
        "Inform the originator that the payment was stopped for regulatory reasons.",
        "Discuss the regulatory concern with the customer.",
        "Contact the client and explain the rejection.",
        "Let the customer know about the regulatory stop.",
        "The customer should be told why the payment was stopped.",
    ],
)
def test_compliance_blocks_customer_contact_instructions(next_step):
    result = check(answer(next_step=next_step, customer_message=None), allowed_citations=ALLOWED,
                   route=Route.COMPLIANCE)
    assert "compliance_customer_contact" in names(result)


def test_compliance_checks_what_happened_too():
    text = answer(what_happened="Regulatory stop; please inform the customer.", customer_message=None)
    assert "compliance_customer_contact" in names(check(text, allowed_citations=ALLOWED, route=Route.COMPLIANCE))


@pytest.mark.parametrize("next_step", ["", "Do not contact the customer about the reason.",
                                       "Never tell the customer why; hand the case to Compliance."])
def test_compliance_allows_empty_or_negated_next_step(next_step):
    result = check(answer(next_step=next_step, customer_message=None), allowed_citations=ALLOWED,
                   route=Route.COMPLIANCE)
    assert result.ok, names(result)


def test_customer_contact_is_normal_advice_outside_compliance():
    assert check(answer(next_step="Advise the customer to check the IBAN with the recipient."),
                 allowed_citations=ALLOWED, route=Route.FIRST_LINE).ok
