"""v0.14.5 structural checks."""

from __future__ import annotations

import re
from typing import Any

from rpf_validator.arrowutil import as_param_map, column_python, match_variant, struct_field
from rpf_validator.contract import SUPPORTED_VERSION_STAMPS, contract_for_stamp, load_contract
from rpf_validator.reader import LoadedFile, LogicalTable
from rpf_validator.report import Finding, ValidationReport
from rpf_validator.solved import describe_solved

VERSION_UNSUPPORTED = "VERSION_UNSUPPORTED"
MISSING_REQUIRED_TABLE = "MISSING_REQUIRED_TABLE"
COLUMN_SCHEMA = "COLUMN_SCHEMA"
DIAGRAM_PAIR = "DIAGRAM_PAIR"
METADATA_INVALID = "METADATA_INVALID"
CASE_MODE_SOLVED_TABLES = "CASE_MODE_SOLVED_TABLES"
FACTS_SOLVED_MISSING = "FACTS_SOLVED_MISSING"
INVALID_ROW_COUNT = "INVALID_ROW_COUNT"
DYNAMICS_VOCABULARY = "DYNAMICS_VOCABULARY"
BUS_ID_REFERENCE = "BUS_ID_REFERENCE"

_SOLVED_TABLES = ("buses_solved", "generators_solved", "switched_shunts_solved")
_P_KEY = re.compile(r"^p[0-9]+$")


def _error(report: ValidationReport, code: str, message: str) -> None:
    report.errors.append(Finding(message=message, code=code))


def _warn(report: ValidationReport, message: str) -> None:
    report.warnings.append(Finding(message=message))


def _version_stamp(metadata: dict[str, str]) -> str | None:
    if "rpf_version" in metadata:
        return metadata["rpf_version"].strip()
    if "raptrix.version" in metadata:
        return metadata["raptrix.version"].strip()
    return None


def check_version(loaded: LoadedFile, contract: dict[str, Any], report: ValidationReport) -> None:
    del contract
    supported = set(SUPPORTED_VERSION_STAMPS)
    stamp = _version_stamp(loaded.metadata)
    raptrix = loaded.metadata.get("raptrix.version")
    rpf_version = loaded.metadata.get("rpf_version")
    if stamp is None:
        _error(report, VERSION_UNSUPPORTED, "missing raptrix.version and rpf_version")
        return
    if raptrix is not None and rpf_version is not None and raptrix.strip() != rpf_version.strip():
        _error(
            report,
            VERSION_UNSUPPORTED,
            f"raptrix.version {raptrix!r} does not match rpf_version {rpf_version!r}",
        )
        return
    if stamp not in supported or contract_for_stamp(stamp) is None:
        _error(
            report,
            VERSION_UNSUPPORTED,
            f"version {stamp!r} is not supported; expected {', '.join(SUPPORTED_VERSION_STAMPS)}",
        )


def check_required_tables(loaded: LoadedFile, contract: dict[str, Any], report: ValidationReport) -> None:
    for name in contract["required_tables"]:
        if name not in loaded.root_names:
            _error(report, MISSING_REQUIRED_TABLE, f"missing required table {name!r}")
            continue
        table = loaded.tables[name]
        if not table.is_struct:
            _error(report, MISSING_REQUIRED_TABLE, f"required table {name!r} is not a struct column")


def check_diagram_pair(loaded: LoadedFile, contract: dict[str, Any], report: ValidationReport) -> None:
    left, right = contract["diagram_tables"]
    has_left = loaded.has_table(left)
    has_right = loaded.has_table(right)
    if has_left != has_right:
        missing = right if has_left else left
        _error(
            report,
            DIAGRAM_PAIR,
            f"{left!r} and {right!r} must both be present or both be absent; missing {missing!r}",
        )


def check_columns(loaded: LoadedFile, contract: dict[str, Any], report: ValidationReport) -> None:
    known = contract["tables"]
    for name, table in loaded.tables.items():
        if name not in known:
            continue
        if not table.is_struct or table.array is None:
            if name not in contract["required_tables"] and not table.is_struct:
                _error(report, COLUMN_SCHEMA, f"table {name!r} is not a struct column")
            continue
        array = table.array
        assert array is not None
        detail = None
        for variant in known[name]:
            detail = match_variant(array.type, variant)
            if detail is None:
                break
        else:
            _error(report, COLUMN_SCHEMA, f"table {name!r} does not match a v0.14.5 schema: {detail}")


def _usable(table: LogicalTable | None) -> bool:
    return table is not None and table.is_struct and table.array is not None and table.logical_rows is not None


def _cell(table: LogicalTable, column: str, row: int = 0) -> Any:
    array = struct_field(table.array, column) if table.array is not None else None
    if array is None:
        return None
    values = column_python(array)
    if row >= len(values):
        return None
    return values[row]


def check_metadata_keys(loaded: LoadedFile, contract: dict[str, Any], report: ValidationReport) -> None:
    metadata = loaded.metadata
    fingerprint = metadata.get("rpf.case_fingerprint")
    if fingerprint is None or fingerprint.strip() == "":
        _error(report, METADATA_INVALID, "rpf.case_fingerprint is missing or empty")
    else:
        if re.fullmatch(r"[0-9a-f]{64}", fingerprint.strip()) is None:
            _warn(
                report,
                "rpf.case_fingerprint is not 64 lowercase hex characters",
            )

    validation_mode = metadata.get("rpf.validation_mode")
    if validation_mode not in contract["validation_modes"]:
        _error(
            report,
            METADATA_INVALID,
            f"rpf.validation_mode {validation_mode!r} is not one of {contract['validation_modes']}",
        )

    case_mode = metadata.get("rpf.case_mode")
    if case_mode not in contract["case_modes"]:
        _error(
            report,
            METADATA_INVALID,
            f"rpf.case_mode {case_mode!r} is not one of {contract['case_modes']}",
        )

    presence = metadata.get("rpf.solved_state_presence")
    if presence not in contract["solved_state_presence"]:
        _error(
            report,
            METADATA_INVALID,
            "rpf.solved_state_presence "
            f"{presence!r} is not one of {contract['solved_state_presence']}",
        )

    table = loaded.tables.get("metadata")
    if not _usable(table):
        return
    assert table is not None and table.logical_rows is not None
    if table.logical_rows != 1:
        _error(
            report,
            INVALID_ROW_COUNT,
            f"metadata logical row count is {table.logical_rows}, expected 1",
        )
        return

    for column, key in (
        ("case_mode", "rpf.case_mode"),
        ("case_fingerprint", "rpf.case_fingerprint"),
        ("validation_mode", "rpf.validation_mode"),
    ):
        value = _cell(table, column)
        expected = metadata.get(key) or ""
        blank = value is None or (isinstance(value, str) and value.strip() == "")
        if blank and expected.strip():
            _warn(
                report,
                f"metadata.{column} is blank; file-level {key} is {expected!r}",
            )
            continue
        if blank:
            _error(report, METADATA_INVALID, f"metadata.{column} is missing")
            continue
        if str(value) != expected:
            _error(
                report,
                METADATA_INVALID,
                f"metadata.{column} {value!r} does not match {key} {expected!r}",
            )


def _table_rows(loaded: LoadedFile, name: str) -> int | None:
    table = loaded.tables.get(name)
    if not _usable(table):
        return None
    assert table is not None and table.logical_rows is not None
    return table.logical_rows


def check_case_mode(loaded: LoadedFile, contract: dict[str, Any], report: ValidationReport) -> None:
    mode = loaded.metadata.get("rpf.case_mode")
    presence = loaded.metadata.get("rpf.solved_state_presence")
    if mode not in contract["case_modes"] or presence not in contract["solved_state_presence"]:
        return

    present = {name for name in _SOLVED_TABLES if loaded.has_table(name)}

    if mode == "solved_snapshot":
        if presence != "actual_solved":
            _error(
                report,
                CASE_MODE_SOLVED_TABLES,
                f"solved_snapshot requires solved_state_presence actual_solved, found {presence!r}",
            )
        for name in ("buses_solved", "generators_solved"):
            if name not in present:
                _error(report, CASE_MODE_SOLVED_TABLES, f"solved_snapshot requires table {name!r}")
        shunt = loaded.metadata.get("rpf.solver.solved_shunt_state_presence")
        if shunt == "actual_solved" and "switched_shunts_solved" not in present:
            _error(
                report,
                CASE_MODE_SOLVED_TABLES,
                "solved_snapshot with rpf.solver.solved_shunt_state_presence=actual_solved "
                "requires table 'switched_shunts_solved'",
            )
        return

    # hour_ahead_advisory is a planning mode for solved-table rules.
    if mode == "warm_start_planning" and presence == "seed_only":
        if "buses_solved" not in present:
            _error(
                report,
                CASE_MODE_SOLVED_TABLES,
                "warm_start_planning with seed_only requires table 'buses_solved'",
            )
        for name in ("generators_solved", "switched_shunts_solved"):
            rows = _table_rows(loaded, name)
            if name in present and rows not in (None, 0):
                _error(
                    report,
                    CASE_MODE_SOLVED_TABLES,
                    f"{name} must be absent or zero-row when solved_state_presence is seed_only",
                )
        solver_keys = [key for key in loaded.metadata if key.startswith("rpf.solver.")]
        if solver_keys:
            _error(
                report,
                CASE_MODE_SOLVED_TABLES,
                f"seed_only must not carry solver provenance keys, found {solver_keys[0]!r}",
            )
        return

    if presence == "actual_solved":
        _error(
            report,
            CASE_MODE_SOLVED_TABLES,
            f"case_mode {mode!r} cannot have solved_state_presence actual_solved",
        )
    if presence == "seed_only":
        _error(
            report,
            CASE_MODE_SOLVED_TABLES,
            f"solved_state_presence seed_only is only valid with warm_start_planning, found {mode!r}",
        )
    for name in present:
        _error(
            report,
            CASE_MODE_SOLVED_TABLES,
            f"case_mode {mode!r} must not contain solved table {name!r}",
        )


def check_facts(loaded: LoadedFile, report: ValidationReport) -> None:
    presence = loaded.metadata.get("rpf.facts_solved_state_presence")
    if presence == "actual_solved" and not loaded.has_table("facts_solved"):
        _error(
            report,
            FACTS_SOLVED_MISSING,
            "rpf.facts_solved_state_presence=actual_solved requires table 'facts_solved'",
        )


def _params_named(params: dict[str, Any]) -> bool:
    if "params_named" not in params:
        return False
    try:
        return float(params["params_named"]) == 1.0
    except (TypeError, ValueError):
        return False


def check_dynamics(loaded: LoadedFile, contract: dict[str, Any], report: ValidationReport) -> None:
    table = loaded.tables.get("dynamics_models")
    if not _usable(table):
        return
    assert table is not None and table.array is not None
    params_column = struct_field(table.array, "params")
    model_column = struct_field(table.array, "model_type")
    if params_column is None or model_column is None:
        return
    rules = contract["dynamics"]
    provenance = set(rules["provenance_keys"])
    illegal_wtt = set(rules["wttqa1_illegal_keys"])
    wtt_model = rules["wttqa1_model"]
    models = column_python(model_column)
    params_values = column_python(params_column)
    for row, (model, raw_params) in enumerate(zip(models, params_values, strict=True)):
        try:
            params = as_param_map(raw_params)
        except TypeError as exc:
            _error(report, DYNAMICS_VOCABULARY, f"dynamics_models row {row}: {exc}")
            continue
        if params is None:
            _error(report, DYNAMICS_VOCABULARY, f"dynamics_models row {row}: params is null")
            continue
        named = _params_named(params)
        for key in params:
            if key in provenance:
                continue
            if _P_KEY.fullmatch(key):
                number = int(key[1:])
                if number < 1 or key != f"p{number}":
                    _error(
                        report,
                        DYNAMICS_VOCABULARY,
                        f"dynamics_models row {row}: positional key {key!r} is not legal; use p1..pN",
                    )
        # DYR rows store dictionary names and the positional p1..pN tail together
        # when params_named=1. The old WTTQA1 collision used p1..p4 as the
        # breakpoint names and did not also write pwr1..pwr4.
        if model == wtt_model and named:
            found = sorted(illegal_wtt.intersection(params))
            has_pwr = all(f"pwr{index}" in params for index in range(1, 5))
            if found and not has_pwr:
                _error(
                    report,
                    DYNAMICS_VOCABULARY,
                    f"dynamics_models row {row}: WTTQA1 breakpoints must be pwr1..pwr4, found {found}",
                )


def _row_detail(table: LogicalTable, row: int) -> str:
    """Name or circuit id for one equipment row, when the column is present."""

    if table.array is None:
        return ""
    bits: list[str] = []
    for column in ("ckt", "name"):
        array = struct_field(table.array, column)
        if array is None:
            continue
        values = column_python(array)
        if row < len(values) and values[row] not in (None, ""):
            bits.append(f"{column}={values[row]}")
    return ", ".join(bits)


def _int_ids(table: LogicalTable, column: str) -> list[int | None]:
    assert table.array is not None
    array = struct_field(table.array, column)
    if array is None:
        return []
    values: list[int | None] = []
    for item in column_python(array):
        if item is None:
            values.append(None)
        else:
            values.append(int(item))
    return values


def check_bus_references(loaded: LoadedFile, contract: dict[str, Any], report: ValidationReport) -> None:
    buses = loaded.tables.get("buses")
    if not _usable(buses):
        return
    assert buses is not None
    known = {bus_id for bus_id in _int_ids(buses, "bus_id") if bus_id is not None}
    for table_name, columns in contract["bus_reference_columns"].items():
        table = loaded.tables.get(table_name)
        if not _usable(table):
            continue
        assert table is not None
        for column in columns:
            for row, bus_id in enumerate(_int_ids(table, column)):
                if bus_id is None:
                    continue
                if bus_id not in known:
                    detail = _row_detail(table, row)
                    suffix = f" ({detail})" if detail else ""
                    _error(
                        report,
                        BUS_ID_REFERENCE,
                        f"{table_name}.{column} row {row} references bus_id {bus_id}, "
                        f"which is not in buses{suffix}",
                    )


def check_dynamics_generator_warning(loaded: LoadedFile, report: ValidationReport) -> None:
    dynamics = loaded.tables.get("dynamics_models")
    generators = loaded.tables.get("generators")
    if not _usable(dynamics) or not _usable(generators):
        return
    assert dynamics is not None and generators is not None and dynamics.array is not None
    gen_buses = {bus_id for bus_id in _int_ids(generators, "bus_id") if bus_id is not None}
    bus_column = struct_field(dynamics.array, "bus_id")
    gen_column = struct_field(dynamics.array, "gen_id")
    model_column = struct_field(dynamics.array, "model_type")
    if bus_column is None or gen_column is None:
        return
    models = column_python(model_column) if model_column is not None else []
    for row, (bus_id, gen_id) in enumerate(
        zip(column_python(bus_column), column_python(gen_column), strict=True)
    ):
        if bus_id is None:
            continue
        if int(bus_id) not in gen_buses:
            model = models[row] if row < len(models) and models[row] not in (None, "") else None
            suffix = f", model_type={model}" if model else ""
            _warn(
                report,
                f"dynamics_models row {row}: (bus_id={bus_id}, gen_id={gen_id}) "
                f"has no generators row{suffix}",
            )


def check_feature_warnings(loaded: LoadedFile, contract: dict[str, Any], report: ValidationReport) -> None:
    metadata = loaded.metadata
    if metadata.get("raptrix.features.dc_converters") != "true":
        _warn(report, "raptrix.features.dc_converters is not 'true'")
    if metadata.get("raptrix.features.diagram_layout") == "true":
        for name in contract["diagram_tables"]:
            if not loaded.has_table(name):
                _warn(report, f"raptrix.features.diagram_layout=true but table {name!r} is missing")
    if metadata.get("rpf.solver.solved_shunt_state_presence") == "not_available":
        _warn(report, "rpf.solver.solved_shunt_state_presence=not_available")
    for flag, tables in contract["feature_flag_tables"].items():
        if metadata.get(flag) != "true":
            continue
        missing = [name for name in tables if not loaded.has_table(name)]
        if missing:
            _warn(report, f"{flag}=true but missing table {missing[0]!r}")


def validate_loaded(loaded: LoadedFile, contract: dict[str, Any] | None = None) -> ValidationReport:
    contract = contract if contract is not None else load_contract()
    report = ValidationReport(path=loaded.path)
    for finding in loaded.findings:
        if finding.code:
            report.errors.append(finding)
        else:
            report.warnings.append(finding)
    check_version(loaded, contract, report)
    check_required_tables(loaded, contract, report)
    check_diagram_pair(loaded, contract, report)
    check_columns(loaded, contract, report)
    check_metadata_keys(loaded, contract, report)
    check_case_mode(loaded, contract, report)
    check_facts(loaded, report)
    check_dynamics(loaded, contract, report)
    check_bus_references(loaded, contract, report)
    check_dynamics_generator_warning(loaded, report)
    check_feature_warnings(loaded, contract, report)
    report.solved = describe_solved(loaded)
    return report
