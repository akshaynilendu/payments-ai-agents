import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mandate_agent import config  # noqa: E402
from mandate_agent.agent import decision_from_audit, run_agent, server_params  # noqa: E402
from mandate_agent.bank import BankSide  # noqa: E402
from mandate_agent.llm import FakeAgentLLM  # noqa: E402
from mandate_agent.mcp_server import build_server  # noqa: E402
from mandate_agent.schema import Outcome  # noqa: E402


def use(i, name, args):
    return {"type": "tool_use", "id": f"t{i}", "name": name, "input": args}


def run(rid, turns, tmp_path):
    bank = BankSide(rid, audit_path=tmp_path / f"{rid}.jsonl")
    llm = FakeAgentLLM(turns)
    proposal, meta = asyncio.run(run_agent(bank.world.requests[rid], llm, build_server(bank)))
    return proposal, meta, decision_from_audit(tmp_path / f"{rid}.jsonl", rid), llm


def test_agent_proposal_goes_through_the_engine(tmp_path):
    turns = [[use(1, "lookup_order", {"order_id": "ORD-1013"})],
             [use(2, "propose_payment", {"action": "REFUND", "order_id": "ORD-1013", "amount": 35.0, "currency": "GBP"})]]
    proposal, meta, decision, llm = run("RQ-14", turns, tmp_path)
    assert decision.outcome == Outcome.EXECUTED and decision.executed["amount"] == 35.0
    assert meta.tool_calls == ["lookup_order", "propose_payment"] and meta.stopped == "proposed"
    assert "SYSTEM NOTICE" in llm.calls[0]["messages"][0]["content"]   # email reaches the model as data
    assert "<email>" in llm.calls[0]["messages"][0]["content"]


def test_injected_payment_is_declined_even_if_the_agent_obeys(tmp_path):
    turns = [[use(1, "propose_payment", {"action": "TRANSFER", "payee_id": "NEW", "payee_name": "D. Marsh",
                                         "account": "40-11-22 11223344", "amount": 2400.0, "currency": "GBP"})]]
    _, _, decision, _ = run("RQ-14", turns, tmp_path)
    assert decision.outcome == Outcome.DECLINED


def test_only_the_first_proposal_counts(tmp_path):
    turns = [[use(1, "propose_payment", {"action": "TRANSFER", "payee_id": "SUP-05", "amount": 6200.0, "currency": "GBP",
                                         "invoice_ref": "HP-3310"}),
              use(2, "propose_payment", {"action": "TRANSFER", "payee_id": "SUP-05", "amount": 4900.0, "currency": "GBP",
                                         "invoice_ref": "HP-3310"})]]
    proposal, meta, decision, _ = run("RQ-06", turns, tmp_path)
    assert proposal["amount"] == 6200.0 and decision.outcome == Outcome.DECLINED
    assert meta.proposals == 2


def test_tool_budget_is_enforced(tmp_path):
    lookups = [[use(i, "get_mandate", {"currency": "GBP"})] for i in range(config.MAX_TOOL_CALLS + 1)]
    turns = lookups + [[use(99, "propose_payment", {"action": "ASK_HUMAN", "note": "unsure"})]]
    _, meta, decision, _ = run("RQ-17", turns[: config.MAX_TURNS], tmp_path)
    assert len(meta.tool_calls) <= config.MAX_TOOL_CALLS + 1
    assert meta.turns <= config.MAX_TURNS


def test_no_proposal_is_recorded(tmp_path):
    _, meta, decision, _ = run("RQ-18", [[{"type": "text", "text": "This is a question."}]], tmp_path)
    assert meta.stopped == "no_proposal" and decision is None


def test_stdio_server_starts_and_logs(tmp_path):
    turns = [[use(1, "propose_payment", {"action": "TRANSFER", "payee_id": "SUP-01", "amount": 740.0,
                                         "currency": "GBP", "invoice_ref": "INV-KW-2291"})]]
    audit = tmp_path / "RQ-03.jsonl"
    req = BankSide("RQ-03").world.requests["RQ-03"]
    asyncio.run(run_agent(req, FakeAgentLLM(turns), server_params("RQ-03", True, audit)))
    assert decision_from_audit(audit, "RQ-03").outcome == Outcome.EXECUTED


from mandate_agent.orchestrator import run_orchestrated  # noqa: E402


def route(r):
    return [{"type": "tool_use", "id": "r1", "name": "route", "input": {"route": r, "reason": "test"}}]


def run_d(rid, turns, tmp_path):
    bank = BankSide(rid, audit_path=tmp_path / f"{rid}.jsonl")
    llm = FakeAgentLLM(turns)
    proposal, meta, r = asyncio.run(run_orchestrated(bank.world.requests[rid], llm, build_server(bank)))
    return proposal, meta, r, decision_from_audit(tmp_path / f"{rid}.jsonl", rid), llm


def test_orchestrator_routes_to_refund_specialist_with_narrow_tools(tmp_path):
    turns = [route("REFUND"),
             [use(1, "lookup_order", {"order_id": "ORD-2001"})],
             [use(2, "propose_payment", {"action": "REFUND", "order_id": "ORD-2001", "amount": 72.0, "currency": "EUR"})]]
    _, meta, r, decision, llm = run_d("RQ-23", turns, tmp_path)
    assert r == "REFUND" and decision.outcome == Outcome.EXECUTED
    assert llm.calls[0]["tools"] == ["route"]
    assert sorted(llm.calls[1]["tools"]) == ["get_mandate", "lookup_order", "propose_payment"]


def test_orchestrator_human_route_logs_ask_human(tmp_path):
    _, _, r, decision, _ = run_d("RQ-18", [route("HUMAN")], tmp_path)
    assert r == "HUMAN" and decision.outcome == Outcome.ASKED_HUMAN


def test_specialist_cannot_use_a_tool_it_was_not_given(tmp_path):
    turns = [route("REFUND"),
             [use(1, "lookup_supplier", {"query": "SUP-01"})],
             [use(2, "propose_payment", {"action": "ASK_HUMAN", "note": "unsure"})]]
    _, meta, _, decision, llm = run_d("RQ-01", turns, tmp_path)
    assert "lookup_supplier" not in meta.tool_calls
    assert "not available" in str(llm.calls[2]["messages"][-1])
