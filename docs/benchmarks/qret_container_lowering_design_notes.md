# qret Container, Operand, and Lowering Design Notes

Date: 2026-07-04

Classification:

- implemented: no new production implementation in this report
- unimplemented: MachineBasicBlock container replacement, operand API rewrite, streaming lowering
- observed: source-level audit of current qret implementation and existing reports
- theoretical: memory-shape discussion below
- unresolved: exact implementation choice and trace-equivalence tests

## Scope

This note records the next candidates after the low-risk H4/H5 work. It does
not change production behavior.

Relevant current source:

- `third_party/quration/quration-core/src/qret/codegen/machine_function.h`
- `third_party/quration/quration-core/src/qret/codegen/machine_function.cpp`
- `third_party/quration/quration-core/src/qret/target/sc_ls_fixed_v0/lowering.cpp`
- `third_party/quration/quration-core/src/qret/target/sc_ls_fixed_v0/pipeline_state.cpp`
- `third_party/quration/quration-core/src/qret/target/sc_ls_fixed_v0/memory_profile_stats.cpp`

## MachineBasicBlock

Current shape:

```text
MachineFunction
  std::list<MachineBasicBlock>

MachineBasicBlock
  std::list<std::unique_ptr<MachineInstruction>> instructions_
  std::map<const MachineInstruction*, ConstIterator> inverse map
  std::vector<MachineBasicBlock*> predecessors_
  std::vector<MachineBasicBlock*> successors_
```

Why the current structure is reasonable:

- `MachineInstruction*` remains stable while instructions are inserted or erased.
- list iterators remain stable for `InsertBefore`, `InsertAfter`, and `Erase`.
- existing routing/simulation code can keep instruction pointers without moving
  objects.
- inverse map gives pointer-to-iterator lookup when list position is needed.
- block predecessor/successor vectors preserve a generic CFG shape even though
  SC_LS_FIXED_V0 mostly uses a single linear block.

Why `std::vector<std::unique_ptr<MachineInstruction>>` is not a safe drop-in:

- inserting in the middle invalidates indices after the insertion point.
- erasing shifts elements.
- a vector reallocation invalidates iterators and references to `unique_ptr`
  elements.
- preserving pointer stability is not enough if users also depend on stable
  iterator/list position.

Known memory components from the current estimator:

- instruction object bytes
- list node bytes: one `unique_ptr` plus two list links per instruction
- operand list node bytes
- inverse map nodes
- basic block list nodes
- predecessor/successor vectors
- metadata bytes

### Candidate comparison

| candidate | expected benefit | main risk | status |
|---|---|---|---|
| intrusive list | removes separate list node allocation and can keep stable links | requires every instruction to carry links and changes ownership model | unimplemented |
| slab/arena object + lightweight link | reduces allocator overhead and can keep stable pointers | erase/lifetime handling and polymorphic destruction must be exact | unimplemented |
| segmented vector | improves locality without moving old segments | middle insertion/erase and stable iteration semantics need an adapter | unimplemented |
| chunked stable storage | good fit if appends dominate and erases are rare | routing insert/erase behavior must be measured per pass | unimplemented |
| stable ID + index table | compact handles and easier serialization | broad API change; every pointer-based user must migrate | unimplemented |

Recommended next step:

1. Add a default-off trace that records instruction selection/order hashes across
   lowering, routing, and simulation.
2. Count actual `InsertBefore`, `InsertAfter`, and `Erase` operations by pass.
3. Only then prototype a chunked stable storage or intrusive list adapter.

An arena-only allocation can reduce allocation overhead, but it does not remove
list links, operand containers, or inverse-map nodes. That is why it is expected
to be a small improvement unless the container shape is also changed.

## Operand API

Current instruction classes expose generic operand containers such as:

- `QTarget()`
- `Condition()`
- `CDepend()`
- `CCreate()`
- `MTarget()`
- `ETarget()`
- `EHTarget()`
- `Ancilla()`

This is flexible and simple for serialization, but it can materialize list-like
containers even for instructions that have zero or one operand in a category.

Why the older compact-operand idea lost effect:

- compatibility accessors still had to produce the old list-style view.
- if that compatibility list is materialized per instruction, the memory win is
  consumed by the compatibility layer.
- serialization and older passes still want iterable ranges.

Lower-risk future API shape:

- singleton operand: direct scalar accessor
- fixed-size operand: fixed array or small inline array
- variable operand: `span`/range over owned storage
- compatibility range: generated lazily and not stored per instruction
- serialization: build temporary JSON/range only at the serialization boundary

Correctness gate for any operand change:

- byte-level pipeline-state compatibility where output is enabled
- final instruction stream hash match
- compile-info resource fields match
- targeted tests for Allocate/DeAllocate, factory instructions, conditions,
  CCreate, magic-state instructions, and ancilla counts

## Streaming Lowering

Current lowering reads qret IR objects and emits SC_LS_FIXED_V0 machine
instructions into `MachineBasicBlock` with `EmplaceBack`.

Important distinction:

- freeing the source IR only after machine construction does not reduce the peak
  if the peak occurs while IR and MachineFunction are both alive.
- lowering by block can reduce lifetime only if later passes no longer need
  source IR pointers or whole-function IR analyses.
- qret pipeline-state JSON is a separate persistence/visualization/debug format;
  skipping it avoids another large materialization but does not remove the
  MachineFunction itself.

Future implementation levels:

| level | idea | risk |
|---|---|---|
| JSON DOM lifetime shortening | parse/load and release earlier | low if hashes match |
| source IR lifetime shortening | release IR after lowering | medium; current passes may retain IR pointers |
| block-consuming lowering | lower one block and discard source block | medium/high; requires pass audit |
| direct lowering without quration IR | parse OpenQASM directly to MachineFunction | high; broad semantic surface |

Recommended next step:

Prototype lifetime tracing first, not a rewrite. The trace should mark:

- IR JSON load start/end
- qret IR object construction
- machine instruction construction high-water
- routing start/end
- pipeline-state build start/end if enabled

Then choose the first phase where two large structures are simultaneously alive.

## Process Isolation

Existing report:

- `docs/benchmarks/surface_code_process_isolation_reproducibility.md`

Result:

- same-artifact compile in a child process was semantically equal.
- independent prepare in a child process diverged before compile.
- first divergent stage was `integral_scf_and_transform`.
- root cause was low-bit floating/numeric drift in independently recomputed
  PySCF/MO integrals, not qret compile isolation itself.

Future process-isolation requirements:

- prepare child must write a complete immutable artifact.
- child exit must happen before qret child starts if the goal is process-tree
  peak reduction.
- qret single-process peak will not be reduced by parent/child isolation.
- artifact byte-level parity is required before using this as a production
  memory optimization.

## One Recommended Next Candidate

Do not start with a full MachineBasicBlock rewrite. The best next candidate is a
read-only lifetime and operation-count trace for MachineFunction construction and
routing.

Reason:

- it is lower risk than changing containers.
- it identifies whether the next peak is object storage, operand storage,
  inverse map rebuild, or routing temporary state.
- it provides the trace hashes needed before a container or operand API change.
