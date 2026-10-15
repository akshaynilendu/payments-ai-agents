import json
from decimal import Decimal
from pathlib import Path

import pytest

from explainer.codes import Rail, Stage, lookup
from explainer.parse import MessageType, ParseError, parse_file, parse_xml

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"
EXPECTED = json.loads((SAMPLES_DIR / "expected.json").read_text(encoding="utf-8"))["samples"]


def _sample_text(name: str) -> str:
    return (SAMPLES_DIR / name).read_text(encoding="utf-8")


# --- happy path: every sample parses to what expected.json says ----------------

@pytest.mark.parametrize("sample", EXPECTED, ids=lambda s: s["file"])
def test_sample_parses_to_expected_values(sample):
    result = parse_file(SAMPLES_DIR / sample["file"])
    assert result.message_type == MessageType(sample["message_type"])
    assert result.rail == Rail(sample["rail"])
    assert result.status == sample["status"]
    assert result.reason_code == sample["reason_code"]
    # Decimal, not float: 0.1 + 0.2 must equal 0.3 when money is involved.
    assert result.amount == Decimal(sample["amount"])
    assert result.currency == sample["currency"]
    assert result.end_to_end_id == sample["end_to_end_id"]


def test_parse_file_accepts_a_string_path():
    assert parse_file(str(SAMPLES_DIR / "sct_inst_ac04_closed.xml")).reason_code == "AC04"


def test_unknown_code_parses_and_lookup_signals_escalation():
    result = parse_file(SAMPLES_DIR / "sct_inst_cnor_unknown.xml")
    assert result.reason_code == "CNOR"
    assert lookup(result.reason_code) is None


def test_proprietary_reason_code_is_kept_for_escalation():
    xml = _sample_text("rtp_ac06_blocked.xml").replace(
        "<Rsn><Cd>AC06</Cd></Rsn>", "<Rsn><Prtry>9910</Prtry></Rsn>")
    result = parse_xml(xml)
    assert result.reason_code == "9910"
    assert lookup(result.reason_code) is None


def test_additional_info_is_kept_but_scrubbed():
    result = parse_file(SAMPLES_DIR / "sct_inst_ab05_timeout.xml")
    assert result.additional_info == ("No response from beneficiary PSP for account [IBAN]",)


def test_message_without_additional_info_has_empty_tuple():
    assert parse_file(SAMPLES_DIR / "sct_inst_ac04_closed.xml").additional_info == ()


# --- rail detection: unclear means UNKNOWN, never a guess ----------------------

@pytest.mark.parametrize(
    "sample, old, new",
    [
        ("sct_inst_ac04_closed.xml", "<Cd>INST</Cd>", "<Cd>XXXX</Cd>"),
        ("sct_inst_ac04_closed.xml", 'Ccy="EUR"', 'Ccy="USD"'),
        ("sdd_md01_no_mandate.xml", "<Cd>CORE</Cd>", "<Cd>XXXX</Cd>"),
        ("rtp_ac06_blocked.xml", "<Prtry>TCH</Prtry>", "<Prtry>FED</Prtry>"),
        ("rtp_ac06_blocked.xml", 'Ccy="USD"', 'Ccy="EUR"'),
    ],
)
def test_unclear_rail_markers_give_unknown(sample, old, new):
    xml = _sample_text(sample)
    assert old in xml
    assert parse_xml(xml.replace(old, new)).rail == Rail.UNKNOWN


def test_sdd_b2b_is_sepa_dd():
    xml = _sample_text("sdd_md01_no_mandate.xml").replace("<Cd>CORE</Cd>", "<Cd>B2B</Cd>")
    assert parse_xml(xml).rail == Rail.SEPA_DD


# --- bad input raises ParseError, never partial data ---------------------------

def _broken(sample: str, old: str, new: str) -> str:
    xml = _sample_text(sample)
    assert old in xml, "test setup: text to replace not found"
    return xml.replace(old, new)


@pytest.mark.parametrize(
    "xml, message",
    [
        ("<Document><unclosed></Document>", "Malformed"),
        ('<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pain.001.001.09"/>', "Not a pacs"),
        ("<Document/>", "Not a pacs"),
        (_broken("sct_inst_ac04_closed.xml", "<Rsn><Cd>AC04</Cd></Rsn>", ""), "Missing reason code"),
        (_broken("sct_inst_ac04_closed.xml", "<TxSts>RJCT</TxSts>", ""), "Missing TxSts"),
        (_broken("sct_inst_ac04_closed.xml",
                 "<OrgnlEndToEndId>E2E-TEST-0001</OrgnlEndToEndId>", ""), "Missing OrgnlEndToEndId"),
        (_broken("sct_inst_ac04_closed.xml", ">250.00<", ">12,50<"), "valid ISO 20022 amount"),
        (_broken("sct_inst_ac04_closed.xml", ">250.00<", ">NaN<"), "valid ISO 20022 amount"),
        (_broken("sct_inst_ac04_closed.xml", ">250.00<", ">-5.00<"), "valid ISO 20022 amount"),
        (_broken("sct_inst_ac04_closed.xml", ' Ccy="EUR"', ""), "currency"),
        (_broken("sdd_md01_no_mandate.xml",
                 '<RtrdIntrBkSttlmAmt Ccy="EUR">120.00</RtrdIntrBkSttlmAmt>', ""), "Missing amount"),
    ],
)
def test_bad_input_raises_parse_error(xml, message):
    with pytest.raises(ParseError, match=message):
        parse_xml(xml)


def test_more_than_one_transaction_is_rejected():
    xml = _sample_text("sct_inst_ac04_closed.xml")
    start, end = xml.index("<TxInfAndSts>"), xml.index("</TxInfAndSts>") + len("</TxInfAndSts>")
    doubled = xml[:end] + xml[start:end] + xml[end:]
    with pytest.raises(ParseError, match="exactly one"):
        parse_xml(doubled)


@pytest.mark.parametrize(
    "attack",
    [
        # XXE: tries to read a local file into the message.
        '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
        '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.002.001.10">&x;</Document>',
        # Entity expansion ("billion laughs", shortened).
        '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
        '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.002.001.10">&b;</Document>',
    ],
)
def test_xml_attacks_are_rejected(attack):
    with pytest.raises(ParseError, match="Unsafe XML"):
        parse_xml(attack)


# --- stage (D10) ------------------------------------------------------------------

@pytest.mark.parametrize("sample", EXPECTED, ids=lambda s: s["file"])
def test_sample_parses_to_expected_stage(sample):
    assert parse_file(SAMPLES_DIR / sample["file"]).stage == Stage(sample["stage"])


def _with_status(status: str, keep_reason: bool) -> str:
    xml = _sample_text("sct_inst_ac04_closed.xml").replace("<TxSts>RJCT</TxSts>", f"<TxSts>{status}</TxSts>")
    if not keep_reason:
        start = xml.index("<StsRsnInf>")
        xml = xml[:start] + xml[xml.index("</StsRsnInf>") + len("</StsRsnInf>"):]
    return xml


@pytest.mark.parametrize("status", ["ACSC", "ACCC", "ACSP", "ACTC", "ACCP", "ACFC", "ACPD", "ACWC"])
def test_success_status_is_not_a_failure_and_needs_no_reason(status):
    result = parse_xml(_with_status(status, keep_reason=False))
    assert (result.stage, result.reason_code) == (Stage.NOT_A_FAILURE, None)


@pytest.mark.parametrize("status", ["PDNG", "RCVD", "ACWP", "ACFW", "PATC"])
def test_pending_status_is_pending(status):
    assert parse_xml(_with_status(status, keep_reason=False)).stage == Stage.PENDING


@pytest.mark.parametrize("status", ["CANC", "BLCK", "XXXX"])
def test_unrecognised_or_non_final_status_is_unknown_and_keeps_its_reason(status):
    result = parse_xml(_with_status(status, keep_reason=True))
    assert (result.stage, result.reason_code) == (Stage.UNKNOWN, "AC04")


def test_return_without_reason_is_still_a_parse_error():
    xml = _sample_text("sdd_md01_no_mandate.xml").replace("<Rsn><Cd>MD01</Cd></Rsn>", "")
    with pytest.raises(ParseError, match="Missing reason code"):
        parse_xml(xml)
