"""Opt-in inventory and topology report. Not a conformance check and not a solve."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rpf_validator.arrowutil import column_python, struct_field
from rpf_validator.checks import validate_loaded
from rpf_validator.contract import load_contract
from rpf_validator.reader import LoadedFile, LogicalTable, load
from rpf_validator.solved import describe_solved

_SOLVED_TABLES = ("buses_solved", "generators_solved", "switched_shunts_solved")
_BALANCE = "stored-solution balance: skipped, no branch flow columns in v0.14.5"


@dataclass
class HealthReport:
    path: str
    conforms: bool
    version: str | None
    text: str
    inventory: dict[str, Any]
    topology: dict[str, Any]
    solved: dict[str, Any]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "conforms": self.conforms,
            "version": self.version,
            "inventory": self.inventory,
            "topology": self.topology,
            "solved": self.solved,
            "warnings": list(self.warnings),
        }

    def to_text(self) -> str:
        return self.text


def health(path: str | Path) -> HealthReport:
    """Build the health report. Raises RpfReadError when the file cannot be read."""

    loaded = load(path)
    validation = validate_loaded(loaded)
    return _from_loaded(loaded, validation.ok)


def _table(loaded: LoadedFile, name: str) -> LogicalTable | None:
    table = loaded.tables.get(name)
    if table is None or not table.is_struct or table.array is None or table.logical_rows is None:
        return None
    return table


def _rows(table: LogicalTable | None) -> int:
    if table is None or table.logical_rows is None:
        return 0
    return table.logical_rows


def _values(table: LogicalTable | None, column: str) -> list[Any] | None:
    if table is None or table.array is None:
        return None
    array = struct_field(table.array, column)
    if array is None:
        return None
    return column_python(array)


def _in_service(table: LogicalTable | None) -> list[bool]:
    """True or non-zero status is in service. A missing column treats every row as in service.

    A null status does not connect and does not count as in service.
    """

    count = _rows(table)
    if count == 0:
        return []
    status = _values(table, "status")
    if status is None:
        return [True] * count
    flags: list[bool] = []
    for value in status:
        if value is None:
            flags.append(False)
        elif isinstance(value, bool):
            flags.append(value)
        elif isinstance(value, (int, float)):
            flags.append(value != 0)
        else:
            flags.append(bool(value))
    return flags


def _ids(values: list[Any] | None) -> list[int | None]:
    if values is None:
        return []
    parsed: list[int | None] = []
    for value in values:
        if value is None:
            parsed.append(None)
        else:
            parsed.append(int(value))
    return parsed


def _find(parent: dict[int, int], node: int) -> int:
    while parent[node] != node:
        parent[node] = parent[parent[node]]
        node = parent[node]
    return node


def _islands(bus_ids: list[int], edges: list[tuple[int, int]]) -> list[list[int]]:
    unique: list[int] = []
    seen: set[int] = set()
    for bus_id in bus_ids:
        if bus_id in seen:
            continue
        seen.add(bus_id)
        unique.append(bus_id)
    parent = {bus_id: bus_id for bus_id in unique}
    for left, right in edges:
        if left not in parent or right not in parent or left == right:
            continue
        root_left = _find(parent, left)
        root_right = _find(parent, right)
        if root_left != root_right:
            parent[root_right] = root_left
    groups: dict[int, list[int]] = {}
    for bus_id in unique:
        groups.setdefault(_find(parent, bus_id), []).append(bus_id)
    return list(groups.values())


def _pair_edges(
    table: LogicalTable | None,
    left_name: str,
    right_name: str,
    warnings: list[str],
    label: str,
) -> tuple[list[tuple[int, int]], set[int]]:
    edges: list[tuple[int, int]] = []
    incident: set[int] = set()
    if _rows(table) == 0:
        return edges, incident
    left = _ids(_values(table, left_name))
    right = _ids(_values(table, right_name))
    active = _in_service(table)
    resistance = _values(table, "r")
    reactance = _values(table, "x")
    for index, (start, end, serving) in enumerate(zip(left, right, active, strict=False)):
        if not serving or start is None or end is None:
            continue
        incident.add(start)
        incident.add(end)
        if start == end:
            warnings.append(f"{label} row {index} is an in-service self-loop on bus {start}")
        else:
            edges.append((start, end))
        if resistance is not None and reactance is not None and label != "transformers_3w":
            if index < len(resistance) and index < len(reactance):
                r_value = resistance[index]
                x_value = reactance[index]
                if r_value is not None and x_value is not None and float(r_value) == 0.0 and float(x_value) == 0.0:
                    warnings.append(f"{label} row {index} is in service with r and x both 0")
    return edges, incident


def _three_winding(
    table: LogicalTable | None,
    warnings: list[str],
) -> tuple[list[tuple[int, int]], set[int]]:
    """Connect the three winding buses. The fictional star point is not a node."""

    edges: list[tuple[int, int]] = []
    incident: set[int] = set()
    if _rows(table) == 0:
        return edges, incident
    high = _ids(_values(table, "bus_h_id"))
    mid = _ids(_values(table, "bus_m_id"))
    low = _ids(_values(table, "bus_l_id"))
    active = _in_service(table)
    for index, serving in enumerate(active):
        if not serving:
            continue
        ends = [high[index] if index < len(high) else None, mid[index] if index < len(mid) else None, low[index] if index < len(low) else None]
        present = [bus_id for bus_id in ends if bus_id is not None]
        if len(present) != len(set(present)):
            warnings.append(f"transformers_3w row {index} repeats a winding bus")
        for bus_id in present:
            incident.add(bus_id)
        for left, right in zip(present, present[1:], strict=False):
            if left != right:
                edges.append((left, right))
        if len(present) == 3 and present[0] != present[2]:
            edges.append((present[0], present[2]))
    return edges, incident


def _inventory(loaded: LoadedFile, contract: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    lines: list[str] = []
    counts: dict[str, Any] = {}
    equipment = (
        ("buses", "buses", False),
        ("branches", "branches", True),
        ("transformers_2w", "two-winding transformers", True),
        ("transformers_3w", "three-winding transformers", True),
        ("generators", "generators", True),
        ("loads", "loads", True),
        ("fixed_shunts", "fixed shunts", False),
        ("switched_shunts", "switched shunts", False),
        ("areas", "areas", False),
        ("zones", "zones", False),
        ("owners", "owners", False),
    )
    phrases: list[str] = []
    for name, label, with_status in equipment:
        table = _table(loaded, name)
        count = _rows(table)
        record: dict[str, Any] = {"count": count}
        phrase = f"{count} {label}"
        if with_status and count:
            in_service = sum(1 for flag in _in_service(table) if flag)
            record["in_service"] = in_service
            phrase += f" ({in_service} in service)"
        counts[name] = record
        phrases.append(phrase)
    lines.append(", ".join(phrases[:6]))
    lines.append(", ".join(phrases[6:]))

    def presence(name: str) -> str:
        count = _rows(_table(loaded, name))
        counts[name] = {"count": count, "present": count > 0}
        if count > 0:
            return f"present ({count})"
        return "absent"

    diagram = _rows(_table(loaded, "diagram_objects")) + _rows(_table(loaded, "diagram_points"))
    diagram_state = "present" if diagram else "absent"
    gis = _gis_present(_table(loaded, "buses"))
    lines.append(f"contingencies: {presence('contingencies')}")
    lines.append(f"dynamics models: {presence('dynamics_models')}")
    lines.append(f"computational load profiles: {presence('computational_load_profiles')}")
    lines.append(f"RAS: {presence('remedial_action_schemes')}")
    lines.append(f"diagram layout: {diagram_state}")
    lines.append(f"GIS coordinates: {'present' if gis else 'absent'}")
    counts["diagram_layout"] = {"present": diagram_state == "present"}
    counts["gis"] = {"present": gis}

    empty = [
        name
        for name in contract["required_tables"]
        if _rows(_table(loaded, name)) == 0
    ]
    counts["empty_tables"] = empty
    if empty:
        lines.append("empty tables: " + ", ".join(empty))
    return {"lines": lines, "counts": counts}, lines


def _gis_present(buses: LogicalTable | None) -> bool:
    latitudes = _values(buses, "latitude")
    longitudes = _values(buses, "longitude")
    if latitudes is None or longitudes is None:
        return False
    return any(
        left is not None and right is not None
        for left, right in zip(latitudes, longitudes, strict=False)
    )


def _topology(
    loaded: LoadedFile,
    warnings: list[str],
) -> tuple[dict[str, Any], list[str]]:
    buses = _table(loaded, "buses")
    bus_ids = [bus_id for bus_id in _ids(_values(buses, "bus_id")) if bus_id is not None]
    edges: list[tuple[int, int]] = []
    incident: set[int] = set()
    for table_name, label in (("branches", "branches"), ("transformers_2w", "transformers_2w")):
        table_edges, table_incident = _pair_edges(_table(loaded, table_name), "from_bus_id", "to_bus_id", warnings, label)
        edges.extend(table_edges)
        incident.update(table_incident)
    winding_edges, winding_incident = _three_winding(_table(loaded, "transformers_3w"), warnings)
    edges.extend(winding_edges)
    incident.update(winding_incident)

    components = _islands(bus_ids, edges)
    if not components:
        payload = {"islands": 0, "largest": 0, "isolated_buses": 0, "isolated_ids": [], "smaller_islands": []}
        return payload, ["0 islands"]
    largest = max(len(component) for component in components)
    smaller = [sorted(component) for component in components if len(component) < largest]
    isolated = sorted(bus_id for bus_id in dict.fromkeys(bus_ids) if bus_id not in incident)
    payload = {
        "islands": len(components),
        "largest": largest,
        "isolated_buses": len(isolated),
        "isolated_ids": isolated[:10],
        "smaller_islands": [
            {"size": len(component), "buses": component if len(component) <= 5 and len(smaller) <= 10 else []}
            for component in smaller[:10]
        ],
    }
    lines = []
    if len(components) == 1:
        lines.append(f"1 island ({largest} buses)")
    else:
        lines.append(f"{len(components)} islands, largest {largest} buses")
    if not isolated:
        lines.append("no isolated buses")
    else:
        shown = ", ".join(str(bus_id) for bus_id in isolated[:10])
        lines.append(f"{len(isolated)} isolated buses: {shown}")
    if smaller:
        lines.append(f"{len(smaller)} smaller islands")
        if len(smaller) <= 10:
            for component in smaller:
                if len(component) <= 5:
                    lines.append(
                        f"  {len(component)} buses: " + ", ".join(str(bus_id) for bus_id in sorted(component))
                    )
                else:
                    lines.append(f"  {len(component)} buses")
    return payload, lines


def _structural(loaded: LoadedFile, warnings: list[str]) -> None:
    buses = _table(loaded, "buses")
    bus_ids = [bus_id for bus_id in _ids(_values(buses, "bus_id")) if bus_id is not None]
    for bus_id, count in sorted(Counter(bus_ids).items()):
        if count > 1:
            warnings.append(f"duplicate bus_id {bus_id} appears {count} times")
    for index, kv in enumerate(_values(buses, "nominal_kv") or []):
        if kv is None:
            continue
        if float(kv) <= 0.0:
            warnings.append(f"buses row {index} nominal_kv {kv} is not positive")
    _contingencies(loaded, warnings)
    _shunt_steps(loaded, warnings)


def _contingencies(loaded: LoadedFile, warnings: list[str]) -> None:
    table = _table(loaded, "contingencies")
    elements = _values(table, "elements")
    if not elements:
        return
    branches = _table(loaded, "branches")
    branch_ids = {bus_id for bus_id in _ids(_values(branches, "branch_id")) if bus_id is not None}
    generators = _table(loaded, "generators")
    names = _values(generators, "name")
    generator_ids = _values(generators, "generator_id")
    generator_buses = _ids(_values(generators, "bus_id"))
    can_match = generators is not None and (names is not None or generator_ids is not None)
    keys: set[tuple[int | None, str]] = set()
    if can_match:
        width = max(len(names or []), len(generator_ids or []), len(generator_buses))
        for index in range(width):
            bus_id = generator_buses[index] if index < len(generator_buses) else None
            if names is not None and index < len(names) and names[index] not in (None, ""):
                keys.add((bus_id, str(names[index])))
            if generator_ids is not None and index < len(generator_ids) and generator_ids[index] is not None:
                keys.add((bus_id, str(int(generator_ids[index]))))
    for row_index, row in enumerate(elements):
        if not row:
            continue
        for element in row:
            if not isinstance(element, dict):
                continue
            branch_id = element.get("branch_id")
            if branch_id is not None and int(branch_id) not in branch_ids:
                warnings.append(
                    f"contingencies row {row_index} references missing branch_id {branch_id}"
                )
            gen_id = element.get("gen_id")
            if gen_id in (None, ""):
                continue
            if not can_match:
                warnings.append(
                    f"contingencies row {row_index} generator {gen_id} cannot be matched; "
                    "generators name and generator_id are unavailable"
                )
                continue
            bus_id = element.get("bus_id")
            token = str(gen_id)
            if bus_id is None:
                matched = any(key == token for _, key in keys)
            else:
                matched = (int(bus_id), token) in keys
            if not matched:
                warnings.append(
                    f"contingencies row {row_index} references missing generator {gen_id}"
                )


def _shunt_steps(loaded: LoadedFile, warnings: list[str]) -> None:
    table = _table(loaded, "switched_shunts")
    steps = _values(table, "b_steps")
    current = _values(table, "current_step")
    if steps is None and current is None:
        return
    width = max(len(steps or []), len(current or []))
    for index in range(width):
        step_list = steps[index] if steps is not None and index < len(steps) else None
        step_index = current[index] if current is not None and index < len(current) else None
        if isinstance(step_list, list) and len(step_list) == 0:
            warnings.append(f"switched_shunts row {index} has an empty b_steps list")
        if step_index is None:
            continue
        limit = len(step_list) if isinstance(step_list, list) else 0
        if int(step_index) < 1 or int(step_index) > limit:
            warnings.append(
                f"switched_shunts row {index} current_step {step_index} is outside 1..{limit}"
            )


def _solved_section(loaded: LoadedFile) -> tuple[dict[str, Any], list[str]]:
    present = any(_rows(_table(loaded, name)) > 0 for name in _SOLVED_TABLES)
    if not present:
        return {"tables": "absent"}, ["solved tables: absent"]
    lines = []
    summary = describe_solved(loaded)
    payload: dict[str, Any] = {"tables": "present", "balance": _BALANCE}
    if summary:
        lines.append(summary)
        payload["summary"] = summary
    lines.append(_BALANCE)
    buses = _table(loaded, "buses_solved")
    voltages = _values(buses, "v_mag_pu") if _rows(buses) else None
    if voltages:
        numbers = [float(value) for value in voltages if isinstance(value, (int, float)) and not isinstance(value, bool)]
        bands = {
            "below_0_90": sum(1 for value in numbers if value < 0.90),
            "below_0_95": sum(1 for value in numbers if value < 0.95),
            "above_1_05": sum(1 for value in numbers if value > 1.05),
            "above_1_10": sum(1 for value in numbers if value > 1.10),
        }
        payload["voltage_bands"] = bands
        lines.append(
            "voltages below 0.90 pu: {below_0_90}; below 0.95: {below_0_95}; "
            "above 1.05: {above_1_05}; above 1.10: {above_1_10}".format(**bands)
        )
    return payload, lines


def _from_loaded(loaded: LoadedFile, conforms: bool) -> HealthReport:
    contract = load_contract()
    version = loaded.metadata.get("raptrix.version") or loaded.metadata.get("rpf_version")
    warnings: list[str] = []
    inventory, inventory_lines = _inventory(loaded, contract)
    topology, topology_lines = _topology(loaded, warnings)
    _structural(loaded, warnings)
    solved, solved_lines = _solved_section(loaded)
    status = f"conforms to {version}" if conforms and version else ("conforms" if conforms else "does not conform")
    lines = [f"Health report  {loaded.path}", status, "", "Inventory", *[f"  {line}" for line in inventory_lines]]
    lines += ["", "Topology", *[f"  {line}" for line in topology_lines]]
    lines += ["", "Solved", *[f"  {line}" for line in solved_lines]]
    lines += ["", "Warnings"]
    if warnings:
        lines.extend(f"  {warning}" for warning in warnings)
    else:
        lines.append("  none")
    return HealthReport(
        path=loaded.path,
        conforms=conforms,
        version=version,
        text="\n".join(lines),
        inventory=inventory,
        topology=topology,
        solved=solved,
        warnings=warnings,
    )
