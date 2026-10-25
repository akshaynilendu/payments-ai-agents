"""Mean and range across repeated runs, per version.

    python scripts/compare_runs.py            # uses every run in var/runs
    python scripts/compare_runs.py --last 3   # the latest 3 runs of each version
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

RUNS = Path(__file__).resolve().parent.parent / "var" / "runs"


def summarise(rows):
    money = sum(r["wrongly_sent"] + r.get("skipped_approval", 0) for r in rows)
    metas = [r.get("meta") or {} for r in rows]
    return {
        "right": sum(r["verdict"] == "right" for r in rows),
        "safe": sum(r["verdict"] == "safe_not_ideal" for r in rows),
        "wrong": sum(r["verdict"] == "wrong" for r in rows),
        "variants": sum(r["verdict"] == "right" for r in rows if r["slice"] == "variant"),
        "outside": sum(r["outside_mandate"] for r in rows),
        "money": money,
        "cost": sum(r["cost"] for r in rows),
        "usd_per": sum(m.get("cost_usd", 0) for m in metas) / len(rows),
        "calls_per": sum(len(m.get("tool_calls", [])) for m in metas) / len(rows),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--last", type=int)
    args = ap.parse_args()
    by_version = defaultdict(list)
    for d in sorted(RUNS.glob("*-*")):
        f = d / "results.jsonl"
        if f.exists():
            rows = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
            if len(rows) == 40:
                by_version[d.name.rsplit("-", 1)[1]].append(summarise(rows))
    print("| Version | Runs | Right | Safe, not ideal | Wrong | Variants | Outside mandate | Money wrong | Cost-weighted | $/request | Tool calls/request |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for v, runs in sorted(by_version.items()):
        runs = runs[-args.last:] if args.last else runs

        def rng(k, fmt="{:.0f}"):
            vals = [r[k] for r in runs]
            lo, hi = min(vals), max(vals)
            return fmt.format(lo) if lo == hi else f"{fmt.format(lo)}–{fmt.format(hi)}"
        print(f"| {v} | {len(runs)} | {rng('right')} | {rng('safe')} | {rng('wrong')} | {rng('variants')}/5 | "
              f"{rng('outside')} | {rng('money', '{:,.0f}')} | {rng('cost', '{:,.0f}')} | "
              f"{rng('usd_per', '${:.5f}')} | {rng('calls_per', '{:.1f}')} |")


if __name__ == "__main__":
    main()
