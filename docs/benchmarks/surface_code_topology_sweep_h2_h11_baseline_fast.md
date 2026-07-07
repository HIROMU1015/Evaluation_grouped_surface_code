# Surface-Code Topology Sweep H2-H11 Baseline/Fast

## Scope

- Run completed at: `2026-07-07T05:49:40+09:00`
- Evaluation HEAD at run: `a4910defcfb1cc7e8c2cd2cd309bbf63c46cb919`
- Config: [`configs/surface_code_topology_sweep_h2_h11_baseline_fast.yaml`](../../configs/surface_code_topology_sweep_h2_h11_baseline_fast.yaml)
- Results:
  - [`results.md`](../../artifacts/surface_code_topology_sweep_h2_h11_baseline_fast/results.md)
  - [`results.csv`](../../artifacts/surface_code_topology_sweep_h2_h11_baseline_fast/results.csv)
  - [`results.jsonl`](../../artifacts/surface_code_topology_sweep_h2_h11_baseline_fast/results.jsonl)
  - [`run.log`](../../artifacts/surface_code_topology_sweep_h2_h11_baseline_fast/logs/run.log)

This is not a full QPE compile. The totals are QPE-scale linear extrapolations
from `efficient_controlled_pf_one_step` compile/profile results.

## Sweep Design

| item | value |
|---|---|
| molecules | H2-H11 |
| PF labels | `2nd`, `4th(new_2)` |
| magic conditions | baseline: period 15, fast_supply: period 8 |
| topology cases | `factory_left_edge`, `factory_center_block`, `factory_right_edge` |
| grid size | 10 x 10 |
| factory count | 4 |
| compile mode | `ftqc_compile_topology_qec` |
| total rows | 120 |
| success | 120 |
| failed | 0 |
| skipped | 0 |

Topology variants:

- [`tutorial_factory_left_edge.yaml`](../../configs/topologies/tutorial_factory_left_edge.yaml)
- [`tutorial_factory_center_block.yaml`](../../configs/topologies/tutorial_factory_center_block.yaml)
- [`tutorial_factory_right_edge.yaml`](../../configs/topologies/tutorial_factory_right_edge.yaml)

## Main Findings

- Topology placement barely changes QPE-scale total runtime in this setting.
  The maximum spread was about `0.036%`, with an average around `0.010%`.
- Topology placement has a larger effect on total qubit volume.
  The average spread was about `9.2%`, with a maximum around `24.4%`.
- `fast_supply` helps most on small systems. For H9-H11, the total runtime
  improvement is almost negligible under these settings.
- `4th(new_2)` is consistently shorter than `2nd`. With the best fast-supply
  topology per molecule, `4th(new_2)` runtime is `22.9%` to `40.3%` of `2nd`
  runtime.
- H4 `4th(new_2)` is the main exception in physical resources: `left_edge`
  uses `code_distance=15` and `physical_qubits=43200`, while `center_block`
  and `right_edge` use `code_distance=13` and `physical_qubits=32448`.

## Best Fast-Supply Runtime

The runtimes below use `code_cycle_time_sec = 1e-6` and show the best topology
within `fast_supply`.

| molecule | 2nd best fast runtime / topology | 4th(new_2) best fast runtime / topology | 4th/2nd |
|---|---:|---:|---:|
| H2 | 12.3 min / center_block | 3.5 min / center_block | 28.6% |
| H3 | 1.56 h / left_edge | 30.0 min / left_edge | 32.2% |
| H4 | 7.85 h / left_edge | 2.47 h / center_block | 31.4% |
| H5 | 14.25 h / center_block | 5.74 h / center_block | 40.3% |
| H6 | 2.41 d / right_edge | 14.75 h / right_edge | 25.5% |
| H7 | 3.92 d / center_block | 1.16 d / center_block | 29.6% |
| H8 | 9.49 d / center_block | 2.40 d / left_edge | 25.2% |
| H9 | 14.64 d / right_edge | 3.84 d / center_block | 26.2% |
| H10 | 28.03 d / right_edge | 6.41 d / right_edge | 22.9% |
| H11 | 38.63 d / right_edge | 9.13 d / right_edge | 23.6% |

## Not Changed

- Full QPE circuit generation was not used.
- QPE phase register, inverse QFT, measurement, and feed-forward were not
  generated.
- The logical circuit, Hamiltonian, grouping, PF labels, target error,
  rotation precision, routing algorithm, grid size, factory count, and QEC
  settings were held fixed across topology cases.
