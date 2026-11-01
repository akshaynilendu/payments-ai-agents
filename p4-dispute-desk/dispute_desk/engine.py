"""Guardrail for a dispute proposal. Same idea as Project 3's policy engine.

The proposal is the outcome. This code can only make it safer: a full refund on
this order becomes ALREADY_REFUNDED, an amount below the fight-cost floor becomes
ACCEPT, and a FIGHT that fails Compelling Evidence 3.0 or does not attach the
required records becomes ASK_HUMAN. It never turns ACCEPT or ASK_HUMAN into FIGHT.
It does not judge "not as described" from email prose. The one address check is
narrower: a delivery to somewhere other than the order address can stay a fight
only when the proposal cites an email from the cardholder's own address that
asks for that place. An instruction inside the cardholder message is not evidence.
"""

from datetime import date, timedelta

from .audit import AuditLog
from .schema import Decision, Finding, Outcome, Priority, Proposal
from .world import World

# Same window as Visa Compelling Evidence 3.0 in DECISIONS.md (D4).
CE_MIN_DAYS = 120
CE_MAX_DAYS = 365

# A line like this is an instruction to the model, not a shop record.
INSTRUCTION = ("assistant:", "system:", "ignore previous", "do not attach")
RECORD_KINDS = {"order", "shipment", "email", "refund", "customer", "p3_audit", "fees"}


def _money(a, b) -> bool:
    return abs(float(a) - float(b)) < 0.005


def _place(address):
    if not address:
        return None
    return (
        address["line1"].strip().lower(),
        address["postcode"].replace(" ", "").lower(),
        address["country"].lower(),
    )


def _same_place(a, b) -> bool:
    return _place(a) is not None and _place(a) == _place(b)


def _ce_elements(order: dict) -> dict:
    ship = order["ship_to"]
    return {
        "ip_address": order["ip_address"],
        "device_id": order["device_id"],
        "shipping_address": (ship["line1"], ship["postcode"], ship["country"]),
        "account_login": order["account_login"],
    }


def _ce_matches(a: dict, b: dict) -> int:
    left, right = _ce_elements(a), _ce_elements(b)
    return sum(1 for key in left if left[key] == right[key])


def _email_supports_delivery(email: dict, order: dict, place: dict | None) -> bool:
    """True when this email is from the cardholder and names the delivery address.

    Instruction lines are skipped, so a line aimed at the model cannot invent an address.
    This does not decide whether the goods were as described.
    """
    sender = (email.get("from") or "").lower()
    own = (order.get("customer_email") or "").lower()
    if not own or own not in sender or not place:
        return False
    kept = []
    for line in f"{email.get('subject', '')}\n{email.get('body', '')}".splitlines():
        if any(mark in line.lower() for mark in INSTRUCTION):
            continue
        kept.append(line)
    blob = "\n".join(kept).lower()
    line1 = (place.get("line1") or "").strip().lower()
    postcode = (place.get("postcode") or "").replace(" ", "").lower()
    if line1 and line1 in blob:
        return True
    return bool(postcode) and postcode in blob.replace(" ", "")


def _without_audit(row: dict) -> dict:
    return {key: value for key, value in row.items() if key != "p3_audit"}


class Engine:
    def __init__(self, world: World | None = None, audit: AuditLog | None = None):
        self.world = world or World()
        self.audit = audit or AuditLog()

    def priority(self, respond_by: date) -> Priority:
        # A date that has already passed is an automatic loss. Due today or tomorrow is filed today.
        if respond_by < self.world.as_of:
            return Priority.LATE
        if respond_by <= self.world.as_of + timedelta(days=1):
            return Priority.SUBMIT_TODAY
        return Priority.NORMAL

    def decide(self, proposal: Proposal) -> Decision:
        dispute = self.world.dispute(proposal.dispute_id)
        order = self.world.order(dispute["order_id"])
        outcome, reasons = self._guard(proposal, dispute, order)
        priority = self.priority(date.fromisoformat(dispute["respond_by"]))
        if proposal.outcome == Outcome.FIGHT and outcome != Outcome.FIGHT:
            reasons.append(Finding(
                code="PROPOSAL_DOWNGRADED",
                detail=f"Proposed FIGHT. The guardrail says {outcome.value}.",
            ))
        if priority == Priority.SUBMIT_TODAY:
            reasons.append(Finding(
                code="SUBMIT_TODAY",
                detail="The response is due by tomorrow. Filing today is the only way it is not an automatic loss.",
            ))
        elif priority == Priority.LATE:
            reasons.append(Finding(
                code="LATE",
                detail="The response date has passed. A late response is an automatic loss.",
            ))
        pack = self._pack(dispute, order)
        record = {
            "event": "DECISION",
            "dispute_id": dispute["id"],
            "proposal": proposal.model_dump(mode="json"),
            "outcome": outcome.value,
            "priority": priority.value,
            "reasons": [item.model_dump() for item in reasons],
            "evidence_pack": pack,
        }
        digest = self.audit.append(record)
        return Decision(
            dispute_id=dispute["id"],
            outcome=outcome,
            priority=priority,
            reasons=reasons,
            evidence_pack=pack,
            audit_hash=digest,
        )

    def _guard(self, proposal: Proposal, dispute: dict, order: dict) -> tuple[Outcome, list[Finding]]:
        # Start from what was proposed. Each step may replace it with a safer outcome, never with FIGHT.
        outcome = proposal.outcome
        paid = self.world.refund_sum(dispute["order_id"])
        amount = float(dispute["amount"])
        if paid >= amount - 0.001:
            outcome = Outcome.ALREADY_REFUNDED
            reasons = [Finding(
                code="FULL_REFUND",
                detail=f"{paid:g} {dispute['currency']} is already refunded on {dispute['order_id']}.",
            )]
        elif outcome == Outcome.ALREADY_REFUNDED:
            outcome = Outcome.ASK_HUMAN
            reasons = [Finding(
                code="REFUND_NOT_ON_LEDGER",
                detail=f"No full refund is on the ledger for {dispute['order_id']}.",
            )]
        else:
            reasons = []

        cost = self.world.fight_cost(dispute["currency"])
        if outcome != Outcome.ALREADY_REFUNDED and amount < cost:
            outcome = Outcome.ACCEPT
            reasons = [Finding(
                code="BELOW_FIGHT_COST",
                detail=(
                    f"{amount:g} {dispute['currency']} is below the {cost:g} fight-cost estimate, "
                    "and the dispute fee is kept either way."
                ),
            )]

        if outcome == Outcome.FIGHT:
            block = self._fight_block(proposal, dispute, order)
            if block:
                outcome = Outcome.ASK_HUMAN
                reasons = [Finding(code=block[0], detail=block[1])]
        if not reasons:
            reasons = [Finding(code="PROPOSAL_STANDS", detail="No guardrail refused this proposal.")]
        return outcome, reasons

    def _fight_block(self, proposal: Proposal, dispute: dict, order: dict) -> tuple[str, str] | None:
        citations, instruction_only = self._citations(proposal, dispute)
        if not citations:
            if instruction_only:
                return (
                    "INSTRUCTION_NOT_EVIDENCE",
                    "The only attached text is an instruction inside the cardholder message.",
                )
            return ("EVIDENCE_MISSING", "A fight needs records, and none were attached.")
        paid = self.world.refund_sum(dispute["order_id"])
        amount = float(dispute["amount"])
        if 0.001 < paid < amount - 0.001:
            return (
                "PARTIAL_REFUND",
                f"{paid:g} of {amount:g} {dispute['currency']} is refunded. The rest needs a person.",
            )
        code = dispute["reason_code"]
        if code == "10.4":
            return self._block_104(order, citations)
        if code == "13.1":
            return self._block_131(order, citations)
        if code == "13.3":
            return self._block_133(dispute, order, citations)
        if code == "13.2":
            return self._block_132(order, citations)
        if code == "12.6":
            return self._block_126(order, citations)
        return ("UNKNOWN_REASON", f"No rule for reason {code}.")

    def _citations(self, proposal: Proposal, dispute: dict) -> tuple[list[tuple[str, str]], bool]:
        # Instructions are dropped before any record is counted, so they can never be the proof.
        found = []
        saw_instruction = False
        message = dispute["cardholder_message"].strip()
        for token in proposal.evidence:
            if token.strip() == message or any(mark in token.lower() for mark in INSTRUCTION):
                saw_instruction = True
                continue
            kind, sep, ref = token.partition(":")
            if sep and kind in RECORD_KINDS and ref and self._record_exists(kind, ref):
                found.append((kind, ref))
        return found, saw_instruction and not found

    def _record_exists(self, kind: str, ref: str) -> bool:
        if kind == "order":
            return ref in self.world.orders
        if kind == "shipment":
            return self._shipment(ref) is not None
        if kind == "email":
            return any(row["email_id"] == ref for rows in self.world.emails.values() for row in rows)
        if kind == "refund":
            return any(row["refund_id"] == ref for row in self.world.refund_rows)
        if kind == "customer":
            return ref in self.world.customers
        if kind == "p3_audit":
            return self._audit(ref) is not None
        if kind == "fees":
            return ref in self.world.fees
        return False

    def _shipment(self, shipment_id: str) -> dict | None:
        for rows in self.world.shipments.values():
            for row in rows:
                if row["shipment_id"] == shipment_id:
                    return row
        return None

    def _audit(self, request_id: str) -> dict | None:
        rows = [row for rows in self.world.emails.values() for row in rows]
        rows += self.world.refund_rows
        for row in rows:
            audit = row.get("p3_audit")
            if audit and audit["request_id"] == request_id:
                return audit
        return None

    def _block_104(self, order: dict, citations: list[tuple[str, str]]) -> tuple[str, str] | None:
        priors = self._qualifying_priors(order)
        if len(priors) < 2:
            return (
                "COMPELLING_EVIDENCE_NOT_MET",
                "Fewer than two undisputed orders on this card fall in the 120 to 365 day window "
                "and share two data elements, so a 10.4 fight is not allowed.",
            )
        cited = {ref for kind, ref in citations if kind == "order"}
        missing = [item for item in sorted(priors) if item not in cited]
        if missing:
            return (
                "EVIDENCE_MISSING",
                "The Compelling Evidence orders are not in the pack: " + ", ".join(missing) + ".",
            )
        return None

    def _qualifying_priors(self, order: dict) -> list[str]:
        refunded = {row["order_id"] for row in self.world.refund_rows}
        when = date.fromisoformat(order["date"])
        found = []
        for other in self.world.orders.values():
            if other["order_id"] == order["order_id"] or other["card_id"] != order["card_id"]:
                continue
            if other["order_id"] in refunded:
                continue
            days = (when - date.fromisoformat(other["date"])).days
            if CE_MIN_DAYS <= days <= CE_MAX_DAYS and _ce_matches(order, other) >= 2:
                found.append(other["order_id"])
        return found

    def _block_131(self, order: dict, citations: list[tuple[str, str]]) -> tuple[str, str] | None:
        ships = self.world.shipments_for(order["order_id"])
        delivered = [row for row in ships if row["tracking_status"] == "delivered"]
        # One parcel delivered and another not is not a fight the engine can allow on its own.
        if len(ships) > 1 and delivered and len(delivered) < len(ships):
            return ("SPLIT_SHIPMENT", "One parcel was delivered and another was not.")
        cited_ids = {ref for kind, ref in citations if kind == "shipment"}
        cited = [row for row in ships if row["shipment_id"] in cited_ids and row["tracking_status"] == "delivered"]
        if not cited:
            return ("NOT_DELIVERED", "No cited shipment shows a delivery.")
        if all(_same_place(row.get("delivered_to"), order["ship_to"]) for row in cited):
            return None
        # Elsewhere is a fight only with an email from the cardholder asking for that address.
        email_ids = {ref for kind, ref in citations if kind == "email"}
        attached = [row for row in self.world.emails_for(order["order_id"]) if row["email_id"] in email_ids]
        if all(
            any(_email_supports_delivery(email, order, row.get("delivered_to")) for email in attached)
            for row in cited
        ):
            return None
        return (
            "DELIVERED_ELSEWHERE",
            "Delivered away from the order address. A fight needs an email from the cardholder's "
            "own address asking for this delivery address.",
        )

    def _block_133(self, dispute: dict, order: dict, citations: list[tuple[str, str]]) -> tuple[str, str] | None:
        # Amount is a field. The email text that says the item was fine or cracked is not read here.
        if not _money(dispute["amount"], order["total"]):
            return (
                "AMOUNT_MISMATCH",
                f"The dispute is {dispute['amount']:g} {dispute['currency']} and the order total is {order['total']:g}.",
            )
        kinds = {kind for kind, _ref in citations}
        if not kinds & {"order", "shipment", "email", "p3_audit"}:
            return ("EVIDENCE_MISSING", "A not-as-described fight needs the order or the customer's email.")
        return None

    def _block_132(self, order: dict, citations: list[tuple[str, str]]) -> tuple[str, str] | None:
        cited = {ref for kind, ref in citations if kind == "order"}
        if order["order_id"] not in cited:
            return ("EVIDENCE_MISSING", "The subscription is on the order, and the order is not in the evidence.")
        cancelled = (order.get("subscription") or {}).get("cancelled_at")
        if cancelled and date.fromisoformat(cancelled) < date.fromisoformat(order["date"]):
            return (
                "CANCELLED_BEFORE_CHARGE",
                f"Cancellation {cancelled} is before the charge on {order['date']}.",
            )
        return None

    def _block_126(self, order: dict, citations: list[tuple[str, str]]) -> tuple[str, str] | None:
        captures = order.get("captures") or []
        settled = [row for row in captures if row["status"] == "settled"]
        voids = [row for row in captures if row["status"] == "void"]
        ships = self.world.shipments_for(order["order_id"])
        cited = {ref for kind, ref in citations if kind == "order"}
        if len(settled) >= 2 and len(ships) <= 1:
            return ("DUPLICATE_CAPTURE", "Two captures of this order settled, so a fight is not supported.")
        if len(settled) == 1 and voids:
            if order["order_id"] in cited:
                return None
            return ("EVIDENCE_MISSING", "The voided attempt is on the order, and the order is not in the evidence.")
        for other_id in cited:
            if other_id == order["order_id"] or other_id not in self.world.orders:
                continue
            other = self.world.order(other_id)
            if other["customer_id"] != order["customer_id"] or not _money(other["total"], order["total"]):
                continue
            if self._delivered(other_id) and self._delivered(order["order_id"]):
                return None
        return (
            "EVIDENCE_MISSING",
            "A duplicate fight needs the voided attempt, or the other real order, in the evidence.",
        )

    def _delivered(self, order_id: str) -> bool:
        return any(row["tracking_status"] == "delivered" for row in self.world.shipments_for(order_id))

    def _pack(self, dispute: dict, order: dict) -> dict:
        cid = order["customer_id"]
        # Bodies are copied onto the pack for a person. Nothing above branches on them.
        emails = [_without_audit(row) for row in self.world.emails_for(dispute["order_id"])]
        refunds = []
        for row in self.world.refund_rows:
            if self.world.order(row["order_id"])["customer_id"] == cid:
                refunds.append(_without_audit(row))
        audits = []
        seen = set()
        for row in self.world.emails_for(dispute["order_id"]) + [
            item for item in self.world.refund_rows
            if self.world.order(item["order_id"])["customer_id"] == cid
        ]:
            audit = row.get("p3_audit")
            if audit and audit["request_id"] not in seen:
                seen.add(audit["request_id"])
                audits.append(audit)
        related = []
        if dispute["reason_code"] == "10.4":
            related = self._earlier_cards(order)
        elif dispute["reason_code"] == "12.6":
            related = self._same_amount_orders(order)
        return {
            "order": order,
            "shipments": self.world.shipments_for(dispute["order_id"]),
            "emails": emails,
            "refunds": refunds,
            "p3_audit": audits,
            "related_orders": related,
        }

    def _earlier_cards(self, order: dict) -> list[dict]:
        refunded = {row["order_id"] for row in self.world.refund_rows}
        when = date.fromisoformat(order["date"])
        found = []
        for other in self.world.orders.values():
            if other["card_id"] != order["card_id"] or other["order_id"] == order["order_id"]:
                continue
            days = (when - date.fromisoformat(other["date"])).days
            if days <= 0:
                continue
            matches = _ce_matches(order, other)
            qualifies = (
                other["order_id"] not in refunded
                and CE_MIN_DAYS <= days <= CE_MAX_DAYS
                and matches >= 2
            )
            found.append({
                "order_id": other["order_id"],
                "date": other["date"],
                "days_before": days,
                "refunded": other["order_id"] in refunded,
                "matching_elements": matches,
                "qualifies": qualifies,
            })
        return sorted(found, key=lambda row: row["date"])

    def _same_amount_orders(self, order: dict) -> list[dict]:
        found = []
        for other in self.world.orders.values():
            if other["customer_id"] != order["customer_id"] or other["order_id"] == order["order_id"]:
                continue
            if not _money(other["total"], order["total"]):
                continue
            found.append({
                "order_id": other["order_id"],
                "date": other["date"],
                "total": other["total"],
                "delivered": self._delivered(other["order_id"]),
            })
        return found
