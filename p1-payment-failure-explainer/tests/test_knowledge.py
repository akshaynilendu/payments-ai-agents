import json
import re

import pytest

from explainer.codes import all_codes
from explainer.knowledge import (
    DEFAULT_PATH, KbRail, SourceType, Topic, all_passages, load_passages,
)

# Codes that deliberately have no next_step passage. Every entry needs a reason; no silent skips.
COVERAGE_EXCEPTIONS = {
    "FR01": "No public source describes FR01 on our rails (no EPC or open TCH use found).",
    "FRAD": "No rail confirmed for pacs.002/pacs.004; in SEPA Instant it is a recall reason "
            "(see KB-SCTI-FRAD-01), and its FRAUD route comes from the code table.",
}

ID_PREFIX_FOR_RAIL = {
    KbRail.SEPA_INSTANT: "KB-SCTI-",
    KbRail.SEPA_DD: "KB-SDD-",
    KbRail.RTP: "KB-RTP-",
    KbRail.ALL: "KB-ALL-",
}
ID_PATTERN = re.compile(r"KB-(SCTI|SDD|RTP|ALL)-([A-Z0-9]{4}|GEN)-\d{2}")


def _next_step_passages_for(code: str, rail: str) -> list:
    return [p for p in all_passages()
            if p.topic is Topic.NEXT_STEP and code in p.codes and p.rail in (rail, KbRail.ALL)]


# --- coverage ---------------------------------------------------------------

@pytest.mark.parametrize(
    "code, rail",
    [(c.code, r) for c in all_codes() if c.code not in COVERAGE_EXCEPTIONS for r in c.rails],
    ids=lambda v: str(v),
)
def test_every_valid_code_rail_pair_has_a_next_step_passage(code, rail):
    assert _next_step_passages_for(code, rail), f"no next_step passage for {code} on {rail}"


def test_every_code_is_covered_or_explicitly_excepted():
    # Catches codes with no confirmed rail, which the pair test above cannot see.
    for entry in all_codes():
        has_any = any(p.topic is Topic.NEXT_STEP and entry.code in p.codes for p in all_passages())
        assert has_any or entry.code in COVERAGE_EXCEPTIONS, entry.code


@pytest.mark.parametrize("code, reason", COVERAGE_EXCEPTIONS.items())
def test_every_exception_is_still_needed(code, reason):
    # A stale exception would hide a gap if the code later gains a rail.
    assert reason.strip()
    assert code in {c.code for c in all_codes()}
    assert not any(p.topic is Topic.NEXT_STEP and code in p.codes for p in all_passages())


# --- data quality of the real file -----------------------------------------

def test_knowledge_base_size_matches_d7():
    assert 35 <= len(all_passages()) <= 50


@pytest.mark.parametrize("passage", all_passages(), ids=lambda p: p.id)
def test_passage_quality(passage):
    words = len(passage.text.split())
    assert 60 <= words <= 150, f"{words} words"
    assert ID_PATTERN.fullmatch(passage.id)
    assert passage.id.startswith(ID_PREFIX_FOR_RAIL[passage.rail])
    assert passage.source_section.strip()


@pytest.mark.parametrize("passage", all_passages(), ids=lambda p: p.id)
def test_runbook_is_labelled_as_team_guidance(passage):
    # D7: runbook guidance must never read like a scheme rule, and vice versa.
    labelled = passage.text.startswith("Team guidance, not a scheme rule")
    assert labelled == (passage.source_type is SourceType.TEAM_RUNBOOK)


def test_rtp_next_steps_are_team_runbook_awaiting_sign_off():
    rtp_steps = [p for p in all_passages() if p.rail is KbRail.RTP and p.topic is Topic.NEXT_STEP]
    assert rtp_steps
    for p in rtp_steps:
        assert p.source_type is SourceType.TEAM_RUNBOOK
        assert p.owner == "Akshay"


def test_no_gated_tch_documents_are_cited():
    # Only open TCH web pages are allowed; the media/.ashx links are gated documentation.
    for p in all_passages():
        assert "/-/media/" not in p.source_url, p.id


# --- loader rejects bad data -------------------------------------------------

def _valid_raw():
    # Start from a real passage so each test breaks exactly one thing.
    passages = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))["passages"]
    return next(p for p in passages if p["id"] == "KB-SCTI-AC04-01")


def _write(tmp_path, passages):
    path = tmp_path / "passages.json"
    path.write_text(json.dumps({"passages": passages}), encoding="utf-8")
    return path


def test_loader_rejects_duplicate_ids(tmp_path):
    with pytest.raises(ValueError, match="Duplicate passage id"):
        load_passages(_write(tmp_path, [_valid_raw(), _valid_raw()]))


@pytest.mark.parametrize(
    "bad, message",
    [
        ({"rail": "FEDWIRE"}, "FEDWIRE"),
        ({"topic": "gossip"}, "gossip"),
        ({"source_type": "blog"}, "blog"),
        ({"codes": ["ZZ99"]}, "unknown code"),
        ({"source_url": "  "}, "empty source_url"),
        ({"source_url": "http://example.org"}, "https"),
        ({"source_url": "DECISIONS.md#d7"}, "https"),
        ({"source_type": "team_runbook", "owner": None}, "needs an owner"),
        ({"source_type": "team_runbook", "owner": " "}, "needs an owner"),
        ({"text": "word " * 151}, "151 words"),
        ({"needs_review": True, "review_note": ""}, "review_note"),
    ],
)
def test_loader_rejects_invalid_passage(tmp_path, bad, message):
    with pytest.raises(ValueError, match=f"Invalid passage KB-SCTI-AC04-01.*{message}"):
        load_passages(_write(tmp_path, [_valid_raw() | bad]))


def test_loader_accepts_team_runbook_with_owner_and_local_link(tmp_path):
    raw = _valid_raw() | {"source_type": "team_runbook", "owner": "Akshay",
                          "source_url": "DECISIONS.md#d7"}
    assert load_passages(_write(tmp_path, [raw]))[0].owner == "Akshay"


def test_loader_rejects_missing_field(tmp_path):
    raw = _valid_raw()
    del raw["source_section"]
    with pytest.raises(ValueError, match="Invalid passage KB-SCTI-AC04-01"):
        load_passages(_write(tmp_path, [raw]))
