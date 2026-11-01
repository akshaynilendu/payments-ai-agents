"""Runs one version on all 30 disputes and scores the engine's decisions.

    python scripts/run_eval.py --version A
    python scripts/run_eval.py --version B
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dispute_desk.engine import Engine  # noqa: E402
from dispute_desk.scoring import load_gold, score_case  # noqa: E402
from dispute_desk.version_a import propose  # noqa: E402
from dispute_desk.world import World  # noqa: E402

SLICES = ["textbook", "messy", "tricky", "trap"]


def _money(totals: dict) -> str:
    if not totals:
        return "none"
    return ", ".join(f"{currency} {amount:,.2f}" for currency, amount in sorted(totals.items()))


def report(version, rows, meta, run_dir: Path):
    n = len(rows)
    right = sum(row["verdict"] == "right" for row in rows)
    out = [f"# Version {version}", "", "| Slice | Right | Safe, not ideal | Wrong |", "|---|---|---|---|"]
    out.append(
        f"| all | {right}/{n} | {sum(row['verdict'] == 'safe_not_ideal' for row in rows)} | "
        f"{sum(row['verdict'] == 'wrong' for row in rows)} |"
    )
    for name in SLICES:
        part = [row for row in rows if row["slice"] == name]
        out.append(
            f"| {name} | {sum(row['verdict'] == 'right' for row in part)}/{len(part)} | "
            f"{sum(row['verdict'] == 'safe_not_ideal' for row in part)} | "
            f"{sum(row['verdict'] == 'wrong' for row in part)} |"
        )
    recovered, accepted = defaultdict(float), defaultdict(float)
    for row in rows:
        # A right fight can recover a negative amount (DP-24). That still counts.
        if row["verdict"] == "right" and row["got"] == "FIGHT":
            recovered[row["currency"]] += row["recovered"]
        if row["accepted_loss"]:
            accepted[row["currency"]] += row["accepted_loss"]
    missed = [row["dispute_id"] for row in rows if row["missed_deadline"]]
    refunded = sum(row["verdict"] == "right" and row["got"] == "ALREADY_REFUNDED" for row in rows)
    changed = [row for row in rows if row["proposed"] != row["got"]]
    out += [
        "",
        "**Money recovered after fees** (right fights: amount − fee − fight cost)",
        "- " + _money(recovered),
        "",
        "**Accepted, fee kept** (right accepts: amount + fee)",
        "- " + _money(accepted),
        "",
        f"**Already refunded:** {refunded} (recovered 0; not paid twice)",
        f"**Missed deadlines:** {len(missed)}" + (f" {missed}" if missed else ""),
        f"**Model cost:** ${sum(item['cost_usd'] for item in meta):.4f} total, "
        f"${sum(item['cost_usd'] for item in meta) / n:.5f} per dispute",
        f"**Seconds:** {sum(item['seconds'] for item in meta):.2f} total",
        "",
        f"**Proposals the engine changed:** {len(changed)}",
    ]
    for row in changed:
        out.append(f"- {row['dispute_id']} ({row['slice']}): proposed {row['proposed']}, decided {row['got']}")
    out += ["", "**Not right**"]
    any_miss = False
    for row in rows:
        if row["verdict"] != "right":
            any_miss = True
            out.append(
                f"- {row['dispute_id']} ({row['slice']}): expected {row['gold']} {row['gold_priority']}, "
                f"got {row['got']} {row['priority']} [{row['verdict']}] {', '.join(row['reasons'])}"
            )
    if not any_miss:
        out.append("- none")
    text = "\n".join(out)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "report.md").write_text(text + "\n", encoding="utf-8")
    print(text)
    print(f"\nSaved to {run_dir.relative_to(ROOT)}")


def _no_proposal(dispute_id, world):
    from datetime import date

    from dispute_desk.schema import Decision, Finding, Outcome
    dispute = world.dispute(dispute_id)
    priority = Engine(world).priority(date.fromisoformat(dispute["respond_by"]))
    return Decision(
        dispute_id=dispute_id,
        outcome=Outcome.ASK_HUMAN,
        priority=priority,
        reasons=[Finding(code="NO_PROPOSAL", detail="The agent made no proposal.")],
        evidence_pack={},
    )


def run_b(dispute_id, run_dir, llm, world):
    import asyncio

    from dispute_desk.agent import decision_from_audit, run_agent, server_params
    audit = run_dir / "audit" / f"{dispute_id}.jsonl"
    dispute = world.dispute(dispute_id)
    proposal, meta = asyncio.run(run_agent(dispute, llm, server_params(dispute_id, audit)))
    decision = decision_from_audit(audit, dispute_id) or _no_proposal(dispute_id, world)
    spent = {"cost_usd": meta.cost_usd, "seconds": 0.0, "tool_calls": meta.tool_calls, "turns": meta.turns,
             "stopped": meta.stopped, "errors": meta.errors}
    return decision, (proposal or {}).get("outcome"), spent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True, choices=["A", "B"])
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    world = World()
    engine = Engine(world)
    gold = load_gold()
    ids = sorted(gold)[: args.limit] if args.limit else sorted(gold)
    run_dir = ROOT / "var" / "runs" / f"{datetime.now():%Y%m%d-%H%M%S}-{args.version}"
    run_dir.mkdir(parents=True, exist_ok=True)
    llm = None
    cost_cap = None
    if args.version == "B":
        from dispute_desk.agent import make_client
        from mandate_agent import config
        llm = make_client()
        cost_cap = config.RUN_COST_CAP_USD
    rows, meta = [], []
    spent_usd = 0.0
    for dispute_id in ids:
        t0 = time.time()
        if args.version == "A":
            proposal = propose(world, dispute_id)
            decision = engine.decide(proposal)
            proposed = proposal.outcome.value
            step = {"cost_usd": 0.0}
        else:
            decision, proposed, step = run_b(dispute_id, run_dir, llm, world)
        step["seconds"] = round(time.time() - t0, 2)
        spent_usd += step["cost_usd"]
        row = score_case(gold[dispute_id], decision, world)
        row["proposed"] = proposed
        rows.append(row)
        meta.append(step)
        print(f"{dispute_id} {row['verdict']:<15} {row['got']:<18} {row['priority']:<12} "
              f"${step['cost_usd']:.5f} {step['seconds']}s", file=sys.stderr)
        if cost_cap is not None and spent_usd > cost_cap:
            print("Cost cap reached, stopping.", file=sys.stderr)
            break
    (run_dir / "results.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
    )
    if args.version == "A":
        (run_dir / "audit.jsonl").write_text(
            "\n".join(json.dumps(entry, default=str) for entry in engine.audit.entries) + "\n",
            encoding="utf-8",
        )
        if not engine.audit.verify():
            raise SystemExit("audit hash chain does not verify")
    report(args.version, rows, meta, run_dir)


if __name__ == "__main__":
    main()
