"""Turn a pacs.002 or pacs.004 into a PaymentStatus, with personal data masked before anything else sees it (D2d)."""

import re
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from defusedxml import DefusedXmlException, ElementTree

from explainer.codes import Rail

# Raw names and account numbers must never leave this module, so they are masked
# while the PaymentStatus is being built, not afterwards.
NAME_MASK = "[NAME]"
IBAN_TEXT_MASK = "[IBAN]"
NUMBER_TEXT_MASK = "[NUMBER]"

# IBAN: 2 letters, 2 check digits, then 11-30 letters/digits, written solid or in groups of 4.
_IBAN_IN_TEXT = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b")
# Any run of 6+ digits (spaces or dashes allowed between them) could be an account number.
_LONG_NUMBER_IN_TEXT = re.compile(r"\d(?:[ -]?\d){5,}")
# ISO 20022 amounts: up to 18 digits, up to 5 decimals. Rejects "NaN", "1e3", "12,50" that Decimal() would accept or misread.
_ISO_AMOUNT = re.compile(r"\d{1,18}(\.\d{1,5})?")

_PARTY_ROLES = {
    "UltmtDbtr": ("ultimate_debtor", None),
    "Dbtr": ("debtor", "DbtrAcct"),
    "Cdtr": ("creditor", "CdtrAcct"),
    "UltmtCdtr": ("ultimate_creditor", None),
}


class MessageType(StrEnum):
    PACS_002 = "PACS_002"
    PACS_004 = "PACS_004"


class ParseError(Exception):
    """The message can't be trusted, so it goes to a person. Messages never include raw field values."""


@dataclass(frozen=True)
class MaskedParty:
    role: str
    name: str | None
    account: str | None


@dataclass(frozen=True)
class PaymentStatus:
    rail: Rail
    message_type: MessageType
    status: str
    reason_code: str
    amount: Decimal
    currency: str
    end_to_end_id: str
    additional_info: tuple[str, ...]
    parties: tuple[MaskedParty, ...]


# --- masking ----------------------------------------------------------------

def mask_iban(iban: str) -> str:
    # Keep country and last 4 so a person can still match it to a customer record.
    iban = iban.replace(" ", "")
    if len(iban) <= 8:
        return "*" * len(iban)
    return iban[:2] + "*" * (len(iban) - 6) + iban[-4:]


def mask_account(account_id: str) -> str:
    if len(account_id) <= 4:
        return "****"
    return "****" + account_id[-4:]


def scrub_free_text(text: str) -> str:
    """Free text can contain anything. v1 catches IBANs and long numbers; it can NOT catch names."""
    text = _IBAN_IN_TEXT.sub(IBAN_TEXT_MASK, text)
    return _LONG_NUMBER_IN_TEXT.sub(NUMBER_TEXT_MASK, text)


# --- parsing ----------------------------------------------------------------

def parse_file(path: str | Path) -> PaymentStatus:
    return parse_xml(Path(path).read_bytes())


def parse_xml(data: bytes | str) -> PaymentStatus:
    if isinstance(data, str):
        data = data.encode("utf-8")
    try:
        # defusedxml refuses entity tricks (XXE, "billion laughs") that plain ElementTree allows.
        root = ElementTree.fromstring(data)
    except DefusedXmlException as e:
        raise ParseError(f"Unsafe XML rejected: {type(e).__name__}") from e
    except ElementTree.ParseError as e:
        raise ParseError(f"Malformed XML: {e}") from e

    message_type = _message_type(root)
    if message_type is MessageType.PACS_002:
        tx = _single_transaction(root, "FIToFIPmtStsRpt", "TxInfAndSts")
        status = _required_text(tx, "TxSts")
        reason_info = tx.find("{*}StsRsnInf")
        amount_el = tx.find("{*}OrgnlTxRef/{*}IntrBkSttlmAmt")
    else:
        tx = _single_transaction(root, "PmtRtr", "TxInf")
        # pacs.004 has no status field: the message itself means "returned".
        status = "RETURNED"
        reason_info = tx.find("{*}RtrRsnInf")
        amount_el = tx.find("{*}RtrdIntrBkSttlmAmt")

    amount, currency = _amount(amount_el)
    return PaymentStatus(
        rail=_detect_rail(tx, currency),
        message_type=message_type,
        status=status,
        reason_code=_reason_code(reason_info),
        amount=amount,
        currency=currency,
        end_to_end_id=_required_text(tx, "OrgnlEndToEndId"),
        additional_info=tuple(
            scrub_free_text(el.text.strip())
            for el in (reason_info.findall("{*}AddtlInf") if reason_info is not None else [])
            if el.text and el.text.strip()
        ),
        parties=_masked_parties(tx),
    )


def _message_type(root) -> MessageType:
    namespace = root.tag[1:].split("}")[0] if root.tag.startswith("{") else ""
    if namespace.startswith("urn:iso:std:iso:20022:tech:xsd:pacs.002."):
        return MessageType.PACS_002
    if namespace.startswith("urn:iso:std:iso:20022:tech:xsd:pacs.004."):
        return MessageType.PACS_004
    raise ParseError("Not a pacs.002 or pacs.004 message")


def _single_transaction(root, body_tag: str, tx_tag: str):
    transactions = root.findall(f"{{*}}{body_tag}/{{*}}{tx_tag}")
    # v1 explains one failure per message; silently picking the first of several would hide the others.
    if len(transactions) != 1:
        raise ParseError(f"Expected exactly one {tx_tag}, found {len(transactions)}")
    return transactions[0]


def _required_text(parent, tag: str) -> str:
    el = parent.find(f"{{*}}{tag}")
    if el is None or not (el.text or "").strip():
        raise ParseError(f"Missing {tag}")
    return el.text.strip()


def _reason_code(reason_info) -> str:
    if reason_info is not None:
        # RTP also sends proprietary codes (e.g. 1100, 9910); they are kept so lookup() returns None and we escalate.
        for path in ("{*}Rsn/{*}Cd", "{*}Rsn/{*}Prtry"):
            el = reason_info.find(path)
            if el is not None and (el.text or "").strip():
                return el.text.strip().upper()
    raise ParseError("Missing reason code")


def _amount(el) -> tuple[Decimal, str]:
    if el is None:
        raise ParseError("Missing amount")
    text = (el.text or "").strip()
    currency = (el.get("Ccy") or "").strip()
    if not _ISO_AMOUNT.fullmatch(text):
        raise ParseError("Amount is not a valid ISO 20022 amount")
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ParseError("Missing or invalid currency")
    return Decimal(text), currency


def _detect_rail(tx, currency: str) -> Rail:
    # Explicit markers only. A wrong rail would pick wrong rules, so anything unclear is UNKNOWN and escalates.
    local_instrument = _first_text(tx, ".//{*}PmtTpInf/{*}LclInstrm/{*}Cd")
    clearing_system = _first_text(tx, ".//{*}SttlmInf/{*}ClrSys/{*}Prtry")
    if local_instrument == "INST" and currency == "EUR":
        return Rail.SEPA_INSTANT
    if local_instrument in ("CORE", "B2B") and currency == "EUR":
        return Rail.SEPA_DD
    if clearing_system == "TCH" and currency == "USD":
        return Rail.RTP
    return Rail.UNKNOWN


def _first_text(parent, path: str) -> str | None:
    el = parent.find(path)
    return el.text.strip().upper() if el is not None and el.text else None


def _masked_parties(tx) -> tuple[MaskedParty, ...]:
    ref = tx.find("{*}OrgnlTxRef")
    if ref is None:
        return ()
    parties = []
    for tag, (role, account_tag) in _PARTY_ROLES.items():
        party = ref.find(f"{{*}}{tag}")
        account = ref.find(f"{{*}}{account_tag}") if account_tag else None
        if party is None and account is None:
            continue
        name_el = party.find(".//{*}Nm") if party is not None else None
        parties.append(MaskedParty(
            role=role,
            name=NAME_MASK if name_el is not None and name_el.text else None,
            account=_masked_account(account),
        ))
    return tuple(parties)


def _masked_account(account) -> str | None:
    if account is None:
        return None
    iban = account.find("{*}Id/{*}IBAN")
    if iban is not None and iban.text:
        return mask_iban(iban.text.strip())
    other = account.find("{*}Id/{*}Othr/{*}Id")
    if other is not None and other.text:
        return mask_account(other.text.strip())
    return None
