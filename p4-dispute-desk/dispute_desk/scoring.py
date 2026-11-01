"""Scores one version's decisions against the answer key (gold/gold.json).

Only this file and the eval script read gold. Per dispute:
  right            outcome and priority both match
  safe_not_ideal   asked a person on a case the key decides, and the deadline is not tomorrow
  wrong            anything else, including asking a person when the reply is due tomorrow

Money recovered after fees counts only a right fight: amount − dispute fee − fight cost.
A right acceptance books amount + fee (the fee is kept either way). Already refunded recovers 0.
"""

import json
from pathlib import Path

from .schema import Decision
from .world import World

ROOT = Path(__file__).resolve().parent.parent


def load_gold():
    return {row["id"]: row for row in json.loads((ROOT / "gold" / "gold.json").read_text(encoding="utf-8"))}


def score_case(gold: dict, decision: Decision, world: World) -> dict:
    dispute = world.dispute(gold["id"])
    got = decision.outcome.value
    priority = decision.priority.value
    missed = priority == "LATE" or (gold["priority"] == "SUBMIT_TODAY" and priority != "SUBMIT_TODAY")
    if got == gold["outcome"] and priority == gold["priority"]:
        verdict = "right"
    elif got == "ASK_HUMAN" and gold["outcome"] != "ASK_HUMAN" and not missed:
        verdict = "safe_not_ideal"
    else:
        verdict = "wrong"

    currency = dispute["currency"]
    amount = float(dispute["amount"])
    fee = world.dispute_fee(currency)
    fight = world.fight_cost(currency)
    recovered = accepted = 0.0
    if verdict == "right" and got == "FIGHT":
        recovered = amount - fee - fight
    elif verdict == "right" and got == "ACCEPT":
        accepted = amount + fee
    return {
        "dispute_id": gold["id"],
        "slice": gold["slice"],
        "gold": gold["outcome"],
        "gold_priority": gold["priority"],
        "got": got,
        "priority": priority,
        "verdict": verdict,
        "currency": currency,
        "recovered": round(recovered, 2),
        "accepted_loss": round(accepted, 2),
        "missed_deadline": missed,
        "reasons": [item.code for item in decision.reasons],
    }
