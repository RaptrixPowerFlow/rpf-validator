import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "goldens" / "planning_tiny.rpf"
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}


def _run(module_call: str, *args: str) -> subprocess.CompletedProcess[str]:
    code = f"from rpf_validator.cli import {module_call}; {module_call}({list(args)!r})"
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=ENV,
        text=True,
        capture_output=True,
        check=False,
    )


def test_validate_and_inspect_exit_zero():
    validated = _run("validate_main", str(GOLDEN))
    assert validated.returncode == 0, validated.stderr
    assert validated.stdout.startswith("PASS")
    inspected = _run("inspect_main", str(GOLDEN))
    assert inspected.returncode == 0, inspected.stderr
    assert "4 buses" in inspected.stdout


def test_validate_json_includes_error_code(tmp_path):
    from tests.helpers import bad_version, rewrite

    dest = tmp_path / "bad.rpf"
    rewrite(GOLDEN, dest, bad_version)
    result = _run("validate_main", "--json", str(dest))
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert any(item["code"] == "VERSION_UNSUPPORTED" for item in payload["errors"])


def test_missing_file_exits_2():
    result = _run("validate_main", str(ROOT / "goldens" / "missing.rpf"))
    assert result.returncode == 2


def test_golden_compare_cli():
    result = _run("validate_main", "--golden", str(GOLDEN), str(GOLDEN))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout
