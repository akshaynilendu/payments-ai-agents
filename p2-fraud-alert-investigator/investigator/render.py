"""Plain-text view of a case summary for the investigator: a fixed template, no generated wording."""

from investigator.schema import UkCaseSummary

SECTION_TITLES = {"customer_baseline": "Customer baseline", "device_login": "Device and login",
                  "payee_risk": "Payee and receiving account", "prior_reports": "Prior reports",
                  "similar_cases": "Similar past cases", "vulnerability": "Vulnerability"}


def render(summary) -> str:
    a, s = summary.alert, summary.assessment
    lines = [f"ALERT {a.alert_id}  [{a.rail}]  {a.amount:,.2f} {a.currency} to \"{a.payee_name}\" ({a.payee_account_masked})",
             f"  Reference (data): \"{a.payment_reference}\"",
             f"  Trigger: {a.trigger_reason}",
             f"  Received: {a.received_at.isoformat()}  Decision point: {a.decision_point}"]
    if isinstance(summary, UkCaseSummary):
        lines.append(f"  Counts as received: {a.received_on_business_day}; establish suspicion by end of "
                     f"{a.decide_suspicion_by}; execute or refuse by end of {a.execute_or_refuse_by} (FG24/6)")
    else:
        lines.append(f"  Deadline: {a.deadline_note}")
    lines.append(f"  Name check: {a.name_check_label}")

    lines.append("\nEVIDENCE")
    for key, title in SECTION_TITLES.items():
        lines.append(f"  {title}:")
        lines += [f"    - {i.fact}  [{i.source_id}]" for i in getattr(summary.evidence, key)]

    lines.append(f"\nASSESSMENT  leading hypothesis (to test, not a verdict): {s.leading_hypothesis}")
    for label, items in (("For", s.evidence_for), ("Against", s.evidence_against)):
        lines.append(f"  {label}:" + ("" if items else " none"))
        lines += [f"    - {i.fact}  [{i.source_id}]" for i in items]
    lines.append("  Missing:")
    lines += [f"    - {m}" for m in s.missing_information]

    if isinstance(summary, UkCaseSummary):
        r = summary.reimbursement
        lines.append("\nAPP REIMBURSEMENT FACTS (UK)")
        lines += [f"  [{'x' if c.met else ' '}] {c.criterion}  [{c.source_id}]" for c in r.in_scope_if_confirmed_app]
        lines += [f"  {r.scope_note}",
                  f"  Amount {r.amount:,.2f}; cap {r.cap:,.2f}; reimbursable up to {r.reimbursable_up_to:,.2f}",
                  f"  {r.excess_note}" + (f". {r.vulnerability_exception_note}" if r.vulnerability_exception_note else ""),
                  f"  If reimbursed: sending PSP {r.sending_psp_share:,.2f}, receiving PSP {r.receiving_psp_share:,.2f} (50:50)",
                  f"  {r.time_limit_note}"]

    lines.append("\nNEXT STEPS (menu)")
    lines += [f"  {n.step}: {n.reason}  [{', '.join(n.source_ids)}]" for n in summary.next_steps]
    lines.append("\nDECISION (investigator): outcome ___  contacted ___  final label ___")
    return "\n".join(lines)
