"""Knowledge base passages (D7): the only rulebook facts the explainer may use besides the code table."""

import json
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from pathlib import Path

# SourceType lives in codes.py because the code table uses it too; re-exported here for passage users.
from explainer.codes import FAILURE_STAGES, SourceType, Stage, all_codes, check_sign_off

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "knowledge" / "passages.json"
MAX_WORDS = 150


class KbRail(StrEnum):
    # Same values as codes.Rail so passages and codes match without translation; ALL = applies to every rail.
    RTP = "RTP"
    SEPA_INSTANT = "SEPA_INSTANT"
    SEPA_DD = "SEPA_DD"
    ALL = "ALL"


# D18: runbook families for ISO codes outside our table, so the AI gets team guidance on what to do next.
CODE_FAMILIES = ("AC", "AG", "AM", "AB", "BE", "ROUTING", "MD", "MS_SL")


def family_of(code: str | None) -> str | None:
    """The runbook family of an ISO reason code, or None when we have no guidance for its family."""
    code = (code or "").strip().upper()
    if code in ("CNOR", "DNOR") or code.startswith("RC"):
        return "ROUTING"  # bank or BIC routing problems
    if code[:2] in ("MS", "SL"):
        return "MS_SL"  # reason withheld or bank-specific service: never guess
    return code[:2] if code[:2] in ("AC", "AG", "AM", "AB", "BE", "MD") else None


class Topic(StrEnum):
    MEANING = "meaning"
    NEXT_STEP = "next_step"
    WHO_ACTS = "who_acts"
    TIME_LIMIT = "time_limit"
    RECALL_RETURN = "recall_return"
    CUSTOMER_MESSAGE = "customer_message"


@dataclass(frozen=True)
class Passage:
    id: str
    rail: KbRail
    codes: tuple[str, ...]
    # Lifecycle stages where this advice is true; retrieval filters on it (D10).
    stages: tuple[Stage, ...]
    # Code families this passage guides (D18). Such passages name no codes and only serve codes outside the table.
    families: tuple[str, ...]
    topic: Topic
    # A guardrail for its codes: always returned for them, never ranked out (D8).
    mandatory: bool
    source_type: SourceType
    owner: str | None
    text: str
    source_url: str
    source_section: str
    needs_review: bool
    reviewed_by: str | None
    reviewed_on: str | None
    review_note: str
    # True-but-may-age context (e.g. "source is a 2023 newsletter"); unlike review_note, it asks for no action.
    caveat: str


def _parse_entry(raw: dict, known_codes: set[str]) -> Passage:
    passage = Passage(
        id=raw["id"],
        rail=KbRail(raw["rail"]),
        codes=tuple(raw["codes"]),
        stages=tuple(Stage(s) for s in raw["stages"]),
        families=tuple(raw.get("families", [])),
        topic=Topic(raw["topic"]),
        mandatory=raw.get("mandatory", False),
        source_type=SourceType(raw["source_type"]),
        owner=raw.get("owner"),
        text=raw["text"],
        source_url=raw["source_url"],
        source_section=raw["source_section"],
        needs_review=raw["needs_review"],
        reviewed_by=raw.get("reviewed_by"),
        reviewed_on=raw.get("reviewed_on"),
        review_note=raw.get("review_note", ""),
        caveat=raw.get("caveat", ""),
    )
    # A passage about a code we don't know can never be retrieved correctly, so it is a data error.
    unknown = [c for c in passage.codes if c not in known_codes]
    if unknown:
        raise ValueError(f"unknown code(s) {unknown}")
    unknown_families = [f for f in passage.families if f not in CODE_FAMILIES]
    if unknown_families:
        raise ValueError(f"unknown families {unknown_families}")
    if passage.families and (passage.codes or passage.rail is not KbRail.ALL):
        # A family passage is for codes outside the table, on any rail; codes would make it match table codes.
        raise ValueError("a family passage names no codes and has rail ALL")
    if not passage.stages:
        raise ValueError("stages is empty")
    # NOT_A_FAILURE, PENDING and UNKNOWN describe a message, not a situation advice can be written for.
    invalid = [s.value for s in passage.stages if s not in FAILURE_STAGES]
    if invalid:
        raise ValueError(f"stages {invalid} are not valid on a passage")
    if passage.mandatory and set(passage.stages) != set(FAILURE_STAGES):
        raise ValueError("mandatory passage must list every stage")
    # A guardrail with no codes would apply to everything, or to nothing; either way it's a mistake.
    if passage.mandatory and not passage.codes:
        raise ValueError("mandatory passage must list the codes it guards")
    if not passage.source_url.strip():
        raise ValueError("empty source_url")
    # Scheme rules and regulations are public sources, so they must link to them.
    if passage.source_type in (SourceType.SCHEME_RULE, SourceType.REGULATION) \
            and not passage.source_url.startswith("https://"):
        raise ValueError(f"{passage.source_type.value} needs an https source_url")
    if passage.source_type is SourceType.TEAM_RUNBOOK and not (passage.owner or "").strip():
        raise ValueError("team_runbook needs an owner")
    words = len(passage.text.split())
    if words > MAX_WORDS:
        raise ValueError(f"text has {words} words (max {MAX_WORDS})")
    if passage.needs_review and not passage.review_note.strip():
        raise ValueError("needs_review is true but review_note is empty")
    # A review note on an approved passage means someone reviewed something, so record who and when.
    check_sign_off(passage.needs_review, passage.reviewed_by, passage.reviewed_on,
                   required=passage.source_type is SourceType.TEAM_RUNBOOK or bool(passage.review_note.strip()))
    return passage


def load_passages(path: Path = DEFAULT_PATH) -> tuple[Passage, ...]:
    """Load and validate. Fails loudly: a bad passage would become a 'fact' the AI repeats to customers."""
    data = json.loads(path.read_text(encoding="utf-8"))
    known_codes = {c.code for c in all_codes()}
    passages: dict[str, Passage] = {}
    for raw in data["passages"]:
        try:
            passage = _parse_entry(raw, known_codes)
        except (KeyError, ValueError) as e:
            raise ValueError(f"Invalid passage {raw.get('id', '?')} in {path}: {e}") from e
        if passage.id in passages:
            raise ValueError(f"Duplicate passage id {passage.id} in {path}")
        passages[passage.id] = passage
    return tuple(passages.values())


@cache
def all_passages() -> tuple[Passage, ...]:
    return load_passages()
