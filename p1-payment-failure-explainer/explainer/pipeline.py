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
from explainer.codes import (FAILURE_STAGES, Rail, ReasonCode, Route, SourceType, Stage, lookup,
                             policy_customer_message)
from explainer.explain import OUTPUT_SCHEMA, build_beyond_prompt, build_prompt, source_label
from explainer.iso_codes import SOURCE_NOTE as ISO_SOURCE_NOTE
from explainer.iso_codes import SOURCE_URL as ISO_SOURCE_URL
from explainer.iso_codes import IsoCode, lookup_iso
from explainer.knowledge import KbRail, Passage, Topic, family_of
from explainer.llm import LLMClient, LLMError, cost_usd
from explainer.parse import PaymentStatus
from explainer.retrieve import (Mode, RetrievalResult, Retrieved, family_passages, general_passages, retrieve,
                                safe_code)

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
# D19: outside the table the customer text is fixed by policy per code family, never generated: no promise,
# no guess, nothing that contradicts the family's runbook. None = no customer message (MD: the specialist
# team decides). A return already settled and came back, so it says "returned", not "did not complete".
_BEYOND_TEXTS = {
    "MD": None,
    "MS_SL": ("{this} did not complete and no reason was given. Please contact the other party.",
              "{this} was returned and no reason was given. Please contact the other party."),
    "AM": ("{this} could not be made for this amount.", "{this} was returned because of the amount."),
    None: ("{this} did not complete.", "{this} was returned."),
}


def beyond_table_customer_message(code: str, rail: Rail, stage: Stage) -> str | None:
    family = family_of(code)
    texts = _BEYOND_TEXTS[family if family in _BEYOND_TEXTS else None]
    if texts is None:
        return None
    returned = stage is Stage.RETURN
    # SDD returns are collections our customer (the creditor) made; everything else is a payment.
    this = "This collection" if returned and rail is Rail.SEPA_DD else "This payment"
    return texts[1 if returned else 0].format(this=this)
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
    AI_BEYOND_TABLE = "ai_beyond_table"  # code not in our table; AI explained it from the ISO definition (D17)
    BASELINE = "baseline"  # no AI by choice: the code table's fixed text, the D4 baseline for evals


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


def explain(status: PaymentStatus, llm: LLMClient, mode: Mode | str = Mode.FILTER_RANK, *,
            log_path: Path = config.EXPLAIN_LOG, **retrieve_options) -> CaseResult:
    """The product entry point (D17): table when it knows, AI for staff when the table has no answer.

    - Code in the table: the table's reviewed text and route; the model is never passed in, so no AI call.
    - Code outside the table that is a valid ISO 20022 code: the AI explains it for staff from the official
      definition and the family runbook; the customer gets the family's fixed text, never AI text (D19).
    - Anything else (stops, unknown codes): the fixed outcome, no AI call.
    """
    in_table = lookup(status.reason_code) is not None
    return explain_case(status, None if in_table else llm, mode, log_path=log_path, **retrieve_options)


def explain_case(status: PaymentStatus, llm: LLMClient | None, mode: Mode | str = Mode.FILTER_RANK, *,
                 log_path: Path = config.EXPLAIN_LOG, **retrieve_options) -> CaseResult:
    """Eval-only (and explain()'s engine); product code calls explain().

    Given a model, this runs the AI on any code, including codes in the table, so the evals can compare the
    AI with the table. llm=None gives the no-AI baseline through the same stops, routing and policy (D4).
    """
    started = time.perf_counter()
    result = _explain(status, llm, mode, retrieve_options)
    result = _with(result, latency_s=round(time.perf_counter() - started, 3))
    _log_case(log_path, status, result)
    return result


def _explain(status: PaymentStatus, llm: LLMClient | None, mode, retrieve_options: dict) -> CaseResult:
    prepared = prepare(status, mode, **retrieve_options)
    base = dict(code=status.reason_code, rail=status.rail, stage=status.stage, citations=(), note=None,
                attempts=0, failures=(), model=None, input_tokens=0, output_tokens=0, cost_usd=0.0, latency_s=0.0)

    if prepared.outcome is not Outcome.PROCEED:
        outcome = CaseOutcome.NOT_A_FAILURE if prepared.outcome is Outcome.NOT_A_FAILURE else CaseOutcome.PENDING
        return CaseResult(outcome=outcome, route=None, what_happened=prepared.message, next_step="",
                          next_step_source=NextStepSource.NONE, customer_message=None, **base)

    code = prepared.code
    if code is None:
        # Not in our table, so the table can't route it (D3). A valid ISO code still has an official
        # definition the AI can explain from (D17); anything else has no guidance at all.
        escalate = dict(
            route=None, what_happened=f"Reason code {safe_code(status.reason_code or '')} is not in our code table.",
            next_step="Escalate for manual triage; no explanation is available for this code.",
            next_step_source=NextStepSource.BASELINE, customer_message=None)
        iso = lookup_iso(status.reason_code, status.message_type.value)
        if iso is None:
            return CaseResult(outcome=CaseOutcome.ESCALATED, **escalate, **base | {"note": "unknown_code"})
        if llm is None:
            return CaseResult(outcome=CaseOutcome.ESCALATED, **escalate, **base | {"note": "beyond_table_no_ai"})
        return _explain_beyond(status, iso, llm, base, escalate)

    route = code.route_for(status.rail)
    # D16(b): where policy fixes the customer message, code owns it and the AI is asked for null.
    customer_policy = policy_customer_message(code.code, status.rail)
    # Tipping off: on a compliance route code owns next_step and nothing goes to the customer (D11, D12).
    compliance = route is Route.COMPLIANCE
    policy = dict(next_step=COMPLIANCE_NEXT_STEP, next_step_source=NextStepSource.POLICY, customer_message=None)
    baseline = dict(route=route, what_happened=code.baseline_what_happened) | (policy if compliance else dict(
        next_step=code.what_to_do_for(status.rail), next_step_source=NextStepSource.BASELINE,
        # D16(b): a policy-owned customer message replaces the table text in the baseline too.
        customer_message=policy_customer_message(code.code, status.rail) or code.customer_message_for(status.rail)))

    if llm is None:
        return CaseResult(outcome=CaseOutcome.BASELINE, **baseline, **base)

    if prepared.retrieval.gap:
        # D7: no relevant guidance, so no AI call: $0 and nothing can be invented.
        return CaseResult(outcome=CaseOutcome.NO_GUIDANCE, **baseline, **base | {"note": NO_GUIDANCE_NOTE})

    passages = prepared.retrieval.all()
    by_id = {r.passage.id: r.passage for r in passages}
    asked = _ask(
        llm,
        lambda feedback: build_prompt(code, status.rail, status.stage, route, passages, feedback),
        lambda response: check(response.text, allowed_citations=set(by_id), route=route,
                               stop_reason=response.stop_reason, code=code.code,
                               customer_policy=bool(customer_policy)))
    if asked.answer:
        answer = asked.answer
        return CaseResult(
            outcome=CaseOutcome.AI_OK if asked.attempts == 1 else CaseOutcome.AI_RETRY_OK,
            route=route,  # never from the AI
            what_happened=answer["what_happened"],
            # On COMPLIANCE the AI writes only what_happened; the rest is policy (D12).
            **(policy if compliance else dict(next_step=answer["next_step"],
                                              next_step_source=NextStepSource.AI,
                                              customer_message=customer_policy or answer["customer_message"])),
            **base | dict(citations=_citations(answer, by_id)) | asked.usage(llm.model))

    # D3: still failing after one retry, so a person takes over with the baseline text.
    return CaseResult(outcome=CaseOutcome.ESCALATED, **baseline, **base | dict(
        note="AI answer failed the checks; showing the baseline (D3).") | asked.usage(llm.model))


def beyond_table_passages(iso: IsoCode, rail: Rail, stage: Stage) -> list[Retrieved]:
    """What the AI gets for a code outside the table: the official definition, then the rail's general passages."""
    iso_passage = Passage(
        id=iso.passage_id, rail=KbRail.ALL, codes=(), stages=FAILURE_STAGES, families=(), topic=Topic.MEANING,
        mandatory=False,
        source_type=SourceType.ISO_CODE_LIST, owner=None, text=f"{iso.code}: {iso.definition}",
        source_url=ISO_SOURCE_URL, source_section=f"{iso.code_set}. {ISO_SOURCE_NOTE.format(release=iso.release)}",
        needs_review=False, reviewed_by=None, reviewed_on=None, review_note="", caveat="")
    return ([Retrieved(iso_passage, None)] + family_passages(iso.code, stage)  # D18: what to do, by family
            + general_passages(rail, stage))


def _explain_beyond(status: PaymentStatus, iso: IsoCode, llm: LLMClient, base: dict, escalate: dict) -> CaseResult:
    """D17: a valid ISO code our table doesn't cover. The AI explains it for staff from the official
    definition; the route stays manual triage and the customer gets fixed policy text, never AI text."""
    passages = beyond_table_passages(iso, status.rail, status.stage)
    by_id = {r.passage.id: r.passage for r in passages}
    asked = _ask(
        llm,
        lambda feedback: build_beyond_prompt(iso, status.rail, status.stage, passages, feedback),
        lambda response: check(response.text, allowed_citations=set(by_id), route=None,
                               stop_reason=response.stop_reason, code=iso.code, customer_policy=True,
                               required_citations=frozenset({iso.passage_id} | {
                                   r.passage.id for r in passages if r.passage.families}),
                               # D19: sensitive words only where the definition or a cited passage uses them.
                               sensitive_sources={pid: p.text for pid, p in by_id.items()},
                               always_allowed=iso.definition))
    if asked.answer:
        return CaseResult(
            outcome=CaseOutcome.AI_BEYOND_TABLE, route=None,
            what_happened=asked.answer["what_happened"], next_step=asked.answer["next_step"],
            next_step_source=NextStepSource.AI,
            customer_message=beyond_table_customer_message(iso.code, status.rail, status.stage),
            **base | dict(citations=_citations(asked.answer, by_id)) | asked.usage(llm.model))
    return CaseResult(outcome=CaseOutcome.ESCALATED, **escalate, **base | dict(
        note="beyond_table_check_failed: AI answer failed the checks; escalated (D3).") | asked.usage(llm.model))


@dataclass(frozen=True)
class _Asked:
    answer: dict | None  # None when no attempt passed the checks
    attempts: int
    failures: tuple[str, ...]
    input_tokens: int
    output_tokens: int

    def usage(self, model: str) -> dict:
        return dict(attempts=self.attempts, failures=self.failures, model=model, input_tokens=self.input_tokens,
                    output_tokens=self.output_tokens,
                    cost_usd=cost_usd(model, self.input_tokens, self.output_tokens))


def _ask(llm: LLMClient, prompt_for, check_answer) -> _Asked:
    """One try plus one retry with the failed checks fed back (D3). Shared by both AI paths."""
    failures_log: list[str] = []
    feedback: list[str] = []
    input_tokens = output_tokens = attempts = 0
    for attempt in range(1, MAX_ATTEMPTS + 1):
        attempts = attempt
        system, user = prompt_for(feedback)
        try:
            response = llm.complete(system, user, OUTPUT_SCHEMA)
        except LLMError as e:
            # The SDK already retried network errors; a second call would blow the latency budget (D4).
            failures_log.append(f"attempt {attempt}: llm_error ({e})")
            break
        input_tokens += response.input_tokens
        output_tokens += response.output_tokens
        checked = check_answer(response)
        if checked.ok:
            return _Asked(checked.answer, attempt, tuple(failures_log), input_tokens, output_tokens)
        feedback = [str(f) for f in checked.failures]
        failures_log += [f"attempt {attempt}: {f}" for f in feedback]
    return _Asked(None, attempts, tuple(failures_log), input_tokens, output_tokens)


def _citations(answer: dict, by_id: dict) -> tuple:
    return tuple(_citation(by_id[cid]) for cid in dict.fromkeys(answer["citations"]))


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
