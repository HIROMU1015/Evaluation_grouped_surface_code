# Factory Count Diagnostic: m0-only vs four-factory H4/H5

## Scope

- Date of run: 2026-07-08.
- Molecules: H4 and H5 only.
- PF: `4th(new_2)`.
- Circuit scope: `efficient_controlled_pf_one_step`.
- Compile mode: `ftqc_compile_topology_qec`.
- Magic generation period: 15.
- Magic stock: fixed 10000.
- Compared a single `m0` factory topology against the four-factory topology with the same `m0` coordinate.
- This is not a full QPE compile. No QPE phase register, inverse QFT, measurement, feed-forward, or repeated QPE circuit was generated.
- H6 or larger was not executed.

## Execution

- success: 16
- failed: 0
- skipped: 0
- peak qret RSS across recorded stages: 7,732,048 KB

## Resource Comparison

| molecule | m0 label | m0 coord | runtime m0-only | runtime four | runtime delta | qubit volume m0-only | qubit volume four | qv delta | active area ave m0-only | active area ave four | area delta | chip cells m0-only | chip cells four | physical qubits m0-only | physical qubits four | d m0-only | d four |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| H4 | left | (0,0) | 2,769,017 | 814,084 | -1.95493e+06 | 28,258,610 | 9,263,739 | -1.89949e+07 | 10.205286 | 11.379340 | +1.17405 | 99 | 96 | 44550 | 32448 | 15 | 13 |
| H4 | center | (4,4) | 2,769,017 | 814,084 | -1.95493e+06 | 26,897,006 | 9,263,731 | -1.76333e+07 | 9.713558 | 11.379331 | +1.66577 | 99 | 96 | 44550 | 32448 | 15 | 13 |
| H4 | right | (9,0) | 2,769,017 | 814,084 | -1.95493e+06 | 27,116,988 | 9,263,739 | -1.78532e+07 | 9.793002 | 11.379340 | +1.58634 | 99 | 96 | 44550 | 32448 | 15 | 13 |
| H4 | far_corner | (9,9) | 2,769,017 | 814,084 | -1.95493e+06 | 26,746,443 | 9,264,413 | -1.7482e+07 | 9.659183 | 11.380168 | +1.72099 | 99 | 96 | 44550 | 32448 | 15 | 13 |
| H5 | left | (0,0) | 7,138,609 | 2,122,295 | -5.01631e+06 | 87,126,712 | 28,179,832 | -5.89469e+07 | 12.204998 | 13.278000 | +1.073 | 99 | 96 | 44550 | 43200 | 15 | 15 |
| H5 | center | (4,4) | 7,138,609 | 2,122,295 | -5.01631e+06 | 83,952,800 | 28,179,832 | -5.5773e+07 | 11.760386 | 13.278000 | +1.51761 | 99 | 96 | 44550 | 43200 | 15 | 15 |
| H5 | right | (9,0) | 7,138,609 | 2,122,295 | -5.01631e+06 | 84,355,168 | 28,179,832 | -5.61753e+07 | 11.816751 | 13.278000 | +1.46125 | 99 | 96 | 44550 | 43200 | 15 | 15 |
| H5 | far_corner | (9,9) | 7,138,609 | 2,122,295 | -5.01631e+06 | 83,651,622 | 28,193,204 | -5.54584e+07 | 11.718196 | 13.284300 | +1.5661 | 99 | 96 | 44550 | 43200 | 15 | 15 |

## Mapping-Only Factory Symbols

The factory-symbol columns below are extracted from Evaluation's compact `mapping.json`, which is generated from `init_compile_info -> mapping -> dump_compile_info` and does not include the later `routing` pass. They should be read as pre-routing/lowering observations, not final routed factory usage.

| molecule | variant | condition | m0 coord | factory set | factory count | used symbols | used coords | magic dist mean | nearest dist mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| H4 | m0_only_left | m0_only | (0,0) | (0,0) | 1 | 0 | (0,0) | 13.8235 | 11.1111 |
| H4 | four_factory_m0_left | four_factory | (0,0) | (0,0);(4,4);(9,0);(9,9) | 4 | 0 | (0,0) | 12.2393 | 3.33333 |
| H4 | m0_only_center | m0_only | (4,4) | (4,4) | 1 | 0 | (4,4) | 6.12793 | 5.33333 |
| H4 | four_factory_m0_center | four_factory | (4,4) | (0,0);(4,4);(9,0);(9,9) | 4 | 0 | (4,4) | 5.10531 | 3.33333 |
| H4 | m0_only_right | m0_only | (9,0) | (9,0) | 1 | 0 | (9,0) | 7.6696 | 8.11111 |
| H4 | four_factory_m0_right | four_factory | (9,0) | (0,0);(4,4);(9,0);(9,9) | 4 | 0 | (9,0) | 6.7005 | 3.33333 |
| H4 | m0_only_far_corner | m0_only | (9,9) | (9,9) | 1 | 0 | (9,9) | 5.64537 | 7.77778 |
| H4 | four_factory_m0_far_corner | four_factory | (9,9) | (0,0);(4,4);(9,0);(9,9) | 4 | 0 | (9,9) | 5.76074 | 3.33333 |
| H5 | m0_only_left | m0_only | (0,0) | (0,0) | 1 | 0 | (0,0) | 13.1518 | 9.63636 |
| H5 | four_factory_m0_left | four_factory | (0,0) | (0,0);(4,4);(9,0);(9,9) | 4 | 0 | (0,0) | 11.3966 | 4 |
| H5 | m0_only_center | m0_only | (4,4) | (4,4) | 1 | 0 | (4,4) | 6.38828 | 5.27273 |
| H5 | four_factory_m0_center | four_factory | (4,4) | (0,0);(4,4);(9,0);(9,9) | 4 | 0 | (4,4) | 5.14766 | 4 |
| H5 | m0_only_right | m0_only | (9,0) | (9,0) | 1 | 0 | (9,0) | 7.40651 | 8.45455 |
| H5 | four_factory_m0_right | four_factory | (9,0) | (0,0);(4,4);(9,0);(9,9) | 4 | 0 | (9,0) | 6.98735 | 4 |
| H5 | m0_only_far_corner | m0_only | (9,9) | (9,9) | 1 | 0 | (9,9) | 6.03093 | 9.45455 |
| H5 | four_factory_m0_far_corner | four_factory | (9,9) | (0,0);(4,4);(9,0);(9,9) | 4 | 0 | (9,9) | 6.60341 | 4 |

## Interpretation

- qret accepted the single-factory topology with only `MSymbol{0}`.
- The compact mapping result still reports only symbol `0`, as expected from the pre-routing lowering path.
- Across matched H4/H5 pairs, max absolute runtime delta between m0-only and four-factory was `5.01631e+06` beats.
- Across matched H4/H5 pairs, max absolute qubit-volume delta was `5.89469e+07`.
- Across matched H4/H5 pairs, max absolute active-area-average delta was `1.72099`.
- In every matched pair, four-factory topology reduced runtime and qubit volume substantially versus m0-only.
- Therefore, nonzero factories affect routed resource metrics even though the pre-routing mapping artifact reports only symbol `0`.

## Artifacts

- `artifacts/surface_code_factory_count_m0_only_vs_four_h4_h5/results.csv`
- `artifacts/surface_code_factory_count_m0_only_vs_four_h4_h5/results.jsonl`
- `artifacts/surface_code_factory_count_m0_only_vs_four_h4_h5/diagnostics.csv`
- `artifacts/surface_code_factory_count_m0_only_vs_four_h4_h5/diagnostics.jsonl`
- `artifacts/surface_code_factory_count_m0_only_vs_four_h4_h5/summary.md`
- `artifacts/surface_code_factory_count_m0_only_vs_four_h4_h5/logs/run.log`
