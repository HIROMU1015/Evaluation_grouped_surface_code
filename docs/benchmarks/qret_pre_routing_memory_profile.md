# qret Pre-Routing RSS Memory Profile

## Purpose

Isolate the H4 `4th(new_2)` topology compile RSS peak before routing, especially
from IR JSON load through immediately before routing input generation. The
control case is H4 `2nd`.

## Method

- qret binary: `build/quration/qret`, rebuilt from the vendored quration source
  inside this Evaluation repository.
- External sampler: `/proc/<pid>/status` and `/proc/<pid>/smaps_rollup` every
  20 ms while `/usr/bin/time -v qret compile ...` was running.
- qret internal markers: enabled only with `QRET_RSS_PROFILE_JSONL`.
- Topology mode only; no H5/H6; QEC was not run because the pre-routing path is
  shared before QEC resource estimation.
- H4 `4th(new_2)` input: existing prepared artifact
  `.../H4_sto-3g_singlet_distance_100_charge_0_grouping__4th_new_2_/2eb5acb2b3f04ba2/step_opt.json`.
- H4 `2nd` input: existing prepared artifact
  `.../H4_sto-3g_singlet_distance_100_charge_0_grouping__2nd/219de8464f2c6658/step_opt.json`.

Raw run data was generated under `artifacts/qret_pre_routing_memory*` during the
measurement and summarized here; it is reproducible with:

```bash
scripts/profile_qret_pre_routing_memory.py --sample-interval-sec 0.02
```

## Prefix Results

| case | pass prefix | GNU time max RSS KB |
| --- | --- | ---: |
| H4 `2nd` | `init_only` | 357,132 |
| H4 `2nd` | `mapping_only` | 357,000 |
| H4 `2nd` | `routing_only` | 427,304 |
| H4 `2nd` | `full_topology` | 450,100 |
| H4 `4th(new_2)` | `init_only` | 1,650,668 |
| H4 `4th(new_2)` | `mapping_only` | 1,650,952 |
| H4 `4th(new_2)` | `routing_only` | 1,980,664 |
| H4 `4th(new_2)` | `full_topology` | 2,086,812 |

The prefix experiment already shows that the large H4 peak is not caused by
routing startup: `init_only` reaches about 1.65 GB because qret still serializes
and saves a pipeline state after the pass prefix.

## Pre-Routing Boundary RSS

Detail run, `full_topology`:

| stage | H4 `2nd` KB | H4 `4th(new_2)` KB |
| --- | ---: | ---: |
| before IR JSON parse | 6,912 | 6,656 |
| after IR JSON parse, JSON DOM alive | 43,520 | 179,336 |
| after `LoadJson`, JSON DOM alive | 43,776 | 179,592 |
| after returning from load function, JSON DOM destroyed | 43,776 | 179,592 |
| after lowering | 43,776 | 179,592 |
| after `mapping` qubit graph | 43,776 | 179,848 |
| routing entry | 43,776 | 179,848 |
| after initial `InstQueue::Peek` | 44,032 | 179,848 |
| immediately before routing main loop | 44,032 | 179,848 |
| after routing main loop | 51,968 | 215,944 |

Findings:

- H4 `4th(new_2)` reaches only about 180 MB before routing starts, roughly 8.6%
  of the 2,086,700 KB full-run max RSS.
- The first pre-routing jump is IR JSON parse: about +173 MB for H4
  `4th(new_2)` from the qret baseline.
- `LoadJson` adds only about +256 KB after JSON parse in this run.
- Returning from `LoadFunctionFromIR` and destroying the JSON DOM did not reduce
  current RSS. This is allocator-retention behavior; it does not mean the JSON
  object remains live.
- Lowering and mapping graph construction do not materially increase current
  RSS for this input.
- `InstQueue` construction and initial `Peek` also do not materially increase
  RSS before the routing loop.

## Where The 2 GB Peak Occurs

The observed 2.09 GB peak is post-routing and mostly output/state materialization:

| stage, H4 `4th(new_2)` full topology | current RSS KB | delta KB |
| --- | ---: | ---: |
| after routing main loop | 215,944 | - |
| after `calc_info_without_topology` | 586,700 | +370,756 |
| before `BuildPipelineState` | 578,348 | -8,352 |
| after `BuildProgramJson` | 1,196,588 | +618,240 |
| after `Json(state)` in `SavePipelineState` | 2,067,500 | +870,912 |
| after `SavePipelineState` returns | 2,077,836 | +10,336 |
| `/usr/bin/time -v` max RSS | 2,086,700 | +8,864 |

Interpretation:

- qret retains the original IR while lowering and passes run, but that overlap is
  not the H4 peak; it is around 180 MB before routing.
- `calc_info_without_topology` is the first post-routing stage with a large
  retained increase.
- `BuildPipelineState` duplicates the machine program into `state.program`
  JSON objects.
- `SavePipelineState` then creates another full `Json(state)` DOM even when the
  output path is `/dev/null`; this creates the largest single increase.

## Decision

Do not spend the next Evaluation-side RSS reduction on pre-routing IR JSON load,
mapping graph construction, or routing input generation. They do not explain the
2.09 GB qret peak.

The next useful RSS reduction target is qret pipeline-state/output
materialization: avoid building/saving the full pipeline state when
`skip_compile_output` uses `/dev/null`, or add a qret option that emits only the
requested `compile_info.json` without duplicating the full program JSON.
