"""The bank-side world for one test case: mandates, payees, orders, history.

Each case starts from the same base files plus its own setup (for example "the
EUR mandate was revoked an hour ago"), so cases never leak into each other.
The gold folder is never read here.
"""

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def _load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


@dataclass
class World:
    mandates: dict            # mandate_id -> mandate
    suppliers: dict           # payee_id -> supplier
    staff: set                # emails allowed to instruct transfers
    supplier_contacts: dict   # payee_id -> contact email
    orders: dict              # order_id -> order
    ledger: list              # payments already made
    directory: dict           # account -> registered name (for CoP / VoP)
    sanctions: dict           # the made-up list
    requests: dict            # request_id -> request envelope (sender, time, text)
    spent_before_october: dict = field(default_factory=dict)
    tokens: dict = field(default_factory=dict)       # token_id -> token
    idempotency: dict = field(default_factory=dict)  # key -> (fingerprint, decision)

    def mandate_for(self, currency):
        for m in self.mandates.values():
            if m["currency"] == currency:
                return m
        return None


def load_world(request_id=None):
    contacts = _load("contacts.json")
    world = World(
        mandates={m["mandate_id"]: m for m in _load("mandates.json")},
        suppliers={s["payee_id"]: s for s in _load("suppliers.json")},
        staff={s["email"].lower() for s in contacts["staff"]},
        supplier_contacts={k: v.lower() for k, v in contacts["supplier_contacts"].items()},
        orders={o["order_id"]: o for o in _load("orders.json")},
        ledger=_load("ledger.json"),
        directory={d["account"]: d["registered_name"] for d in _load("payee_directory.json")},
        sanctions=_load("sanctions_list.json"),
        requests={r["request_id"]: r for r in _load("requests.json")},
    )
    if request_id:
        apply_setup(world, _load("case_setup.json").get(request_id, {}))
    return world


def apply_setup(world, setup):
    setup = copy.deepcopy(setup)
    for mid, changes in setup.get("mandate_overrides", {}).items():
        world.mandates[mid].update(changes)
    for row in setup.get("extra_ledger", []):
        row.setdefault("status", "EXECUTED")
        row.setdefault("agent_id", "agent-hb-ops-01")
        world.ledger.append(row)
    world.spent_before_october.update(setup.get("spent_before_october", {}))
