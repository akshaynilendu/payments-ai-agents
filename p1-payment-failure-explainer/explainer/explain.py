"""Build the prompt and the output schema for the AI explanation (D11)."""

from typing import Sequence

from explainer.codes import (WITHHELD_REASON_CODES, Rail, ReasonCode, Route, SourceType, Stage,
                             policy_customer_message, route_descriptions)
from explainer.retrieve import RAIL_LABELS, Retrieved

FIELDS = ("what_happened", "next_step", "customer_message", "citations")

# Structured output: the model can only return these four fields. There is no route field,
# so the AI has no way to change the route (D2, D11).
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "what_happened": {"type": "string", "description": "What the code means for this payment, for an operations agent."},
        "next_step": {"type": "string", "description": "A recommended next step for the operations agent."},
        "customer_message": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "description": "A neutral draft for the customer, or null.",
        },
        "citations": {"type": "array", "items": {"type": "string"}, "description": "IDs of the passages used."},
    },
    "required": list(FIELDS),
    "additionalProperties": False,
}

STAGE_LABELS = {
    Stage.REJECT: "rejected before settlement: no money moved",
    Stage.RETURN: "returned after settlement: the money moved and came back (includes SDD refunds)",
    Stage.RECALL: "a recall: the sender is asking for settled money back",
    Stage.RECALL_ANSWER: "an answer to a recall",
    Stage.UNKNOWN: "unknown: the message does not say whether money moved",
}

# Positive rules (what to do, not what to avoid). They open the prompt and close it, so they stay in view.
RULES = """You explain failed payments to a payments operations team.

Rules:
1. Use only the case facts and the passages in this message. When they do not cover something, leave it out.
2. Put the ID of every passage you used in "citations". Cite at least one passage.
3. "what_happened": one to three sentences for an operations agent on what this code means for this payment.
4. "next_step": a recommendation for the operations agent; a person decides and acts. When the advice comes from a passage labelled "Team guidance", say that it is team guidance.
5. "customer_message": a short, neutral draft for the customer that says what happened and what they can do. Describe only facts that are already true; keep dates, durations and outcomes such as refunds or credits out of it.
6. The route comes from the bank's routing table. Treat it as fixed context and keep your advice consistent with it.
7. Follow every passage marked MANDATORY.
8. Keep "what_happened" and "next_step" under 600 characters each and "customer_message" under 400.
9. When the route is COMPLIANCE, write "what_happened" for the compliance team, return "next_step" as an empty string and "customer_message" as null: the bank's policy sets both.
10. When the case facts say the customer message is set by bank policy, return "customer_message" as null.
11. Keep "customer_message" consistent with "next_step": it never asks the customer to do something the next step rules out."""


SOURCE_LABELS = {
    SourceType.SCHEME_RULE: "Scheme rule",
    SourceType.REGULATION: "Regulation",
    SourceType.TEAM_RUNBOOK: "Team guidance",
}


def source_label(source_type: SourceType) -> str:
    # The label comes from data, not from the AI's wording (D7).
    return SOURCE_LABELS[source_type]


# Which bank we are decides who "the customer" is; without it a draft can address the wrong party (D16).
PERSPECTIVE = {
    Rail.SEPA_INSTANT: "We are the payer's bank (the debtor's bank). The customer is the payer who sent this "
                       "payment; the other party is the beneficiary.",
    Rail.RTP: "We are the payer's bank (the sending bank). The customer is the payer who sent this payment; "
              "the other party is the receiver.",
    Rail.SEPA_DD: "We are the creditor's bank. The customer is the creditor who collected this direct debit; "
                  "the other party is the debtor (the payer).",
    Rail.UNKNOWN: "The rail is unknown, so which bank we are, and who the customer is, is not known.",
}


def case_facts(code: ReasonCode, rail: Rail, stage: Stage, route: Route) -> list[str]:
    """The case facts the AI sees. The eval judge gets exactly these too, so both judge the same case (D13)."""
    return [
        f"Reason code: {code.code} ({code.name})",
        f"Baseline meaning: {code.meaning}",
        f"Rail: {RAIL_LABELS[rail]}",
        f"Our role: {PERSPECTIVE[rail]}",
        f"Stage: {stage.value} ({STAGE_LABELS[stage]})",
        f"Route (fixed by the routing table): {route.value}: {route_descriptions()[route]}",
    ] + ([
        "Reason withheld: the other bank gave no reason on purpose. The customer message says only that no "
        "reason was given, without suggesting possible causes.",
    ] if code.code in WITHHELD_REASON_CODES else []) + ([
        "Customer message: set by bank policy.",
    ] if policy_customer_message(code.code, rail) else [])


def build_prompt(code: ReasonCode, rail: Rail, stage: Stage, route: Route, passages: Sequence[Retrieved],
                 failures: Sequence[str] = ()) -> tuple[str, str]:
    """Return (system, user). Only code-level facts go in: no amounts, IDs, parties or free text (D11)."""
    facts = "\n".join(["Case facts:"] + [f"- {fact}" for fact in case_facts(code, rail, stage, route)])
    blocks = []
    for item in passages:
        p = item.passage
        tags = source_label(p.source_type) + (", MANDATORY" if p.mandatory else "")
        blocks.append(f"[{p.id}] ({tags})\n{p.text}")
    user = f"{facts}\n\nPassages:\n\n" + "\n\n".join(blocks) + f"\n\n{RULES}"
    if failures:
        user += ("\n\nYour previous answer failed these checks: " + "; ".join(failures)
                 + ". Write a new answer that passes them.")
    return RULES, user
