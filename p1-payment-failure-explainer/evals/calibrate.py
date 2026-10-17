"""Compare Akshay's blind hand grades with the LLM judge, per criterion (D13).

    .venv/bin/python -m evals.calibrate
"""

import argparse
import csv
import json
from pathlib import Path

from evals.judge import CRITERIA
from evals.make_grading_sheet import KEY, SHEET

RESULTS_DIR = Path(__file__).resolve().parent / "results"
_VALUES = {"pass": True, "p": True, "yes": True, "y": True, "1": True,
           "fail": False, "f": False, "no": False, "n": False, "0": False}


def read_human(sheet: Path) -> dict[str, dict]:
    """Every grade must be filled in: an empty cell would silently count as agreement or disagreement."""
    grades, problems = {}, []
    with sheet.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            case = row["case"]
            grades[case] = {"note": row.get("note", "")}
            for c in CRITERIA:
                value = (row.get(c) or "").strip().lower()
                if value not in _VALUES:
                    problems.append(f"{case}.{c}={row.get(c)!r}")
                else:
                    grades[case][c] = _VALUES[value]
    if problems:
        raise ValueError("fill in pass/fail for: " + ", ".join(problems))
    return grades


def read_judge(key: dict, results_dir: Path) -> dict[str, dict]:
    judged = {}
    for run in {v["run"] for v in key.values()}:
        for line in (results_dir / run / "judge.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if key.get(row["id"], {}).get("run") == run:
                judged[row["id"]] = row
    return judged


def calibrate(human: dict, judged: dict) -> dict:
    report = {"per_criterion": {}, "disagreements": [], "judge_errors": []}
    for c in CRITERIA:
        pairs = [(h[c], judged[cid]["grades"][c]["pass"]) for cid, h in human.items()
                 if judged.get(cid, {}).get("grades")]
        agree = sum(a == b for a, b in pairs)
        report["per_criterion"][c] = {
            "n": len(pairs), "agree": agree, "agreement": agree / len(pairs) if pairs else 0.0,
            # Which way the judge errs matters: lenient on "safe" is worse than strict.
            "judge_more_lenient": sum(b and not a for a, b in pairs),
            "judge_more_strict": sum(a and not b for a, b in pairs),
        }
    for cid, h in sorted(human.items()):
        j = judged.get(cid)
        if not j or not j.get("grades"):
            report["judge_errors"].append(cid)
            continue
        for c in CRITERIA:
            if h[c] != j["grades"][c]["pass"]:
                report["disagreements"].append({
                    "case": cid, "criterion": c, "human": "pass" if h[c] else "fail",
                    "judge": "pass" if j["grades"][c]["pass"] else "fail",
                    "judge_reason": j["grades"][c]["reason"], "human_note": h["note"]})
    return report


ADJUDICATIONS = Path(__file__).resolve().parent / "adjudications.json"
RULING_LABELS = {"A": "Akshay right", "J": "judge right", "?": "ambiguous"}


def read_adjudications(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    rulings = data["rulings"]
    bad = {k: v for k, v in rulings.items() if v not in RULING_LABELS}
    if bad:
        raise ValueError(f"rulings must be A, J or ?: {bad}")
    return rulings


def adjudicate(report: dict, rulings: dict[str, str]) -> dict:
    """Judge correctness after adjudication: right if it agreed with Akshay, or the disagreement was ruled J.
    Ambiguous and pending disagreements are left out of the rate and counted separately."""
    for d in report["disagreements"]:
        d["adjudicated"] = rulings.get(f"{d['case']}.{d['criterion']}", "pending")
    for c, r in report["per_criterion"].items():
        mine = [d["adjudicated"] for d in report["disagreements"] if d["criterion"] == c]
        judge_right = r["agree"] + mine.count("J")
        decided = r["n"] - mine.count("?") - mine.count("pending")
        r["adjudicated"] = {"judge_right": judge_right, "decided": decided,
                            "rate": judge_right / decided if decided else 0.0,
                            "akshay_right": mine.count("A"), "judge_ruled": mine.count("J"), "ambiguous": mine.count("?"),
                            "pending": mine.count("pending")}
    return report


def format_report(report: dict) -> str:
    lines = ["# Judge calibration (judge vs Akshay, blind)", "",
             "Blind grades are unchanged. \"After adjudication\" counts the judge right where it agreed with "
             "Akshay or a disagreement was ruled J (judge right); ambiguous and pending rulings are left out.", "",
             "| criterion | agreement (blind) | judge more lenient | judge more strict | after adjudication | A / J / ? / pending |",
             "|---|---|---|---|---|---|"]
    for c, r in report["per_criterion"].items():
        a = r.get("adjudicated")
        after = f"{a['judge_right']}/{a['decided']} ({a['rate']:.0%})" if a else "-"
        counts = f"{a['akshay_right']} / {a['judge_ruled']} / {a['ambiguous']} / {a['pending']}" if a else "-"
        lines.append(f"| {c} | {r['agree']}/{r['n']} ({r['agreement']:.0%}) | {r['judge_more_lenient']} | "
                     f"{r['judge_more_strict']} | {after} | {counts} |")
    lines += ["", "## Disagreements", "",
              "| case | criterion | you | judge | adjudicated | judge's reason | your note |", "|---|---|---|---|---|---|---|"]
    cell = lambda text: (text or "").replace("|", "/").replace("\n", " ")
    for d in report["disagreements"]:
        ruling = d.get("adjudicated", "pending")
        label = f"{ruling} ({RULING_LABELS[ruling]})" if ruling in RULING_LABELS else ruling
        lines.append(f"| {d['case']} | {d['criterion']} | {d['human']} | {d['judge']} | {label} | "
                     f"{cell(d['judge_reason'])} | {cell(d['human_note'])} |")
    if not report["disagreements"]:
        lines.append("| - | - | - | - | - | - | - |")
    if report.get("adjudicated_by"):
        lines += ["", f"Adjudicated by {report['adjudicated_by']}."]
    for key, note in report.get("adjudication_notes", {}).items():
        lines.append(f"- {key}: {note}")
    if report["judge_errors"]:
        lines += ["", f"Judge errors (not compared): {', '.join(report['judge_errors'])}"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sheet", type=Path, default=SHEET)
    parser.add_argument("--key", type=Path, default=KEY)
    parser.add_argument("--adjudications", type=Path, default=ADJUDICATIONS)
    args = parser.parse_args(argv)
    key = json.loads(args.key.read_text(encoding="utf-8"))
    report = adjudicate(calibrate(read_human(args.sheet), read_judge(key, RESULTS_DIR)),
                        read_adjudications(args.adjudications))
    if args.adjudications.exists():
        data = json.loads(args.adjudications.read_text(encoding="utf-8"))
        report["adjudicated_by"] = data.get("adjudicated_by")
        report["adjudication_notes"] = data.get("notes", {})
    text = format_report(report)
    (RESULTS_DIR / "calibration.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
