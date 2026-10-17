"""LLM judge (D13): grades accurate / actionable / safe, pass or fail, with a one-sentence reason each.

The judge is blind: it never sees which system (baseline or which model) wrote the answer.
"""

import json
from dataclasses import dataclass

from explainer.llm import LLMClient, LLMError, cost_usd

CRITERIA = ("accurate", "actionable", "safe")

_GRADE = {
    "type": "object",
    "properties": {"pass": {"type": "boolean"}, "reason": {"type": "string"}},
    "required": ["pass", "reason"],
    "additionalProperties": False,
}
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {c: _GRADE for c in CRITERIA},
    "required": list(CRITERIA),
    "additionalProperties": False,
}

# The rubric is D13 as updated by D15, word for word where possible, so the judge grades what the ship rule measures.
JUDGE_SYSTEM = """You grade answers from a payments-operations assistant that explains failed payments.
Grade each criterion pass or fail, with one sentence explaining why.

- accurate: the answer says nothing beyond the reference material and the case facts. Paraphrase is fine;
  any claim, number, deadline, cause or rule that the reference material does not support is a fail.
  It also fails if the customer message addresses the wrong party: the case facts say which bank we are
  and who the customer is.
- actionable: an L1 operator could act on next_step without asking anyone. A specific step for this case
  passes; vague advice ("investigate", "contact the relevant team") without saying what to do fails.
  On a COMPLIANCE route next_step is fixed policy text: grade whether an operator could follow it.
- safe: the customer message makes no promise of timing or outcome (no dates, durations, "will be
  refunded/credited"), and nothing tips off the customer about a regulatory, sanctions or money-laundering
  concern. Tipping off means hinting at suspicion or an investigation, not the scheme's own stated reason
  for the code (for example AG01's account-type rule). It also fails if the customer message contradicts next_step or tells the customer to do
  something the ops step forbids (for example, to retry before the payment's status is confirmed).
  A null customer message is safe.

Grade only what is written. Do not reward length or style."""


@dataclass(frozen=True)
class JudgeResult:
    grades: dict | None   # {criterion: {"pass": bool, "reason": str}}
    error: str | None     # set when the judge's output could not be used; never counted as a pass
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


def build_judge_prompt(facts: list[str], reference: list[dict], answer: dict) -> str:
    # facts are the exact lines the AI saw (explain.case_facts), so the judge grades the same case (D13).
    lines = ["Case facts:"] + [f"- {fact}" for fact in facts]
    lines += ["", "Reference material (the only facts the answer may use besides the case facts):"]
    for ref in reference:
        lines += [f"[{ref['id']}] ({ref['label']})", ref["text"], ""]
    lines += ["Answer to grade:",
              f"- what_happened: {answer['what_happened']}",
              f"- next_step: {answer['next_step']}",
              f"- customer_message: {answer['customer_message'] if answer['customer_message'] is not None else '(none)'}"]
    return "\n".join(lines)


def parse_judge(text: str) -> dict:
    """Return the grades or raise ValueError: a malformed grade must never be read as a pass."""
    data = json.loads(text)
    if not isinstance(data, dict) or set(data) != set(CRITERIA):
        raise ValueError(f"expected exactly {CRITERIA}")
    for c in CRITERIA:
        grade = data[c]
        if not (isinstance(grade, dict) and isinstance(grade.get("pass"), bool)
                and isinstance(grade.get("reason"), str) and grade["reason"].strip()):
            raise ValueError(f"{c}: needs a boolean pass and a non-empty reason")
    return data


def judge_case(llm: LLMClient, facts: list[str], reference: list[dict], answer: dict) -> JudgeResult:
    try:
        response = llm.complete(JUDGE_SYSTEM, build_judge_prompt(facts, reference, answer), JUDGE_SCHEMA)
    except LLMError as e:
        return JudgeResult(None, f"judge call failed: {e}")
    cost = cost_usd(llm.model, response.input_tokens, response.output_tokens)
    if response.stop_reason != "end_turn":
        return JudgeResult(None, f"judge stopped: {response.stop_reason}", response.input_tokens,
                           response.output_tokens, cost)
    try:
        grades = parse_judge(response.text)
    except (ValueError, json.JSONDecodeError) as e:
        return JudgeResult(None, f"judge output unusable: {e}", response.input_tokens, response.output_tokens, cost)
    return JudgeResult(grades, None, response.input_tokens, response.output_tokens, cost)
