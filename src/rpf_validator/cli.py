"""Command-line entry points for rpf-validate and rpf-inspect."""

from __future__ import annotations

import argparse
import json
import sys

from rpf_validator import compare, summarize, validate
from rpf_validator.reader import RpfReadError


def _parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("file", help="Path to an .rpf file")
    parser.add_argument("--json", action="store_true", help="Print JSON")
    return parser


def validate_main(argv: list[str] | None = None) -> None:
    parser = _parser("rpf-validate")
    parser.add_argument("--golden", help="Compare logical content with this golden .rpf file")
    args = parser.parse_args(argv)
    try:
        report = validate(args.file)
    except RpfReadError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(2) from exc

    comparison = None
    if args.golden:
        try:
            comparison = compare(args.file, args.golden)
        except RpfReadError as exc:
            print(exc, file=sys.stderr)
            raise SystemExit(2) from exc

    if args.json:
        payload: dict[str, object] = {"validation": report.to_dict()}
        if comparison is not None:
            payload["comparison"] = comparison.to_dict()
        print(json.dumps(payload if comparison is not None else report.to_dict(), indent=2))
    else:
        print(report.to_text())
        if comparison is not None:
            print(comparison.to_text())

    failed = not report.ok or (comparison is not None and not comparison.ok)
    raise SystemExit(1 if failed else 0)


def inspect_main(argv: list[str] | None = None) -> None:
    parser = _parser("rpf-inspect")
    args = parser.parse_args(argv)
    try:
        summary = summarize(args.file)
    except RpfReadError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(2) from exc
    if args.json:
        print(json.dumps(summary.to_dict(), indent=2))
    else:
        print(summary.to_text())
    raise SystemExit(0)
