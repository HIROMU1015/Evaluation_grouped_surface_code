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

## Phase 1 Decomposition: Fixed-PF Architecture Effects

This section treats each PF independently. For each fixed
`molecule / PF / magic regime`, the spread is computed across the three
topology cases as:

```text
spread = (max(topology cases) - min(topology cases)) / min(topology cases)
```

The purpose is to separate whether the observed qubit-volume differences come
from runtime, chip cells, physical qubits, code distance, or topology-dependent
layout/routing occupancy.

### Spread by PF and Magic Regime

| PF | magic regime | runtime spread avg / max | qubit volume spread avg / max | chip_cells spread | physical_qubits / code_distance spread |
|---|---:|---:|---:|---:|---:|
| `2nd` | baseline | `0.0095% / 0.0287%` | `9.21% / 21.98%` | `0%` | `0%` |
| `2nd` | fast_supply | `0.0112% / 0.0364%` | `9.24% / 24.40%` | `0%` | `0%` |
| `4th(new_2)` | baseline | `0.0100% / 0.0323%` | `9.16% / 21.38%` | `0%` | H4 only |
| `4th(new_2)` | fast_supply | `0.0087% / 0.0286%` | `9.08% / 23.21%` | `0%` | H4 only |

Runtime changes are tiny compared with qubit-volume changes. The chip-cell
count is fixed at `96` in all `120` rows. `physical_qubits` and `code_distance`
are also fixed within each molecule/PF/magic group, except for H4
`4th(new_2)`.

### Best Topology Frequency

Runtime-best topology is not stable. Ties are counted for each tied topology.

| PF | magic regime | runtime-best frequency |
|---|---:|---|
| `2nd` | baseline | center: 7, left: 3, right: 3 |
| `2nd` | fast_supply | center: 5, right: 4, left: 2 |
| `4th(new_2)` | baseline | center: 5, left: 4, right: 4 |
| `4th(new_2)` | fast_supply | center: 5, right: 3, left: 2 |

Qubit-volume-best topology is stable:

| metric | best topology | worst topology |
|---|---|---|
| `qubit_volume` | `factory_center_block`: 40/40 groups | `factory_left_edge`: 40/40 groups |

### Discrete Resource Spread

| metric | result |
|---|---|
| `chip_cells` | no spread; all rows use `96` |
| `physical_qubits` | spread only for H4 `4th(new_2)` |
| `code_distance` | spread only for H4 `4th(new_2)` |

For H4 `4th(new_2)`, the exception is:

| topology | code_distance | physical_qubits |
|---|---:|---:|
| `factory_left_edge` | 15 | 43200 |
| `factory_center_block` | 13 | 32448 |
| `factory_right_edge` | 13 | 32448 |

### Qubit-Volume Interpretation

Qubit volume can be read approximately as runtime multiplied by effective
spatial occupancy. Since runtime is almost unchanged while qubit volume moves
by about `9%` on average and up to `24.4%`, the dominant effect is not runtime.

Using `qubit_volume / runtime_with_topology` as a proxy for effective spatial
occupancy, the spread almost matches the qubit-volume spread:

| group | runtime spread | qubit volume spread | `(qubit_volume / runtime)` spread |
|---|---:|---:|---:|
| H2 `2nd` fast_supply | `0.036%` | `24.40%` | `24.36%` |
| H2 `4th(new_2)` fast_supply | `0.0035%` | `23.21%` | `23.21%` |
| H3 `2nd` baseline | `0.0276%` | `15.77%` | `15.77%` |
| H4 `4th(new_2)` baseline | `0.0190%` | `12.82%` | `12.82%` |

The Phase 1 conclusion is that the qubit-volume difference is mostly a
topology/layout/routing occupancy effect. It is not explained by runtime,
chip-cell count, physical-qubit count, or code distance, except for the H4
`4th(new_2)` left-edge case.

The current sweep has `mapping_result_json` disabled, so it cannot yet identify
which cells, routes, or operation regions create the occupancy gap. A follow-up
run should enable the relevant mapping/layout diagnostics for selected small
cases, especially the center-block versus left-edge contrast.

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
