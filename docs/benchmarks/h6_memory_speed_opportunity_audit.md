# H6 Memory and Compile Speed Opportunity Audit

Date: 2026-07-03

Note: This is a historical H6 audit from 2026-07-03. The `reps=4` basis
decomposition default was adopted later after H4/H5 strict A/B validation.

Scope:

- Case: H6 `4th(new_2)`
- Compile mode: `ftqc_compile_topology_qec`
- Compile info output: `summary`
- Pipeline-state output: skipped
- Existing H6/H7/H8 caches were not used for the measured runs.
- Strict A/B used the same integral cache so that input QASM stayed identical.

## Runs

Artifacts:

- Baseline: `artifacts/h6_memory_speed_audit/run_20260703_h6_batch1`
- Candidate A: `artifacts/h6_memory_speed_audit/run_20260703_h6_batch8_strict`
- Candidate B: `artifacts/h6_memory_speed_audit/run_20260703_h6_batch16_strict`

The first `batch8` attempt with an independent integral cache was rejected for
semantic comparison because the QASM hash and raw metrics differed. The strict
runs below copied only the baseline integral cache, not the prepared artifact.

## Summary

| run | batch size | total sec | prepare sec | compile sec | peak tree RSS | raw metrics | stream hash |
|---|---:|---:|---:|---:|---:|---|---|
| baseline | 1 | 134.723 | 115.207 | 19.516 | 1.677 GiB | reference | reference |
| batch8 strict | 8 | 131.922 | 112.069 | 19.853 | 1.635 GiB | match | match |
| batch16 strict | 16 | 131.445 | 111.563 | 19.881 | 1.639 GiB | match | match |

Strict checks that matched for batch8/batch16:

- input QASM hash
- normalized instruction stream hash
- instruction count
- magic-state count
- runtime
- runtime without topology
- code distance

`step_opt.json` byte hash differed between runs, but the normalized stream hash
and raw qret metrics matched exactly. This is acceptable for semantic parity,
but byte identity should not be used as the pass/fail criterion for this option.

## Stage Bottlenecks

Baseline prepare-stage dominant costs:

| stage | elapsed sec | count |
|---|---:|---:|
| RZ helper qret opt | 54.760 | 769 |
| Python streaming inline | 20.761 | 1 |
| basis circuit | 14.964 | 1 |
| qret parse | 2.967 | 1 |
| IR rotation precision rewrite | 2.696 | 1 |
| qret main cleanup | 2.491 | 1 |

With `batch_size=16`, RZ helper qret opt became 49 invocations, but total helper
time stayed about 52.057 sec. The gain is therefore mostly invocation overhead,
not a fundamental reduction in synthesis work.

## Memory Observations

Peak process-tree RSS:

- baseline: 1.677 GiB
- batch8 strict: 1.635 GiB
- batch16 strict: 1.639 GiB

Stage-level subprocess max RSS:

- `qret_parse`: about 1.28 GB
- `qret_opt_main_cleanup`: about 0.97 GB
- `qret_compile`: about 0.94 GB
- individual/batched RZ helper qret calls: about 13 MB

No large transient prepared-step helper JSONs remained:

- `rz_call_cache/rz_helper_*.json`: 0
- `rz_call_cache/main_before_python_inline.json`: 0

## Focused Stage Deep Dive

Artifacts:

- `artifacts/h6_memory_speed_audit/deep_dive/deep_dive_summary.json`
- Probe script: `artifacts/h6_memory_speed_audit/deep_dive_h6.py`

These probes reused the baseline H6 prepared inputs and helper cache. They did
not introduce a production implementation.

### qret parse / main cleanup

The prepared IR contains 771 circuits: `main` plus 770 helper functions. All 770
helpers are directly reachable from `main`, so there is no dead helper-definition
pruning opportunity in this H6 case.

`qret opt` main cleanup on the full IR:

- elapsed: 2.518 sec
- max RSS: 969,360 KB
- input size: 47,387,694 bytes
- output size: 47,387,695 bytes

Skipping main cleanup was tested by running Python inline directly on
`step_ir.json`. The normalized instruction stream matched the cleanup-input
baseline exactly:

- stream hash: `2e0e7d0af425e883e11f523888786b4f68d33191517231d23daeae6a4bd961cd`
- emitted instructions: 2,379,533
- magic states: 513,028
- gate depth: 1,331,019

The direct inline path was 1.156 sec slower than inline from the cleanup output,
but it would avoid the 2.518 sec cleanup subprocess. Net opportunity is therefore
about 1.36 sec on H6, with stage-local peak RSS reduction for the cleanup
subprocess. It is not expected to reduce the whole-run peak while `qret_parse`
remains larger.

### Python inline

| input | reader | elapsed sec | max RSS | stream |
|---|---|---:|---:|---|
| cleanup output | incremental | 20.773 | 104,076 KB | match |
| cleanup output | `json.load` | 20.506 | 382,712 KB | match |
| pre-cleanup `step_ir.json` | incremental | 21.929 | 103,664 KB | match |

The current incremental reader is already doing the important memory reduction:
about 279 MB lower max RSS than the plain `json.load` path. Runtime is nearly
unchanged. Further Python-inline memory work is therefore lower priority unless
the algorithm itself is changed.

### basis circuit generation

The grouped step circuit build took 3.551 sec. The expensive part is basis
conversion. Decomposition repetitions were probed without changing production
code:

| reps | basis sec | QASM bytes | RZ count | QASM hash vs reps=8 |
|---:|---:|---:|---:|---|
| 0 | 0.959 | 4,197,285 | 143,348 | differ |
| 1 | 0.758 | 4,197,285 | 143,348 | differ |
| 2 | 2.194 | 4,200,535 | 143,348 | differ |
| 4 | 7.122 | 6,945,045 | 258,848 | match |
| 8 | 15.153 | 6,945,045 | 258,848 | reference |

`reps=4` produced the same QASM hash, byte size, operation count, and RZ count as
the current `reps=8` setting for H6, while saving about 8.03 sec. This is the
strongest low-risk speed candidate found in this audit. `reps=0/1/2` are not
semantically acceptable for this case.

## Assessment

`SURFACE_CODE_RZ_HELPER_BATCH_SIZE=16` is semantically safe on this H6 strict
A/B and gives a small improvement:

- total elapsed: about 2.4% faster
- prepare elapsed: about 3.2% faster
- peak process-tree RSS: about 2.3% lower

This is not a high-impact optimization for H6. It is a low-risk tuning knob, but
the measured win is small.

Higher-impact candidates to investigate later:

1. Reduce qret parse peak memory. It remains the largest qret-side preparation
   stage in this H6 audit.
2. Consider removing or narrowing qret main cleanup only after broader semantic
   tests. H6 stream parity matched, but the expected speed win is only about
   1.36 sec and it is not a whole-run peak RSS fix.
3. Test lowering basis decomposition repetitions from 8 to 4 across smaller
   strict cases. H6 QASM hash parity matched and the measured saving was about
   8.03 sec.
4. Keep the current Python incremental inline reader. It cuts about 279 MB
   compared with plain `json.load` and does not need immediate rework.
5. Keep strict A/B runs pinned to the same integral cache; otherwise numerical
   input drift can look like a compiler semantic difference.

Conclusion: H6 has limited easy savings left. Existing helper batching can be
considered as a minor tuning option. The most concrete speed candidate is
reducing basis decomposition repetitions from 8 to 4, subject to strict parity
tests. The next substantial memory work should focus on `qret_parse` and IR
handling rather than RZ helper batching.
