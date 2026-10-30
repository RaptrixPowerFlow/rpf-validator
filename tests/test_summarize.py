import json
from pathlib import Path

from rpf_validator import summarize

ROOT = Path(__file__).resolve().parents[1]
GOLDENS = ROOT / "goldens"
MANIFEST = json.loads((GOLDENS / "manifest.json").read_text(encoding="utf-8"))


def test_planning_summary_line_and_counts():
    summary = summarize(GOLDENS / "planning_tiny.rpf")
    spec = MANIFEST["files"]["planning_tiny.rpf"]
    assert summary.case_mode == "flat_start_planning"
    assert summary.version == "v0.14.5"
    assert summary.fingerprint == spec["fingerprint"]
    assert summary.summary.startswith("flat_start_planning, 4 buses, 3 branches, 2 generators")
    assert "contingency" not in summary.summary
    assert summary.summary.endswith("fingerprint 11111111…")
    counts = dict(summary.tables)
    assert counts["buses"] == spec["rows"]["buses"]
    assert counts["branches"] == 3
    assert counts["generators"] == 2
    assert counts["contingencies"] == 0
    assert summary.feature_flags["raptrix.features.dc_converters"] == "true"


def test_solved_golden_reports_the_solution():
    summary = summarize(GOLDENS / "solved_tiny.rpf")
    assert summary.solved is not None
    assert summary.solved.startswith("Solved power flow (actual_solved):")
    assert "4 bus voltages 1 pu" in summary.solved
    assert "60 MW" in summary.solved
    assert "6 Mvar" in summary.solved
    planning = summarize(GOLDENS / "planning_tiny.rpf")
    assert planning.solved is None


def test_contingency_summary_counts_one_contingency():
    summary = summarize(GOLDENS / "contingency_tiny.rpf")
    assert "1 contingency" in summary.summary
    assert summary.summary.endswith("fingerprint 22222222…")
