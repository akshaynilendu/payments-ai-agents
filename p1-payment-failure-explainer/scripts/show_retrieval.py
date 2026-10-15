"""Developer tool, not part of the product: show what retrieval returns for ~20 cases with the real model.

Run from the project folder: .venv/bin/python scripts/show_retrieval.py
"""

import sys
import tempfile
from pathlib import Path

# Running a file in scripts/ puts scripts/ on the import path, not the project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from explainer.codes import Rail, Stage  # noqa: E402
from explainer.knowledge import all_passages  # noqa: E402
from explainer.parse import parse_file, parse_xml  # noqa: E402
from explainer.pipeline import prepare  # noqa: E402
from explainer.retrieve import retrieve  # noqa: E402

EXTRA_CASES = [
    ("AC01", Rail.SEPA_INSTANT, Stage.REJECT), ("AG01", Rail.SEPA_INSTANT, Stage.REJECT),
    ("MS03", Rail.SEPA_INSTANT, Stage.REJECT),
    ("AG01", Rail.SEPA_DD, Stage.REJECT), ("MD06", Rail.SEPA_DD, Stage.RETURN), ("RR04", Rail.SEPA_DD, Stage.REJECT),
    ("AC03", Rail.RTP, Stage.REJECT), ("AG01", Rail.RTP, Stage.REJECT), ("DS24", Rail.RTP, Stage.REJECT),
    ("AC04", Rail.UNKNOWN, Stage.REJECT), ("RR04", Rail.UNKNOWN, Stage.REJECT),
    # FRAD at both stages shows what D10 changes: nothing at reject, recall advice at recall.
    ("FRAD", Rail.SEPA_INSTANT, Stage.REJECT), ("FRAD", Rail.SEPA_INSTANT, Stage.RECALL),
    # Unknown stage: only advice true at every stage, plus guardrails.
    ("AC04", Rail.SEPA_INSTANT, Stage.UNKNOWN), ("RR04", Rail.SEPA_DD, Stage.UNKNOWN),
]


def main() -> None:
    samples = sorted((PROJECT_ROOT / "samples").glob("*.xml"))
    # Go through the real parser so the cases are exactly what the product would see.
    parsed = [(s.name, parse_file(s)) for s in samples]
    cases = [(name, p.reason_code, p.rail, p.stage) for name, p in parsed]
    cases += [("extra", code, rail, stage) for code, rail, stage in EXTRA_CASES]

    # Demo runs must not pollute the real knowledge-gap log, so gaps go to a temp file.
    with tempfile.TemporaryDirectory() as tmp:
        gaps_path = Path(tmp) / "gaps.jsonl"
        for n, (origin, code, rail, stage) in enumerate(cases, 1):
            lines_before = _count_lines(gaps_path)
            result = retrieve(code, rail, stage, gaps_path=gaps_path)
            gap_logged = _count_lines(gaps_path) > lines_before
            print(f"\n[{n:02}] {code} on {rail.value} at {stage.value}  ({origin})  "
                  f"gap logged: {'YES' if gap_logged else 'no'}")
            for rank, item in enumerate(result.all(), 1):
                flag = "MANDATORY" if item.passage.mandatory else "         "
                score = f"{item.score:.2f}" if item.score is not None else " -- "
                text = item.passage.text[:80].replace("\n", " ")
                print(f"  {rank}. {item.passage.id:<16} {score}  {flag}  {text}")
            if not result.all():
                print("  (no passages)")

    # A settled payment stops before lookup and retrieval.
    settled = (PROJECT_ROOT / "samples" / "sct_inst_ac04_closed.xml").read_text(encoding="utf-8")
    start, end = settled.index("<StsRsnInf>"), settled.index("</StsRsnInf>") + len("</StsRsnInf>")
    settled = settled[:start].replace("<TxSts>RJCT</TxSts>", "<TxSts>ACSC</TxSts>") + settled[end:]
    prepared = prepare(parse_xml(settled))
    print(f"\n[--] ACSC (settled) on SEPA_INSTANT: {prepared.outcome.value}: {prepared.message}")

    full = next(p for p in all_passages() if p.id == "KB-RTP-GEN-01")
    print(f"\nFull text of {full.id} ({full.source_url}):\n{full.text}")


def _count_lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines()) if path.exists() else 0


if __name__ == "__main__":
    main()
