"""Export everything an owner console needs into one JSON file.

    python scripts/export_console_data.py                 # latest Version B run
    python scripts/export_console_data.py --run var/runs/20261101-151114-B

Read-only: uses data/, gold/ and a saved run. No model calls, no keys.

Each dispute in a run has its own audit file. For the console, the decisions are
re-chained into one log in the order the disputes were opened, with the same
hashing as dispute_desk/audit.py. Each entry keeps its original per-dispute hash.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dispute_desk.audit import AuditLog  # noqa: E402

OUT = ROOT / "console" / "console_data.json"

# From README "Results" (three runs of B).
RESULTS = [
    {"version": "A", "design": "Code rules only", "right": "19/30", "safe_not_ideal": 2, "wrong": 9,
     "recovered": "£130 + €80", "usd_per_dispute": 0.0, "seconds": "<0.1"},
    {"version": "B", "design": "One agent + guardrail (shipped)", "right": "28, 27, 27", "safe_not_ideal": 2,
     "wrong": "0-1", "recovered": "£226 + €84", "usd_per_dispute": 0.001, "seconds": "~4.5"},
]

PLAIN = {
    "PROPOSAL_STANDS": "The proposal was allowed",
    "PROPOSAL_DOWNGRADED": "A fight was made safer",
    "FULL_REFUND": "This order was already refunded in full",
    "REFUND_NOT_ON_LEDGER": "The claimed refund is not on this order",
    "BELOW_FIGHT_COST": "The amount is below the cost of fighting",
    "PARTIAL_REFUND": "Only part of the amount was refunded",
    "COMPELLING_EVIDENCE_NOT_MET": "Compelling Evidence 3.0 is not met",
    "EVIDENCE_MISSING": "The fight did not attach the records it needs",
    "DELIVERED_ELSEWHERE": "Delivered somewhere the customer did not ask for",
    "NOT_DELIVERED": "Tracking does not show a delivery",
    "SPLIT_SHIPMENT": "One parcel arrived and another did not",
    "AMOUNT_MISMATCH": "The disputed amount is not the order total",
    "INSTRUCTION_NOT_EVIDENCE": "An instruction in the cardholder message is not evidence",
    "SUBMIT_TODAY": "The reply is due by tomorrow, so file it today",
    "LATE": "The reply date has passed",
    "CANCELLED_BEFORE_CHARGE": "The subscription was cancelled before this charge",
    "DUPLICATE_CAPTURE": "The same order was captured twice",
}


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def latest_b_run():
    runs = sorted(path for path in (ROOT / "var" / "runs").glob("*-B") if (path / "results.jsonl").exists())
    if not runs:
        sys.exit("No Version B run found in var/runs. Run scripts/run_eval.py --version B first.")
    return runs[-1]


def canonical(entry):
    """The exact string audit.py hashes."""
    return json.dumps({k: v for k, v in entry.items() if k != "hash"}, sort_keys=True, ensure_ascii=False, default=str)


def first_decision(path: Path):
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("outcome"):
            return entry
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path)
    run = (parser.parse_args().run or latest_b_run()).resolve()

    disputes = {row["id"]: row for row in load("data/disputes.json")}
    fees = load("data/fees.json")
    results = {}
    for line in (run / "results.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            results[row["dispute_id"]] = row

    decisions = {}
    for path in sorted((run / "audit").glob("DP-*.jsonl")):
        entry = first_decision(path)
        if entry:
            decisions[entry["dispute_id"]] = entry

    cases = []
    for dispute_id in sorted(disputes):
        dispute = disputes[dispute_id]
        scored = results.get(dispute_id, {})
        decision = decisions.get(dispute_id) or {}
        currency = dispute["currency"]
        amount = float(dispute["amount"])
        fee = fees["dispute_fee"][currency]
        fight = fees["fight_cost_estimate"][currency]
        reasons = decision.get("reasons") or [{"code": code, "detail": ""} for code in scored.get("reasons", [])]
        cases.append({
            "dispute_id": dispute_id,
            "slice": scored.get("slice"),
            "reason_code": dispute["reason_code"],
            "opened_at": dispute["opened_at"],
            "respond_by": dispute["respond_by"],
            "cardholder_message": dispute["cardholder_message"],
            "priority": decision.get("priority") or scored.get("priority"),
            "proposal": decision.get("proposal"),
            "decision": decision.get("outcome") or scored.get("got"),
            "gold_outcome": scored.get("gold"),
            "gold_priority": scored.get("gold_priority"),
            "verdict": scored.get("verdict"),
            "reasons": [{"code": item["code"], "plain": PLAIN.get(item["code"], item["code"].replace("_", " ").capitalize()),
                         "detail": item.get("detail")} for item in reasons],
            "evidence_pack": decision.get("evidence_pack") or {},
            "money": {
                "amount": amount,
                "currency": currency,
                "dispute_fee": fee,
                "fight_cost": fight,
                "recovered_if_fight": round(amount - fee - fight, 2),
                "loss_if_accept": round(amount + fee, 2),
                "recovered_this_run": scored.get("recovered", 0),
                "accepted_loss_this_run": scored.get("accepted_loss", 0),
            },
            "original_audit_hash": decision.get("hash"),
        })

    log = AuditLog()
    for case in sorted(cases, key=lambda row: (row["opened_at"], row["dispute_id"])):
        entry = decisions.get(case["dispute_id"])
        if entry:
            log.append({k: v for k, v in entry.items() if k not in ("seq", "prev_hash", "hash")})
    if not log.verify():
        sys.exit("re-chained audit does not verify")
    audit = [{
        "seq": entry["seq"],
        "dispute_id": entry.get("dispute_id"),
        "opened_at": disputes[entry["dispute_id"]]["opened_at"],
        "outcome": entry.get("outcome"),
        "priority": entry.get("priority"),
        "prev_hash": entry["prev_hash"],
        "hash": entry["hash"],
        "hashed_body": canonical(entry),
    } for entry in log.entries]

    data = {
        "meta": {
            "source_run": run.name,
            "desk_as_of": fees["desk_as_of"],
            "note": "Made-up data only. Hollowbrook Ceramics is fictional.",
            "hashing": "sha256 over hashed_body (UTF-8). prev_hash of entry 1 is 64 zeros.",
            "order": "Audit entries are in the order the disputes were opened.",
        },
        "disputes": cases,
        "audit": audit,
        "results": RESULTS,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)} from {run.name}: {len(cases)} disputes, {len(audit)} audit entries")


if __name__ == "__main__":
    main()
