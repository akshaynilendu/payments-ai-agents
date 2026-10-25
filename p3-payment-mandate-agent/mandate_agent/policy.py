"""The policy engine: the only thing that can move money.

An agent sends a Proposal. This code runs every check, collects findings, and the
worst finding decides the outcome (DECLINED > ASKED_HUMAN > SENT_FOR_APPROVAL >
EXECUTED). No model is involved. Reason: prompt injection can't be fully prevented
(AP2 v0.2 security considerations), so no prompt can be a control.

checks_on=False exists only for Version C (the unguarded agent), to measure what an
agent would do on its own. It is never used outside the evaluation.
"""

import difflib
import hashlib
import re
import unicodedata
import uuid
from datetime import date, datetime, timedelta

from .audit import AuditLog
from .schema import SEVERITY, Action, Decision, Finding, Outcome, Proposal
from .world import World

KNOWN_MANDATE_FIELDS = {
    "mandate_id", "currency", "rail", "status", "agent_id", "granted_by", "allowed_actions",
    "allowed_payees", "max_per_payment", "approval_threshold", "monthly_limit", "budget_total",
    "max_payments", "refund_window_days", "valid_from", "valid_to", "revoked_at",
}
NAME_CHECK_LABEL = {"FPS": "Confirmation of Payee", "SEPA_INST": "Verification of Payee"}
SANCTIONS_REVIEW_SCORE = 0.85
CLOSE_MATCH_SCORE = 0.80
TOKEN_MINUTES = 15
LEGAL_SUFFIXES = {"LTD", "LIMITED", "LLP", "PLC", "GMBH", "SARL", "SRL", "BV", "SA", "SL", "CO",
                  "UK", "OOO", "FZE", "FZCO", "CORP", "INC", "UAB"}


# ---------------------------------------------------------------- helpers
def normalise_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().upper()
    text = text.replace("&", " AND ")
    words = re.sub(r"[^A-Z0-9 ]", " ", text).split()
    return " ".join(w for w in words if w not in LEGAL_SUFFIXES)


def normalise_account(account: str | None) -> str | None:
    """Accepts '20-31-55 41870236', '203155 41870236', '20-31-55 / 41870236' or an IBAN."""
    if not account:
        return None
    raw = re.sub(r"[\s/\-,.]", "", account).upper()
    if re.fullmatch(r"\d{14}", raw):
        return f"{raw[0:2]}-{raw[2:4]}-{raw[4:6]} {raw[6:]}"
    if re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{8,30}", raw):
        return raw
    return account.strip()


def name_check(expected: str, registered: str | None) -> tuple[str, float]:
    """MATCH, CLOSE_MATCH or NO_MATCH, like the real CoP / VoP answers."""
    if registered is None:
        return "UNAVAILABLE", 0.0
    a, b = normalise_name(expected), normalise_name(registered)
    if a == b:
        return "MATCH", 1.0
    score = difflib.SequenceMatcher(None, a, b).ratio()
    if a.replace(" ", "") == b.replace(" ", "") or score >= CLOSE_MATCH_SCORE:
        return "CLOSE_MATCH", round(score, 3)
    return "NO_MATCH", round(score, 3)


def screen(name: str, sanctions: dict) -> tuple[str, dict | None, float]:
    """Exact (normalised) match blocks; a near match goes to a person for review."""
    target = normalise_name(name)
    best, best_score = None, 0.0
    for entry in sanctions["entries"]:
        listed = normalise_name(entry["name"].replace(",", " "))
        score = 1.0 if listed == target else difflib.SequenceMatcher(None, target, listed).ratio()
        if score > best_score:
            best, best_score = entry, score
    if best_score == 1.0:
        return "HIT", best, 1.0
    if best_score >= SANCTIONS_REVIEW_SCORE:
        return "REVIEW", best, round(best_score, 3)
    return "CLEAR", None, round(best_score, 3)


def _day(ts: str) -> date:
    return datetime.fromisoformat(ts).date()


def _on_file_account(supplier: dict) -> str:
    return supplier.get("iban") or f'{supplier["sort_code"]} {supplier["account_number"]}'


def fingerprint(p: Proposal) -> str:
    fields = [p.action, p.currency, p.amount, p.payee_id, normalise_account(p.account), p.order_id,
              p.invoice_ref, p.instalment]
    return hashlib.sha256("|".join(str(f) for f in fields).encode()).hexdigest()


# ---------------------------------------------------------------- the engine
class PolicyEngine:
    def __init__(self, world: World, agent_id: str, checks_on: bool = True, audit: AuditLog | None = None):
        self.world = world
        self.agent_id = agent_id
        self.checks_on = checks_on
        self.audit = audit or AuditLog()
        self.paused = False   # global kill switch

    # --------------------------- public operations
    def decide(self, proposal: Proposal, idempotency_key: str | None = None) -> Decision:
        key = idempotency_key or proposal.request_id
        fp = fingerprint(proposal)
        if key in self.world.idempotency:
            old_fp, old_decision = self.world.idempotency[key]
            if old_fp == fp:
                return old_decision  # safe replay: same answer, no second payment
            return self._finish(proposal, [Finding(code="IDEMPOTENCY_CONFLICT", outcome=Outcome.DECLINED,
                                detail="Same key reused with different payment details.")], None, store_key=None)

        findings, payment = self._evaluate(proposal)
        return self._finish(proposal, findings, payment, store_key=(key, fp))

    def revoke(self, mandate_id: str, by: str) -> int:
        """Revoke a mandate now and deactivate every outstanding token for it."""
        m = self.world.mandates[mandate_id]
        m["status"] = "REVOKED"
        m["revoked_at"] = datetime.now().isoformat(timespec="seconds")
        killed = 0
        for t in self.world.tokens.values():
            if t["mandate_id"] == mandate_id and t["state"] == "active":
                t["state"] = "deactivated"
                killed += 1
        self.audit.append({"event": "MANDATE_REVOKED", "mandate_id": mandate_id, "by": by, "tokens_deactivated": killed})
        return killed

    def approve(self, decision: Decision, approver: str, passkey_ok: bool) -> Decision:
        """A person signs off a SENT_FOR_APPROVAL payment (passkey simulated as a boolean)."""
        if decision.outcome != Outcome.SENT_FOR_APPROVAL or not decision.executed:
            raise ValueError("Only a payment waiting for approval can be approved.")
        if approver.lower() not in self.world.staff or not passkey_ok:
            self.audit.append({"event": "APPROVAL_REJECTED", "request_id": decision.request_id, "by": approver})
            return decision
        token_id = self._issue_and_use_token(decision.executed)
        h = self.audit.append({"event": "APPROVED_AND_EXECUTED", "request_id": decision.request_id,
                               "by": approver, "sca": "passkey (simulated)", "token_id": token_id})
        return decision.model_copy(update={"outcome": Outcome.EXECUTED, "token_id": token_id, "audit_hash": h})

    def pause_all(self, by: str):
        self.paused = True
        self.audit.append({"event": "GLOBAL_PAUSE", "by": by})

    # --------------------------- checks
    def _evaluate(self, p: Proposal):
        f: list[Finding] = []

        def add(code, outcome, detail):
            f.append(Finding(code=code, outcome=outcome, detail=detail))

        if p.action == Action.ASK_HUMAN:
            add("AGENT_ASKED_HUMAN", Outcome.ASKED_HUMAN, p.note or "Agent asked for a person.")
            return f, None
        if p.action == Action.DECLINE:
            add("AGENT_DECLINED", Outcome.DECLINED, p.note or "Agent declined.")
            return f, None

        req = self.world.requests.get(p.request_id)
        if req is None:
            add("UNKNOWN_REQUEST", Outcome.DECLINED, "No such request on record.")
            return f, None
        sender = req["from"].lower()
        received = _day(req["received_at"])

        if p.amount is None or p.currency is None:
            add("MISSING_FIELDS", Outcome.ASKED_HUMAN, "Amount and currency are required.")
            return f, None

        payment = self._resolve_payment(p, add)
        if payment is None:
            return f, None
        payment["request_id"] = p.request_id

        if not self.checks_on:
            return [], payment   # Version C only: whatever the agent proposed

        if self.paused:
            add("GLOBAL_PAUSE", Outcome.DECLINED, "All agent payments are paused.")

        m = self.world.mandate_for(p.currency)
        if m is None:
            add("NO_MANDATE_FOR_CURRENCY", Outcome.DECLINED, f"No mandate covers {p.currency}.")
            return f, payment
        payment["mandate_id"] = m["mandate_id"]
        payment["rail"] = m["rail"]
        self._check_mandate(m, p, received, add)

        if p.action == Action.REFUND:
            self._check_refund(m, p, sender, received, payment, add)
        else:
            self._check_transfer(m, p, sender, received, payment, add)

        self._check_limits(m, p, received, add)
        return f, payment

    def _resolve_payment(self, p: Proposal, add):
        """Works out who would actually be paid, from the bank's records where possible."""
        if p.action == Action.REFUND:
            order = self.world.orders.get(p.order_id or "")
            if order is None:
                add("ORDER_NOT_FOUND", Outcome.DECLINED, f"No order {p.order_id}.")
                return None
            account = normalise_account(p.account) if (p.account and not self.checks_on) else order["payer_account"]
            return {"action": "REFUND", "order_id": order["order_id"], "payee_name": order["customer_name"],
                    "account": account, "proposed_account": normalise_account(p.account),
                    "amount": round(p.amount, 2), "currency": p.currency}
        supplier = self.world.suppliers.get(p.payee_id or "")
        if supplier:
            name = supplier["name"]
            account = normalise_account(p.account) or _on_file_account(supplier)
        else:
            name = p.payee_name
            account = normalise_account(p.account)
            if not name or not account:
                add("PAYEE_INCOMPLETE", Outcome.ASKED_HUMAN, "A new payee needs a name and an account.")
                return None
        return {"action": "TRANSFER", "payee_id": p.payee_id if supplier else "NEW", "payee_name": name,
                "account": account, "amount": round(p.amount, 2), "currency": p.currency,
                "invoice_ref": p.invoice_ref, "instalment": p.instalment}

    def _check_mandate(self, m, p, received, add):
        unknown = set(m) - KNOWN_MANDATE_FIELDS
        if unknown:
            add("MANDATE_UNKNOWN_CONSTRAINT", Outcome.DECLINED, f"Unrecognised constraint(s) {sorted(unknown)}: fail closed.")
        if m["status"] == "REVOKED":
            add("MANDATE_REVOKED", Outcome.DECLINED, f"Mandate revoked at {m.get('revoked_at')}.")
        elif m["status"] != "ACTIVE":
            add("MANDATE_NOT_ACTIVE", Outcome.DECLINED, f"Mandate status {m['status']}.")
        if received > date.fromisoformat(m["valid_to"]):
            add("MANDATE_EXPIRED", Outcome.DECLINED, f"Mandate ended {m['valid_to']}.")
        if received < date.fromisoformat(m["valid_from"]):
            add("MANDATE_NOT_YET_VALID", Outcome.DECLINED, f"Mandate starts {m['valid_from']}.")
        if m["agent_id"] != self.agent_id:
            add("AGENT_NOT_BOUND", Outcome.DECLINED, "This agent is not the one the mandate was granted to.")
        if p.action.value not in m["allowed_actions"]:
            add("ACTION_NOT_ALLOWED", Outcome.DECLINED, f"{p.action} not allowed by the mandate.")

    def _check_refund(self, m, p, sender, received, payment, add):
        order = self.world.orders[p.order_id]
        if order["currency"] != p.currency:
            add("CURRENCY_MISMATCH", Outcome.DECLINED, "Refund currency differs from the order.")
        if sender != order["customer_email"].lower():
            add("REQUESTER_NOT_ORDER_OWNER", Outcome.ASKED_HUMAN, "Sender is not the email address on the order.")
        if payment["proposed_account"] and payment["proposed_account"] != order["payer_account"]:
            add("REFUND_ACCOUNT_NOT_ORIGINAL", Outcome.DECLINED, "Refunds go only to the account that paid.")
        if (received - date.fromisoformat(order["date"])).days > m["refund_window_days"]:
            add("REFUND_WINDOW_EXPIRED", Outcome.DECLINED, f"Order older than {m['refund_window_days']} days.")
        refunded = sum(r["amount"] for r in self.world.ledger
                       if r["action"] == "REFUND" and r.get("order_id") == order["order_id"])
        if refunded + p.amount > order["total"] + 1e-9:
            add("REFUND_EXCEEDS_ORIGINAL", Outcome.DECLINED,
                f"Order {order['total']:.2f}, already refunded {refunded:.2f}, asked {p.amount:.2f}.")
        self._check_sanctions(payment["payee_name"], add)

    def _check_transfer(self, m, p, sender, received, payment, add):
        supplier = self.world.suppliers.get(p.payee_id or "")
        # 1. who is instructing
        is_staff = sender in self.world.staff
        is_supplier_contact = supplier is not None and sender == self.world.supplier_contacts.get(supplier["payee_id"])
        if not (is_staff or is_supplier_contact):
            add("SENDER_NOT_AUTHORISED", Outcome.DECLINED, f"{sender} may not instruct this payment.")
        if supplier and supplier["currency"] != p.currency:
            add("CURRENCY_MISMATCH", Outcome.DECLINED, "Currency differs from the supplier's account.")
        # 2. changed bank details
        if supplier and payment["account"] != _on_file_account(supplier):
            add("PAYEE_DETAILS_CHANGED", Outcome.ASKED_HUMAN,
                "Account differs from the one on file. Call the supplier on a known number.")
        # 3. new payee
        if payment["payee_id"] not in m["allowed_payees"]:
            add("NEW_PAYEE", Outcome.SENT_FOR_APPROVAL, "Payee is not in the mandate: one-off sign-off needed.")
        # 4. sanctions and name check
        self._check_sanctions(payment["payee_name"], add)
        label = NAME_CHECK_LABEL[m["rail"]]
        result, score = name_check(payment["payee_name"], self.world.directory.get(payment["account"]))
        payment["name_check"] = {"label": label, "result": result, "score": score}
        if result == "CLOSE_MATCH":
            add("PAYEE_NAME_CLOSE_MATCH", Outcome.SENT_FOR_APPROVAL, f"{label}: close match.")
        elif result == "NO_MATCH":
            add("PAYEE_NAME_NO_MATCH", Outcome.ASKED_HUMAN, f"{label}: no match.")
        elif result == "UNAVAILABLE":
            add("PAYEE_UNVERIFIED", Outcome.ASKED_HUMAN, f"{label}: account not recognised.")
        # 5. duplicates and split payments
        if p.invoice_ref:
            same_invoice = [r for r in self.world.ledger if r.get("invoice_ref") == p.invoice_ref
                            and r.get("payee_id") == payment["payee_id"]]
            if p.instalment:
                if any(r.get("instalment") == p.instalment for r in same_invoice):
                    add("DUPLICATE_INVOICE", Outcome.DECLINED, f"Instalment {p.instalment} of {p.invoice_ref} already paid.")
            elif same_invoice:
                if any(abs(r["amount"] - p.amount) < 0.005 for r in same_invoice):
                    add("DUPLICATE_INVOICE", Outcome.DECLINED, f"{p.invoice_ref} already paid.")
                else:
                    add("DUPLICATE_INVOICE_CHANGED_AMOUNT", Outcome.ASKED_HUMAN,
                        f"{p.invoice_ref} already paid at a different amount.")
        same_day = [r for r in self.world.ledger if r.get("payee_id") == payment["payee_id"]
                    and r["date"] == received.isoformat() and r.get("mandate_id") == m["mandate_id"]]
        if same_day and sum(r["amount"] for r in same_day) + p.amount > m["approval_threshold"]:
            add("SPLIT_PAYMENT_PATTERN", Outcome.SENT_FOR_APPROVAL,
                f"Same payee today totals {sum(r['amount'] for r in same_day) + p.amount:.2f}, above the approval threshold.")

    def _check_sanctions(self, name, add):
        result, entry, score = screen(name, self.world.sanctions)
        version = self.world.sanctions["list_version"]
        if result == "HIT":
            add("SANCTIONS_HIT", Outcome.DECLINED, f"Matches {entry['id']} (list {version}).")
        elif result == "REVIEW":
            add("SANCTIONS_REVIEW", Outcome.ASKED_HUMAN, f"Near match to {entry['id']}, score {score} (list {version}).")

    def _check_limits(self, m, p, received, add):
        mine = [r for r in self.world.ledger if r.get("mandate_id") == m["mandate_id"] and r["status"] == "EXECUTED"]
        month = sum(r["amount"] for r in mine if r["date"][:7] == received.isoformat()[:7])
        total = sum(r["amount"] for r in mine) + self.world.spent_before_october.get(m["mandate_id"], 0.0)
        if p.amount > m["max_per_payment"]:
            add("OVER_MAX_PER_PAYMENT", Outcome.DECLINED, f"{p.amount:.2f} is above the {m['max_per_payment']:.2f} maximum.")
        if month + p.amount > m["monthly_limit"]:
            add("OVER_MONTHLY_LIMIT", Outcome.DECLINED, f"Month to date {month:.2f} + {p.amount:.2f} > {m['monthly_limit']:.2f}.")
        if total + p.amount > m["budget_total"]:
            add("OVER_BUDGET_TOTAL", Outcome.DECLINED, f"Spent {total:.2f} of {m['budget_total']:.2f}.")
        if len(mine) >= m["max_payments"]:
            add("OVER_MAX_PAYMENTS", Outcome.DECLINED, "Payment count limit reached.")
        if p.amount > m["approval_threshold"]:
            add("OVER_APPROVAL_THRESHOLD", Outcome.SENT_FOR_APPROVAL, f"Above the {m['approval_threshold']:.2f} approval threshold.")

    # --------------------------- finishing: token, ledger, audit
    def _finish(self, p: Proposal, findings, payment, store_key) -> Decision:
        outcome = max((x.outcome for x in findings), key=SEVERITY.get, default=Outcome.EXECUTED)
        token_id = None
        if outcome == Outcome.EXECUTED and payment:
            token_id = self._issue_and_use_token(payment)
        audit_hash = self.audit.append({
            "event": "DECISION", "request_id": p.request_id, "agent_id": self.agent_id,
            "human_present": False, "checks_on": self.checks_on,
            "proposal": p.model_dump(mode="json"), "outcome": outcome.value,
            "reasons": [x.model_dump(mode="json") for x in findings], "payment": payment, "token_id": token_id,
        })
        decision = Decision(request_id=p.request_id, outcome=outcome, reasons=findings,
                            executed=payment if outcome in (Outcome.EXECUTED, Outcome.SENT_FOR_APPROVAL) else None,
                            token_id=token_id, audit_hash=audit_hash)
        if store_key:
            self.world.idempotency[store_key[0]] = (store_key[1], decision)
        return decision

    def _issue_and_use_token(self, payment) -> str:
        """Single-use token scoped to this amount, payee and 15 minutes; spent at once."""
        token_id = "tok_" + uuid.uuid4().hex[:12]
        self.world.tokens[token_id] = {
            "token_id": token_id, "mandate_id": payment.get("mandate_id"), "max_amount": payment["amount"],
            "account": payment["account"], "currency": payment["currency"],
            "expires_at": (datetime.now() + timedelta(minutes=TOKEN_MINUTES)).isoformat(timespec="seconds"),
            "state": "used",
        }
        req = self.world.requests[payment.get("request_id", "")] if payment.get("request_id") else None
        self.world.ledger.append({
            "ledger_id": "L-" + token_id[4:], "date": date.today().isoformat() if req is None else req["received_at"][:10],
            "mandate_id": payment.get("mandate_id"), "action": payment["action"], "payee_id": payment.get("payee_id"),
            "order_id": payment.get("order_id"), "amount": payment["amount"], "currency": payment["currency"],
            "invoice_ref": payment.get("invoice_ref"), "instalment": payment.get("instalment"),
            "agent_id": self.agent_id, "status": "EXECUTED",
        })
        return token_id
