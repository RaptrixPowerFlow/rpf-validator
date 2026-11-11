"""Load the vendored v0.14.5 and v0.14.6 contract snapshots."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_DIR = Path(__file__).parent

# Stamps the vendored snapshots accept. A later stamp adds a file and a registry entry.
_SNAPSHOT_FILES = {
    "v0.14.6": "contract_v0146.json",
    "0.14.6": "contract_v0146.json",
    "v0.14.5": "contract_v0145.json",
    "0.14.5": "contract_v0145.json",
}

SUPPORTED_VERSION_STAMPS = tuple(_SNAPSHOT_FILES)


@lru_cache(maxsize=4)
def load_contract(stamp: str = "v0.14.5") -> dict[str, Any]:
    """Load one vendored snapshot.

    The default remains the v0.14.5 snapshot so existing callers keep that pin.
    ``validate`` selects the snapshot from the file stamp.
    """

    name = _SNAPSHOT_FILES.get(stamp)
    if name is None:
        raise KeyError(f"no vendored contract snapshot for {stamp!r}")
    with (_DIR / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def contract_for_stamp(stamp: str) -> dict[str, Any] | None:
    """Return the snapshot for a version stamp, or None when the stamp is unknown."""

    if stamp not in _SNAPSHOT_FILES:
        return None
    return load_contract(stamp)


def known_table_names(contract: dict[str, Any] | None = None) -> set[str]:
    contract = contract if contract is not None else load_contract()
    return set(contract["tables"])
