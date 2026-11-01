"""Append-only, hash-chained audit log.

Same construction as Project 3's mandate_agent/audit.py: each entry stores the
hash of the one before it, so editing a past entry breaks every hash after it.
This is tamper evidence, not a real signature (no private keys).
"""

import hashlib
import json


def _hash(entry: dict) -> str:
    body = json.dumps(entry, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class AuditLog:
    def __init__(self):
        self.entries: list[dict] = []

    def append(self, record: dict) -> str:
        prev = self.entries[-1]["hash"] if self.entries else "0" * 64
        entry = {"seq": len(self.entries) + 1, "prev_hash": prev, **record}
        entry["hash"] = _hash({k: v for k, v in entry.items() if k != "hash"})
        self.entries.append(entry)
        return entry["hash"]

    def verify(self) -> bool:
        prev = "0" * 64
        for entry in self.entries:
            if entry["prev_hash"] != prev or entry["hash"] != _hash({k: v for k, v in entry.items() if k != "hash"}):
                return False
            prev = entry["hash"]
        return True

    def for_dispute(self, dispute_id: str) -> list[dict]:
        return [entry for entry in self.entries if entry.get("dispute_id") == dispute_id]
