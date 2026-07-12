# Logical-Qubit Placement Sweep Summary

## Scope

- molecules: H4-H7
- PF: `4th(new_2)`
- circuit scope: `efficient_controlled_pf_one_step`
- rotation precision: `1e-5` conventional and `1e-2` cheap-RZ diagnostic
- grid: 10 x 10
- factory placement: four center-block factories
- magic generation period: 15
- maximum magic-state stock: 10000
- rows: 32 success / 0 failed / 0 skipped

The four placement conditions are:

| condition | role |
| --- | --- |
| `auto_greedy_soft` | qret automatic-mapping baseline |
| `explicit_compact_numeric` | compact cells with logical IDs in numeric order |
| `explicit_compact_interaction_aware` | the same compact cells, with logical IDs assigned to reduce weighted CNOT distance |
| `explicit_perimeter_numeric` | perimeter placement used as an intentionally non-compact stress case |

This is an automatic-baseline plus explicit-placement experiment, not a four-algorithm comparison.
qret advertises a METIS partition option, but the current implementation throws
`Partition by METIS is not implemented.`. The explicit placements and their source-QASM hashes,
qubit-to-cell mappings, bounding boxes, control-qubit IDs, and weighted interaction objectives are
recorded in `configs/topologies/logical_placement_h4_h7/placement_manifest.json`.

## Placement spread

Within each molecule and precision, the spread is

```text
spread = (maximum - minimum) / minimum
```

and is calculated from single-step resources.

| molecule | precision | runtime spread | QV spread | average active-area spread | QV minimum | QV maximum |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| H4 | `1e-5` | 0.00160% | 10.938% | 10.936% | interaction-aware | perimeter |
| H4 | `1e-2` | 0.03278% | 8.983% | 8.947% | interaction-aware | perimeter |
| H5 | `1e-5` | 0.00165% | 8.233% | 8.231% | interaction-aware | perimeter |
| H5 | `1e-2` | 0.00883% | 7.793% | 7.784% | interaction-aware | perimeter |
| H6 | `1e-5` | 0.00223% | 6.431% | 6.429% | interaction-aware | perimeter |
| H6 | `1e-2` | 0.01375% | 7.087% | 7.073% | interaction-aware | perimeter |
| H7 | `1e-5` | 0.00735% | 5.357% | 5.363% | interaction-aware | perimeter |
| H7 | `1e-2` | 0.06101% | 5.901% | 5.955% | interaction-aware | perimeter |

Logical placement changes qubit volume and average active area by several percent while runtime is
nearly unchanged. Therefore, in this experiment placement primarily changes occupied cell-time, not
the scheduling critical path.

## Same-cell assignment effect

`explicit_compact_numeric` and `explicit_compact_interaction_aware` use exactly the same cell set.
Their comparison isolates logical-ID assignment from placement shape and factory geometry.

| molecule | weighted CNOT objective reduction | QV reduction at `1e-5` | QV reduction at `1e-2` |
| --- | ---: | ---: | ---: |
| H4 | 18.41% | 2.170% | 1.922% |
| H5 | 16.78% | 1.226% | 1.807% |
| H6 | 17.77% | 1.694% | 1.709% |
| H7 | 17.19% | 1.648% | 1.850% |

The interaction-aware assignment is the qubit-volume minimum in all eight molecule/precision
groups. A roughly 17-18% reduction in the static weighted-Manhattan CNOT objective translates to a
smaller 1.2-2.2% reduction in compiled qubit volume. Thus, the static objective is directionally
useful but is not proportional to the final routed resource.

## Auto baseline and stress placement

Relative to the interaction-aware compact placement, qret's automatic baseline has higher qubit
volume in every group.

| molecule | auto penalty at `1e-5` | auto penalty at `1e-2` |
| --- | ---: | ---: |
| H4 | 6.578% | 3.641% |
| H5 | 5.626% | 6.073% |
| H6 | 4.126% | 4.471% |
| H7 | 3.472% | 4.631% |

The automatic mapping coordinates are identical between `1e-5` and `1e-2` for each molecule, so
these precision-regime comparisons are not caused by automatic placement changing between runs.

Relative to compact numeric placement, the perimeter stress case raises qubit volume by 3.620-8.531%
at `1e-5` and 3.943-6.889% at `1e-2`. This comparison intentionally changes both shape and distance
to the center factories, so it demonstrates sensitivity to an unfavorable placement but does not
separate Clifford-routing distance from magic-delivery distance.

## Interpretation

- Data-side logical placement remains a material space-time resource variable after cheap RZ:
  qubit-volume spread is 5.90-8.98% at `1e-2`.
- Cheap RZ does not uniformly amplify placement sensitivity. Spread decreases for H4/H5 and grows
  modestly for H6/H7.
- The persistent placement spread contrasts with the earlier factory-placement result, where cheap
  RZ reduced H4-H7 spread to 0.19-4.15%. This supports moving architecture analysis from factory-only
  placement toward logical-qubit placement and Clifford-side routing.
- Runtime spread remains at most 0.061%, while qubit volume closely follows average active area.
  Placement affects space/occupancy much more strongly than elapsed beat count.
- The interaction-aware placement is a diagnostic upper bound on a simple placement improvement,
  not a new qret automatic mapper. It uses interaction information extracted before synthesis.

Within every molecule/precision group, code distance, physical-qubit count, and chip-cell count are
identical across all four placements. The placement spreads therefore do not contain a code-distance
threshold change. Across precision regimes, H5 changes from distance 15 to 13 and H7 from 17 to 15,
so absolute `1e-5` versus `1e-2` resource reductions still include QEC discretization effects.

## Execution resources

- wall time: 10 min 59.98 sec
- peak RSS reported by `/usr/bin/time`: 32,464,960 KiB (about 31.0 GiB)
- cgroup limits: `MemoryHigh=44G`, `MemoryMax=48G`
- observed cgroup peak during execution: about 35.5 GiB
- swap growth during execution: none observed

## Next question

The next useful experiment is a grid size/aspect-ratio sweep while holding one automatic and one
explicit interaction-aware placement policy fixed. Capacity and aspect ratio should be varied
separately. This tests whether the remaining placement sensitivity is due to available routing room,
communication diameter, or congestion rather than the logical-ID assignment alone.
