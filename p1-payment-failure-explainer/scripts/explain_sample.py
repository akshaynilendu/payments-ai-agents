"""Developer tool, not part of the product: explain one sample end to end through explain() (D17).

A code in the table uses the table's text and makes no model call ($0). The default sample, CNOR, is a valid
ISO code outside the table, so it makes one paid call (well under $0.01). Needs ANTHROPIC_API_KEY in
.env.server (gitignored). Run from the project folder: .venv/bin/python scripts/explain_sample.py [sample.xml]
"""

import json
import sys
from dataclasses import asdict
from pathlib import Path

# Running a file in scripts/ puts scripts/ on the import path, not the project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from explainer import config  # noqa: E402
from explainer.llm import AnthropicClient  # noqa: E402
from explainer.parse import parse_file  # noqa: E402
from explainer.pipeline import explain  # noqa: E402


def main() -> None:
    sample = sys.argv[1] if len(sys.argv) > 1 else "sct_inst_cnor_unknown.xml"
    status = parse_file(PROJECT_ROOT / "samples" / sample)
    result = explain(status, AnthropicClient())

    print(json.dumps(asdict(result), indent=2, default=str))
    print(f"\nModel: {result.model}   outcome: {result.outcome.value}   attempts: {result.attempts}")
    print(f"Tokens: {result.input_tokens} in / {result.output_tokens} out   "
          f"cost: ${result.cost_usd:.5f} (prices checked {config.PRICING_CHECKED_ON})   "
          f"latency: {result.latency_s:.2f} s")


if __name__ == "__main__":
    main()
