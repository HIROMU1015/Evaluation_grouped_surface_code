# Fixed-Circuit Runtime Grid-Threshold Summary

## Scope

- molecules: H5 control and H7 target
- PF: `4th(new_2)`
- circuit scope: `efficient_controlled_pf_one_step`
- rotation precision: `1e-5` fixed
- placement: explicit interaction-aware
- grids: 8x8, 8x10, 9x9, 10x8, 10x10, 10x12, 12x10
- factory condition: centered 2x2 block, period 15, stock 10000
- rows: 14 success / 0 failed / 0 skipped

Within each molecule, QASM hash, optimized IR hash, rotation precision, RZ count/depth,
magic-state count/depth, topology-free runtime, and code distance are identical across all grids.
The runtime differences are therefore architecture differences, not circuit-synthesis changes.

## Runtime results

Changes are relative to the matched 10x10 result.

| molecule | grid | runtime | vs 10x10 | topology overhead |
| --- | --- | ---: | ---: | ---: |
| H5 | 8x8 | 2,122,291 | +0.000000% | 26 |
| H5 | 8x10 | 2,122,291 | +0.000000% | 26 |
| H5 | 9x9 | 2,122,622 | +0.015596% | 357 |
| H5 | 10x8 | 2,122,291 | +0.000000% | 26 |
| H5 | 10x10 | 2,122,291 | reference | 26 |
| H5 | 10x12 | 2,122,291 | +0.000000% | 26 |
| H5 | 12x10 | 2,122,291 | +0.000000% | 26 |
| H7 | 8x8 | 9,858,370 | +11.121544% | 987,508 |
| H7 | 8x10 | 8,871,631 | -0.000778% | 769 |
| H7 | 9x9 | 8,871,647 | -0.000597% | 785 |
| H7 | 10x8 | 8,871,614 | -0.000969% | 752 |
| H7 | 10x10 | 8,871,700 | reference | 838 |
| H7 | 10x12 | 8,871,167 | -0.006008% | 305 |
| H7 | 12x10 | 8,871,184 | -0.005816% | 322 |

H5 is runtime-insensitive over the tested grids: its maximum change is 0.016%. H7 is also
runtime-insensitive once the grid is at least 8x10, 9x9, or 10x8. Excluding 8x8, the H7 runtime
spread is about 0.006%. The only strong runtime effect is H7 on 8x8.

## Threshold interpretation

The 8x8 center-factory topology has 12 cells under the soft placement-candidate rule. H7 has 15
logical qubits, so the explicit placement requires three supplemental non-soft cells. Increasing
either grid dimension, or moving to 9x9, provides enough soft candidates and immediately returns
runtime to the uncongested level.

The H7 8x8 static weighted CNOT distance is `1,032,100`, lower than the 10x10 value of `1,182,008`.
The runtime penalty therefore cannot be explained by longer static pair distances. It is consistent
with insufficient routing slack / occupied-cell congestion caused by packing the logical qubits
around the center factories. Direct routing-wait and congestion counters were not collected, so the
mechanism remains an inference.

The result supports a threshold model:

```text
adequate routing slack:
  grid shape changes -> runtime approximately unchanged

insufficient routing slack:
  architecture constraint enters the critical path -> runtime rises sharply
```

## Secondary metrics

H7 8x8 also increases QV by 14.057% relative to 10x10. This combines the 11.122% runtime increase
with a 2.642% increase in average active area. For all other H7 grids, QV remains between -0.255%
and +1.220% of 10x10 while runtime is effectively unchanged. Their QV differences are therefore
active-area effects rather than critical-path effects.

The 10x12 and 12x10 cases reduce topology overhead from 838 beats to 305-322 beats, but this changes
total runtime by less than 0.01%. It is not a practically large runtime improvement.

## Conclusion

- A large architecture-induced runtime change exists for a fixed circuit, but it appears at a
  routing-capacity threshold rather than as a broad sensitivity to grid shape.
- H7 8x8 is the observed congested case; 8x10, 9x9, and 10x8 are already sufficient to remove the
  11.12% penalty.
- H5 is a valid non-congested control and shows no material runtime sensitivity.
- The next high-value diagnostic is direct routing-wait / congestion instrumentation on H7 8x8
  versus H7 8x10 or 10x10, not a broader aggregate grid sweep.

## Execution resources

- wall time: 9 min 38.90 sec
- peak RSS: 3,381,608 KiB (about 3.23 GiB)
- process swaps: 0
- memory guard: `MemoryHigh=44G`, `MemoryMax=48G`
