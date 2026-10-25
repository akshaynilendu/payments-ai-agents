"""UK Faster Payments: the payment is already held, so this is a post-hold decision with FG24/6 deadlines
(D3), Confirmation of Payee, and APP reimbursement facts (D4)."""

from decimal import ROUND_HALF_UP, Decimal

from investigator.data import Alert, Dataset
from investigator.deadlines import uk_deadlines
from investigator.flows.common import alert_fields, evidence, next_steps
from investigator.schema import (Hypothesis, Reimbursement, ScopeCriterion, UkAlert, UkCaseSummary,
                                 UkNextStep as S, UkNextStepItem)

CAP = Decimal("85000")  # PSR PS24/7, from 7 October 2024
SOURCES = ["https://www.psr.org.uk/ps24-7-app-scams-reimbursement-confirming-max-level/",
           "https://www.psr.org.uk/media/kwlgyzti/ps23-4-app-scams-policy-statement-dec-2023.pdf"]
IN_SCOPE_SEGMENTS = {"RETAIL", "MICRO_ENTERPRISE"}  # consumers, micro-enterprises (charities not modelled)

PLAN = {
    Hypothesis.GENUINE: [S.RELEASE_WITH_NOTE],
    Hypothesis.ACCOUNT_TAKEOVER: [S.CALL_CUSTOMER_REGISTERED_NUMBER],
    Hypothesis.APP_IMPERSONATION: [S.CALL_CUSTOMER_REGISTERED_NUMBER, S.ASK_PAYMENT_PURPOSE],
    Hypothesis.APP_INVESTMENT: [S.ASK_PAYMENT_PURPOSE, S.REQUEST_INFO_RECEIVING_BANK],
    Hypothesis.APP_PURCHASE: [S.ASK_PAYMENT_PURPOSE, S.REQUEST_INFO_RECEIVING_BANK],
    Hypothesis.APP_INVOICE_CEO: [S.CALL_CUSTOMER_REGISTERED_NUMBER, S.REQUEST_INFO_RECEIVING_BANK],
    Hypothesis.INSUFFICIENT_EVIDENCE: [S.CALL_CUSTOMER_REGISTERED_NUMBER, S.ASK_PAYMENT_PURPOSE],
}
REASONS = {
    S.RELEASE_WITH_NOTE: "Every check is consistent with the customer's normal behaviour",
    S.CALL_CUSTOMER_REGISTERED_NUMBER: "Confirm the payment with the customer on the number we hold, not one given in the session",
    S.ASK_PAYMENT_PURPOSE: "The payment purpose in the customer's own words is needed to test the hypothesis",
    S.REQUEST_INFO_RECEIVING_BANK: "The receiving bank can confirm who holds the account and how it is used",
    S.ESCALATE_MLRO: "Receiving-account evidence (mule pattern, repeated fraud reports or our own fraud cases); the MLRO decides on reporting",
}


def _pounds(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def reimbursement(ds: Dataset, alert: Alert) -> Reimbursement:
    c, p = ds.customers[alert.customer_id], ds.payees[alert.payee_id]
    up_to = _pounds(min(alert.amount, CAP))
    flagged = bool(c.vulnerability_flags) or c.age_band == "80+"
    return Reimbursement(
        in_scope_if_confirmed_app=[
            ScopeCriterion(criterion="Sent by Faster Payments", met=True, source_id=f"alert:{alert.alert_id}:rail"),
            ScopeCriterion(criterion="Payer is a consumer or micro-enterprise", met=c.segment in IN_SCOPE_SEGMENTS,
                           source_id=f"customer_history:{c.customer_id}:segment"),
            ScopeCriterion(criterion="Receiving account is in the UK", met=p.scheme == "UK",
                           source_id=f"payee_risk:{p.payee_id}:scheme"),
            ScopeCriterion(criterion="Receiving account is not controlled by the customer (own-name payee to be checked)",
                           met=p.name != c.display_name, source_id=f"payee_risk:{p.payee_id}:payee_is_payer"),
        ],
        scope_note=("In scope if confirmed as an APP scam and every criterion is met. This is not a verdict. "
                    "An unauthorised payment (for example account takeover) is not an APP scam."),
        amount=alert.amount, cap=CAP, reimbursable_up_to=up_to,
        excess_note="Up to £100 excess may apply",
        vulnerability_exception_note=(
            "Customer has a vulnerability indicator: the excess does not apply if the vulnerability had a "
            "material impact on their ability to protect themselves (assessed case by case)") if flagged else None,
        sending_psp_share=_pounds(up_to / 2), receiving_psp_share=_pounds(up_to / 2),
        time_limit_note="Claims made more than 13 months after the last payment are out of scope",
        sources=SOURCES,
    )


def build(ds: Dataset, alert: Alert, result) -> UkCaseSummary:
    d = uk_deadlines(alert.received_at)
    return UkCaseSummary(
        alert=UkAlert(**alert_fields(ds, alert), received_on_business_day=d.received_on,
                      decide_suspicion_by=d.decide_suspicion_by, execute_or_refuse_by=d.execute_or_refuse_by),
        check_result_ids=[f.id for f in result.findings],
        evidence=evidence(result.findings),
        assessment=result.assessment,
        reimbursement=reimbursement(ds, alert),
        next_steps=next_steps(result, PLAN, REASONS, S.ESCALATE_MLRO, UkNextStepItem),
    )
