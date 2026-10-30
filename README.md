# rpf-validator

Public validator and reference datasets for the open Raptrix Power Interchange (.rpf) format.

This repository provides tools and goldens to check that an `.rpf` file conforms to the locked schema contract (starting with v0.14.5) and to inspect what the file contains. It is intentionally standalone so you can validate converter output or published reference cases without the commercial Raptrix solver.

**MPL-2.0** — free to use, modify, and distribute.

## Status

Early. The first public step in making the open .rpf interchange easier to inspect and verify.

## What it does

- Validates structural conformance to the public schema contract (required tables, case-mode rules, metadata, version stamp).
- Supports reference datasets (goldens) so converter round-trips can be checked without a solver.
- Answers “does this file conform to v0.14.5 and what does it contain?”

It does **not** perform power-flow solves or validate physical correctness of a solution.

## Related repositories

- [raptrix-cim-rs](https://github.com/RaptrixPowerFlow/raptrix-cim-rs) — Open CIM/CGMES → .rpf converter and the source of truth for the schema contract.
- [raptrix-psse-rs](https://github.com/RaptrixPowerFlow/raptrix-psse-rs) — Open PSS/E → .rpf converter.
- [raptrix-pslf-rs](https://github.com/RaptrixPowerFlow/raptrix-pslf-rs) — Open GE PSLF → .rpf converter.

## License

Mozilla Public License 2.0 (MPL-2.0).

## Contact

For the broader Raptrix Power open ecosystem and commercial products, see [raptrixpower.com](https://raptrixpower.com).
