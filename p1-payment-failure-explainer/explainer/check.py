"""Checks on the AI's answer, in code, no AI. Each failure has a name, so a retry can say exactly what to fix."""

import json
import re
from dataclasses import dataclass

from explainer.codes import WITHHELD_REASON_CODES, Route
from explainer.explain import FIELDS

LENGTH_LIMITS = {"what_happened": 600, "next_step": 600, "customer_message": 400}
MAX_CITATIONS = 6

# D2c: promises of timing or outcome to a customer. Checked on customer_message only: ops text may
# legitimately quote rule deadlines from a passage (e.g. "15 banking business days").
PROMISE_PATTERNS = [re.compile(p, re.IGNORECASE) for p in (
    r"\bwithin\s+\d+",
    r"\b\d+\s+(?:business\s+|banking\s+|working\s+)?(?:days?|hours?|minutes?|weeks?)\b",
    r"\bguarantee",
    r"\bpromise",
    r"\bwill\s+be\s+(?:credited|refunded|returned|reversed|resolved|paid|received|completed)\b",
    r"\byou\s+will\s+(?:receive|get)\b",
    r"\bby\s+(?:tomorrow|today|tonight|end\s+of)\b",
    r"\bshortly\b",
    r"\bas\s+soon\s+as\b",
)]


# D12: on a COMPLIANCE route, no field may tell anyone to contact the customer (tipping off).
_PARTY = r"(?:the\s+|our\s+)?(?:customer|client|originator|payer|account\s+holder|sender)"
CUSTOMER_CONTACT_PATTERNS = [re.compile(p, re.IGNORECASE) for p in (
    r"\b(?:advise|tell|contact|inform|notify|call|e-?mail|message|update|let|reach\s+out\s+to|speak\s+(?:to|with)"
    r"|talk\s+(?:to|with)|explain\s+to)\s+(?:\w+\s+){0,2}?" + _PARTY + r"\b",
    r"\b(?:discuss|share|explain|raise|mention)\b[^.]{0,60}?\bwith\s+" + _PARTY + r"\b",
    r"\b(?:customer|client|originator|payer)\s+(?:should|must|can|may|will)\s+be\s+"
    r"(?:told|informed|advised|contacted|notified|updated)\b",
)]
# "Do not contact the customer" is the policy itself, so negated instructions are not contact.
_NEGATION = re.compile(r"\b(?:not|never|no)\b|n't", re.IGNORECASE)


# D16(b): next_step forbids resending (e.g. "before anyone resends, confirm ... pacs.028")...
_RESEND_FORBIDDEN = re.compile(
    r"\bpacs\.028\b|\bbefore\s+(?:anyone|the\s+customer|they|you)?\s*(?:re-?sends?|resubmits?|retr(?:y|ies)|tries\s+again)"
    r"|\b(?:do\s+not|don't|never)\s+(?:re-?send|resubmit|retry|send\s+(?:it|the\s+payment)\s+again)", re.IGNORECASE)
# ...so the customer message must not tell the customer to do it.
_RETRY_INSTRUCTION = re.compile(
    r"\b(?:try\s+(?:it\s+)?again|re-?send|resubmit|retry|re-?issue|send\s+(?:it|the\s+payment|a\s+new\s+payment)\s+again"
    r"|send\s+again)\b", re.IGNORECASE)

# D16(c): guessing at a withheld reason. MS03 exists because national law can forbid giving the cause.
_SPECULATION = re.compile(
    r"\b(?:may|might|could)\s+(?:be|have\s+been)\s+(?:due|because|caused|related)|\bpossibl[ey]\b|\blikely\b"
    r"|\bdue\s+to\b|\bsuch\s+as\b|\bfor\s+example\b|\breasons?\s+(?:include|like|could|may|might)"
    r"|\bregulat|\bsanction|\binsufficient|\bclosed\b|\bblocked\b|\bdeceased\b|\bfraud|\baccount\s+status", re.IGNORECASE)


def contradiction(next_step: str, customer_message: str | None) -> str | None:
    """The retry phrase in the customer message, if next_step forbids resending; else None."""
    if not customer_message or not _RESEND_FORBIDDEN.search(next_step or ""):
        return None
    for match in _RETRY_INSTRUCTION.finditer(customer_message):
        # "Please don't send it again" is the policy itself, not a retry instruction.
        if not _NEGATION.search(customer_message[max(0, match.start() - 25):match.start()]):
            return match.group(0)
    return None


def speculation(code: str | None, customer_message: str | None) -> str | None:
    """The guessing phrase in a customer message for a reason-withheld code; else None."""
    if code not in WITHHELD_REASON_CODES or not customer_message:
        return None
    match = _SPECULATION.search(customer_message)
    return match.group(0) if match else None


def _customer_contact(text: str) -> str | None:
    for pattern in CUSTOMER_CONTACT_PATTERNS:
        for match in pattern.finditer(text):
            if not _NEGATION.search(text[max(0, match.start() - 25):match.start()]):
                return match.group(0)
    return None


@dataclass(frozen=True)
class Failure:
    name: str
    detail: str = ""

    def __str__(self) -> str:
        return f"{self.name} ({self.detail})" if self.detail else self.name


@dataclass(frozen=True)
class CheckResult:
    answer: dict | None
    failures: tuple[Failure, ...]

    @property
    def ok(self) -> bool:
        return not self.failures


def check(text: str, *, allowed_citations: set[str], route: Route | None,
          stop_reason: str = "end_turn", code: str | None = None, customer_policy: bool = False) -> CheckResult:
    failures: list[Failure] = []
    if stop_reason != "end_turn":
        # Cut off by the token cap or refused: even valid-looking JSON may be incomplete.
        failures.append(Failure("truncated_or_refused", stop_reason))

    try:
        answer = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return CheckResult(None, tuple(failures + [Failure("invalid_json")]))
    schema_failures = _schema_failures(answer)
    if schema_failures:
        # Field checks below assume the shape, so stop here.
        return CheckResult(None, tuple(failures + schema_failures))

    compliance = route is Route.COMPLIANCE
    # On COMPLIANCE the policy text replaces next_step, so the AI is asked to leave it empty (D12).
    for field in ("what_happened",) if compliance else ("what_happened", "next_step"):
        if not answer[field].strip():
            failures.append(Failure("empty_field", field))
    customer = answer["customer_message"]
    if customer is not None and not customer.strip():
        failures.append(Failure("empty_field", "customer_message: use null instead of an empty string"))

    citations = answer["citations"]
    if not citations:
        failures.append(Failure("no_citation"))
    unknown = sorted({c for c in citations if c not in allowed_citations})
    if unknown:
        failures.append(Failure("unknown_citation", ", ".join(unknown)))
    if len(citations) > MAX_CITATIONS:
        failures.append(Failure("too_long", f"citations: {len(citations)} > {MAX_CITATIONS}"))

    if compliance and customer is not None:
        # Tipping off: nothing goes to the customer from the AI on a compliance stop.
        failures.append(Failure("compliance_customer_message"))
    if compliance:
        for field in ("what_happened", "next_step"):
            phrase = _customer_contact(answer[field])
            if phrase:
                failures.append(Failure("compliance_customer_contact", f"{field}: {phrase}"))
    if customer_policy and customer is not None:
        # D16(b): the bank's policy text replaces it, so the AI is asked for null.
        failures.append(Failure("policy_customer_message", "customer_message is set by bank policy; return null"))
    if not compliance:
        phrase = contradiction(answer["next_step"], customer)
        if phrase:
            failures.append(Failure("customer_contradicts_next_step", phrase))
    phrase = speculation(code, customer)
    if phrase:
        failures.append(Failure("speculative_reason", phrase))
    if customer:
        for pattern in PROMISE_PATTERNS:
            match = pattern.search(customer)
            if match:
                failures.append(Failure("promise_phrase", match.group(0)))
                break

    for field, limit in LENGTH_LIMITS.items():
        value = answer[field]
        if value is not None and len(value) > limit:
            failures.append(Failure("too_long", f"{field}: {len(value)} > {limit} characters"))

    return CheckResult(answer, tuple(failures))


def _schema_failures(answer) -> list[Failure]:
    if not isinstance(answer, dict):
        return [Failure("schema_invalid", "not a JSON object")]
    failures = []
    missing = [f for f in FIELDS if f not in answer]
    extra = sorted(set(answer) - set(FIELDS))
    if missing:
        failures.append(Failure("schema_invalid", f"missing {', '.join(missing)}"))
    if extra:
        # Includes any attempt to return a route: the routing table decides, not the AI.
        failures.append(Failure("schema_invalid", f"unexpected {', '.join(extra)}"))
    if missing:
        return failures
    for field in ("what_happened", "next_step"):
        if not isinstance(answer[field], str):
            failures.append(Failure("schema_invalid", f"{field} must be text"))
    if answer["customer_message"] is not None and not isinstance(answer["customer_message"], str):
        failures.append(Failure("schema_invalid", "customer_message must be text or null"))
    if not isinstance(answer["citations"], list) or not all(isinstance(c, str) for c in answer["citations"]):
        failures.append(Failure("schema_invalid", "citations must be a list of passage IDs"))
    return failures
