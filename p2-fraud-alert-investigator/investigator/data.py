"""Read-only access to the made-up input data. The gold answers are out of reach on purpose (D8)."""

import json
from datetime import datetime
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from investigator.schema import Outcome, Rail

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
GOLD_DIR = PROJECT_ROOT / "gold"

_FROZEN = ConfigDict(extra="forbid", frozen=True)


class Customer(BaseModel):
    model_config = _FROZEN
    customer_id: str
    display_name: str
    home_rail: Rail
    segment: Literal["RETAIL", "MICRO_ENTERPRISE", "CORPORATE"]
    age_band: str  # vulnerability only, never a fraud signal (D6)
    usual_amount: Decimal
    currency: str
    usual_payee_ids: list[str]
    usual_hours: tuple[int, int]  # local hours [start, end)
    vulnerability_flags: list[str]


class LoginSession(BaseModel):
    model_config = _FROZEN
    session_id: str
    customer_id: str
    started_at: datetime
    device_id: str
    new_device: bool
    sim_swap_at: datetime | None
    remote_access_tool: bool
    on_call_during_session: bool
    typing_hesitation: bool


class Payee(BaseModel):
    model_config = _FROZEN
    payee_id: str
    name: str  # data only (D7)
    account: str
    scheme: Literal["UK", "SEPA"]
    account_age_days: int
    inbound_unrelated_payers_30d: int
    money_out_median_minutes: int
    prior_fraud_reports: int
    name_check: Literal["MATCH", "CLOSE_MATCH", "NO_MATCH"]


class PriorPayment(BaseModel):
    model_config = _FROZEN
    paid_at: datetime
    amount: Decimal


class Alert(BaseModel):
    model_config = _FROZEN
    alert_id: str
    payment_id: str
    customer_id: str
    session_id: str
    payee_id: str
    amount: Decimal
    currency: str
    rail: Rail
    reference: str  # data only (D7)
    received_at: datetime
    trigger_reason: str
    recent_payments_to_payee: list[PriorPayment]


class PastCase(BaseModel):
    model_config = _FROZEN
    case_id: str
    closed_at: datetime
    customer_id: str
    payee_id: str
    receiving_account: str
    outcome: Outcome
    signals: list[str]


class Dataset(BaseModel):
    model_config = _FROZEN
    customers: dict[str, Customer]
    sessions: dict[str, LoginSession]
    payees: dict[str, Payee]
    past_cases: list[PastCase]
    alerts: list[Alert]


def _read(data_dir: Path, name: str):
    path = (data_dir / name).resolve()
    # Versions must never see the answers: refuse anything inside gold/, however the path is spelled.
    if path == GOLD_DIR.resolve() or GOLD_DIR.resolve() in path.parents:
        raise PermissionError("the gold answers are not readable by the investigator")
    return json.loads(path.read_text(encoding="utf-8"))


def load_dataset(data_dir: Path = DATA_DIR) -> Dataset:
    return _load(Path(data_dir).resolve())


@cache
def _load(data_dir: Path) -> Dataset:
    return Dataset(
        customers={c["customer_id"]: c for c in _read(data_dir, "customers.json")},
        sessions={s["session_id"]: s for s in _read(data_dir, "devices_logins.json")},
        payees={p["payee_id"]: p for p in _read(data_dir, "payees.json")},
        past_cases=_read(data_dir, "past_cases.json"),
        alerts=_read(data_dir, "alerts.json"),
    )
