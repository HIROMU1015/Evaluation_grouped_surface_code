# qret Lazy Inverse Map Optimization

## Execution Limits

- largest measured case: `H5`
- H6 executed: `False`
- H7 executed: `False`
- H8 executed: `False`
- H9 executed: `False`
- H9 memory: estimated from observed H4/H5 values, not measured.
- H9 labels used below: `observed`, `estimated`, `theoretical`

## Production Configuration Under Test

- magic path storage: `interned`
- non-path operands: legacy containers
- compile-info output: `summary`
- summary TimeSeries: `legacy_timeseries`
- DepGraph: `compact`
- inverse-map release after routing: enabled
- pipeline-state output: skipped
- inverse-map construction switch: `QRET_INVERSE_MAP_CONSTRUCTION=eager|lazy`
- production default after this H5 gate: `eager`; `lazy` remains an explicit candidate mode.
- post-measurement default rollback: `True`; A/B runs used explicit env modes and were not rerun after the default-only change to respect the H5 run cap.

## Source Call-Site Audit

| call site | stage | eager/lazy | required reason | removable |
| --------- | ----- | ---------- | --------------- | --------- |
| `routing.cpp` setup loop | after validation, before queue/simulator setup | eager in `eager`, skipped in `lazy` | old production built all block maps before routing; source audit found no direct setup dependency | yes, behind runtime switch |
| `MachineBasicBlock::EnsureInverseMap` | helper entry | lazy | rebuilds only the target block on demand | no |
| `Contain` | simulator/search block lookup | lazy | must find the owner block for a specific instruction pointer | no |
| `InsertBefore` / `InsertAfter` / `Erase` | routing mutation and pruning | lazy | mutations need pointer-to-iterator lookup in the touched block | no |
| `MachineFunction::ReleaseInverseMaps` | after routing temporaries | release | frees valid maps and records the block universe | no |
| `runtime_simulation_pruning.cpp` | standalone pruning pass | eager per block | pass iterates and mutates the same block; retained for custom pipeline compatibility | no change |

Validation runs before either construction mode. Lazy mode enters routing setup with maps unbuilt; the first `Contain`, `InsertBefore`, `InsertAfter`, or `Erase` call constructs only that block.

## Direct Mutation Audit

- `MachineBasicBlock::EmplaceBack` remains the only public append helper and synchronizes the map when it is already valid; otherwise it leaves construction deferred.
- `MachineFunction::AddBlock`, `InsertBlock`, `Erase`, and `Clear` only mutate the block list, not instruction lists.
- External direct access to the private `instructions_` container was not found in `qret/src`; routing mutations use the inverse-map APIs.

## Run Matrix

| case | variant | requested runs | observed runs | median qret peak KB | median routing peak KB | median elapsed s | median max live entries |
| ---- | ------- | -------------: | ------------: | ------------------: | ---------------------: | ---------------: | ----------------------: |
| H4 `4th(new_2)` | eager | 1 | 1 | 171,212 | 168,616 | 4.678 | 570,378 |
| H4 `4th(new_2)` | lazy | 1 | 1 | 170,872 | 165,792 | 4.587 | 0 |
| H5 `4th(new_2)` | eager | 2 | 2 | 434,900 | 434,900 | 18.091 | 1,499,072 |
| H5 `4th(new_2)` | lazy | 2 | 2 | 434,852 | 434,852 | 17.919 | 0 |

## Metric Parity

| comparison | raw equal | normalized equal | raw mismatches | normalized mismatches |
| ---------- | --------: | ---------------: | -------------- | --------------------- |
| h4_4th_new2:lazy:run_1 | True | True | [] | [] |
| h5_4th_new2:lazy:run_1 | True | True | [] | [] |
| h5_4th_new2:lazy:run_2 | True | True | [] | [] |

## H5 A/B Details

| variant | run | qret peak KB | tree peak KB | routing entry KB | routing main peak KB | before release KB | after release KB | calc-info peak KB | elapsed s | uordblks KB | fordblks KB | constructed blocks | never constructed blocks | max live entries |
| ------- | --: | -----------: | -----------: | ---------------: | -------------------: | ----------------: | ---------------: | ----------------: | --------: | ----------: | ----------: | -----------------: | -----------------------: | ---------------: |
| eager | 1 | 434,780 | 436,060 | 434,780 | 434,780 | 434,780 | 434,780 | 434,780 | 18.119 | 388,014 | 39,841 | 3 | 0 | 1,499,072 |
| eager | 2 | 435,020 | 436,300 | 435,020 | 435,020 | 435,020 | 435,020 | 435,020 | 18.063 | 388,014 | 39,841 | 3 | 0 | 1,499,072 |
| lazy | 1 | 434,728 | 436,008 | 434,728 | 434,728 | 434,728 | 434,728 | 434,728 | 17.901 | 294,324 | 133,531 | 0 | 3 | 0 |
| lazy | 2 | 434,976 | 436,256 | 434,976 | 434,976 | 434,976 | 434,976 | 434,976 | 17.938 | 294,324 | 133,531 | 0 | 3 | 0 |

## H5 Adoption Gate

- H4 raw/normalized parity: `True`
- H5 raw/normalized parity: `True`
- summary schema compatible: `True`
- pipeline-state serialization compatible: `True`
- targeted lazy fallback tests required: `True`
- custom pipeline lazy rebuild tests required: `True`
- H5 median qret peak reduction KB: `48`
- H5 median qret peak reduction percent: `0.011`
- all lazy runs below eager: `False`
- elapsed regression percent: `-0.951`
- elapsed gate <=3%: `True`
- H5 max live entries reduction percent: `100.000`
- H5 max live gate: `True`
- pool lifetime leak observed: `False`
- production candidate adopted by H5 measurement: `False`

## Safety

H5 runs recorded `MemTotal`, `MemAvailable`, `SwapTotal`, `SwapFree`, and disk free before execution. H6-H9 are rejected by script guard and test guard.

| case | variant | run | MemTotal KB | MemAvailable KB | SwapTotal KB | SwapFree KB | disk free bytes |
| ---- | ------- | --: | ----------: | --------------: | -----------: | ----------: | --------------: |
| H5 `4th(new_2)` | eager | 1 | 65,522,476 | 54,441,028 | 2,097,148 | 296,648 | 12,917,063,680 |
| H5 `4th(new_2)` | eager | 2 | 65,522,476 | 54,512,192 | 2,097,148 | 296,648 | 12,910,268,416 |
| H5 `4th(new_2)` | lazy | 1 | 65,522,476 | 54,516,900 | 2,097,148 | 296,648 | 12,903,501,824 |
| H5 `4th(new_2)` | lazy | 2 | 65,522,476 | 54,509,736 | 2,097,148 | 296,648 | 12,896,911,360 |

## H9 Estimates

H9 was not run. These estimates combine instruction-count ratio, instruction-type count ratio, bytes-per-instruction, and component-growth models from observed H4/H5 values.

- observed classification present: `observed`
- estimated classification present: `estimated`
- theoretical classification present: `theoretical`

| scenario | variant | classification | component | MB |
| -------- | ------- | -------------- | --------- | --: |
| central | current_production_eager | estimated | instruction_object | 6548.2 |
| central | current_production_eager | estimated | operand_containers | 2440.5 |
| central | current_production_eager | estimated | path_storage | 240.3 |
| central | current_production_eager | estimated | instruction_list_nodes | 1637.1 |
| central | current_production_eager | estimated | inverse_map | 2728.5 |
| central | current_production_eager | estimated | metadata | 1091.4 |
| central | current_production_eager | estimated | routing_temporary | 934.3 |
| central | current_production_eager | estimated | python_parent | 58.8 |
| central | current_production_eager | estimated | total | 15679.0 |
| central | with_lazy_inverse_map_candidate | estimated | instruction_object | 6548.2 |
| central | with_lazy_inverse_map_candidate | estimated | operand_containers | 2440.5 |
| central | with_lazy_inverse_map_candidate | estimated | path_storage | 240.3 |
| central | with_lazy_inverse_map_candidate | estimated | instruction_list_nodes | 1637.1 |
| central | with_lazy_inverse_map_candidate | estimated | inverse_map | 0.0 |
| central | with_lazy_inverse_map_candidate | estimated | metadata | 1091.4 |
| central | with_lazy_inverse_map_candidate | estimated | routing_temporary | 927.1 |
| central | with_lazy_inverse_map_candidate | estimated | python_parent | 58.3 |
| central | with_lazy_inverse_map_candidate | estimated | total | 12942.9 |
| conservative | current_production_eager | estimated | instruction_object | 5544.9 |
| conservative | current_production_eager | estimated | operand_containers | 2065.5 |
| conservative | current_production_eager | estimated | path_storage | 204.0 |
| conservative | current_production_eager | estimated | instruction_list_nodes | 1391.5 |
| conservative | current_production_eager | estimated | inverse_map | 2319.2 |
| conservative | current_production_eager | estimated | metadata | 927.7 |
| conservative | current_production_eager | estimated | routing_temporary | 782.4 |
| conservative | current_production_eager | estimated | python_parent | 49.2 |
| conservative | current_production_eager | estimated | total | 13284.5 |
| conservative | with_lazy_inverse_map_candidate | estimated | instruction_object | 5544.9 |
| conservative | with_lazy_inverse_map_candidate | estimated | operand_containers | 2065.5 |
| conservative | with_lazy_inverse_map_candidate | estimated | path_storage | 204.0 |
| conservative | with_lazy_inverse_map_candidate | estimated | instruction_list_nodes | 1391.5 |
| conservative | with_lazy_inverse_map_candidate | estimated | inverse_map | 0.0 |
| conservative | with_lazy_inverse_map_candidate | estimated | metadata | 927.7 |
| conservative | with_lazy_inverse_map_candidate | estimated | routing_temporary | 770.2 |
| conservative | with_lazy_inverse_map_candidate | estimated | python_parent | 48.4 |
| conservative | with_lazy_inverse_map_candidate | estimated | total | 10952.3 |
| upper | current_production_eager | estimated | instruction_object | 8234.4 |
| upper | current_production_eager | estimated | operand_containers | 3070.4 |
| upper | current_production_eager | estimated | path_storage | 863.5 |
| upper | current_production_eager | estimated | instruction_list_nodes | 2050.9 |
| upper | current_production_eager | estimated | inverse_map | 3418.2 |
| upper | current_production_eager | estimated | metadata | 1367.3 |
| upper | current_production_eager | estimated | routing_temporary | 1187.9 |
| upper | current_production_eager | estimated | python_parent | 74.7 |
| upper | current_production_eager | estimated | total | 20267.3 |
| upper | with_lazy_inverse_map_candidate | estimated | instruction_object | 8234.4 |
| upper | with_lazy_inverse_map_candidate | estimated | operand_containers | 3070.4 |
| upper | with_lazy_inverse_map_candidate | estimated | path_storage | 863.5 |
| upper | with_lazy_inverse_map_candidate | estimated | instruction_list_nodes | 2050.9 |
| upper | with_lazy_inverse_map_candidate | estimated | inverse_map | 0.0 |
| upper | with_lazy_inverse_map_candidate | estimated | metadata | 1367.3 |
| upper | with_lazy_inverse_map_candidate | estimated | routing_temporary | 1187.9 |
| upper | with_lazy_inverse_map_candidate | estimated | python_parent | 74.7 |
| upper | with_lazy_inverse_map_candidate | estimated | total | 16849.1 |

| scenario | classification | lazy inverse-map theoretical saving MB | saving % |
| -------- | -------------- | ------------------------------------: | -------: |
| central | theoretical | 2736.1 | 17.451 |
| conservative | theoretical | 2332.2 | 17.556 |
| upper | theoretical | 3418.2 | 16.866 |

## Provenance

| case | variant | run | Evaluation HEAD | qret hash | lib hash | optimized IR hash | topology hash | pipeline hash | mode |
| ---- | ------- | --: | --------------- | --------- | -------- | ----------------- | ------------- | ------------- | ---- |
| H4 `4th(new_2)` | eager | 1 | `9b8b7e61a616f2b895b7b1787a45d6ec7a750390` | `d519cdb25446cf243053e84ffa559b7e6bd7dbd66365e1488d632208616dbbf5` | `0b9b3a08bb983ca53b8e6847e28702c786189cc565f3e513ab8186693ec1129f` | `fff1b0d259fd6c0db72f498aa1d1d063fc32c2dbe8b9f8744bc05ac7bacb2a84` | `b7a81d54181fdc7985f026501290417a9bf8356773b7113466245d452b253b89` | `a94211c6b4ccd25f951d804b044e06483ddbc898c8a45cbeb452d2579d4f10a1` | `eager` |
| H4 `4th(new_2)` | lazy | 1 | `9b8b7e61a616f2b895b7b1787a45d6ec7a750390` | `d519cdb25446cf243053e84ffa559b7e6bd7dbd66365e1488d632208616dbbf5` | `0b9b3a08bb983ca53b8e6847e28702c786189cc565f3e513ab8186693ec1129f` | `fff1b0d259fd6c0db72f498aa1d1d063fc32c2dbe8b9f8744bc05ac7bacb2a84` | `b7a81d54181fdc7985f026501290417a9bf8356773b7113466245d452b253b89` | `9efcd40132d4e9109a3d033390b3cad47cfa4ce26a2af1cef1ef3b410efb569d` | `lazy` |
| H5 `4th(new_2)` | eager | 1 | `9b8b7e61a616f2b895b7b1787a45d6ec7a750390` | `d519cdb25446cf243053e84ffa559b7e6bd7dbd66365e1488d632208616dbbf5` | `0b9b3a08bb983ca53b8e6847e28702c786189cc565f3e513ab8186693ec1129f` | `18ea2695b70f5a408c815f8373e69ac178d518c77ffb7acb5c14c2085d82d1db` | `b7a81d54181fdc7985f026501290417a9bf8356773b7113466245d452b253b89` | `3a994a49a74294315045bf2c4585b020e65511a123810279b6d541a665e61b93` | `eager` |
| H5 `4th(new_2)` | eager | 2 | `9b8b7e61a616f2b895b7b1787a45d6ec7a750390` | `d519cdb25446cf243053e84ffa559b7e6bd7dbd66365e1488d632208616dbbf5` | `0b9b3a08bb983ca53b8e6847e28702c786189cc565f3e513ab8186693ec1129f` | `18ea2695b70f5a408c815f8373e69ac178d518c77ffb7acb5c14c2085d82d1db` | `b7a81d54181fdc7985f026501290417a9bf8356773b7113466245d452b253b89` | `91545e81d65daba4aa05ab32f92cd277ac7643be394249662013225480e94ccc` | `eager` |
| H5 `4th(new_2)` | lazy | 1 | `9b8b7e61a616f2b895b7b1787a45d6ec7a750390` | `d519cdb25446cf243053e84ffa559b7e6bd7dbd66365e1488d632208616dbbf5` | `0b9b3a08bb983ca53b8e6847e28702c786189cc565f3e513ab8186693ec1129f` | `18ea2695b70f5a408c815f8373e69ac178d518c77ffb7acb5c14c2085d82d1db` | `b7a81d54181fdc7985f026501290417a9bf8356773b7113466245d452b253b89` | `967e0d631208a155950a0c63fd6e31c53d0b52d153ac4c4e39560106f2649e04` | `lazy` |
| H5 `4th(new_2)` | lazy | 2 | `9b8b7e61a616f2b895b7b1787a45d6ec7a750390` | `d519cdb25446cf243053e84ffa559b7e6bd7dbd66365e1488d632208616dbbf5` | `0b9b3a08bb983ca53b8e6847e28702c786189cc565f3e513ab8186693ec1129f` | `18ea2695b70f5a408c815f8373e69ac178d518c77ffb7acb5c14c2085d82d1db` | `b7a81d54181fdc7985f026501290417a9bf8356773b7113466245d452b253b89` | `0c1c331e0bf0d33cec92ca6a01720b84a78d545070901261910146b780c669b3` | `lazy` |

## Decision

- production default after this phase: `eager`.
- lazy mode was not adopted because the H5 RSS gate failed despite raw/normalized metric parity and zero live inverse-map entries.
- custom pipelines are not assumed to keep inverse-map usage at zero; lazy mode rebuilds on demand per block.
- H6/H7/H8/H9 execution remains prohibited.
