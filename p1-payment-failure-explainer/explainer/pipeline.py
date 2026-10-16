"""The explainer: prepare() decides whether there is a failure to explain and gathers the facts;
explain_case() adds the AI call, the check, one retry and escalation (D3, D7, D11).
"""

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from explainer import config
from explainer.check import check
from explainer.codes import Rail, ReasonCode, Route, Stage, lookup
from explainer.explain import OUTPUT_SCHEMA, build_prompt, source_label
from explainer.llm import LLMClient, LLMError, cost_usd
from explainer.parse import PaymentStatus
from explainer.retrieve import Mode, RetrievalResult, retrieve, safe_code

NO_FAILURE_MESSAGE = "No failure to explain: the payment was accepted or settled."
# Resending a pending payment is the classic way to pay twice (same reasoning as the DS24 runbook).
PENDING_MESSAGE = ("No failure to explain yet: the payment is still pending. Do not resend; wait for the "
                   "final status or request it (pacs.028 status request).")


class Outcome(StrEnum):
    NOT_A_FAILURE = "NOT_A_FAILURE"
    PENDING = "PENDING"
    PROCEED = "PROCEED"


@dataclass(frozen=True)
class Prepared:
    outcome: Outcome
    status: PaymentStatus
    message: str | None = None             # set when the explainer stops
    code: ReasonCode | None = None         # None for a code not in our table: escalate (D3)
    retrieval: RetrievalResult | None = None


def prepare(status: PaymentStatus, mode: Mode | str = Mode.FILTER_RANK, **retrieve_options) -> Prepared:
    # Stop before lookup and retrieval: there is nothing to explain, and no cost should be spent on it.
    if status.stage is Stage.NOT_A_FAILURE:
        return Prepared(Outcome.NOT_A_FAILURE, status, message=NO_FAILURE_MESSAGE)
    if status.stage is Stage.PENDING:
        return Prepared(Outcome.PENDING, status, message=PENDING_MESSAGE)
    code = lookup(status.reason_code)
    retrieval = retrieve(status.reason_code or "", status.rail, status.stage, mode, **retrieve_options)
    return Prepared(Outcome.PROCEED, status, code=code, retrieval=retrieval)


# --- explain_case (piece 3) --------------------------------------------------------

NO_GUIDANCE_NOTE = "No guidance available: showing the baseline for this code (D7)."
# D12: a policy-fixed answer is owned by code, never generated. Team runbook text.
COMPLIANCE_NEXT_STEP = ("Hand to Compliance. Do not contact the customer about the reason; "
                        "Compliance decides what, if anything, is said.")
MAX_ATTEMPTS = 2  # one try plus one retry with the failures fed back (D3)


class NextStepSource(StrEnum):
    AI = "ai"
    BASELINE = "baseline"   # the code table's fixed text
    POLICY = "policy"       # COMPLIANCE_NEXT_STEP: team runbook, owned by code (D12)
    NONE = "none"           # nothing to do: not a failure, or pending


class CaseOutcome(StrEnum):
    AI_OK = "ai_ok"
    AI_RETRY_OK = "ai_retry_ok"
    ESCALATED = "escalated"
    NO_GUIDANCE = "no_guidance"
    NOT_A_FAILURE = "not_a_failure"
    PENDING = "pending"


@dataclass(frozen=True)
class Citation:
    id: str
    # Both from passages.json, never from the AI's wording, so "Team guidance" can't be faked or dropped.
    source_type: str
    label: str
    title: str
    url: str


@dataclass(frozen=True)
class CaseResult:
    outcome: CaseOutcome
    code: str | None
    rail: Rail
    stage: Stage
    route: Route | None  # always from the routing table; None means manual triage (unknown code)
    what_happened: str
    next_step: str
    next_step_source: NextStepSource
    customer_message: str | None
    citations: tuple[Citation, ...]
    note: str | None
    attempts: int
    failures: tuple[str, ...]  # e.g. "attempt 1: unknown_citation (KB-X)"
    model: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_s: float


def explain_case(status: PaymentStatus, llm: LLMClient, mode: Mode | str = Mode.FILTER_RANK, *,
                 log_path: Path = config.EXPLAIN_LOG, **retrieve_options) -> CaseResult:
    started = time.perf_counter()
    result = _explain(status, llm, mode, retrieve_options)
    result = _with(result, latency_s=round(time.perf_counter() - started, 3))
    _log_case(log_path, status, result)
    return result


def _explain(status: PaymentStatus, llm: LLMClient, mode, retrieve_options: dict) -> CaseResult:
    prepared = prepare(status, mode, **retrieve_options)
    base = dict(code=status.reason_code, rail=status.rail, stage=status.stage, citations=(), note=None,
                attempts=0, failures=(), model=None, input_tokens=0, output_tokens=0, cost_usd=0.0, latency_s=0.0)

    if prepared.outcome is not Outcome.PROCEED:
        outcome = CaseOutcome.NOT_A_FAILURE if prepared.outcome is Outcome.NOT_A_FAILURE else CaseOutcome.PENDING
        return CaseResult(outcome=outcome, route=None, what_happened=prepared.message, next_step="",
                          next_step_source=NextStepSource.NONE, customer_message=None, **base)

    code = prepared.code
    if code is None:
        # Not in our table: no facts to explain from, and the table can't route it (D3).
        return CaseResult(
            outcome=CaseOutcome.ESCALATED, route=None,
            what_happened=f"Reason code {safe_code(status.reason_code or '')} is not in our code table.",
            next_step="Escalate for manual triage; no explanation is available for this code.",
            next_step_source=NextStepSource.BASELINE, customer_message=None, **base | {"note": "unknown_code"})

    route = code.route_for(status.rail)
    # Tipping off: on a compliance route code owns next_step and nothing goes to the customer (D11, D12).
    compliance = route is Route.COMPLIANCE
    policy = dict(next_step=COMPLIANCE_NEXT_STEP, next_step_source=NextStepSource.POLICY, customer_message=None)
    baseline = dict(route=route, what_happened=code.baseline_what_happened) | (policy if compliance else dict(
        next_step=code.what_to_do_for(status.rail), next_step_source=NextStepSource.BASELINE,
        customer_message=code.baseline_customer_message))

    if prepared.retrieval.gap:
        # D7: no relevant guidance, so no AI call: $0 and nothing can be invented.
        return CaseResult(outcome=CaseOutcome.NO_GUIDANCE, **baseline, **base | {"note": NO_GUIDANCE_NOTE})

    passages = prepared.retrieval.all()
    by_id = {r.passage.id: r.passage for r in passages}
    failures_log: list[str] = []
    feedback: list[str] = []
    input_tokens = output_tokens = 0
    attempts = 0
    for attempt in range(1, MAX_ATTEMPTS + 1):
        attempts = attempt
        system, user = build_prompt(code, status.rail, status.stage, route, passages, feedback)
        try:
            response = llm.complete(system, user, OUTPUT_SCHEMA)
        except LLMError as e:
            # The SDK already retried network errors; a second call would blow the latency budget (D4).
            failures_log.append(f"attempt {attempt}: llm_error ({e})")
            break
        input_tokens += response.input_tokens
        output_tokens += response.output_tokens
        checked = check(response.text, allowed_citations=set(by_id), route=route, stop_reason=response.stop_reason)
        if checked.ok:
            answer = checked.answer
            return CaseResult(
                outcome=CaseOutcome.AI_OK if attempt == 1 else CaseOutcome.AI_RETRY_OK,
                route=route,  # never from the AI
                what_happened=answer["what_happened"],
                # On COMPLIANCE the AI writes only what_happened; the rest is policy (D12).
                **(policy if compliance else dict(next_step=answer["next_step"],
                                                  next_step_source=NextStepSource.AI,
                                                  customer_message=answer["customer_message"])),
                **base | dict(
                    citations=tuple(_citation(by_id[cid]) for cid in dict.fromkeys(answer["citations"])),
                    attempts=attempt, failures=tuple(failures_log), model=llm.model,
                    input_tokens=input_tokens, output_tokens=output_tokens,
                    cost_usd=cost_usd(llm.model, input_tokens, output_tokens)))
        feedback = [str(f) for f in checked.failures]
        failures_log += [f"attempt {attempt}: {f}" for f in feedback]

    # D3: still failing after one retry, so a person takes over with the baseline text.
    return CaseResult(outcome=CaseOutcome.ESCALATED, **baseline, **base | dict(
        note="AI answer failed the checks; showing the baseline (D3).", attempts=attempts,
        failures=tuple(failures_log), model=llm.model, input_tokens=input_tokens, output_tokens=output_tokens,
        cost_usd=cost_usd(llm.model, input_tokens, output_tokens)))


def _citation(passage) -> Citation:
    return Citation(id=passage.id, source_type=passage.source_type.value, label=source_label(passage.source_type),
                    title=passage.source_section, url=passage.source_url)


def _with(result: CaseResult, **changes) -> CaseResult:
    return CaseResult(**(result.__dict__ | changes))


def _log_case(path: Path, status: PaymentStatus, result: CaseResult) -> None:
    """One line per case. No prompt or answer text, no amounts or names, no raw transaction reference."""
    record = {
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        # A short hash lets ops match log lines to a case without storing the reference itself.
        "case_id": hashlib.sha256(status.end_to_end_id.encode()).hexdigest()[:12],
        "code": safe_code(result.code or ""),
        "rail": result.rail.value,
        "stage": result.stage.value,
        "outcome": result.outcome.value,
        "route": result.route.value if result.route else None,
        "attempts": result.attempts,
        # Failure names only: details can quote the AI's text (e.g. a matched promise phrase).
        "failures": [f.split(": ", 1)[1].split(" (")[0] for f in result.failures],
        "model": result.model,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "cost_usd": round(result.cost_usd, 6),
        "latency_s": result.latency_s,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
