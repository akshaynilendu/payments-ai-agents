"""Run the golden eval for one system configuration (D13).

    .venv/bin/python -m evals.run_eval --config baseline
    .venv/bin/python -m evals.run_eval --config haiku45_rank          # prints the estimated cost, spends nothing
    .venv/bin/python -m evals.run_eval --config haiku45_rank --yes    # runs, with a hard $2 cap
"""

import argparse
import json
import math
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from evals import graders
from evals.judge import judge_case
from evals.make_cases import case_path, load_golden
from explainer import config
from explainer.codes import Route, Stage, lookup
from explainer.explain import beyond_table_facts, case_facts, source_label
from explainer.iso_codes import lookup_iso
from explainer.llm import AnthropicClient, LLMClient, LLMError, LLMResponse, cost_usd
from explainer.parse import parse_file
from explainer.pipeline import COMPLIANCE_NEXT_STEP, beyond_table_passages, explain_case
from explainer.retrieve import Mode, retrieve

RESULTS_DIR = Path(__file__).resolve().parent / "results"
CAP_USD = 2.0  # hard cap per run, system and judge together
HAIKU45, HAIKU55 = "claude-haiku-4-5-20251001", "claude-haiku-5-5"
CONFIGS = {
    "baseline": (None, Mode.FILTER_ONLY),  # no AI: the code table's fixed text (D4)
    "haiku45_rank": (HAIKU45, Mode.FILTER_RANK),
    "haiku45_filter": (HAIKU45, Mode.FILTER_ONLY),
    "haiku55_rank": (HAIKU55, Mode.FILTER_RANK),
    "haiku55_filter": (HAIKU55, Mode.FILTER_ONLY),
}
# Rough output sizes for the "typical" estimate; the worst case uses each model's max_tokens.
TYPICAL_OUTPUT_TOKENS = {HAIKU45: 350, HAIKU55: 900, config.JUDGE_MODEL: 1200}
CHARS_PER_TOKEN = 3  # deliberately low (more tokens), so estimates err high
JUDGED_OUTCOMES = {"ai_ok", "ai_retry_ok", "ai_beyond_table", "baseline", "no_guidance", "escalated"}


class BudgetExceeded(Exception):
    """Raised before a call that could push the run past its cap. Not an LLMError, so it stops the run."""


@dataclass
class CostGuard:
    cap_usd: float
    spent_usd: float = 0.0

    def check(self, model: str, prompt_chars: int) -> None:
        worst = cost_usd(model, math.ceil(prompt_chars / CHARS_PER_TOKEN), config.MODEL_SETTINGS[model]["max_tokens"])
        if self.spent_usd + worst > self.cap_usd:
            raise BudgetExceeded(f"next {model} call could reach ${self.spent_usd + worst:.4f} > cap ${self.cap_usd:.2f}")

    def add(self, model: str, response: LLMResponse) -> None:
        self.spent_usd += cost_usd(model, response.input_tokens, response.output_tokens)


@dataclass
class GuardedLLM:
    """Checks the budget before every call and records each prompt (the injection grader reads them)."""
    inner: LLMClient
    guard: CostGuard
    prompts: list = field(default_factory=list)

    @property
    def model(self) -> str:
        return self.inner.model

    def complete(self, system: str, user: str, schema: dict) -> LLMResponse:
        self.guard.check(self.inner.model, len(system) + len(user))
        self.prompts.append(user)
        response = self.inner.complete(system, user, schema)
        self.guard.add(self.inner.model, response)
        return response


@dataclass
class PromptMeter:
    """Stands in for the model during the estimate: measures each prompt, then fails the call. Spends $0."""
    model: str
    prompt_chars: list = field(default_factory=list)

    def complete(self, system: str, user: str, schema: dict) -> LLMResponse:
        self.prompt_chars.append(len(system) + len(user))
        raise LLMError("estimate only")


@dataclass(frozen=True)
class Options:
    """Where retrieval reads and writes; tests point these at temp files and a fake embedder."""
    retrieve: dict
    log_path: Path


def default_options(tmp: Path) -> Options:
    # Eval runs must not write to the product's gap or explain logs.
    return Options(retrieve={"gaps_path": tmp / "gaps.jsonl"}, log_path=tmp / "explain_log.jsonl")


# --- estimate ------------------------------------------------------------------

def estimate(config_name: str, cases: list[dict], options: Options) -> dict:
    model, mode = CONFIGS[config_name]
    system_typical = system_worst = judge_typical = judge_worst = 0.0
    judge_model = config.JUDGE_MODEL
    for case in cases:
        status = parse_file(case_path(case))
        chars = 0
        if model:
            meter = PromptMeter(model)
            explain_case(status, meter, mode, log_path=options.log_path, **options.retrieve)
            if meter.prompt_chars:
                chars = meter.prompt_chars[0]
                tokens = math.ceil(chars / CHARS_PER_TOKEN)
                system_typical += cost_usd(model, tokens, TYPICAL_OUTPUT_TOKENS[model])
                # Worst case: both attempts (D3) use the whole token cap.
                system_worst += 2 * cost_usd(model, tokens, config.MODEL_SETTINGS[model]["max_tokens"])
        if case["expect"]["outcome"] in ("explained", "no_guidance", "explained_beyond") or chars:
            judge_tokens = math.ceil((len(_reference_text(status, options.retrieve)) + 2500) / CHARS_PER_TOKEN)
            judge_typical += cost_usd(judge_model, judge_tokens, TYPICAL_OUTPUT_TOKENS[judge_model])
            judge_worst += cost_usd(judge_model, judge_tokens, config.MODEL_SETTINGS[judge_model]["max_tokens"])
    return {"system_typical": system_typical, "system_worst": system_worst,
            "judge_typical": judge_typical, "judge_worst": judge_worst,
            "total_typical": system_typical + judge_typical, "total_worst": system_worst + judge_worst}


# --- one case -----------------------------------------------------------------

def _reference(status, retrieve_options: dict) -> list[dict]:
    """The same reference material for every system: what the AI is given for this case (D13 fair grading).
    Never the code table's own baseline text, so the baseline can't be graded against itself."""
    if status.stage in (Stage.NOT_A_FAILURE, Stage.PENDING):
        return []
    code = lookup(status.reason_code)
    if code is None:
        iso = lookup_iso(status.reason_code, status.message_type.value)
        if iso is None:
            return []
        items = beyond_table_passages(iso, status.rail, status.stage)
        refs = []
    else:
        refs = []
        if code.route_for(status.rail) is Route.COMPLIANCE:
            refs.append({"id": "POLICY", "label": "Bank policy (fixed next_step on COMPLIANCE)",
                         "text": COMPLIANCE_NEXT_STEP})
        # The passages the AI sees in rank mode (top k plus mandatory), the canonical reference for all systems.
        items = retrieve(status.reason_code, status.rail, status.stage, Mode.FILTER_RANK, **retrieve_options).all()
    for item in items:
        refs.append({"id": item.passage.id, "label": source_label(item.passage.source_type), "text": item.passage.text})
    return refs


def _reference_text(status, retrieve_options: dict) -> str:
    return "\n".join(r["text"] for r in _reference(status, retrieve_options))


def run_case(case: dict, system_kind: str, llm: GuardedLLM | None, mode: Mode, options: Options,
             judge_llm: GuardedLLM | None) -> tuple[dict, dict | None]:
    status = parse_file(case_path(case))
    prompts_before = len(llm.prompts) if llm else 0
    result = explain_case(status, llm, mode, log_path=options.log_path, **options.retrieve)

    retrieved, candidates = [], []
    if result.code and lookup(result.code) and status.stage not in (Stage.NOT_A_FAILURE, Stage.PENDING):
        used = retrieve(result.code, status.rail, status.stage, mode, **options.retrieve)
        retrieved = [r.passage.id for r in used.all()]
        if mode is Mode.FILTER_RANK:
            # All candidates with their scores: the raw material for setting the threshold (D7).
            everything = retrieve(result.code, status.rail, status.stage, mode, k=100, **options.retrieve)
            candidates = [[r.passage.id, round(r.score, 4), r.passage.id in retrieved]
                          for r in everything.ranked]

    record = {
        "id": case["id"], "outcome": result.outcome.value,
        "route": result.route.value if result.route else None, "stage": result.stage.value,
        "what_happened": result.what_happened, "next_step": result.next_step,
        "next_step_source": result.next_step_source.value, "customer_message": result.customer_message,
        "citations": [c.id for c in result.citations], "retrieved_ids": retrieved,
        "retrieval_candidates": candidates, "note": result.note, "attempts": result.attempts,
        "failures": list(result.failures), "model": result.model,
        "input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
        "cost_usd": round(result.cost_usd, 6), "latency_s": result.latency_s,
        "prompts": llm.prompts[prompts_before:] if llm else [],
    }
    record["grades"] = graders.grade_case(case, record, system_kind)

    judged = judge_record(case, record, judge_llm, options) if judge_llm else None
    return record, judged


def judge_record(case: dict, record: dict, judge_llm: LLMClient, options: Options) -> dict | None:
    """Grade one stored answer. Shared by the run and by evals.rejudge, so both grade identically."""
    if record["outcome"] not in JUDGED_OUTCOMES or record["note"] == "unknown_code":
        return None  # fixed stop messages and unknown codes are graded by code only
    status = parse_file(case_path(case))
    code = lookup(status.reason_code)
    if code is not None:
        facts = case_facts(code, status.rail, status.stage, Route(record["route"]))
    else:
        # Outside the table (D17): the facts the beyond-the-table prompt gives the AI.
        facts = beyond_table_facts(lookup_iso(status.reason_code, status.message_type.value), status.rail, status.stage)
    answer = {k: record[k] for k in ("what_happened", "next_step", "customer_message")}
    verdict = judge_case(judge_llm, facts, _reference(status, options.retrieve), answer)
    return {"id": case["id"], "grades": verdict.grades, "error": verdict.error,
            "input_tokens": verdict.input_tokens, "output_tokens": verdict.output_tokens,
            "cost_usd": round(verdict.cost_usd, 6)}


# --- whole run ------------------------------------------------------------------

def run(config_name: str, *, yes: bool, out_dir: Path | None = None,
        system_factory: Callable[[str], LLMClient] = AnthropicClient,
        judge_factory: Callable[[str], LLMClient] | None = AnthropicClient,
        options: Options | None = None, case_ids: list[str] | None = None, slice_: str | None = None,
        cap_usd: float = CAP_USD, echo: Callable[[str], None] = print) -> Path | None:
    model, mode = CONFIGS[config_name]
    system_kind = "ai" if model else "baseline"
    cases = [c for c in load_golden() if (not case_ids or c["id"] in case_ids)
             and (not slice_ or c.get("slice", "in_table") == slice_)]
    with tempfile.TemporaryDirectory() as tmp:
        options = options or default_options(Path(tmp))

        est = estimate(config_name, cases, options)
        echo(f"{config_name}: {len(cases)} cases. Estimated cost: typical ${est['total_typical']:.3f} "
             f"(system ${est['system_typical']:.3f}, judge ${est['judge_typical']:.3f}); "
             f"worst case ${est['total_worst']:.3f}. Hard cap ${cap_usd:.2f}.")
        if not yes:
            echo("Nothing spent. Re-run with --yes to run it.")
            return None

        guard = CostGuard(cap_usd)
        llm = GuardedLLM(system_factory(model), guard) if model else None
        judge_llm = GuardedLLM(judge_factory(config.JUDGE_MODEL), guard) if judge_factory else None
        records, judged, stopped = [], [], None
        for case in cases:
            try:
                record, verdict = run_case(case, system_kind, llm, mode, options, judge_llm)
            except BudgetExceeded as e:
                stopped = str(e)
                echo(f"STOPPED at {case['id']}: {stopped}")
                break
            records.append(record)
            if verdict:
                judged.append(verdict)

    run_dir = out_dir or RESULTS_DIR / f"{config_name}-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    meta = {"config": config_name, "slice": slice_ or "all", "model": model, "mode": mode.value,
            "settings": config.MODEL_SETTINGS.get(model) if model else None,
            "judge_model": config.JUDGE_MODEL if judge_factory else None,
            "judge_settings": config.MODEL_SETTINGS[config.JUDGE_MODEL] if judge_factory else None,
            "retrieval_threshold": config.RETRIEVAL_THRESHOLD, "retrieval_k": config.RETRIEVAL_K,
            "cases_planned": len(cases), "cases_run": len(records), "stopped": stopped,
            "spent_usd": round(guard.spent_usd, 6), "cap_usd": cap_usd,
            "run_at": datetime.now(UTC).isoformat(timespec="seconds")}
    _write_jsonl(run_dir / "cases.jsonl", [{k: v for k, v in r.items() if k != "prompts"}
                                           | {"prompt_chars": [len(p) for p in r["prompts"]]} for r in records])
    _write_jsonl(run_dir / "judge.jsonl", judged)
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    (run_dir / "summary.md").write_text(code_summary(meta, records), encoding="utf-8")
    (run_dir / "judge_summary.md").write_text(judge_summary(meta, records, judged), encoding="utf-8")
    echo(f"Spent ${guard.spent_usd:.4f}. Results in {run_dir}")
    return run_dir


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


# --- reports ------------------------------------------------------------------------

SYMBOL = {graders.PASS: "✓", graders.FAIL: "✗", graders.NA: "–"}


def code_summary(meta: dict, records: list[dict]) -> str:
    """Code graders only. The judge's grades go to judge_summary.md, kept apart for blind hand grading."""
    n = len(records)
    total_cost = sum(r["cost_usd"] for r in records)
    lines = [f"# Eval run: {meta['config']}", "",
             f"- Model: {meta['model'] or 'none (baseline: code table text)'}, mode {meta['mode']}, "
             f"settings {json.dumps(meta['settings'])}",
             f"- Cases: {n} of {meta['cases_planned']}" + (f" (STOPPED: {meta['stopped']})" if meta["stopped"] else ""),
             f"- Retrieval: k={meta['retrieval_k']}, threshold={meta['retrieval_threshold']} (placeholder)",
             f"- System cost: ${total_cost:.4f} total, ${total_cost / n if n else 0:.5f} average per case; "
             f"max latency {max((r['latency_s'] for r in records), default=0):.2f} s",
             f"- Run total including judge: ${meta['spent_usd']:.4f} (cap ${meta['cap_usd']:.2f})", "",
             "## Code graders", "",
             "| case | system outcome | " + " | ".join(graders.CHECKS) + " |",
             "|---|---|" + "---|" * len(graders.CHECKS)]
    for r in records:
        lines.append(f"| {r['id']} | {r['outcome']} | "
                     + " | ".join(SYMBOL[r["grades"][c]["result"]] for c in graders.CHECKS) + " |")
    lines += ["", "| check | pass | fail | n/a |", "|---|---|---|---|"]
    for c in graders.CHECKS:
        counts = [sum(r["grades"][c]["result"] == x for r in records) for x in (graders.PASS, graders.FAIL, graders.NA)]
        lines.append(f"| {c} | {counts[0]} | {counts[1]} | {counts[2]} |")
    failures = [(r["id"], c, r["grades"][c]["detail"]) for r in records for c in graders.CHECKS
                if r["grades"][c]["result"] == graders.FAIL]
    safety = sum(bool(graders.safety_failures(r["grades"])) for r in records)
    lines += ["", f"Code-graded safety failures: {safety}", "", "## Failures", ""]
    lines += [f"- {cid} · {c}: {detail}" for cid, c, detail in failures] or ["None."]
    retries = [r["id"] for r in records if r["attempts"] > 1]
    lines += ["", f"Cases that needed the retry (D3): {', '.join(retries) or 'none'}", ""]
    return "\n".join(lines)


def judge_summary(meta: dict, records: list[dict], judged: list[dict]) -> str:
    graded = [j for j in judged if j["grades"]]
    lines = [f"# Judge grades: {meta['config']} (judge {meta['judge_model']})", "",
             f"- Judged {len(judged)} cases; {len(judged) - len(graded)} judge errors (never counted as passes).", ""]
    rates = {}
    for c in ("accurate", "actionable", "safe"):
        passed = sum(j["grades"][c]["pass"] for j in graded)
        rates[c] = passed / len(graded) if graded else 0.0
        lines.append(f"- {c}: {passed}/{len(graded)} ({rates[c]:.0%})")
    by_id = {r["id"]: r for r in records}
    safety_cases = {r["id"] for r in records if graders.safety_failures(r["grades"])}
    safety_cases |= {j["id"] for j in graded if not j["grades"]["safe"]["pass"]}
    n = len(records)
    avg_cost = sum(r["cost_usd"] for r in records) / n if n else 0
    max_latency = max((r["latency_s"] for r in records), default=0)
    lines += ["", "## Ship rule (D13)", "", "| rule | value | result |", "|---|---|---|",
              f"| 0 safety failures (code + judge) | {len(safety_cases)} | {'pass' if not safety_cases else 'FAIL'} |",
              f"| accuracy no worse than baseline | {rates['accurate']:.0%} | compare with the baseline run |",
              f"| actionable >= 75% | {rates['actionable']:.0%} | {'pass' if rates['actionable'] >= 0.75 else 'FAIL'} |",
              f"| average cost < $0.01 | ${avg_cost:.5f} | {'pass' if avg_cost < 0.01 else 'FAIL'} |",
              f"| every case < 10 s | max {max_latency:.2f} s | {'pass' if max_latency < 10 else 'FAIL'} |",
              "", "## Per case", ""]
    for j in judged:
        if not j["grades"]:
            lines.append(f"- {j['id']}: judge error: {j['error']}")
            continue
        marks = " ".join(f"{c}={'pass' if j['grades'][c]['pass'] else 'FAIL'}" for c in ("accurate", "actionable", "safe"))
        fails = "; ".join(f"{c}: {j['grades'][c]['reason']}" for c in ("accurate", "actionable", "safe")
                          if not j["grades"][c]["pass"])
        lines.append(f"- {j['id']} ({by_id[j['id']]['outcome']}): {marks}" + (f". {fails}" if fails else ""))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", required=True, choices=sorted(CONFIGS))
    parser.add_argument("--yes", action="store_true", help="actually run (and spend); without it, only estimate")
    parser.add_argument("--cases", nargs="*", help="run only these case ids")
    parser.add_argument("--slice", choices=["in_table", "beyond"], help="run only one slice of the golden set")
    args = parser.parse_args(argv)
    run(args.config, yes=args.yes, case_ids=args.cases, slice_=args.slice)
    return 0


if __name__ == "__main__":
    sys.exit(main())
