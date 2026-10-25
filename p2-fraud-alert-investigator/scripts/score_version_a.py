"""Score Version A against the gold answers, by slice. Evaluation only: this script reads gold/, the versions never do.

Run from the project folder:  python scripts/score_version_a.py
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from investigator.data import load_dataset  # noqa: E402
from investigator.version_a import investigate  # noqa: E402


def main() -> None:
    gold = json.loads((ROOT / "gold" / "gold.json").read_text(encoding="utf-8"))["alerts"]
    ds = load_dataset()
    slices = defaultdict(lambda: [0, 0])
    rows = []
    for alert in ds.alerts:
        g = gold[alert.alert_id]
        got = investigate(ds, alert).assessment.leading_hypothesis.value
        ok = got == g["true_outcome"]
        if g["difficulty"] == "hard":
            group = "hard"
        elif g.get("variant"):
            group = "familiar: realistic variants"
        else:
            group = "familiar: textbook"
        for key in ("all", group, f"rail {alert.rail}"):
            slices[key][0] += ok
            slices[key][1] += 1
        if not ok:
            rows.append(f"  {alert.alert_id} {alert.rail:9} true={g['true_outcome']:18} got={got:21} "
                        f"({g.get('variant') or g.get('hard_kind') or 'textbook'})")
    print("Version A (code only): leading hypothesis vs gold")
    for key in ("all", "familiar: textbook", "familiar: realistic variants", "hard", "rail FPS", "rail SEPA_INST"):
        right, total = slices[key]
        print(f"  {key:30} {right:2}/{total:2}  {100 * right / total:3.0f}%")
    print("Misses:")
    print("\n".join(rows))


if __name__ == "__main__":
    main()
