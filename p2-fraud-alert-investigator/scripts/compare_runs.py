"""Combine saved runs into one comparison: per version, the mean and range over repeated runs.

    python scripts/compare_runs.py RUN_DIR [RUN_DIR ...]      (folders under var/runs)
Writes nothing; prints a markdown table for the README.
"""

import json
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SLICES = ["familiar: textbook", "familiar: realistic variants", "hard"]


def load(run_dir: Path) -> tuple[str, list]:
    version = run_dir.name.split("-")[-1]
    rows = [json.loads(line) for line in (run_dir / "results.jsonl").read_text().splitlines() if line]
    return version, rows


def stats(values: list[float]) -> str:
    mean = sum(values) / len(values)
    if len(values) == 1 or min(values) == max(values):
        return f"{mean:g}"
    return f"{mean:.1f} ({min(values):g}-{max(values):g})"


def main() -> None:
    runs = defaultdict(list)
    for arg in sys.argv[1:]:
        path = Path(arg) if Path(arg).is_absolute() else ROOT / "var" / "runs" / arg
        version, rows = load(path)
        if len(rows) == 40:
            runs[version].append(rows)
    print("| Version | Runs | Right (of 40) | Textbook (23) | Variants (11) | Hard (6) | Fraud labelled GENUINE "
          "| Cost-weighted errors | $ per case |")
    print("|---|---|---|---|---|---|---|---|---|")
    for version in ["A", "B", "C", "H", "HC"]:
        if version not in runs:
            continue
        rs = runs[version]
        right = [sum(r["got"] == r["truth"] for r in rows) for rows in rs]
        per_slice = [[sum(r["got"] == r["truth"] for r in rows if r["slice"] == s) for rows in rs] for s in SLICES]
        released = [sum(r["truth"] != "GENUINE" and r["got"] == "GENUINE" for r in rows) for rows in rs]
        cost = [float(sum(Decimal(r["cost_weight"]) for r in rows)) for rows in rs]
        usd = [sum(r.get("usd", 0) for r in rows) / 40 for rows in rs]
        print(f"| {version} | {len(rs)} | {stats(right)} | " + " | ".join(stats(v) for v in per_slice)
              + f" | {stats(released)} | {stats(cost)} | ${sum(usd) / len(usd):.5f} |")


if __name__ == "__main__":
    main()
