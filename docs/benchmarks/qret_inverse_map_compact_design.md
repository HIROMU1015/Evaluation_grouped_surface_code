# qret Compact Inverse Map Design Audit

## Execution Limits

- largest measured case: `H5`
- H6 executed: `False`
- H7 executed: `False`
- H8 executed: `False`
- H9 executed: `False`
- H9 memory: estimated from observed H4/H5 values, not measured.

## Production Configuration

- magic path storage: `interned`
- non-path operands: legacy list containers
- compile-info output: `summary`
- summary TimeSeries: `legacy_timeseries`
- DepGraph: `compact`
- inverse-map release after routing: enabled
- pipeline-state output skip: enabled through the Evaluation architecture

## H4 Correctness And Schema

- profile-off return code: `0`
- profile-on return code: `0`
- raw/normalized metric parity: `True`
- profile-off has inverse-map usage fields: `False`
- profile-on has inverse-map usage fields: `True`

| comparison | raw equal | normalized equal | raw mismatches | normalized mismatches |
| ---------- | --------: | ---------------: | -------------- | --------------------- |
| h4_profile_off_vs_on | True | True | [] | [] |

## H5 Observed Profile

- qret peak RSS KB: `434,892`
- process tree peak KB: `436,172`
- elapsed seconds: `18.235`
- routing peak stage: `routing_entry_from_pass_manager`
- routing peak RSS KB: `434,892`
- routing before inverse-map release RSS KB: `434,892`
- routing after inverse-map release RSS KB: `434,892`
- qret inverse map entries: `1,499,072`
- qret inverse map estimated MB: `57.2`
- allocator uordblks at before-release KB: `387,978`
- allocator fordblks at before-release KB: `39,877`

## H5 Safety Snapshot

- MemTotal KB: `65,522,476`
- MemAvailable KB: `54,438,940`
- SwapTotal KB: `2,097,148`
- SwapFree KB: `287,408`
- disk free bytes: `11,556,941,824`
- script guard rejects H6/H7/H8/H9 case names before qret execution.

## Usage Counters

| counter | value |
| ------- | ----: |
| `inverse_map_usage_construct_inverse_map_count` | 3 |
| `inverse_map_usage_initial_inserted_entries` | 1,499,072 |
| `inverse_map_usage_full_rebuild_count` | 3 |
| `inverse_map_usage_lazy_rebuild_count` | 0 |
| `inverse_map_usage_contain_count` | 0 |
| `inverse_map_usage_contain_hit_count` | 0 |
| `inverse_map_usage_contain_miss_count` | 0 |
| `inverse_map_usage_insert_before_count` | 0 |
| `inverse_map_usage_insert_after_count` | 0 |
| `inverse_map_usage_erase_count` | 0 |
| `inverse_map_usage_release_count` | 3 |
| `inverse_map_usage_max_live_entries` | 1,499,072 |
| `inverse_map_usage_final_entries_before_release_total` | 1,499,072 |

## Compact Candidate Model

| candidate | classification | estimated MB | theoretical saving MB | note |
| --------- | -------------- | -----------: | --------------------: | ---- |
| `current_std_map` | observed | 57.2 | 0.0 | current std::map<const MachineInstruction*, ConstIterator> |
| `stable_instruction_id_vector` | theoretical | 22.9 | 34.3 | requires a stable 32-bit instruction ID or equivalent side metadata |
| `block_local_slot_vector_tombstone` | theoretical | 24.3 | 32.9 | requires block-local slot ownership and tombstone/free-list policy |
| `unordered_map_pointer_iterator` | theoretical | 71.5 | 0.0 | lower code risk, but allocator and bucket overhead keep savings modest |
| `sorted_flat_pointer_iterator` | theoretical | 22.9 | 34.3 | compact, but Insert/Erase are O(N) unless updates are batched |
| `partial_lazy_inverse_map_lower_bound` | theoretical | 0.0 | 57.2 | lower-bound estimate; exact unique touched pointers are not observed |

## Stable ID Layout Projection

The stable-ID option is not implemented here. The table is a layout projection: observed object bytes plus a 32-bit ID rounded to each instruction type's alignment.

| instruction type | count | current object MB | projected object MB | delta MB |
| ---------------- | ----: | ----------------: | ------------------: | -------: |
| `TWIST` | 671,574 | 51.2 | 56.4 | 5.1 |
| `HADAMARD` | 319,094 | 21.9 | 24.3 | 2.4 |
| `LATTICE_SURGERY_MAGIC` | 236,800 | 41.6 | 43.4 | 1.8 |
| `PROBABILITY_HINT` | 236,800 | 19.9 | 21.7 | 1.8 |
| `CNOT` | 34,780 | 3.2 | 3.4 | 0.3 |
| `ALLOCATE` | 10 | 0.0 | 0.0 | 0.0 |
| `DEALLOCATE` | 10 | 0.0 | 0.0 | 0.0 |
| `ALLOCATE_MAGIC_FACTORY` | 4 | 0.0 | 0.0 | 0.0 |

## Lifetime And Stability Audit

- owner: each `MachineBasicBlock` owns one inverse map for its instruction list.
- construction: routing constructs maps for all blocks immediately after validation.
- last normal use: routing main loop mutations and block lookup helpers; compile-info and serialization use linear iteration and do not require the inverse map.
- release: `MachineFunction::ReleaseInverseMaps()` clears all maps after routing temporaries are destroyed.
- lazy rebuild: `Contain`, `InsertBefore`, `InsertAfter`, and `Erase` call `EnsureInverseMap()`, so custom passes after release can rebuild on demand.
- iterator stability: `std::list` insert preserves existing iterators; erase invalidates only the erased iterator and the map erases that pointer.
- pointer stability: instructions are separately allocated behind `unique_ptr`; list node movement does not move instruction objects.
- multi-compile safety: profile counters are process-local and reset by qret process lifetime; production data remains per `MachineBasicBlock`.

## H9 Estimates

H9 was not run. These estimates combine instruction-count ratio, instruction-type ratio, bytes-per-instruction, and component-growth models from observed H4/H5 values.

- observed classification present: `observed`
- estimated classification present: `estimated`
- theoretical classification present: `theoretical`
- selected compact candidate: `partial_lazy_inverse_map_lower_bound`

| scenario | variant | classification | component | MB |
| -------- | ------- | -------------- | --------- | --: |
| central | current_production | estimated | instruction_object | 6548.2 |
| central | current_production | estimated | operand_containers | 2440.5 |
| central | current_production | estimated | path_storage | 240.3 |
| central | current_production | estimated | instruction_list_nodes | 1637.1 |
| central | current_production | estimated | inverse_map | 2728.5 |
| central | current_production | estimated | metadata | 1091.4 |
| central | current_production | estimated | routing_temporary | 930.7 |
| central | current_production | estimated | python_parent | 58.5 |
| central | current_production | estimated | total | 15675.1 |
| central | with_compact_inverse_map_candidate | estimated | instruction_object | 6548.2 |
| central | with_compact_inverse_map_candidate | estimated | operand_containers | 2440.5 |
| central | with_compact_inverse_map_candidate | estimated | path_storage | 240.3 |
| central | with_compact_inverse_map_candidate | estimated | instruction_list_nodes | 1637.1 |
| central | with_compact_inverse_map_candidate | estimated | inverse_map | 0.0 |
| central | with_compact_inverse_map_candidate | estimated | metadata | 1091.4 |
| central | with_compact_inverse_map_candidate | estimated | routing_temporary | 930.7 |
| central | with_compact_inverse_map_candidate | estimated | python_parent | 58.5 |
| central | with_compact_inverse_map_candidate | estimated | total | 12946.7 |
| conservative | current_production | estimated | instruction_object | 5544.9 |
| conservative | current_production | estimated | operand_containers | 2065.5 |
| conservative | current_production | estimated | path_storage | 204.0 |
| conservative | current_production | estimated | instruction_list_nodes | 1391.5 |
| conservative | current_production | estimated | inverse_map | 2319.2 |
| conservative | current_production | estimated | metadata | 927.7 |
| conservative | current_production | estimated | routing_temporary | 776.2 |
| conservative | current_production | estimated | python_parent | 48.8 |
| conservative | current_production | estimated | total | 13277.9 |
| conservative | with_compact_inverse_map_candidate | estimated | instruction_object | 5544.9 |
| conservative | with_compact_inverse_map_candidate | estimated | operand_containers | 2065.5 |
| conservative | with_compact_inverse_map_candidate | estimated | path_storage | 204.0 |
| conservative | with_compact_inverse_map_candidate | estimated | instruction_list_nodes | 1391.5 |
| conservative | with_compact_inverse_map_candidate | estimated | inverse_map | 0.0 |
| conservative | with_compact_inverse_map_candidate | estimated | metadata | 927.7 |
| conservative | with_compact_inverse_map_candidate | estimated | routing_temporary | 776.2 |
| conservative | with_compact_inverse_map_candidate | estimated | python_parent | 48.8 |
| conservative | with_compact_inverse_map_candidate | estimated | total | 10958.7 |
| upper | current_production | estimated | instruction_object | 8234.4 |
| upper | current_production | estimated | operand_containers | 3070.4 |
| upper | current_production | estimated | path_storage | 863.5 |
| upper | current_production | estimated | instruction_list_nodes | 2050.9 |
| upper | current_production | estimated | inverse_map | 3418.2 |
| upper | current_production | estimated | metadata | 1367.3 |
| upper | current_production | estimated | routing_temporary | 1187.9 |
| upper | current_production | estimated | python_parent | 74.7 |
| upper | current_production | estimated | total | 20267.3 |
| upper | with_compact_inverse_map_candidate | estimated | instruction_object | 8234.4 |
| upper | with_compact_inverse_map_candidate | estimated | operand_containers | 3070.4 |
| upper | with_compact_inverse_map_candidate | estimated | path_storage | 863.5 |
| upper | with_compact_inverse_map_candidate | estimated | instruction_list_nodes | 2050.9 |
| upper | with_compact_inverse_map_candidate | estimated | inverse_map | 0.0 |
| upper | with_compact_inverse_map_candidate | estimated | metadata | 1367.3 |
| upper | with_compact_inverse_map_candidate | estimated | routing_temporary | 1187.9 |
| upper | with_compact_inverse_map_candidate | estimated | python_parent | 74.7 |
| upper | with_compact_inverse_map_candidate | estimated | total | 16849.1 |

## Decision

- production inverse-map implementation changed in this task: `False`
- H5 adoption decision for compact inverse map: `defer`; this phase produced read-only measurements and design estimates only.
- next production candidate: `partial_lazy_inverse_map_lower_bound`.
- H6/H7/H8/H9 execution remains prohibited.
