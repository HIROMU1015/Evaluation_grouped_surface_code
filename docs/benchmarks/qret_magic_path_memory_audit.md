# qret LATTICE_SURGERY_MAGIC Path Memory Audit

This is a read-only profiling audit. It does not change the production instruction schema, routing algorithm, operand API, serialization schema, or path representation. H6 was not run.

## Environment

- Evaluation HEAD at run start: `72613e4cc70567de4eabf2358ffe2bbcd5f0b8e2`
- qret executable hash: `d519cdb25446cf243053e84ffa559b7e6bd7dbd66365e1488d632208616dbbf5`
- libqret-core hash: `c19fe468aab020a1de76523e7d8ad5be9937a2ab31854fae92b863b53dc72b18`
- output root: `/home/abe/Project/Evaluation_grouped_surface_code/artifacts/qret_magic_path_memory`
- sample interval: `0.02` sec
- compile-info mode: `summary`
- summary TimeSeries: `summary_legacy_timeseries`
- DepGraph: `compact`
- inverse map release: `QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING=1`
- pipeline-state output: `skip`

## Ownership Audit

| field/container | owner | construction | mutation | last use | serialization use |
| --------------- | ----- | ------------ | -------- | -------- | ----------------- |
| condition list | ScLsInstructionBase::condition_list_ | constructor/FromJson | SetCondition in pruning or direct construction | validation, simulator, queue dependencies, compile-info | DefaultJson condition |
| qtarget | LatticeSurgeryMagic::q_ | New/FromJson/lowering | SetQubitList API; no routing path-local mutation found | runnability, route search, compile-info | DefaultJson qtarget |
| mtarget | LatticeSurgeryMagic::m_ | New/FromJson | SetMagicFactory in 2D magic routing | MagicFactory availability and RunLatticeSurgeryMagic | DefaultJson mtarget |
| basis_list | LatticeSurgeryMagic::basis_list_ | New/FromJson/lowering | no setter; copied when 3D magic is replaced by LatticeSurgery | runnability and boundary checks | ToJson basis_list |
| ancilla/path | LatticeSurgeryMagic::ancilla_ | New/FromJson; route result assigned during routing | SetPath only; temporary route may pop endpoints before assignment | runnability, RunLatticeSurgeryMagic, compile-info, pipeline-state | DefaultJson ancilla |
| metadata | ScLsInstructionBase::metadata_ | default construction/FromJson | MetadataMut during scheduling | compile-info, pipeline-state, debug output | DefaultJson metadata |

## Routing Mutation Audit

| call site | stage | operation | random insertion needed | iterator stability needed |
| --------- | ----- | --------- | ----------------------- | ------------------------- |
| SearchLatticeSurgeryMagicPath2DBFSAndRun | routing | copy route.logical_path, pop_front, pop_back, SetMagicFactory, SetPath | no | no stored-path iterator stability |
| SearchLatticeSurgeryMagicPath2DSteinerAndRun | routing | SetMagicFactory and SetPath from SearchRoute::Ancilla2D | no | no |
| SearchLatticeSurgeryMagicPath3DAndRun | routing | copy route.logical_path, pop endpoints, create LatticeSurgery, erase magic | no for retained magic path | queue handles instruction replacement, not path nodes |
| LatticeSurgeryMagic::FromJson | pipeline load | JsonToT builds list sequentially | no | no |
| IsLatticeSurgeryMagicRunnable / RunLatticeSurgeryMagic | routing simulation | read-only iteration over Path() | no | no |
| DefaultJson / ToString | serialization/debug | read-only iteration over Path() | no | no |

- `std::list` required for retained `LATTICE_SURGERY_MAGIC::ancilla_`: `no` based on audited call sites.
- Generated path read-only after assignment: `yes` for surviving `LATTICE_SURGERY_MAGIC` instructions.
- Contiguous storage feasibility: `yes`, conditional on preserving order, serialization, and route-search temporary APIs.

## H4 Instrumentation Check

| variant | profile enabled | qret peak KB | elapsed s | magic profile | raw equal | normalized equal |
| ------- | --------------: | -----------: | --------: | ------------: | --------: | ---------------: |
| profile_off | 0 | 220,840 | 5.435 | False |  |  |
| profile_on | 1 | 216,968 | 5.495 | True | True | True |

## H5 Profile Run

- qret peak RSS: `547,624` KB
- process tree peak RSS: `548,904` KB
- elapsed: `20.704` s
- max RSS stage: `routing_main_loop_peak`
- compile_info bytes: `2,172`
- Note: H5 peak was captured with profiling enabled, so it includes profiling overhead.

## Magic Path Distribution

- path count: `236,800`
- total coordinate count: `2,377,512`
- length min/median/mean/max: `1` / `10.000` / `10.040` / `25`
- p75/p90/p95/p99: `12` / `13` / `14` / `14`

| bucket | count |
| ------ | ----: |
| empty | 0 |
| length_1 | 532 |
| length_17_32 | 163 |
| length_2 | 0 |
| length_3 | 576 |
| length_33_64 | 0 |
| length_4 | 1,524 |
| length_5_8 | 84,633 |
| length_65_plus | 0 |
| length_9_16 | 149,372 |

## Coordinate Distribution

| axis | min | max | unique | negative | int8 | int16 |
| ---- | --: | --: | -----: | -------: | ---: | ----: |
| x | 0 | 9 | 10 | False | True | True |
| y | 0 | 9 | 10 | False | True | True |
| z | 0 | 0 | 1 | False | True | True |
| dx | -1 | 1 | 3 | True | True | True |
| dy | -1 | 1 | 3 | True | True | True |
| dz | 0 | 0 | 1 | False | True | True |
- unit delta ratio: `100.000%`
- Manhattan distance 1 ratio: `100.000%`
- consecutive duplicate coordinates: `0`

## Duplication

| mode | unique paths/shapes | duplicate count | duplicate % | most frequent |
| ---- | ------------------: | --------------: | ----------: | ------------: |
| exact | 320 | 236,480 | 99.865 | 27,854 |
| reverse-canonical | 320 | 236,480 | 99.865 | 27,854 |
| relative-shape | 295 | 236,505 | 99.875 | 27,877 |

- exact hash distinct collision count: `0`
- exact hash collision fallback used: `False`

## Top Exact Path Frequencies

| rank | frequency | length | first coord | last coord |
| ---: | --------: | -----: | ----------- | ---------- |
| 1 | 27,854 | 8 | `[1, 1, 0]` | `[8, 1, 0]` |
| 2 | 15,906 | 13 | `[1, 2, 0]` | `[7, 8, 0]` |
| 3 | 15,843 | 12 | `[0, 4, 0]` | `[8, 7, 0]` |
| 4 | 15,781 | 13 | `[1, 2, 0]` | `[8, 7, 0]` |
| 5 | 15,571 | 12 | `[0, 4, 0]` | `[7, 8, 0]` |
| 6 | 12,580 | 11 | `[1, 2, 0]` | `[8, 5, 0]` |
| 7 | 12,539 | 11 | `[1, 2, 0]` | `[7, 6, 0]` |
| 8 | 12,059 | 8 | `[1, 3, 0]` | `[7, 2, 0]` |
| 9 | 11,082 | 10 | `[0, 4, 0]` | `[7, 6, 0]` |
| 10 | 11,037 | 10 | `[0, 4, 0]` | `[8, 5, 0]` |

## Prefix/Suffix Sharing

| side | length | total | shared paths | shared keys |
| ---- | -----: | ----: | -----------: | ----------: |
| prefix | length_ge_2 | 236,268 | 236,267 | 11 |
| prefix | length_ge_4 | 235,692 | 235,690 | 32 |
| prefix | length_ge_8 | 206,315 | 206,309 | 87 |
| suffix | length_ge_2 | 236,268 | 236,265 | 45 |
| suffix | length_ge_4 | 235,692 | 235,685 | 62 |
| suffix | length_ge_8 | 206,315 | 206,299 | 97 |

## Segment Compressibility

- total segments: `527,139`
- coordinates per segment mean: `4.510`
- one segment or less: `21.660%`
- two segments or less: `62.991%`
- four segments or less: `99.841%`
- max segment count: `7`

## Memory Breakdown

| component | observed count | estimated bytes | MB | note |
| --------- | -------------: | --------------: | --: | ---- |
| instruction object | 236,800 | 39,782,400 | 37.9 | includes list object bodies |
| qtarget list nodes | 236,800 | 5,683,200 | 5.4 | sizeof estimate |
| basis list nodes | 236,800 | 4,025,600 | 3.8 | LSM-specific operand |
| condition list nodes | 0 | 0 | 0.0 | base operand |
| ccreate list nodes | 236,800 | 5,683,200 | 5.4 | measurement output |
| mtarget list nodes | 236,800 | 5,683,200 | 5.4 | magic factory |
| path Coord3D payload | 2,377,512 | 28,530,144 | 27.2 | raw data only |
| path list pointer overhead | 2,377,512 | 38,040,192 | 36.3 | two pointers per node estimate |
| path allocator alignment overhead | 2,377,512 | 9,510,048 | 9.1 | aligned-node estimate |
| path list object bodies | 236,800 | 5,683,200 | 5.4 | inside instruction object |

All byte totals except counts are estimates from `sizeof` and a simple list-node model. The C++ standard does not define `std::list` node layout.

## All MachineFunction Ancilla/Path

- LATTICE_SURGERY_MAGIC ancilla/path bytes: `63.5` MB
- CNOT ancilla/path bytes: `4.9` MB
- other instruction ancilla/path bytes: `0.0` MB
- all ancilla/path bytes: `68.4` MB

## Theoretical Representation Sizes

| representation | estimated MB | saving MB | saving % | semantic risk | implementation risk |
| -------------- | -----------: | --------: | -------: | ------------- | ------------------- |
| std::list<Coord3D> current aligned estimate | 78.0 | 0.0 | 0.000 | none | none |
| std::vector<Coord3D> capacity==size | 32.6 | 45.3 | 58.156 | low | low |
| std::vector<Coord3D> next-power-of-two capacity | 40.7 | 37.3 | 47.829 | low | low |
| inline4 + overflow vector | 34.5 | 43.5 | 55.807 | low | medium |
| inline8 + overflow vector | 35.3 | 42.7 | 54.728 | low | medium |
| flat pool + offset no sharing | 29.0 | 49.0 | 62.790 | low | medium |
| flat pool + exact path interning | 1.0 | 77.0 | 98.781 | low | medium |
| flat pool + reverse canonical interning | 1.2 | 76.8 | 98.492 | medium | medium |
| relative shape pool + origin | 3.7 | 74.3 | 95.310 | medium | high |
| segment representation | 8.5 | 69.4 | 89.050 | medium | high |

These are ancilla/path-field estimates. RSS can fall by less because malloc arenas may retain freed pages and because replacing containers changes allocation timing.

## Candidate Ranking

| rank | candidate | theoretical saving MB | ancilla/path saving % | required code scope | semantic risk |
| ---: | --------- | --------------------: | --------------------: | ------------------- | ------------- |
| 1 | std::vector<Coord3D> | 45.3 | 58.156 | path container/API-compatible storage | low |
| 2 | flat pool + exact path interning | 77.0 | 98.781 | path container/API-compatible storage | low |

## Conclusions

1. H4 raw metrics equal: `True`.
2. H4 normalized metrics equal: `True`.
3. The next implementation candidate should be selected from the ranking above, capped at two candidates.
4. H6 was not run.
