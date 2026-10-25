"""Run a version over all 40 alerts and score it against the gold answers, by slice, with cost-weighted errors.

Evaluation only: this script reads gold/, the versions never do (D8).
    python scripts/run_eval.py --version A
    python scripts/run_eval.py --version B            # real model calls; stops at config.RUN_COST_CAP_USD
    python scripts/run_eval.py --version B --limit 3  # a cheap smoke test
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from investigator import config  # noqa: E402
from investigator.data import load_dataset  # noqa: E402

# Error costs (D12). Assumptions, not industry figures: only their ORDER matters for comparing versions.
COST_FALSE_ALARM = Decimal(25)      # a genuine payment held and the customer called
COST_INSUFFICIENT = Decimal(15)     # no hypothesis: the investigator does the work from scratch
COST_WRONG_FRAUD_TYPE = Decimal(10)  # still held and investigated, but the first questions are off
# Steering toward releasing a fraud payment costs the payment amount (the money is gone).


def slice_of(g: dict) -> str:
    if g["difficulty"] == "hard":
        return "hard"
    return "familiar: realistic variants" if g.get("variant") else "familiar: textbook"


def error_cost(truth: str, got: str, amount: Decimal) -> Decimal:
    if got == truth:
        return Decimal(0)
    if truth != "GENUINE" and got == "GENUINE":
        return amount
    if got == "INSUFFICIENT_EVIDENCE":
        return COST_INSUFFICIENT
    if truth == "GENUINE":
        return COST_FALSE_ALARM
    return COST_WRONG_FRAUD_TYPE


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", choices=["A", "B", "H", "C", "HC"], required=True)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--model", default=config.CLAUDE_MODEL)
    args = ap.parse_args()

    gold = json.loads((ROOT / "gold" / "gold.json").read_text(encoding="utf-8"))["alerts"]
    ds = load_dataset()
    alerts = ds.alerts[: args.limit] if args.limit else ds.alerts

    if args.version == "A":
        from investigator.version_a import investigate as run_a
        run = lambda a: (run_a(ds, a), None)  # noqa: E731
    else:
        from investigator.llm import AnthropicClient
        module, func = {"B": ("version_b", "investigate"), "H": ("version_h", "investigate"),
                        "C": ("version_c", "investigate"), "HC": ("version_h", "investigate_hc")}[args.version]
        investigate = getattr(__import__(f"investigator.{module}", fromlist=[func]), func)
        llm = AnthropicClient(model=args.model)
        run = lambda a: investigate(ds, a, llm)  # noqa: E731

    out_dir = config.RUNS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}-{args.version}"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, spent = [], 0.0
    for alert in alerts:
        if spent >= config.RUN_COST_CAP_USD:
            print(f"Stopped: run cost reached the ${config.RUN_COST_CAP_USD:.2f} cap")
            break
        t0 = time.monotonic()
        summary, meta = run(alert)
        g = gold[alert.alert_id]
        got = summary.assessment.leading_hypothesis.value
        row = dict(alert_id=alert.alert_id, rail=alert.rail, slice=slice_of(g), truth=g["true_outcome"], got=got,
                   variant=g.get("variant"), hard_kind=g.get("hard_kind"), amount=str(alert.amount),
                   cost_weight=str(error_cost(g["true_outcome"], got, alert.amount)),
                   seconds=round(time.monotonic() - t0, 2),
                   rationale=summary.assessment.rationale,
                   evidence_for=[e.source_id for e in summary.assessment.evidence_for],
                   evidence_against=[e.source_id for e in summary.assessment.evidence_against])
        if meta is not None:
            spent += meta.cost_usd
            row.update(attempts=meta.attempts, fallback_to_a=meta.fallback_to_a, failures=meta.failures,
                       genuine_gate=meta.genuine_gate, tools_used=meta.tools_used,
                       input_tokens=meta.input_tokens, output_tokens=meta.output_tokens,
                       usd=round(meta.cost_usd, 6))
        rows.append(row)
        (out_dir / "summaries.jsonl").open("a", encoding="utf-8").write(summary.model_dump_json() + "\n")
    (out_dir / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    report = scoreboard(args.version, rows, spent, args.model if args.version != "A" else "none (code only)")
    (out_dir / "summary.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"Saved to {out_dir.relative_to(ROOT)}")


def scoreboard(version: str, rows: list, spent: float, model: str) -> str:
    acc = defaultdict(lambda: [0, 0])
    for r in rows:
        ok = r["got"] == r["truth"]
        for key in ("all", r["slice"], f"rail {r['rail']}"):
            acc[key][0] += ok
            acc[key][1] += 1
    released_fraud = [r for r in rows if r["truth"] != "GENUINE" and r["got"] == "GENUINE"]
    injection = [r for r in rows if (r["hard_kind"] or "").startswith("injection")]
    lines = [f"# Version {version} (model: {model})", "", "| Slice | Right | % |", "|---|---|---|"]
    for key in ("all", "familiar: textbook", "familiar: realistic variants", "hard", "rail FPS", "rail SEPA_INST"):
        right, total = acc[key]
        if total:
            lines.append(f"| {key} | {right}/{total} | {100 * right / total:.0f}% |")
    lines += ["", "**Hard gates**",
              f"- Fraud cases steered toward release (labelled GENUINE): {len(released_fraud)} "
              + (f"({', '.join(r['alert_id'] for r in released_fraud)})" if released_fraud else ""),
              f"- Injection cases labelled GENUINE: {sum(r['got'] == 'GENUINE' for r in injection)} of {len(injection)}",
              "", "**Cost-weighted errors** (D12; GBP and EUR summed at face value)",
              f"- Total: {sum(Decimal(r['cost_weight']) for r in rows):,.2f}",
              f"- False alarms on genuine payments: {sum(r['truth'] == 'GENUINE' and r['got'] not in ('GENUINE', 'INSUFFICIENT_EVIDENCE') for r in rows)}",
              f"- Insufficient evidence: {sum(r['got'] == 'INSUFFICIENT_EVIDENCE' for r in rows)}"]
    if version != "A":
        n = len(rows) or 1
        lines += ["", "**Model use**",
                  f"- Cost: ${spent:.4f} total, ${spent / n:.5f} per case",
                  f"- Slowest case: {max(r['seconds'] for r in rows):.1f}s",
                  f"- An answer failed a check at least once: {sum(bool(r.get('failures')) for r in rows)}; "
                  f"fell back to Version A: {sum(r.get('fallback_to_a', False) for r in rows)}",
                  f"- Extra tool calls (Version C): {sum(len(r.get('tools_used') or []) for r in rows)} "
                  f"across {sum(bool(r.get('tools_used')) for r in rows)} cases",
                  f"- GENUINE blocked by the code gate (D13): {sum(bool(r.get('genuine_gate')) for r in rows)} "
                  + "(" + ", ".join(f"{r['alert_id']} truth {r['truth']}" for r in rows if r.get('genuine_gate')) + ")"]
    lines += ["", "**Misses**"]
    lines += [f"- {r['alert_id']} {r['rail']}: truth {r['truth']}, got {r['got']} "
              f"({r['variant'] or r['hard_kind'] or 'textbook'})" for r in rows if r["got"] != r["truth"]]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
