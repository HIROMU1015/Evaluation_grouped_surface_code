# qret Magic Factory Selection Audit

## Scope

- Date: 2026-07-08.
- Repository: `/home/abe/Project/Evaluation_grouped_surface_code`.
- Read-only source audit of vendored `third_party/quration`.
- No quration/qret implementation change.
- No full QPE compile.
- No QPE phase register, inverse QFT, measurement, feed-forward, or repeated QPE circuit generation.
- Optional diagnostic was limited to H4/H5, PF=`4th(new_2)`, `efficient_controlled_pf_one_step`.
- H6 or larger was not executed in this audit.
- Focus: `LATTICE_SURGERY_MAGIC` and magic factory topology handling.

## Background

The previous factory symbol / m0 diagnostic reported that all compact
`mapping.json` artifacts used magic factory symbol `0`. The source audit shows
that this is a pre-routing observation: Evaluation's compact mapping artifact is
generated from `init_compile_info -> mapping -> dump_compile_info`, not from the
later `routing` pass.

## Questions

- Q1. Does qret always use symbol 0 for `LATTICE_SURGERY_MAGIC`?
- Q2. Is there nearest / geometry / availability based factory selection?
- Q3. How does topology YAML encode factory symbol and coordinate?
- Q4. Is there a setting for multiple factory allocation or selection?
- Q5. Do nonzero factories affect layout / scheduling / active area if the
  mapping-only artifact reports only symbol 0?
- Q6. Are previous topology-sweep resource differences closer to m0 placement,
  factory set, logical layout, or routing/scheduling effects?

## Source Locations Inspected

| path | line range | why inspected | finding |
|---|---:|---|---|
| `third_party/quration/quration-core/src/qret/target/sc_ls_fixed_v0/lowering.cpp` | 223-269 | normal T/TDag lowering | `LatticeSurgeryMagic::New(..., MSymbol{0}, ...)` is hard-coded for non-distributed normal lowering. |
| `third_party/quration/quration-core/src/qret/target/sc_ls_fixed_v0/lowering.cpp` | 734-752 | PBC non-Clifford lowering | PBC mode maps non-Clifford rotations cyclically over `MSymbol{i}` factories; this is not the current standard mode. |
| `third_party/quration/quration-core/src/qret/target/sc_ls_fixed_v0/lowering.cpp` | 790-797 | factory allocation | All magic factories present in topology are emitted as `ALLOCATE_MAGIC_FACTORY`; factory count comes from topology. |
| `third_party/quration/quration-core/src/qret/target/sc_ls_fixed_v0/topology.cpp` | 272-280, 328-337 | YAML parser | `magic_factory` entries read `symbol` and `coord`; symbol-to-coordinate assignment is direct. |
| `third_party/quration/quration-core/src/qret/target/sc_ls_fixed_v0/topology.cpp` | 682-704, 759-769 | topology validation | factory symbols and coordinates must be unique; no four-factory fixed-count requirement was found. |
| `third_party/quration/quration-core/src/qret/target/sc_ls_fixed_v0/state.cpp` | 19-27, 149-178 | runtime state | magic factories are stored per symbol and z plane; symbol lists are sorted by ID. |
| `third_party/quration/quration-core/src/qret/target/sc_ls_fixed_v0/state.h` | 35-130 | factory stock model | stock/generation are per factory state, but period/capacity come from global machine options. |
| `third_party/quration/quration-core/src/qret/target/sc_ls_fixed_v0/search_grid.cpp` | 335-357, 532-604 | 2D magic route search | BFS seeds from all available factories and sets `route.magic_factory` from the selected route. |
| `third_party/quration/quration-core/src/qret/target/sc_ls_fixed_v0/search_grid.cpp` | 39-67 | tie handling near factory | adjacent factory choice prefers larger stock, then lower symbol ID on stock ties. |
| `third_party/quration/quration-core/src/qret/target/sc_ls_fixed_v0/search_grid.cpp` | 780-805 | Steiner magic search | multi-qubit magic search adds all available factories to a virtual magic terminal. |
| `third_party/quration/quration-core/src/qret/target/sc_ls_fixed_v0/simulator.cpp` | 1530-1607, 1612-1644 | 2D `LATTICE_SURGERY_MAGIC` routing | routing invokes magic route search and overwrites the instruction's factory symbol with the selected factory. |
| `third_party/quration/quration-core/src/qret/target/sc_ls_fixed_v0/sc_ls_fixed_v0_compile_backend.cpp` | 207-228, 383-432 | machine options / CLI | topology path, PBC mode, cultivation, global period, and global stock exist; no factory-selection-policy option was found. |
| `third_party/quration/quration-core/src/qret/target/sc_ls_fixed_v0/calc_compile_info.cpp` | 428-455, 2309-2338 | resource accounting | factory allocations contribute to factory count; active area/qubit volume are computed from scheduled active instructions. |
| `src/trotterlib/surface_code.py` | 5129-5155, 5919-6111 | Evaluation compact mapping artifact | compact `mapping.json` uses mapping-only output, so its factory symbol counts are pre-routing. |

## Findings

### Observed From Source

- In standard non-PBC lowering, T/TDag becomes `LATTICE_SURGERY_MAGIC` with
  `MSymbol{0}` initially. This explains why the mapping-only artifact reports
  symbol `0`.
- Routing is not limited to that initial symbol. In 2D single-qubit
  `LATTICE_SURGERY_MAGIC`, qret searches from all available magic factories and
  writes the selected factory back to the instruction.
- Multi-qubit magic search also includes all available factories in its Steiner
  graph.
- Multiple factories are represented by multiple `magic_factory` entries in the
  topology. qret allocates all of them.
- `magic_generation_period` and `maximum_magic_state_stock` are global machine
  options, not per-factory topology fields.
- No CLI/config option for choosing a nearest/stock/symbol factory selection
  policy was found. The only route searcher option shown by hidden help is
  `--sc_ls_fixed_v0-route-searcher-type`, and source currently accepts only the
  default value.
- PBC mode contains a different lowering path that cycles non-Clifford
  rotations across factories, but current Evaluation runs do not enable PBC
  mode.

### Not Found

- No topology YAML field for per-factory capacity, period, or priority was
  found.
- No documented or hidden qret CLI option was found that forces
  `LATTICE_SURGERY_MAGIC` to use nearest factory, symbol 0, round-robin, or a
  custom allocator in standard mode.
- No quration/qret implementation change was made.

### Unresolved

- The final routed factory symbol distribution is not directly retained by the
  current Evaluation artifact when `skip_compile_output=true`.
- The previous m0 diagnostic's `used factory symbol = 0` should be interpreted
  as pre-routing/lowering evidence, not proof that final routed execution used
  only symbol 0.
- The exact tie-breaking among equal-distance BFS routes depends on queue
  ordering, free-ancilla state, stock state, and lower-symbol tie behavior near
  factories.

## Optional Diagnostic: m0-only vs four-factory

Because source audit alone did not quantify whether nonzero factories affect
routed resources, a small H4/H5 diagnostic was run.

Conditions:

- Molecules: H4 and H5 only.
- PF: `4th(new_2)`.
- Circuit scope: `efficient_controlled_pf_one_step`.
- Magic period: 15.
- Magic stock: fixed 10000.
- Topologies: one `m0` factory vs four factories with the same m0 coordinate.
- H6 or larger was not executed.

Execution:

- success: 16
- failed: 0
- skipped: 0
- elapsed wall time: 4:04.20
- outer peak RSS: 7,731,864 KB
- swaps: 0

Resource effect:

| molecule | m0 coordinate | runtime m0-only | runtime four-factory | qubit volume m0-only | qubit volume four-factory |
|---|---:|---:|---:|---:|---:|
| H4 | `(0,0)` | 2,769,017 | 814,084 | 28,258,610 | 9,263,739 |
| H4 | `(4,4)` | 2,769,017 | 814,084 | 26,897,006 | 9,263,731 |
| H4 | `(9,0)` | 2,769,017 | 814,084 | 27,116,988 | 9,263,739 |
| H4 | `(9,9)` | 2,769,017 | 814,084 | 26,746,443 | 9,264,413 |
| H5 | `(0,0)` | 7,138,609 | 2,122,295 | 87,126,712 | 28,179,832 |
| H5 | `(4,4)` | 7,138,609 | 2,122,295 | 83,952,800 | 28,179,832 |
| H5 | `(9,0)` | 7,138,609 | 2,122,295 | 84,355,168 | 28,179,832 |
| H5 | `(9,9)` | 7,138,609 | 2,122,295 | 83,651,622 | 28,193,204 |

Interpretation:

- qret accepted single-factory topologies with only `MSymbol{0}`.
- The mapping-only artifact still reports only symbol `0`, as expected from
  standard lowering before routing.
- Four-factory topology reduced runtime and qubit volume substantially in every
  matched H4/H5 pair.
- Therefore, nonzero factories do affect routed resource metrics even when the
  current compact mapping artifact reports only symbol `0`.
- In these H4/H5 cases, factory count/supply is a major effect. It should be
  separated from m0 coordinate placement and from full factory-coordinate-set
  geometry in future topology sweeps.

## Interpretation

The strongest source-level answer is:

- qret standard lowering initializes `LATTICE_SURGERY_MAGIC` with symbol `0`.
- qret routing has multi-factory route search and can overwrite that symbol.
- Evaluation's compact `mapping.json` currently observes the first item, not the
  final routed factory selection.

The previous H4-H7 symbol diagnostic remains useful as evidence about lowering
and mapping-only state, but it should not be used alone to claim that final
routed execution always uses factory symbol 0. The new H4/H5 m0-only vs
four-factory diagnostic shows that nonzero factories materially affect routed
runtime and qubit volume.

For earlier topology sweep interpretation, this means:

- Differences among four-factory topologies cannot be reduced to "only m0 is
  used" without a post-routing factory-usage artifact.
- Factory count/supply has a large effect when changing from one factory to
  four factories.
- Within fixed four-factory count, the remaining differences are more likely
  geometry/layout/routing/scheduling effects of the coordinate set.

## Next Diagnostic Candidates

- Add a small post-routing factory-usage extraction path for H4/H5 that compacts
  final routed instructions and deletes raw pipeline state immediately.
- Repeat only the smallest H4/H5 cases for PF=`2nd` to check whether the same
  factory-count effect holds.
- Keep future architecture sweeps stratified by fixed factory count and fixed
  magic supply before interpreting m0 coordinate effects.

## Artifacts

- `artifacts/surface_code_factory_count_m0_only_vs_four_h4_h5/results.csv`
- `artifacts/surface_code_factory_count_m0_only_vs_four_h4_h5/results.jsonl`
- `artifacts/surface_code_factory_count_m0_only_vs_four_h4_h5/diagnostics.csv`
- `artifacts/surface_code_factory_count_m0_only_vs_four_h4_h5/diagnostics.jsonl`
- `artifacts/surface_code_factory_count_m0_only_vs_four_h4_h5/summary.md`
- `artifacts/surface_code_factory_count_m0_only_vs_four_h4_h5/logs/run.log`
