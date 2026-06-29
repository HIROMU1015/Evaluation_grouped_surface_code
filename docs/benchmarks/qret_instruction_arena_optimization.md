# qret Instruction Arena Allocation Evaluation

## Execution Limits

- largest measured case: `H5`
- H6 executed: `False`
- H7 executed: `False`
- H8 executed: `False`
- H9 executed: `False`
- H9 memory: not measured in Phase A.

## Production Configuration

- production default after Phase A: `legacy`
- candidate switch: `QRET_INSTRUCTION_ALLOCATION=legacy|arena`
- magic path storage: `interned`
- non-path operands: legacy containers
- compile-info output: `summary`
- summary TimeSeries: `legacy_timeseries`
- DepGraph: `compact`
- inverse-map construction: default `eager`
- inverse-map release after routing: enabled
- pipeline-state output: skipped

## Source Audit

- SC_LS_FIXED_V0 has 24 concrete instruction enum values and all concrete instruction factories return `std::unique_ptr<Derived>(new Derived(...))`.
- `FromJson` delegates to those factories, so deserialization and pipeline-state load use the same allocation path.
- `MachineBasicBlock` remains `std::list<std::unique_ptr<MachineInstruction>>`; list-node storage, iterator stability, and ownership semantics are unchanged.
- `InsertBefore`, `InsertAfter`, `EmplaceBack`, and `Erase` still move or destroy `unique_ptr` nodes; arena mode changes only the object allocation backing `new Derived(...)`.
- Virtual dispatch, `dynamic_cast`/`Cast` style use, instruction classes, operands, metadata, serialization, and routing algorithms are unchanged.
- Arena ownership is MachineFunction-scoped. Routing allocations occur under the same compile-scope arena, and chunks are freed when the MachineFunction is destroyed.
- Erased instructions still run their destructor through `unique_ptr`; arena `operator delete` records the delete and defers raw memory reuse until MachineFunction teardown.
- Arena mode cannot remove object bodies, vptrs, padding, operand containers, or instruction list nodes.

## Allocation Model

| item | value | classification |
| ---- | ----: | -------------- |
| H5 legacy allocation count model | 23,985,152 bytes | theoretical |
| H5 arena allocation count | 1,499,072 | observed |
| H5 arena requested bytes | 144,451,120 | observed |
| H5 arena used bytes | 150,792,216 | observed |
| H5 arena reserved bytes | 150,994,944 | observed |
| H5 arena internal fragmentation bytes | 6,341,096 | observed |
| H5 arena chunks | 144 | observed |

## H4 Correctness

- raw and normalized metric parity: `True`
- semantic projection parity: `True`
- canonical instruction stream hash was not emitted by the production qret binary; opcode counts, instruction count, raw metrics, normalized metrics, DepGraph counts, schema, and pipeline-state skip marker were compared instead.

## H5 A/B Results

| variant | runs | median qret peak KB | min | max | peak variation % | median elapsed s | elapsed variation % | median construction ms | median routing ms | median compile-info ms |
| ------- | ---: | -------------------: | --: | --: | ---------------: | ---------------: | ------------------: | ---------------------: | ----------------: | ---------------------: |
| legacy | 2 | 434,932 | 434,932 | 434,932 | 0.000 | 18.916 | 1.348 | 756 | 13,247 | 3,348 |
| arena | 2 | 424,116 | 423,872 | 424,360 | 0.115 | 18.478 | 0.994 | 743 | 13,212 | 2,948 |

## Gate Decision

- arena status: `rejected`
- H5 median peak reduction KB: `10,816`
- H5 median peak reduction %: `2.487`
- elapsed regression %: `-2.314`
- every arena run below legacy range: `True`
- peak gate passed: `False`
- elapsed gate passed: `True`

## Metric Parity Details

| comparison | raw equal | normalized equal | semantic projection equal |
| ---------- | --------- | ---------------- | ------------------------- |
| h4_4th_new2:arena:run_1 | True | True | True |
| h4_4th_new2:legacy:run_1 | True | True | True |
| h5_4th_new2:arena:run_1 | True | True | True |
| h5_4th_new2:arena:run_2 | True | True | True |
| h5_4th_new2:legacy:run_1 | True | True | True |
| h5_4th_new2:legacy:run_2 | True | True | True |

## Conclusion

- Phase A evaluated exactly one instruction-storage candidate: MachineFunction-scoped instruction arena allocation.
- It did not implement instruction list-node removal, operand API redesign, inverse-map compactization, instruction-count reduction, flat/tagged instruction representation, or chunk/stream routing.
- Production default changes only if the gate passes; otherwise `legacy` remains the default and `arena` remains an explicit candidate mode.
