import json
import os
import subprocess
import sys
from pathlib import Path

import pyarrow as pa

from rpf_validator import health_report, validate
from tests.fixture_writer import _bus, _metadata_row, _network, write_case
from tests.helpers import replace_table_field, rewrite

ROOT = Path(__file__).resolve().parents[1]
GOLDENS = ROOT / "goldens"
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}


def test_planning_golden_is_one_island_without_solved_tables():
    report = health_report(GOLDENS / "planning_tiny.rpf")
    assert report.conforms
    assert report.topology["islands"] == 1
    assert report.topology["largest"] == 4
    assert report.topology["isolated_buses"] == 0
    assert report.warnings == []
    text = report.to_text()
    assert "1 island (4 buses)" in text
    assert "no isolated buses" in text
    assert "solved tables: absent" in text
    assert "4 buses" in text
    assert "Warnings" in text
    assert "none" in text


def test_solved_golden_skips_balance_and_counts_voltage_bands():
    report = health_report(GOLDENS / "solved_tiny.rpf")
    assert report.conforms
    assert "60 MW" in report.solved["summary"]
    assert report.solved["balance"].startswith("stored-solution balance: skipped")
    assert report.solved["voltage_bands"] == {
        "below_0_90": 0,
        "below_0_95": 0,
        "above_1_05": 0,
        "above_1_10": 0,
    }


def test_contingency_golden_reports_one_contingency():
    report = health_report(GOLDENS / "contingency_tiny.rpf")
    assert report.inventory["counts"]["contingencies"]["present"] is True
    assert report.inventory["counts"]["contingencies"]["count"] == 1
    assert report.warnings == []


def test_opening_a_branch_makes_two_islands(tmp_path):
    def open_middle(schema, batch):
        table_index = schema.get_field_index("branches")
        struct = batch.column(table_index)
        field_index = struct.type.get_field_index("status")
        values = struct.field(field_index).to_pylist()
        values[1] = False
        return replace_table_field(schema, batch, "branches", "status", pa.array(values, type=pa.bool_()))

    dest = tmp_path / "split.rpf"
    rewrite(GOLDENS / "planning_tiny.rpf", dest, open_middle)
    report = health_report(dest)
    assert report.topology["islands"] == 2
    assert report.topology["largest"] == 2


def test_duplicate_bus_and_self_loop_warn_without_failing_validation(tmp_path):
    tables = _network()
    tables["buses"].append(_bus(1, "North copy", "PQ"))
    tables["metadata"] = [
        _metadata_row(
            case_mode="flat_start_planning",
            presence="not_computed",
            validation_mode="topology_only",
            fingerprint="1" * 64,
            study_name="duplicate",
            planning=True,
        )
    ]
    duplicate = tmp_path / "duplicate.rpf"
    write_case(
        duplicate,
        tables,
        case_mode="flat_start_planning",
        solved_state_presence="not_computed",
        validation_mode="topology_only",
        fingerprint="1" * 64,
    )
    health = health_report(duplicate)
    validation = validate(duplicate)
    assert validation.ok
    assert any("duplicate bus_id 1" in warning for warning in health.warnings)

    def loop(schema, batch):
        table_index = schema.get_field_index("branches")
        struct = batch.column(table_index)
        from_values = struct.field(struct.type.get_field_index("from_bus_id")).to_pylist()
        to_values = struct.field(struct.type.get_field_index("to_bus_id")).to_pylist()
        to_values[0] = from_values[0]
        return replace_table_field(schema, batch, "branches", "to_bus_id", pa.array(to_values, type=pa.int32()))

    looped = tmp_path / "loop.rpf"
    rewrite(GOLDENS / "planning_tiny.rpf", looped, loop)
    assert validate(looped).ok
    assert any("self-loop" in warning for warning in health_report(looped).warnings)


def test_health_cli_json_reports_island_count():
    code = (
        "from rpf_validator.cli import health_main; "
        f"health_main(['--json', {str(GOLDENS / 'planning_tiny.rpf')!r}])"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=ENV,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["topology"]["islands"] == 1
    assert payload["conforms"] is True
