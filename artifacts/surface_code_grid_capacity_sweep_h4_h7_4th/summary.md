# Logical-Grid Capacity Sweep Summary

## Scope

- molecules: H4-H7
- PF: `4th(new_2)`
- circuit scope: `efficient_controlled_pf_one_step`
- rotation precision: `1e-5` conventional and `1e-2` cheap-RZ diagnostic
- logical-cell grids: 8x8, 10x10, and 12x12
- placement policies: qret `auto_greedy_soft` and explicit interaction-aware
- factories: four factories in a centered 2x2 block on every grid
- magic generation period: 15
- maximum magic-state stock: 10000
- rows: 44 success / 4 failed / 0 skipped

The 10x10 explicit topology is identical to the interaction-aware topology used in the preceding
logical-placement sweep. Each other explicit topology is generated deterministically from the same
pre-synthesis weighted CNOT graph. The generated mappings, QASM hashes, cell coordinates, and the
number of non-soft supplemental cells are recorded in
`configs/topologies/logical_grid_capacity_h4_h7/grid_capacity_manifest.json`.

## Auto-mapping capacity boundary

The centered 8x8 grid provides 12 candidates under qret's soft automatic-placement rule. Therefore,
automatic mapping succeeds for H4 (9 logical qubits) and H5 (11), but fails for H6 (13) and H7 (15)
at both precision values.

| molecule | logical qubits | auto 8x8 | explicit 8x8 | auto 10x10 | auto 12x12 |
| --- | ---: | --- | --- | --- | --- |
| H4 | 9 | success | success | success | success |
| H5 | 11 | success | success | success | success |
| H6 | 13 | failed | success | success | success |
| H7 | 15 | failed | success | success | success |

All four failures report `Failed to find partition` followed by `Failed to find place to map
qubits`. Explicit H6/H7 placement demonstrates that the grid has enough physical cells; the failure
is a candidate-generation / automatic-mapping policy limit rather than simple cell-count exhaustion.
The explicit generator supplements one non-soft cell for H6 and three for H7 on 8x8, and records
that intervention in the manifest.

## Explicit placement: grid effect

The following table reports change relative to the matched 10x10 interaction-aware result.

| molecule | precision | 8x8 runtime | 8x8 QV | 12x12 runtime | 12x12 QV |
| --- | ---: | ---: | ---: | ---: | ---: |
| H4 | `1e-5` | +0.000% | +0.645% | +0.000% | +0.646% |
| H4 | `1e-2` | +0.000% | +0.794% | +0.000% | +0.796% |
| H5 | `1e-5` | +0.000% | +0.342% | +0.000% | +0.342% |
| H5 | `1e-2` | +0.000% | +0.754% | +0.000% | +0.745% |
| H6 | `1e-5` | +0.000% | +1.593% | -0.000% | +0.350% |
| H6 | `1e-2` | +0.005% | -0.024% | +0.000% | +0.602% |
| H7 | `1e-5` | +11.122% | +14.057% | -0.008% | +0.929% |
| H7 | `1e-2` | +0.197% | +1.648% | -0.061% | +0.304% |

H4-H6 are weakly sensitive to grid capacity under the explicit policy: runtime is effectively
unchanged and QV remains within about 1.6% of 10x10. H7 crosses a capacity/congestion boundary on
8x8 in the conventional regime. Its topology-induced runtime increment changes from 838 beats on
10x10 to 987,508 beats on 8x8, and QV rises by 14.06%.

The H7 8x8 penalty is much smaller under cheap RZ. The pre-synthesis weighted CNOT distance of the
8x8 explicit placement is lower than that of 10x10 (`1,032,100` versus `1,182,008`), yet the
conventional compile is much worse. Static pair distance alone therefore does not explain the
result. The observation is consistent with routing congestion and occupied-cell interference from
the much larger conventional RZ-synthesis / magic workload, but direct congestion counters are not
available in this sweep.

## Automatic placement: larger is not automatically better

Relative to the matched 10x10 automatic result:

| molecule | precision | 8x8 QV | 12x12 QV |
| --- | ---: | ---: | ---: |
| H4 | `1e-5` | -4.161% | +3.125% |
| H4 | `1e-2` | -0.837% | +5.868% |
| H5 | `1e-5` | -4.463% | +1.791% |
| H5 | `1e-2` | -4.348% | +2.426% |
| H6 | `1e-5` | failed | +1.336% |
| H6 | `1e-2` | failed | +2.647% |
| H7 | `1e-5` | failed | +1.863% |
| H7 | `1e-2` | failed | +3.155% |

The 12x12 automatic mapper spreads logical qubits farther apart instead of using the extra cells as
routing slack. Mapping diagnostics show the distance increase directly.

| molecule | CNOT mean 10x10 -> 12x12 | nearest-factory mean 10x10 -> 12x12 | magic-op mean 10x10 -> 12x12 |
| --- | ---: | ---: | ---: |
| H4 | 5.690 -> 9.020 | 4.333 -> 5.778 | 6.782 -> 7.685 |
| H5 | 8.031 -> 9.496 | 4.818 -> 6.000 | 6.830 -> 7.462 |
| H6 | 7.315 -> 8.961 | 4.769 -> 6.154 | 6.553 -> 7.154 |
| H7 | 7.783 -> 9.847 | 4.933 -> 6.267 | 6.361 -> 7.187 |

Consequently, the automatic-mapping QV penalty relative to interaction-aware placement generally
increases with grid size. At 12x12 it is 4.43-9.20% for conventional RZ and 6.59-8.86% for cheap RZ
among H4-H7. Added area is not beneficial unless the placement objective prevents unnecessary
communication-distance growth.

## Static footprint

The grid choice changes static chip capacity even when active-area QV changes little.

| grid | non-factory chip cells | physical-qubit multiplier vs 10x10 |
| --- | ---: | ---: |
| 8x8 | 60 | 0.625x |
| 10x10 | 96 | 1.000x |
| 12x12 | 140 | 1.458x |

For a fixed code distance, physical-qubit count scales with these chip-cell counts. Moving from
10x10 to 12x12 increases the static physical-qubit footprint by 45.8%, while the explicit-placement
QV improvement is absent. The larger grid lowers active-area ratio because the denominator grows,
but it does not lower absolute average active area in this experiment.

Within each molecule/precision group, code distance is common across all successful grids. The grid
comparisons therefore do not contain a code-distance threshold change. Across precision regimes,
H5 changes from distance 15 to 13 and H7 from 17 to 15, as in the previous sweep.

## Interpretation

- 8x8 is sufficient for H4/H5 under both policies, but automatic placement reaches its 12-candidate
  limit at H6/H7.
- Explicit placement can fit H6/H7 on 8x8, but conventional H7 suffers a clear routing-capacity
  penalty. This is a practical capacity boundary, not merely an automatic-mapper failure.
- 10x10 is the most robust tested point: it avoids H7 congestion without the static footprint and
  automatic-distance growth of 12x12.
- 12x12 does not improve runtime or QV under the tested policies. Its main observed effect is a
  larger static footprint and, for auto mapping, longer communication distances.
- Cheap RZ reduces the H7 8x8 congestion penalty rather than exposing a larger grid sensitivity.
  Grid sensitivity therefore depends on the workload routed through the available cells.

## Execution resources

- wall time: 19 min 56.35 sec
- peak RSS reported by `/usr/bin/time`: 32,465,388 KiB (about 31.0 GiB)
- cgroup limits: `MemoryHigh=44G`, `MemoryMax=48G`
- highest observed cgroup current usage: about 33.3 GiB
- swap growth during execution: none observed

The high-RSS intervals occurred while extracting H7 automatic mapping results. Normal compile
intervals were much smaller.

## Next question

The next clean experiment is an aspect-ratio sweep at approximately fixed cell count, using H6/H7
and retaining 10x10 as a reference. Because 8x8 exposed both a mapper candidate limit and H7
congestion, the aspect-ratio sweep should report mapping success separately from routed runtime/QV
and should keep an explicit interaction-aware policy alongside the automatic baseline.
