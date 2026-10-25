"""Version C: an agent that may dig deeper (D15).

The core checks always run first; the agent cannot skip them. It then gets three read-only tools for more detail
and may call at most MAX_TOOL_CALLS of them before it must submit its assessment through submit_assessment,
whose input is exactly Version B's answer. Every tool result becomes a citable finding with its own id, so the
facts still come from code; the same checks, payment-data fence and GENUINE gate as Version B apply. A failed
submission gets one chance to fix; after that, or if the agent never submits, the summary falls back to
Version A's. Nothing any tool returns can come from after the alert (no hindsight, D8).

The question this version answers: does letting the model choose extra checks beat running a fixed set?
"""

import json
import time
from collections import Counter

from investigator.checks import Finding, run_checks
from investigator.data import Alert, Dataset
from investigator.llm import LLMError, cost_usd
from investigator.schema import Assessment, EvidenceItem, Hypothesis
from investigator.version_a import MLRO_TRIGGERS, Result, assess
from investigator.version_b import SCHEMA, SYSTEM, RunMeta, build_prompt, check_answer, genuine_gate

MAX_TOOL_CALLS = 4
MAX_TURNS = 8
MAX_SUBMIT_ATTEMPTS = 2

TOOLS = [
    {"name": "login_history",
     "description": "Earlier login sessions of this customer before the alert: devices used, whether the alert's "
                    "device was seen before, earlier SIM swaps and remote-access detections.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "past_case_detail",
     "description": "Detail of one of our closed past cases (by case id, e.g. from the similar-cases fact): its "
                    "outcome, closing date, signals, and whether it paid the same receiving account as this alert.",
     "input_schema": {"type": "object", "properties": {"case_id": {"type": "string"}}, "required": ["case_id"],
                      "additionalProperties": False}},
    {"name": "receiving_account_network",
     "description": "Every one of our closed past cases that paid this alert's receiving account, with outcomes "
                    "and how many different customers of ours paid it.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
]
SUBMIT = {"name": "submit_assessment",
          "description": "Submit your final assessment. Call exactly once, when you are done investigating.",
          "input_schema": SCHEMA}

SYSTEM_C = SYSTEM + f"""

You can investigate before you submit. The FACTS already include every core check. You may call up to \
{MAX_TOOL_CALLS} investigation tools when more detail could change your assessment; do not call them otherwise. \
Each tool result is a new fact with its own id that you may cite. Finish by calling submit_assessment exactly once."""


def login_history(ds: Dataset, alert: Alert) -> Finding:
    current = ds.sessions[alert.session_id]
    earlier = sorted((s for s in ds.sessions.values()
                      if s.customer_id == alert.customer_id and s.started_at < current.started_at),
                     key=lambda s: s.started_at)
    devices = sorted({s.device_id for s in earlier})
    seen = current.device_id in devices
    swaps = [s.sim_swap_at.date().isoformat() for s in earlier if s.sim_swap_at]
    remote = sum(s.remote_access_tool for s in earlier)
    fact = (f"{len(earlier)} earlier session(s) before this one; devices used: {', '.join(devices) or 'none'}; "
            f"this session's device {current.device_id} {'was' if seen else 'was never'} seen before; "
            f"earlier SIM swaps: {', '.join(swaps) or 'none'}; earlier remote-access detections: {remote}")
    return Finding(f"login_history:{alert.customer_id}:sessions", "device_login", fact)


def past_case_detail(ds: Dataset, alert: Alert, case_id: str) -> Finding:
    payee = ds.payees[alert.payee_id]
    case = next((c for c in ds.past_cases if c.case_id == case_id and c.closed_at < alert.received_at), None)
    if case is None:
        return Finding(f"past_case:{case_id}:detail", "similar_cases", f"No closed case {case_id} before this alert")
    same = case.receiving_account == payee.account
    fact = (f"Case {case.case_id} closed {case.closed_at.date().isoformat()} as {case.outcome}; signals: "
            f"{', '.join(case.signals)}; {'paid the same' if same else 'paid a different'} receiving account")
    return Finding(f"past_case:{case.case_id}:detail", "similar_cases", fact)


def receiving_account_network(ds: Dataset, alert: Alert) -> Finding:
    payee = ds.payees[alert.payee_id]
    cases = [c for c in ds.past_cases if c.receiving_account == payee.account and c.closed_at < alert.received_at]
    outcomes = Counter(c.outcome for c in cases)
    customers = len({c.customer_id for c in cases})
    fact = (f"{len(cases)} of our closed case(s) paid this receiving account, from {customers} different "
            f"customer(s); outcomes: {', '.join(f'{o} x{n}' for o, n in sorted(outcomes.items())) or 'none'}")
    return Finding(f"receiving_account_network:{payee.payee_id}:cases", "prior_reports", fact)


def run_tool(ds: Dataset, alert: Alert, name: str, args: dict) -> Finding:
    if name == "login_history":
        return login_history(ds, alert)
    if name == "past_case_detail":
        return past_case_detail(ds, alert, str(args.get("case_id", "")))
    if name == "receiving_account_network":
        return receiving_account_network(ds, alert)
    raise ValueError(name)


def assess_c(ds: Dataset, alert: Alert, findings: list[Finding], llm, meta: RunMeta):
    findings = list(findings)
    messages = [{"role": "user", "content": build_prompt(alert, findings)}]
    tools, tool_calls, submits = TOOLS + [SUBMIT], 0, 0
    meta.tools_used = []
    start = time.monotonic()
    for _ in range(MAX_TURNS):
        try:
            response = llm.chat(SYSTEM_C, messages, tools)
        except LLMError as e:
            meta.failures.append(str(e))
            break
        meta.attempts += 1
        meta.input_tokens += response.input_tokens
        meta.output_tokens += response.output_tokens
        meta.cost_usd += cost_usd(llm.model, response.input_tokens, response.output_tokens)
        messages.append({"role": "assistant", "content": response.blocks})
        uses = [b for b in response.blocks if b.get("type") == "tool_use"]
        if not uses:
            messages.append({"role": "user", "content": "Call submit_assessment to finish."})
            continue
        results = []
        for use in uses:
            if use["name"] == "submit_assessment":
                submits += 1
                answer = use.get("input") or {}
                problems = check_answer(answer, findings)
                if not problems:
                    meta.seconds = time.monotonic() - start
                    by_id = {f.id: f for f in findings}
                    assessment = Assessment(
                        leading_hypothesis=Hypothesis(answer["leading_hypothesis"]),
                        evidence_for=[EvidenceItem(fact=by_id[i].fact, source_id=i)
                                      for i in dict.fromkeys(answer["evidence_for"])],
                        evidence_against=[EvidenceItem(fact=by_id[i].fact, source_id=i)
                                          for i in dict.fromkeys(answer["evidence_against"])],
                        missing_information=answer["missing_information"],
                        rationale=answer["rationale"] or None)
                    assessment = genuine_gate(assessment, findings, meta)
                    escalate = [f.id for f in findings if f.signals & MLRO_TRIGGERS]
                    return Result(findings, assessment, escalate)
                meta.failures.append(f"submit {submits}: " + "; ".join(problems))
                if submits >= MAX_SUBMIT_ATTEMPTS:
                    meta.seconds = time.monotonic() - start
                    meta.fallback_to_a = True
                    return assess(findings)
                results.append({"type": "tool_result", "tool_use_id": use["id"], "is_error": True,
                                "content": "Failed these checks; fix them and submit again:\n- " + "\n- ".join(problems)})
            elif tool_calls >= MAX_TOOL_CALLS:
                results.append({"type": "tool_result", "tool_use_id": use["id"], "is_error": True,
                                "content": "Tool budget used up. Call submit_assessment now."})
            else:
                tool_calls += 1
                try:
                    finding = run_tool(ds, alert, use["name"], use.get("input") or {})
                except ValueError:
                    results.append({"type": "tool_result", "tool_use_id": use["id"], "is_error": True,
                                    "content": "Unknown tool."})
                    continue
                meta.tools_used.append(use["name"])
                if finding.id not in {f.id for f in findings}:
                    findings.append(finding)
                results.append({"type": "tool_result", "tool_use_id": use["id"],
                                "content": json.dumps({"id": finding.id, "fact": finding.fact})})
        messages.append({"role": "user", "content": results})
        if tool_calls >= MAX_TOOL_CALLS:
            tools = [SUBMIT]
    meta.seconds = time.monotonic() - start
    meta.fallback_to_a = True
    return assess(findings)


def investigate(ds: Dataset, alert: Alert, llm):
    from investigator.flows import flow_for
    meta = RunMeta()
    result = assess_c(ds, alert, run_checks(ds, alert), llm, meta)
    return flow_for(alert.rail).build(ds, alert, result), meta
