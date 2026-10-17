import json
import re

import pytest

from explainer.codes import DEFAULT_PATH, Rail, Route, SourceType, all_codes, load_codes, lookup

# D2c: baseline text must never promise timings or outcomes.
TIMING_OR_PROMISE = re.compile(
    r"\b(\d+|days?|hours?|minutes?|within|guarantee\w*|will be (credited|refunded|returned))\b",
    re.IGNORECASE,
)


# --- lookup -----------------------------------------------------------------

def test_known_code_returns_its_details():
    ac04 = lookup("AC04")
    assert ac04 is not None
    assert ac04.name == "Closed Account Number"
    assert set(ac04.rails) == {Rail.RTP, Rail.SEPA_INSTANT, Rail.SEPA_DD}
    assert ac04.default_route == Route.FIRST_LINE


def test_lookup_ignores_case_and_spaces():
    assert lookup(" ac04 ") == lookup("AC04")


@pytest.mark.parametrize("code", ["CNOR", "ZZ99", "", "   ", None])
def test_unknown_or_empty_code_returns_none(code):
    assert lookup(code) is None


# --- routing ----------------------------------------------------------------

@pytest.mark.parametrize(
    "code, rail, expected",
    [
        ("AM04", Rail.RTP, Route.TREASURY),
        ("AM04", Rail.SEPA_DD, Route.FIRST_LINE),
        ("AG01", Rail.RTP, Route.DEVELOPER),
        ("AG01", Rail.SEPA_INSTANT, Route.FIRST_LINE),
        ("RR04", Rail.SEPA_DD, Route.COMPLIANCE),
        ("FRAD", Rail.SEPA_INSTANT, Route.FRAUD),
        ("AB05", Rail.SEPA_INSTANT, Route.FIRST_LINE),  # D14: a single timeout is a customer problem
    ],
)
def test_route_for_rail(code, rail, expected):
    assert lookup(code).route_for(rail) == expected


# --- table integrity --------------------------------------------------------

def test_table_has_expected_codes():
    expected = {"AC01", "AC03", "AC04", "AC06", "AG01", "AM04", "AM05", "AB05",
                "DS24", "MD01", "MD06", "MS02", "MS03", "RR04", "FRAD", "FR01"}
    assert {c.code for c in all_codes()} == expected


@pytest.mark.parametrize("entry", all_codes(), ids=lambda c: c.code)
def test_entry_is_complete_and_consistent(entry):
    for text in (entry.name, entry.meaning, entry.baseline_what_happened,
                 entry.baseline_what_to_do, entry.baseline_customer_message):
        assert text.strip()
    # A code with no confirmed rail is a guess unless a human has been told why.
    if not entry.rails:
        assert entry.needs_review
    if entry.needs_review:
        assert entry.review_note.strip()
    # Overrides and notes only make sense for rails the code is confirmed on.
    assert set(entry.route_by_rail) <= set(entry.rails)
    assert set(entry.rail_notes) <= set(entry.rails)
    assert set(entry.iso_code_sets) <= {"ExternalStatusReason1Code", "ExternalReturnReason1Code"}


@pytest.mark.parametrize("entry", all_codes(), ids=lambda c: c.code)
def test_baselines_make_no_timing_or_promise(entry):
    for text in (entry.baseline_what_happened, entry.baseline_what_to_do,
                 entry.baseline_customer_message):
        assert not TIMING_OR_PROMISE.search(text), text


def test_qc_is_never_a_default_route():
    for entry in all_codes():
        assert entry.default_route != Route.QC
        assert Route.QC not in entry.route_by_rail.values()


def test_every_source_id_is_defined():
    data = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))
    for entry in all_codes():
        assert set(entry.source_ids) <= set(data["sources"]), entry.code


# --- loader rejects bad tables ---------------------------------------------

def _write_table(tmp_path, entries):
    path = tmp_path / "codes.json"
    path.write_text(json.dumps({"codes": entries}), encoding="utf-8")
    return path


def _valid_raw():
    # Start from a real entry so each test breaks exactly one thing.
    codes = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))["codes"]
    return next(c for c in codes if c["code"] == "AC04")


def test_loader_rejects_duplicate_codes(tmp_path):
    path = _write_table(tmp_path, [_valid_raw(), _valid_raw()])
    with pytest.raises(ValueError, match="Duplicate"):
        load_codes(path)


@pytest.mark.parametrize(
    "bad",
    [
        {"default_route": "NOBODY"},
        {"category": "weather"},
        {"rails": ["FEDWIRE"]},
        {"rails": ["UNKNOWN"]},
        {"route_by_rail": {"RTP": "NOBODY"}},
    ],
)
def test_loader_rejects_invalid_values(tmp_path, bad):
    path = _write_table(tmp_path, [_valid_raw() | bad])
    with pytest.raises(ValueError, match="Invalid entry AC04"):
        load_codes(path)


def test_loader_rejects_missing_field(tmp_path):
    raw = _valid_raw()
    del raw["baseline_customer_message"]
    path = _write_table(tmp_path, [raw])
    with pytest.raises(ValueError, match="Invalid entry AC04"):
        load_codes(path)


# --- provenance: scheme facts vs team runbook (piece 1b) -------------------------

def _sources():
    return json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))["sources"]


def test_no_gated_tch_source_remains():
    assert "TCH_RTP" not in _sources()
    for entry in all_codes():
        assert "TCH_RTP" not in entry.source_ids, entry.code


def test_every_team_evidence_source_is_defined():
    for entry in all_codes():
        if entry.team_runbook:
            assert set(entry.team_runbook.evidence_source_ids) <= set(_sources()), entry.code


def test_rtp_is_only_ever_a_team_runbook_rail():
    # No open scheme source confirms our RTP pairings, so every one must be team guidance,
    # either still under review or signed off by a named reviewer.
    for entry in all_codes():
        assert Rail.RTP not in entry.scheme_rails, entry.code
        if Rail.RTP in entry.rails:
            team = entry.team_runbook
            assert team.owner == "Akshay"
            assert team.needs_review or team.reviewed_by, entry.code


def test_review_notes_no_longer_compare_with_rtp_lists():
    for entry in all_codes():
        assert not re.search(r"RTP list|RTP uses|TCH uses", entry.review_note), entry.code


@pytest.mark.parametrize("code", ["AG01", "AM04", "DS24"])
def test_scheme_meanings_are_neutral(code):
    entry = lookup(code)
    for text in (entry.meaning, entry.baseline_what_happened, entry.baseline_what_to_do):
        assert "RTP" not in text and "TCH" not in text, text


@pytest.mark.parametrize(
    "code, rail, expected",
    [
        ("AC04", Rail.SEPA_DD, SourceType.SCHEME_RULE),
        ("AC04", Rail.RTP, SourceType.TEAM_RUNBOOK),
        ("DS24", Rail.RTP, SourceType.TEAM_RUNBOOK),
        ("MD01", Rail.RTP, None),
    ],
)
def test_rail_source(code, rail, expected):
    assert lookup(code).rail_source(rail) == expected


def test_what_to_do_uses_team_guidance_only_on_team_rails():
    am04 = lookup("AM04")
    assert "Treasury" in am04.what_to_do_for(Rail.RTP)
    assert am04.what_to_do_for(Rail.SEPA_DD) == am04.baseline_what_to_do
    assert "Treasury" not in am04.baseline_what_to_do


def test_am04_treasury_route_cites_open_evidence():
    team = lookup("AM04").team_runbook
    assert team.route_by_rail[Rail.RTP] == Route.TREASURY
    assert "FED_RTP_ORDER" in team.evidence_source_ids


# --- loader rejects a bad team_runbook --------------------------------------

def _with_team(**team):
    block = {"owner": "Akshay", "needs_review": True, "rails": ["RTP"], "note": "awaiting sign-off"}
    block.update(team)
    return _valid_raw() | {"rails": ["SEPA_DD"], "team_runbook": block}


@pytest.mark.parametrize(
    "raw, message",
    [
        (_with_team(owner=""), "needs an owner"),
        (_with_team(owner=None), "needs an owner"),
        (_with_team(note=""), "note is empty"),
        (_with_team(rails=["SEPA_DD"]), "already scheme rails"),
        (_with_team(rails=["UNKNOWN"]), "UNKNOWN"),
        (_with_team(route_by_rail={"SEPA_INSTANT": "DEVELOPER"}), "team_runbook.route_by_rail"),
        (_with_team(what_to_do_by_rail={"SEPA_DD": "x"}), "team_runbook.what_to_do_by_rail"),
        (_with_team(route_by_rail={"RTP": "NOBODY"}), "NOBODY"),
        (_valid_raw() | {"rails": ["SEPA_DD"], "route_by_rail": {"RTP": "DEVELOPER"}}, "route_by_rail"),
    ],
)
def test_loader_rejects_bad_team_runbook(tmp_path, raw, message):
    with pytest.raises(ValueError, match=f"Invalid entry AC04.*{message}"):
        load_codes(_write_table(tmp_path, [raw]))


def test_loader_merges_team_rails_and_routes(tmp_path):
    raw = _with_team(route_by_rail={"RTP": "TREASURY"})
    entry = load_codes(_write_table(tmp_path, [raw]))["AC04"]
    assert entry.rails == (Rail.SEPA_DD, Rail.RTP)
    assert entry.scheme_rails == (Rail.SEPA_DD,)
    assert entry.route_for(Rail.RTP) == Route.TREASURY
    assert entry.route_for(Rail.SEPA_DD) == Route.FIRST_LINE


# --- sign-off: approval needs a recorded reviewer and date -------------------

@pytest.mark.parametrize(
    "fields, message",
    [
        ({"needs_review": False}, "reviewed_by and reviewed_on"),
        ({"needs_review": False, "reviewed_by": "Akshay"}, "reviewed_by and reviewed_on"),
        ({"needs_review": False, "reviewed_on": "2026-10-15"}, "reviewed_by and reviewed_on"),
        ({"needs_review": False, "reviewed_by": " ", "reviewed_on": "2026-10-15"}, "reviewed_by and reviewed_on"),
        ({"needs_review": False, "reviewed_by": "Akshay", "reviewed_on": "15/10/2026"}, "must be a date"),
    ],
)
def test_loader_rejects_team_approval_without_sign_off(tmp_path, fields, message):
    with pytest.raises(ValueError, match=f"Invalid entry AC04.*{message}"):
        load_codes(_write_table(tmp_path, [_with_team(**fields)]))


def test_loader_accepts_signed_off_team_block(tmp_path):
    raw = _with_team(needs_review=False, reviewed_by="Akshay", reviewed_on="2026-10-15")
    team = load_codes(_write_table(tmp_path, [raw]))["AC04"].team_runbook
    assert (team.reviewed_by, team.reviewed_on) == ("Akshay", "2026-10-15")


SIGNED_OFF_TEAM_BLOCKS = {"AC03", "AC04", "AC06", "AG01", "AM04", "DS24"}


def test_signed_off_team_blocks_are_exactly_the_approved_ones():
    # Sign-off is Akshay's call; this list changes deliberately, never as a side effect.
    signed = {e.code for e in all_codes() if e.team_runbook and e.team_runbook.reviewed_by}
    assert signed == SIGNED_OFF_TEAM_BLOCKS
    for code in signed:
        team = lookup(code).team_runbook
        assert (team.reviewed_by, team.reviewed_on, team.needs_review) == ("Akshay", "2026-10-15", False)


@pytest.mark.parametrize(
    "code, phrase",
    [
        # The team baseline must be as strong as its runbook passage, so evals compare like with like.
        ("AC03", "do not resubmit with the same details"),
        ("AC03", "saved payee"),
        ("AC04", "Do not retry the payment to the same account"),
        ("AC06", "that decision belongs to the recipient's bank"),
        ("DS24", "pacs.028"),
    ],
)
def test_rtp_team_next_step_matches_its_runbook_passage(code, phrase):
    assert phrase in lookup(code).what_to_do_for(Rail.RTP)
