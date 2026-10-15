"""Reason-code table: the only facts the explainer is allowed to state (D2b)."""

import json
from dataclasses import dataclass
from datetime import date
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


class SourceType(StrEnum):
    SCHEME_RULE = "scheme_rule"
    # Our own operational guidance: must be labelled as team guidance, never as a scheme rule (D7).
    TEAM_RUNBOOK = "team_runbook"


def check_sign_off(needs_review: bool, reviewed_by: str | None, reviewed_on: str | None,
                   *, required: bool = True) -> None:
    """Team guidance only counts as approved with a recorded reviewer and date, so approval is auditable.

    required=False (scheme rules) still checks the date format, but doesn't demand a sign-off.
    """
    if reviewed_on is not None:
        try:
            date.fromisoformat(reviewed_on)
        except (TypeError, ValueError):
            raise ValueError("reviewed_on must be a date like 2026-10-15") from None
    if required and not needs_review and not ((reviewed_by or "").strip() and reviewed_on):
        raise ValueError("needs_review is false but reviewed_by and reviewed_on are not both set")


@dataclass(frozen=True)
class TeamRunbook:
    """Our own guidance for a code, kept apart from scheme facts so it can be reviewed and signed off as one block."""
    owner: str
    needs_review: bool
    reviewed_by: str | None
    reviewed_on: str | None
    rails: tuple[Rail, ...]
    route_by_rail: Mapping[Rail, Route]
    rail_notes: Mapping[Rail, str]
    what_to_do_by_rail: Mapping[Rail, str]
    evidence_source_ids: tuple[str, ...]
    note: str


@dataclass(frozen=True)
class ReasonCode:
    code: str
    name: str
    meaning: str
    # rails, route_by_rail and rail_notes merge scheme and team facts, so callers see one table;
    # scheme_rails, team_runbook and rail_source() say where each fact comes from.
    rails: tuple[Rail, ...]
    scheme_rails: tuple[Rail, ...]
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
    team_runbook: TeamRunbook | None

    def route_for(self, rail: Rail) -> Route:
        # Some codes are handled differently per rail (e.g. AM04 on RTP goes to Treasury by team decision).
        return self.route_by_rail.get(rail, self.default_route)

    def what_to_do_for(self, rail: Rail) -> str:
        if self.team_runbook is not None and rail in self.team_runbook.what_to_do_by_rail:
            return self.team_runbook.what_to_do_by_rail[rail]
        return self.baseline_what_to_do

    def rail_source(self, rail: Rail) -> SourceType | None:
        if rail in self.scheme_rails:
            return SourceType.SCHEME_RULE
        if self.team_runbook is not None and rail in self.team_runbook.rails:
            return SourceType.TEAM_RUNBOOK
        return None


def _parse_rails(values: list[str]) -> tuple[Rail, ...]:
    rails = tuple(Rail(r) for r in values)
    if Rail.UNKNOWN in rails:
        raise ValueError("UNKNOWN is not a valid rail in the code table")
    return rails


def _keys_within(mapping: dict, rails: tuple[Rail, ...], what: str) -> None:
    # An override for a rail the code isn't confirmed on would be a fact with no backing.
    extra = {Rail(k) for k in mapping} - set(rails)
    if extra:
        raise ValueError(f"{what} has rails {sorted(extra)} not in its own rails")


def _parse_team_runbook(raw: dict, scheme_rails: tuple[Rail, ...]) -> TeamRunbook:
    owner = (raw.get("owner") or "").strip()
    note = raw.get("note", "")
    rails = _parse_rails(raw["rails"])
    if not owner:
        raise ValueError("team_runbook needs an owner")
    if raw["needs_review"] and not note.strip():
        raise ValueError("team_runbook needs_review is true but note is empty")
    check_sign_off(raw["needs_review"], raw.get("reviewed_by"), raw.get("reviewed_on"))
    # A rail is backed either by a scheme source or by the team, never both, so provenance stays unambiguous.
    overlap = set(rails) & set(scheme_rails)
    if overlap:
        raise ValueError(f"team_runbook rails {sorted(overlap)} are already scheme rails")
    for field in ("route_by_rail", "rail_notes", "what_to_do_by_rail"):
        _keys_within(raw.get(field, {}), rails, f"team_runbook.{field}")
    # MappingProxyType makes the dicts read-only, so a frozen object really can't change.
    return TeamRunbook(
        owner=owner,
        needs_review=raw["needs_review"],
        reviewed_by=raw.get("reviewed_by"),
        reviewed_on=raw.get("reviewed_on"),
        rails=rails,
        route_by_rail=MappingProxyType({Rail(k): Route(v) for k, v in raw.get("route_by_rail", {}).items()}),
        rail_notes=MappingProxyType({Rail(k): v for k, v in raw.get("rail_notes", {}).items()}),
        what_to_do_by_rail=MappingProxyType({Rail(k): v for k, v in raw.get("what_to_do_by_rail", {}).items()}),
        evidence_source_ids=tuple(raw.get("evidence_source_ids", [])),
        note=note,
    )


def _parse_entry(raw: dict) -> ReasonCode:
    scheme_rails = _parse_rails(raw["rails"])
    _keys_within(raw.get("route_by_rail", {}), scheme_rails, "route_by_rail")
    _keys_within(raw.get("rail_notes", {}), scheme_rails, "rail_notes")
    team = _parse_team_runbook(raw["team_runbook"], scheme_rails) if "team_runbook" in raw else None

    route_by_rail = {Rail(k): Route(v) for k, v in raw.get("route_by_rail", {}).items()}
    rail_notes = {Rail(k): v for k, v in raw.get("rail_notes", {}).items()}
    rails = scheme_rails
    if team is not None:
        rails = scheme_rails + team.rails
        route_by_rail |= team.route_by_rail
        rail_notes |= team.rail_notes

    return ReasonCode(
        code=raw["code"],
        name=raw["name"],
        meaning=raw["meaning"],
        rails=rails,
        scheme_rails=scheme_rails,
        category=Category(raw["category"]),
        default_route=Route(raw["default_route"]),
        route_by_rail=MappingProxyType(route_by_rail),
        rail_notes=MappingProxyType(rail_notes),
        baseline_what_happened=raw["baseline_what_happened"],
        baseline_what_to_do=raw["baseline_what_to_do"],
        baseline_customer_message=raw["baseline_customer_message"],
        iso_code_sets=tuple(raw["iso_code_sets"]),
        source_ids=tuple(raw["source_ids"]),
        needs_review=raw["needs_review"],
        review_note=raw["review_note"],
        team_runbook=team,
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
