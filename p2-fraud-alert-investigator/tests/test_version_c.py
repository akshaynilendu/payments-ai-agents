"""Version C with a scripted agent ($0, no network): tools, budget, submission checks, fallback, no hindsight."""

import pytest

from investigator.checks import run_checks
from investigator.llm import FakeAgentLLM, LLMError
from investigator.schema import Hypothesis
from investigator.version_a import investigate as investigate_a
from investigator.version_b import is_payment_data
from investigator.version_c import MAX_TOOL_CALLS, investigate, past_case_detail, receiving_account_network


def tool(name, i, **args):
    return {"type": "tool_use", "id": f"t{i}", "name": name, "input": args}


def submit(i, findings, hypothesis="APP_IMPERSONATION", cite=None):
    solid = [f for f in findings if f.signals and not is_payment_data(f.id)]
    fid = cite or solid[0].id
    return tool("submit_assessment", i, leading_hypothesis=hypothesis, evidence_for=[fid], evidence_against=[],
                missing_information=["Who was the customer speaking to?"], rationale=f"Warning sign [{fid}].")


@pytest.fixture(scope="module")
def case(ds, gold):
    alert = next(a for a in ds.alerts if gold[a.alert_id]["hard_kind"] == "injection_reference")
    return alert, run_checks(ds, alert)


def test_agent_can_dig_then_cite_what_it_found(ds, case):
    alert, findings = case
    llm = FakeAgentLLM([[tool("login_history", 1)],
                        [submit(2, findings, cite=f"login_history:{alert.customer_id}:sessions")]])
    summary, meta = investigate(ds, alert, llm)
    assert meta.tools_used == ["login_history"] and not meta.fallback_to_a
    assert summary.assessment.evidence_for[0].source_id == f"login_history:{alert.customer_id}:sessions"
    assert f"login_history:{alert.customer_id}:sessions" in summary.check_result_ids


def test_tool_budget_is_enforced(ds, case):
    alert, findings = case
    turns = [[tool("login_history", i)] for i in range(MAX_TOOL_CALLS + 1)] + [[submit(99, findings)]]
    llm = FakeAgentLLM(turns)
    _, meta = investigate(ds, alert, llm)
    assert len(meta.tools_used) == MAX_TOOL_CALLS
    assert llm.calls[-1]["tools"] == ["submit_assessment"]


def test_bad_submission_gets_one_fix_then_falls_back(ds, case):
    alert, findings = case
    bad = tool("submit_assessment", 1, leading_hypothesis="APP_PURCHASE", evidence_for=["made:up"],
               evidence_against=[], missing_information=[], rationale="x [made:up]")
    bad2 = {**bad, "id": "t2"}
    summary, meta = investigate(ds, alert, FakeAgentLLM([[bad], [bad2]]))
    assert meta.fallback_to_a
    assert summary.assessment == investigate_a(ds, alert).assessment


def test_genuine_gate_applies_to_the_agent(ds, case):
    alert, findings = case
    summary, meta = investigate(ds, alert, FakeAgentLLM([[submit(1, findings, "GENUINE")]]))
    assert summary.assessment.leading_hypothesis == Hypothesis.INSUFFICIENT_EVIDENCE and meta.genuine_gate


def test_never_submitting_falls_back(ds, case):
    alert, _ = case
    turns = [[{"type": "text", "text": "thinking aloud"}]] * 8
    _, meta = investigate(ds, alert, FakeAgentLLM(turns))
    assert meta.fallback_to_a


def test_model_error_falls_back(ds, case):
    alert, _ = case
    _, meta = investigate(ds, alert, FakeAgentLLM([LLMError("timeout")]))
    assert meta.fallback_to_a


def test_tools_never_show_hindsight(ds):
    # Pick a past case closed after some alert: the tool must not reveal it to that alert.
    alert = min(ds.alerts, key=lambda a: a.received_at)
    later = [c for c in ds.past_cases if c.closed_at >= alert.received_at]
    for c in later:
        assert "No closed case" in past_case_detail(ds, alert, c.case_id).fact
    net = receiving_account_network(ds, alert)
    assert all(c.case_id not in net.fact for c in later)


def test_core_checks_always_run_before_the_agent(ds, case):
    alert, findings = case
    llm = FakeAgentLLM([[submit(1, findings)]])
    investigate(ds, alert, llm)
    prompt = llm.calls[0]["messages"][0]["content"]
    assert f"payee_risk:{alert.payee_id}:account_age" in prompt  # payee risk is mandatory


def test_version_hc_sends_only_rule_gaps_to_the_agent(ds):
    from investigator.version_h import investigate_hc
    a_answers = {a.alert_id: investigate_a(ds, a).assessment.leading_hypothesis for a in ds.alerts}
    for a in ds.alerts:
        findings = run_checks(ds, a)
        llm = FakeAgentLLM([[submit(1, findings, "APP_PURCHASE")]])
        summary, _ = investigate_hc(ds, a, llm)
        if a_answers[a.alert_id] == Hypothesis.INSUFFICIENT_EVIDENCE:
            assert len(llm.calls) == 1
        else:
            assert llm.calls == [] and summary.assessment.leading_hypothesis == a_answers[a.alert_id]
