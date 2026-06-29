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

Phase 3 measured pre-routing and MachineFunction high-water stages with bounded
read-only instrumentation. It did not add a production optimization. The H5
high-water was already formed before the routing main loop, and lazy inverse-map
construction again changed allocator in-use bytes without changing qret peak RSS.

| phase | case | variant | observed runs | qret peak KB | elapsed s | first max VmHWM stage | decision |
| ----- | ---- | ------- | ------------: | ------------: | --------: | --------------------- | -------- |
| Phase 3 | H5 `4th(new_2)` | eager high-water profile | 1 | 434,864 | 19.135 | `routing_after_splitter_construct` | kept |
| Phase 3 | H5 `4th(new_2)` | lazy high-water profile | 1 | 434,816 | 18.973 | `routing_after_splitter_construct` | diagnostic only |
| Phase 3 | H5 `4th(new_2)` | eager + trim after inverse release | 1 | 435,048 | 19.357 | `after_machine_function_construction` | diagnostic only |

Phase 3 H4 raw and normalized metrics matched across profile-off/profile-on,
eager/lazy, and diagnostic trim variants. H5 was run only after H4 parity passed.
The detailed report is
[`qret_pre_routing_high_water_audit.md`](qret_pre_routing_high_water_audit.md).

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

The high-water audit shows that H5 reaches current peak RSS before the routing
main loop. The JSON DOM does not overlap with MachineFunction high-water enough
to explain the peak: `after_json_parse_or_dom_build` reached `226,076 KB`
VmRSS, then the DOM was destroyed before lowering. MachineFunction construction
alone reached `434,608 KB`, and routing setup lifted the process to `434,864 KB`.

H5 high-water profile, eager production-equivalent mode:

| stage | VmRSS KB | VmHWM KB | uordblks KB | fordblks KB | conclusion |
| ----- | -------: | -------: | ----------: | ----------: | ---------- |
| after JSON parse / DOM build | 226,076 | 239,616 | 202,917 | 98 | JSON DOM is large but below peak |
| before MachineFunction construction | 379,568 | 412,444 | 145,048 | 227,371 | source IR remains live; allocator retains earlier pages |
| during MachineFunction construction | 415,920 | 415,920 | 408,982 | 137 | construction pushes live allocator bytes near peak |
| after MachineFunction construction | 434,608 | 434,608 | 427,747 | 116 | peak is effectively formed before routing |
| routing entry | 434,608 | 434,608 | 282,932 | 144,931 | RSS remains high after lowering frees |
| routing setup / first max | 434,864 | 434,864 | 377,611 | 50,252 | first observed H5 max VmHWM stage |
| before inverse-map release | 434,864 | 434,864 | 388,032 | 39,831 | eager inverse map is live |
| after inverse-map release | 434,864 | 434,864 | 294,344 | 133,519 | inverse map freed, RSS retained |
| compile-info peak | 434,864 | 434,864 | 416,222 | 11,641 | later pass reuses retained heap arena |
| before process exit | 434,864 | 434,864 | 297 | 427,566 | freed heap remains mapped until exit |

H5 MachineFunction and related component estimates at the peak-relevant stage:

| component | classification | H5 value |
| --------- | -------------- | -------: |
| instruction count | observed | 1,499,072 |
| instruction object bytes | theoretical | 144,451,120 bytes / 137.8 MB |
| non-path/path operand container bytes | theoretical | 59,136,892 bytes / 56.4 MB |
| interned path dynamic bytes | theoretical | 116,292 bytes / 0.1 MB |
| instruction list-node bytes | theoretical | 35,977,728 bytes / 34.3 MB |
| inverse-map entries | observed | 1,499,072 eager / 0 lazy |
| inverse-map bytes | theoretical | 59,962,880 bytes / 57.2 MB |
| metadata bytes | theoretical | 23,985,152 bytes / 22.9 MB |
| routing temporary bytes | theoretical | 21,133,864 bytes / 20.2 MB |
| compact DepGraph nodes / edges | observed | 1,499,072 / 1,533,838 |
| compact DepGraph payload bytes | theoretical | 62,324,224 bytes / 59.4 MB |

The allocator evidence is now concrete: inverse-map release drops `uordblks` by
about `93,688 KB` while VmRSS stays flat, and compile-info later increases
`uordblks` back to `416,222 KB` without increasing VmRSS. The freed heap arena is
therefore retained by glibc and reused by later passes. Diagnostic `malloc_trim`
after inverse-map release dropped H5 VmRSS by `108,736 KB`, but only after the
process had already reached its high-water; it is not a production optimization.

## H9 Estimates

H9 remains unmeasured. The current extrapolation uses observed H4/H5 component
growth and keeps `observed`, `estimated`, and `theoretical` labels separate.

| component | H5 theoretical MB | H9 central estimated MB | note |
| --------- | ----------------: | ----------------------: | ---- |
| instruction objects | 137.8 | 6,572.9 | biggest peak-effective resident payload |
| operand containers | 56.4 | 2,690.9 | only useful if redesigned without compatibility caches |
| instruction list nodes | 34.3 | 1,637.1 | smaller H5 payload but direct live-set removal |
| inverse map | 57.2 | 2,728.5 | not peak-effective in current H5 evidence |
| metadata | 22.9 | 1,091.4 | coupled to instruction layout |

These H9 values are estimates only. They should guide priority only after the H5
peak-effectiveness test passes.

## Next Candidate Ranking

| rank | candidate | H5 expected peak saving | classification | H9 estimated effect | peak effective | risk | decision |
| ---: | --------- | ----------------------: | -------------- | ------------------: | -------------- | ---- | -------- |
| 1 | instruction object arena / flat storage | about 35 MB from a conservative 25% object reduction | theoretical | about 1.6 GB at the same 25% model | yes | high | next implementation candidate |
| 2 | instruction list-node removal | about 35 MB if list nodes are eliminated | theoretical | about 1.6 GB | yes | medium-high | good second candidate or combined design input |
| 3 | residual operand API redesign | about 35 MB from 60% container reduction | theoretical | about 1.6 GB at the same model | yes | medium-high | useful only without owner-side compatibility caches |
| 4 | allocator strategy / process isolation | 0 MB same-process peak; 108 MB post-peak RSS trim observed | observed | unknown | no for current process | medium | design only; needs a safe serialization boundary |
| 5 | inverse-map compactization / lazy default | 48 KB observed lazy-vs-eager peak movement | observed | about 2.7 GB theoretical map payload | no in current H5 | medium | do not adopt as next production optimization |
| 6 | instruction count reduction | case-dependent | unresolved | high | yes | high | separate algorithmic project |
| 7 | chunk / stream routing | potentially high | unresolved | high | yes | very high | not next without a MachineFunction artifact design |

Next implementation should target **instruction object arena / flat storage**.
The acceptance gate remains H5-only: raw and normalized metrics must match,
production defaults must stay unchanged, H6-H9 must not be executed, and the H5
qret peak must move by at least `30 MB` or `7%`. The immediate design work is:

1. Add a selectable legacy/arena allocation path for `ScLsInstructionBase`
   subclasses without changing instruction semantics.
2. Preserve stable instruction pointers or introduce a stable ID facade before
   touching routing insertion/erase code.
3. Keep inverse-map construction eager by default and release-after-routing
   enabled, so the comparison isolates instruction storage.
4. Run H4 semantic parity first, then one H5 eager production-equivalent profile.
5. Treat H9 only as an estimated model until an H5 candidate passes the gate.
