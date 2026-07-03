# qret InstQueue Routing Profile

Date: 2026-07-04

Classification:

- diagnostic only: default-off C++ instrumentation was used locally
- implemented: no production qret change
- production adopted: none
- evaluated and rejected: low-risk InstQueue candidate 1/2/3 for the observed H5 path
- observed: H5 InstQueue counters and timings
- unresolved: H4 did not emit an InstQueue profile JSON

## Scope

- Repository: `/home/abe/Project/Evaluation_grouped_surface_code`
- qret source inspected/temporarily instrumented:
  `third_party/quration/quration-core/src/qret/target/sc_ls_fixed_v0/inst_queue.*`
- External quration repository: read-only, not modified
- Circuit: grouped H-chain, uncontrolled single Trotter step
- PF order: `4th(new_2)`
- Compile mode: `ftqc_compile_topology_qec`
- Production basis setting during profile: `SURFACE_CODE_QASM_DECOMPOSE_REPS=4`

The instrumentation was default-off and enabled only with:

```bash
QRET_PROFILE_INST_QUEUE=1
QRET_PROFILE_INST_QUEUE_PATH=/home/abe/Project/Evaluation_grouped_surface_code/artifacts/surface_code_basis_decompose_ab/instqueue_profile_h4_h5/inst_queue_profile.json
```

The diagnostic source edits are not part of production and should not remain in
committed qret source.

## Commands

```bash
./scripts/build_qret.sh

QRET_PROFILE_INST_QUEUE=1 \
QRET_PROFILE_INST_QUEUE_PATH=/home/abe/Project/Evaluation_grouped_surface_code/artifacts/surface_code_basis_decompose_ab/instqueue_profile_h4_h5/inst_queue_profile.json \
.venv/bin/python scripts/profile_basis_decomposition_reps.py \
  --output-root artifacts/surface_code_basis_decompose_ab/instqueue_profile_h4_h5 \
  --cases H4 H5 \
  --reps 4 \
  --runs 1 \
  --reset-output
```

Artifacts:

- H4/H5 run summary:
  `artifacts/surface_code_basis_decompose_ab/instqueue_profile_h4_h5/summary.json`
- H5 InstQueue profile:
  `artifacts/surface_code_basis_decompose_ab/instqueue_profile_h4_h5/inst_queue_profile.json`
- H4-only rerun summary:
  `artifacts/surface_code_basis_decompose_ab/instqueue_profile_h4_final/summary.json`

The combined H4/H5 command produced the profile from the final H5 qret compile
process. A separate H4-only rerun compiled successfully but did not emit a
profile JSON, so the detailed hotspot ranking below is H5-only.

## H5 Profile

Observed H5 elapsed/RSS with instrumentation:

| case | total sec | prepare sec | qret compile sec | process-tree peak RSS | qret peak RSS |
|---|---:|---:|---:|---:|---:|
| H5 | 62.433 | 53.670 | 8.764 | 947,596 KB | 550,844 KB |

InstQueue counters:

| item | value |
|---|---:|
| `Peek()` calls | 2,248 |
| `Peek()` requested instructions | 2,999,000 |
| `Peek()` actual instructions | 2,997,088 |
| `CalculateWeight()` calls | 2,248 |
| inverse-depth calls | 2,248 |
| runnable rebuild calls | 2,248 |
| `SetBeat()` calls | 2,367,479 |
| `SetBeat()` released reserved entries | 0 |
| `IsReserved()` calls | 0 |
| `InsertAfter()` calls | 0 |
| `Replace()` calls | 0 |
| qmap/cmap full-scan entries | 0 / 0 |
| max queue nodes | 3,999 |
| max runnable entries | 14 |
| max reserved entries | 0 |

Hotspot ranking inside the measured InstQueue hooks:

| rank | area | total sec |
|---:|---|---:|
| 1 | `Peek()` total | 1.114 |
| 2 | runnable set rebuild inside `Peek()` | 0.617 |
| 3 | `CalculateWeight()` | 0.617 |
| 4 | inverse-depth DFS | 0.616 |
| 5 | `SetBeat()` | 0.029 |
| 6 | `IsReserved()` / `InsertAfter()` / `Replace()` | 0.000 |

The measured routing-side time is therefore concentrated in repeated
`Peek()`-window processing, inverse-depth weight calculation, and runnable set
rebuild. Membership checks and qmap/cmap scans are not hot in this H5 path.

## Candidate Evaluation

### Candidate 1: `SetBeat()` erase iterator

Classification: evaluated and rejected for this pass.

Rationale:

- `SetBeat()` was called 2,367,479 times, but total measured time was only
  0.029 sec.
- `set_beat_released` was `0`, so the erase branch was not exercised in the H5
  profile.
- Replacing `erase` + `begin()` with the erase return iterator would not affect
  the observed H5 run and would not be a measurable speedup.
- Because the branch was not exercised, an implementation would require a
  separate targeted test before production adoption.

Decision: not implemented.

### Candidate 2: reserved membership O(1) helper

Classification: evaluated and rejected for this pass.

Rationale:

- `IsReserved()` calls were `0`.
- `max_reserved` was `0`.
- There is no observed H5 benefit from adding an auxiliary membership set.

Decision: not implemented.

### Candidate 3: reverse index for qmap/cmap scans

Classification: evaluated and rejected for this pass.

Rationale:

- `InsertAfter()` calls were `0`.
- `Replace()` calls were `0`.
- qmap/cmap scan entries were `0`.
- A reverse index would add synchronization complexity without a measured H5
  benefit in this path.

Decision: not implemented.

## Correctness Status

No production qret change was adopted, so routing order and resource metrics are
unchanged by this report.

The diagnostic H5 run used the same production inputs as the `reps=4`
remeasurement. It is not used as a correctness gate because the instrumentation
only records timings and counters.

## Recommended Next qret Speed Candidate

The next single candidate should be a trace-only study of `Peek()` weight
recalculation and runnable rebuild, not an immediate algorithm change.

Reason:

- It is the only observed InstQueue cost above 1 second in H5.
- Changing weight calculation timing, tie-breaks, or runnable comparator is
  high risk.
- A safe next step is to add a debug trace hash for selected instruction index,
  runnable selection, beat assignment, inserted routing instruction, and final
  instruction stream. Only after the trace is stable should an incremental or
  cached weight calculation be evaluated.

Unresolved:

- H4-only qret compile did not emit InstQueue counters. This should be
  investigated only if future work requires H4-level InstQueue hotspot evidence;
  it does not change the H5 candidate decisions above.
