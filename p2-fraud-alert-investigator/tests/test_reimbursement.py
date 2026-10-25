from decimal import Decimal

from investigator.data import Alert
from investigator.flows.uk_fps import reimbursement
from investigator.schema import UkCaseSummary


def uk(summaries):
    return [s for s in summaries.values() if isinstance(s, UkCaseSummary)]


def test_cap_and_fifty_fifty_split(summaries):
    for s in uk(summaries):
        r = s.reimbursement
        assert r.cap == Decimal("85000")
        assert r.reimbursable_up_to == min(r.amount, r.cap)
        assert r.sending_psp_share == r.receiving_psp_share
        assert abs(r.sending_psp_share + r.receiving_psp_share - r.reimbursable_up_to) <= Decimal("0.01")
        assert r.excess_note == "Up to £100 excess may apply"


def test_amount_above_cap_is_limited(ds):
    a = next(x for x in ds.alerts if x.rail == "FPS")
    big = Alert(**{**a.model_dump(), "amount": Decimal("120000.00")})
    r = reimbursement(ds, big)
    assert r.reimbursable_up_to == Decimal("85000.00") and r.receiving_psp_share == Decimal("42500.00")


def test_vulnerability_note_only_when_flagged(ds, summaries):
    for s in uk(summaries):
        c = ds.customers[next(a for a in ds.alerts if a.alert_id == s.alert.alert_id).customer_id]
        flagged = bool(c.vulnerability_flags) or c.age_band == "80+"
        assert (s.reimbursement.vulnerability_exception_note is not None) == flagged


def test_own_name_payee_is_flagged_as_not_met(summaries, gold):
    aid = next(k for k, g in gold.items() if g["hard_kind"] == "novel_own_name_exchange")
    crit = {c.criterion: c.met for c in summaries[aid].reimbursement.in_scope_if_confirmed_app}
    assert crit["Receiving account is not controlled by the customer (own-name payee to be checked)"] is False
