"""Version A: code-only rules, template wording, menu next steps. The baseline every later version must beat.

Rules run in a fixed priority order (D5): the highest-priority rule that fires sets the leading hypothesis;
the evidence of every other rule that fires goes to evidence_against. INSUFFICIENT_EVIDENCE only when no
rule fires. Rules read signal tags only, never names or references (D7), and age band has no tag (D6).
"""

from dataclasses import dataclass

from investigator.checks import Finding, run_checks, signals_of
from investigator.data import Alert, Dataset
from investigator.schema import Assessment, EvidenceItem, Hypothesis


@dataclass(frozen=True)
class Rule:
    hypothesis: Hypothesis
    requires: frozenset[str]
    forbids: frozenset[str] = frozenset()

    def fires(self, signals: frozenset[str]) -> bool:
        return self.requires <= signals and not (self.forbids & signals)


RULES = [  # priority order: first is highest
    Rule(Hypothesis.ACCOUNT_TAKEOVER, frozenset({"NEW_DEVICE", "SIM_SWAP_72H"})),
    Rule(Hypothesis.APP_IMPERSONATION, frozenset({"ON_CALL", "NEW_PAYEE", "AMOUNT_3X"})),
    Rule(Hypothesis.APP_INVOICE_CEO, frozenset({"BUSINESS", "KNOWN_NAME_NEW_ACCOUNT"})),
    Rule(Hypothesis.APP_INVESTMENT, frozenset({"GROWING_SERIES", "MANY_INBOUND"})),
    Rule(Hypothesis.APP_PURCHASE, frozenset({"NEW_PAYEE", "MODEST_AMOUNT", "YOUNG_ACCOUNT", "PRIOR_REPORTS"})),
    Rule(Hypothesis.GENUINE, frozenset({"NAME_MATCH", "ESTABLISHED_ACCOUNT", "NO_REPORTS", "AMOUNT_WITHIN_3X"}),
         forbids=frozenset({"NEW_DEVICE", "SIM_SWAP_72H", "REMOTE_ACCESS", "PAST_FRAUD_ON_ACCOUNT"})),
]

# Receiving-account (mule) evidence supports a fraud hypothesis but never decides one.
SUPPORTING = frozenset({"MULE_PATTERN", "FAST_MONEY_OUT", "MANY_INBOUND", "YOUNG_ACCOUNT", "NAME_NO_MATCH",
                        "NAME_CLOSE_MATCH", "PRIOR_REPORTS", "PAST_FRAUD_ON_ACCOUNT", "TYPING_HESITATION"})
# A usual payee is the one fact that cuts against every fraud hypothesis.
COUNTER_TO_FRAUD = frozenset({"USUAL_PAYEE"})
MLRO_TRIGGERS = frozenset({"MULE_PATTERN", "MANY_REPORTS", "PAST_FRAUD_ON_ACCOUNT"})

MISSING = {
    Hypothesis.GENUINE: ["Customer confirmation of the payment purpose, if policy requires it"],
    Hypothesis.ACCOUNT_TAKEOVER: ["Whether the customer requested the SIM swap",
                                  "Whether the customer recognises the new device and this payment"],
    Hypothesis.APP_IMPERSONATION: ["Who the customer was speaking to during the session",
                                   "The payment purpose in the customer's own words"],
    Hypothesis.APP_INVESTMENT: ["How the customer found the investment",
                                "Whether the customer can withdraw from it"],
    Hypothesis.APP_PURCHASE: ["What is being bought and how the seller was found",
                              "Whether the customer has seen the goods"],
    Hypothesis.APP_INVOICE_CEO: ["Whether the supplier confirmed the new account through a known contact"],
    Hypothesis.INSUFFICIENT_EVIDENCE: ["The payment purpose in the customer's own words",
                                       "Whether the customer is acting under anyone's instruction"],
}


@dataclass(frozen=True)
class Result:
    findings: list[Finding]
    assessment: Assessment
    escalate_ids: list[str]  # non-empty means the flow adds ESCALATE_MLRO


def _items(findings: list[Finding], wanted: frozenset[str], skip: set[str] = frozenset()) -> list[EvidenceItem]:
    return [EvidenceItem(fact=f.fact, source_id=f.id) for f in findings
            if f.signals & wanted and f.id not in skip]


def assess(findings: list[Finding]) -> Result:
    signals = signals_of(findings)
    fired = [r for r in RULES if r.fires(signals)]
    if not fired:
        assessment = Assessment(leading_hypothesis=Hypothesis.INSUFFICIENT_EVIDENCE, evidence_for=[],
                                evidence_against=[], missing_information=MISSING[Hypothesis.INSUFFICIENT_EVIDENCE])
    else:
        lead, others = fired[0], fired[1:]
        wanted = lead.requires | (SUPPORTING if lead.hypothesis != Hypothesis.GENUINE else frozenset())
        evidence_for = _items(findings, wanted)
        used = {e.source_id for e in evidence_for}
        against_tags = frozenset().union(*(r.requires for r in others))
        if lead.hypothesis != Hypothesis.GENUINE:
            against_tags |= COUNTER_TO_FRAUD
        assessment = Assessment(leading_hypothesis=lead.hypothesis, evidence_for=evidence_for,
                                evidence_against=_items(findings, against_tags, used),
                                missing_information=MISSING[lead.hypothesis])
    escalate = [f.id for f in findings if f.signals & MLRO_TRIGGERS]
    return Result(findings, assessment, escalate)


def investigate(ds: Dataset, alert: Alert):
    from investigator.flows import flow_for  # flows import this module's types; import late to avoid a cycle
    return flow_for(alert.rail).build(ds, alert, assess(run_checks(ds, alert)))
