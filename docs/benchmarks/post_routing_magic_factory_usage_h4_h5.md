# Post-Routing Magic Factory Usage Diagnostic H4/H5

## Scope

- Date: 2026-07-08.
- Molecules: H4 and H5 only.
- PF: `4th(new_2)` only.
- Circuit scope: `efficient_controlled_pf_one_step`.
- Compile mode: `ftqc_compile_topology_qec`.
- Magic generation period: 15.
- Magic stock: fixed 10000.
- Topologies: four-factory variants with the same coordinate set and different
  symbol-to-coordinate assignments.
- No full QPE compile was generated.
- No QPE phase register, inverse QFT, measurement, feed-forward, or repeated
  QPE circuit was generated.
- H6 or larger was not executed.
- quration/qret implementation was not changed.

## Motivation

The previous factory-selection audit found that Evaluation's compact
`mapping.json` artifact is produced before routing. It observes lowering and
mapping state, where standard qret lowering initializes
`LATTICE_SURGERY_MAGIC` with `MSymbol{0}`. Source audit also showed that later
routing can write a selected factory symbol back into the instruction.

This diagnostic checks the final routed instruction stream for H4/H5, because
the m0-only vs four-factory resource gap is only interpretable if nonzero
factories are actually used after routing.

## Method

`skip_compile_output=false` was enabled only for this diagnostic. qret then
wrote the post-routing pipeline-state JSON to `step_sc_ls_fixed_v0.json`.

The schema probe on H4 `four_factory_m0_center` found:

- final routed instructions live in `program[*]`;
- magic instructions have `type: LATTICE_SURGERY_MAGIC`;
- the final routed magic factory symbol is stored in `mtarget`;
- every observed magic instruction had an `mtarget`, so confidence is `high`.

Raw pipeline-state JSON was generated under
`artifacts/post_routing_magic_factory_usage_h4_h5/raw_tmp/`, compacted, and then
deleted.

## Results

| molecule | topology | final factory symbol counts | final factory coordinate counts | magic ops | missing | runtime | qubit volume | confidence |
|---|---|---|---|---:|---:|---:|---:|---|
| H4 | `four_factory_m0_left` | `{"0":21789,"1":54270,"2":54271,"3":54270}` | `{"(0,0)":21789,"(4,4)":54270,"(9,0)":54271,"(9,9)":54270}` | 184600 | 0 | 814084 | 9263739 | high |
| H4 | `four_factory_m0_center` | `{"0":54270,"1":21789,"2":54271,"3":54270}` | `{"(0,0)":21789,"(4,4)":54270,"(9,0)":54271,"(9,9)":54270}` | 184600 | 0 | 814084 | 9263731 | high |
| H4 | `four_factory_m0_right` | `{"0":54271,"1":21789,"2":54270,"3":54270}` | `{"(0,0)":21789,"(4,4)":54270,"(9,0)":54271,"(9,9)":54270}` | 184600 | 0 | 814084 | 9263739 | high |
| H4 | `four_factory_m0_far_corner` | `{"0":54270,"1":21789,"2":54270,"3":54271}` | `{"(0,0)":21789,"(4,4)":54270,"(9,0)":54271,"(9,9)":54270}` | 184600 | 0 | 814084 | 9264413 | high |
| H5 | `four_factory_m0_left` | `{"0":51466,"1":141485,"2":141471,"3":141484}` | `{"(0,0)":51466,"(4,4)":141485,"(9,0)":141471,"(9,9)":141484}` | 475906 | 0 | 2122295 | 28179832 | high |
| H5 | `four_factory_m0_center` | `{"0":141485,"1":51466,"2":141471,"3":141484}` | `{"(0,0)":51466,"(4,4)":141485,"(9,0)":141471,"(9,9)":141484}` | 475906 | 0 | 2122295 | 28179832 | high |
| H5 | `four_factory_m0_right` | `{"0":141471,"1":51466,"2":141485,"3":141484}` | `{"(0,0)":51466,"(4,4)":141485,"(9,0)":141471,"(9,9)":141484}` | 475906 | 0 | 2122295 | 28179832 | high |
| H5 | `four_factory_m0_far_corner` | `{"0":141484,"1":51466,"2":141485,"3":141471}` | `{"(0,0)":51466,"(4,4)":141485,"(9,0)":141471,"(9,9)":141484}` | 475906 | 0 | 2122295 | 28193204 | high |

Aggregate:

- Total extracted `LATTICE_SURGERY_MAGIC` ops: 2,642,024.
- Missing factory symbols: 0.
- Field used: `mtarget`.
- Every four-factory case uses nonzero factory symbols.
- Coordinate usage is invariant under symbol permutation, up to the symbol name
  assigned to each coordinate.

## Resource Consistency

The earlier m0-only vs four-factory diagnostic reported:

| molecule | m0-only runtime | four-factory runtime | m0-only qubit volume range | four-factory qubit volume range |
|---|---:|---:|---:|---:|
| H4 | 2769017 | 814084 | 26746443-28258610 | 9263731-9264413 |
| H5 | 7138609 | 2122295 | 83651622-87126712 | 28179832-28193204 |

The post-routing extraction confirms that the four-factory resource rows are not
just pre-routing symbol-0 artifacts: nonzero factories are used in the final
routed instruction stream.

## Interpretation

Observed:

- `program[*].mtarget` is a compact, direct source for final routed factory
  symbols in these H4/H5 qret outputs.
- Four-factory topology uses symbols 0, 1, 2, and 3 after routing.
- Physical coordinate usage is stable across symbol permutations:
  `(0,0)` is the least-used coordinate, while `(4,4)`, `(9,0)`, and `(9,9)`
  account for most magic deliveries in these cases.
- Runtime is unchanged across symbol permutations, and qubit volume changes only
  slightly for the far-corner variant, matching the previous four-factory
  resource rows.

Inferred:

- The m0-only vs four-factory runtime/qubit-volume gap is consistent with real
  multi-factory routed usage.
- The compact mapping artifact should not be used to infer final factory usage.
- Future architecture sweeps should keep a compact post-routing factory-usage
  artifact with at least:
  `total_lattice_surgery_magic_ops`, `final_factory_symbol_counts`,
  `final_factory_coordinate_counts`, `missing_factory_symbol_count`,
  `candidate_field_names_used`, `confidence`, topology symbol-coordinate map,
  and the resource metrics needed to correlate runtime and qubit volume.

Unresolved:

- This diagnostic covers only H4/H5, PF=`4th(new_2)`, and
  `efficient_controlled_pf_one_step`.
- It does not prove the same factory distribution for H6+ or other PF labels.
- It does not expose route distance, queue ordering, or stock tie-break details
  for each individual magic operation.

## Artifact Policy

- Compact outputs retained:
  - `artifacts/post_routing_magic_factory_usage_h4_h5/post_routing_factory_usage.csv`
  - `artifacts/post_routing_magic_factory_usage_h4_h5/post_routing_factory_usage.jsonl`
  - `artifacts/post_routing_magic_factory_usage_h4_h5/summary.md`
- Runner outputs retained locally:
  - `artifacts/post_routing_magic_factory_usage_h4_h5/runner_results.csv`
  - `artifacts/post_routing_magic_factory_usage_h4_h5/runner_results.jsonl`
  - `artifacts/post_routing_magic_factory_usage_h4_h5/runner_results.md`
  - `artifacts/post_routing_magic_factory_usage_h4_h5/logs/run.log`
- Raw temporary directory before deletion: 3,483,019,266 bytes.
- `artifacts/post_routing_magic_factory_usage_h4_h5/raw_tmp/` was deleted.
- Full raw pipeline-state JSON and raw `mapping_state.json` are not retained.

## Execution Notes

- Phase C runner success: 8, failed: 0, skipped: 0.
- Phase C elapsed wall time: 5:32.80.
- Phase C outer peak RSS: 8,324,584 KB.
- Phase C swaps: 0.
- Compact extraction elapsed wall time: 3:09.12.
- Compact extraction peak RSS: 4,691,524 KB.
- Compact extraction swaps: 0.

## References

- `docs/benchmarks/qret_magic_factory_selection_audit.md`
- `docs/benchmarks/surface_code_factory_symbol_m0_diagnostic_h4_h7.md`
- `artifacts/post_routing_magic_factory_usage_h4_h5/summary.md`
- `artifacts/post_routing_magic_factory_usage_h4_h5/post_routing_factory_usage.csv`
