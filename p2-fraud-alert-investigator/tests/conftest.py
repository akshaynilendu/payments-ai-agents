import json
from pathlib import Path

import pytest

from investigator.data import load_dataset
from investigator.version_a import investigate

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def ds():
    return load_dataset()


@pytest.fixture(scope="session")
def summaries(ds):
    return {a.alert_id: investigate(ds, a) for a in ds.alerts}


@pytest.fixture(scope="session")
def gold():
    # Tests may read the answers; the investigator package may not (D8).
    return json.loads((ROOT / "gold" / "gold.json").read_text(encoding="utf-8"))["alerts"]
