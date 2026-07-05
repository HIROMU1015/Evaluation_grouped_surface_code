# Major Opportunity Prioritization

Date: 2026-07-05

Status:

- major opportunity scan: partially complete
- purpose: identify the largest remaining optimization targets before starting
  another implementation
- new large-case execution in this pass: none
- sources: current source, existing H5/H6/H9/H10 artifacts, and existing qret
  memory reports

## Current Context

Current production already includes the major low-risk wins found so far:

- basis decomposition default: `SURFACE_CODE_QASM_DECOMPOSE_REPS=4`
- compile-info summary output
- pipeline-state output skip
- compact dependency graph
- magic path interning
- inverse-map release after routing
- Python streaming inline path

The remaining large opportunities split into two different goals:

- elapsed reduction
- peak RSS reduction

They should not be treated as the same target.

## Observed Scaling Snapshot

| case | total sec | prepare sec | compile sec | largest observed qret parse RSS | qret compile RSS |
|---|---:|---:|---:|---:|---:|
| H5 | 62.302 | 53.655 | 8.648 | 549,516 KB | 458,984 KB |
| H6 | 134.723 | 115.207 | 19.516 | 1,281,972 KB | 986,420 KB |
| H9 | 742.387 | 623.983 | 118.377 | 8,021,632 KB | 5,577,192 KB |
| H10 | 1143.250 | 954.260 | 188.990 | 12,849,652 KB | 8,711,112 KB |

The H9/H10 values are observed historical artifacts, not new runs from this
pass.

## Elapsed Opportunities

### Rank 1: RZ Helper qret Optimization

Classification: observed hotspot, not yet solved.

Aggregate qret helper optimization time:

| case | unique helper count | qret helper opt aggregate sec |
|---|---:|---:|
| H5 | 404 | 28.737 |
| H6 | 769 | 54.760 |
| H9 | 3,629 | 258.748 |
| H10 | 5,435 | 387.328 |

This is the largest remaining elapsed target. Prior batching reduced invocation
count but did not materially reduce H6 helper work, so the next question is not
just process startup. The likely target is the work inside each helper qret opt
or an equivalent batch/in-process helper path that preserves byte/semantic
parity.

Next diagnostic before implementation:

- profile a small representative helper set and split time into qret parse,
  optimization passes, synthesis, and JSON serialization
- compare helper output hashes against the current path
- keep the benchmark at H5/H6 scale; do not use H9/H10 for exploration

### Rank 2: Python Streaming Inline

Classification: observed runtime hotspot; memory already improved.

| case | python streaming inline sec |
|---|---:|
| H5 | 9.569 |
| H6 | 20.761 |
| H9 | 129.295 |
| H10 | 198.490 |

The incremental reader already reduced memory versus `json.load`, but runtime is
large at H9/H10. This is a good elapsed target after helper opt because it is a
single Python stage with stable semantic hashes.

Next diagnostic:

- add lightweight counters for emitted instructions, JSON tokens/objects, and
  replacement lookups
- identify whether time is parser I/O, object construction, override lookup, or
  output serialization

### Rank 3: Basis Circuit / QASM Generation

Classification: partially optimized by `reps=4`.

| case | basis circuit sec | QASM text sec | build step circuit sec |
|---|---:|---:|---:|
| H5 | 3.104 | 1.069 | 1.553 |
| H6 | 14.964 | 2.289 | 3.520 |
| H9 | 92.570 | 14.519 | 28.561 |
| H10 | 144.892 | 21.562 | 47.372 |

`reps=8 -> 4` was adopted and remains the concrete win here. Further reductions
may exist, but the next candidates are less obvious than helper opt or Python
inline.

### Rank 4: qret Compile Routing / Simulation

Classification: important, but current low-risk InstQueue candidates were not
the main cost.

H5 qret-only historical profile showed routing around 13.2 sec and compile-info
around 3.3 sec. The recent InstQueue profile showed only about 1.1 sec in
`Peek()` hooks on H5, so `Peek()` alone is not enough to explain the full routing
cost.

Next diagnostic:

- add trace hashes first: selected instruction, beat assignment, inserted route
  instruction, and final stream
- profile simulator/path-search costs separately from `InstQueue::Peek()`

## Peak RSS Opportunities

### Rank 1: qret Parse / IR JSON Generation

Classification: largest observed memory hotspot.

qret parse peak is higher than qret compile peak in current large artifacts:

| case | qret parse max RSS | qret compile max RSS | parse over compile |
|---|---:|---:|---:|
| H5 | 549,516 KB | 458,984 KB | +90,532 KB |
| H6 | 1,281,972 KB | 986,420 KB | +295,552 KB |
| H9 | 8,021,632 KB | 5,577,192 KB | +2,444,440 KB |
| H10 | 12,849,652 KB | 8,711,112 KB | +4,138,540 KB |

This should be the first memory target. It is earlier than routing and dominates
process-tree peak for large cases.

Likely area:

- OpenQASM input parsing
- IR object construction
- IR JSON DOM/string serialization
- simultaneous input/output buffers

Next diagnostic:

- add qret parse high-water markers equivalent to the compile backend markers
- measure H4/H5 first, then H6 only if needed and safe
- identify whether the peak is parser AST, quration IR, JSON serialization, or
  output buffering

### Rank 2: qret Compile MachineFunction Live Set

Classification: observed peak-effective area, partially optimized.

Current H5 high-water evidence says the qret compile peak forms before the
routing main loop, around MachineFunction construction and routing setup. This
means optimizations after routing, such as inverse-map release, can reduce live
allocator bytes without moving VmHWM.

Peak-relevant H5 component estimates:

| component | H5 estimate |
|---|---:|
| instruction objects | 137.8 MB |
| operand containers | 56.4 MB |
| instruction list nodes | 34.3 MB |
| compact DepGraph payload | 59.4 MB |
| metadata | 22.9 MB |
| routing temporary | 20.2 MB |

The prior arena-only and old compact-operand variants did not pass adoption
gates. A larger redesign may still be worthwhile, but only after qret parse is
split because parse is currently the larger memory peak.

### Rank 3: Python Parent RSS

Classification: not first priority.

H5 parent RSS is substantial, but large-case process-tree peak is dominated by
qret child processes. Parent-side work should not outrank qret parse unless a
specific parent object is shown to overlap the qret child peak.

## Recommended Order

1. Memory first: instrument qret parse high-water.
2. Elapsed first: profile RZ helper qret opt internals on a small helper sample.
3. Then optimize Python streaming inline if helper opt is not tractable.
4. Only after parse/helper data, return to MachineFunction container or routing
   changes.

This order targets the largest observed opportunities instead of the most
convenient code paths.

## Current Conclusion

The largest remaining memory opportunity is qret parse / IR JSON generation.

The largest remaining elapsed opportunity is RZ helper qret optimization.

`InstQueue::Peek()` and MachineFunction container work are still relevant, but
they are not the first targets if the goal is to start with the biggest likely
impact.

## Probe Results

Date: 2026-07-05

Scope:

- production implementation change: none
- large-case execution: none
- measured cases: existing H5/H6 artifacts only
- temporary output location: `/tmp/qret_major_probe_*`

### Parse AST Early Release Probe

Experimental flag:

- `QRET_PARSE_RELEASE_AST_BEFORE_SAVE=1`

Observed result:

| case | mode | parse max RSS | elapsed | normalized IR JSON |
|---|---|---:|---:|---|
| H5 | baseline | 549,624 KB | 1.24 sec | equal after `metadata.created_at` normalization |
| H5 | release AST before save | 549,552 KB | 1.25 sec | equal after `metadata.created_at` normalization |
| H6 | baseline | 1,281,176 KB | 2.93 sec | equal after `metadata.created_at` normalization |
| H6 | release AST before save | 1,281,780 KB | 2.93 sec | equal after `metadata.created_at` normalization |

The flag reduces live heap before JSON DOM construction:

| case | baseline `mallinfo2_uordblks_kb` after JSON DOM | candidate after JSON DOM | live heap delta |
|---|---:|---:|---:|
| H5 | 218,099 KB | 170,308 KB | -47,791 KB |
| H6 | 505,787 KB | 393,881 KB | -111,906 KB |

However, it does not reduce process peak RSS because the high-water mark is
already reached during OpenQASM AST construction. This means AST early release
is useful evidence but not the primary memory optimization. A peak-effective
parse optimization needs to reduce the parser/AST construction peak itself, or
avoid the full OpenQASM parse path for generated surface-code QASM.

### Parallel RZ Helper qret Opt Probe

Prototype:

- keep the existing helper semantics
- split helpers into batch size 64
- run helper qret opt batches in parallel
- run main cleanup and Python inline exactly once after helper validation

H4 `2nd` same-input validation:

| mode | helper count | helper qret invocation count | effective workers | total helper pipeline wall | output parity |
|---|---:|---:|---:|---:|---|
| legacy batch1/worker1 | 65 | 65 | 1 | 6.061 sec | reference |
| candidate batch64/worker8 | 65 | 2 | 2 | 5.584 sec | equal after `metadata.created_at` normalization |

The fixed-input validation used the same H4 `2nd` `step_ir.json` and
`rz_call_cache_metadata.json` for both modes. The optimized IR JSON differed
only in `metadata.created_at`; after that normalization it was identical. The
instruction summary also matched exactly:

- normalized instruction stream hash:
  `97731002e80de41ff4e1cc9db4ce1390bd51c932f81e660ec3d63e632a7ff9ca`
- scheduled instruction count: `84,148`
- emitted instruction count: `84,149`
- `T` count: `19,848`
- gate depth: `48,900`

A separate full H4 `2nd` end-to-end run also matched the compile/resource
metrics numerically: `gate_count=121,064`, `gate_depth=46,124`,
`num_physical_qubits=32,448`, `runtime=90,972`, `qubit_volume=1,055,940`,
`code_distance=13`, and `step_magic_state_count=19,848`. The only metric-file
differences were elapsed time, hash fields, and cache metadata.

H5 result:

| mode | helper count | helper qret invocation count | helper qret wall | helper qret elapsed sum | total helper pipeline wall | output parity |
|---|---:|---:|---:|---:|---:|---|
| current serial batch64 probe | 404 | 7 serial | 27.151 sec | 27.151 sec | 41.434 sec | normalized JSON equal |
| parallel batch64 prototype | 404 | 7 parallel | 4.348 sec | 27.177 sec | 17.820 sec | normalized JSON equal |

H6 result:

| mode | helper count | helper qret invocation count | helper qret wall | helper qret elapsed sum | total helper pipeline wall | output parity |
|---|---:|---:|---:|---:|---:|---|
| current serial batch1 artifact | 769 | 769 serial | about 54.760 sec | about 54.760 sec | not isolated in this probe | existing production output |
| parallel batch64 prototype | 769 | 13 parallel | 4.339 sec | 51.719 sec | 33.807 sec | normalized JSON equal to existing H6 `step_opt.json` |

Per-helper-batch qret memory stayed small in the prototype:

- H5 helper batch max RSS: about 13.6 MB per qret subprocess
- H6 helper batch max RSS: about 13.6 MB per qret subprocess

The later serial stages remain visible:

| case | main cleanup wall | main cleanup max RSS | Python inline wall |
|---|---:|---:|---:|
| H5 parallel prototype | 1.094 sec | 418,908 KB | 9.095 sec |
| H6 parallel prototype | 2.418 sec | 969,284 KB | 20.728 sec |

Conclusion:

- RZ helper qret opt parallelism is the strongest near-term elapsed candidate.
- It preserves final normalized IR JSON in the H5/H6 probes.
- It trades a small amount of concurrent memory for large wall-clock reduction.
- The production implementation now uses bounded worker count, deterministic
  result merge order, robust per-cache-entry locking, and unit coverage for
  output parity under parallel misses.

Production defaults:

- `SURFACE_CODE_RZ_HELPER_BATCH_SIZE=64`
- `SURFACE_CODE_RZ_HELPER_PARALLEL_WORKERS=8`

### Updated Priority

1. Validate bounded parallel RZ helper optimization in end-to-end H5 if the next
   goal is final adoption evidence.
2. For memory reduction, do not spend production effort on AST early release
   alone; instrument and redesign the qret parse/AST construction path instead.
3. After helper parallelism, Python inline remains the next elapsed target.
