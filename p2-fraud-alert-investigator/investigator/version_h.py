"""Version H: code first, AI where the code has no answer (D14).

Version A runs first. If a rule fires, its answer stands: on the patterns the rules were written for, code is
right, free and instant. Only when no rule fires (Version A says INSUFFICIENT_EVIDENCE) does Version B run,
with all its checks and the GENUINE gate. Project 1 reached the same design: deterministic where you can,
AI where you must.
"""

from investigator.checks import run_checks
from investigator.data import Alert, Dataset
from investigator.llm import LLMClient
from investigator.schema import Hypothesis
from investigator.version_a import assess
from investigator.version_b import RunMeta, assess_b


def investigate(ds: Dataset, alert: Alert, llm: LLMClient, use_agent: bool = False):
    """use_agent=False is Version H (code, then Version B); True is Version HC (code, then the Version C agent)."""
    from investigator.flows import flow_for
    meta = RunMeta()
    findings = run_checks(ds, alert)
    result = assess(findings)
    if result.assessment.leading_hypothesis == Hypothesis.INSUFFICIENT_EVIDENCE:
        if use_agent:
            from investigator.version_c import assess_c
            result = assess_c(ds, alert, findings, llm, meta)
        else:
            result = assess_b(alert, findings, llm, meta)
    return flow_for(alert.rail).build(ds, alert, result), meta


def investigate_hc(ds: Dataset, alert: Alert, llm: LLMClient):
    return investigate(ds, alert, llm, use_agent=True)
