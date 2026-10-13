"""Checks the test fixtures themselves, so later parser and eval tests rest on sound data."""

import json
from pathlib import Path

import pytest
from defusedxml import ElementTree

from explainer.codes import Rail, Route, lookup

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"
EXPECTED = json.loads((SAMPLES_DIR / "expected.json").read_text(encoding="utf-8"))["samples"]
NAMESPACE = {
    "PACS_002": "urn:iso:std:iso:20022:tech:xsd:pacs.002.001.10",
    "PACS_004": "urn:iso:std:iso:20022:tech:xsd:pacs.004.001.09",
}


def _raw(sample) -> str:
    return (SAMPLES_DIR / sample["file"]).read_text(encoding="utf-8")


def _iban_checksum_ok(iban: str) -> bool:
    # ISO 13616 mod-97 check: proves the sample IBANs are well-formed, so masking tests are realistic.
    rearranged = iban[4:] + iban[:4]
    digits = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(digits) % 97 == 1


def test_every_sample_file_has_an_expectation_and_vice_versa():
    on_disk = {p.name for p in SAMPLES_DIR.glob("*.xml")}
    assert on_disk == {s["file"] for s in EXPECTED}


@pytest.mark.parametrize("sample", EXPECTED, ids=lambda s: s["file"])
def test_sample_is_well_formed_and_of_the_expected_type(sample):
    root = ElementTree.fromstring(_raw(sample).encode("utf-8"))
    assert root.tag == f"{{{NAMESPACE[sample['message_type']]}}}Document"


@pytest.mark.parametrize("sample", EXPECTED, ids=lambda s: s["file"])
def test_sample_contains_its_expected_values(sample):
    # Cheap text checks; the parser tests in step 5 will check the structure properly.
    raw = _raw(sample)
    assert f"<Cd>{sample['reason_code']}</Cd>" in raw
    assert f"<OrgnlEndToEndId>{sample['end_to_end_id']}</OrgnlEndToEndId>" in raw
    assert f'Ccy="{sample["currency"]}">{sample["amount"]}<' in raw


@pytest.mark.parametrize("sample", EXPECTED, ids=lambda s: s["file"])
def test_code_and_rail_pair_is_confirmed_by_the_table(sample):
    entry = lookup(sample["reason_code"])
    if sample["route"] is None:
        # The escalation sample must stay outside the table, or it stops testing escalation.
        assert entry is None
        return
    rail = Rail(sample["rail"])
    assert entry is not None
    assert rail in entry.rails, f"{entry.code} is not confirmed on {rail}"
    assert entry.route_for(rail) == Route(sample["route"])


@pytest.mark.parametrize("sample", EXPECTED, ids=lambda s: s["file"])
def test_sample_really_contains_the_pii_that_masking_must_remove(sample):
    raw = _raw(sample)
    for value in sample["pii"]:
        assert value in raw
        if value[:2].isalpha() and value[2:4].isdigit():
            assert _iban_checksum_ok(value), value


def test_samples_cover_every_route_that_a_confirmed_code_can_reach():
    covered = {s["route"] for s in EXPECTED}
    # FRAUD has no code with a confirmed rail yet (FRAD/FR01), and QC is never a default route.
    assert covered == {"FIRST_LINE", "DEVELOPER", "TREASURY", "COMPLIANCE", None}
