# Contract snapshot v0.14.5

The released `rpf-validator` package validates `.rpf` files against the vendored snapshot `src/rpf_validator/contract_v0145.json`. Users and CI do not clone `raptrix-cim-rs` and do not run Rust. A live checkout of that repository is a maintainer aid for generating the next snapshot. The released validator never reads it.

## Pin

| | |
| --- | --- |
| Snapshot | `contract_v0145.json` |
| Schema stamp | `v0.14.5` (readers also accept `0.14.5`) |
| Source repository | https://github.com/RaptrixPowerFlow/raptrix-cim-rs |
| Source commit | `0d4d48f` |

The authority for the wire contract remains `docs/schema-contract.md` and `raptrix-cim-arrow/src/schema.rs` in `raptrix-cim-rs`. This package copies the table layouts, version tokens, and the closed metadata enums from that commit. Do not hand-edit field types in the JSON. Do not point the package at whatever is on `main`.

## What v1 checks

Structural conformance only:

- Version stamp `v0.14.5` or `0.14.5`. If both `raptrix.version` and `rpf_version` are present, they must agree.
- The 18 canonical root tables, plus required `dc_converters`, present as struct columns even at zero rows. Tables are matched by name. Unknown trailing root columns are ignored.
- Column names and Arrow types are a prefix of a canonical layout or a documented read dialect. A missing field is an error only when that contract field is non-nullable.
- Required file metadata and agreement with the single `metadata` row for `case_mode`, `case_fingerprint`, and `validation_mode`. A blank table cell does not fail the file when the file-level key is set; that mismatch is a warning. `rpf.validation_mode` accepts `topology_only`, `solved_ready`, and `converter_export` (the token used by converter and solver exports, including the v0.14.5 funnel demo).
- When `case_mode` is `solved_snapshot` or solved tables have rows, the report states that the file contains a solved power flow and summarizes bus voltage, generator MW/Mvar, solved shunts, and solver metadata. That summary describes the stored solution. It does not check physical correctness.
- Case-mode and solved-table consistency, including `hour_ahead_advisory`.
- `rpf.rows.<table>` when the key is present: it must be an integer no greater than the struct length. A missing key falls back to the struct length and produces a warning.
- Dynamics `params` vocabulary (`p1`..`pN`, no `p0`). A `params_named=1` row may carry dictionary names and the positional tail together. `WTTQA1` is rejected only when those named breakpoints are still `p1`..`p4` and `pwr1`..`pwr4` are absent.
- Non-null bus ids on `branches`, `generators`, `loads`, `transformers_2w`, and `transformers_3w` (`bus_h_id`, `bus_m_id`, `bus_l_id`). `fixed_shunts` and `switched_shunts` are not checked in v1.

The stored fingerprint is required and non-empty. It is not recomputed. The CIM writer hashes source paths, sizes, and mtimes (`rpf_case_fingerprint_v1`), which is not a content hash of the `.rpf`.

## hour_ahead_advisory

`hour_ahead_advisory` is a legal `rpf.case_mode` token. For solved-table rules it is treated like a planning mode: `buses_solved`, `generators_solved`, and `switched_shunts_solved` must be absent, and `solved_state_presence` must not be `actual_solved` or `seed_only`. The CIM writer does not currently emit this token. v1 has no golden for it. A unit test accepts the token on an otherwise valid planning file.

## Later stamps

When a later stamp appears (for example v0.14.6), generate a new `contract_v0146.json`, record the new commit, and either support dual-read or drop the old snapshot once the ecosystem has moved. Replacing `contract_v0145.json` in place is not the update path.

## Out of scope

RPF is a case interchange: the network model, an optional solved state, contingencies, and case context. It is not a multi-period production-cost or outage-schedule format. This validator does not run a power flow, does not check physical correctness, and does not interpret multi-hour outage schedules or chronological load series. Those, if needed later, belong in optional tables under a minor version bump or in a companion file.
