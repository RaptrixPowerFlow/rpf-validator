<!--
rpf-validator — public conformance checks for the Raptrix Power Interchange
Copyright (c) 2026 Raptrix Power
-->

# rpf-validator

Check an `.rpf` file against the locked Raptrix Power Interchange contract, and see what the file contains.

Two questions:

1. Does this file conform to schema **v0.14.5**?
2. What is in it, including a stored solved power flow when the file carries one?

The package is standalone. It reads Apache Arrow IPC with `pyarrow`. It does not run a power flow, and it does not need the commercial Raptrix solver or a Rust toolchain.

![License: MPL-2.0](https://img.shields.io/badge/License-MPL%202.0-brightgreen.svg)
MPL-2.0. Free to use, modify, and distribute.

Part of the open Raptrix suite. The authoritative wire contract stays in [raptrix-cim-rs](https://github.com/RaptrixPowerFlow/raptrix-cim-rs). This repository vendors one snapshot of that contract so a third party can check converter output on its own.

## Install

Python 3.12 or newer. Development and RHEL 10 use **Python 3.12.10**. The only runtime dependency is `pyarrow`.

Windows:

```bat
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\rpf-validate goldens\planning_tiny.rpf
```

macOS and Linux:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/rpf-validate goldens/planning_tiny.rpf
```

`".[dev]"` installs pytest with the package. Omit `.[dev]` if you only want the commands.

Activate the virtual environment and the commands are `rpf-validate` and `rpf-inspect`.

## Validate

```bash
rpf-validate goldens/planning_tiny.rpf
rpf-validate --json path/to/case.rpf
```

```text
PASS goldens/planning_tiny.rpf
0 error(s), 0 warning(s)
```

| Exit | Meaning |
| --- | --- |
| 0 | The file conforms. Warnings may still be printed. |
| 1 | A contract check failed, or a golden comparison did not match. |
| 2 | The path is missing or is not an Arrow IPC file. |

Each error has a stable code such as `VERSION_UNSUPPORTED`, `MISSING_REQUIRED_TABLE`, `CASE_MODE_SOLVED_TABLES`, `DYNAMICS_VOCABULARY`, `BUS_ID_REFERENCE`, or `INVALID_ROW_COUNT`. `--json` prints those codes.

A solved file adds one sentence before the error count. The numbers are the values stored in the file. They are not a judgment that the solution is physically correct.

```text
PASS goldens/solved_tiny.rpf
Solved power flow (actual_solved): 4 bus voltages 1 pu, angle 0 deg; 2 in-service generators totaling 60 MW / 6 Mvar. Solver synthetic-0.
0 error(s), 0 warning(s)
```

## Inspect

```bash
rpf-inspect goldens/solved_tiny.rpf
rpf-inspect --json path/to/case.rpf
```

The first lines name the case and, when present, the stored solution:

```text
solved_snapshot, 4 buses, 3 branches, 2 generators, fingerprint 33333333…
Solved power flow (actual_solved): 4 bus voltages 1 pu, angle 0 deg; 2 in-service generators totaling 60 MW / 6 Mvar. Solver synthetic-0.
```

The rest of the report lists the version stamp, case mode, solved-state presence, fingerprint, one logical row count per table, and feature flags. `rpf-inspect` describes the file even when validation would fail.

## Compare with a golden

```bash
rpf-validate --golden goldens/solved_tiny.rpf path/to/candidate.rpf
```

This runs the contract checks, then compares logical content: case mode, table names, row counts, the stored fingerprint, and column values by name. Column order inside a table does not have to match. A match prints `MATCH` and exits 0. A difference prints `DIFFER` and exits 1.

The fingerprint is compared as a stored string. The validator does not recompute it.

## Library

```python
from rpf_validator import compare, summarize, validate

report = validate("path/to/case.rpf")
if not report.ok:
    for error in report.errors:
        print(error.code, error.message)

summary = summarize("path/to/case.rpf")
print(summary.summary)
print(summary.solved)

match = compare("path/to/candidate.rpf", "goldens/solved_tiny.rpf")
```

`validate` raises `RpfReadError` when the path cannot be read. A readable file that fails the contract returns a report with `ok` false.

## Tests

From the repository root, with the dev install above:

```bash
python -m pytest
```

On Windows, if the virtual environment is not activated:

```bat
.venv\Scripts\python -m pytest
```

The suite is local. It does not use a network, a solver, or any file outside this repository. The checks cover the three synthetic goldens, the command exit codes, and the cases that must fail: a bad version stamp, a missing required table, solved tables on a planning case, an illegal dynamics key, a bad row count, and a broken bus reference.

## What a pass means

A pass means the file matches the vendored v0.14.5 reader contract.

- The version stamp is `v0.14.5` or `0.14.5`.
- The 18 canonical tables are present, plus `dc_converters`, even when a table has zero rows.
- Known tables match a contract column layout or a documented read dialect. Tables are matched by name.
- Case mode, solved-state presence, and the solved tables agree. `hour_ahead_advisory` is accepted and treated as a planning mode.
- Dynamics parameters use `p1`..`pN`. `p0` is rejected. A named `WTTQA1` row must use `pwr1`..`pwr4` for its power breakpoints.
- Non-null bus references on branches, generators, loads, and transformers point at `buses`.

A pass does not mean the network solves, the voltages are credible, or the fingerprint was recomputed.

The full rule list and the snapshot pin are in [docs/CONTRACT.md](docs/CONTRACT.md). The snapshot is `raptrix-cim-rs` commit `0d4d48f`.

## Reference files

The files in `goldens/` are synthetic. They contain no utility model and no customer data.

| File | What it shows |
| --- | --- |
| `goldens/planning_tiny.rpf` | `flat_start_planning`. 4 buses, 3 branches, 2 generators. |
| `goldens/contingency_tiny.rpf` | The same network plus one contingency. |
| `goldens/solved_tiny.rpf` | `solved_snapshot` with bus voltages and generator output. |

`goldens/manifest.json` records the expected case mode, fingerprint, and row counts for each file.

## Related repositories

- [raptrix-cim-rs](https://github.com/RaptrixPowerFlow/raptrix-cim-rs) is the source of truth for the schema contract.
- [raptrix-psse-rs](https://github.com/RaptrixPowerFlow/raptrix-psse-rs) converts PSS/E into `.rpf`.
- [raptrix-pslf-rs](https://github.com/RaptrixPowerFlow/raptrix-pslf-rs) converts GE PSLF into `.rpf`.

For the commercial Raptrix Power products, see [raptrixpower.com](https://raptrixpower.com).

## License

Mozilla Public License 2.0. See [LICENSE](LICENSE).
