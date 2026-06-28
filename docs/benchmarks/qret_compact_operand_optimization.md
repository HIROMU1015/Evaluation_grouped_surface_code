# qret Compact Singleton Operand A/B

## Execution Limits

- largest measured case: `H5`
- H6 executed: `False`
- H7 executed: `False`
- H8 executed: `False`
- H9 executed: `False`
- H9 memory: estimated from observed H4/H5 values, not measured.

## Phase 0 Magic Path Baseline

- final holder: `std::list<Coord3D>` plus optional shared handle
- production default: `interned`
- rollback: `QRET_MAGIC_PATH_STORAGE=legacy_list`
- Phase 1 baseline source: Phase 0 interned runs from current final-holder validation.

## Compact Operand Scope

- `TWIST.qtarget`
- `HADAMARD.qtarget`
- `LATTICE_SURGERY_MAGIC.qtarget`
- `LATTICE_SURGERY_MAGIC.ccreate`
- `LATTICE_SURGERY_MAGIC.mtarget`
- `PROBABILITY_HINT.cdepend`

## Run Matrix

| case | variant | runs | median qret peak KB | median routing peak KB | median routing exit KB | median elapsed s |
| ---- | ------- | ---: | ------------------: | ---------------------: | ---------------------: | ---------------: |
| H4 `4th(new_2)` | baseline | 1 | 170,948 | 168,420 | 168,420 | 4.847 |
| H4 `4th(new_2)` | candidate | 1 | 174,368 | 166,176 | 166,176 | 5.240 |
| H5 `4th(new_2)` | baseline | 2 | 434,924 | 434,924 | 434,924 | 18.565 |
| H5 `4th(new_2)` | candidate | 2 | 422,600 | 421,832 | 421,832 | 20.253 |

## Metric Parity

| comparison | raw equal | normalized equal | raw mismatches | normalized mismatches |
| ---------- | --------: | ---------------: | -------------- | --------------------- |
| h4_4th_new2:candidate:run_1 | True | True | [] | [] |
| h5_4th_new2:candidate:run_1 | True | True | [] | [] |
| h5_4th_new2:candidate:run_2 | True | True | [] | [] |

## H5 Gate

- raw metrics parity: `True`
- normalized metrics parity: `True`
- path interning stats unchanged: `True`
- H5 median qret peak reduction KB: `12,324`
- H5 median qret peak reduction percent: `2.834`
- all candidate runs below baseline: `True`
- elapsed regression percent: `9.092`
- elapsed gate <=3%: `False`
- production candidate adopted by H5 measurement: `False`

## Routing Peak Operand Component Snapshot

| case | variant | run | MachineFunction inst | non-path operand MB | path storage MB | qtarget node MB | cdepend node MB | ccreate node MB | mtarget node MB |
| ---- | ------- | --: | -------------------: | ------------------: | --------------: | --------------: | ---------------: | ---------------: | --------------: |
| H4 `4th(new_2)` | baseline | 1 | 570,378 | 19.6 | 1.5 | 11.2 | 2.1 | 2.1 | 2.1 |
| H5 `4th(new_2)` | baseline | 1 | 1,499,072 | 51.4 | 5.0 | 29.7 | 5.4 | 5.4 | 5.4 |
| H5 `4th(new_2)` | baseline | 2 | 1,499,072 | 51.4 | 5.0 | 29.7 | 5.4 | 5.4 | 5.4 |
| H4 `4th(new_2)` | candidate | 1 | 570,378 | 2.6 | 1.5 | 0.5 | 0.0 | 0.0 | 0.0 |
| H5 `4th(new_2)` | candidate | 1 | 1,499,072 | 7.0 | 5.0 | 1.6 | 0.0 | 0.0 | 0.0 |
| H5 `4th(new_2)` | candidate | 2 | 1,499,072 | 7.0 | 5.0 | 1.6 | 0.0 | 0.0 | 0.0 |

## Safety And Provenance

H5 runs recorded `MemTotal`, `MemAvailable`, `SwapTotal`, `SwapFree`, and disk free before execution. H6-H9 are rejected by script guard and test guard.

- baseline summary: `/home/abe/Project/Evaluation_grouped_surface_code/artifacts/qret_compact_operands/phase0_magic_path/summary.json`
- candidate qret hash: `d519cdb25446cf243053e84ffa559b7e6bd7dbd66365e1488d632208616dbbf5`
- candidate lib hash: `de718ac2b82e1a4efa6b957509acaf62f9e497fe40b229df9d7a642363c8349c`
