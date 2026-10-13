"""Reason-code table: the only facts the explainer is allowed to state (D2b)."""

import json
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "reason_codes.json"


class Rail(StrEnum):
    RTP = "RTP"
    SEPA_INSTANT = "SEPA_INSTANT"
    SEPA_DD = "SEPA_DD"
    # For messages the parser can't place on a rail. Never valid in the code table.
    UNKNOWN = "UNKNOWN"


class Category(StrEnum):
    ACCOUNT = "account"
    FUNDS = "funds"
    MANDATE = "mandate"
    REGULATORY = "regulatory"
    TIMEOUT = "timeout"
    TECHNICAL = "technical"
    FRAUD = "fraud"


class Route(StrEnum):
    FIRST_LINE = "FIRST_LINE"
    DEVELOPER = "DEVELOPER"
    FRAUD = "FRAUD"
    COMPLIANCE = "COMPLIANCE"
    TREASURY = "TREASURY"
    # Triggered by a post-release spike (v2), never by the code alone.
    QC = "QC"


@dataclass(frozen=True)
class ReasonCode:
    code: str
    name: str
    meaning: str
    rails: tuple[Rail, ...]
    category: Category
    default_route: Route
    route_by_rail: Mapping[Rail, Route]
    rail_notes: Mapping[Rail, str]
    baseline_what_happened: str
    baseline_what_to_do: str
    baseline_customer_message: str
    iso_code_sets: tuple[str, ...]
    source_ids: tuple[str, ...]
    needs_review: bool
    review_note: str

    def route_for(self, rail: Rail) -> Route:
        # Some codes mean different things per rail (e.g. AM04 on RTP is a bank liquidity issue).
        return self.route_by_rail.get(rail, self.default_route)


def _parse_entry(raw: dict) -> ReasonCode:
    code = raw["code"]
    rails = tuple(Rail(r) for r in raw["rails"])
    if Rail.UNKNOWN in rails:
        raise ValueError(f"{code}: UNKNOWN is not a valid rail in the code table")
    # MappingProxyType makes the dicts read-only, so a frozen ReasonCode really can't change.
    return ReasonCode(
        code=code,
        name=raw["name"],
        meaning=raw["meaning"],
        rails=rails,
        category=Category(raw["category"]),
        default_route=Route(raw["default_route"]),
        route_by_rail=MappingProxyType(
            {Rail(k): Route(v) for k, v in raw.get("route_by_rail", {}).items()}
        ),
        rail_notes=MappingProxyType(
            {Rail(k): v for k, v in raw.get("rail_notes", {}).items()}
        ),
        baseline_what_happened=raw["baseline_what_happened"],
        baseline_what_to_do=raw["baseline_what_to_do"],
        baseline_customer_message=raw["baseline_customer_message"],
        iso_code_sets=tuple(raw["iso_code_sets"]),
        source_ids=tuple(raw["source_ids"]),
        needs_review=raw["needs_review"],
        review_note=raw["review_note"],
    )


def load_codes(path: Path = DEFAULT_PATH) -> dict[str, ReasonCode]:
    """Load and validate the table. Fails loudly: a bad table must stop startup, not mislead customers."""
    data = json.loads(path.read_text(encoding="utf-8"))
    codes: dict[str, ReasonCode] = {}
    for raw in data["codes"]:
        try:
            entry = _parse_entry(raw)
        except (KeyError, ValueError) as e:
            raise ValueError(f"Invalid entry {raw.get('code', '?')} in {path}: {e}") from e
        if entry.code in codes:
            raise ValueError(f"Duplicate code {entry.code} in {path}")
        codes[entry.code] = entry
    return codes


@cache
def _default_codes() -> dict[str, ReasonCode]:
    return load_codes()


def lookup(code: str | None) -> ReasonCode | None:
    """None means 'not in our table': the caller must escalate, never let the AI improvise."""
    if not code:
        return None
    return _default_codes().get(code.strip().upper())


def all_codes() -> list[ReasonCode]:
    return list(_default_codes().values())
