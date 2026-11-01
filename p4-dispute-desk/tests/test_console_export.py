"""The console file is one hash chain, in the order the disputes were opened."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_exported_chain_verifies():
    subprocess.run([sys.executable, str(ROOT / "scripts" / "export_console_data.py")], check=True)
    data = json.loads((ROOT / "console" / "console_data.json").read_text(encoding="utf-8"))
    assert len(data["disputes"]) == 30
    assert len(data["audit"]) == 30
    assert data["meta"]["source_run"].endswith("-B")
    assert {row["version"] for row in data["results"]} == {"A", "B"}
    opened = [row["opened_at"] for row in data["audit"]]
    assert opened == sorted(opened)
    prev = "0" * 64
    for entry in data["audit"]:
        body = json.loads(entry["hashed_body"])
        assert body["prev_hash"] == prev == entry["prev_hash"]
        assert hashlib.sha256(entry["hashed_body"].encode("utf-8")).hexdigest() == entry["hash"]
        prev = entry["hash"]
    sample = next(row for row in data["disputes"] if row["dispute_id"] == "DP-01")
    assert sample["cardholder_message"]
    assert sample["respond_by"]
    assert sample["proposal"] and sample["decision"]
    assert sample["evidence_pack"]
    assert sample["money"]["amount"] > 0
