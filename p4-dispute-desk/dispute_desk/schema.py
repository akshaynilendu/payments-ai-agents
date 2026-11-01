"""What the agent may propose, and what the rules engine decides.

The proposal is the only thing an agent sends. The deadline, the ledger and the
tracking live in the shop's records; the engine reads those itself.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class Outcome(StrEnum):
    FIGHT = "FIGHT"
    ACCEPT = "ACCEPT"
    ALREADY_REFUNDED = "ALREADY_REFUNDED"
    ASK_HUMAN = "ASK_HUMAN"


class Priority(StrEnum):
    SUBMIT_TODAY = "SUBMIT_TODAY"
    NORMAL = "NORMAL"
    LATE = "LATE"


class Proposal(BaseModel):
    dispute_id: str
    outcome: Outcome
    evidence: list[str] = Field(default_factory=list)
    note: str | None = None


class Finding(BaseModel):
    code: str
    detail: str


class Decision(BaseModel):
    dispute_id: str
    outcome: Outcome
    priority: Priority
    reasons: list[Finding]
    evidence_pack: dict
    audit_hash: str | None = None
