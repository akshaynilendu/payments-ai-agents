from collections import Counter

from investigator.checks import run_checks
from investigator.data import Customer, Dataset
from investigator.schema import Hypothesis
from investigator.version_a import RULES, assess, investigate


def test_runs_on_all_40(ds, summaries):
    assert len(ds.alerts) == 40 and len(summaries) == 40
    assert Counter(a.rail for a in ds.alerts) == {"FPS": 24, "SEPA_INST": 16}


def test_priority_order_and_conflicts_go_to_against():
    # Hand-built findings where ATO and impersonation both fire: ATO wins (higher priority).
    from investigator.checks import Finding
    f = [Finding("x:1:a", "device_login", "new device", frozenset({"NEW_DEVICE"})),
         Finding("x:1:b", "device_login", "sim swap", frozenset({"SIM_SWAP_72H"})),
         Finding("x:1:c", "device_login", "on call", frozenset({"ON_CALL"})),
         Finding("x:1:d", "customer_baseline", "new payee", frozenset({"NEW_PAYEE"})),
         Finding("x:1:e", "customer_baseline", "3x", frozenset({"AMOUNT_3X"}))]
    a = assess(f).assessment
    assert a.leading_hypothesis == Hypothesis.ACCOUNT_TAKEOVER
    assert {e.source_id for e in a.evidence_for} == {"x:1:a", "x:1:b"}
    assert {e.source_id for e in a.evidence_against} == {"x:1:c", "x:1:d", "x:1:e"}


def test_insufficient_evidence_only_when_no_rule_fires(ds):
    for a in ds.alerts:
        findings = run_checks(ds, a)
        signals = frozenset(s for f in findings for s in f.signals)
        none_fire = not any(r.fires(signals) for r in RULES)
        assert (assess(findings).assessment.leading_hypothesis == Hypothesis.INSUFFICIENT_EVIDENCE) == none_fire


def test_age_band_never_changes_the_hypothesis(ds, summaries):
    for band in ["18-29", "30-44", "45-64", "65-79", "80+"]:
        customers = {k: Customer(**{**c.model_dump(), "age_band": band}) for k, c in ds.customers.items()}
        changed = Dataset(**{**dict(ds), "customers": customers})
        for a in ds.alerts:
            s = investigate(changed, a)
            assert s.assessment.leading_hypothesis == summaries[a.alert_id].assessment.leading_hypothesis
            assert [n.step for n in s.next_steps] == [n.step for n in summaries[a.alert_id].next_steps]


def test_age_band_produces_no_signal(ds):
    for a in ds.alerts:
        vuln = [f for f in run_checks(ds, a) if f.section == "vulnerability"]
        assert vuln and all(not f.signals for f in vuln)


def _textbook(g):
    return g["difficulty"] == "familiar" and not g.get("variant")


def test_textbook_cases_are_right(summaries, gold):
    # The rules were written for the textbook profiles, so they must get those right: a regression guard,
    # not a score. The score comes from scripts/score_version_a.py, over all slices (D10).
    for k, g in gold.items():
        if _textbook(g):
            assert summaries[k].assessment.leading_hypothesis == g["true_outcome"], k


def test_suggested_steps_are_acceptable_on_textbook_cases(summaries, gold):
    for k, g in gold.items():
        if _textbook(g):
            assert {n.step.value for n in summaries[k].next_steps} <= set(g["acceptable_next_steps"]), k


def test_realistic_variants_present(gold):
    # D10: 11 ordinary cases that do not match the textbook profile, on both rails, both directions.
    variants = {k: g for k, g in gold.items() if g.get("variant")}
    assert len(variants) == 11
    assert {g["rail"] for g in variants.values()} == {"FPS", "SEPA_INST"}
    assert any(g["true_outcome"] == "GENUINE" for g in variants.values())
    assert any(g["true_outcome"] != "GENUINE" for g in variants.values())
    assert all(g["difficulty"] == "familiar" for g in variants.values())


def test_version_a_never_calls_a_fraud_case_genuine(summaries, gold):
    # The costliest error is steering toward releasing fraud. Version A may say "insufficient evidence",
    # but on this data it must never label a fraud case GENUINE.
    for k, g in gold.items():
        if g["true_outcome"] != "GENUINE":
            assert summaries[k].assessment.leading_hypothesis.value != "GENUINE", k
