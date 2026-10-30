"""Describe a solved power-flow payload when the file carries one."""

from __future__ import annotations

from rpf_validator.arrowutil import column_python, struct_field
from rpf_validator.reader import LoadedFile, LogicalTable


def _usable(table: LogicalTable | None) -> bool:
    return table is not None and table.array is not None and table.logical_rows not in (None, 0)


def _numbers(table: LogicalTable, column: str) -> list[float]:
    assert table.array is not None
    array = struct_field(table.array, column)
    if array is None:
        return []
    values: list[float] = []
    for item in column_python(array):
        if isinstance(item, bool) or item is None:
            continue
        if isinstance(item, (int, float)):
            values.append(float(item))
    return values


def _flags(table: LogicalTable, column: str) -> list[bool] | None:
    assert table.array is not None
    array = struct_field(table.array, column)
    if array is None:
        return None
    return [bool(item) for item in column_python(array) if item is not None]


def _num(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _range(values: list[float], unit: str) -> str | None:
    if not values:
        return None
    low = min(values)
    high = max(values)
    if low == high:
        return f"{_num(low)} {unit}"
    return f"{_num(low)}–{_num(high)} {unit}"


def describe_solved(loaded: LoadedFile) -> str | None:
    """One paragraph when the file carries a solved snapshot. None otherwise."""

    mode = loaded.metadata.get("rpf.case_mode")
    presence = loaded.metadata.get("rpf.solved_state_presence")
    buses = loaded.tables.get("buses_solved")
    generators = loaded.tables.get("generators_solved")
    shunts = loaded.tables.get("switched_shunts_solved")
    solved_rows = any(_usable(table) for table in (buses, generators, shunts))
    if mode != "solved_snapshot" and presence != "actual_solved" and not solved_rows:
        return None

    parts: list[str] = []
    if _usable(buses):
        assert buses is not None and buses.logical_rows is not None
        voltage = _range(_numbers(buses, "v_mag_pu"), "pu")
        angle = _range(_numbers(buses, "v_ang_deg"), "deg")
        text = f"{buses.logical_rows} bus voltages"
        if voltage:
            text += f" {voltage}"
        if angle:
            text += f", angle {angle}"
        parts.append(text)
    if _usable(generators):
        assert generators is not None and generators.logical_rows is not None
        status = _flags(generators, "status")
        p_values = _numbers(generators, "p_mw")
        q_values = _numbers(generators, "q_mvar")
        if status is not None and len(status) == len(p_values):
            in_service = sum(1 for flag in status if flag)
            p_total = sum(value for value, flag in zip(p_values, status, strict=True) if flag)
            q_total = (
                sum(value for value, flag in zip(q_values, status, strict=True) if flag)
                if len(q_values) == len(status)
                else None
            )
            text = f"{in_service} in-service generators"
        else:
            in_service = generators.logical_rows
            p_total = sum(p_values) if p_values else None
            q_total = sum(q_values) if q_values else None
            text = f"{in_service} generators"
        if p_total is not None:
            text += f" totaling {_num(p_total)} MW"
        if q_total is not None:
            text += f" / {_num(q_total)} Mvar"
        parts.append(text)
    if _usable(shunts):
        assert shunts is not None and shunts.logical_rows is not None
        parts.append(f"{shunts.logical_rows} solved shunts")

    solver = loaded.metadata.get("rpf.solver.version")
    solver_mode = loaded.metadata.get("rpf.solver.mode")
    iterations = loaded.metadata.get("rpf.solver.iterations")
    solver_bits = [bit for bit in (solver, solver_mode) if bit]
    solver_text = ""
    if solver_bits or iterations is not None:
        solver_text = " Solver " + ", ".join(solver_bits) if solver_bits else " Solver"
        if iterations is not None:
            solver_text += f", iterations {iterations}"
        solver_text += "."

    if not parts and not solver_text:
        label = presence or mode or "solved"
        return f"Solved power flow ({label})."
    body = "; ".join(parts)
    label = presence or "solved"
    return f"Solved power flow ({label}): {body}.{solver_text}"
