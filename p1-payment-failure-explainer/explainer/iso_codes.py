"""Official ISO 20022 reason codes, for codes our table doesn't cover (D17).

The official JSON download is a JSON Schema: each code set has an "enum" of codes and a "description"
that lists each code as *`CODE`-definition. It carries definitions but no names (names are only in
the XLSX). pacs.002 reasons come from ExternalStatusReason1Code, pacs.004 from ExternalReturnReason1Code.
"""

import json
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from explainer import config

STATUS_SET = "ExternalStatusReason1Code"   # pacs.002 status reasons
RETURN_SET = "ExternalReturnReason1Code"   # pacs.004 return reasons
SET_FOR_MESSAGE = {"PACS_002": STATUS_SET, "PACS_004": RETURN_SET}
# Required by the iso20022.org terms of use for any copy (fixture, prompt passage, citation).
SOURCE_NOTE = ("ISO 20022 External Code Sets ({release}). Not the official site; "
               "for the latest version see https://www.iso20022.org/")
SOURCE_URL = "https://www.iso20022.org/"

_ENTRY = re.compile(r"\*`([A-Z0-9]{4})`-(.*?)(?=\s*\*`[A-Z0-9]{4}`-|\Z)", re.S)


@dataclass(frozen=True)
class IsoCode:
    code: str
    code_set: str
    definition: str
    release: str

    @property
    def passage_id(self) -> str:
        return f"ISO-{self.code}"


def load_iso_codes(path: Path) -> tuple[str, dict[str, dict[str, str]]]:
    """Return (release, {code set: {code: definition}}). Fails loudly if a listed code has no definition."""
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Download the JSON external code sets from https://www.iso20022.org/ by hand "
            f"(the site blocks scripts) and save it there; it is gitignored.")
    data = json.loads(path.read_text(encoding="utf-8"))
    release = data.get("$comment_release", config.ISO_CODE_SETS_RELEASE)
    sets = {}
    for name in (STATUS_SET, RETURN_SET):
        block = data["definitions"][name]
        definitions = {code: " ".join(text.split()) for code, text in _ENTRY.findall(block["description"])}
        missing = [c for c in block["enum"] if c not in definitions]
        if missing:
            raise ValueError(f"{name}: codes without a definition: {missing}")
        sets[name] = {c: definitions[c] for c in block["enum"]}
    return release, sets


@cache
def _codes(path: Path) -> tuple[str, dict[str, dict[str, str]]]:
    return load_iso_codes(path)


def lookup_iso(code: str | None, message_type: str, path: Path | None = None) -> IsoCode | None:
    """The official definition of a reason code for this message type, or None if it isn't an ISO code."""
    code_set = SET_FOR_MESSAGE.get(str(message_type))
    if not code or not code_set:
        return None
    release, sets = _codes(path or config.ISO_CODE_SETS_FILE)
    definition = sets[code_set].get(code.strip().upper())
    return IsoCode(code.strip().upper(), code_set, definition, release) if definition else None
