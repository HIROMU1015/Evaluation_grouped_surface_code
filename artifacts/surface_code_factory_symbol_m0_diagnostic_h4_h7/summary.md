# Factory Symbol / m0 Diagnostic Summary

## Scope

- Molecules executed: H4, H5, H6, H7
- PF: `4th(new_2)`
- Circuit scope: `efficient_controlled_pf_one_step`
- Magic period: 15
- Magic stock: fixed 10000
- H8 or larger was not executed.
- This is not a full QPE compile.

## Topology Variants

All variants use the same coordinate set; only the symbol assignment changes.

| variant | m0 | m1 | m2 | m3 | coordinate set |
| --- | --- | --- | --- | --- | --- |
| m0_left | (0,0) | (4,4) | (9,0) | (9,9) | (0,0);(4,4);(9,0);(9,9) |
| m0_center | (4,4) | (0,0) | (9,0) | (9,9) | (0,0);(4,4);(9,0);(9,9) |
| m0_right | (9,0) | (0,0) | (4,4) | (9,9) | (0,0);(4,4);(9,0);(9,9) |
| m0_far_corner | (9,9) | (0,0) | (4,4) | (9,0) | (0,0);(4,4);(9,0);(9,9) |

## Results

| molecule | variant | m0 coord | used symbols | used coords | magic dist mean | active area ave | qubit volume | runtime | peak RSS KB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| H4 | m0_left | (0,0) | 0 | (0,0) | 12.2393 | 11.3793 | 9263739 | 814084 | 2969744 |
| H4 | m0_center | (4,4) | 0 | (4,4) | 5.10531 | 11.3793 | 9263731 | 814084 | 2969944 |
| H4 | m0_right | (9,0) | 0 | (9,0) | 6.7005 | 11.3793 | 9263739 | 814084 | 2969708 |
| H4 | m0_far_corner | (9,9) | 0 | (9,9) | 5.76074 | 11.3802 | 9264413 | 814084 | 2969944 |
| H5 | m0_left | (0,0) | 0 | (0,0) | 11.3966 | 13.278 | 28179832 | 2122295 | 7732048 |
| H5 | m0_center | (4,4) | 0 | (4,4) | 5.14766 | 13.278 | 28179832 | 2122295 | 7730872 |
| H5 | m0_right | (9,0) | 0 | (9,0) | 6.98735 | 13.278 | 28179832 | 2122295 | 7731572 |
| H5 | m0_far_corner | (9,9) | 0 | (9,9) | 6.60341 | 13.2843 | 28193204 | 2122295 | 7731404 |
| H6 | m0_left | (0,0) | 0 | (0,0) | 10.8083 | 15.1153 | 69171725 | 4576283 | 16812084 |
| H6 | m0_center | (4,4) | 0 | (4,4) | 5.00913 | 15.1153 | 69171725 | 4576283 | 16812152 |
| H6 | m0_right | (9,0) | 0 | (9,0) | 7.72226 | 15.1153 | 69171725 | 4576283 | 16812476 |
| H6 | m0_far_corner | (9,9) | 0 | (9,9) | 7.19169 | 15.1161 | 69175405 | 4576283 | 16811736 |
| H7 | m0_left | (0,0) | 0 | (0,0) | 10.8322 | 17.2799 | 153291432 | 8871104 | 32464948 |
| H7 | m0_center | (4,4) | 0 | (4,4) | 4.92452 | 17.2802 | 153294237 | 8871103 | 32465248 |
| H7 | m0_right | (9,0) | 0 | (9,0) | 7.65315 | 17.2799 | 153291432 | 8871104 | 32465192 |
| H7 | m0_far_corner | (9,9) | 0 | (9,9) | 7.16782 | 17.2973 | 153446215 | 8871113 | 32465496 |

## Interpretation

### Observed

- All cases used magic factory symbol 0: true.
- Used magic factory coordinates followed the m0 coordinate: true.
- The four topology variants used the same factory coordinate set and changed only symbol assignment.
- Qubit volume range across executed rows: 9263731 to 153446215.
- Active-area average range across executed rows: 11.37933063418517 to 17.297290092009874.

### Inferred

- These results are consistent with qret selecting magic factory symbol 0 for `LATTICE_SURGERY_MAGIC`, rather than selecting the geometrically nearest available factory.
- Magic-delivery distance follows m0 placement, but active area and qubit volume are mostly invariant under symbol-only permutations in this fixed coordinate set.
- The earlier topology-sweep volume differences therefore cannot be attributed to symbol assignment alone; factory coordinate-set placement, layout occupancy, and/or other qret scheduling details remain relevant.

### Unresolved

- This is an observed result for the executed H-chain inputs, not a formal proof of qret behavior for every input.
- The internal reason for choosing symbol 0 remains a quration/qret implementation question.

## Safety / Execution

- Success rows: 16
- Peak RSS max: 32465496 KB
- Compile elapsed max: 68.58359760791063 s
- Raw `mapping_state.json` files were not retained.

## Artifacts

- `artifacts/surface_code_factory_symbol_m0_diagnostic_h4_h7/diagnostics.csv`
- `artifacts/surface_code_factory_symbol_m0_diagnostic_h4_h7/diagnostics.jsonl`
- `artifacts/surface_code_factory_symbol_m0_diagnostic_h4_h7/summary.md`
- `artifacts/surface_code_factory_symbol_m0_diagnostic_h4_h7/logs/`
