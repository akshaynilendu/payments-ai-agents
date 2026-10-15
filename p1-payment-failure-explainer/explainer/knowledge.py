"""Knowledge base passages (D7): the only rulebook facts the explainer may use besides the code table."""

import json
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from pathlib import Path

from explainer.codes import all_codes

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "knowledge" / "passages.json"
MAX_WORDS = 150


class KbRail(StrEnum):
    # Same values as codes.Rail so passages and codes match without translation; ALL = applies to every rail.
    RTP = "RTP"
    SEPA_INSTANT = "SEPA_INSTANT"
    SEPA_DD = "SEPA_DD"
    ALL = "ALL"


class Topic(StrEnum):
    MEANING = "meaning"
    NEXT_STEP = "next_step"
    WHO_ACTS = "who_acts"
    TIME_LIMIT = "time_limit"
    RECALL_RETURN = "recall_return"
    CUSTOMER_MESSAGE = "customer_message"


class SourceType(StrEnum):
    SCHEME_RULE = "scheme_rule"
    # Our own operational guidance: the AI must label it as team guidance, never as a scheme rule (D7).
    TEAM_RUNBOOK = "team_runbook"


@dataclass(frozen=True)
class Passage:
    id: str
    rail: KbRail
    codes: tuple[str, ...]
    topic: Topic
    source_type: SourceType
    owner: str | None
    text: str
    source_url: str
    source_section: str
    needs_review: bool
    review_note: str


def _parse_entry(raw: dict, known_codes: set[str]) -> Passage:
    passage = Passage(
        id=raw["id"],
        rail=KbRail(raw["rail"]),
        codes=tuple(raw["codes"]),
        topic=Topic(raw["topic"]),
        source_type=SourceType(raw["source_type"]),
        owner=raw.get("owner"),
        text=raw["text"],
        source_url=raw["source_url"],
        source_section=raw["source_section"],
        needs_review=raw["needs_review"],
        review_note=raw.get("review_note", ""),
    )
    # A passage about a code we don't know can never be retrieved correctly, so it is a data error.
    unknown = [c for c in passage.codes if c not in known_codes]
    if unknown:
        raise ValueError(f"unknown code(s) {unknown}")
    if not passage.source_url.strip():
        raise ValueError("empty source_url")
    if passage.source_type is SourceType.SCHEME_RULE and not passage.source_url.startswith("https://"):
        raise ValueError("scheme_rule needs an https source_url")
    if passage.source_type is SourceType.TEAM_RUNBOOK and not (passage.owner or "").strip():
        raise ValueError("team_runbook needs an owner")
    words = len(passage.text.split())
    if words > MAX_WORDS:
        raise ValueError(f"text has {words} words (max {MAX_WORDS})")
    if passage.needs_review and not passage.review_note.strip():
        raise ValueError("needs_review is true but review_note is empty")
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
