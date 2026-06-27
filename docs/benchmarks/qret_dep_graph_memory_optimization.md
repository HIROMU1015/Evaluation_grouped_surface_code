# qret DepGraph Memory Optimization

## Purpose

Reduce the remaining H4 `4th(new_2)` RSS peak in
`CompileInfoWithoutTopology::RunOnMachineFunction` by replacing the
instruction dependency graph payload used for depth metrics. This follows the
previous profiling result that identified local `DepGraph graph` construction
as the dominant peak after pipeline-state output was skipped.

## Implementation Notes

`DepGraph` is only constructed in
`third_party/quration/quration-core/src/qret/target/sc_ls_fixed_v0/calc_compile_info.cpp`
inside `CompileInfoWithoutTopology::RunOnMachineFunction`. The old
implementation kept:

- `std::map<const ScLsInstructionBase*, IdType> ptr2id_`
- `std::map<IdType, const ScLsInstructionBase*> id2ptr_`
- `DiGraph`, whose nodes contain nested `unordered_set` adjacency containers

The only production call sites needed scalar depth values from
`FindHeaviestPath` and `FindLongestPath`; the returned path and per-node map
were not used. `id2ptr_` was only reported in stats. The remaining pointer-map
uses were replaced in the compile-info pass with dense instruction ids.

This change adds `CompactDepGraph`, a dense-id graph with flat vectors:
`parent_offsets`, `parent_ids`, `edge_lengths`, `node_weights`, and a reusable
DP buffer. It preserves the existing edge rules:

- qtarget dependencies follow the previous writer of the same `QSymbol`
- `Move` and `MoveTrans` update the qsymbol owner from source to destination
- classical `Condition` and `CDepend` edges keep the previous measurement
  reaction-time behavior
- reserved classical symbols do not create normal dependency edges
- duplicate edges overwrite length, matching `DiGraph::AddEdge`

The same binary supports A/B switching through `QRET_DEP_GRAPH_IMPL`:
`legacy`, `legacy_no_id2ptr`, `legacy_dense`, and `compact`. Empty/unset uses
`compact`. Invalid values fail with an explicit error and keep the accepted
values in the message.

## Measurement

Command:

```bash
/home/abe/myproject/.venv/bin/python3.11 scripts/profile_qret_dep_graph_memory.py --implementation legacy --implementation legacy_no_id2ptr --implementation legacy_dense --implementation compact --repeat 3 --sample-interval-sec 0.02
```

Common setup:

- qret: `build/quration/qret`
- topology: `third_party/quration/quration-core/examples/data/topology/tutorial.yaml`
- passes: init compile info, mapping, routing, calc-info without topology,
  calc-info with topology, dump compile info
- option: `sc_ls_fixed_v0_skip_pipeline_state_output: true`
- profiler: `QRET_RSS_PROFILE_JSONL`, plus `/usr/bin/time -v`
- cases: H4 `2nd`, H4 `4th(new_2)`
- repeats: 3 per implementation per case

Raw results are under ignored `artifacts/qret_dep_graph_memory/`.

## A/B Results

| case | impl | peak runs KB | median peak KB | elapsed runs s | median elapsed s | before DepGraph KB | after DepGraph KB | DepGraph delta KB | pass-end KB | nodes | edges | rc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| H4 `2nd` | legacy | 189300, 189252, 189244 | 189252 | 0.885, 0.818, 0.818 | 0.818 | 52340 | 189252 | 136960 | 130048 | 121056 | 123380 | 0,0,0 |
| H4 `2nd` | legacy_no_id2ptr | 181432, 181936, 181600 | 181600 | 0.794, 0.799, 0.815 | 0.799 | 52320 | 181600 | 129280 | 122292 | 121056 | 123380 | 0,0,0 |
| H4 `2nd` | legacy_dense | 174380, 174516, 174356 | 174380 | 0.785, 0.767, 0.807 | 0.785 | 52524 | 174380 | 121856 | 115148 | 121056 | 123380 | 0,0,0 |
| H4 `2nd` | compact | 73136, 73684, 73728 | 73684 | 0.578, 0.577, 0.583 | 0.578 | 52436 | 57044 | 4608 | 57044 | 121056 | 123380 | 0,0,0 |
| H4 `4th(new_2)` | legacy | 861020, 861288, 860816 | 861020 | 4.609, 4.346, 4.451 | 4.451 | 216464 | 861020 | 644608 | 574908 | 570378 | 581822 | 0,0,0 |
| H4 `4th(new_2)` | legacy_no_id2ptr | 825124, 824972, 825252 | 825124 | 4.251, 4.235, 4.443 | 4.251 | 216460 | 825124 | 608768 | 551884 | 570378 | 581822 | 0,0,0 |
| H4 `4th(new_2)` | legacy_dense | 788836, 788892, 789968 | 788892 | 4.220, 4.117, 4.120 | 4.120 | 215908 | 788892 | 573184 | 502304 | 570378 | 581822 | 0,0,0 |
| H4 `4th(new_2)` | compact | 314180, 314160, 313972 | 314160 | 3.016, 2.997, 3.030 | 3.016 | 216388 | 244036 | 27648 | 244036 | 570378 | 581822 | 0,0,0 |

Compact vs legacy:

| case | peak RSS reduction | DepGraph-construction delta reduction | elapsed reduction |
| --- | ---: | ---: | ---: |
| H4 `2nd` | 115568 KB / 61.1% | 132352 KB / 96.6% | 29.3% |
| H4 `4th(new_2)` | 546860 KB / 63.5% | 616960 KB / 95.7% | 32.3% |

Staged variants showed that dropping `id2ptr_` alone saves about 4% peak RSS,
and removing both pointer maps while retaining legacy `DiGraph` saves about
8%. The large win comes from replacing `DiGraph`'s per-node adjacency
containers and path-result temporary maps with the compact CSR-like layout and
scalar DP.

## Compact Graph Stats

| case | nodes | edges | duplicate edges overwritten | max indegree | average indegree | compact payload capacity B | DP capacity |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| H4 `2nd` | 121056 | 123380 | 19848 | 2 | 1.0192 | 4114176 | 121056 |
| H4 `4th(new_2)` | 570378 | 581822 | 91300 | 2 | 1.0201 | 29728848 | 570378 |

`topological_order_invariant` was true in compact markers. The flat payload
capacity includes parent offsets, parent ids, edge lengths, node weights, and
the reusable DP buffer after depth calculations.

## Semantic Equivalence

For both cases, all implementations and all repeats matched the `legacy`
run-0 normalized metrics. Determinism also matched within each implementation.

Compared fields exclude only volatile output path and execution-time fields
from the existing metric extractor: `compile_info_json` and
`execution_time_sec`. The extractor did not emit profiling, timestamp, or
DepGraph mode metadata into normalized compile-info metrics. The semantic
fields checked include runtime, runtime-without-topology, gate count/depth,
magic count/depth, measurement feedback count/depth, factory counts, qubit
volume, code distance, physical qubit count, `t_count`, and `t_depth`.

## Validation

Commands run:

```bash
/home/abe/myproject/.venv/bin/python3.11 -m pytest tests/test_qret_pre_routing_profile.py -q
/home/abe/myproject/.venv/bin/python3.11 -m compileall scripts tests
git diff --check
scripts/build_qret.sh
/home/abe/.local/vcpkg/downloads/tools/cmake-4.2.3-linux/cmake-4.2.3-linux-x86_64/bin/cmake -S third_party/quration -B build/quration-tests -DCMAKE_BUILD_TYPE=Release -DQRET_BUILD_APPLICATION=OFF -DQRET_BUILD_ALGORITHM=OFF -DQRET_BUILD_EXAMPLE=OFF -DQRET_BUILD_TEST=ON -DQRET_BUILD_PYTHON=OFF -DQRET_USE_QULACS=OFF -DCMAKE_TOOLCHAIN_FILE=/home/abe/.local/vcpkg/scripts/buildsystems/vcpkg.cmake
/home/abe/.local/vcpkg/downloads/tools/cmake-4.2.3-linux/cmake-4.2.3-linux-x86_64/bin/cmake --build build/quration-tests --target target_sc_ls_fixed_v0_compact_dep_graph --parallel 2
./build/quration-tests/quration-core/tests/target_sc_ls_fixed_v0_compact_dep_graph --gtest_color=no
env QRET_DEP_GRAPH_IMPL=bad build/quration/qret compile --pipeline artifacts/qret_dep_graph_memory/h4_2nd/compact/run_00/compile.yaml --verbose
```

The C++ gtest binary ran 9 tests covering empty/single-node graphs, linear,
fork/join, multiple parents, duplicate overwrite semantics, zero weights and
lengths, node/edge updates for depth calculations, reserved classical
no-dependency behavior, invalid non-topological edges, missing edge updates,
and legacy-vs-compact `DepGraph` metrics on a small `Move`/`MoveTrans`
machine function.

`ctest -R compact_dep_graph` found no registered tests in this local test
build, so the gtest executable was run directly.

The invalid implementation-mode check exited with code 1 and printed:
`Invalid QRET_DEP_GRAPH_IMPL 'bad'. Expected one of: legacy, legacy_no_id2ptr, legacy_dense, compact.`
