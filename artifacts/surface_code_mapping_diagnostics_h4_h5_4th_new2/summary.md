# H4/H5 4th(new_2) Mapping Diagnostics

Mapping-only diagnostics for topology placement contrast. Full compile was not rerun; existing `compile_info.json` files were reused, and mapping-only qret runs produced `mapping.json` plus `mapping_compile_info.json`. Raw mapping state JSON was deleted after extracting summaries.

## Main Finding

For H4/H5 `4th(new_2)`, `qubit_volume` tracks `chip_cell_active_qubit_area_ave`, not runtime. The runtime delta between `center_block` and `left_edge` is effectively zero, while the active-area delta matches the qubit-volume delta.

The mapping diagnostic shows that all `LATTICE_SURGERY_MAGIC` operations use magic factory symbol `0` in these cases. Therefore, the effective magic-delivery distance is controlled mainly by where `m0` is placed:

- `left_edge`: `m0 = (0, 0)`, far from most allocated logical qubits.
- `center_block`: `m0 = (4, 4)`, near the logical-qubit cluster.
- `right_edge`: `m0 = (9, 0)`, intermediate for these mapped layouts.

This explains the stable ordering:

```text
qubit_volume: center_block < right_edge < left_edge
```

The current data suggests the volume gap is primarily an active-area / magic-delivery geometry effect, not a chip-cell count, runtime, or generic physical-qubit-count effect. H4 `left_edge` also has a larger code distance and physical-qubit count, but H5 keeps those fixed and still shows the same center/right/left volume ordering.

## Summary Table

| molecule | case | topology | magic period | runtime | qubit volume | active area ave | active area peak | d | physical qubits | magic op dist mean / max | nearest magic dist mean / max | cnot dist mean / max |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| H4 | baseline_left_edge | left_edge | 15 | 814085 | 10378538 | 12.749 | 55 | 15 | 43200 | 13.56 / 16 | 8.00 / 13 | 6.27 / 13 |
| H4 | baseline_center_block | center_block | 15 | 814086 | 9199159 | 11.300 | 45 | 13 | 32448 | 6.78 / 8 | 4.33 / 7 | 5.69 / 13 |
| H4 | baseline_right_edge | right_edge | 15 | 814240 | 9508834 | 11.678 | 46 | 13 | 32448 | 8.32 / 13 | 5.89 / 10 | 5.78 / 11 |
| H4 | fast_supply_left_edge | left_edge | 8 | 813266 | 10238762 | 12.590 | 55 | 15 | 43200 | 13.56 / 16 | 8.00 / 13 | 6.27 / 13 |
| H4 | fast_supply_center_block | center_block | 8 | 813263 | 9110787 | 11.203 | 45 | 13 | 32448 | 6.78 / 8 | 4.33 / 7 | 5.69 / 13 |
| H4 | fast_supply_right_edge | right_edge | 8 | 813394 | 9285847 | 11.416 | 46 | 13 | 32448 | 8.32 / 13 | 5.89 / 10 | 5.78 / 11 |
| H5 | baseline_left_edge | left_edge | 15 | 2122354 | 31055023 | 14.632 | 61 | 15 | 43200 | 12.84 / 16 | 7.73 / 13 | 5.70 / 15 |
| H5 | baseline_center_block | center_block | 15 | 2122313 | 28471935 | 13.416 | 53 | 15 | 43200 | 6.83 / 8 | 4.82 / 8 | 8.03 / 16 |
| H5 | baseline_right_edge | right_edge | 15 | 2122998 | 29252370 | 13.779 | 66 | 15 | 43200 | 8.38 / 13 | 6.45 / 10 | 7.89 / 17 |
| H5 | fast_supply_left_edge | left_edge | 8 | 2121423 | 30732556 | 14.487 | 61 | 15 | 43200 | 12.84 / 16 | 7.73 / 13 | 5.70 / 15 |
| H5 | fast_supply_center_block | center_block | 8 | 2121413 | 28257330 | 13.320 | 53 | 15 | 43200 | 6.83 / 8 | 4.82 / 8 | 8.03 / 16 |
| H5 | fast_supply_right_edge | right_edge | 8 | 2122020 | 28766040 | 13.556 | 66 | 15 | 43200 | 8.38 / 13 | 6.45 / 10 | 7.89 / 17 |

## Per-Molecule Interpretation

### H4

- magic period `15`: center vs left volume delta `12.82%`, active-area delta `12.82%`, runtime delta `-0.0001%`.
  Magic operation distance mean: center `6.78`, left `13.56`, right `8.32`.
  Active area ave: center `11.300`, left `12.749`, right `11.678`.
- magic period `8`: center vs left volume delta `12.38%`, active-area delta `12.38%`, runtime delta `0.0004%`.
  Magic operation distance mean: center `6.78`, left `13.56`, right `8.32`.
  Active area ave: center `11.203`, left `12.590`, right `11.416`.
### H5

- magic period `15`: center vs left volume delta `9.07%`, active-area delta `9.07%`, runtime delta `0.0019%`.
  Magic operation distance mean: center `6.83`, left `12.84`, right `8.38`.
  Active area ave: center `13.416`, left `14.632`, right `13.779`.
- magic period `8`: center vs left volume delta `8.76%`, active-area delta `8.76%`, runtime delta `0.0005%`.
  Magic operation distance mean: center `6.83`, left `12.84`, right `8.38`.
  Active area ave: center `13.320`, left `14.487`, right `13.556`.

## Files

- JSONL: `artifacts/surface_code_mapping_diagnostics_h4_h5_4th_new2/diagnostics.jsonl`
- CSV: `artifacts/surface_code_mapping_diagnostics_h4_h5_4th_new2/diagnostics.csv`
- Per-case directories contain `mapping.json`, `mapping_summary.json`, and `mapping_compile_info.json`.
