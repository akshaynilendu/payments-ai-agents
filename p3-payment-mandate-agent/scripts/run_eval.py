"""Runs one version on all 40 requests and scores it.

    python scripts/run_eval.py --version A
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

import asyncio  # noqa: E402

from mandate_agent import config, version_a  # noqa: E402
from mandate_agent.agent import decision_from_audit, run_agent, server_params  # noqa: E402
from mandate_agent.bank import BankSide  # noqa: E402
from mandate_agent.orchestrator import run_orchestrated  # noqa: E402
from mandate_agent.scoring import load_gold, score_case  # noqa: E402

SLICES = ["textbook", "variant", "tricky", "attack", "ambiguous"]


def run_a(rid, run_dir):
    bank = BankSide(rid, audit_path=run_dir / "audit" / f"{rid}.jsonl")
    proposal = version_a.propose(bank)
    bank.propose_payment(**proposal)
    return bank.decisions[0], {**proposal, "request_id": rid}, {"cost_usd": 0.0}


LLM = None


def run_b(rid, run_dir):
    audit = run_dir / "audit" / f"{rid}.jsonl"
    req = BankSide(rid).world.requests[rid]
    proposal, meta = asyncio.run(run_agent(req, LLM, server_params(rid, True, audit)))
    decision = decision_from_audit(audit, rid)
    m = {"cost_usd": meta.cost_usd, "tool_calls": meta.tool_calls, "turns": meta.turns,
         "proposals": meta.proposals, "stopped": meta.stopped, "errors": meta.errors}
    return decision, ({**proposal, "request_id": rid} if proposal else None), m


def same_proposals_checks_off(rid, proposal):
    """Version C: the same agent proposals, sent to a server with every check switched off."""
    if proposal is None:
        return None
    bank = BankSide(rid, checks_on=False)
    bank.propose_payment(**{k: v for k, v in proposal.items() if k != "request_id"})
    return bank.decisions[0]


def run_d(rid, run_dir):
    audit = run_dir / "audit" / f"{rid}.jsonl"
    req = BankSide(rid).world.requests[rid]
    proposal, meta, route = asyncio.run(run_orchestrated(req, LLM, server_params(rid, True, audit)))
    decision = decision_from_audit(audit, rid)
    m = {"cost_usd": meta.cost_usd, "tool_calls": meta.tool_calls, "turns": meta.turns, "route": route,
         "proposals": meta.proposals, "stopped": meta.stopped, "errors": meta.errors}
    return decision, ({**proposal, "request_id": rid} if proposal else None), m


RUNNERS = {"A": run_a, "B": run_b, "D": run_d}


def report(version, rows, meta, run_dir):
    n = len(rows)
    right = sum(r["verdict"] == "right" for r in rows)
    out = [f"# Version {version}", "", "| Slice | Right | Safe, not ideal | Wrong |", "|---|---|---|---|"]
    out.append(f"| all | {right}/{n} | {sum(r['verdict'] == 'safe_not_ideal' for r in rows)} | {sum(r['verdict'] == 'wrong' for r in rows)} |")
    for s in SLICES:
        part = [r for r in rows if r["slice"] == s]
        out.append(f"| {s} | {sum(r['verdict'] == 'right' for r in part)}/{len(part)} | "
                   f"{sum(r['verdict'] == 'safe_not_ideal' for r in part)} | {sum(r['verdict'] == 'wrong' for r in part)} |")
    sent, skipped = defaultdict(float), defaultdict(float)
    for r in rows:
        if r["wrongly_sent"]:
            sent[r["currency"]] += r["wrongly_sent"]
        if r["skipped_approval"]:
            skipped[r["currency"]] += r["skipped_approval"]
    outside = [r["request_id"] for r in rows if r["outside_mandate"]]
    out += ["", "**Hard gate**",
            f"- Payments outside the mandate: {len(outside)} {outside if outside else ''}",
            "- Wrong payee, wrong amount or should not be paid: " + (", ".join(f"{c} {v:,.2f}" for c, v in sent.items()) or "none"),
            "- Right payment, but sent without the required approval: " + (", ".join(f"{c} {v:,.2f}" for c, v in skipped.items()) or "none"),
            "", f"**Cost-weighted errors:** {sum(r['cost'] for r in rows):,.2f}",
            f"**Model cost:** ${sum(m['cost_usd'] for m in meta):.4f} total, ${sum(m['cost_usd'] for m in meta) / n:.5f} per request",
            "", "**Not right**"]
    for r in rows:
        if r["verdict"] != "right":
            out.append(f"- {r['request_id']} ({r['slice']}): expected {r['gold']}, got {r['got']} "
                       f"[{r['verdict']}] {', '.join(r['reasons'])}" + (f" SENT {r['currency']} {r['wrongly_sent']:,.2f}" if r["wrongly_sent"] else "")
                       + (f" NO APPROVAL {r['currency']} {r['skipped_approval']:,.2f}" if r["skipped_approval"] else ""))
    text = "\n".join(out)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "report.md").write_text(text + "\n", encoding="utf-8")
    print(text)
    print(f"\nSaved to {run_dir.relative_to(ROOT)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True, choices=sorted(RUNNERS))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--model", default=config.CLAUDE_MODEL)
    args = parser.parse_args()
    if args.version != "A":
        global LLM
        from mandate_agent.llm import AnthropicClient
        LLM = AnthropicClient(args.model)
    gold = load_gold()
    ids = sorted(gold)[: args.limit] if args.limit else sorted(gold)
    run_dir = ROOT / "var" / "runs" / f"{datetime.now():%Y%m%d-%H%M%S}-{args.version}"
    run_dir.mkdir(parents=True, exist_ok=True)
    rows, meta, rows_c = [], [], []
    spent = 0.0
    for rid in ids:
        t0 = time.time()
        decision, proposal, m = RUNNERS[args.version](rid, run_dir)
        m["seconds"] = round(time.time() - t0, 2)
        spent += m["cost_usd"]
        row = score_case(gold[rid], decision, proposal)
        row["proposal"], row["meta"] = proposal, m
        rows.append(row)
        meta.append(m)
        if args.version != "A":
            rows_c.append(score_case(gold[rid], same_proposals_checks_off(rid, proposal), proposal))
        print(f"{rid} {row['verdict']:<15} {row['got']:<18} ${m['cost_usd']:.5f} {m['seconds']}s", file=sys.stderr)
        if spent > config.RUN_COST_CAP_USD:
            print("Cost cap reached, stopping.", file=sys.stderr)
            break
    (run_dir / "results.jsonl").write_text("\n".join(json.dumps(r, default=str) for r in rows) + "\n", encoding="utf-8")
    report(args.version, rows, meta, run_dir)
    if args.version != "A":
        calls = [len(m.get("tool_calls", [])) for m in meta]
        print(f"\n**Agent use:** {sum(calls)} tool calls ({sum(calls) / len(calls):.1f} per request), "
              f"slowest {max(m['seconds'] for m in meta)}s, no proposal: "
              f"{[r['request_id'] for r in rows if r['proposal'] is None]}, extra proposals refused: "
              f"{sum(max(0, m['proposals'] - 1) for m in meta)}")
        routes = [m["route"] for m in meta if "route" in m]
        if routes:
            print("**Routes:** " + ", ".join(f"{k} {routes.count(k)}" for k in ("REFUND", "SUPPLIER", "HUMAN")))
    if rows_c:
        print()
        report("C (same proposals, every check off)", rows_c, [{"cost_usd": 0.0}] * len(rows_c), run_dir / "c")


if __name__ == "__main__":
    main()
