"""Version A: code only. Keyword and field rules propose an outcome.

This reads the reason code, whether this order has a refund, the amount, and a
few words in the cardholder message. It was not tuned on the traps. The engine
is a guardrail: it can stop a fight, and it will not turn an ACCEPT into one.
"""

from .schema import Outcome, Proposal
from .world import World


def propose(world: World, dispute_id: str) -> Proposal:
    dispute = world.dispute(dispute_id)
    text = dispute["cardholder_message"].lower()
    paid = world.refund_sum(dispute["order_id"])
    evidence = [f"order:{dispute['order_id']}"]
    evidence += [f"shipment:{row['shipment_id']}" for row in world.shipments_for(dispute["order_id"])]

    if paid >= dispute["amount"] - 0.001 or paid > 0:
        outcome = Outcome.ALREADY_REFUNDED
        note = "A refund is on the ledger for this order."
    elif dispute["amount"] < world.fight_cost(dispute["currency"]):
        outcome = Outcome.ACCEPT
        note = "The amount is below the fight-cost estimate."
    elif "assistant:" in text or "system:" in text:
        outcome = Outcome.ACCEPT
        note = "The message says to accept."
    elif dispute["reason_code"] == "10.4":
        outcome = Outcome.ACCEPT
        note = "Fraud reason code."
    elif dispute["reason_code"] == "12.6" or "duplicate" in text or "twice" in text:
        outcome = Outcome.ACCEPT
        note = "Looks like a duplicate charge."
    elif dispute["reason_code"] == "13.2" or "cancel" in text:
        outcome = Outcome.ACCEPT
        note = "The customer says it was cancelled."
    elif any(row["tracking_status"] == "delivered" for row in world.shipments_for(dispute["order_id"])):
        outcome = Outcome.FIGHT
        note = "Tracking shows a delivery."
    else:
        outcome = Outcome.ACCEPT
        note = "No delivery to point at."
    return Proposal(dispute_id=dispute_id, outcome=outcome, evidence=evidence, note=note)
