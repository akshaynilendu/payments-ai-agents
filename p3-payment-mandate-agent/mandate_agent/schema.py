"""What an agent may propose, and what the bank side decides.

The proposal is the only thing an agent can send. It cannot carry the sender,
the time, or an "approved" flag: the server reads those from its own records.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class Action(StrEnum):
    TRANSFER = "TRANSFER"
    REFUND = "REFUND"
    ASK_HUMAN = "ASK_HUMAN"
    DECLINE = "DECLINE"


class Outcome(StrEnum):
    EXECUTED = "EXECUTED"
    SENT_FOR_APPROVAL = "SENT_FOR_APPROVAL"
    ASKED_HUMAN = "ASKED_HUMAN"
    DECLINED = "DECLINED"


# Worst outcome wins when several checks fire.
SEVERITY = {Outcome.EXECUTED: 0, Outcome.SENT_FOR_APPROVAL: 1, Outcome.ASKED_HUMAN: 2, Outcome.DECLINED: 3}


class Proposal(BaseModel):
    request_id: str
    action: Action
    currency: str | None = None
    amount: float | None = Field(default=None, gt=0)
    # TRANSFER: a known supplier id, or "NEW" with name and account
    payee_id: str | None = None
    payee_name: str | None = None
    account: str | None = None          # "12-34-56 12345678" or an IBAN
    invoice_ref: str | None = None
    instalment: str | None = None       # e.g. "3/3" when an invoice is paid in parts
    # REFUND: the order; money always goes back to the account that paid
    order_id: str | None = None
    note: str | None = None             # the agent's short reason, kept for the audit log


class Finding(BaseModel):
    code: str
    outcome: Outcome
    detail: str


class Decision(BaseModel):
    request_id: str
    outcome: Outcome
    reasons: list[Finding]
    executed: dict | None = None        # what money actually moved (or would, for approval)
    token_id: str | None = None
    audit_hash: str | None = None
