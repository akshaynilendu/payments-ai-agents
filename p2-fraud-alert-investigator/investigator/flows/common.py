"""Pieces both flows share: grouping findings into evidence sections and building menu next steps."""

import re

from investigator.checks import Finding
from investigator.data import Alert, Dataset
from investigator.schema import Evidence, EvidenceItem

SECTIONS = ("customer_baseline", "device_login", "payee_risk", "prior_reports", "similar_cases", "vulnerability")


def evidence(findings: list[Finding]) -> Evidence:
    return Evidence(**{s: [EvidenceItem(fact=f.fact, source_id=f.id) for f in findings if f.section == s]
                       for s in SECTIONS})


def masked(account: str) -> str:
    # Investigators need enough to tell accounts apart, not the full number.
    return "****" + re.sub(r"[^A-Z0-9]", "", account.upper())[-4:]


def alert_fields(ds: Dataset, alert: Alert) -> dict:
    payee = ds.payees[alert.payee_id]
    return dict(alert_id=alert.alert_id, payment_id=alert.payment_id, amount=alert.amount, currency=alert.currency,
                payee_name=payee.name, payee_account_masked=masked(payee.account),
                payment_reference=alert.reference, received_at=alert.received_at,
                trigger_reason=alert.trigger_reason)


def next_steps(result, plan: dict, reasons: dict, mlro_step, item_cls) -> list:
    """Menu steps for the leading hypothesis, each citing the evidence that led to it."""
    hypothesis = result.assessment.leading_hypothesis
    trigger = next(f.id for f in result.findings if f.id.endswith(":trigger_reason"))
    cited = [e.source_id for e in result.assessment.evidence_for] or [trigger]
    steps = [item_cls(step=s, reason=reasons[s], source_ids=cited) for s in plan[hypothesis]]
    if result.escalate_ids and mlro_step not in plan[hypothesis]:
        steps.append(item_cls(step=mlro_step, reason=reasons[mlro_step], source_ids=result.escalate_ids))
    return steps

