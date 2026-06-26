# RSS Optimization Validation

## Scope

This note validates only the next Evaluation-side RSS reductions needed after
the stage-profiling work. It does not repeat the H2/H4 matrix, batch-size RSS
comparison, or `step_ir.json` load comparison.

Environment notes:

- Python: `/home/abe/myproject/.venv/bin/python3.11`
- Case: H4 `4th(new_2)`, batch size 2, topology compile unless noted.
- Circuit-release A/B/C uses integral-cache-seeded isolated cache roots. A first
  fully cold run with separate SCF caches produced a different semantic stream
  in one condition, so the comparison below uses the same cached integrals and
  cold prepared/compile/helper caches.
- `benchmark_results/` contains raw metrics and is intentionally untracked.

## Circuit Object Release

Observed semantic core fields matched across A/B/C:

- normalized instruction stream hash:
  `458803ab9ce5b9461d6d6d64d62fd21f5e3cf98c72d0b190c83480e177a240ef`
- instruction count: `401762`
- gate depth: `235772`
- magic-state count/depth: `91300` / `87029`
- peak magic layer: `8`
- opcode counts matched.

`optimized_ir_hash` differed across runs, but the normalized instruction stream
hash and counts matched. This is treated as semantic equality for this
experiment.

| condition | prepare elapsed | prepare sampled peak RSS | `build_step_circuit` delta | `basis_circuit` delta | release `qc,qc_basis` drop | release `qasm_text` drop | compile-start current RSS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 24.076 s | 329,068 KB | +43,008 KB | +46,604 KB | N/A | N/A | 312,296 KB |
| `del` | 24.180 s | 329,660 KB | +42,496 KB | +45,404 KB | 0 KB | 0 KB | 305,864 KB |
| `del + gc.collect()` | 24.514 s | 331,560 KB | +42,752 KB | +47,084 KB | 3,184 KB | 0 KB | 303,152 KB |

Observed facts:

- `del qc_basis; del qc` alone did not lower current RSS at the release point.
- `gc.collect()` after deleting circuit objects lowered current RSS by only
  about 3.1 MB and collected 128 objects.
- Deleting `qasm_text` did not lower current RSS, with or without GC.
- Prepare sampled peak did not improve; run-to-run variation is larger than the
  direct release-stage gain.

Judgment:

- Do not add production circuit-object early release for RSS reduction yet.
- Do not add production `gc.collect()`. Its direct effect was small, added about
  40 ms at the release stage, and did not lower prepare peak.

## `compile_info.json`

Fields actually used by `normalize_surface_code_step_metrics`:

- required: `magic_state_consumption_count`,
  `magic_state_consumption_depth`, `runtime`, `runtime_without_topology`,
  `qubit_volume`
- optional integer fields: `gate_count`, `gate_depth`,
  `measurement_feedback_count`, `measurement_feedback_depth`,
  `magic_factory_count`, `chip_cell_count`, `code_distance`,
  `num_physical_qubits`, `t_count`, `t_depth`
- passthrough: `execution_time_sec`

Independent extraction results, qret not rerun:

| input | method | elapsed | current RSS delta after extraction | current RSS after release | ru_maxrss | normalized metrics |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| H4 4th topology, 18.97 MB | full `json.load()` | 0.213 s | +53,872 KB | N/A | 111,692 KB | equal |
| H4 4th topology, 18.97 MB | full load + `del` | 0.218 s | +53,560 KB | +29,912 KB | 111,044 KB | equal |
| H4 4th topology, 18.97 MB | metric-field scan | 1.476 s | -96 KB | N/A | 57,344 KB | equal |
| H4 4th QEC, 18.97 MB | full `json.load()` | 0.212 s | +53,844 KB | N/A | 111,652 KB | equal |
| H4 4th QEC, 18.97 MB | full load + `del` | 0.222 s | +53,516 KB | +29,868 KB | 110,892 KB | equal |
| H4 4th QEC, 18.97 MB | metric-field scan | 1.490 s | -96 KB | N/A | 57,344 KB | equal |
| H4 2nd topology, 4.06 MB | full `json.load()` | 0.074 s | +11,360 KB | N/A | 54,720 KB | equal |
| H4 2nd topology, 4.06 MB | full load + `del` | 0.078 s | +11,448 KB | +9,404 KB | 54,712 KB | equal |
| H4 2nd topology, 4.06 MB | metric-field scan | 0.371 s | -64 KB | N/A | 42,720 KB | equal |

Cache-hit path, H4 4th topology:

| method | compile elapsed | read stage current RSS delta | read stage sampled peak | post-normalize current RSS |
| --- | ---: | ---: | ---: | ---: |
| full load before payload release change | 0.188 s | +51,864 KB | 289,176 KB | 270,888 KB |
| metric-field scan prototype | 1.426 s | -68 KB | 237,696 KB | 219,452 KB |
| full load + production payload `del` | 0.195 s | +51,828 KB | 288,156 KB | 246,172 KB |

Observed facts:

- Full load is fast but raises current RSS by about 52-54 MB for H4 4th.
- Deleting the full payload after normalization lowers current RSS by about
  23.6 MB for H4 4th. `gc.collect()` had no additional effect in the independent
  measurement.
- Metric-field scanning reduces H4 4th current RSS by about 52 MB and cuts
  child-process `ru_maxrss` roughly in half, but it is about 1.2-1.3 s slower on
  the 18.97 MB files.
- Topology-only and QEC compile-info files produced identical normalized metrics
  across methods.
- A separate "keep required top-level subtree only" method was not implemented:
  the fields used by the current normalizer are top-level scalars, so the
  metric-field scan is already the smaller prototype. The full-load +
  metric-field dict + payload release path covers the early-release comparison.

Judgment:

- Production change applied: release the full `compile_info` payload with `del`
  immediately after normalization. This is low risk and improves retained RSS.
- Metric-field extraction remains opt-in through
  `SURFACE_CODE_COMPILE_INFO_EXTRACTION_MODE=top_level_metric_fields`. Do not
  make it the default yet because it uses a custom JSON scanner and is slower on
  cache-hit runs.

## Prepare/Compile Split

H4 `4th(new_2)`, topology compile, batch size 2, same integral cache seeded into
both runs:

| condition | compile-start parent current RSS | parent ru_maxrss | qret subprocess peak RSS | elapsed |
| --- | ---: | ---: | ---: | ---: |
| same process prepare -> compile | 311,012 KB | 356,912 KB | 2,089,680 KB | 31.266 s |
| split process prepare only | N/A | 336,220 KB | N/A | 24.522 s |
| split process compile only | 40,060 KB | 112,192 KB | 2,089,852 KB | 6.986 s |

Observed facts:

- Split compile starts with about 270,952 KB less parent current RSS.
- The qret subprocess peak remains about 2.09 GB in both cases.
- Core semantic fields matched between same-process and split-process prepare.
- Total split elapsed was about 31.508 s versus 31.266 s same-process in this
  single run.

Judgment:

- Split prepare/compile is useful for measurement separation and memory-limited
  operation.
- It is not a qret peak-RSS fix; the qret subprocess remains dominant.

## Final Ranking

| candidate | measured RSS reduction | elapsed impact | implementation size | semantic risk | recommendation |
| --- | ---: | ---: | --- | --- | --- |
| circuit object early release | 0 KB with `del`; about 3 MB only with GC | none for `del`; small GC cost | small | low | do not productionize for RSS |
| production `gc.collect()` | about 3 MB in one release stage | about 40 ms at release stage | small | low-medium operational cost | do not add |
| compile-info payload early release | about 23.6 MB retained-RSS drop after normalization | negligible | small | low | implemented |
| compile-info metric-field extraction | about 52 MB current-RSS reduction on H4 4th cache-hit path | about +1.2 s | medium, custom parser | medium | keep opt-in prototype |
| prepare/compile split process | about 271 MB lower parent RSS at compile start | about +0.24 s in one run | medium script/operation | low | useful operational mode, not default |

## Answers

1. Circuit object early release lowered current RSS by 0 MB with `del` alone.
   `del + gc.collect()` lowered it by about 3 MB at the circuit-object release
   stage.
2. `gc.collect()` had a small circuit-object effect and no `compile_info`
   payload effect beyond `del`.
3. Avoiding full `compile_info.json` load lowered H4 4th current RSS by about
   52 MB, but was slower.
4. The partial extractor is useful as an opt-in memory mode, but the custom
   parser and slower cache-hit elapsed do not justify default production use yet.
5. Prepare/compile split meaningfully lowers parent RSS at compile start, but
   not qret subprocess peak RSS.
6. Production change to keep: `compile_info` payload early release after
   normalization.
7. Do not add production circuit release, production GC, or default partial JSON
   extraction based on these measurements.
