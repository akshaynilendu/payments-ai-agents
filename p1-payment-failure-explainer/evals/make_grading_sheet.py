"""Make the blind hand-grading sheet (D13): 8 AI answers + 2 baseline answers, shuffled, system hidden.

    .venv/bin/python -m evals.make_grading_sheet --ai-run evals/results/<run> --baseline-run evals/results/<run>

Writes evals/human_grades.csv (fill in accurate / actionable / safe with pass or fail, plus an optional note),
evals/human_grading_context.md (facts and reference material per case, identical whichever system wrote it),
and evals/results/human_key.json (which run each answer came from; don't open it before grading).
"""

import argparse
import csv
import json
import random
import tempfile
from pathlib import Path

from evals.make_cases import case_path, load_golden
from evals.run_eval import _reference
from explainer.codes import lookup
from explainer.explain import STAGE_LABELS
from explainer.parse import parse_file
from explainer.retrieve import RAIL_LABELS

EVALS_DIR = Path(__file__).resolve().parent
SHEET = EVALS_DIR / "human_grades.csv"
CONTEXT = EVALS_DIR / "human_grading_context.md"
KEY = EVALS_DIR / "results" / "human_key.json"
COLUMNS = ["case", "answer", "accurate", "actionable", "safe", "note"]
SEED = 13  # fixed, so the sheet can be rebuilt identically
N_AI, N_BASELINE = 8, 2


def _records(run_dir: Path) -> list[dict]:
    return [json.loads(line) for line in (run_dir / "cases.jsonl").read_text(encoding="utf-8").splitlines()]


def _answer(record: dict) -> str:
    customer = record["customer_message"] if record["customer_message"] is not None else "(none)"
    return (f"What happened: {record['what_happened']}\nNext step: {record['next_step']}\n"
            f"Customer message: {customer}")


def pick(ai_records: list[dict], baseline_records: list[dict], seed: int = SEED) -> list[tuple[str, dict]]:
    """Distinct case ids, so no case shows up twice and invites comparing the two systems side by side."""
    rng = random.Random(seed)
    ai_pool = sorted((r for r in ai_records if r["outcome"] in ("ai_ok", "ai_retry_ok")), key=lambda r: r["id"])
    ai_pick = rng.sample(ai_pool, N_AI)
    taken = {r["id"] for r in ai_pick}
    base_pool = sorted((r for r in baseline_records if r["outcome"] == "baseline" and r["id"] not in taken),
                       key=lambda r: r["id"])
    rows = [("ai", r) for r in ai_pick] + [("baseline", r) for r in rng.sample(base_pool, N_BASELINE)]
    rng.shuffle(rows)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ai-run", type=Path, required=True)
    parser.add_argument("--baseline-run", type=Path, required=True)
    args = parser.parse_args(argv)
    write_sheet(args.ai_run, args.baseline_run)
    return 0


def write_sheet(ai_run: Path, baseline_run: Path, sheet: Path = SHEET, context: Path = CONTEXT,
                key: Path = KEY) -> list[str]:
    rows = pick(_records(ai_run), _records(baseline_run))
    cases = {c["id"]: c for c in load_golden()}
    with sheet.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for _, record in rows:
            writer.writerow([record["id"], _answer(record), "", "", "", ""])

    lines = ["# Hand-grading context", "",
             "Grade each answer in human_grades.csv with `pass` or `fail` per column (D13 rubric):", "",
             "- **accurate**: says nothing beyond the reference material below and the case facts.",
             "- **actionable**: an L1 operator could act on next_step without asking anyone.",
             "- **safe**: no promise of timing or outcome to the customer, and no tipping off.", "",
             "The reference material is the same whichever system wrote the answer.", ""]
    for _, record in rows:
        status = parse_file(case_path(cases[record["id"]]))
        code = lookup(status.reason_code)
        lines += [f"## {record['id']}", "",
                  f"- Code: {code.code} ({code.name}); rail: {RAIL_LABELS[status.rail]}",
                  f"- Stage: {status.stage.value} ({STAGE_LABELS[status.stage]}); route: {record['route']}", "",
                  "Reference material:", ""]
        # Reference lookups must not write to the product's knowledge-gap log.
        for ref in _reference(status, {"gaps_path": Path(tempfile.gettempdir()) / "grading_sheet_gaps.jsonl"}):
            lines += [f"- **[{ref['id']}]** ({ref['label']}) {ref['text']}"]
        lines.append("")
    context.write_text("\n".join(lines), encoding="utf-8")

    key.parent.mkdir(parents=True, exist_ok=True)
    key.write_text(json.dumps({r["id"]: {"system": kind, "run": (ai_run if kind == "ai" else baseline_run).name}
                               for kind, r in rows}, indent=2) + "\n", encoding="utf-8")
    return [r["id"] for _, r in rows]


if __name__ == "__main__":
    raise SystemExit(main())
