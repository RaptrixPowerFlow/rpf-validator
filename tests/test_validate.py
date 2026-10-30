import json
from pathlib import Path

import pyarrow as pa
import pytest

from rpf_validator import validate
from tests.helpers import (
    add_buses_solved,
    bad_branch_bus,
    bad_version,
    blank_table_fingerprint,
    converter_export_mode,
    drop_dc_converters,
    dynamics_named_with_positional,
    dynamics_p0,
    dynamics_wttqa1_current,
    dynamics_wttqa1_old,
    hour_ahead,
    inflate_bus_rows,
    replace_table_field,
    rewrite,
    unprefixed_version,
)

ROOT = Path(__file__).resolve().parents[1]
GOLDENS = ROOT / "goldens"
MANIFEST = json.loads((GOLDENS / "manifest.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["planning_tiny.rpf", "contingency_tiny.rpf", "solved_tiny.rpf"])
def test_goldens_pass(name):
    report = validate(GOLDENS / name)
    assert report.ok, report.to_text()
    assert report.errors == []


def test_manifest_matches_golden_summaries():
    from rpf_validator import summarize

    for name, spec in MANIFEST["files"].items():
        summary = summarize(GOLDENS / name)
        assert summary.case_mode == spec["case_mode"]
        assert summary.fingerprint == spec["fingerprint"]
        counts = dict(summary.tables)
        for table, rows in spec["rows"].items():
            assert counts[table] == rows


def _codes(path: Path) -> set[str]:
    report = validate(path)
    return {item.code for item in report.errors if item.code}


def test_bus_reference_message_includes_circuit(tmp_path):
    dest = tmp_path / "bus.rpf"
    rewrite(GOLDENS / "planning_tiny.rpf", dest, bad_branch_bus)
    report = validate(dest)
    message = next(item.message for item in report.errors if item.code == "BUS_ID_REFERENCE")
    assert "ckt=1" in message


def test_unmatched_dynamics_warning_includes_model_type(tmp_path):
    def orphan(schema, batch):
        table_index = schema.get_field_index("dynamics_models")
        struct = batch.column(table_index)
        field_index = struct.type.get_field_index("bus_id")
        values = struct.field(field_index).to_pylist()
        values[0] = 9999
        return replace_table_field(schema, batch, "dynamics_models", "bus_id", pa.array(values, type=pa.int32()))

    dest = tmp_path / "orphan.rpf"
    rewrite(GOLDENS / "planning_tiny.rpf", dest, orphan)
    report = validate(dest)
    assert any("model_type=GENCLS" in item.message for item in report.warnings)


def test_negative_mutations(tmp_path):
    source = GOLDENS / "planning_tiny.rpf"
    cases = [
        ("version.rpf", bad_version, "VERSION_UNSUPPORTED"),
        ("dropped.rpf", drop_dc_converters, "MISSING_REQUIRED_TABLE"),
        ("solved-on-planning.rpf", add_buses_solved, "CASE_MODE_SOLVED_TABLES"),
        ("p0.rpf", dynamics_p0, "DYNAMICS_VOCABULARY"),
        ("rows.rpf", inflate_bus_rows, "INVALID_ROW_COUNT"),
        ("bus.rpf", bad_branch_bus, "BUS_ID_REFERENCE"),
    ]
    for filename, mutate, code in cases:
        dest = tmp_path / filename
        rewrite(source, dest, mutate)
        assert code in _codes(dest), validate(dest).to_text()


def test_named_params_may_include_positional_tail(tmp_path):
    dest = tmp_path / "named.rpf"
    rewrite(GOLDENS / "planning_tiny.rpf", dest, dynamics_named_with_positional)
    report = validate(dest)
    assert report.ok, report.to_text()
    assert not any(item.code == "DYNAMICS_VOCABULARY" for item in report.errors)


def test_wttqa1_pwr_breakpoints_allow_positional_tail(tmp_path):
    dest = tmp_path / "wttqa1.rpf"
    rewrite(GOLDENS / "planning_tiny.rpf", dest, dynamics_wttqa1_current)
    report = validate(dest)
    assert report.ok, report.to_text()


def test_wttqa1_old_breakpoint_names_fail(tmp_path):
    dest = tmp_path / "wttqa1_old.rpf"
    rewrite(GOLDENS / "planning_tiny.rpf", dest, dynamics_wttqa1_old)
    assert "DYNAMICS_VOCABULARY" in _codes(dest)


def test_hour_ahead_token_is_accepted(tmp_path):
    dest = tmp_path / "hour_ahead.rpf"
    rewrite(GOLDENS / "planning_tiny.rpf", dest, hour_ahead)
    report = validate(dest)
    assert report.ok, report.to_text()


def test_blank_table_cell_uses_file_level_key(tmp_path):
    dest = tmp_path / "blank_fp.rpf"
    rewrite(GOLDENS / "planning_tiny.rpf", dest, blank_table_fingerprint)
    report = validate(dest)
    assert report.ok, report.to_text()
    assert any("metadata.case_fingerprint is blank" in item.message for item in report.warnings)


def test_converter_export_validation_mode_is_accepted(tmp_path):
    dest = tmp_path / "converter_export.rpf"
    rewrite(GOLDENS / "planning_tiny.rpf", dest, converter_export_mode)
    report = validate(dest)
    assert report.ok, report.to_text()


def test_unprefixed_version_stamp_is_accepted(tmp_path):
    dest = tmp_path / "plain.rpf"
    rewrite(GOLDENS / "planning_tiny.rpf", dest, unprefixed_version)
    report = validate(dest)
    assert report.ok, report.to_text()
