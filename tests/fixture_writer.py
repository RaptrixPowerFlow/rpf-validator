"""Test-only writer for tiny synthetic .rpf files. Not a public API."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa

from rpf_validator.arrowutil import to_pa_type
from rpf_validator.contract import contract_for_stamp, load_contract

_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _dummy(spec: dict[str, Any]) -> Any:
    kind = spec["kind"]
    if kind == "bool":
        return False
    if kind in {"int8", "int16", "int32", "int64", "uint8", "uint16", "uint32", "uint64"}:
        return 0
    if kind in {"float16", "float32", "float64"}:
        return 0.0
    if kind in {"utf8", "large_utf8", "dictionary"}:
        return ""
    if kind == "timestamp":
        return _EPOCH
    if kind in {"list", "large_list"}:
        return []
    if kind == "map":
        return {}
    if kind == "struct":
        return {
            field["name"]: None if field["nullable"] else _dummy(field["type"])
            for field in spec["fields"]
        }
    raise TypeError(f"cannot dummy {kind}")


def _column_values(field: dict[str, Any], rows: list[dict[str, Any]], pad: int) -> list[Any]:
    values: list[Any] = []
    for index in range(pad):
        supplied = index < len(rows) and field["name"] in rows[index]
        if supplied:
            value = rows[index][field["name"]]
            if value is None and not field["nullable"]:
                value = _dummy(field["type"])
            values.append(value)
        elif field["nullable"]:
            values.append(None)
        else:
            values.append(_dummy(field["type"]))
    return values


def _table_array(contract: dict[str, Any], name: str, rows: list[dict[str, Any]], pad: int) -> pa.StructArray:
    fields = contract["tables"][name][0]["fields"]
    arrays = []
    pa_fields = []
    for field in fields:
        values = _column_values(field, rows, pad)
        arrow_type = to_pa_type(field["type"])
        array = pa.array(values, type=arrow_type)
        if array.type != arrow_type:
            array = array.cast(arrow_type)
        arrays.append(array)
        pa_fields.append(pa.field(field["name"], arrow_type, nullable=field["nullable"]))
    return pa.StructArray.from_arrays(arrays, fields=pa_fields)


def write_case(
    path: str | Path,
    tables: dict[str, list[dict[str, Any]]],
    *,
    case_mode: str,
    solved_state_presence: str,
    validation_mode: str,
    fingerprint: str,
    extra_metadata: dict[str, str] | None = None,
    contract: dict[str, Any] | None = None,
    version: str = "v0.14.5",
) -> dict[str, int]:
    contract = contract if contract is not None else contract_for_stamp(version)
    if contract is None:
        contract = load_contract()
    names = list(contract["required_tables"])
    for name in tables:
        if name not in names:
            names.append(name)
    counts = {name: len(tables.get(name, [])) for name in names}
    pad = max(counts.values()) if counts else 0
    metadata: dict[str, str] = {
        "raptrix.version": version,
        "rpf_version": version,
        "rpf.case_mode": case_mode,
        "rpf.solved_state_presence": solved_state_presence,
        "rpf.validation_mode": validation_mode,
        "rpf.case_fingerprint": fingerprint,
        "raptrix.features.dc_converters": "true",
    }
    for name, count in counts.items():
        metadata[f"rpf.rows.{name}"] = str(count)
    if extra_metadata:
        metadata.update(extra_metadata)

    arrays = []
    fields = []
    for name in names:
        array = _table_array(contract, name, tables.get(name, []), pad)
        arrays.append(array)
        fields.append(pa.field(name, array.type, nullable=True))
    schema = pa.schema(fields, metadata={key: value.encode("utf-8") for key, value in metadata.items()})
    batch = pa.record_batch(arrays, schema=schema)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with pa.OSFile(str(path), "wb") as handle:
        writer = pa.ipc.new_file(handle, schema)
        writer.write_batch(batch)
        writer.close()
    return counts


def _bus(bus_id: int, name: str, bus_type: str) -> dict[str, Any]:
    return {
        "bus_id": bus_id,
        "name": name,
        "type": bus_type,
        "p_sched": 0.0,
        "q_sched": 0.0,
        "v_mag_set": 1.0,
        "v_ang_set": 0.0,
        "q_min": -1.0,
        "q_max": 1.0,
        "g_shunt": 0.0,
        "b_shunt": 0.0,
        "area": 1,
        "zone": 1,
        "v_min": 0.9,
        "v_max": 1.1,
        "p_min_agg": 0.0,
        "p_max_agg": 1.0,
        "nominal_kv": 138.0,
        "bus_uuid": f"bus-{bus_id}",
        "qd_load_pu": 0.0,
        "qg_sched_pu": 0.0,
    }


def _branch(branch_id: int, from_bus: int, to_bus: int) -> dict[str, Any]:
    return {
        "branch_id": branch_id,
        "from_bus_id": from_bus,
        "to_bus_id": to_bus,
        "ckt": "1",
        "r": 0.01,
        "x": 0.1,
        "b_shunt": 0.0,
        "tap": 1.0,
        "phase": 0.0,
        "rate_a": 100.0,
        "rate_b": 100.0,
        "rate_c": 100.0,
        "status": True,
        "from_nominal_kv": 138.0,
        "to_nominal_kv": 138.0,
    }


def _generator(generator_id: int, bus_id: int, name: str) -> dict[str, Any]:
    return {
        "generator_id": generator_id,
        "bus_id": bus_id,
        "name": name,
        "unit_type": "sync",
        "hierarchy_level": "unit",
        "status": True,
        "is_ibr": False,
        "p_sched_mw": 50.0,
        "q_sched_mvar": 0.0,
        "p_min_mw": 0.0,
        "p_max_mw": 100.0,
        "q_min_mvar": -50.0,
        "q_max_mvar": 50.0,
        "mbase_mva": 100.0,
    }


def _load(bus_id: int, load_id: str) -> dict[str, Any]:
    return {
        "bus_id": bus_id,
        "id": load_id,
        "status": True,
        "p_pu": 0.2,
        "q_pu": 0.05,
    }


def _metadata_row(
    *,
    case_mode: str,
    presence: str,
    validation_mode: str,
    fingerprint: str,
    study_name: str,
    planning: bool,
) -> dict[str, Any]:
    return {
        "base_mva": 100.0,
        "frequency_hz": 60.0,
        "study_name": study_name,
        "timestamp_utc": _EPOCH,
        "raptrix_version": "v0.14.5",
        "is_planning_case": planning,
        "source_case_id": study_name,
        "snapshot_timestamp_utc": _EPOCH,
        "case_fingerprint": fingerprint,
        "validation_mode": validation_mode,
        "case_mode": case_mode,
        "solved_state_presence": presence,
        "modern_grid_profile": False,
        "has_ibr": False,
        "has_smart_valve": False,
        "has_multi_terminal_dc": False,
    }


def _network() -> dict[str, list[dict[str, Any]]]:
    return {
        "buses": [
            _bus(1, "North", "Slack"),
            _bus(2, "East", "PQ"),
            _bus(3, "South", "PQ"),
            _bus(4, "West", "PV"),
        ],
        "branches": [
            _branch(1, 1, 2),
            _branch(2, 2, 3),
            _branch(3, 3, 4),
        ],
        "generators": [
            _generator(1, 1, "G1"),
            _generator(2, 4, "G2"),
        ],
        "loads": [
            _load(2, "L1"),
            _load(3, "L2"),
        ],
        "dynamics_models": [
            {
                "bus_id": 1,
                "gen_id": "1",
                "model_type": "GENCLS",
                "params": {"p1": 5.0, "p2": 0.0},
            }
        ],
    }


def _contingency() -> dict[str, Any]:
    return {
        "contingency_id": "N-1-1",
        "elements": [
            {
                "element_type": "branch_outage",
                "branch_id": 2,
                "bus_id": None,
                "gen_id": None,
                "load_id": None,
                "amount_mw": None,
                "status_change": True,
                "equipment_kind": None,
                "equipment_id": None,
            }
        ],
    }


def build_screening_case(
    path: str | Path,
    fingerprint: str,
    profiles: list[dict[str, Any]],
    *,
    version: str = "v0.14.6",
) -> dict[str, int]:
    """Planning case plus computational_load_profiles rows."""

    tables = _network()
    tables["metadata"] = [
        _metadata_row(
            case_mode="flat_start_planning",
            presence="not_computed",
            validation_mode="topology_only",
            fingerprint=fingerprint,
            study_name="screening_tiny",
            planning=True,
        )
    ]
    tables["computational_load_profiles"] = profiles
    return write_case(
        path,
        tables,
        case_mode="flat_start_planning",
        solved_state_presence="not_computed",
        validation_mode="topology_only",
        fingerprint=fingerprint,
        version=version,
    )


def build_planning(path: str | Path, fingerprint: str) -> dict[str, int]:
    tables = _network()
    tables["metadata"] = [
        _metadata_row(
            case_mode="flat_start_planning",
            presence="not_computed",
            validation_mode="topology_only",
            fingerprint=fingerprint,
            study_name="planning_tiny",
            planning=True,
        )
    ]
    return write_case(
        path,
        tables,
        case_mode="flat_start_planning",
        solved_state_presence="not_computed",
        validation_mode="topology_only",
        fingerprint=fingerprint,
    )


def build_contingency(path: str | Path, fingerprint: str) -> dict[str, int]:
    tables = _network()
    tables["metadata"] = [
        _metadata_row(
            case_mode="flat_start_planning",
            presence="not_computed",
            validation_mode="topology_only",
            fingerprint=fingerprint,
            study_name="contingency_tiny",
            planning=True,
        )
    ]
    tables["contingencies"] = [_contingency()]
    return write_case(
        path,
        tables,
        case_mode="flat_start_planning",
        solved_state_presence="not_computed",
        validation_mode="topology_only",
        fingerprint=fingerprint,
    )


def build_solved(path: str | Path, fingerprint: str) -> dict[str, int]:
    tables = _network()
    tables["metadata"] = [
        _metadata_row(
            case_mode="solved_snapshot",
            presence="actual_solved",
            validation_mode="solved_ready",
            fingerprint=fingerprint,
            study_name="solved_tiny",
            planning=False,
        )
    ]
    tables["buses_solved"] = [
        {"bus_id": bus_id, "v_mag_pu": 1.0, "v_ang_deg": 0.0}
        for bus_id in (1, 2, 3, 4)
    ]
    tables["generators_solved"] = [
        {"bus_id": 1, "id": "1", "p_mw": 40.0, "q_mvar": 5.0, "status": True},
        {"bus_id": 4, "id": "2", "p_mw": 20.0, "q_mvar": 1.0, "status": True},
    ]
    return write_case(
        path,
        tables,
        case_mode="solved_snapshot",
        solved_state_presence="actual_solved",
        validation_mode="solved_ready",
        fingerprint=fingerprint,
        extra_metadata={"rpf.solver.version": "synthetic-0"},
    )
