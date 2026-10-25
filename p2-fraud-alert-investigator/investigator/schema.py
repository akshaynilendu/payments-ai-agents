"""The case summary (BRIEF.md). Every fact carries the id of the check result it came from; there is no score
or verdict field anywhere; next steps come only from the rail's fixed menu; the decision is left to a human."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator


class Rail(StrEnum):
    FPS = "FPS"
    SEPA_INST = "SEPA_INST"


class Outcome(StrEnum):
    GENUINE = "GENUINE"
    ACCOUNT_TAKEOVER = "ACCOUNT_TAKEOVER"
    APP_IMPERSONATION = "APP_IMPERSONATION"
    APP_INVESTMENT = "APP_INVESTMENT"
    APP_PURCHASE = "APP_PURCHASE"
    APP_INVOICE_CEO = "APP_INVOICE_CEO"


class Hypothesis(StrEnum):
    """An outcome to investigate, never a verdict: the human decides (BRIEF.md)."""
    GENUINE = "GENUINE"
    ACCOUNT_TAKEOVER = "ACCOUNT_TAKEOVER"
    APP_IMPERSONATION = "APP_IMPERSONATION"
    APP_INVESTMENT = "APP_INVESTMENT"
    APP_PURCHASE = "APP_PURCHASE"
    APP_INVOICE_CEO = "APP_INVOICE_CEO"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


# D2: each rail has its own fixed menu; no recall in v1 (we decide before money moves).
class UkNextStep(StrEnum):
    RELEASE_WITH_NOTE = "RELEASE_WITH_NOTE"
    CALL_CUSTOMER_REGISTERED_NUMBER = "CALL_CUSTOMER_REGISTERED_NUMBER"
    ASK_PAYMENT_PURPOSE = "ASK_PAYMENT_PURPOSE"
    REQUEST_INFO_RECEIVING_BANK = "REQUEST_INFO_RECEIVING_BANK"
    ESCALATE_MLRO = "ESCALATE_MLRO"


class SepaNextStep(StrEnum):
    EXECUTE_WITH_NOTE = "EXECUTE_WITH_NOTE"
    REJECT_BEFORE_EXECUTION = "REJECT_BEFORE_EXECUTION"
    CALL_CUSTOMER_REGISTERED_NUMBER = "CALL_CUSTOMER_REGISTERED_NUMBER"
    ASK_PAYMENT_PURPOSE = "ASK_PAYMENT_PURPOSE"
    ESCALATE_MLRO = "ESCALATE_MLRO"


SEPA_DEADLINE_NOTE = "Held before execution; no regulated hold window; not sent until decided"

_STRICT = ConfigDict(extra="forbid", frozen=True)


class EvidenceItem(BaseModel):
    model_config = _STRICT
    fact: str = Field(min_length=1)
    source_id: str = Field(min_length=1)


class Evidence(BaseModel):
    model_config = _STRICT
    customer_baseline: list[EvidenceItem]
    device_login: list[EvidenceItem]
    payee_risk: list[EvidenceItem]
    prior_reports: list[EvidenceItem]
    similar_cases: list[EvidenceItem]
    vulnerability: list[EvidenceItem]


class Assessment(BaseModel):
    """No numeric score, by design: a score would read as a verdict."""
    model_config = _STRICT
    leading_hypothesis: Hypothesis
    evidence_for: list[EvidenceItem]
    evidence_against: list[EvidenceItem]
    missing_information: list[str]
    # Version B/C only: one or two sentences, every fact cited as [id]. Code checks the ids and the numbers (D11).
    rationale: str | None = None


class Decision(BaseModel):
    """Filled in by the human investigator only."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    outcome: str | None = None
    contacted: bool | None = None
    final_label: Outcome | None = None


class _AlertCore(BaseModel):
    model_config = _STRICT
    alert_id: str
    payment_id: str
    amount: Decimal
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    payee_name: str  # quoted as data, never interpreted (D7)
    payee_account_masked: str = Field(pattern=r"^\*{4}[A-Z0-9]{4}$")
    payment_reference: str  # quoted as data, never interpreted (D7)
    received_at: datetime
    trigger_reason: str


class UkAlert(_AlertCore):
    rail: Literal[Rail.FPS] = Rail.FPS
    decision_point: Literal["POST_HOLD"] = "POST_HOLD"
    name_check_label: Literal["Confirmation of Payee"] = "Confirmation of Payee"
    received_on_business_day: date
    decide_suspicion_by: date      # end of this business day (FG24/6 para 3.3)
    execute_or_refuse_by: date     # end of this business day (FG24/6 para 3.3)


class SepaAlert(_AlertCore):
    rail: Literal[Rail.SEPA_INST] = Rail.SEPA_INST
    decision_point: Literal["PRE_EXECUTION"] = "PRE_EXECUTION"
    name_check_label: Literal["Verification of Payee"] = "Verification of Payee"
    decide_suspicion_by: None = None
    execute_or_refuse_by: None = None
    deadline_note: Literal["Held before execution; no regulated hold window; not sent until decided"] = SEPA_DEADLINE_NOTE


class ScopeCriterion(BaseModel):
    model_config = _STRICT
    criterion: str
    met: bool
    source_id: str = Field(min_length=1)


class Reimbursement(BaseModel):
    """Facts and arithmetic for the PSR APP reimbursement requirement (D4). Never a verdict."""
    model_config = _STRICT
    in_scope_if_confirmed_app: list[ScopeCriterion]
    scope_note: str
    amount: Decimal
    cap: Decimal
    reimbursable_up_to: Decimal
    excess_note: str
    vulnerability_exception_note: str | None
    sending_psp_share: Decimal
    receiving_psp_share: Decimal
    time_limit_note: str
    sources: list[str]


class UkNextStepItem(BaseModel):
    model_config = _STRICT
    step: UkNextStep
    reason: str = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)


class SepaNextStepItem(BaseModel):
    model_config = _STRICT
    step: SepaNextStep
    reason: str = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)


class _SummaryCore(BaseModel):
    model_config = _STRICT
    # Every id any section may cite: the check results run for this alert, plus the alert's own fields.
    check_result_ids: list[str] = Field(min_length=1)
    evidence: Evidence
    assessment: Assessment
    decision: Decision = Decision()

    def cited_ids(self) -> list[str]:
        ids = [i.source_id for name in Evidence.model_fields for i in getattr(self.evidence, name)]
        ids += [i.source_id for i in self.assessment.evidence_for + self.assessment.evidence_against]
        ids += [sid for step in self.next_steps for sid in step.source_ids]  # type: ignore[attr-defined]
        return ids

    @model_validator(mode="after")
    def _every_citation_resolves(self):
        unknown = sorted(set(self.cited_ids()) - set(self.check_result_ids))
        if unknown:
            raise ValueError(f"cited ids not produced by any check: {unknown}")
        return self


class UkCaseSummary(_SummaryCore):
    rail: Literal[Rail.FPS] = Rail.FPS
    alert: UkAlert
    reimbursement: Reimbursement
    next_steps: list[UkNextStepItem] = Field(min_length=1)

    @model_validator(mode="after")
    def _reimbursement_citations_resolve(self):
        unknown = sorted({c.source_id for c in self.reimbursement.in_scope_if_confirmed_app} - set(self.check_result_ids))
        if unknown:
            raise ValueError(f"reimbursement cites unknown ids: {unknown}")
        return self


class SepaCaseSummary(_SummaryCore):
    rail: Literal[Rail.SEPA_INST] = Rail.SEPA_INST
    alert: SepaAlert
    next_steps: list[SepaNextStepItem] = Field(min_length=1)


CaseSummary = Annotated[Union[UkCaseSummary, SepaCaseSummary], Field(discriminator="rail")]
CASE_SUMMARY = TypeAdapter(CaseSummary)  # validates either rail from JSON or a dict
