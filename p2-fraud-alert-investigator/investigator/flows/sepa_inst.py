"""SEPA Instant: the payment has not been executed yet, so this is a pre-execution decision with no
regulated hold window, Verification of Payee, and no UK reimbursement section (D2)."""

from investigator.data import Alert, Dataset
from investigator.flows.common import alert_fields, evidence, next_steps
from investigator.schema import Hypothesis, SepaAlert, SepaCaseSummary, SepaNextStep as S, SepaNextStepItem

PLAN = {
    Hypothesis.GENUINE: [S.EXECUTE_WITH_NOTE],
    Hypothesis.ACCOUNT_TAKEOVER: [S.CALL_CUSTOMER_REGISTERED_NUMBER],
    Hypothesis.APP_IMPERSONATION: [S.CALL_CUSTOMER_REGISTERED_NUMBER, S.ASK_PAYMENT_PURPOSE],
    Hypothesis.APP_INVESTMENT: [S.ASK_PAYMENT_PURPOSE],
    Hypothesis.APP_PURCHASE: [S.ASK_PAYMENT_PURPOSE],
    Hypothesis.APP_INVOICE_CEO: [S.CALL_CUSTOMER_REGISTERED_NUMBER],
    Hypothesis.INSUFFICIENT_EVIDENCE: [S.CALL_CUSTOMER_REGISTERED_NUMBER, S.ASK_PAYMENT_PURPOSE],
}
# Version A never proposes REJECT_BEFORE_EXECUTION: refusing a customer's payment is the human's call.
REASONS = {
    S.EXECUTE_WITH_NOTE: "Every check is consistent with the customer's normal behaviour",
    S.REJECT_BEFORE_EXECUTION: "The evidence supports refusing the payment before it is sent",
    S.CALL_CUSTOMER_REGISTERED_NUMBER: "Confirm the payment with the customer on the number we hold, not one given in the session",
    S.ASK_PAYMENT_PURPOSE: "The payment purpose in the customer's own words is needed to test the hypothesis",
    S.ESCALATE_MLRO: "Receiving-account evidence (mule pattern, repeated fraud reports or our own fraud cases); the MLRO decides on reporting",
}


def build(ds: Dataset, alert: Alert, result) -> SepaCaseSummary:
    return SepaCaseSummary(
        alert=SepaAlert(**alert_fields(ds, alert)),
        check_result_ids=[f.id for f in result.findings],
        evidence=evidence(result.findings),
        assessment=result.assessment,
        next_steps=next_steps(result, PLAN, REASONS, S.ESCALATE_MLRO, SepaNextStepItem),
    )
