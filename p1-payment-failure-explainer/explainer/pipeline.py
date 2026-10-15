"""First step of the explainer: decide whether there is a failure to explain, then gather the facts.

Piece 3 adds the AI call and the check on top of prepare().
"""

from dataclasses import dataclass
from enum import StrEnum

from explainer.codes import ReasonCode, Stage, lookup
from explainer.parse import PaymentStatus
from explainer.retrieve import Mode, RetrievalResult, retrieve

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
