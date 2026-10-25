"""Version A: code only. Fixed patterns read the email, the bank side decides.

Written against the textbook wording only (ORD-1234 order numbers, "Amount:" lines,
sort code and account, IBAN). It was not tuned on the messy variants, so it shows how
far plain parsing gets before an AI reads anything.
"""

import re

from .bank import BankSide

ORDER = re.compile(r"\bORD-\d{4}\b")
MONEY = r"(\d{1,3}(?:,\d{3})*\.\d{2})"
AMOUNT_LINE = re.compile(r"(?:amount|total|due)[^\n\d£€]*(?:£|€|GBP|EUR)?\s*" + MONEY, re.I)
ANY_AMOUNT = re.compile(r"(?:£|€|GBP\s|EUR\s)\s*" + MONEY)
SORT_ACCOUNT = re.compile(r"(\d{2}-\d{2}-\d{2})\D{1,30}?(\d{8})\b")
IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")
INVOICE = re.compile(r"\b(?:invoice|INV)\s*:?\s*([A-Z]{2,4}-[A-Z0-9-]*\d)", re.I)
REF = re.compile(r"\b([A-Z]{2,4}-(?:[A-Z]{2}-)?\d{3,6}(?:-\d{2,4})?)\b")
INSTALMENT = re.compile(r"instalment\s+(\d)\s+of\s+(\d)", re.I)


def _amount(text):
    m = AMOUNT_LINE.search(text) or ANY_AMOUNT.search(text)
    return float(m.group(1).replace(",", "")) if m else None


def propose(bank: BankSide) -> dict:
    req = bank.world.requests[bank.request_id]
    text = req["subject"] + "\n" + req["body"]
    sender = req["from"].lower()

    order = ORDER.search(text)
    if order:
        info = bank.lookup_order(order.group(0))
        if "error" in info:
            return {"action": "ASK_HUMAN", "note": "Order not found."}
        amount = _amount(req["body"]) or info["refundable_left"]
        return {"action": "REFUND", "order_id": info["order_id"], "amount": amount, "currency": info["currency"]}

    supplier = bank.lookup_supplier(sender)
    if "error" in supplier:
        return {"action": "ASK_HUMAN", "note": "Sender is not a known supplier and no order number found."}
    amount = _amount(req["body"])
    if amount is None:
        return {"action": "ASK_HUMAN", "note": "No amount found."}
    acct = SORT_ACCOUNT.search(req["body"])
    iban = IBAN.search(req["body"])
    account = f"{acct.group(1)} {acct.group(2)}" if acct else (iban.group(0) if iban else None)
    inv = INVOICE.search(text) or REF.search(text)
    inst = INSTALMENT.search(text)
    return {"action": "TRANSFER", "payee_id": supplier["payee_id"], "amount": amount,
            "currency": supplier["currency"], "account": account,
            "invoice_ref": inv.group(1) if inv else None,
            "instalment": f"{inst.group(1)}/{inst.group(2)}" if inst else None}
