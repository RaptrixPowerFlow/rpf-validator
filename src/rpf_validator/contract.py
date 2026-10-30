"""Load the vendored v0.14.5 contract snapshot."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_SNAPSHOT_PATH = Path(__file__).with_name("contract_v0145.json")

# Stamps the vendored snapshot accepts. A later stamp adds a file and a registry entry.
SUPPORTED_VERSION_STAMPS = ("v0.14.5", "0.14.5")


@lru_cache(maxsize=1)
def load_contract() -> dict[str, Any]:
    with _SNAPSHOT_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def contract_for_stamp(stamp: str) -> dict[str, Any] | None:
    """Return the snapshot for a version stamp, or None when the stamp is unknown."""

    if stamp not in SUPPORTED_VERSION_STAMPS:
        return None
    return load_contract()


def known_table_names(contract: dict[str, Any] | None = None) -> set[str]:
    contract = contract if contract is not None else load_contract()
    return set(contract["tables"])
