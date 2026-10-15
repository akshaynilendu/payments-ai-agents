import json
import re

import pytest

from explainer.codes import Stage, all_codes
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


def test_rtp_next_steps_are_team_runbook_owned_by_akshay():
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
    # An unsigned runbook must still be under review; approval needs a sign-off (tested below).
    raw = _valid_raw() | {"source_type": "team_runbook", "owner": "Akshay",
                          "source_url": "DECISIONS.md#d7",
                          "needs_review": True, "review_note": "awaiting sign-off"}
    assert load_passages(_write(tmp_path, [raw]))[0].owner == "Akshay"


def test_loader_rejects_missing_field(tmp_path):
    raw = _valid_raw()
    del raw["source_section"]
    with pytest.raises(ValueError, match="Invalid passage KB-SCTI-AC04-01"):
        load_passages(_write(tmp_path, [raw]))


# --- sign-off: approval needs a recorded reviewer and date -------------------

def _runbook_raw(**fields):
    return _valid_raw() | {"source_type": "team_runbook", "owner": "Akshay",
                           "source_url": "DECISIONS.md#d7"} | fields


@pytest.mark.parametrize(
    "fields, message",
    [
        ({"needs_review": False, "reviewed_by": None, "reviewed_on": None}, "reviewed_by and reviewed_on"),
        ({"needs_review": False, "reviewed_by": "Akshay", "reviewed_on": None}, "reviewed_by and reviewed_on"),
        ({"needs_review": False, "reviewed_by": None, "reviewed_on": "2026-10-15"}, "reviewed_by and reviewed_on"),
        ({"needs_review": False, "reviewed_by": "Akshay", "reviewed_on": "yesterday"}, "must be a date"),
    ],
)
def test_loader_rejects_runbook_approval_without_sign_off(tmp_path, fields, message):
    with pytest.raises(ValueError, match=f"Invalid passage KB-SCTI-AC04-01.*{message}"):
        load_passages(_write(tmp_path, [_runbook_raw(**fields)]))


def test_loader_accepts_signed_off_runbook(tmp_path):
    raw = _runbook_raw(needs_review=False, reviewed_by="Akshay", reviewed_on="2026-10-15")
    assert load_passages(_write(tmp_path, [raw]))[0].reviewed_on == "2026-10-15"


def test_scheme_rule_needs_no_sign_off_but_dates_must_be_valid(tmp_path):
    # Scheme passages are checked against their source, not signed off by the team.
    assert load_passages(_write(tmp_path, [_valid_raw()]))[0].reviewed_by is None
    with pytest.raises(ValueError, match="must be a date"):
        load_passages(_write(tmp_path, [_valid_raw() | {"reviewed_on": "soon"}]))


def test_every_passage_has_sign_off_fields():
    raw = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))["passages"]
    for p in raw:
        assert "reviewed_by" in p and "reviewed_on" in p, p["id"]


SIGNED_OFF_PASSAGES = {
    "KB-RTP-AC03-01", "KB-RTP-AC04-01", "KB-RTP-AC06-01", "KB-RTP-AG01-01", "KB-RTP-AM04-01",
    "KB-RTP-DS24-01", "KB-SCTI-GEN-02", "KB-ALL-GEN-03",
}


def test_signed_off_passages_are_exactly_the_approved_ones():
    # Sign-off is Akshay's call; this list changes deliberately, never as a side effect.
    signed = {p.id for p in all_passages() if p.reviewed_by}
    assert signed == SIGNED_OFF_PASSAGES
    for p in all_passages():
        if p.id in signed:
            assert (p.reviewed_by, p.reviewed_on, p.needs_review) == ("Akshay", "2026-10-15", False)


def test_review_queue_is_empty():
    assert [p.id for p in all_passages() if p.needs_review] == []


def test_approved_scheme_passage_with_review_note_needs_sign_off(tmp_path):
    raw = _valid_raw() | {"needs_review": False, "review_note": "checked by hand", "reviewed_by": None}
    with pytest.raises(ValueError, match="reviewed_by and reviewed_on"):
        load_passages(_write(tmp_path, [raw]))


def test_approved_scheme_passage_with_only_a_caveat_needs_no_sign_off(tmp_path):
    # Caveats are context, not review work, so they don't demand a reviewer.
    raw = _valid_raw() | {"needs_review": False, "review_note": "", "caveat": "source is from 2023"}
    assert load_passages(_write(tmp_path, [raw]))[0].caveat == "source is from 2023"


def test_dated_tch_sources_carry_a_caveat():
    for pid in ["KB-RTP-GEN-02", "KB-RTP-GEN-03"]:
        assert "November 2023" in next(p for p in all_passages() if p.id == pid).caveat


def test_scti_recall_window_cites_the_rulebook_section():
    p = next(p for p in all_passages() if p.id == "KB-SCTI-GEN-02")
    assert "4.3.2.2" in p.source_section
    assert "10 banking business days" in p.text and "13 months" in p.text


def test_amlr_passage_cites_no_article_number():
    p = next(p for p in all_passages() if p.id == "KB-ALL-GEN-03")
    assert not re.search(r"Art(icle|\.)\s*\d", p.text)
    assert "10 July 2027" in p.text


# --- mandatory guardrails -----------------------------------------------------

def test_only_the_tipping_off_guardrail_is_mandatory():
    assert [p.id for p in all_passages() if p.mandatory] == ["KB-ALL-GEN-01"]


def test_loader_rejects_mandatory_passage_without_codes(tmp_path):
    # Every stage listed, so the codes check is the one that fires.
    raw = _valid_raw() | {"mandatory": True, "codes": [],
                          "stages": ["REJECT", "RETURN", "RECALL", "RECALL_ANSWER"]}
    with pytest.raises(ValueError, match="mandatory passage must list the codes"):
        load_passages(_write(tmp_path, [raw]))


def test_every_all_rail_passage_names_the_codes_it_applies_to():
    # An ALL passage with no codes would match every code on every rail.
    for p in all_passages():
        if p.rail is KbRail.ALL:
            assert p.codes, p.id


# --- stages (D10) ---------------------------------------------------------------

@pytest.mark.parametrize(
    "stages, message",
    [
        ([], "stages is empty"),
        (["LATER"], "LATER"),
        (["UNKNOWN"], "not valid on a passage"),
        (["NOT_A_FAILURE"], "not valid on a passage"),
        (["REJECT", "PENDING"], "not valid on a passage"),
    ],
)
def test_loader_rejects_invalid_stages(tmp_path, stages, message):
    with pytest.raises(ValueError, match=f"Invalid passage KB-SCTI-AC04-01.*{message}"):
        load_passages(_write(tmp_path, [_valid_raw() | {"stages": stages}]))


def test_loader_rejects_mandatory_passage_missing_a_stage(tmp_path):
    raw = _valid_raw() | {"mandatory": True, "stages": ["REJECT", "RETURN", "RECALL"]}
    with pytest.raises(ValueError, match="mandatory passage must list every stage"):
        load_passages(_write(tmp_path, [raw]))


def test_no_recall_or_return_passage_is_tagged_reject():
    for p in all_passages():
        if p.topic is Topic.RECALL_RETURN:
            assert Stage.REJECT not in p.stages, p.id


def test_frad_passages_are_recall_only():
    for p in all_passages():
        if "FRAD" in p.codes:
            assert p.stages == (Stage.RECALL,), p.id


def test_rtp_runbook_next_steps_are_reject_only():
    for p in all_passages():
        if p.source_type is SourceType.TEAM_RUNBOOK:
            assert p.stages == (Stage.REJECT,), p.id
