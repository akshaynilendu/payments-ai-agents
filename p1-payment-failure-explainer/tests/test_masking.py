import json
from pathlib import Path

import pytest

from explainer.parse import (
    NAME_MASK, ParseError, mask_account, mask_iban, parse_file, parse_xml, scrub_free_text,
)

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"
EXPECTED = json.loads((SAMPLES_DIR / "expected.json").read_text(encoding="utf-8"))["samples"]


# --- the leak check: the strongest, simplest test of D2d ------------------------

@pytest.mark.parametrize("sample", EXPECTED, ids=lambda s: s["file"])
def test_no_personal_data_survives_parsing(sample):
    result = parse_file(SAMPLES_DIR / sample["file"])
    # repr() shows every field, nested ones included: if a value isn't there, no caller can reach it.
    everything = repr(result)
    for value in sample["pii"]:
        assert value not in everything, f"leaked: {value}"


@pytest.mark.parametrize("sample", EXPECTED, ids=lambda s: s["file"])
def test_parties_are_present_but_masked(sample):
    parties = {p.role: p for p in parse_file(SAMPLES_DIR / sample["file"]).parties}
    assert set(parties) == {"debtor", "creditor"}
    for party in parties.values():
        assert party.name == NAME_MASK
        assert party.account is not None and "*" in party.account


def test_iban_keeps_country_and_last_four():
    result = parse_file(SAMPLES_DIR / "sct_inst_ac04_closed.xml")
    debtor = next(p for p in result.parties if p.role == "debtor")
    assert debtor.account == "DE" + "*" * 16 + "3000"


def test_us_account_keeps_last_four():
    result = parse_file(SAMPLES_DIR / "rtp_ac06_blocked.xml")
    debtor = next(p for p in result.parties if p.role == "debtor")
    assert debtor.account == "****9012"


def test_parse_error_does_not_echo_personal_data():
    xml = (SAMPLES_DIR / "sct_inst_ac04_closed.xml").read_text(encoding="utf-8")
    with pytest.raises(ParseError) as exc_info:
        parse_xml(xml.replace("<Rsn><Cd>AC04</Cd></Rsn>", ""))
    assert "Erika Mustermann" not in str(exc_info.value)
    assert "DE89370400440532013000" not in str(exc_info.value)


# --- masking helpers ----------------------------------------------------------

@pytest.mark.parametrize(
    "iban, expected",
    [
        ("NL91ABNA0417164300", "NL" + "*" * 12 + "4300"),
        ("DE89 3704 0044 0532 0130 00", "DE" + "*" * 16 + "3000"),
        ("SHORT", "*****"),
    ],
)
def test_mask_iban(iban, expected):
    assert mask_iban(iban) == expected


@pytest.mark.parametrize("account, expected", [("123456789012", "****9012"), ("123", "****")])
def test_mask_account(account, expected):
    assert mask_account(account) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Account FR1420041010050500013M02606 timed out", "Account [IBAN] timed out"),
        ("Account DE89 3704 0044 0532 0130 00 closed", "Account [IBAN] closed"),
        ("US account 123456789012 blocked", "US account [NUMBER] blocked"),
        ("Card 1234-5678-9012 rejected", "Card [NUMBER] rejected"),
        # Short codes and amounts are useful context and must survive.
        ("Code AB05 for 1200.50 EUR", "Code AB05 for 1200.50 EUR"),
        ("No response from beneficiary PSP", "No response from beneficiary PSP"),
    ],
)
def test_scrub_free_text(text, expected):
    assert scrub_free_text(text) == expected


@pytest.mark.xfail(strict=True, reason="Known v1 limitation: names inside free text are not detected (see README)")
def test_names_in_free_text_are_not_yet_masked():
    assert "Erika Mustermann" not in scrub_free_text("Refused by Erika Mustermann")
