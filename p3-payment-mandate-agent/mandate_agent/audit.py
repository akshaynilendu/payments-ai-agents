"""Append-only, hash-chained audit log.

Each entry stores the hash of the one before it, so changing or deleting any past
entry breaks every hash after it. This is a simulation of tamper evidence, not
real signing (no private keys), and the README says so.
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
        for e in self.entries:
            if e["prev_hash"] != prev or e["hash"] != _hash({k: v for k, v in e.items() if k != "hash"}):
                return False
            prev = e["hash"]
        return True

    def evidence_pack(self, request_id: str) -> list[dict]:
        """Everything recorded about one request, in order: for a dispute or a complaint."""
        return [e for e in self.entries if e.get("request_id") == request_id]
