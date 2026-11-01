"""The shop's records. The answer key in gold/ is not loaded here."""

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


class World:
    def __init__(self):
        self.disputes = {row["id"]: row for row in _load("disputes.json")}
        self.orders = {row["order_id"]: row for row in _load("orders.json")}
        self.customers = {row["customer_id"]: row for row in _load("customers.json")}
        self.fees = _load("fees.json")
        self.shipments: dict[str, list] = {}
        for row in _load("shipments.json"):
            self.shipments.setdefault(row["order_id"], []).append(row)
        self.emails: dict[str, list] = {}
        for row in _load("emails.json"):
            self.emails.setdefault(row["order_id"], []).append(row)
        self.refund_rows = _load("refunds.json")
        self.as_of = date.fromisoformat(self.fees["desk_as_of"])

    def dispute(self, dispute_id: str) -> dict:
        return self.disputes[dispute_id]

    def order(self, order_id: str) -> dict:
        return self.orders[order_id]

    def shipments_for(self, order_id: str) -> list:
        return self.shipments.get(order_id, [])

    def emails_for(self, order_id: str) -> list:
        return self.emails.get(order_id, [])

    def refunds_for(self, order_id: str) -> list:
        return [row for row in self.refund_rows if row["order_id"] == order_id]

    def refund_sum(self, order_id: str) -> float:
        return sum(row["amount"] for row in self.refunds_for(order_id))

    def fight_cost(self, currency: str) -> float:
        return self.fees["fight_cost_estimate"][currency]

    def dispute_fee(self, currency: str) -> float:
        return self.fees["dispute_fee"][currency]
