# qret TimeSeries Memory Optimization

## Environment

- Evaluation HEAD at run start: `559d6df6d7a4f0ceb6208e881a59ec98af8b6669`
- qret executable hash used: `d519cdb25446cf243053e84ffa559b7e6bd7dbd66365e1488d632208616dbbf5`
- qret core library hash used: `67bd68c35c6b2b5c686e8490e4a7c1651524bbc57f35560e8176d864cf394735`
- qret core library path: `/home/abe/Project/Evaluation_grouped_surface_code/build/quration/cmake-build/quration-core/src/libqret-core.so.1.0.2`
- compiler: `c++ (Ubuntu 11.4.0-1ubuntu1~22.04) 11.4.0`
- platform: `Linux-6.8.0-47-generic-x86_64-with-glibc2.35`
- MemTotal KB: `65522476`
- SwapTotal KB: `2097148`
- compile mode: `ftqc_compile_topology`
- batch size: `2`
- sampling interval: `0.02` sec

## qret Hash Provenance

- build before executable hash: `d519cdb25446cf243053e84ffa559b7e6bd7dbd66365e1488d632208616dbbf5`
- build before core hash: `67bd68c35c6b2b5c686e8490e4a7c1651524bbc57f35560e8176d864cf394735`
- build after executable hash: `d519cdb25446cf243053e84ffa559b7e6bd7dbd66365e1488d632208616dbbf5`
- build after core hash: `67bd68c35c6b2b5c686e8490e4a7c1651524bbc57f35560e8176d864cf394735`
- executable hash changed by build: `False`
- core library hash changed by build: `False`

The qret executable is a small dynamically linked launcher. Most SC_LS_FIXED_V0 C++ changes live in `libqret-core.so`, so executable SHA-256 alone can stay unchanged after qret C++ changes. This run records both hashes and treats either changing during measurement as a failure.

## Production Decision

- Current production default remains `summary_legacy_timeseries` (`QRET_SUMMARY_TIME_SERIES_IMPL` unset).
- `summary_compact_timeseries` and `summary_event_sweep` remain selectable profiling candidates via `QRET_SUMMARY_TIME_SERIES_IMPL`.
- H6 skipped reason: `no H5 candidate passed the H6 gate`.

## Semantic Audit

| field | element type | source | average | peak | sum use | derived metric |
| --- | --- | --- | --- | --- | --- | --- |
| `gate_throughput` | `uint64_t` | active instruction count in MachineFunction order | `uint64_t` sum in beat order / runtime | max | no separate derived sum | throughput stats |
| `measurement_feedback_rate` | `uint64_t` | first use of measurement-created c-symbol, counted at `creation beat + StartCorrecting()` | counted-event sum / runtime | max sparse beat count | sum is counted feedback events | feedback stats |
| `magic_state_consumption_rate` | `uint64_t` | per-beat `UseMagicState()` count | `uint64_t` sum in beat order / runtime | max | no separate derived sum | magic consumption stats |
| `entanglement_consumption_rate` | `uint64_t` | per-beat `CountEntanglement()` | `uint64_t` sum in beat order / runtime | max | no separate derived sum | entanglement stats |
| `chip_cell_algorithmic_qubit` | `uint64_t` | `TimeSeries::ChipInfo::ChipCellAlgorithmicQubit()` | `uint64_t` sum in beat order / runtime | max | no | cell stats |
| `chip_cell_algorithmic_qubit_ratio` | `double` | algorithmic qubits / chip cells | `double` sum in beat order / runtime | max | no | ratio stats |
| `chip_cell_active_qubit_area` | `uint64_t` | used ancilla + algorithmic qubits | `uint64_t` sum in beat order / runtime | max | yes | `qubit_volume` |
| `chip_cell_active_qubit_area_ratio` | `double` | active area / chip cells | `double` sum in beat order / runtime | max | no | ratio stats |

Observed semantics used by all variants:

- Active interval is `[Metadata().beat, Metadata().beat + effective_latency)`, where zero latency is treated as one active beat for TimeSeries membership.
- Runtime uses the legacy raw-latency bound plus one stored beat; compact and event-sweep use the same runtime value.
- Same-beat instruction order is MachineFunction traversal order. Compact CSR stores pointers in that order, and event-sweep keeps the active set ordered by stable MachineFunction index.
- Multi-beat instructions are processed on every active beat, matching legacy behavior for throughput, magic, entanglement, ancilla, factories, allocate/deallocate, CCreate, and Condition.
- Chip state is a running state for `q_symb`, `m_symb`, and `e_symb`; `used_ancilla_count` is beat-local active ancilla use.
- Feedback keeps the legacy two-pass beat behavior: CCreate records first, Condition then counts the first use at `creation beat + StartCorrecting()`; reserved symbols, duplicate CCreate, and unknown Condition keep legacy error behavior.

## Existing Memory

| case | runtime | machine inst | pointer count | pointer duplication | beat2inst bytes | beat2chip bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| H4 `4th(new_2)` | 428740 | 570306 | 836328 | 1.466 | 17143 | 8373 |
| H5 `4th(new_2)` | 1188700 | 1499072 | 2205426 | 1.471 | 46310 | 23216 |

## Variant Design

| variant | representation | asymptotic storage | semantic risk |
| --- | --- | --- | --- |
| `summary_legacy_timeseries` | `vector<vector<const Instruction*>>` plus `vector<ChipInfo>` | `O(runtime + stored pointers + runtime chip snapshots)` | oracle baseline |
| `summary_compact_timeseries` | CSR offsets plus flat instruction pointer array plus `vector<ChipInfo>` | `O(runtime offsets + stored pointers + runtime chip snapshots)` | low, because per-beat sequences remain directly comparable |
| `summary_event_sweep` | one instruction pointer table plus sorted start/end index vectors and running chip state | `O(machine instructions + start/end events + active set)` | medium, because feedback/order must be reproduced without beat snapshots |

## Isolated qret A/B

| case | variant | runs | median qret peak KB | median elapsed s | median compile_info B | max RSS stage |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| H4 `4th(new_2)` | `full` | 1 | 317192 | 3.077 | 18966758 | `compile_info_json_after_assign_chip_cell_active_qubit_area_ratio` |
| H4 `4th(new_2)` | `summary_legacy_timeseries` | 2 | 248866 | 2.784 | 2142 | `calc_info_with_topology_after_summary_accumulation` |
| H4 `4th(new_2)` | `summary_compact_timeseries` | 2 | 246298 | 2.671 | 2142 | `calc_info_with_topology_after_compact_beat2chip_resize` |
| H4 `4th(new_2)` | `summary_event_sweep` | 3 | 244284 | 2.818 | 2142 | `calc_info_without_topology_after_dep_graph` |
| H5 `4th(new_2)` | `summary_legacy_timeseries` | 2 | 641426 | 7.882 | 2172 | `calc_info_with_topology_after_summary_accumulation` |
| H5 `4th(new_2)` | `summary_compact_timeseries` | 2 | 619310 | 7.618 | 2172 | `calc_info_with_topology_after_summary_accumulation` |
| H5 `4th(new_2)` | `summary_event_sweep` | 2 | 616992 | 7.988 | 2172 | `calc_info_with_topology_after_summary_accumulation` |

## Container Footprint

| case | variant | snapshot stage | VmRSS KB | estimated container KB | outer vector KB | offset KB | pointer KB | beat2chip KB | event index/pointer KB | active peak |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| H4 `4th(new_2)` | `summary_legacy_timeseries` | `calc_info_with_topology_after_summary_accumulation` | 248756 | 25517 | 10048 |  | 7094 | 8373 |  |  |
| H4 `4th(new_2)` | `summary_compact_timeseries` | `calc_info_with_topology_after_summary_accumulation` | 246356 | 18257 | 0 | 3349 | 6533 | 8373 |  |  |
| H4 `4th(new_2)` | `summary_event_sweep` | `calc_info_with_topology_after_summary_accumulation` | 243644 | 8911 | 0 |  | 0 | 0 | 8911 | 13 |
| H5 `4th(new_2)` | `summary_legacy_timeseries` | `calc_info_with_topology_after_summary_accumulation` | 641216 | 69527 | 27860 |  | 18450 | 23216 |  |  |
| H5 `4th(new_2)` | `summary_compact_timeseries` | `calc_info_with_topology_after_summary_accumulation` | 619400 | 49733 | 0 | 9286 | 17229 | 23216 |  |  |
| H5 `4th(new_2)` | `summary_event_sweep` | `calc_info_with_topology_after_summary_accumulation` | 616732 | 23423 | 0 |  | 0 | 0 | 23423 | 14 |

## Container Reduction

| case | variant | old pointer entries | new entries/events | old ChipInfo count | new estimated state KB | estimated state saved KB |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| H4 `4th(new_2)` | `summary_compact_timeseries` | 836328 | 836328 | 428740 | 18257 | 7260 |
| H4 `4th(new_2)` | `summary_event_sweep` | 836328 | 1140612 | 428740 | 8911 | 16606 |
| H5 `4th(new_2)` | `summary_compact_timeseries` | 2205426 | 2205426 | 1188700 | 49733 | 19794 |
| H5 `4th(new_2)` | `summary_event_sweep` | 2205426 | 2998144 | 1188700 | 23423 | 46104 |

## Isolated Savings vs Legacy TimeSeries

| case | candidate | legacy peak KB | candidate peak KB | saved KB | saved % |
| --- | --- | ---: | ---: | ---: | ---: |
| H4 `4th(new_2)` | `summary_compact_timeseries` | 248866 | 246298 | 2568 | 1.03 |
| H4 `4th(new_2)` | `summary_event_sweep` | 248866 | 244284 | 4582 | 1.84 |
| H5 `4th(new_2)` | `summary_compact_timeseries` | 641426 | 619310 | 22116 | 3.45 |
| H5 `4th(new_2)` | `summary_event_sweep` | 641426 | 616992 | 24434 | 3.81 |

## End-to-End A/B

| case | variant | tree peak KB | qret peak KB | parent peak KB | parent at tree peak KB | qret at tree peak KB | read JSON sampled peak KB | compile_info B |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| H5 `4th(new_2)` | `summary_legacy_timeseries` | 901380 | 649116 | 250984 | 250984 | 649116 | 250984 | 2172 |
| H5 `4th(new_2)` | `summary_compact_timeseries` | 924192 | 668372 | 254540 | 254540 | 668372 | 254540 | 2172 |
| H5 `4th(new_2)` | `summary_event_sweep` | 885176 | 630252 | 253900 | 253900 | 629996 | 253900 | 2172 |

## Semantic Comparisons

- `h4_4th_new2:summary_compact_timeseries` vs `full`: normalized equal `True`, raw resource equal `True`, raw mismatches `[]`.
- `h4_4th_new2:summary_event_sweep` vs `full`: normalized equal `True`, raw resource equal `True`, raw mismatches `[]`.
- `h4_4th_new2:summary_legacy_timeseries` vs `full`: normalized equal `True`, raw resource equal `True`, raw mismatches `[]`.
- `h5_4th_new2:summary_compact_timeseries` vs `summary_legacy_timeseries`: normalized equal `True`, raw resource equal `True`, raw mismatches `[]`.
- `h5_4th_new2:summary_event_sweep` vs `summary_legacy_timeseries`: normalized equal `True`, raw resource equal `True`, raw mismatches `[]`.

## Execution Plan

- H5 candidates from H4: `['summary_event_sweep', 'summary_compact_timeseries']`
- H6 final candidate: `None`
- H6 skipped reason: `no H5 candidate passed the H6 gate`
- H6 gate decisions: `{'summary_compact_timeseries': {'baseline_elapsed_sec': 7.8816291694529355, 'elapsed_delta_pct': -3.3395096854743604, 'elapsed_sec': 7.618421399965882, 'h5_baseline_peak_kb': 641426.0, 'h5_peak_kb': 619310.0, 'passes_h6_gate': False, 'saved_kb': 22116.0, 'saved_pct': 3.447942552999099, 'semantic_ok': True}, 'summary_event_sweep': {'baseline_elapsed_sec': 7.8816291694529355, 'elapsed_delta_pct': 1.3526099216913583, 'elapsed_sec': 7.988236867589876, 'h5_baseline_peak_kb': 641426.0, 'h5_peak_kb': 616992.0, 'passes_h6_gate': False, 'saved_kb': 24434.0, 'saved_pct': 3.8093248480728876, 'semantic_ok': True}}`
- H6 headroom: `{'MemAvailable': 54907548, 'MemTotal': 65522476, 'SwapFree': 122060, 'SwapTotal': 2097148, 'disk_free_bytes': 11632713728}`

## Correctness And Safety

- compact DepGraph marker on isolated runs: `True`
- pipeline-state output skipped on isolated runs: `True`
- all runs succeeded: `True`
- guard triggered: `False`
- maximum swap used KB: `1975088`
- minimum MemAvailable KB: `54211764`

## Final Answers

1. H6 `beat2inst_`: not measured because H6 was skipped (`no H5 candidate passed the H6 gate`). H5 legacy beat2inst capacity was `46310` KB.
2. H6 `beat2chip_`: not measured because H6 was skipped. H5 legacy beat2chip capacity was `23216` KB.
3. Pointer duplication ratio: H5 legacy `1.471`.
4. Compact CSR estimated container reduction on H5: `19794` KB.
5. Event-sweep estimated container reduction on H5: `46104` KB.
6. H6 qret peak: not measured because no H5 candidate passed the H6 gate. H5 event-sweep isolated qret peak median was `616992` KB.
7. H6 process tree peak: not measured because H6 was skipped. H5 event-sweep end-to-end tree peak is reported above.
8. Elapsed change on H5: event-sweep `1.35`%, compact `-3.34`%.
9. Full and summary raw metrics matched for all measured H4/H5 comparisons.
10. Beat-level targeted tests matched legacy TimeSeries for compact CSR and event-sweep.
11. Multi-beat semantics were preserved by processing every active beat in legacy order; event-sweep maintains an active set ordered by MachineFunction index.
12. Event-sweep was not made production default because H5 qret peak reduction stayed below both 5% and 50 MB.
13. Legacy fallback remains the default and is also selectable through `QRET_SUMMARY_TIME_SERIES_IMPL=legacy_timeseries` or the compatibility alias `aggregate`.
14. Next largest qret RSS stage for the best H5 candidate is `calc_info_with_topology_after_summary_accumulation`.
15. H5 event-sweep peak minus routing-end RSS is `69120` KB.
16. Next qret-side object to inspect is the remaining summary accumulation peak after event-sweep indexing; Python parent JSON handling is a separate end-to-end bottleneck.
17. Python parent-process optimization should be handled as a follow-up, after qret-side TimeSeries work is not the dominant H5/H6 gate.

## Execution Time Naming

`compile_info.json` field `execution_time_sec` is qret's physical execution-time estimate from QEC resource estimation. Evaluation-generated step metrics now preserve it as `estimated_execution_time_sec` and store wall-clock compile elapsed as `compile_wall_time_sec`. The legacy generated-step alias `execution_time_sec` remains wall-clock elapsed for existing consumers.

## Artifacts

- output root: `/home/abe/Project/Evaluation_grouped_surface_code/artifacts/qret_timeseries_memory`
- `results.jsonl`: one JSON object per run.
- `summary.csv`: compact spreadsheet table.
