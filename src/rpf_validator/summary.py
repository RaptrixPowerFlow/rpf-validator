"""Content summary for an .rpf file."""

from __future__ import annotations

from rpf_validator.checks import _version_stamp
from rpf_validator.reader import LoadedFile
from rpf_validator.report import CaseSummary
from rpf_validator.solved import describe_solved


def _phrase(count: int, singular: str, plural: str) -> str:
    word = singular if count == 1 else plural
    return f"{count} {word}"


def one_line(loaded: LoadedFile, rows: dict[str, int]) -> str:
    mode = loaded.metadata.get("rpf.case_mode") or "unknown case mode"
    parts = [mode]
    for name, singular, plural in (
        ("buses", "bus", "buses"),
        ("branches", "branch", "branches"),
        ("generators", "generator", "generators"),
    ):
        if name in rows:
            parts.append(_phrase(rows[name], singular, plural))
    contingencies = rows.get("contingencies", 0)
    if contingencies:
        parts.append(_phrase(contingencies, "contingency", "contingencies"))
    fingerprint = loaded.metadata.get("rpf.case_fingerprint")
    if fingerprint:
        short = fingerprint if len(fingerprint) <= 8 else f"{fingerprint[:8]}…"
        parts.append(f"fingerprint {short}")
    return ", ".join(parts)


def summarize_loaded(loaded: LoadedFile) -> CaseSummary:
    rows: dict[str, int] = {}
    table_rows: list[tuple[str, int]] = []
    for name in loaded.root_names:
        table = loaded.tables[name]
        count = table.logical_rows if table.logical_rows is not None else table.physical_rows
        rows[name] = count
        table_rows.append((name, count))
    flags = {
        key: value
        for key, value in sorted(loaded.metadata.items())
        if ".features." in key
    }
    return CaseSummary(
        path=loaded.path,
        version=_version_stamp(loaded.metadata),
        case_mode=loaded.metadata.get("rpf.case_mode"),
        solved_state_presence=loaded.metadata.get("rpf.solved_state_presence"),
        validation_mode=loaded.metadata.get("rpf.validation_mode"),
        fingerprint=loaded.metadata.get("rpf.case_fingerprint"),
        tables=table_rows,
        feature_flags=flags,
        summary=one_line(loaded, rows),
        solved=describe_solved(loaded),
    )
