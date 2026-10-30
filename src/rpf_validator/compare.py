"""Structural comparison of two .rpf files after name-based reconstruction."""

from __future__ import annotations

from rpf_validator.arrowutil import column_python
from rpf_validator.reader import LoadedFile, LogicalTable
from rpf_validator.report import ComparisonReport


def _values_by_name(table: LogicalTable) -> dict[str, list[object]]:
    if table.array is None:
        return {}
    values: dict[str, list[object]] = {}
    for index, field in enumerate(table.array.type):
        values[field.name] = column_python(table.array.field(index))
    return values


def compare_loaded(left: LoadedFile, right: LoadedFile) -> ComparisonReport:
    """Compare logical content. Column order inside a table is ignored."""

    report = ComparisonReport(path=left.path, golden=right.path)
    left_mode = left.metadata.get("rpf.case_mode")
    right_mode = right.metadata.get("rpf.case_mode")
    if left_mode != right_mode:
        report.mismatches.append(f"case_mode {left_mode!r} != {right_mode!r}")

    left_fp = left.metadata.get("rpf.case_fingerprint")
    right_fp = right.metadata.get("rpf.case_fingerprint")
    if left_fp != right_fp:
        report.mismatches.append(f"fingerprint {left_fp!r} != {right_fp!r}")

    left_names = set(left.root_names)
    right_names = set(right.root_names)
    if left_names != right_names:
        missing = sorted(right_names - left_names)
        extra = sorted(left_names - right_names)
        report.mismatches.append(
            f"table names differ; missing {missing}, extra {extra}"
        )

    for name in sorted(left_names & right_names):
        left_table = left.tables[name]
        right_table = right.tables[name]
        if left_table.logical_rows != right_table.logical_rows:
            report.mismatches.append(
                f"table {name} rows {left_table.logical_rows} != {right_table.logical_rows}"
            )
            continue
        if not left_table.is_struct or not right_table.is_struct:
            if left_table.is_struct != right_table.is_struct:
                report.mismatches.append(f"table {name} struct layout differs")
            continue
        left_values = _values_by_name(left_table)
        right_values = _values_by_name(right_table)
        left_columns = set(left_values)
        right_columns = set(right_values)
        if left_columns != right_columns:
            report.mismatches.append(
                f"table {name} columns differ; "
                f"missing {sorted(right_columns - left_columns)}, "
                f"extra {sorted(left_columns - right_columns)}"
            )
        for column in sorted(left_columns & right_columns):
            if left_values[column] != right_values[column]:
                report.mismatches.append(f"table {name} column {column} values differ")
    return report
