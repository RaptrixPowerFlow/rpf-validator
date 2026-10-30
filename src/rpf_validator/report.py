"""Validation, summary, and comparison reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Finding:
    message: str
    code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        if self.code is None:
            return {"message": self.message}
        return {"code": self.code, "message": self.message}


@dataclass
class ValidationReport:
    path: str
    errors: list[Finding] = field(default_factory=list)
    warnings: list[Finding] = field(default_factory=list)
    solved: str | None = None

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "ok": self.ok,
            "errors": [item.to_dict() for item in self.errors],
            "warnings": [item.to_dict() for item in self.warnings],
            "solved": self.solved,
        }

    def to_text(self) -> str:
        status = "PASS" if self.ok else "FAIL"
        lines = [f"{status} {self.path}"]
        if self.solved:
            lines.append(self.solved)
        for item in self.errors:
            lines.append(f"  {item.code}  {item.message}")
        for item in self.warnings:
            lines.append(f"  warning  {item.message}")
        lines.append(f"{len(self.errors)} error(s), {len(self.warnings)} warning(s)")
        return "\n".join(lines)


@dataclass
class CaseSummary:
    path: str
    version: str | None
    case_mode: str | None
    solved_state_presence: str | None
    validation_mode: str | None
    fingerprint: str | None
    tables: list[tuple[str, int]]
    feature_flags: dict[str, str]
    summary: str
    solved: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "version": self.version,
            "case_mode": self.case_mode,
            "solved_state_presence": self.solved_state_presence,
            "validation_mode": self.validation_mode,
            "fingerprint": self.fingerprint,
            "tables": [{"name": name, "rows": rows} for name, rows in self.tables],
            "feature_flags": self.feature_flags,
            "summary": self.summary,
            "solved": self.solved,
        }

    def to_text(self) -> str:
        lines = [self.summary]
        if self.solved:
            lines.append(self.solved)
        lines.append("")
        lines.append(f"version: {self.version or ''}")
        lines.append(f"case_mode: {self.case_mode or ''}")
        lines.append(f"solved_state_presence: {self.solved_state_presence or ''}")
        lines.append(f"validation_mode: {self.validation_mode or ''}")
        lines.append(f"fingerprint: {self.fingerprint or ''}")
        lines.append("tables:")
        for name, rows in self.tables:
            lines.append(f"  {name}  {rows}")
        if self.feature_flags:
            lines.append("features:")
            for key, value in self.feature_flags.items():
                lines.append(f"  {key}={value}")
        return "\n".join(lines)


@dataclass
class ComparisonReport:
    path: str
    golden: str
    mismatches: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.mismatches

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "golden": self.golden,
            "ok": self.ok,
            "mismatches": list(self.mismatches),
        }

    def to_text(self) -> str:
        status = "MATCH" if self.ok else "DIFFER"
        lines = [f"{status} {self.path} against {self.golden}"]
        for item in self.mismatches:
            lines.append(f"  {item}")
        return "\n".join(lines)
