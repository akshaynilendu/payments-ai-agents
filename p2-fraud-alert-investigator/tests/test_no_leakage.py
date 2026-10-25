import json
import re
from pathlib import Path

import pytest

from investigator import data
from investigator.data import GOLD_DIR, _read

ROOT = Path(__file__).resolve().parent.parent


def test_every_past_case_closes_before_every_alert(ds):
    first_alert = min(a.received_at for a in ds.alerts)
    assert all(pc.closed_at < first_alert for pc in ds.past_cases)


def test_loader_refuses_the_gold_folder():
    with pytest.raises(PermissionError):
        _read(GOLD_DIR, "gold.json")
    with pytest.raises(PermissionError):
        _read(ROOT / "data", "../gold/gold.json")  # however the path is spelled


def test_investigator_code_never_mentions_the_gold_file():
    for py in (ROOT / "investigator").rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        assert "gold.json" not in text, py
        if py.name != "data.py":  # data.py names the folder only to refuse it
            assert not re.search(r"\bgold\b", text, re.IGNORECASE), py


def test_gold_is_not_in_the_dataset_folder():
    assert not any("true_outcome" in p.read_text(encoding="utf-8") for p in (ROOT / "data").glob("*.json"))


def test_alert_data_carries_no_outcome_fields():
    alerts = json.loads((ROOT / "data" / "alerts.json").read_text(encoding="utf-8"))
    banned = {"outcome", "true_outcome", "label", "difficulty", "hard_kind"}
    assert all(not banned & set(a) for a in alerts)


def test_gold_shape(gold, ds, summaries):
    assert set(gold) == {a.alert_id for a in ds.alerts}
    from collections import Counter
    by_rail = Counter((g["rail"], g["true_outcome"]) for g in gold.values())
    for rail in ("FPS", "SEPA_INST"):
        assert {o for r, o in by_rail if r == rail} == {"GENUINE", "ACCOUNT_TAKEOVER", "APP_IMPERSONATION",
                                                        "APP_INVESTMENT", "APP_PURCHASE", "APP_INVOICE_CEO"}
    hard = Counter((g["rail"], g["hard_kind"]) for g in gold.values() if g["difficulty"] == "hard")
    assert hard == {("FPS", "mixed"): 1, ("FPS", "novel_remote_access"): 1, ("FPS", "novel_own_name_exchange"): 1,
                    ("FPS", "injection_reference"): 1, ("SEPA_INST", "mixed"): 1, ("SEPA_INST", "injection_payee_name"): 1}
    for aid, g in gold.items():
        assert g["rail"] == summaries[aid].rail
        assert set(g["key_evidence_ids"]) <= set(summaries[aid].check_result_ids), aid


def test_regeneration_is_reproducible():
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    from generate_data import generate
    g = generate()
    assert g.alerts == json.loads((ROOT / "data" / "alerts.json").read_text(encoding="utf-8"))
    assert g.gold == json.loads((ROOT / "gold" / "gold.json").read_text(encoding="utf-8"))["alerts"]
