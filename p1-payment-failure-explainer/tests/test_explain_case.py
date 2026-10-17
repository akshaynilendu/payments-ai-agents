"""End-to-end explainer tests with FakeLLM: no network, $0."""

import json
from pathlib import Path

import pytest

from explainer.codes import Route, lookup
from explainer.embed import FakeEmbedder
from explainer.explain import OUTPUT_SCHEMA, RULES
from explainer.llm import FakeLLM, LLMError, LLMResponse
from explainer.parse import parse_file, parse_xml
from explainer.pipeline import COMPLIANCE_NEXT_STEP, NO_GUIDANCE_NOTE, CaseOutcome, NextStepSource, explain_case
from tests.test_parse import SAMPLES_DIR, _with_status

EXPECTED = json.loads((SAMPLES_DIR / "expected.json").read_text(encoding="utf-8"))["samples"]


@pytest.fixture
def run(tmp_path):
    """explain_case() offline: fake embedder, temp cache, gap and explain logs."""
    options = {"embedder": FakeEmbedder(), "cache_path": tmp_path / "e.npz", "gaps_path": tmp_path / "g.jsonl"}
    log_path = tmp_path / "explain.jsonl"

    def _run(sample, answers, **extra):
        status = parse_file(SAMPLES_DIR / sample) if isinstance(sample, str) else sample
        llm = FakeLLM(list(answers))
        result = explain_case(status, llm, log_path=log_path, **options | extra)
        return result, llm

    _run.log = lambda: [json.loads(line) for line in log_path.read_text().splitlines()]
    return _run


def ok_answer(citations, customer_message="Your payment could not be completed. Please contact the recipient."):
    return {
        "what_happened": "The payment was rejected because of the reason code shown.",
        "next_step": "Ask the customer to check the details with the other party.",
        "customer_message": customer_message,
        "citations": citations,
    }


# --- happy path and retry ------------------------------------------------------------

def test_happy_path(run):
    result, llm = run("sct_inst_ac04_closed.xml", [ok_answer(["KB-SCTI-AC04-01"])])
    assert result.outcome is CaseOutcome.AI_OK
    assert (result.attempts, len(llm.calls)) == (1, 1)
    assert result.route is Route.FIRST_LINE
    assert [(c.id, c.label) for c in result.citations] == [("KB-SCTI-AC04-01", "Scheme rule")]
    assert (result.input_tokens, result.output_tokens) == (1000, 200)
    # Haiku 4.5 at $1 / $5 per million tokens.
    assert result.cost_usd == pytest.approx(1000 * 1 / 1e6 + 200 * 5 / 1e6)
    assert result.latency_s >= 0


def test_invented_citation_is_retried_with_feedback_and_then_passes(run):
    result, llm = run("sct_inst_ac04_closed.xml",
                      [ok_answer(["KB-INVENTED-01"]), ok_answer(["KB-SCTI-AC04-01"])])
    assert result.outcome is CaseOutcome.AI_RETRY_OK
    assert result.attempts == 2
    assert "unknown_citation (KB-INVENTED-01)" in llm.calls[1]["user"]
    assert "unknown_citation" not in llm.calls[0]["user"]
    assert result.failures == ("attempt 1: unknown_citation (KB-INVENTED-01)",)
    assert result.input_tokens == 2000


def test_two_failures_escalate_with_the_baseline(run):
    result, llm = run("sct_inst_ac04_closed.xml", ["not json", ok_answer([])])
    ac04 = lookup("AC04")
    assert result.outcome is CaseOutcome.ESCALATED
    assert len(llm.calls) == 2
    assert result.what_happened == ac04.baseline_what_happened
    assert result.next_step == ac04.baseline_what_to_do
    assert result.customer_message == ac04.baseline_customer_message
    assert result.citations == ()
    assert [f.split(": ")[1] for f in result.failures] == ["invalid_json", "no_citation"]


def test_truncated_answer_is_retried(run):
    truncated = LLMResponse(json.dumps(ok_answer(["KB-SCTI-AC04-01"])), 1000, 1024, "max_tokens")
    result, _ = run("sct_inst_ac04_closed.xml", [truncated, ok_answer(["KB-SCTI-AC04-01"])])
    assert result.outcome is CaseOutcome.AI_RETRY_OK


def test_model_call_error_escalates_without_a_second_call(run):
    result, llm = run("sct_inst_ac04_closed.xml", [LLMError("model call failed: APITimeoutError")])
    assert result.outcome is CaseOutcome.ESCALATED
    assert len(llm.calls) == 1
    assert "llm_error" in result.failures[0]


# --- safety ----------------------------------------------------------------------------

def test_compliance_customer_message_is_blocked(run):
    # RR04 routes to COMPLIANCE; any customer text risks tipping off (D11).
    rr04 = ["KB-SCTI-RR04-01"]
    result, _ = run("sct_inst_rr04_regulatory.xml", [ok_answer(rr04), ok_answer(rr04)])
    assert result.outcome is CaseOutcome.ESCALATED
    assert result.route is Route.COMPLIANCE
    assert result.customer_message is None  # baseline text too: nothing to the customer
    assert all("compliance_customer_message" in f for f in result.failures)


def test_compliance_retry_with_null_message_passes(run):
    rr04 = ["KB-SCTI-RR04-01"]
    result, _ = run("sct_inst_rr04_regulatory.xml", [ok_answer(rr04), ok_answer(rr04, customer_message=None)])
    assert result.outcome is CaseOutcome.AI_RETRY_OK
    assert result.customer_message is None


def test_promise_phrase_is_blocked(run):
    promise = ok_answer(["KB-SCTI-AC04-01"], customer_message="Your money will be refunded within 2 days.")
    result, _ = run("sct_inst_ac04_closed.xml", [promise, promise])
    assert result.outcome is CaseOutcome.ESCALATED
    assert "Your money will be refunded" not in (result.customer_message or "")
    assert any("promise_phrase" in f for f in result.failures)


def test_the_ai_cannot_change_the_route(run):
    rr04 = ["KB-SCTI-RR04-01"]
    sneaky = ok_answer(rr04, customer_message=None) | {"route": "FIRST_LINE"}
    result, llm = run("sct_inst_rr04_regulatory.xml", [sneaky, ok_answer(rr04, customer_message=None)])
    assert result.outcome is CaseOutcome.AI_RETRY_OK
    assert result.route is Route.COMPLIANCE
    assert "schema_invalid (unexpected route)" in llm.calls[1]["user"]
    # The schema the model is held to has no route field at all.
    assert "route" not in OUTPUT_SCHEMA["properties"]


def test_route_always_matches_the_table_for_every_sample(run):
    for sample in EXPECTED:
        status = parse_file(SAMPLES_DIR / sample["file"])
        entry = lookup(status.reason_code)
        answers = [ok_answer(["KB-ALL-GEN-01"], customer_message=None)] * 2
        result, _ = run(sample["file"], answers)
        assert result.route == (entry.route_for(status.rail) if entry else None), sample["file"]


def test_team_runbook_citation_is_labelled_from_data(run):
    result, _ = run("rtp_ac06_blocked.xml", [ok_answer(["KB-RTP-AC06-01"])])
    [citation] = result.citations
    assert (citation.source_type, citation.label) == ("team_runbook", "Team guidance")


# --- no AI call when there is nothing to explain or no guidance ---------------------------

def test_gap_makes_no_ai_call_and_shows_the_baseline(run):
    result, llm = run("sct_inst_ac04_closed.xml", [], threshold=1.01)
    assert result.outcome is CaseOutcome.NO_GUIDANCE
    assert llm.calls == [] and result.cost_usd == 0
    assert result.note == NO_GUIDANCE_NOTE
    assert result.what_happened == lookup("AC04").baseline_what_happened
    assert result.route is Route.FIRST_LINE


def test_unknown_code_escalates_without_an_ai_call(run):
    result, llm = run("sct_inst_cnor_unknown.xml", [])
    assert result.outcome is CaseOutcome.ESCALATED
    assert llm.calls == [] and result.route is None


@pytest.mark.parametrize("status, outcome", [("ACSC", CaseOutcome.NOT_A_FAILURE), ("PDNG", CaseOutcome.PENDING)])
def test_success_and_pending_make_no_ai_call(run, status, outcome):
    result, llm = run(parse_xml(_with_status(status, keep_reason=False)), [])
    assert result.outcome is outcome and llm.calls == []


# --- prompt -------------------------------------------------------------------------------

def test_rules_open_and_close_the_prompt(run):
    _, llm = run("sct_inst_ac04_closed.xml", [ok_answer(["KB-SCTI-AC04-01"])])
    call = llm.calls[0]
    assert call["system"] == RULES
    assert call["user"].rstrip().endswith(RULES.splitlines()[-1])
    assert call["schema"] is OUTPUT_SCHEMA


def test_prompt_has_case_facts_and_labelled_passages(run):
    _, llm = run("sct_inst_rr04_regulatory.xml", [ok_answer(["KB-SCTI-RR04-01"], customer_message=None)])
    user = llm.calls[0]["user"]
    assert "Reason code: RR04 (Regulatory Reason)" in user
    assert "Stage: REJECT (rejected before settlement: no money moved)" in user
    assert "Route (fixed by the routing table): COMPLIANCE" in user
    assert "[KB-ALL-GEN-01] (Regulation, MANDATORY)" in user
    assert "[KB-SCTI-RR04-01] (Scheme rule)" in user


@pytest.mark.parametrize("sample", [s for s in EXPECTED if s["route"]], ids=lambda s: s["file"])
def test_prompt_contains_no_personal_data_amounts_ids_or_free_text(run, sample):
    _, llm = run(sample["file"], [ok_answer(["KB-ALL-GEN-01"], customer_message=None)] * 2)
    sent = " ".join(c["system"] + c["user"] for c in llm.calls)
    for value in sample["pii"] + [sample["amount"], sample["end_to_end_id"]]:
        assert value not in sent, value
    # D11: the free-text field never reaches the prompt (data minimisation, no prompt-injection surface).
    assert "No response from beneficiary" not in sent


# --- logging --------------------------------------------------------------------------------

def test_each_case_logs_one_line_without_text_or_personal_data(run):
    run("sct_inst_ac04_closed.xml", [ok_answer(["KB-INVENTED-01"]), ok_answer(["KB-SCTI-AC04-01"])])
    [record] = run.log()
    assert set(record) == {"timestamp", "case_id", "code", "rail", "stage", "outcome", "route", "attempts",
                           "failures", "model", "input_tokens", "output_tokens", "cost_usd", "latency_s"}
    assert (record["outcome"], record["attempts"], record["failures"]) == ("ai_retry_ok", 2, ["unknown_citation"])
    assert record["cost_usd"] == pytest.approx(0.004)
    logged = json.dumps(record)
    for leak in ["E2E-TEST-0001", "Erika", "DE89370400440532013000", "KB-INVENTED-01", "beneficiary"]:
        assert leak not in logged, leak



# --- D12: policy-fixed answers are owned by code (first live run) ------------------------------

# Reconstructed from the first live RR04 run (the log deliberately stores no answer text): the AI cited
# the no-tipping-off rule and still told ops to have the customer discuss the regulatory concern.
LIVE_RR04_ANSWER = {
    "what_happened": "The beneficiary's bank rejected the payment for a regulatory reason.",
    "next_step": "Advise the customer to discuss the regulatory concern with the beneficiary before retrying.",
    "customer_message": None,
    "citations": ["KB-ALL-GEN-01", "KB-SCTI-RR04-01"],
}


def test_live_rr04_output_is_blocked_and_overridden(run):
    result, llm = run("sct_inst_rr04_regulatory.xml", [LIVE_RR04_ANSWER, LIVE_RR04_ANSWER])
    # Blocked: the check names the customer-contact instruction and feeds it back on the retry.
    assert "compliance_customer_contact (next_step: Advise the customer)" in llm.calls[1]["user"]
    assert result.outcome is CaseOutcome.ESCALATED
    # Overridden: whatever the AI wrote, ops see only the policy text and nothing goes to the customer.
    assert result.next_step == COMPLIANCE_NEXT_STEP
    assert result.next_step_source is NextStepSource.POLICY
    assert result.customer_message is None
    assert "discuss the regulatory concern" not in result.next_step + result.what_happened


def test_compliance_retry_keeps_the_ai_what_happened_and_the_policy_next_step(run):
    fixed = LIVE_RR04_ANSWER | {"next_step": ""}
    result, _ = run("sct_inst_rr04_regulatory.xml", [LIVE_RR04_ANSWER, fixed])
    assert result.outcome is CaseOutcome.AI_RETRY_OK
    assert result.what_happened == fixed["what_happened"]
    assert (result.next_step, result.next_step_source) == (COMPLIANCE_NEXT_STEP, NextStepSource.POLICY)


def test_compliance_next_step_is_overridden_even_when_it_passes_the_checks(run):
    # A next_step no pattern catches still never reaches ops: code owns it on COMPLIANCE.
    harmless = LIVE_RR04_ANSWER | {"next_step": "File the case in the regulatory queue and wait for the outcome."}
    result, _ = run("sct_inst_rr04_regulatory.xml", [harmless])
    assert result.outcome is CaseOutcome.AI_OK
    assert result.next_step == COMPLIANCE_NEXT_STEP


@pytest.mark.parametrize("threshold, outcome", [(None, CaseOutcome.ESCALATED), (1.01, CaseOutcome.NO_GUIDANCE)])
def test_every_compliance_path_uses_the_policy_next_step(run, threshold, outcome):
    extra = {"threshold": threshold} if threshold else {}
    answers = [] if threshold else ["not json", "not json"]
    result, _ = run("sct_inst_rr04_regulatory.xml", answers, **extra)
    assert result.outcome is outcome
    assert (result.next_step, result.customer_message) == (COMPLIANCE_NEXT_STEP, None)


def test_rr04_table_baseline_matches_the_policy_text():
    # One text everywhere, so the D4 baseline and the product say the same thing.
    assert lookup("RR04").baseline_what_to_do == COMPLIANCE_NEXT_STEP


def test_non_compliance_next_step_source_is_recorded(run):
    ai, _ = run("sct_inst_ac04_closed.xml", [ok_answer(["KB-SCTI-AC04-01"])])
    baseline, _ = run("sct_inst_ac04_closed.xml", [], threshold=1.01)
    assert ai.next_step_source is NextStepSource.AI
    assert baseline.next_step_source is NextStepSource.BASELINE


def test_prompt_tells_the_ai_what_to_return_on_compliance(run):
    _, llm = run("sct_inst_rr04_regulatory.xml", [LIVE_RR04_ANSWER | {"next_step": ""}])
    assert 'When the route is COMPLIANCE, write "what_happened" for the compliance team' in llm.calls[0]["system"]


# --- D16 --------------------------------------------------------------------------------

DS24_POLICY = "Your payment did not complete. Please don't send it again until we've confirmed its status."


def _rtp_ds24():
    xml = (SAMPLES_DIR / "rtp_ac06_blocked.xml").read_text(encoding="utf-8")
    return parse_xml(xml.replace("<Rsn><Cd>AC06</Cd></Rsn>", "<Rsn><Cd>DS24</Cd></Rsn>"))


def test_rtp_ds24_customer_message_is_policy_text_in_the_ai_path(run):
    result, llm = run(_rtp_ds24(), [ok_answer(["KB-RTP-DS24-01"], customer_message=None)])
    assert result.outcome is CaseOutcome.AI_OK
    assert result.customer_message == DS24_POLICY
    assert "Customer message: set by bank policy." in llm.calls[0]["user"]


def test_rtp_ds24_ai_customer_message_is_retried_then_replaced(run):
    result, llm = run(_rtp_ds24(), [ok_answer(["KB-RTP-DS24-01"], customer_message="Please try again later."),
                                    ok_answer(["KB-RTP-DS24-01"], customer_message=None)])
    assert result.outcome is CaseOutcome.AI_RETRY_OK
    assert "policy_customer_message" in llm.calls[1]["user"]
    assert result.customer_message == DS24_POLICY


def test_rtp_ds24_baseline_uses_the_policy_text(run, tmp_path):
    status = _rtp_ds24()
    result = explain_case(status, None, log_path=tmp_path / "l.jsonl", embedder=FakeEmbedder(),
                          cache_path=tmp_path / "e.npz", gaps_path=tmp_path / "g.jsonl")
    assert result.outcome is CaseOutcome.BASELINE and result.customer_message == DS24_POLICY
    assert lookup("DS24").baseline_customer_message == DS24_POLICY


def test_withheld_reason_fact_is_in_the_prompt_and_speculation_is_retried(run):
    speculative = "Your payment was rejected. This may be due to a regulatory restriction."
    xml =(SAMPLES_DIR / "sct_inst_ac04_closed.xml").read_text(encoding="utf-8").replace("<Cd>AC04</Cd>", "<Cd>MS03</Cd>")
    result, llm = run(parse_xml(xml), [ok_answer(["KB-SCTI-MS03-01"], customer_message=speculative),
                                       ok_answer(["KB-SCTI-MS03-01"], customer_message="No reason was given.")])
    assert "Reason withheld" in llm.calls[0]["user"]
    assert "speculative_reason" in llm.calls[1]["user"]
    assert result.outcome is CaseOutcome.AI_RETRY_OK


@pytest.mark.parametrize("sample, role", [
    ("sct_inst_ac04_closed.xml", "We are the payer's bank (the debtor's bank)"),
    ("rtp_ac06_blocked.xml", "We are the payer's bank (the sending bank)"),
    ("sdd_am04_insufficient.xml", "We are the creditor's bank"),
])
def test_prompt_states_which_bank_we_are(run, sample, role):
    code = parse_file(SAMPLES_DIR / sample).reason_code
    cite = {"AC04": "KB-SCTI-AC04-01", "AC06": "KB-RTP-AC06-01", "AM04": "KB-SDD-AM04-01"}[code]
    _, llm = run(sample, [ok_answer([cite])])
    assert f"Our role: {role}" in llm.calls[0]["user"]
