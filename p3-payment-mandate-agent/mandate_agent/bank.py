"""The bank side as a service: the agent's 5 tools and the owner's tools.

Every version goes through this class. Version A calls it directly; the AI versions
reach it only through the MCP server (mcp_server.py), which exposes the agent tools
and nothing else. Only propose_payment can lead to money moving, and only if the
policy engine says yes.
"""

import json
from pathlib import Path

from .policy import PolicyEngine, _on_file_account, name_check, normalise_account, normalise_name, screen
from .schema import Proposal
from .world import load_world

AGENT_ID = "agent-hb-ops-01"


class BankSide:
    def __init__(self, request_id: str, checks_on: bool = True, audit_path: Path | None = None):
        self.request_id = request_id   # the server, not the agent, says which request this is
        self.world = load_world(request_id)
        self.engine = PolicyEngine(self.world, AGENT_ID, checks_on=checks_on)
        self.audit_path = audit_path
        self.decisions = []

    # ------------------------------------------------ agent tools (read only, then propose)
    def get_mandate(self, currency: str) -> dict:
        m = self.world.mandate_for(currency.upper())
        if m is None:
            return {"error": f"No mandate for {currency}."}
        mine = [r for r in self.world.ledger if r.get("mandate_id") == m["mandate_id"] and r["status"] == "EXECUTED"]
        this_month = self.world.requests[self.request_id]["received_at"][:7]
        month = sum(r["amount"] for r in mine if r["date"][:7] == this_month)
        return {k: m[k] for k in ("mandate_id", "currency", "rail", "status", "allowed_actions",
                                  "max_per_payment", "approval_threshold", "monthly_limit",
                                  "refund_window_days", "valid_from", "valid_to")} | {
            "allowed_suppliers": [p for p in m["allowed_payees"] if p != "ORIGINAL_PAYER"],
            "refunds_go_to": "the account that paid the original order, only",
            "spent_this_month": round(month, 2),
            "left_this_month": round(m["monthly_limit"] - month, 2),
        }

    def lookup_order(self, order_id: str) -> dict:
        o = self.world.orders.get(order_id.strip().upper())
        if o is None:
            return {"error": f"No order {order_id}."}
        refunded = sum(r["amount"] for r in self.world.ledger
                       if r["action"] == "REFUND" and r.get("order_id") == o["order_id"])
        return {k: o[k] for k in ("order_id", "currency", "date", "customer_name", "customer_email", "lines", "total")} | {
            "already_refunded": round(refunded, 2), "refundable_left": round(o["total"] - refunded, 2)}

    def lookup_supplier(self, query: str) -> dict:
        """Find a known supplier by id, name or email address."""
        q = query.strip().lower()
        for s in self.world.suppliers.values():
            if q in (s["payee_id"].lower(), s["contact"].lower()) or normalise_name(query) == normalise_name(s["name"]):
                paid = [{k: r[k] for k in ("date", "amount", "invoice_ref") if k in r} | (
                        {"instalment": r["instalment"]} if r.get("instalment") else {})
                        for r in self.world.ledger if r.get("payee_id") == s["payee_id"]]
                return {"payee_id": s["payee_id"], "name": s["name"], "currency": s["currency"],
                        "account_on_file": _on_file_account(s), "known_contact": s["contact"],
                        "recent_payments": paid}
        return {"error": "No known supplier matches.", "query": query}

    def check_payee(self, name: str, account: str, currency: str) -> dict:
        """Preview only. propose_payment runs these checks again."""
        acct = normalise_account(account)
        m = self.world.mandate_for(currency.upper())
        label = {"FPS": "Confirmation of Payee", "SEPA_INST": "Verification of Payee"}.get(m["rail"] if m else "", "Name check")
        result, score = name_check(name, self.world.directory.get(acct))
        sanc, entry, sscore = screen(name, self.world.sanctions)
        return {"name_check": {"label": label, "result": result},
                "sanctions": {"result": sanc, "list_version": self.world.sanctions["list_version"]}}

    def propose_payment(self, **fields) -> dict:
        try:
            proposal = Proposal(**{**fields, "request_id": self.request_id})
        except Exception as e:  # malformed proposals are refused, never guessed at
            return {"outcome": "INVALID_PROPOSAL", "error": str(e)[:300]}
        decision = self.engine.decide(proposal)
        self.decisions.append(decision)
        self._save_audit()
        return {"outcome": decision.outcome.value,
                "reasons": [{"code": r.code, "detail": r.detail} for r in decision.reasons]}

    # ------------------------------------------------ owner tools (never given to the agent)
    def approve_payment(self, request_id: str, approver: str, passkey_ok: bool) -> dict:
        pending = next(d for d in reversed(self.decisions) if d.request_id == request_id)
        result = self.engine.approve(pending, approver, passkey_ok)
        self._save_audit()
        return {"outcome": result.outcome.value}

    def revoke_mandate(self, mandate_id: str, by: str) -> dict:
        n = self.engine.revoke(mandate_id, by)
        self._save_audit()
        return {"revoked": mandate_id, "tokens_deactivated": n}

    def pause_all(self, by: str) -> dict:
        self.engine.pause_all(by)
        self._save_audit()
        return {"paused": True}

    def export_evidence_pack(self, request_id: str) -> list[dict]:
        return self.engine.audit.evidence_pack(request_id)

    def _save_audit(self):
        if self.audit_path:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            self.audit_path.write_text("\n".join(json.dumps(e, ensure_ascii=False, default=str)
                                                 for e in self.engine.audit.entries) + "\n", encoding="utf-8")
