# qret H4/H5 Memory Reduction Strategy

Only H4 and H5 were observed. H6, H7, H8, and H9 were not executed.

## Execution Limits

- largest measured case: `H5`
- H6 executed: `False`
- H7 executed: `False`
- H8 executed: `False`
- H9 executed: `False`
- H9 memory: estimated from observed H4/H5 values, not measured.
- H9 labels used below: `observed`, `estimated`, `theoretical`

## Current Production

- magic path storage: `interned`
- rollback: `QRET_MAGIC_PATH_STORAGE=legacy_list`
- non-path operands: legacy containers
- compile-info mode: summary
- TimeSeries mode: legacy summary TimeSeries
- DepGraph mode: compact
- inverse-map construction: eager by default; `QRET_INVERSE_MAP_CONSTRUCTION=lazy` remains an explicit rejected candidate mode
- inverse-map release after routing: enabled
- pipeline-state output: skipped

Phase 0 accepted exact path interning on the final holder layout
(`std::list<Coord3D>` plus optional shared handle). Phase 1 measured compact
singleton non-path operands, but did not adopt it for production.

| phase | case | variant | observed runs | median qret peak KB | median routing peak KB | median elapsed s | decision |
| ----- | ---- | ------- | ------------: | ------------------: | ---------------------: | ---------------: | -------- |
| Phase 0 | H5 `4th(new_2)` | legacy path | 2 | 551,500 | 551,500 | 21.050 | replaced |
| Phase 0 | H5 `4th(new_2)` | interned path | 2 | 434,924 | 434,924 | 18.565 | production |
| Phase 1 | H5 `4th(new_2)` | current production | 2 | 434,924 | 434,924 | 18.565 | kept |
| Phase 1 | H5 `4th(new_2)` | compact singleton operands | 2 | 422,600 | 421,832 | 20.253 | not adopted |

Phase 1 raw and normalized metrics matched for H4/H5, and path interning counters
were unchanged. The candidate was rejected because H5 median qret peak improved by
only `12,324 KB` (`2.834%`) and elapsed regressed by `9.092%`.

Phase 2 measured lazy inverse-map construction. It eliminated all inverse-map
entries in the current H5 production pipeline, but was not adopted because RSS
peak did not move enough to pass the H5 gate.

| phase | case | variant | observed runs | median qret peak KB | median routing peak KB | median elapsed s | median max live inverse-map entries | decision |
| ----- | ---- | ------- | ------------: | ------------------: | ---------------------: | ---------------: | ----------------------------------: | -------- |
| Phase 2 | H5 `4th(new_2)` | eager inverse-map construction | 2 | 434,900 | 434,900 | 18.091 | 1,499,072 | kept |
| Phase 2 | H5 `4th(new_2)` | lazy inverse-map construction | 2 | 434,852 | 434,852 | 17.919 | 0 | not adopted |

Phase 2 raw and normalized metrics matched for H4/H5. The H5 median qret peak
improved by only `48 KB` (`0.011%`), and one lazy run was higher than one eager
run, so the production default remains eager. The useful diagnostic result is
that allocator in-use bytes at `routing_before_inverse_map_release` dropped by
about `93,690 KB` while VMRSS stayed at the previous high-water level. The next
effective optimization must reduce the pre-routing/MachineFunction RSS high-water
or allocator retention, not only remove data that no longer controls VMRSS.

## Operand Audit

The compact singleton candidate targeted the highest-count 0/1 fields. It removed
about `44.4 MB` of estimated list-node payload on H5, but added about `29.6 MB` to
instruction object bodies because the compatibility adapter carried an owner-side
list cache. Net estimated MachineFunction reduction at routing peak was only
about `14.8 MB`, matching the small observed RSS reduction.

| instruction type | field | count | empty | length 1 | length 2 | length 3+ | estimated MB |
| ---------------- | ----- | ----: | ----: | -------: | -------: | --------: | -----------: |
| `TWIST` | `qtarget` | 671,574 | 0 | 671,574 | 0 | 0 | 15.4 |
| `HADAMARD` | `qtarget` | 319,094 | 0 | 319,094 | 0 | 0 | 7.3 |
| `LATTICE_SURGERY_MAGIC` | `qtarget` | 236,800 | 0 | 236,800 | 0 | 0 | 5.4 |
| `LATTICE_SURGERY_MAGIC` | `ccreate` | 236,800 | 0 | 236,800 | 0 | 0 | 5.4 |
| `LATTICE_SURGERY_MAGIC` | `mtarget` | 236,800 | 0 | 236,800 | 0 | 0 | 5.4 |
| `PROBABILITY_HINT` | `cdepend` | 236,800 | 0 | 236,800 | 0 | 0 | 5.4 |
| `CNOT` | `qtarget` | 34,780 | 0 | 0 | 34,780 | 0 | 1.6 |
| all instructions | `condition` | 236,800 elements | many | not singleton-only | possible | possible | 5.4 |

| instruction type | field | construction | mutation | random insertion | erase | iterator stability |
| ---------------- | ----- | ------------ | -------- | ---------------- | ----- | ------------------ |
| `TWIST` | `qtarget` | `New` / `FromJson` / lowering | none found | no | no | not required by consumers |
| `HADAMARD` | `qtarget` | `New` / `FromJson` / lowering | none found | no | no | not required by consumers |
| `LATTICE_SURGERY_MAGIC` | `qtarget` | `New` / `FromJson` / routing | whole-field `SetQubitList` | no | no | sequence order required |
| `LATTICE_SURGERY_MAGIC` | `ccreate` | `New` / `FromJson` | none found | no | no | not required by consumers |
| `LATTICE_SURGERY_MAGIC` | `mtarget` | `New` / `FromJson` | scalar `SetMagicFactory` | no | no | not required by consumers |
| `PROBABILITY_HINT` | `cdepend` | `New` / `FromJson` | none found | no | no | not required by consumers |
| `CNOT` | `qtarget` | `New` / `FromJson` | none found | no | no | order and length-2 semantics required |
| all instructions | `condition` | parser/lowering | consumed by validation/routing | not proven singleton | no | keep unchanged |

## Stage Live Set

The previous strategy treated inverse map as `0.0 MB` because it used the
post-release snapshot. That was stage-incorrect for the qret peak. At the routing
live peak, inverse map entries are live. They become zero only after
`routing_after_inverse_map_release`.

H5 current production, run 1:

| stage | observed RSS KB | uordblks KB | fordblks KB | inst count | instruction object MB | non-path operand MB | path MB | list-node MB | inverse-map MB | routing temp MB |
| ----- | --------------: | ----------: | ----------: | ---------: | --------------------: | ------------------: | ------: | -----------: | -------------: | --------------: |
| after IR JSON parse | 226,540 | 202,915 | 100 |  |  |  |  |  |  |  |
| after MachineFunction construction | 371,692 | 347,707 | 80 |  |  |  |  |  |  |  |
| routing start | 404,864 | 252,660 | 144,835 | 1,499,072 | 137.8 | 51.4 | 0.0 | 34.3 | 0.0 | 0.0 |
| routing main-loop live peak | 434,856 | 413,472 | 939 | 1,499,072 | 137.8 | 51.4 | 5.0 | 34.3 | 57.2 | 19.9 |
| before inverse-map release | 434,856 | 385,016 | 29,395 | 1,499,072 | 137.8 | 51.4 | 5.0 | 34.3 | 57.2 | 0.0 |
| after inverse-map release | 434,856 | 291,324 | 123,087 | 1,499,072 | 137.8 | 51.4 | 5.0 | 34.3 | 0.0 | 0.0 |
| calc-info start | 434,856 | 291,281 | 123,130 | 1,499,072 |  |  |  |  |  |  |
| calc-info peak | 434,856 | 414,949 | 254 | 1,499,072 |  |  |  |  |  |  |
| compile exit | 434,856 | 286 | 414,917 |  |  |  |  |  |  |  |

H5 compact singleton operand candidate at the same routing live point:

| component | current production MB | compact candidate MB | delta MB |
| --------- | --------------------: | -------------------: | -------: |
| instruction object | 137.8 | 167.3 | -29.6 |
| non-path operand containers | 51.4 | 7.0 | 44.4 |
| path storage | 5.0 | 5.0 | 0.0 |
| instruction list nodes | 34.3 | 34.3 | 0.0 |
| inverse map at routing peak | 57.2 | 57.2 | 0.0 |
| inverse map after release | 0.0 | 0.0 | 0.0 |
| metadata | 22.9 | 22.9 | 0.0 |
| routing temporary | 19.9 | 19.9 | 0.0 |

## Inverse Map

| item | observed / estimated value |
| ---- | -------------------------: |
| routing peak entries | 1,499,072 |
| routing peak estimated bytes | 59,962,880 |
| routing peak MB | 57.2 |
| after-release entries | 0 |
| after-release bytes | 0 |
| largest block entries | 1,499,048 |
| valid blocks at peak | 3 |
| released blocks after release | 3 |
| estimated node bytes | 40 |
| build count | 3 block maps at routing setup |
| insert count | 1,499,072 initial entries plus routing mutation inserts |
| erase count | not directly instrumented; source path erases replacement targets |
| lookup count | not directly instrumented |
| rebuild count | 1 per block at routing setup; lazy rebuild possible after release |

The current implementation stores `std::map<const MachineInstruction*, ConstIterator>`
inside each `MachineBasicBlock`. Compile-info and pipeline-state output iterate
instructions directly and do not need the inverse map after routing.

Lazy construction result:

| item | eager H5 median | lazy H5 median |
| ---- | --------------: | -------------: |
| max live inverse-map entries | 1,499,072 | 0 |
| constructed block count | 3 | 0 |
| never-constructed block count | 0 | 3 |
| initial inserted entries | 1,499,072 | 0 |
| qret peak RSS KB | 434,900 | 434,852 |
| median RSS saving KB |  | 48 |
| adoption | kept | rejected |

The lazy candidate remains useful as an explicit diagnostic and custom-pipeline
fallback path. It is not a production default because H5 RSS was dominated by
another live set or allocator-retained high-water mark.

Candidate structures:

| candidate | likely H5 effect | notes |
| --------- | ---------------: | ----- |
| keep `std::map` | 0 MB | current production |
| `std::unordered_map` | modest | removes tree pointers but keeps per-node allocation |
| dense instruction ID + vector | high | replaces map nodes with flat payload; needs stable IDs |
| instruction-local stable ID + vector | high | best fit if instruction list work also proceeds |
| block-local map with smaller value | medium | less invasive, still node-based unless unordered/flat |
| necessary-only partial construction | medium-high | route helpers using insert/erase must be audited first |

## H9 Estimates

The estimates use four H4->H5 models: instruction-count ratio,
instruction-type ratio, bytes-per-instruction, and component-growth. Scenario
rows combine those model outputs; they are not a single mechanically compounded
growth rate.

| scenario | variant | classification | instruction object MB | operand containers MB | path storage MB | instruction list MB | inverse map MB | metadata MB | routing temp MB | Python parent MB | total MB |
| -------- | ------- | -------------- | --------------------: | --------------------: | --------------: | ------------------: | -------------: | ----------: | --------------: | ---------------: | -------: |
| conservative | current production | estimated | 5,587.0 | 2,083.2 | 204.5 | 1,391.5 | 2,319.2 | 927.7 | 806.0 | 50.7 | 13,369.8 |
| conservative | compact operands | estimated | 6,786.2 | 285.0 | 204.5 | 1,391.5 | 2,319.2 | 927.7 | 806.0 | 50.7 | 12,770.8 |
| central | current production | estimated | 6,580.3 | 2,453.6 | 241.6 | 1,638.9 | 2,731.5 | 1,092.6 | 949.2 | 59.7 | 15,747.5 |
| central | compact operands | estimated | 7,992.7 | 337.2 | 241.9 | 1,638.9 | 2,731.5 | 1,092.6 | 949.2 | 59.7 | 15,043.7 |
| upper | current production | estimated | 8,308.4 | 3,098.0 | 863.5 | 2,069.3 | 3,448.9 | 1,379.5 | 1,198.5 | 75.4 | 20,441.5 |
| upper | compact operands | estimated | 10,110.4 | 453.6 | 863.5 | 2,073.2 | 3,455.3 | 1,382.1 | 1,200.8 | 75.5 | 19,614.3 |

| scenario | classification | compact-operand theoretical saving MB | saving % |
| -------- | -------------- | ------------------------------------: | -------: |
| conservative | theoretical | 599.0 | 4.480 |
| central | theoretical | 703.8 | 4.469 |
| upper | theoretical | 827.2 | 4.047 |

The compact singleton operand H9 estimate is useful as a model, but the H5
gate failed, so this candidate is not production.

## Next Candidate Ranking

| rank | candidate | H5 live bytes | H5 realistic saving | H9 estimated saving | peak effective | risk | scope |
| ---: | --------- | ------------: | ------------------: | ------------------: | -------------- | ---- | ----- |
| 1 | pre-routing/MachineFunction high-water reduction | broad live set | needs H5 diagnosis | high | yes | medium | IR parse, lowering/mapping temporaries, allocator retention |
| 2 | instruction object arena/flat storage | 137.8 MB | 30-60 MB | 1.3-2.6 GB | likely | high | instruction class layout and ownership |
| 3 | instruction list-node removal | 34.3 MB | 20-34 MB | 1.0-1.6 GB | likely | medium-high | `MachineBasicBlock::Container`, iterator users |
| 4 | residual operand compaction with real range API | 51.4 MB | 20-35 MB | 0.8-1.5 GB | likely | medium-high | operand APIs, no compatibility cache |
| 5 | inverse map compactization | 57.2 MB live bytes | low unless it also reduces high-water | 1.6-2.4 GB model only | no in current H5 | medium | `MachineBasicBlock` inverse map and mutation helpers |
| 6 | instruction count reduction | all instruction-scaled components | case-dependent | high | yes | high | routing/lowering semantics |
| 7 | MachineFunction chunk/stream routing | broad live set | high theoretical | high | yes | very high | routing architecture |

Next implementation candidates are limited to:

1. **Pre-routing/MachineFunction high-water audit**
   - target files/classes: IR load/lowering/mapping path plus `MachineFunction` live-set instrumentation
   - current observation: lazy inverse-map mode removes the map live set but H5 VMRSS stays flat
   - required measurement: H4/H5 only, with allocator fields at IR parse, MachineFunction build, lowering, mapping, and routing entry
   - acceptance: identify a component whose H5 RSS effect is at least 30 MB or 7%, without H6-H9 execution
   - rollback: read-only profiling first
   - H9 effect: estimated only from H4/H5 component growth

2. **Instruction object arena/flat storage**
   - target files/classes: `ScLsInstructionBase` subclasses and ownership in `MachineBasicBlock`
   - current data structure: per-instruction heap allocation behind `std::unique_ptr`
   - required API changes: preserve instruction polymorphism or introduce a stable tagged arena facade
   - H4 tests: all semantic parity plus insertion/erase/lazy rebuild tests
   - H5 A/B: only after high-water audit shows instruction objects are peak-effective
   - acceptance: same H5-only gates, with no H6-H9 execution
   - rollback: selectable legacy allocation path
   - H9 effect: model only, not measured

3. **Instruction list-node removal**
   - target files/classes: `MachineBasicBlock::Container`, routing insertion call sites
   - current data structure: `std::list<std::unique_ptr<MachineInstruction>>`
   - proposed data structure: flat/chunked owner with stable instruction pointers and ID-based positions
   - required API changes: iterator-dependent code must move to pointer/ID ranges
   - H4 tests: insertion order, replacement/erase, queue dependencies, compile-info parity
   - H5 A/B: only after high-water audit confirms list nodes are peak-effective
   - acceptance: same H5-only gates, plus targeted iterator lifetime tests
   - rollback: keep `std::list` implementation selectable at compile time
   - H9 effect: central estimate about 1.6 GB for list-node payload alone

4. **Inverse map compactization**
   - target files/classes: `qret/codegen/machine_function.{h,cpp}`
   - current data structure: `std::map<const MachineInstruction*, ConstIterator>`
   - proposed data structure: stable instruction ID plus block-local flat vector/index table
   - required API changes: keep `Contain`, `InsertBefore`, `InsertAfter`, `Erase`
   - H4 tests: insert/erase/lazy rebuild, routing replacement, validation, pipeline-state output
   - H5 A/B: only after proving inverse-map storage is still peak-effective; lazy construction showed it is not peak-effective in current H5
   - acceptance: raw/normalized parity, all candidate peaks below baseline, >=30 MB or >=7% H5 reduction, elapsed <=3% regression
   - rollback: compile-time guarded fallback to current `std::map`
   - H9 effect: central estimate about 2.7 GB for eager map nodes, but this is theoretical/model-only and not a current H5 adoption basis
