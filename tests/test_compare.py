from pathlib import Path

from rpf_validator import compare, validate
from tests.helpers import rewrite, swap_bus_name_and_type

ROOT = Path(__file__).resolve().parents[1]
GOLDENS = ROOT / "goldens"


def test_golden_matches_itself():
    path = GOLDENS / "planning_tiny.rpf"
    report = compare(path, path)
    assert report.ok, report.to_text()


def test_column_order_does_not_affect_compare(tmp_path):
    source = GOLDENS / "planning_tiny.rpf"
    swapped = tmp_path / "swapped.rpf"
    rewrite(source, swapped, swap_bus_name_and_type)
    schema_report = validate(swapped)
    assert any(item.code == "COLUMN_SCHEMA" for item in schema_report.errors)
    report = compare(swapped, source)
    assert report.ok, report.to_text()


def test_row_count_mismatch(tmp_path):
    from tests.helpers import inflate_bus_rows

    dest = tmp_path / "rows.rpf"
    rewrite(GOLDENS / "planning_tiny.rpf", dest, inflate_bus_rows)
    report = compare(dest, GOLDENS / "planning_tiny.rpf")
    assert not report.ok
    assert any("buses" in item and "rows" in item for item in report.mismatches)
