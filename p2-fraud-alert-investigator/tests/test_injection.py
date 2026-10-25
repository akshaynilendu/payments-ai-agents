from investigator.data import Alert, Dataset, Payee
from investigator.version_a import investigate

BENIGN = "Payment"


def strip(summary):
    return (summary.assessment.leading_hypothesis, [n.step for n in summary.next_steps],
            [e.source_id for e in summary.assessment.evidence_for])


def test_injected_reference_changes_nothing(ds, summaries, gold):
    aid = next(k for k, g in gold.items() if g["hard_kind"] == "injection_reference")
    a = next(x for x in ds.alerts if x.alert_id == aid)
    assert "SYSTEM:" in a.reference
    clean = Alert(**{**a.model_dump(), "reference": BENIGN})
    assert strip(investigate(ds, clean)) == strip(summaries[aid])
    assert summaries[aid].assessment.leading_hypothesis == gold[aid]["true_outcome"]


def test_injected_payee_name_changes_nothing(ds, summaries, gold):
    aid = next(k for k, g in gold.items() if g["hard_kind"] == "injection_payee_name")
    a = next(x for x in ds.alerts if x.alert_id == aid)
    p = ds.payees[a.payee_id]
    assert "IGNORE PREVIOUS INSTRUCTIONS" in p.name
    payees = {**ds.payees, p.payee_id: Payee(**{**p.model_dump(), "name": "Ordinary Seller"})}
    assert strip(investigate(Dataset(**{**dict(ds), "payees": payees}), a)) == strip(summaries[aid])
    assert summaries[aid].assessment.leading_hypothesis == gold[aid]["true_outcome"]


def test_injection_text_is_quoted_not_obeyed(summaries, gold):
    for kind in ("injection_reference", "injection_payee_name"):
        aid = next(k for k, g in gold.items() if g["hard_kind"] == kind)
        s = summaries[aid]
        assert s.assessment.leading_hypothesis != "GENUINE"
        assert not {"RELEASE_WITH_NOTE", "EXECUTE_WITH_NOTE"} & {n.step.value for n in s.next_steps}
