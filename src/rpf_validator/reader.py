"""Read an .rpf Arrow IPC file into logical tables."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pyarrow as pa

from rpf_validator.report import Finding

ROW_COUNT = "INVALID_ROW_COUNT"


class RpfReadError(Exception):
    """The path is not a readable Arrow IPC file with at least one root batch."""


@dataclass
class LogicalTable:
    name: str
    is_struct: bool
    physical_rows: int
    logical_rows: int | None
    array: pa.StructArray | None


@dataclass
class LoadedFile:
    path: str
    metadata: dict[str, str]
    root_names: list[str]
    tables: dict[str, LogicalTable]
    findings: list[Finding] = field(default_factory=list)

    def has_table(self, name: str) -> bool:
        return name in self.root_names


def _decode_metadata(schema: pa.Schema) -> dict[str, str]:
    raw = schema.metadata or {}
    decoded: dict[str, str] = {}
    for key, value in raw.items():
        key_text = key.decode("utf-8", "replace") if isinstance(key, (bytes, bytearray)) else str(key)
        if isinstance(value, (bytes, bytearray)):
            decoded[key_text] = value.decode("utf-8", "replace")
        else:
            decoded[key_text] = str(value)
    return decoded


def _parse_row_count(name: str, physical_rows: int, metadata: dict[str, str]) -> tuple[int | None, Finding | None]:
    """Logical length is ``rpf.rows.<table>`` when that key parses.

    A missing key falls back to the struct length and is a warning.
    A present key that is not an integer, or that exceeds the struct length,
    is ``INVALID_ROW_COUNT`` and the table is left unusable.
    """

    key = f"rpf.rows.{name}"
    if key not in metadata:
        return physical_rows, Finding(
            message=f"{key} is absent; using struct length {physical_rows}",
        )
    raw = metadata[key].strip()
    if raw == "" or not raw.isdecimal():
        return None, Finding(
            code=ROW_COUNT,
            message=f"{key}={metadata[key]!r} is not an integer",
        )
    value = int(raw)
    if value > physical_rows:
        return None, Finding(
            code=ROW_COUNT,
            message=(
                f"{key}={value} exceeds struct length {physical_rows}"
            ),
        )
    return value, None


def load(path: str | Path) -> LoadedFile:
    path = Path(path)
    try:
        reader = pa.ipc.open_file(path)
    except (OSError, pa.ArrowInvalid, pa.ArrowException) as exc:
        raise RpfReadError(f"cannot read Arrow IPC file {path}: {exc}") from exc

    if reader.num_record_batches == 0:
        raise RpfReadError(f"{path} contains zero root record batches")

    schema = reader.schema
    metadata = _decode_metadata(schema)
    root_names: list[str] = []
    columns: dict[str, list[pa.Array]] = {}
    for batch_index in range(reader.num_record_batches):
        batch = reader.get_batch(batch_index)
        seen: set[str] = set()
        for index, name in enumerate(schema.names):
            if name in seen:
                continue
            seen.add(name)
            if name not in columns:
                root_names.append(name)
                columns[name] = []
            columns[name].append(batch.column(index))

    tables: dict[str, LogicalTable] = {}
    findings: list[Finding] = []
    for name in root_names:
        pieces = columns[name]
        try:
            combined = pieces[0] if len(pieces) == 1 else pa.concat_arrays(pieces)
        except pa.ArrowException as exc:
            raise RpfReadError(f"cannot combine root column {name!r} in {path}: {exc}") from exc
        if isinstance(combined, pa.ChunkedArray):
            combined = combined.combine_chunks()
        physical = len(combined)
        is_struct = pa.types.is_struct(combined.type)
        if not is_struct:
            tables[name] = LogicalTable(name, False, physical, None, None)
            continue
        logical, finding = _parse_row_count(name, physical, metadata)
        if finding is not None:
            findings.append(finding)
        array = combined.slice(0, logical) if logical is not None else None
        tables[name] = LogicalTable(name, True, physical, logical, array)

    return LoadedFile(str(path), metadata, root_names, tables, findings)
