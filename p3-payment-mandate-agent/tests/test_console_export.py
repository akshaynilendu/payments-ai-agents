import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_exported_chain_verifies():
    subprocess.run([sys.executable, str(ROOT / "scripts" / "export_console_data.py")], check=True)
    data = json.loads((ROOT / "console" / "console_data.json").read_text(encoding="utf-8"))
    assert len(data["requests"]) == 40
    prev = "0" * 64
    for e in data["audit"]:
        body = json.loads(e["hashed_body"])
        assert body["prev_hash"] == prev == e["prev_hash"]
        assert hashlib.sha256(e["hashed_body"].encode("utf-8")).hexdigest() == e["hash"]
        prev = e["hash"]
