"""Majority vote over the last 3 judge passes of a run (the judge isn't repeatable: Sonnet 5.5 rejects
temperature 0, so one pass is too noisy to ship on).

    .venv/bin/python -m evals.majority evals/results/<run> [...]

Writes judge_majority.jsonl and majority_summary.md into each run. Compare with:
    .venv/bin/python -m evals.compare --judge-file judge_majority.jsonl <baseline run> <run> ...
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from evals.judge import CRITERIA

PASSES = 3


def pass_files(run_dir: Path) -> list[Path]:
    """The latest PASSES judge files: archived versions (judge_vN.jsonl) then the current judge.jsonl."""
    versions = sorted(run_dir.glob("judge_v*.jsonl"), key=lambda p: int(p.stem.split("_v")[1]))
    files = versions + [run_dir / "judge.jsonl"]
    if len(files) < PASSES:
        raise ValueError(f"{run_dir.name}: needs {PASSES} judge passes, has {len(files)}")
    return files[-PASSES:]


def majority(run_dir: Path) -> tuple[list[dict], dict]:
    passes = [{(r := json.loads(line))["id"]: r for line in f.read_text(encoding="utf-8").splitlines()}
              for f in pass_files(run_dir)]
    stats = {"grades": 0, "unanimous": 0, "split": Counter(), "changed": [0] * (PASSES - 1), "missing_votes": 0}
    rows = []
    for cid in sorted(set().union(*passes)):
        grades = {}
        for c in CRITERIA:
            # A judge error is a missing vote, never a pass.
            votes = [p[cid]["grades"][c]["pass"] for p in passes if p.get(cid) and p[cid]["grades"]]
            stats["missing_votes"] += PASSES - len(votes)
            if len(votes) == PASSES:
                stats["grades"] += 1
                if len(set(votes)) == 1:
                    stats["unanimous"] += 1
                else:
                    stats["split"][c] += 1
                for i in range(PASSES - 1):
                    stats["changed"][i] += votes[i] != votes[i + 1]
            passed = votes.count(True) > len(votes) / 2 if votes else False
            grades[c] = {"pass": passed, "reason": f"majority of {len(votes)}: {votes.count(True)} pass, "
                                                  f"{votes.count(False)} fail"}
        rows.append({"id": cid, "grades": grades, "error": None if any(p.get(cid) for p in passes) else "no votes"})
    stats["files"] = [f.name for f in pass_files(run_dir)]
    return rows, stats


def summary(run_name: str, stats: dict) -> str:
    n = stats["grades"]
    split = stats["split"]
    return (f"# Judge majority vote: {run_name}\n\n"
            f"- Passes: {', '.join(stats['files'])}\n"
            f"- Unanimous: {stats['unanimous']}/{n} ({stats['unanimous'] / n if n else 0:.0%}); "
            f"split 2-1: accurate {split['accurate']}, actionable {split['actionable']}, safe {split['safe']}\n"
            f"- Grades that changed between consecutive passes: {stats['changed']}\n"
            f"- Missing votes (judge errors): {stats['missing_votes']}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("runs", nargs="+", type=Path)
    args = parser.parse_args(argv)
    for run_dir in args.runs:
        rows, stats = majority(run_dir)
        (run_dir / "judge_majority.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        text = summary(run_dir.name, stats)
        (run_dir / "majority_summary.md").write_text(text, encoding="utf-8")
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
