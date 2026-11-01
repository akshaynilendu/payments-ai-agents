"""The generated files match the brief: 30 disputes, the mix, the six traps, Project 3 hashes."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from generate_data import main  # noqa: E402


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_world_matches_the_brief():
    main()
    disputes = load("data/disputes.json")
    gold = load("gold/gold.json")
    orders = {o["order_id"]: o for o in load("data/orders.json")}
    refunds = load("data/refunds.json")
    fees = load("data/fees.json")
    by_g = {g["id"]: g for g in gold}

    assert [d["id"] for d in disputes] == [f"DP-{i:02d}" for i in range(1, 31)]
    assert [g["id"] for g in gold] == [d["id"] for d in disputes]
    slices = {}
    for g in gold:
        slices[g["slice"]] = slices.get(g["slice"], 0) + 1
        assert "\n" not in g["why"]
    assert slices == {"textbook": 8, "messy": 4, "tricky": 12, "trap": 6}
    assert {g["tag"] for g in gold if g.get("tag")} == {
        "deadline_tomorrow", "delivered_elsewhere", "already_refunded_p3",
        "fraud_with_history", "below_fight_cost", "two_real_orders",
    }
    assert by_g["DP-07"]["outcome"] == "ACCEPT"
    assert by_g["DP-22"]["outcome"] == "ACCEPT"
    assert by_g["DP-25"]["outcome"] == "FIGHT"
    assert by_g["DP-25"]["priority"] == "SUBMIT_TODAY"
    assert by_g["DP-26"]["outcome"] == "ACCEPT"
    assert by_g["DP-27"]["outcome"] == "ALREADY_REFUNDED"
    assert by_g["DP-28"]["outcome"] == "FIGHT"
    assert by_g["DP-28"]["priority"] == "NORMAL"
    assert by_g["DP-29"]["outcome"] == "ACCEPT"
    assert by_g["DP-30"]["outcome"] == "FIGHT"
    assert {g["priority"] for g in gold} == {"SUBMIT_TODAY", "NORMAL"}
    assert sum(1 for g in gold if g["priority"] == "SUBMIT_TODAY") == 1
    disputed = orders["ORD-1128"]
    prior = orders["ORD-1088"]
    assert disputed["card_id"] == prior["card_id"]
    shared = sum(1 for field in ("ip_address", "device_id", "account_login") if disputed[field] == prior[field])
    assert shared >= 1 and disputed["ship_to"] == prior["ship_to"]
    assert orders["ORD-1107"]["ip_address"].startswith("203.0.113.")
    assert fees["dispute_fee"] == {"GBP": 15.0, "EUR": 15.0}
    assert fees["fight_cost_estimate"] == {"GBP": 25.0, "EUR": 25.0}
    assert fees["desk_as_of"] == "2026-11-16"
    assert next(d["respond_by"] for d in disputes if d["id"] == "DP-25") == "2026-11-17"
    assert orders["ORD-2016"]["source"] == "p3"
    giulia = next(r for r in refunds if r["order_id"] == "ORD-2016")
    assert giulia["p3_ledger_id"] == "L-0008"
    assert giulia["p3_audit"]["request_id"] == "RQ-40"
    assert len(giulia["p3_audit"]["hash"]) == 64
    assert "outcome" not in disputes[0]
    assert "slice" not in disputes[0]
