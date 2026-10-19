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


# --- D16: customer message vs next_step, and withheld reasons ---------------------------

RESEND_FORBIDDEN_STEP = ("Check the logs. Before anyone resends, confirm the original payment's final status "
                         "(pacs.028 status request) to avoid a duplicate payment.")


@pytest.mark.parametrize("customer", [
    "Your payment timed out. Please try again later.",
    "Please resend the payment.",
    "You can send it again in a moment.",
])
def test_customer_retry_contradicting_next_step_is_blocked(customer):
    result = check(answer(next_step=RESEND_FORBIDDEN_STEP, customer_message=customer),
                   allowed_citations=ALLOWED, route=Route.DEVELOPER)
    assert "customer_contradicts_next_step" in names(result)


@pytest.mark.parametrize("customer", [
    "Your payment did not complete. Please don't send it again until we've confirmed its status.",
    "Your payment did not complete. We are checking its status.",
])
def test_negated_or_neutral_customer_message_is_fine(customer):
    result = check(answer(next_step=RESEND_FORBIDDEN_STEP, customer_message=customer),
                   allowed_citations=ALLOWED, route=Route.DEVELOPER)
    assert "customer_contradicts_next_step" not in names(result)


def test_retry_advice_is_fine_when_next_step_does_not_forbid_it():
    result = check(answer(customer_message="Please try again later or use a standard transfer."),
                   allowed_citations=ALLOWED, route=Route.FIRST_LINE)
    assert result.ok


@pytest.mark.parametrize("customer", [
    "Your payment was returned without a reason. This may be due to their account status or a regulatory restriction.",
    "No reason was given; possible causes include insufficient funds.",
    "The other bank declined it, likely because the account is closed.",
])
@pytest.mark.parametrize("code", ["MS02", "MS03"])
def test_speculating_about_a_withheld_reason_is_blocked(code, customer):
    result = check(answer(customer_message=customer), allowed_citations=ALLOWED, route=Route.FIRST_LINE, code=code)
    assert "speculative_reason" in names(result)


def test_saying_no_reason_was_given_is_fine_for_withheld_codes():
    customer = "Your payment was returned and no reason was given. Please contact the other party to arrange payment."
    assert check(answer(customer_message=customer), allowed_citations=ALLOWED, route=Route.FIRST_LINE, code="MS03").ok


def test_speculation_rule_only_applies_to_withheld_codes():
    customer = "Your payment was declined because the account is closed."
    assert check(answer(customer_message=customer), allowed_citations=ALLOWED, route=Route.FIRST_LINE, code="AC04").ok


def test_policy_owned_customer_message_must_come_back_null():
    result = check(answer(), allowed_citations=ALLOWED, route=Route.DEVELOPER, customer_policy=True)
    assert "policy_customer_message" in names(result)
    assert check(answer(customer_message=None), allowed_citations=ALLOWED, route=Route.DEVELOPER,
                 customer_policy=True).ok


def test_required_citation_must_be_cited():
    result = check(answer(), allowed_citations=ALLOWED | {"ISO-CNOR"}, route=None,
                   required_citations=frozenset({"ISO-CNOR"}))
    assert "missing_required_citation" in names(result)
    cited = check(answer(citations=["ISO-CNOR"]), allowed_citations=ALLOWED | {"ISO-CNOR"}, route=None,
                  required_citations=frozenset({"ISO-CNOR"}))
    assert "missing_required_citation" not in names(cited)


# --- D19: sensitive words beyond the table ------------------------------------------------

SOURCES = {"ISO-CNOR": "Creditor bank is not registered under this BIC in the CSM",
           "KB-ALL-FAM-BE-01": "Do not speculate about fraud or about why the details were rejected."}


@pytest.mark.parametrize("text, stem", [
    ("This may be fraudulent.", "fraud"), ("Check sanctions screening.", "sanction"),
    ("A regulatory stop is likely.", "regulat"), ("The payer may be deceased.", "deceas"),
    ("An investigation is under way.", "investigat"),
])
def test_unsupported_sensitive_word_is_blocked(text, stem):
    result = check(answer(what_happened=text, citations=["ISO-CNOR"]), allowed_citations=set(SOURCES), route=None,
                   sensitive_sources=SOURCES, always_allowed=SOURCES["ISO-CNOR"])
    assert ("unsupported_sensitive_word", stem) in [(f.name, f.detail) for f in result.failures]


def test_sensitive_word_allowed_when_a_cited_passage_uses_it():
    text = answer(next_step="Do not speculate about fraud.", citations=["ISO-CNOR", "KB-ALL-FAM-BE-01"])
    result = check(text, allowed_citations=set(SOURCES), route=None, sensitive_sources=SOURCES,
                   always_allowed=SOURCES["ISO-CNOR"])
    assert "unsupported_sensitive_word" not in names(result)


def test_sensitive_word_not_allowed_by_an_uncited_passage():
    text = answer(next_step="Do not speculate about fraud.", citations=["ISO-CNOR"])
    result = check(text, allowed_citations=set(SOURCES), route=None, sensitive_sources=SOURCES,
                   always_allowed=SOURCES["ISO-CNOR"])
    assert "unsupported_sensitive_word" in names(result)


def test_sensitive_word_allowed_when_the_iso_definition_uses_it():
    result = check(answer(what_happened="The end customer is deceased.", citations=["ISO-MD07"]),
                   allowed_citations={"ISO-MD07"}, route=None, sensitive_sources={"ISO-MD07": "End customer is deceased."},
                   always_allowed="End customer is deceased.")
    assert "unsupported_sensitive_word" not in names(result)


def test_sensitive_word_check_is_off_for_table_codes():
    # Table codes keep their own checks; the word list is for codes beyond the table (D19).
    assert check(answer(what_happened="Possible regulatory reason."), allowed_citations=ALLOWED,
                 route=Route.FIRST_LINE).ok
