import json
import re

import pytest

from explainer.codes import DEFAULT_PATH, Rail, Route, all_codes, load_codes, lookup

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
        ("AB05", Rail.SEPA_INSTANT, Route.DEVELOPER),
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
