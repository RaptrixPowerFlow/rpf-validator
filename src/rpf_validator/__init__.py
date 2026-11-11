"""Validate and inspect Raptrix Power Interchange (.rpf) files."""

from __future__ import annotations

from pathlib import Path

from rpf_validator.compare import compare_loaded
from rpf_validator.checks import validate_loaded
from rpf_validator.health import HealthReport, health
from rpf_validator.reader import RpfReadError, load
from rpf_validator.report import CaseSummary, ComparisonReport, ValidationReport
from rpf_validator.summary import summarize_loaded

__all__ = [
    "CaseSummary",
    "ComparisonReport",
    "HealthReport",
    "RpfReadError",
    "ValidationReport",
    "compare",
    "health_report",
    "summarize",
    "validate",
]


def validate(path: str | Path) -> ValidationReport:
    """Check ``path`` against the vendored snapshot for its version stamp."""

    return validate_loaded(load(path))


def summarize(path: str | Path) -> CaseSummary:
    """Describe the case mode, row counts, fingerprint, and feature flags."""

    return summarize_loaded(load(path))


def health_report(path: str | Path) -> HealthReport:
    """Inventory, islands, and structural notes. Does not change conformance."""

    return health(path)


def compare(path: str | Path, golden: str | Path) -> ComparisonReport:
    """Compare logical table content with a golden file. Column order is ignored."""

    return compare_loaded(load(path), load(golden))
