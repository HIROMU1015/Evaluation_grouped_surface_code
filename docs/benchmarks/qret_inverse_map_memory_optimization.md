# qret Inverse Map Memory Optimization

H6 was not run. This profile only uses H4 for instrumentation/correctness checks and H5 for A/B selection.

## Environment

- Evaluation HEAD at run start: `568bf122e3bc6afacc975b66049bb642d337604a`
- qret executable hash: `d519cdb25446cf243053e84ffa559b7e6bd7dbd66365e1488d632208616dbbf5`
- libqret-core hash: `72ab48ae5227c325d5b0d236d3f48e115f04b37f8c07ac63f7445f72a3d6aa41`
- libqret-core path: `/home/abe/Project/Evaluation_grouped_surface_code/build/quration/cmake-build/quration-core/src/libqret-core.so.1.0.2`
- build requested: `False`
- batch size: `2`
- sampling interval: `0.02` sec
- output root: `/home/abe/Project/Evaluation_grouped_surface_code/artifacts/qret_inverse_map_memory`

## Consumer Audit

| method | call site | stage | lazy rebuild required |
| ------ | --------- | ----- | --------------------- |
| `ConstructInverseMap` | `routing.cpp` | routing start after validate | no |
| `ConstructInverseMap` | `runtime_simulation_pruning.cpp` | pruning pass setup | no |
| `Contain` | `simulator.h`, `search_chip_comm.cpp` | routing helper lookup | yes for custom post-routing passes |
| `InsertBefore` | `simulator.cpp`, `runtime_simulation_pruning.cpp` | routing/pruning mutation | yes |
| `InsertAfter` | `simulator.cpp`, `search_chip_comm.cpp` | routing mutation | yes |
| `Erase` | `simulator.cpp`, `search_chip_comm.cpp`, `runtime_simulation_pruning.cpp` | routing/pruning mutation | yes |
| `InverseMapSize` | `memory_profile_stats.cpp` | profiling markers | no |
| `mp_` | `machine_function.cpp` only | implementation detail | no external direct use |

Compile-info and pipeline-state output iterate instructions directly and do not require the inverse map. Custom post-routing passes remain compatible because `Contain`, `InsertBefore`, `InsertAfter`, and `Erase` rebuild lazily.

## Corrected MachineFunction Breakdown

| component | count | estimated bytes | share |
| --------- | ----: | --------------: | ----: |
| instruction object bytes | 1,498,544 | 140,613,808 | 38.8% |
| instruction list node bytes | 1,498,544 | 35,965,056 | 9.9% |
| basic block node bytes | 3 | 456 | 0.0% |
| inverse map bytes | 1,498,544 | 59,941,760 | 16.6% |
| operand list node bytes |  | 125,567,692 | 34.7% |
| condition list bytes | 236,736 | 5,681,664 | 1.6% |
| ancilla/path coordinate list node bytes | 2,561,533 | 71,722,924 | 19.8% |
| destination coordinate bytes | 14 | 168 | 0.0% |
| metadata bytes | 1,498,544 | 23,976,704 | 6.6% |
| predecessor/successor container bytes |  | 0 | 0.0% |
| compile-info bytes |  | 768 | 0.0% |
| IR pointer bytes |  | 8 | 0.0% |
| MachineFunction corrected total |  | 362,089,540 | 100.0% |

Destination coordinate and metadata bytes are reported as object subfields and are not added again to the corrected total. Ancilla/path list nodes are included once through operand list node bytes.

## Instruction Type Breakdown

| type | count | object MB | operand MB | ancilla/path MB | total MB |
| ---- | ----: | --------: | ---------: | --------------: | -------: |
| LATTICE_SURGERY_MAGIC | 236,736 | 37.9 | 79.7 | 63.5 | 123.1 |
| TWIST | 671,158 | 51.2 | 20.8 | 0.0 | 87.3 |
| HADAMARD | 319,110 | 21.9 | 7.3 | 0.0 | 36.5 |
| PROBABILITY_HINT | 236,736 | 19.9 | 5.4 | 0.0 | 30.7 |
| CNOT | 34,780 | 3.2 | 6.5 | 4.9 | 10.5 |
| ALLOCATE | 10 | 0.0 | 0.0 | 0.0 | 0.0 |
| DEALLOCATE | 10 | 0.0 | 0.0 | 0.0 | 0.0 |
| ALLOCATE_MAGIC_FACTORY | 4 | 0.0 | 0.0 | 0.0 | 0.0 |

## H5 Inverse Map

- entry count: `1,498,544`
- estimated bytes: `59,941,760` (`57.2` MB)
- basic block count: `3`
- largest block entries: `1,498,520`
- key size bytes: `8`
- mapped iterator size bytes: `8`
- estimated node overhead bytes: `24`

`std::map` node size is an estimate; the C++ standard does not specify node layout.

## H5 A/B

| variant | median peak | routing exit | after release | calc-info peak | elapsed |
| ------- | ----------: | -----------: | ------------: | -------------: | ------: |
| baseline | 641,488 | 548,048 | 548,048 | 641,488 | 21.269 |
| inverse_map_release | 548,032 | 548,032 | 548,032 | 548,032 | 21.124 |

## Allocator A/B

| variant | stage | uordblks | fordblks | RSS |
| ------- | ----- | -------: | -------: | --: |
| baseline | `routing_before_inverse_map_release` | 510,182 | 30,537 | 547,772 |
| baseline | `routing_after_inverse_map_release` | 510,180 | 30,539 | 547,772 |
| baseline | `after_calc_info_with_topology` | 510,180 | 123,911 | 641,212 |
| inverse_map_release | `routing_before_inverse_map_release` | 510,179 | 30,536 | 547,892 |
| inverse_map_release | `routing_after_inverse_map_release` | 416,519 | 124,196 | 547,892 |
| inverse_map_release | `after_calc_info_with_topology` | 416,518 | 124,197 | 547,892 |

## Correctness

- raw metrics parity: `True`
- normalized metrics parity: `True`
- H4 full schema raw parity: `True`
- H4 full schema normalized parity: `True`
- summary schema: qret return code was zero for completed A/B runs.
- custom pipeline lazy rebuild: covered by `target_sc_ls_fixed_v0_machine_function_inverse_map`.
- routing after release inverse map entries: `0`

## H4 Full Schema Check

| release env | return code | elapsed | compile_info bytes | after-release entries |
| ----------- | ----------: | ------: | -----------------: | --------------------: |
| 0 | 0 | 5.847 | 18,966,758 | 570,306 |
| 1 | 0 | 5.738 | 18,966,758 | 0 |

## Final Answers

1. H5 inverse map estimated size: `57.2` MB.
2. Release-immediate RSS drop: `0.0` MB.
3. H5 final peak drop: `91.3` MB (`14.57%`).
4. Calc-info reuse of freed allocator space: compare `fordblks` in Allocator A/B; observed after-release `fordblks` is `124,196` KB.
5. Elapsed ratio release/baseline: `0.9932`.
6. Lazy rebuild works in targeted C++ tests.
7. Custom pipeline compatibility is maintained by lazy rebuild.
8. Corrected MachineFunction total: `345.3` MB.
9. Ancilla/path list: `68.4` MB.
10. Metadata: `22.9` MB.
11. Operand list: `119.8` MB.
12. Inverse map release production default: `True`.
13. If not production default, reason: `passes=True`, consistent peak drop `True`, elapsed ratio `0.9932`.
14. Next candidate is ancilla/path only if the corrected value crosses the threshold above; otherwise move to Python parent memory.
15. Python parent process should be considered if inverse map and ancilla/path do not meet the next-candidate threshold.
16. H6 was not run.
