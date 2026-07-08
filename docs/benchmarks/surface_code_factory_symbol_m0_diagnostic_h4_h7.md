# Surface-Code Factory Symbol / m0 Diagnostic H4-H7

## Scope

- Date of run: 2026-07-08.
- Mandatory phase: H4/H5.
- Safety-gated phases executed: H6 and H7.
- H8 or larger was not executed.
- PF: `4th(new_2)`.
- Circuit scope: `efficient_controlled_pf_one_step`.
- Compile mode: `ftqc_compile_topology_qec`.
- Magic generation period: 15.
- Magic stock: fixed 10000.
- Factory coordinate set fixed to `(0,0)`, `(4,4)`, `(9,0)`, `(9,9)`.
- Only the factory symbol-to-coordinate assignment was changed.

This is not a full QPE compile. No QPE phase register, inverse QFT, measurement,
feed-forward, or repeated QPE circuit was generated. QPE-scale totals, where
present in runner outputs, are linear extrapolations from one compiled/profiled
`efficient_controlled_pf_one_step`.

## Purpose

The diagnostic separates two possibilities:

- qret always or preferentially uses magic factory symbol `0`.
- qret selects a magic factory by geometry, distance, routing, or availability.

This matters because earlier topology sweeps may have been closer to an `m0`
placement sweep than a comparison of full factory sets.

## Topology Variants

| variant | m0 coordinate | m1 coordinate | m2 coordinate | m3 coordinate | coordinate set |
|---|---:|---:|---:|---:|---|
| `m0_left` | `(0,0)` | `(4,4)` | `(9,0)` | `(9,9)` | `(0,0); (4,4); (9,0); (9,9)` |
| `m0_center` | `(4,4)` | `(0,0)` | `(9,0)` | `(9,9)` | `(0,0); (4,4); (9,0); (9,9)` |
| `m0_right` | `(9,0)` | `(0,0)` | `(4,4)` | `(9,9)` | `(0,0); (4,4); (9,0); (9,9)` |
| `m0_far_corner` | `(9,9)` | `(0,0)` | `(4,4)` | `(9,0)` | `(0,0); (4,4); (9,0); (9,9)` |

## Results

| molecule | variant | m0 coordinate | used factory symbols | used factory coordinates | magic count by factory | active area ave | qubit volume | runtime | chip cells | physical qubits | code distance |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| H4 | `m0_left` | `(0,0)` | `0` | `(0,0)` | `{"0":184600}` | 11.379340 | 9,263,739 | 814,084 | 96 | 32,448 | 13 |
| H4 | `m0_center` | `(4,4)` | `0` | `(4,4)` | `{"0":184600}` | 11.379331 | 9,263,731 | 814,084 | 96 | 32,448 | 13 |
| H4 | `m0_right` | `(9,0)` | `0` | `(9,0)` | `{"0":184600}` | 11.379340 | 9,263,739 | 814,084 | 96 | 32,448 | 13 |
| H4 | `m0_far_corner` | `(9,9)` | `0` | `(9,9)` | `{"0":184600}` | 11.380168 | 9,264,413 | 814,084 | 96 | 32,448 | 13 |
| H5 | `m0_left` | `(0,0)` | `0` | `(0,0)` | `{"0":475906}` | 13.278000 | 28,179,832 | 2,122,295 | 96 | 43,200 | 15 |
| H5 | `m0_center` | `(4,4)` | `0` | `(4,4)` | `{"0":475906}` | 13.278000 | 28,179,832 | 2,122,295 | 96 | 43,200 | 15 |
| H5 | `m0_right` | `(9,0)` | `0` | `(9,0)` | `{"0":475906}` | 13.278000 | 28,179,832 | 2,122,295 | 96 | 43,200 | 15 |
| H5 | `m0_far_corner` | `(9,9)` | `0` | `(9,9)` | `{"0":475906}` | 13.284300 | 28,193,204 | 2,122,295 | 96 | 43,200 | 15 |
| H6 | `m0_left` | `(0,0)` | `0` | `(0,0)` | `{"0":1025480}` | 15.115264 | 69,171,725 | 4,576,283 | 96 | 43,200 | 15 |
| H6 | `m0_center` | `(4,4)` | `0` | `(4,4)` | `{"0":1025480}` | 15.115264 | 69,171,725 | 4,576,283 | 96 | 43,200 | 15 |
| H6 | `m0_right` | `(9,0)` | `0` | `(9,0)` | `{"0":1025480}` | 15.115264 | 69,171,725 | 4,576,283 | 96 | 43,200 | 15 |
| H6 | `m0_far_corner` | `(9,9)` | `0` | `(9,9)` | `{"0":1025480}` | 15.116068 | 69,175,405 | 4,576,283 | 96 | 43,200 | 15 |
| H7 | `m0_left` | `(0,0)` | `0` | `(0,0)` | `{"0":1971706}` | 17.279860 | 153,291,432 | 8,871,104 | 96 | 55,488 | 17 |
| H7 | `m0_center` | `(4,4)` | `0` | `(4,4)` | `{"0":1971706}` | 17.280178 | 153,294,237 | 8,871,103 | 96 | 55,488 | 17 |
| H7 | `m0_right` | `(9,0)` | `0` | `(9,0)` | `{"0":1971706}` | 17.279860 | 153,291,432 | 8,871,104 | 96 | 55,488 | 17 |
| H7 | `m0_far_corner` | `(9,9)` | `0` | `(9,9)` | `{"0":1971706}` | 17.297290 | 153,446,215 | 8,871,113 | 96 | 55,488 | 17 |

## Distance Check

`LATTICE_SURGERY_MAGIC` delivery distance follows the coordinate assigned to
symbol `0`:

| molecule | m0 left | m0 center | m0 right | m0 far corner |
|---|---:|---:|---:|---:|
| H4 mean magic distance | 12.2393 | 5.1053 | 6.7005 | 5.7607 |
| H5 mean magic distance | 11.3966 | 5.1477 | 6.9874 | 6.6034 |
| H6 mean magic distance | 10.8083 | 5.0091 | 7.7223 | 7.1917 |
| H7 mean magic distance | 10.8322 | 4.9245 | 7.6531 | 7.1678 |

## Interpretation

### Observed

- All 16 executed cases used only magic factory symbol `0` for `LATTICE_SURGERY_MAGIC`.
- The used factory coordinate always matched the coordinate assigned to `m0`.
- The nearest nonzero-symbol factory was not selected when `m0` was far away.
- Magic delivery distance moved strongly with m0 placement.
- Active area and qubit volume were mostly invariant under symbol-only permutations. The far-corner m0 case produced a small increase, most visibly in H7.

### Inferred

- These runs are consistent with qret using magic factory symbol `0` preferentially for `LATTICE_SURGERY_MAGIC`, not choosing the nearest factory by geometry.
- The earlier topology sweep cannot be explained by symbol assignment alone. It also changed the factory coordinate set and possibly layout occupancy/scheduling behavior.
- The previous `center_block < right_edge < left_edge` qubit-volume ordering should be treated as a placement/layout effect involving m0 and the broader topology, not as proof that qret uses all factories geometrically.

### Unresolved

- The quration/qret implementation reason for symbol-0 selection remains unresolved.
- This is an observed result for H4-H7 `4th(new_2)` only, not a formal proof for all inputs.
- It remains unclear how to make qret use multiple magic factories or choose factories by geometry.

## Safety / Execution

- H4/H5 mandatory phase: success 8, failed 0, skipped 0.
- H6 safety-gated phase: success 4, failed 0, skipped 0.
- H7 safety-gated phase: success 4, failed 0, skipped 0.
- H8 or larger was not executed.
- Peak RSS:
  - H4/H5 run: 7,732,048 KB.
  - H6 run: 16,812,476 KB.
  - H7 run: 32,465,496 KB.
- Elapsed wall time:
  - H4/H5 run: 3:35.85.
  - H6 run: 5:41.52.
  - H7 run: 11:05.54.
- Raw `mapping_state.json` files were not retained.

## Artifacts

- `artifacts/surface_code_factory_symbol_m0_diagnostic_h4_h7/diagnostics.csv`
- `artifacts/surface_code_factory_symbol_m0_diagnostic_h4_h7/diagnostics.jsonl`
- `artifacts/surface_code_factory_symbol_m0_diagnostic_h4_h7/summary.md`
- `artifacts/surface_code_factory_symbol_m0_diagnostic_h4_h7/logs/h4_h5_run.log`
- `artifacts/surface_code_factory_symbol_m0_diagnostic_h4_h7/logs/h6_run.log`
- `artifacts/surface_code_factory_symbol_m0_diagnostic_h4_h7/logs/h7_run.log`
