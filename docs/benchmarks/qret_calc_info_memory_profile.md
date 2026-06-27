# qret Calc-Info RSS Profile

## Purpose

Identify the remaining H4 `4th(new_2)` qret topology compile RSS peak after
`sc_ls_fixed_v0_skip_pipeline_state_output: true`. This run profiles only the
remaining peak source; it does not implement a production RSS optimization.

## Measurement

Command:

```bash
/home/abe/myproject/.venv/bin/python3.11 scripts/profile_qret_calc_info_memory.py --sample-interval-sec 0.02
```

All qret subprocesses used:

- rebuilt Evaluation vendored qret: `build/quration/qret`
- topology: `third_party/quration/quration-core/examples/data/topology/tutorial.yaml`
- option: `sc_ls_fixed_v0_skip_pipeline_state_output: true`
- internal markers: `QRET_RSS_PROFILE_JSONL`
- external sampler interval: 20 ms
- cases: H4 `2nd`, H4 `4th(new_2)`

The script also runs full prefix D once without `QRET_RSS_PROFILE_JSONL` for
semantic comparison.

## Implementation Structure

| component | source | role | large data observed |
| --- | --- | --- | --- |
| `CompileInfoWithoutTopology::RunOnMachineFunction` | `third_party/quration/quration-core/src/qret/target/sc_ls_fixed_v0/calc_compile_info.cpp:923` | scans machine instructions, constructs `DepGraph`, computes depth/runtime metrics | local `DepGraph graph` is the peak source |
| `DepGraph` | `third_party/quration/quration-core/src/qret/target/sc_ls_fixed_v0/calc_compile_info.h:21` | wraps dense instruction ids over `DiGraph` plus pointer/id maps | `ptr2id_`, `id2ptr_`, `DiGraph graph_` |
| `CalcRuntimeWithoutTopology` | `third_party/quration/quration-core/src/qret/target/sc_ls_fixed_v0/calc_compile_info.cpp:724` | scheduling simulation without topology using `InstQueue` | no RSS jump after queue construction or initial peek |
| `CompileInfoWithTopology::RunOnMachineFunction` | `third_party/quration/quration-core/src/qret/target/sc_ls_fixed_v0/calc_compile_info.cpp:1151` | builds `TimeSeries`, fills compile-info time-series vectors | small retained vector payload relative to peak |
| `TimeSeries` | `third_party/quration/quration-core/src/qret/target/sc_ls_fixed_v0/calc_compile_info.h:72` | `beat2inst_`, `beat2chip_` by routed beat | tens of MB in H4 `4th(new_2)`, not the peak |
| `DumpCompileInfo::RunOnMachineFunction` | `third_party/quration/quration-core/src/qret/target/sc_ls_fixed_v0/calc_compile_info.cpp:1429` | prints and writes compile info | JSON DOM/write adds no observed RSS beyond existing heap |
| `ScLsFixedV0CompileInfo` | `third_party/quration/quration-core/src/qret/target/sc_ls_fixed_v0/compile_info.h:16` | retained compile metrics | 8 time-series vectors after with-topology |
| `ScLsFixedV0CompileInfo::Json()` | `third_party/quration/quration-core/src/qret/target/sc_ls_fixed_v0/compile_info.cpp:110` | converts retained vectors to `nlohmann::ordered_json` | JSON node count scales with vector elements |
| RSS marker runtime | `third_party/quration/quration-core/src/qret/base/rss_profile.cpp:47` | emits `/proc/self/status` and `smaps_rollup` fields | includes `RssAnon`, `RssFile`, `RssShmem`, PSS, private dirty |
| prefix runner | `scripts/profile_qret_calc_info_memory.py:25` | runs pass prefixes A-D in separate qret subprocesses | writes raw logs under ignored artifacts |

## Prefix Comparison

| case | prefix | last pass | elapsed s | GNU time max RSS KB | sampled tree peak KB | qret marker peak | compile-info size B |
| --- | --- | --- | ---: | ---: | ---: | --- | ---: |
| H4 `2nd` | A | routing | 0.380 | 52,140 | 53,420 | `routing_after_main_loop` 52,140 | absent |
| H4 `2nd` | B | calc without topology | 0.804 | 189,336 | 190,616 | `calc_info_without_topology_after_dep_graph` 189,336 | absent |
| H4 `2nd` | C | calc with topology | 0.785 | 189,536 | 190,816 | `calc_info_without_topology_after_dep_graph` 189,536 | absent |
| H4 `2nd` | D | dump compile info | 0.888 | 188,984 | 190,264 | `calc_info_without_topology_after_dep_graph` 188,984 | 4,063,636 |
| H4 `2nd` | D no profile | dump compile info | 0.740 | 189,980 | 191,260 | n/a | 4,063,636 |
| H4 `4th(new_2)` | A | routing | 1.655 | 216,244 | 217,268 | `routing_after_main_loop` 215,988 | absent |
| H4 `4th(new_2)` | B | calc without topology | 3.931 | 861,032 | 862,056 | `calc_info_without_topology_after_dep_graph` 860,776 | absent |
| H4 `4th(new_2)` | C | calc with topology | 4.347 | 860,556 | 861,836 | `calc_info_without_topology_after_dep_graph` 860,556 | absent |
| H4 `4th(new_2)` | D | dump compile info | 4.603 | 860,724 | 862,004 | `calc_info_without_topology_after_dep_graph` 860,724 | 18,970,408 |
| H4 `4th(new_2)` | D no profile | dump compile info | 3.999 | 863,384 | 864,664 | n/a | 18,970,408 |

Prefix deltas from GNU time max RSS:

| case | B - A KB | C - B KB | D - C KB |
| --- | ---: | ---: | ---: |
| H4 `2nd` | 137,196 | 200 | -552 |
| H4 `4th(new_2)` | 644,788 | -476 | 168 |

## Stage RSS

| case | run | stage | VmRSS KB |
| --- | --- | --- | ---: |
| H4 `2nd` | B | routing after main loop | 52,376 |
| H4 `2nd` | B | after `DepGraph` construction | 189,336 |
| H4 `2nd` | B | pass exit, `DepGraph` still live | 189,336 |
| H4 `2nd` | B | pass-manager after calc without topology | 130,328 |
| H4 `2nd` | D | before JSON DOM | 129,632 |
| H4 `2nd` | D | after JSON DOM | 129,632 |
| H4 `2nd` | D | after JSON stream write | 129,632 |
| H4 `4th(new_2)` | B | routing after main loop | 216,168 |
| H4 `4th(new_2)` | B | after `DepGraph` construction | 860,776 |
| H4 `4th(new_2)` | B | pass exit, `DepGraph` still live | 860,776 |
| H4 `4th(new_2)` | B | pass-manager after calc without topology | 860,776 |
| H4 `4th(new_2)` | D | before JSON DOM | 860,724 |
| H4 `4th(new_2)` | D | after JSON DOM | 860,724 |
| H4 `4th(new_2)` | D | after JSON stream write | 860,724 |

The exact post-pass current RSS is allocator-sensitive. A previous
skip-output A/B run recorded H4 `4th(new_2)` post-calc RSS around 579,500 KB.
The detailed marker run above kept the freed `DepGraph` heap resident and stayed
near 860 MB. In both cases, the live compile-info payload at that point is not
the cause: before with-topology, retained compile-info vector capacity is 0.

## Container Scale

| case | stage/container | count/capacity | estimated payload |
| --- | --- | ---: | ---: |
| H4 `2nd` | `DepGraph` nodes | 121,056 | 15,495,168 B |
| H4 `2nd` | `DepGraph` edges | 123,380 | 987,040 B |
| H4 `2nd` | `DepGraph` pointer maps | 121,056 + 121,056 entries | 2,905,344 B |
| H4 `2nd` | `TimeSeries::beat2inst_` buckets | 91,056 | 2,185,344 B |
| H4 `2nd` | `TimeSeries::beat2inst_` pointer capacity | 192,548 | 1,540,384 B |
| H4 `2nd` | `TimeSeries::beat2chip_` capacity | 91,056 | 1,821,120 B |
| H4 `2nd` | compile-info vectors | 728,448 elements | 5,827,584 B |
| H4 `2nd` | compile-info JSON DOM | 728,541 nodes | 728,464 array elements |
| H4 `4th(new_2)` | `DepGraph` nodes | 570,378 | 73,008,384 B |
| H4 `4th(new_2)` | `DepGraph` edges | 581,822 | 4,654,576 B |
| H4 `4th(new_2)` | `DepGraph` pointer maps | 570,378 + 570,378 entries | 13,689,072 B |
| H4 `4th(new_2)` | `TimeSeries::beat2inst_` buckets | 428,864 | 10,292,736 B |
| H4 `4th(new_2)` | `TimeSeries::beat2inst_` pointer capacity | 908,493 | 7,267,944 B |
| H4 `4th(new_2)` | `TimeSeries::beat2chip_` capacity | 428,864 | 8,577,280 B |
| H4 `4th(new_2)` | compile-info vectors | 3,430,912 elements | 27,447,296 B |
| H4 `4th(new_2)` | compile-info JSON DOM | 3,431,005 nodes | 3,430,928 array elements |

`DepGraph` measured payload does not include `std::list`, `std::map`, and
`std::unordered_*` node/bucket allocator overhead. The observed RSS jump is much
larger than the raw payload estimate because every node has nested
`unordered_set` storage and the graph uses pointer/id maps in addition to
`DiGraph` node and edge storage.

## RSS Breakdown

| case | stage | VmRSS KB | VmHWM KB | VmSize KB | RssAnon KB | RssFile KB | PSS KB | private dirty KB |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| H4 `2nd` | routing after main loop | 52,376 | 52,376 | 56,224 | 44,952 | 7,424 | 49,349 | 45,196 |
| H4 `2nd` | after `DepGraph` construction | 189,336 | 189,336 | 193,144 | 181,912 | 7,424 | 186,365 | 182,212 |
| H4 `2nd` | run end after prefix B | 130,328 | 189,336 | 133,840 | 122,904 | 7,424 | 127,133 | 122,980 |
| H4 `4th(new_2)` | routing after main loop | 216,168 | 216,168 | 220,256 | 208,744 | 7,424 | 213,334 | 209,180 |
| H4 `4th(new_2)` | after `DepGraph` construction | 860,776 | 860,776 | 864,700 | 853,352 | 7,424 | 857,890 | 853,736 |
| H4 `4th(new_2)` | run end after prefix B | 860,776 | 860,776 | 864,700 | 853,352 | 7,424 | 857,890 | 853,736 |

The peak is anonymous/private dirty heap, not mapped file RSS or page cache.

## Semantic Check

Profiling on/off full prefix D normalized metrics matched for both cases after
excluding only `compile_info_json` and `execution_time_sec`.

Explicit semantic fields checked:

`magic_state_consumption_count`, `magic_state_consumption_depth`, `runtime`,
`runtime_without_topology`, `qubit_volume`, `gate_count`, `gate_depth`,
`measurement_feedback_count`, `measurement_feedback_depth`,
`magic_factory_count`, `chip_cell_count`, `code_distance`,
`num_physical_qubits`, `t_count`, `t_depth`.

`t_count` and `t_depth` were absent in both profiled and unprofiled outputs.
All other listed fields were present and equal.

## Answers

1. Exact peak stage: H4 `4th(new_2)` reaches the remaining peak in
   `CompileInfoWithoutTopology::RunOnMachineFunction`, immediately after local
   `auto graph = DepGraph(mf)`.
2. The retained post-calc heap is not compile-info source data. Before
   with-topology, compile-info vector capacity is 0. The live baseline after
   routing is about 216 MB; the rest is allocator-held anonymous heap from
   `DepGraph` and its nested STL allocations.
3. Internal peak of `calc_info_without_topology`: 860,776 KB marker RSS in the
   final H4 `4th(new_2)` prefix B run, with 570,378 graph nodes and 581,822
   graph edges.
4. `calc_info_with_topology` RSS growth: no observed RSS increase in H4
   `4th(new_2)`. Its retained compile-info vectors are about 27.4 MB capacity,
   and `TimeSeries` temporary capacity is about 26.1 MB by raw payload.
5. `dump_compile_info` cost: no observed RSS increase. H4 `4th(new_2)`
   `compile_info.json` is 18,970,408 B; JSON DOM has 3,431,005 nodes, but the
   process RSS was already dominated by allocator-retained heap.
6. Compile-info source data and JSON DOM do duplicate the time-series data, but
   the duplicated scale is tens of MB, not the 860 MB peak.
7. Large containers: the only stage-local container matching the peak location
   is `DepGraph` over all machine instructions, using `std::map`, `DiGraph`
   nodes/edges, and nested `unordered_set` adjacency storage.
8. Scaling: H4 `4th(new_2)` has 570,378 machine instructions vs 121,056 for H4
   `2nd` (4.71x), and the `DepGraph` RSS jump grows from about 137 MB to about
   645 MB (4.70x).
9. Allocator vs object retention: the object-level live compile-info data is
   small or zero at the peak. The remaining RSS is anonymous/private dirty heap
   retained by the allocator after large STL graph allocations. The exact
   post-pass current RSS varied across runs, but the peak location did not.
10. Next low-risk candidates: optimize or replace `DepGraph`; do not target
    JSON dumping, with-topology vectors, or pipeline-state output first.

## Candidate Ranking

| rank | candidate | expected RSS impact | risk | reason |
| ---: | --- | --- | --- | --- |
| 1 | Replace `DepGraph` STL-heavy representation with dense vectors/CSR-style adjacency keyed by dense instruction id | high | medium | directly targets the 645 MB H4 `4th(new_2)` jump |
| 2 | Remove or avoid `id2ptr_` and reduce `ptr2id_`/map overhead where dense ids are enough | medium | low-medium | pointer/id maps scale with every instruction |
| 3 | Reserve and flatten adjacency storage during `DepGraph` construction | medium | medium | nested `unordered_set` allocation overhead dominates raw payload |
| 4 | Compute depth metrics in one compact topological DP without retaining full nested graph containers | high | medium-high | largest structural fix but touches metric logic |
| 5 | Consider a profiling-only `malloc_trim(0)` experiment after calc-info | current RSS only | low for experiment | would not reduce `ru_maxrss`; useful only to quantify allocator behavior |
| 6 | Optimize compile-info JSON/time-series dumping | low for current peak | low | measured DOM/vector sizes are not the remaining 860 MB peak |

