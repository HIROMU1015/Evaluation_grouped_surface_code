# Surface-Code Basis Decomposition reps=4 A/B

Date: 2026-07-04

Classification:

- implemented: `SURFACE_CODE_QASM_DECOMPOSE_REPS` default changed from `8` to `4`
- production adopted: yes
- diagnostic only: H4/H5 A/B artifacts under `artifacts/surface_code_basis_decompose_ab/`
- observed: H2 regression, H4/H5 strict A/B, current-production H4/H5 remeasurement
- estimated: none in this report
- theoretical: none in this report

## Scope

- Repository: `/home/abe/Project/Evaluation_grouped_surface_code`
- Start commit: `7c23474f2c9b892111c2d599853367ef7a8928ff`
- Branch: `main`
- Circuit: grouped H-chain, uncontrolled single Trotter step
- PF order: `4th(new_2)`
- Compile mode: `ftqc_compile_topology_qec`
- Compile info output: `summary`
- qret: `build/quration/qret`, version `1.0.2`
- Topology: `third_party/quration/quration-core/examples/data/topology/tutorial.yaml`
- Python: `3.11.0rc1`
- Qiskit: `1.3.0`
- Cold condition: application-cold per run; OS page cache was not dropped

The A/B script uses an independent cache root for every run. It rejects H6 or
larger cases because this task only benchmarks H4/H5.

## Commands

```bash
.venv/bin/python scripts/profile_basis_decomposition_reps.py \
  --output-root artifacts/surface_code_basis_decompose_ab/h4_h5_reps4_vs_8 \
  --cases H4 H5 \
  --reps 8 4 \
  --runs 3 \
  --reset-output

.venv/bin/python scripts/profile_basis_decomposition_reps.py \
  --output-root artifacts/surface_code_basis_decompose_ab/production_reps4_h4_h5 \
  --cases H4 H5 \
  --reps 4 \
  --runs 1 \
  --reset-output

.venv/bin/pytest -q tests/test_surface_code_basis_decomposition.py
```

Artifacts:

- Strict A/B summary: `artifacts/surface_code_basis_decompose_ab/h4_h5_reps4_vs_8/summary.json`
- Production remeasurement: `artifacts/surface_code_basis_decompose_ab/production_reps4_h4_h5/summary.json`
- H2 smoke artifact: `artifacts/surface_code_basis_decompose_ab/smoke_h2/summary.json`

## What `reps` Controls

`SURFACE_CODE_QASM_DECOMPOSE_REPS` is passed to
`_decompose_to_basis(..., decompose_reps=...)` before OpenQASM2 export. It
controls repeated decomposition of Qiskit instructions into the configured
QASM basis gates:

```text
rz, cx, sx, x
```

The canonical setting is now in `src/trotterlib/config.py`. The previous value
is still available:

```bash
SURFACE_CODE_QASM_DECOMPOSE_REPS=8 PYTHONPATH=src python ...
```

## Existing H6 Probe Rechecked

H6 was not rerun. The existing artifact
`artifacts/h6_memory_speed_audit/deep_dive/basis_probe/basis_probe_summary.json`
was rechecked.

| reps | basis sec | QASM bytes | RZ count | QASM SHA-256 | vs reps=8 |
|---:|---:|---:|---:|---|---|
| 4 | 7.121601 | 6,945,045 | 258,848 | `b831142e6985f940370b272993b9173c48045061fa505f6669e727931876d5e8` | match |
| 8 | 15.153203 | 6,945,045 | 258,848 | `b831142e6985f940370b272993b9173c48045061fa505f6669e727931876d5e8` | reference |

`reps=0/1/2` produced different QASM hashes and were not considered candidates.

## H4/H5 Strict A/B Results

Median over 3 independent application-cold runs.

| case | reps | total sec | prepare sec | qret compile sec | process-tree peak RSS | parent peak RSS | qret peak RSS |
|---|---:|---:|---:|---:|---:|---:|---:|
| H4 | 8 | 27.527 | 24.388 | 3.089 | 506,988 KB | 329,480 KB | 201,148 KB |
| H4 | 4 | 26.356 | 23.215 | 3.116 | 506,440 KB | 328,932 KB | 201,424 KB |
| H5 | 8 | 66.477 | 57.712 | 8.733 | 947,052 KB | 490,792 KB | 550,744 KB |
| H5 | 4 | 62.869 | 54.091 | 8.758 | 941,676 KB | 489,272 KB | 550,872 KB |

Direct delta:

| case | total speedup | prepare speedup | qret compile delta | tree RSS delta | qret RSS delta |
|---|---:|---:|---:|---:|---:|
| H4 | 1.171 sec / 4.25% | 1.173 sec / 4.81% | -0.028 sec | -548 KB | +276 KB |
| H5 | 3.608 sec / 5.43% | 3.620 sec / 6.27% | -0.024 sec | -5,376 KB | +128 KB |

The speedup is in preparation, especially basis conversion. qret compile time and
qret RSS are unchanged within measurement noise.

## Correctness Checks

| case | QASM byte-identical | IR hash match | normalized stream hash match | compile-info resource fields match |
|---|---|---|---|---|
| H4 | true | true | true | true |
| H5 | true | true | true | true |

Observed H4 hashes:

- QASM: `f99ec56549b1517633732083d41cb60201c1b23130b66eece9bd562362f9207d`
- IR: `d75a5ee44002fe5a2223641a1fee32eafb6ddc51ded11125e8164fac627d6694`
- normalized stream: `0bbe2b55ad5334a8bb06df5b500a6c05905767237e1fd21766a9fab0ec63e320`
- compile info: `802eb18d3f5d82b53b51b9c31002ec29322d02a3c858502f0e0151ccd4a224ee`

Observed H5 hashes:

- QASM: `aecf66e565a6f47c75fb71b097861d8f12fa0348a25f9fde717275cfd15981a1`
- IR: `295e1f4c0c10af7ce3fb460a8016a74b504795a3601668964d370ea0fa1f0e5a`
- normalized stream: `1b119248b47f65a82ca45b88ac95f9a548814e1606caa0e3c57770f0239c7177`
- compile info: `f0fd579e2528c2b832707e418ab7c464365d294a09d716f86e5e99f38a9dc504`

`step_opt.json` raw byte hash did not match. It also varied across repeated runs
with the same `reps` setting. Therefore the acceptance gate uses raw QASM, raw
parsed IR, normalized instruction stream, and compile-info resource fields. The
normalization rule is: compare the emitted instruction stream summary hash rather
than raw JSON bytes that can contain nonsemantic ordering/path differences.

Selected resource fields were identical, including:

- magic-state count/depth
- runtime with and without topology
- chip cells
- qubit volume
- physical qubits
- code distance
- gate count/depth
- measurement feedback count/depth
- throughput/rate summary fields

Because QASM is byte-identical after setting exported global phase to `0.0`,
global-phase metadata did not introduce an output difference for H4/H5.

## Production Remeasurement

After adopting `reps=4` as the default, H4/H5 were rerun once in the current
production configuration.

| case | total sec | prepare sec | qret compile sec | process-tree peak RSS | parent peak RSS | qret peak RSS |
|---|---:|---:|---:|---:|---:|---:|
| H4 | 26.319 | 23.196 | 3.123 | 514,860 KB | 345,816 KB | 201,060 KB |
| H5 | 62.302 | 53.655 | 8.648 | 943,804 KB | 489,620 KB | 550,796 KB |

Key production stage observations:

| case | basis circuit sec | QASM text sec | qret parse sec / max RSS | qret compile sec / max RSS |
|---|---:|---:|---:|---:|
| H4 | 1.118 | 0.401 | 0.461 / 202,996 KB | 3.086 / 178,348 KB |
| H5 | 3.104 | 1.069 | 1.286 / 549,516 KB | 8.595 / 458,984 KB |

## Decision

`reps=4` is production adopted.

Reasons:

- H4 and H5 QASM are byte-identical to `reps=8`.
- Parsed IR hashes match.
- Normalized instruction stream hashes match.
- Compile-info resource fields match.
- H2 regression test exists.
- `SURFACE_CODE_QASM_DECOMPOSE_REPS=8` override is preserved.
- H4/H5 elapsed improved by 4.25% and 5.43% respectively.
- Peak RSS did not show a material regression.

Residual risk:

- This is an observed H2/H4/H5 plus existing H6 artifact result, not a proof for
  every possible future circuit. Controlled PF and full QPE were not included in
  this A/B.
