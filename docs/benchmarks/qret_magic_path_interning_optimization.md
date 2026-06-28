# qret Exact Magic Path Interning A/B

## Execution Limits

- largest measured case: `H5`
- H6 executed: `False`
- H7 executed: `False`
- H8 executed: `False`
- H9 executed: `False`
- H9 memory: estimated from observed H4/H5 values, not measured.
- unique vector diagnostic: `not run`; exact interner counters were sufficient.

## Implementation Notes

- `QRET_MAGIC_PATH_STORAGE=legacy_list` keeps the old per-instruction `std::list<Coord3D>` storage.
- `QRET_MAGIC_PATH_STORAGE=interned` interns exact ordered paths during routing only.
- The candidate uses immutable shared `std::list<Coord3D>` handles instead of `std::vector<Coord3D>` because the public instruction API returns `const std::list<Coord3D>&`.
- Final holder layout is `std::list<Coord3D>` plus an optional shared handle; interned mode clears the local list payload and reads through the handle.
- The interner is scoped to one routing pass; path handles keep only the exact shared path payload alive after the temporary interner is destroyed.
- Legacy and interned path payloads are not stored simultaneously in an instruction.
- A full C++ test sweep exposed a destructor issue with the initial `std::variant` holder. The holder was changed without rerunning H5, to respect the H5 run cap; the exact interning algorithm and serialization behavior are unchanged.

## Run Matrix

| case | variant | requested runs | observed runs | median qret peak KB | median routing peak KB | median elapsed s |
| ---- | ------- | -------------: | ------------: | ------------------: | ---------------------: | ---------------: |
| H4 `4th(new_2)` | legacy | 1 | 1 | 222,276 | 217,924 | 5.574 |
| H4 `4th(new_2)` | candidate | 1 | 1 | 171,220 | 168,692 | 4.886 |
| H5 `4th(new_2)` | legacy | 2 | 2 | 551,820 | 551,820 | 21.403 |
| H5 `4th(new_2)` | candidate | 2 | 2 | 434,838 | 434,838 | 18.642 |

## Metric Parity

| comparison | raw equal | normalized equal | raw mismatches | normalized mismatches |
| ---------- | --------: | ---------------: | -------------- | --------------------- |
| h4_4th_new2:candidate:run_1 | True | True | [] | [] |
| h5_4th_new2:candidate:run_1 | True | True | [] | [] |
| h5_4th_new2:candidate:run_2 | True | True | [] | [] |

## H5 Adoption Gate

- H4 semantic parity: `True`
- serialization compatible: `True`
- pool lifetime leak observed: `False`
- H5 median qret peak reduction KB: `116,982`
- H5 median qret peak reduction percent: `21.199`
- all candidate runs below baseline: `True`
- elapsed regression percent: `-12.902`
- elapsed gate <=3%: `True`
- production candidate adopted by H5 measurement: `True`

## Component Snapshot

| case | variant | run | prepared IR inst | MachineFunction inst | bytes/inst est | path storage MB | interner unique paths | hit rate % |
| ---- | ------- | --: | ---------------: | -------------------: | -------------: | --------------: | -------------------: | ---------: |
| H4 `4th(new_2)` | legacy | 1 | 401,906 | 570,378 | 204.783 | 26.9 | 0 | 0.000 |
| H4 `4th(new_2)` | candidate | 1 | 401,906 | 570,378 | 157.973 | 1.5 | 233 | 99.745 |
| H5 `4th(new_2)` | legacy | 1 | 1,063,500 | 1,499,072 | 202.877 | 68.4 | 0 | 0.000 |
| H5 `4th(new_2)` | legacy | 2 | 1,063,500 | 1,499,072 | 202.877 | 68.4 | 0 | 0.000 |
| H5 `4th(new_2)` | candidate | 1 | 1,063,500 | 1,499,072 | 158.546 | 5.0 | 320 | 99.865 |
| H5 `4th(new_2)` | candidate | 2 | 1,063,500 | 1,499,072 | 158.546 | 5.0 | 320 | 99.865 |

## Safety

H5 runs recorded `MemTotal`, `MemAvailable`, `SwapTotal`, `SwapFree`, and disk free before execution. H6-H9 are rejected by script guard and test guard.

| case | variant | run | MemTotal KB | MemAvailable KB | SwapTotal KB | SwapFree KB | disk free bytes |
| ---- | ------- | --: | ----------: | --------------: | -----------: | ----------: | --------------: |
| H5 `4th(new_2)` | legacy | 1 | 65,522,476 | 54,270,744 | 2,097,148 | 287,388 | 11,858,010,112 |
| H5 `4th(new_2)` | legacy | 2 | 65,522,476 | 54,586,468 | 2,097,148 | 287,388 | 11,852,382,208 |
| H5 `4th(new_2)` | candidate | 1 | 65,522,476 | 54,591,196 | 2,097,148 | 287,388 | 11,846,770,688 |
| H5 `4th(new_2)` | candidate | 2 | 65,522,476 | 54,603,368 | 2,097,148 | 287,388 | 11,841,290,240 |
