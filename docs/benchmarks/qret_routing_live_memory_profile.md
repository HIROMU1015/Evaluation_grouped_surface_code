# qret Routing Live Memory Profile

H6 was not run. This profile uses H4 for instrumentation validation and H5 for candidate selection only.

## Environment

- Evaluation HEAD: `2e65a2f4598e88b879bbb5a2d056fdd5949492c3`
- qret executable hash: `d519cdb25446cf243053e84ffa559b7e6bd7dbd66365e1488d632208616dbbf5`
- libqret-core hash: `daafaad311548477ce29bccb4de4377bd1a7b37e1ceee42ee7f0823026ad62c0`
- compiler: `c++ (Ubuntu 11.4.0-1ubuntu1~22.04) 11.4.0`
- allocator: `glibc malloc/mallinfo2 when mallinfo2_supported=true`
- MemTotal KB: `65522476`
- SwapTotal KB: `2097148`
- disk free bytes at start: `12909961216`
- output root: `/home/abe/Project/Evaluation_grouped_surface_code/artifacts/qret_routing_live_memory`
- build requested: `True`

## Run Summary

| case | variant | runs | median peak KB | median elapsed sec | max stage | missing markers |
| ---- | ------- | ---: | -------------: | -----------------: | --------- | --------------- |
| H4 `4th(new_2)` | baseline | 1 | 248,324 | 5.622 | calc_info_with_topology_after_summary_accumulation |  |
| H4 `4th(new_2)` | trim_after_json_destroy | 1 | 249,188 | 5.657 | calc_info_with_topology_after_summary_stats_store |  |
| H4 `4th(new_2)` | trim_after_routing_temporary_destroy | 1 | 249,344 | 5.780 | calc_info_with_topology_after_summary_accumulation |  |
| H5 `4th(new_2)` | baseline | 2 | 640,514 | 22.326 | calc_info_with_topology_after_summary_accumulation |  |
| H5 `4th(new_2)` | trim_after_json_destroy | 1 | 641,160 | 22.384 | calc_info_with_topology_after_summary_accumulation |  |
| H5 `4th(new_2)` | trim_after_routing_temporary_destroy | 1 | 640,756 | 22.653 | calc_info_with_topology_after_summary_accumulation |  |

- H5 baseline median peak KB: `640,514`
- H4 baseline median peak KB: `248,324`
- `trim_both` run: `False`

## Lifetime Audit

| object | construction | destruction | live at routing exit | estimated bytes |
| ------ | ------------ | ----------- | -------------------- | --------------: |
| IR file stream/input buffer | before_ir_file_read | stream closed when LoadFunctionFromIR returns | no explicit full input buffer | 23,111,215 |
| parsed JSON DOM | after_ir_json_parse | after_ir_json_dom_destroy | no | 167,650,424 |
| MachineFunction/instructions/metadata | before_lowering/after_lowering | compile exit | yes | 386,065,620 |
| routing InstQueue/state/simulator | routing_after_queue_construct/routing_after_state_construct | routing_after_temporary_destroy | no | 21,358,160 |
| DepGraph | calc_info_without_topology | after calc_info_without_topology | not constructed yet |  |
| compile-info object | init_compile_info / calc_info passes | compile exit | partially initialized |  |

## Stage Memory

| stage | RSS KB | PSS KB | PrivateDirty KB | uordblks KB | fordblks KB |
| ----- | -----: | -----: | --------------: | ----------: | ----------: |
| compile_entry | 7,168 | 4,051 | 456 | 212 | 51 |
| before_ir_file_read | 7,424 | 4,348 | 496 | 236 | 27 |
| after_ir_file_read | 7,424 | 4,352 | 500 | 244 | 19 |
| before_ir_json_parse | 7,424 | 4,352 | 500 | 244 | 19 |
| after_ir_json_parse | 226,544 | 223,612 | 219,696 | 202,832 | 51 |
| before_load_json | 226,544 | 223,680 | 219,700 | 202,834 | 49 |
| after_load_json_machine_function_built | 371,696 | 368,540 | 364,432 | 347,570 | 137 |
| before_ir_json_dom_destroy | 371,696 | 368,544 | 364,436 | 347,573 | 134 |
| after_ir_json_dom_destroy | 379,888 | 376,500 | 372,392 | 144,976 | 227,303 |
| before_input_buffer_destroy | 379,888 | 376,500 | 372,392 | 144,976 | 227,303 |
| after_input_buffer_destroy | 379,888 | 376,500 | 372,392 | 144,976 | 227,303 |
| before_lowering | 379,888 | 376,564 | 372,392 | 144,979 | 227,300 |
| after_lowering | 431,088 | 428,408 | 424,108 | 423,859 | 32 |
| before_mapping | 431,088 | 428,420 | 424,120 | 279,125 | 144,766 |
| after_mapping | 431,088 | 428,420 | 424,120 | 279,126 | 144,765 |
| routing_entry | 431,088 | 428,420 | 424,120 | 279,130 | 144,761 |
| routing_after_queue_construct | 431,088 | 428,484 | 424,120 | 372,792 | 51,099 |
| routing_after_state_construct | 431,088 | 428,548 | 424,120 | 372,842 | 51,049 |
| routing_after_initial_peek | 431,088 | 428,548 | 424,120 | 373,708 | 50,183 |
| routing_main_loop_peak | 545,776 | 543,435 | 539,000 | 537,692 | 1,175 |
| routing_main_loop_exit | 547,568 | 545,355 | 540,920 | 539,160 | 1,555 |
| routing_before_temporary_destroy | 547,568 | 545,355 | 540,920 | 539,160 | 1,555 |
| routing_after_temporary_destroy | 547,568 | 545,355 | 540,920 | 510,178 | 30,537 |
| routing_pass_exit | 547,568 | 545,355 | 540,920 | 510,178 | 30,537 |
| before_calc_info_without_topology | 547,568 | 545,355 | 540,920 | 510,175 | 30,540 |
| after_calc_info_without_topology | 614,640 | 612,331 | 607,896 | 510,184 | 108,859 |
| before_calc_info_with_topology | 614,640 | 612,331 | 607,896 | 510,183 | 108,860 |
| after_calc_info_with_topology | 641,008 | 638,731 | 634,296 | 510,186 | 123,897 |
| compile_exit | 641,008 | 638,731 | 634,296 | 270 | 633,813 |

## Object Estimates

| object | count | estimated payload MB | notes |
| ------ | ----: | -------------------: | ----- |
| JSON DOM | 1,063,075 | 159.9 | nlohmann JSON dynamic payload estimate, not RSS |
| MachineFunction | 1,498,544 | 368.2 | instructions, list nodes, metadata, inverse maps |
| routing temporary | 2,000 | 20.4 | InstQueue plus simulator/state estimates |
| raw instruction strings | 0 | 0.0 | MachineFunction does not retain raw JSON strings |
| metadata | 1,498,544 | 22.9 | ScLsMetadata objects |

## Trim Diagnostics

| variant | trim stage | pre RSS KB | post RSS KB | RSS drop KB | uordblks drop KB | elapsed sec |
| ------- | ---------- | ----------: | -----------: | ----------: | --------------: | ----------: |
| trim_after_json_destroy | after_json_dom_destroy | 146,160 | 63,472 | 82,688 | -1 | 0.001165 |
| trim_after_routing_temporary_destroy | after_routing_temporary_destroy | 216,324 | 213,504 | 2,820 | 0 | 0.000543 |
| trim_after_json_destroy | after_json_dom_destroy | 379,820 | 152,456 | 227,364 | 0 | 0.004354 |
| trim_after_routing_temporary_destroy | after_routing_temporary_destroy | 546,944 | 541,684 | 5,260 | 0 | 0.019941 |

## Candidate Ranking

| rank | candidate | theoretical saving MB | measured evidence | risk | priority |
| ---: | --------- | --------------------: | ----------------- | ---- | -------- |
| 1 | MachineFunction live object | 368.2 | estimated live MachineFunction payload at routing/calc stages | medium/high; instruction ownership or schema changes are risky | proposal_only |
| 2 | JSON DOM allocator retention | 222.0 | trim drop 227,364 KB after JSON DOM destroy; H5 peak saving 0 KB | low for lifetime audit; production trim is out of scope | report_only |
| 3 | routing temporary allocator retention | 20.4 | trim drop 5,260 KB after routing temporary destroy; H5 peak saving 0 KB | low for scope/lifetime changes; malloc_trim is out of scope | report_only |

## Optimization A/B

No production optimization was implemented in this commit. Gate-passing evidence points to MachineFunction live payload, which is a higher-risk ownership/schema change. Diagnostic `malloc_trim` is not a production optimization.

## Final Answers

1. JSON DOM estimated payload MB: `159.9`.
2. JSON DOM uordblks decrease after destroy: `202,597` KB.
3. JSON DOM destroy RSS delta: `8,192` KB; when RSS does not drop with uordblks falling, the main diagnosis is allocator-retained heap and/or later live-object growth rather than a still-live JSON DOM.
4. Diagnostic trim effect: see table above; `trim_both` run was `False`.
5. MachineFunction estimated payload MB: `368.2`.
6. raw string MB: `0.0`; metadata MB: `22.9`.
7. routing temporary estimated payload MB: `20.4`.
8. routing pass local InstQueue/simulator containers are marked after temporary destruction; remaining live payload is MachineFunction/compile state.
9. H5 max RSS stage: `calc_info_with_topology_after_summary_accumulation`.
10. Candidate meeting 100 MB/10%/150 MB gate: `True`.
11. production optimization implemented: `False` in this profiling commit.
12. optimization A/B H5 peak reduction: not applicable.
13. if not implemented, reason: the gate-passing qret-side candidate is MachineFunction live payload, which requires higher-risk instruction/container ownership work; JSON trim did not reduce H5 peak and production malloc_trim is forbidden.
14. malloc_trim is diagnostic only and is not proposed as production default.
15. next priority: use the candidate ranking above; if none passes, move to parent process/compile-info read path before H6.
16. Python parent process should be considered only after qret-side candidates fail the gate.
17. H6 was not run.

## Correctness

- raw qret metrics equal across measured trim variants: `True`
- normalized metrics equal across measured trim variants: `True`
- compact DepGraph and compile-info mode compatibility are covered by the C++/Python validation suite.
