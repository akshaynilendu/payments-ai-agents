import json

import pytest

from explainer.iso_codes import RETURN_SET, STATUS_SET, load_iso_codes, lookup_iso
from tests.conftest import ISO_FIXTURE


def test_fixture_carries_the_terms_of_use_notice():
    # iso20022.org terms: copies must say they are not the official site and point to it.
    comment = json.loads(ISO_FIXTURE.read_text(encoding="utf-8"))["$comment"]
    assert "Not the official site" in comment and "https://www.iso20022.org/" in comment


def test_loader_parses_definitions_for_both_sets():
    release, sets = load_iso_codes(ISO_FIXTURE)
    assert release == "2Q2026 v3"
    assert sets[STATUS_SET]["AB06"] == "Transaction stopped due to timeout at the Instructed Agent."
    assert sets[RETURN_SET]["MD07"] == "End customer is deceased."


def test_message_type_picks_the_code_set():
    # AB06 is a status reason only: valid on a pacs.002, not on a pacs.004.
    assert lookup_iso("AB06", "PACS_002").code_set == STATUS_SET
    assert lookup_iso("AB06", "PACS_004") is None
    assert lookup_iso("md07", "PACS_004").code == "MD07"


@pytest.mark.parametrize("code", ["ZZ99", "", None])
def test_non_iso_codes_return_none(code):
    assert lookup_iso(code, "PACS_002") is None


def test_missing_file_explains_how_to_get_it(tmp_path):
    with pytest.raises(FileNotFoundError, match="iso20022.org"):
        load_iso_codes(tmp_path / "missing.json")


def test_code_without_definition_is_rejected(tmp_path):
    bad = {"definitions": {STATUS_SET: {"description": "*`AB06`-x", "enum": ["AB06", "AB07"]},
                           RETURN_SET: {"description": "", "enum": []}}}
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="AB07"):
        load_iso_codes(path)
