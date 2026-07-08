# Post-Routing Magic Factory Usage H4/H5

## Scope

- Molecules: H4 and H5 only.
- PF: `4th(new_2)` only.
- Circuit scope: `efficient_controlled_pf_one_step` only.
- Topologies: four-factory variants `four_factory_m0_left`, `four_factory_m0_center`, `four_factory_m0_right`, `four_factory_m0_far_corner`.
- This is not a full QPE compile; no QPE phase register, inverse QFT, measurement, feed-forward, or repeated QPE circuit was generated.
- H6 or larger was not executed.
- quration/qret implementation was not changed.

## Schema Probe

- qret post-routing output is the `step_sc_ls_fixed_v0.json` pipeline-state produced with `skip_compile_output=false`.
- Final routed instructions are in `program[*]`.
- `LATTICE_SURGERY_MAGIC` instructions use `type: LATTICE_SURGERY_MAGIC` and the final routed factory symbol is stored in `mtarget`.
- Extractor confidence is `high` for all cases: `mtarget` was present for every observed `LATTICE_SURGERY_MAGIC` instruction.

## Results

| molecule | topology | ops | symbol counts | coordinate counts | missing | runtime | qubit volume | confidence |
|---|---|---:|---|---|---:|---:|---:|---|
| H4 | `four_factory_m0_left` | 184600 | `{"0":21789,"1":54270,"2":54271,"3":54270}` | `{"(0,0)":21789,"(4,4)":54270,"(9,0)":54271,"(9,9)":54270}` | 0 | 814084 | 9263739 | high |
| H4 | `four_factory_m0_center` | 184600 | `{"0":54270,"1":21789,"2":54271,"3":54270}` | `{"(0,0)":21789,"(4,4)":54270,"(9,0)":54271,"(9,9)":54270}` | 0 | 814084 | 9263731 | high |
| H4 | `four_factory_m0_right` | 184600 | `{"0":54271,"1":21789,"2":54270,"3":54270}` | `{"(0,0)":21789,"(4,4)":54270,"(9,0)":54271,"(9,9)":54270}` | 0 | 814084 | 9263739 | high |
| H4 | `four_factory_m0_far_corner` | 184600 | `{"0":54270,"1":21789,"2":54270,"3":54271}` | `{"(0,0)":21789,"(4,4)":54270,"(9,0)":54271,"(9,9)":54270}` | 0 | 814084 | 9264413 | high |
| H5 | `four_factory_m0_left` | 475906 | `{"0":51466,"1":141485,"2":141471,"3":141484}` | `{"(0,0)":51466,"(4,4)":141485,"(9,0)":141471,"(9,9)":141484}` | 0 | 2122295 | 28179832 | high |
| H5 | `four_factory_m0_center` | 475906 | `{"0":141485,"1":51466,"2":141471,"3":141484}` | `{"(0,0)":51466,"(4,4)":141485,"(9,0)":141471,"(9,9)":141484}` | 0 | 2122295 | 28179832 | high |
| H5 | `four_factory_m0_right` | 475906 | `{"0":141471,"1":51466,"2":141485,"3":141484}` | `{"(0,0)":51466,"(4,4)":141485,"(9,0)":141471,"(9,9)":141484}` | 0 | 2122295 | 28179832 | high |
| H5 | `four_factory_m0_far_corner` | 475906 | `{"0":141484,"1":51466,"2":141485,"3":141471}` | `{"(0,0)":51466,"(4,4)":141485,"(9,0)":141471,"(9,9)":141484}` | 0 | 2122295 | 28193204 | high |

## Aggregate

- Total extracted `LATTICE_SURGERY_MAGIC` ops: `2642024`.
- Aggregate final factory symbol counts: `{"0":660506,"1":415520,"2":782994,"3":783004}`.
- Aggregate final factory coordinate counts: `{"(0,0)":293020,"(4,4)":783020,"(9,0)":782968,"(9,9)":783016}`.
- Nonzero factory symbols appear in every four-factory case.
- Missing factory symbol count is 0 in every case.

## Interpretation

Observed:

- The compact mapping artifact was pre-routing, but post-routing `program[*].mtarget` shows final factory usage.
- Four-factory topology uses symbols 0, 1, 2, and 3 after routing.
- The `mtarget` distribution follows the fixed physical coordinate set more than the symbolic name of m0; when m0 is reassigned to a coordinate, the count associated with that coordinate moves to the new symbol.
- Runtime and qubit volume match the earlier four-factory H4/H5 resource rows, while final usage confirms that nonzero factories are actually used.

Inferred:

- The m0-only vs four-factory runtime and qubit-volume gap is consistent with real multi-factory routed usage, not merely with a pre-routing lowering artifact.
- For future architecture sweeps, the compact artifact should retain at minimum: `total_lattice_surgery_magic_ops`, `final_factory_symbol_counts`, `final_factory_coordinate_counts`, `missing_factory_symbol_count`, `candidate_field_names_used`, `confidence`, topology symbol-coordinate map, and resource metrics needed to correlate runtime/qubit volume.

Unresolved:

- This diagnostic covers only H4/H5, PF=`4th(new_2)`, and `efficient_controlled_pf_one_step`.
- It does not prove the same distribution for H6+ or other PF labels.
- It does not isolate detailed route distance or stock-tie behavior inside qret.

## Artifact Policy

- Compact outputs retained: `artifacts/post_routing_magic_factory_usage_h4_h5/post_routing_factory_usage.jsonl`, `artifacts/post_routing_magic_factory_usage_h4_h5/post_routing_factory_usage.csv`, `artifacts/post_routing_magic_factory_usage_h4_h5/summary.md`.
- Raw temporary directory size before deletion: `3483019266` bytes.
- Raw temporary directory removed: `True`.
- Full raw pipeline-state JSON and raw `mapping_state.json` are not retained.
