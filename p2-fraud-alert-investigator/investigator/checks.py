"""The five read-only checks (shared by both rails). Each returns findings with a stable id
"{check}:{subject}:{field}", a plain fact for the human, and the signal tags the rules read.

Rules read only the signal tags, never the free text: payee names and references are quoted, not
interpreted (D7). Age band produces no signal at all; it only appears as a vulnerability fact (D6).
"""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from investigator.data import Alert, Dataset
from investigator.schema import Outcome, Rail

NAME_CHECK_LABEL = {Rail.FPS: "Confirmation of Payee", Rail.SEPA_INST: "Verification of Payee"}
LOCAL_TZ = {Rail.FPS: ZoneInfo("Europe/London"), Rail.SEPA_INST: ZoneInfo("Europe/Brussels")}

# Thresholds in one place, so a reviewer can see exactly what "young" or "large" means.
LARGE_MULTIPLE = Decimal(3)          # amount >= 3x the customer's usual
MODEST_AMOUNT = Decimal(2500)        # purchase scams are usually small
SIM_SWAP_WINDOW = timedelta(hours=72)
YOUNG_ACCOUNT_DAYS = 90
ESTABLISHED_ACCOUNT_DAYS = 180
MULE_ACCOUNT_DAYS = 7
MANY_INBOUND = 10
FAST_MONEY_OUT_MINUTES = 60
SERIES_MIN_PAYMENTS = 3              # including the held one
SIMILARITY_MIN = 0.5
SIMILAR_TOP_N = 3
VULNERABILITY_AGE_BANDS = {"80+"}    # vulnerability only, never a fraud signal (D6)

# Signals that describe risk; similar_cases compares alerts on these only.
RISK_SIGNALS = frozenset({
    "NEW_DEVICE", "SIM_SWAP_72H", "REMOTE_ACCESS", "ON_CALL", "TYPING_HESITATION", "NEW_PAYEE",
    "AMOUNT_3X", "OUT_OF_HOURS", "KNOWN_NAME_NEW_ACCOUNT", "NAME_NO_MATCH", "NAME_CLOSE_MATCH",
    "YOUNG_ACCOUNT", "MANY_INBOUND", "FAST_MONEY_OUT", "PRIOR_REPORTS", "GROWING_SERIES",
})


@dataclass(frozen=True)
class Finding:
    id: str
    section: str  # which evidence section of the summary it belongs to
    fact: str
    signals: frozenset[str] = frozenset()


def _money(amount: Decimal, currency: str) -> str:
    return f"{amount:,.2f} {currency}"


def alert_facts(alert: Alert, payee_name: str) -> list[Finding]:
    """The alert's own fields, so next steps can cite them. Quoted, never parsed (D7)."""
    a = f"alert:{alert.alert_id}"
    return [
        Finding(f"{a}:rail", "alert", f"Rail: {alert.rail}"),
        Finding(f"{a}:amount", "alert", f"Amount: {_money(alert.amount, alert.currency)}"),
        Finding(f"{a}:trigger_reason", "alert", f"Alert trigger: {alert.trigger_reason}"),
        Finding(f"{a}:reference", "alert", f'Payment reference (quoted as data): "{alert.reference}"'),
        Finding(f"{a}:payee_name", "alert", f'Payee name (quoted as data): "{payee_name}"'),
    ]


def customer_history(ds: Dataset, alert: Alert) -> list[Finding]:
    c = ds.customers[alert.customer_id]
    cid = f"customer_history:{c.customer_id}"
    out = [Finding(f"{cid}:segment", "customer_baseline", f"Customer segment: {c.segment}",
                   frozenset() if c.segment == "RETAIL" else frozenset({"BUSINESS"}))]

    ratio = alert.amount / c.usual_amount
    sig = {"AMOUNT_3X" if ratio >= LARGE_MULTIPLE else "AMOUNT_WITHIN_3X"}
    if alert.amount <= MODEST_AMOUNT:
        sig.add("MODEST_AMOUNT")
    out.append(Finding(f"{cid}:amount_vs_usual", "customer_baseline",
                       f"Amount is {ratio:.1f}x the customer's usual payment of {_money(c.usual_amount, c.currency)}",
                       frozenset(sig)))

    prior = alert.recent_payments_to_payee
    amounts = [p.amount for p in sorted(prior, key=lambda p: p.paid_at)] + [alert.amount]
    if alert.payee_id in c.usual_payee_ids:
        fact, sig = "Payee is one of the customer's usual payees", {"USUAL_PAYEE"}
    elif not prior:
        fact, sig = "First payment to this payee", {"NEW_PAYEE"}
    else:
        growing = len(amounts) >= SERIES_MIN_PAYMENTS and all(x < y for x, y in zip(amounts, amounts[1:]))
        shown = ", ".join(f"{x:,.2f}" for x in amounts)
        fact = f"{len(prior)} earlier payment(s) to this payee in the last 90 days; amounts in order: {shown}"
        sig = {"GROWING_SERIES"} if growing else set()
    out.append(Finding(f"{cid}:payee_history", "customer_baseline", fact, frozenset(sig)))

    local = alert.received_at.astimezone(LOCAL_TZ[alert.rail])
    start, end = c.usual_hours
    usual = start <= local.hour < end
    out.append(Finding(f"{cid}:time_of_day", "customer_baseline",
                       f"Sent at {local:%H:%M} local; usual hours {start:02d}:00-{end:02d}:00",
                       frozenset() if usual else frozenset({"OUT_OF_HOURS"})))

    notes = list(c.vulnerability_flags)
    if c.age_band in VULNERABILITY_AGE_BANDS:
        notes.append(f"age band {c.age_band}")
    fact = ("Vulnerability indicators: " + ", ".join(notes)) if notes else "No vulnerability indicators recorded"
    out.append(Finding(f"{cid}:vulnerability", "vulnerability", fact))  # no signals, ever (D6)
    return out


def device_login(ds: Dataset, alert: Alert) -> list[Finding]:
    s = ds.sessions[alert.session_id]
    sid = f"device_login:{s.session_id}"
    swap_recent = s.sim_swap_at is not None and timedelta(0) <= s.started_at - s.sim_swap_at <= SIM_SWAP_WINDOW
    if s.sim_swap_at is None:
        swap_fact = "No SIM swap recorded"
    else:
        hours = (s.started_at - s.sim_swap_at).total_seconds() / 3600
        swap_fact = f"SIM swap {hours:.0f} hours before this session"

    def flag(field: str, on: bool, yes: str, no: str, signal: str) -> Finding:
        return Finding(f"{sid}:{field}", "device_login", yes if on else no,
                       frozenset({signal}) if on else frozenset())

    return [
        flag("new_device", s.new_device, f"New device ({s.device_id}) first seen this session",
             f"Known device ({s.device_id})", "NEW_DEVICE"),
        flag("sim_swap", swap_recent, swap_fact, swap_fact, "SIM_SWAP_72H"),
        flag("remote_access", s.remote_access_tool, "Remote-access software detected during the session",
             "No remote-access software detected", "REMOTE_ACCESS"),
        flag("on_call", s.on_call_during_session, "Customer was on a phone call during the session",
             "No active phone call during the session", "ON_CALL"),
        flag("typing", s.typing_hesitation, "Hesitant typing pattern on the payment screen",
             "Normal typing pattern", "TYPING_HESITATION"),
    ]


def payee_risk(ds: Dataset, alert: Alert) -> list[Finding]:
    """Mandatory for every alert: the receiving account is where mule evidence lives."""
    p = ds.payees[alert.payee_id]
    c = ds.customers[alert.customer_id]
    pid = f"payee_risk:{p.payee_id}"
    label = NAME_CHECK_LABEL[alert.rail]
    out = [Finding(f"{pid}:name_check", "payee_risk", f"{label} result: {p.name_check}",
                   frozenset({f"NAME_{p.name_check}"}))]

    age_sig = set()
    if p.account_age_days < YOUNG_ACCOUNT_DAYS:
        age_sig.add("YOUNG_ACCOUNT")
    if p.account_age_days >= ESTABLISHED_ACCOUNT_DAYS:
        age_sig.add("ESTABLISHED_ACCOUNT")
    if p.account_age_days < MULE_ACCOUNT_DAYS and p.inbound_unrelated_payers_30d >= MANY_INBOUND:
        age_sig.add("MULE_PATTERN")
    out.append(Finding(f"{pid}:account_age", "payee_risk",
                       f"Receiving account opened {p.account_age_days} days ago", frozenset(age_sig)))
    out.append(Finding(f"{pid}:inbound_payers", "payee_risk",
                       f"{p.inbound_unrelated_payers_30d} unrelated payers sent money to this account in 30 days",
                       frozenset({"MANY_INBOUND"}) if p.inbound_unrelated_payers_30d >= MANY_INBOUND else frozenset()))
    out.append(Finding(f"{pid}:money_out_speed", "payee_risk",
                       f"Money typically leaves this account {p.money_out_median_minutes} minutes after arriving (median)",
                       frozenset({"FAST_MONEY_OUT"}) if p.money_out_median_minutes <= FAST_MONEY_OUT_MINUTES else frozenset()))
    out.append(Finding(f"{pid}:scheme", "payee_risk", f"Receiving account is held in the {p.scheme} scheme"))

    # Exact name equality is structural matching, not reading the name for meaning (D7).
    usual_names = {ds.payees[u].name: ds.payees[u].account for u in c.usual_payee_ids}
    changed = p.name in usual_names and usual_names[p.name] != p.account and p.payee_id not in c.usual_payee_ids
    out.append(Finding(f"{pid}:known_name_new_account", "payee_risk",
                       "Same name as a usual payee, but a different account" if changed
                       else "No usual payee with this name and a different account",
                       frozenset({"KNOWN_NAME_NEW_ACCOUNT"}) if changed else frozenset()))
    own = p.name == c.display_name
    out.append(Finding(f"{pid}:payee_is_payer", "payee_risk",
                       "Payee name is the customer's own name" if own else "Payee name differs from the customer's name",
                       frozenset({"OWN_NAME_PAYEE"}) if own else frozenset()))
    return out


def prior_reports(ds: Dataset, alert: Alert) -> list[Finding]:
    p = ds.payees[alert.payee_id]
    pid = f"prior_reports:{p.payee_id}"
    sig = {"PRIOR_REPORTS"} if p.prior_fraud_reports else {"NO_REPORTS"}
    if p.prior_fraud_reports >= 2:
        sig.add("MANY_REPORTS")
    # Only cases closed before this alert: anything later would be hindsight (D8).
    ours = [pc for pc in ds.past_cases
            if pc.receiving_account == p.account and pc.closed_at < alert.received_at and pc.outcome != Outcome.GENUINE]
    fact = (f"{len(ours)} of our closed fraud cases paid this account: "
            + ", ".join(f"{pc.case_id} ({pc.outcome})" for pc in ours)) if ours \
        else "None of our closed fraud cases paid this account"
    return [
        Finding(f"{pid}:external_reports", "prior_reports",
                f"{p.prior_fraud_reports} fraud report(s) received about this account", frozenset(sig)),
        Finding(f"{pid}:past_cases_on_account", "prior_reports", fact,
                frozenset({"PAST_FRAUD_ON_ACCOUNT"}) if ours else frozenset()),
    ]


def similar_cases(ds: Dataset, alert: Alert, signals: frozenset[str]) -> list[Finding]:
    mine = signals & RISK_SIGNALS
    scored = []
    for pc in ds.past_cases:
        if pc.closed_at >= alert.received_at:
            continue  # hindsight (D8)
        theirs = frozenset(pc.signals) & RISK_SIGNALS
        union = mine | theirs
        score = len(mine & theirs) / len(union) if union else 0.0
        if score >= SIMILARITY_MIN:
            scored.append((score, pc.closed_at, pc))
    scored.sort(key=lambda t: (-t[0], -t[1].timestamp()))
    top = scored[:SIMILAR_TOP_N]
    if top:
        fact = "Most similar closed cases: " + "; ".join(f"{pc.case_id} {pc.outcome} (similarity {s:.2f})" for s, _, pc in top)
    else:
        fact = f"No closed case with similarity >= {SIMILARITY_MIN}"
    return [Finding(f"similar_cases:{alert.alert_id}:top_matches", "similar_cases", fact)]


def run_checks(ds: Dataset, alert: Alert) -> list[Finding]:
    payee = ds.payees[alert.payee_id]  # a missing payee must fail loudly: payee_risk is mandatory
    findings = alert_facts(alert, payee.name)
    findings += customer_history(ds, alert) + device_login(ds, alert) + payee_risk(ds, alert) + prior_reports(ds, alert)
    findings += similar_cases(ds, alert, signals_of(findings))
    return findings


def signals_of(findings: list[Finding]) -> frozenset[str]:
    return frozenset(s for f in findings for s in f.signals)
