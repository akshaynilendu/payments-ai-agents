"""Re-grade the stored answers of an existing run with the current judge. No new AI answers.

    .venv/bin/python -m evals.rejudge --run evals/results/<run>           # estimate only
    .venv/bin/python -m evals.rejudge --run evals/results/<run> --yes     # re-grade, hard $2 cap

The previous grades are kept as judge_vN.jsonl / judge_summary_vN.md, so calibration history isn't lost.
"""

import argparse
import json
import math
import tempfile
from pathlib import Path
from typing import Callable

from evals.make_cases import load_golden
from evals.run_eval import (CAP_USD, CHARS_PER_TOKEN, TYPICAL_OUTPUT_TOKENS, BudgetExceeded, CostGuard,
                            GuardedLLM, Options, default_options, judge_record, judge_summary)
from explainer import config
from explainer.llm import AnthropicClient, LLMClient, cost_usd

JUDGE_PROMPT_CHARS = 9000  # generous: facts + every allowed passage + the answer


def _archive(run_dir: Path) -> int:
    version = 1
    while (run_dir / f"judge_v{version}.jsonl").exists():
        version += 1
    for current, archived in (("judge.jsonl", f"judge_v{version}.jsonl"),
                              ("judge_summary.md", f"judge_summary_v{version}.md")):
        if (run_dir / current).exists():
            (run_dir / current).rename(run_dir / archived)
    return version


def rejudge(run_dir: Path, *, yes: bool, judge_factory: Callable[[str], LLMClient] = AnthropicClient,
            options: Options | None = None, cap_usd: float = CAP_USD, echo: Callable[[str], None] = print) -> bool:
    records = [json.loads(line) for line in (run_dir / "cases.jsonl").read_text(encoding="utf-8").splitlines()]
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    model = config.JUDGE_MODEL
    tokens = math.ceil(JUDGE_PROMPT_CHARS / CHARS_PER_TOKEN)
    n = len(records)
    echo(f"Re-judge {run_dir.name}: up to {n} answers. Estimated ${n * cost_usd(model, tokens, TYPICAL_OUTPUT_TOKENS[model]):.3f} "
         f"typical, ${n * cost_usd(model, tokens, config.MODEL_SETTINGS[model]['max_tokens']):.3f} worst case. "
         f"Hard cap ${cap_usd:.2f}.")
    if not yes:
        echo("Nothing spent. Re-run with --yes to re-grade.")
        return False

    cases = {c["id"]: c for c in load_golden()}
    guard = CostGuard(cap_usd)
    judge = GuardedLLM(judge_factory(model), guard)
    judged = []
    with tempfile.TemporaryDirectory() as tmp:
        options = options or default_options(Path(tmp))
        try:
            for record in records:
                verdict = judge_record(cases[record["id"]], record, judge, options)
                if verdict:
                    judged.append(verdict)
        except BudgetExceeded as e:
            echo(f"STOPPED: {e}. Old grades left in place.")
            return False

    version = _archive(run_dir)
    (run_dir / "judge.jsonl").write_text("".join(json.dumps(j, ensure_ascii=False) + "\n" for j in judged),
                                         encoding="utf-8")
    meta = meta | {"judge_rerun": {"previous_saved_as": f"v{version}", "spent_usd": round(guard.spent_usd, 6)}}
    (run_dir / "judge_summary.md").write_text(judge_summary(meta, records, judged), encoding="utf-8")
    echo(f"Spent ${guard.spent_usd:.4f}. Previous grades saved as judge_v{version}.jsonl.")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)
    rejudge(args.run, yes=args.yes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
