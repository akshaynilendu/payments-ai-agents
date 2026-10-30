"""Export everything the owner console needs into one JSON file.

    python scripts/export_console_data.py                 # latest Version B run
    python scripts/export_console_data.py --run var/runs/20261025-132526-B

Read-only: uses data/, gold/ and a saved run. No model calls, no keys.

Each request in a run has its own one-entry audit log. For the console, the 40
decisions are re-chained into one log in the order the emails arrived, with the
same hashing as mandate_agent/audit.py, so the "verify chain" and "tamper" demos
work on a realistic day of activity. Each entry keeps its original per-request hash.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mandate_agent.audit import AuditLog  # noqa: E402

OUT = ROOT / "console" / "console_data.json"

# From README "Results" (3 runs each of B and D; C is B's proposals with every check off).
RESULTS = [
    {"version": "A", "design": "Code rules only", "right": "29", "safe_not_ideal": 4, "wrong": 7,
     "outside_mandate": 0, "money_wrong": "£108 + €80 sent wrongly", "usd_per_request": 0.0, "seconds": "<0.1"},
    {"version": "B", "design": "One agent + rules engine (shipped)", "right": "34, 34, 34", "safe_not_ideal": 6,
     "wrong": 0, "outside_mandate": 0, "money_wrong": "none", "usd_per_request": 0.00073, "seconds": "~4"},
    {"version": "C", "design": "Same agent, rules switched off", "right": "25", "safe_not_ideal": 6, "wrong": 9,
     "outside_mandate": 9, "money_wrong": "£640 + €1,620 sent wrongly; £2,615 + €1,100 sent without approval",
     "usd_per_request": None, "seconds": None},
    {"version": "D", "design": "Orchestrator + 2 specialist agents", "right": "33, 33, 33", "safe_not_ideal": 7,
     "wrong": 0, "outside_mandate": 0, "money_wrong": "none", "usd_per_request": 0.00080, "seconds": "~5.4"},
]

PLAIN = {
    "OVER_APPROVAL_THRESHOLD": "Above the amount the owner must approve",
    "AGENT_ASKED_HUMAN": "The agent was unsure and handed it to a person",
    "OVER_MONTHLY_LIMIT": "Would go over this month's limit",
    "PAYEE_NAME_CLOSE_MATCH": "Payee name is close to, but not exactly, the account name",
    "PAYEE_NAME_NO_MATCH": "Payee name does not match the account",
    "NEW_PAYEE": "First payment to this payee",
    "MANDATE_REVOKED": "The owner revoked the mandate",
    "MANDATE_EXPIRED": "The mandate has expired",
    "OVER_BUDGET_TOTAL": "Would go over the mandate's total budget",
    "REFUND_WINDOW_EXPIRED": "Too long since the order to refund",
    "SPLIT_PAYMENT_PATTERN": "Looks like one payment split into smaller ones",
}


def load(p):
    return json.loads((ROOT / p).read_text(encoding="utf-8"))


def latest_b_run():
    runs = sorted(d for d in (ROOT / "var" / "runs").glob("*-B") if (d / "results.jsonl").exists())
    if not runs:
        sys.exit("No Version B run found in var/runs. Run scripts/run_eval.py --version B first.")
    return runs[-1]


def canonical(entry):
    """The exact string audit.py hashes."""
    return json.dumps({k: v for k, v in entry.items() if k != "hash"}, sort_keys=True, ensure_ascii=False, default=str)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=Path)
    run = (ap.parse_args().run or latest_b_run()).resolve()

    emails = {r["request_id"]: r for r in load("data/requests.json")}
    gold_raw = load("gold/gold.json")
    gold = {g["request_id"]: g for g in (gold_raw if isinstance(gold_raw, list) else gold_raw.values())}
    setup = load("data/case_setup.json")
    results = {}
    for line in (run / "results.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            results[r["request_id"]] = r

    decisions = {}
    for f in sorted((run / "audit").glob("RQ-*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                e = json.loads(line)
                if e.get("event") == "DECISION":
                    decisions[e["request_id"]] = e

    requests = []
    for rid in sorted(emails):
        em, res, g, dec = emails[rid], results.get(rid, {}), gold.get(rid, {}), decisions.get(rid)
        reasons = (dec or {}).get("reasons", [])
        proposal = (dec or {}).get("proposal") or res.get("proposal")
        meta = res.get("meta") or {}
        requests.append({
            "request_id": rid, "slice": res.get("slice", g.get("slice")),
            "received_at": em.get("received_at"), "from": em.get("from"),
            "subject": em.get("subject"), "body": em.get("body"),
            "scenario": setup.get(rid),
            "proposal": proposal, "agent_note": (proposal or {}).get("note"),
            "outcome": res.get("got"), "gold_outcome": res.get("gold"), "verdict": res.get("verdict"),
            "reasons": [{"code": r["code"], "plain": PLAIN.get(r["code"], r["code"].replace("_", " ").capitalize()),
                         "detail": r.get("detail")} for r in reasons],
            "payment": (dec or {}).get("payment"),
            "tool_calls": meta.get("tool_calls", []),
            "cost_usd": meta.get("cost_usd"),
            "seconds": meta.get("seconds"),
            "original_audit_hash": (dec or {}).get("hash"),
        })

    log = AuditLog()
    for rq in sorted(requests, key=lambda r: (r["received_at"] or "", r["request_id"])):
        dec = decisions.get(rq["request_id"])
        if dec:
            log.append({k: v for k, v in dec.items() if k not in ("seq", "prev_hash", "hash")})
    assert log.verify()
    audit = [{"seq": e["seq"], "request_id": e.get("request_id"), "outcome": e.get("outcome"),
              "prev_hash": e["prev_hash"], "hash": e["hash"], "hashed_body": canonical(e)} for e in log.entries]

    data = {
        "meta": {"source_run": run.name, "note": "Made-up data only. Hollowbrook Ceramics is fictional.",
                 "hashing": "sha256 over hashed_body (UTF-8). prev_hash of entry 1 is 64 zeros."},
        "mandates": load("data/mandates.json"),
        "requests": requests,
        "audit": audit,
        "results": RESULTS,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    by = {}
    for r in requests:
        by[r["outcome"]] = by.get(r["outcome"], 0) + 1
    print(f"Wrote {OUT.relative_to(ROOT)} from {run.name}: {len(requests)} requests, {len(audit)} audit entries, {by}")


if __name__ == "__main__":
    main()
