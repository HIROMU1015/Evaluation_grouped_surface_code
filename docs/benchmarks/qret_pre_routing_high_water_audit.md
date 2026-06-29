# qret Pre-Routing High-Water Audit

## Execution Limits

- largest measured case: `H5`
- H6 executed: `False`
- H7 executed: `False`
- H8 executed: `False`
- H9 executed: `False`
- H9 memory: estimated from observed H4/H5 values, not measured.

## Production Configuration

- magic path storage: `interned`
- non-path operands: legacy containers
- compile-info output: `summary`
- summary TimeSeries: `legacy_timeseries`
- DepGraph: `compact`
- inverse-map construction: default `eager`; explicit `lazy` diagnostic mode remains available
- inverse-map release after routing: enabled
- pipeline-state output: skipped

## Instrumentation Design

- `QRET_PROFILE_HIGH_WATER=1` enables bounded high-water markers only when `QRET_RSS_PROFILE_JSONL` is also set.
- `during_machine_function_construction` samples at 100,000 emitted machine-instruction intervals.
- Process-tree sampling keeps at most `250,000` rows in memory per run.
- Process markers include `VmRSS`, `VmHWM`, `VmSize`, `VmData`, `RssAnon`, `RssFile`, `ru_maxrss`, and glibc `mallinfo2` fields when available.
- Diagnostic `malloc_trim(0)` is controlled by `QRET_RSS_DIAGNOSTIC_TRIM_STAGE` and is not a production path.

## Source Lifetime Audit

| object | ownership/scope | live overlap conclusion |
| ------ | --------------- | ----------------------- |
| input JSON stream/buffer | `std::ifstream` inside `LoadFunctionFromIR` | no full explicit text buffer is retained after function return |
| parsed JSON DOM | local `qret::Json j` in `LoadFunctionFromIR` | overlaps with source IR `IRContext` during `LoadJson`, then is destroyed before lowering |
| source IR representation | `IRContext context` in `RunCompilation` | remains live while lowering and passes run because `MachineFunction` keeps an IR pointer |
| MachineFunction | local `mf` in `RunCompilation` | live through mapping/routing/compile-info and process exit |
| lowering temporary | local lowering contexts | not retained after `Lowering::RunOnMachineFunction` |
| mapping temporary | local `QubitGraph`/mapping structures | not retained after mapping pass exit |
| routing temporary | `InstQueue`/simulator/search state | destroyed before `routing_after_temporary_destroy` |
| inverse map | `MachineBasicBlock::mp_` | eager builds before routing; release clears maps after routing; lazy can avoid construction |
| DepGraph | local in `CompileInfoWithoutTopology` | compact graph is local to depth calculation and destroyed after pass |
| serialization buffer | compile-info JSON DOM in `DumpCompileInfo` | summary mode is small; pipeline-state serialization is skipped |

## Stage Timeline

| logical stage | observed stage | VmRSS KB | VmHWM KB | uordblks KB | fordblks KB | VmRSS-uord KB |
| ------------- | -------------- | -------: | -------: | ----------: | ----------: | -----------: |
| process_start | process_start | 7,168 | 7,168 | 216 | 47 | 6,952 |
| before_input_json_read | before_input_json_read | 7,424 | 7,424 | 238 | 25 | 7,186 |
| after_input_json_read | after_input_json_read | 7,424 | 7,424 | 246 | 17 | 7,178 |
| after_json_parse_or_dom_build | after_json_parse_or_dom_build | 226,076 | 239,616 | 202,917 | 98 | 23,159 |
| before_machine_function_construction | before_machine_function_construction | 379,568 | 412,444 | 145,048 | 227,371 | 234,520 |
| during_machine_function_construction | during_machine_function_construction | 415,920 | 415,920 | 408,982 | 137 | 6,938 |
| after_machine_function_construction | after_machine_function_construction | 434,608 | 434,608 | 427,747 | 116 | 6,861 |
| before_lowering | before_lowering | 379,568 | 412,444 | 145,049 | 227,370 | 234,519 |
| after_lowering | after_lowering | 434,608 | 434,608 | 427,747 | 116 | 6,861 |
| before_mapping | before_mapping | 434,608 | 434,608 | 282,931 | 144,932 | 151,677 |
| after_mapping | after_mapping | 434,608 | 434,608 | 282,932 | 144,931 | 151,676 |
| before_validation | before_validation | 434,608 | 434,608 | 282,951 | 144,912 | 151,657 |
| after_validation | after_validation | 434,608 | 434,608 | 282,951 | 144,912 | 151,657 |
| routing_entry | routing_entry_from_pass_manager | 434,608 | 434,608 | 282,932 | 144,931 | 151,676 |
| routing_after_setup | routing_after_setup | 434,864 | 434,864 | 377,611 | 50,252 | 57,253 |
| routing_main_loop_peak | routing_main_loop_peak | 434,864 | 434,864 | 377,612 | 50,251 | 57,252 |
| routing_before_inverse_map_release | routing_before_inverse_map_release | 434,864 | 434,864 | 388,032 | 39,831 | 46,832 |
| routing_after_inverse_map_release | routing_after_inverse_map_release | 434,864 | 434,864 | 294,344 | 133,519 | 140,520 |
| before_compile_info | before_calc_info_without_topology | 434,864 | 434,864 | 294,244 | 133,619 | 140,620 |
| compile_info_peak | calc_info_with_topology_after_summary_stats_store | 434,864 | 434,864 | 416,222 | 11,641 | 18,642 |
| after_compile_info | after_calc_info_with_topology | 434,864 | 434,864 | 294,256 | 133,607 | 140,608 |
| before_serialization | before_serialization | 434,864 | 434,864 | 294,272 | 133,591 | 140,592 |
| after_serialization | dump_compile_info_after_json_stream_write | 434,864 | 434,864 | 294,311 | 133,552 | 140,553 |
| before_process_exit | before_process_exit | 434,864 | 434,864 | 297 | 427,566 | 434,567 |

## H4 Correctness

- raw and normalized metric parity across H4 measured variants: `True`
- profile-off variants produce compile metrics without qret RSS profile rows.
- profile-on eager/lazy variants keep summary compile-info schema and pipeline-state skip behavior.

## H5 Observed Memory Timeline

- eager qret peak RSS KB: `434,864`
- eager first max VmHWM stage: `routing_after_splitter_construct`
- eager first max VmRSS stage: `routing_after_splitter_construct`
- routing entry VmHWM KB: `434,608`

## Eager vs Lazy

| variant | qret peak KB | first max VmHWM stage | inverse entries | inverse bytes | routing-before uord KB | routing-after uord KB |
| ------- | ------------: | --------------------- | --------------: | ------------: | ---------------------: | --------------------: |
| eager | 434,864 | routing_after_splitter_construct | 1,499,072 | 59,962,880 | 388,032 | 294,344 |
| lazy | 434,816 | routing_after_splitter_construct | 0 | 0 | 294,339 | 294,344 |

## Allocator Retention Analysis

- The report compares `VmRSS`, `VmHWM`, `uordblks`, `fordblks`, and `VmRSS-uordblks` at every requested stage.
- A drop in `uordblks` without a matching `VmRSS` drop is treated as allocator-retained arena, not a still-live object by itself.
- `malloc_trim` diagnostics are diagnostic only and are not proposed as production default.

| trim variant | qret peak KB | trim stage | RSS drop KB | uordblks drop KB | fordblks drop KB |
| ------------ | ------------: | ---------- | ----------: | ---------------: | ---------------: |
| h4_4th_new2:eager_trim_after_machine_function | 171,216 | after_machine_function_construction | 0 | 0 | 140 |
| h4_4th_new2:eager_trim_after_mapping | 171,192 | after_mapping | 50,404 | 0 | 164 |
| h4_4th_new2:eager_trim_after_inverse_release | 171,256 | routing_after_inverse_map_release | 39,452 | -1 | 2,833 |
| h4_4th_new2:eager_trim_after_compile_info | 171,116 | after_compile_info | 39,604 | 0 | 2,829 |
| h5_4th_new2:eager_trim_after_inverse_release | 435,048 | routing_after_inverse_map_release | 108,736 | 0 | 116 |

## MachineFunction Component Analysis

| component | H5 eager observed/theoretical value |
| --------- | ---------------------------------: |
| `instruction_count` | 1,499,072 |
| `basic_block_count` | 3 |
| `instruction_type_count` | {'ALLOCATE': 10, 'ALLOCATE_MAGIC_FACTORY': 4, 'CNOT': 34780, 'DEALLOCATE': 10, 'HADAMARD': 319094, 'LATTICE_SURGERY_MAGIC': 236800, 'PROBABILITY_HINT': 236800, 'TWIST': 671574} |
| `instruction_object_bytes` | 144,451,120 |
| `operand_container_bytes` | 59,136,892 |
| `interned_path_storage_bytes` | 116,292 |
| `instruction_list_node_bytes` | 35,977,728 |
| `inverse_map_entries` | 1,499,072 |
| `inverse_map_bytes` | 59,962,880 |
| `metadata_bytes` | 23,985,152 |
| `machine_total_bytes` | 299,529,844 |
| `routing_temporary_bytes` | 21,133,864 |
| `depgraph_nodes` | 1,499,072 |
| `depgraph_edges` | 1,533,838 |
| `depgraph_bytes` | 62,324,224 |

## Process Isolation Feasibility

- Existing qret supports a serialization boundary at SC_LS_FIXED_V0 pipeline state, but Evaluation production skips that output to avoid a large JSON duplicate.
- Splitting immediately after IR parse would require serializing qret IR; that reintroduces JSON materialization and does not carry MachineFunction state.
- Splitting after MachineFunction construction would require a compact machine-function artifact that preserves instruction metadata, topology-derived symbols, and compile-info initialization state. That artifact does not currently exist.
- H4 process-isolation production implementation was therefore not added; the safe follow-up is a design task, not an optimization toggle.

## Hypothesis Evaluation

| hypothesis | status | basis |
| ---------- | ------ | ----- |
| A | supported | routing_entry VmHWM is compared against the run high-water. |
| B | supported | uordblks and VmRSS are compared around inverse-map release. |
| C | partially supported | fordblks after frees and later calc-info allocations are inspected in the timeline. |
| D | rejected | JSON DOM is destroyed before lowering; the H5 high-water appears after MachineFunction construction/routing setup. |
| E | supported | MachineFunction component estimate is compared with the H5 RSS high-water. |

## H9 Estimates

- observed classification present: `observed`
- estimated classification present: `estimated`
- theoretical classification present: `theoretical`
- H9 was not run; estimates extrapolate H4/H5 component growth.

## Decision

- No production optimization was implemented in this audit.
- Lazy inverse-map remains a diagnostic candidate, not the default.
- The next implementation should target MachineFunction live payload that exists before routing and remains live at the H5 high-water.

## Next Candidate Ranking

| rank | candidate | classification | H5 expected saving KB | peak effective | risk | basis |
| ---: | --------- | -------------- | --------------------: | -------------- | ---- | ----- |
| 1 | D: instruction object arena / flat storage | theoretical | 35,266 | True | high | MachineFunction is live when H5 high-water is reached. |
| 2 | E: instruction list-node removal | theoretical | 35,134 | True | medium-high | list nodes are live before routing and scale with instruction count. |
| 3 | F: residual operand API redesign | theoretical | 34,650 | True | medium-high | operand containers are live in MachineFunction at high-water. |
| 4 | inverse-map compactization | observed | 48 | False | medium | live inverse-map entries 1,499,072->0 did not move peak enough. |
| 5 | G: allocator strategy / process isolation | observed | 0 | False | medium | diagnostic malloc_trim is measured but is not a production optimization. |
