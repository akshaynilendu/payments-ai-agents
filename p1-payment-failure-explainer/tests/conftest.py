from pathlib import Path

import pytest

from explainer import config

ISO_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "iso20022_external_codes_extract.json"


@pytest.fixture(autouse=True)
def iso_extract(monkeypatch):
    """Tests use the committed ISO extract: the full official file is gitignored, so fresh clones lack it."""
    monkeypatch.setattr(config, "ISO_CODE_SETS_FILE", ISO_FIXTURE)
