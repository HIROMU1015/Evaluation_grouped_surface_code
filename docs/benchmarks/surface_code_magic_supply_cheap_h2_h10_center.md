# Surface-Code Cheap Magic Supply Sweep H2-H10 Center Topology

## Scope

- Date of run: 2026-07-07.
- Targets: H2-H10.
- PF labels: `2nd` and `4th(new_2)`.
- Circuit scope: `efficient_controlled_pf_one_step`.
- Compile mode: `ftqc_compile_topology_qec`.
- Topology fixed to `factory_center_block`.
- Magic regimes:
  - `normal_p15_center`: period 15, fixed stock 10000.
  - `fast_p8_center`: period 8, fixed stock 10000.
  - `cheap_p4_center`: period 4, fixed stock 10000.
  - `cheap_p2_center`: period 2, fixed stock 10000.
  - `cheap_p1_center`: period 1, fixed stock 10000.
  - `cheap_p1_large_stock_center`: period 1, fixed stock 1000000.
- Expected rows: 108.
- Observed rows: 108 success, 0 failed, 0 skipped.

This is not a full QPE compile. The reported QPE-scale totals are linear extrapolations from one compiled/profiled `efficient_controlled_pf_one_step`. No QPE phase register, inverse QFT, measurement, feed-forward, or repeated QPE circuit was generated. The cheap-magic cases are diagnostic assumptions only and are not a STAR architecture implementation or validation.

## Outputs

- Config: `configs/surface_code_magic_supply_cheap_h2_h10_center.yaml`
- CSV: `artifacts/surface_code_magic_supply_cheap_h2_h10_center/results.csv`
- JSONL: `artifacts/surface_code_magic_supply_cheap_h2_h10_center/results.jsonl`
- Sweep markdown: `artifacts/surface_code_magic_supply_cheap_h2_h10_center/results.md`
- Run log: `artifacts/surface_code_magic_supply_cheap_h2_h10_center/logs/run.log`

## Main Findings

- Magic count and magic depth are invariant across all six magic regimes for every molecule/PF group. The magic supply conditions changed scheduling/resource estimates, not logical magic demand.
- `cheap_p1_center` and `cheap_p1_large_stock_center` are identical for all 18 molecule/PF groups in both runtime and qubit volume. With period 1, fixed stock 10000 was already not binding in this diagnostic.
- Runtime improvement saturates quickly as H-chain size grows. From `fast_p8_center` to `cheap_p1_center`, H10 improves by only 0.0176% for 2nd PF and 0.0034% for 4th(new_2).
- The largest runtime sensitivity is at H2: `normal_p15_center` to `cheap_p1_center` improves by 10.2737% for 2nd PF and 6.5016% for 4th(new_2). This does not persist for larger H.
- 4th(new_2) is less sensitive to magic supply than 2nd PF in runtime. Weighted across H2-H10, `p15 -> p1` improves runtime by 0.0753% for 2nd PF and 0.0169% for 4th(new_2).
- Qubit volume improvements are larger than runtime improvements in several small-H cases, but exposed spatial fields (`chip_cells`, `physical_qubits`, `code_distance`) are constant within every molecule/PF group across regimes. The remaining qubit-volume movement is therefore not explained by those exposed spatial fields.

## Runtime Totals

These are QPE-scale linear extrapolated `total_runtime_with_topology` values.

| molecule | PF | p15 | p8 | p4 | p2 | p1 | p1 large |
|---|---|---:|---:|---:|---:|---:|---:|
| H2 | 2nd | 823,174,482 | 739,232,052 | 738,872,940 | 738,693,384 | 738,603,606 | 738,603,606 |
| H2 | 4th(new_2) | 226,188,000 | 211,533,984 | 211,504,320 | 211,489,488 | 211,482,072 | 211,482,072 |
| H3 | 2nd | 5,704,659,452 | 5,599,050,970 | 5,590,381,617 | 5,590,381,617 | 5,590,381,617 | 5,590,381,617 |
| H3 | 4th(new_2) | 1,807,590,600 | 1,800,135,000 | 1,799,472,825 | 1,799,464,650 | 1,799,464,650 | 1,799,464,650 |
| H4 | 2nd | 28,425,875,264 | 28,273,674,144 | 28,211,635,644 | 28,207,334,308 | 28,207,334,308 | 28,207,334,308 |
| H4 | 4th(new_2) | 8,900,402,238 | 8,891,404,379 | 8,886,998,380 | 8,886,659,457 | 8,886,659,457 | 8,886,659,457 |
| H5 | 2nd | 51,414,608,824 | 51,306,389,888 | 51,255,741,580 | 51,233,820,900 | 51,233,244,040 | 51,233,244,040 |
| H5 | 4th(new_2) | 20,660,717,055 | 20,651,955,555 | 20,647,973,940 | 20,646,202,170 | 20,646,143,760 | 20,646,143,760 |
| H6 | 2nd | 208,643,824,736 | 208,368,778,560 | 208,272,654,400 | 208,231,801,632 | 208,230,490,848 | 208,230,490,848 |
| H6 | 4th(new_2) | 53,108,240,020 | 53,093,756,980 | 53,088,650,780 | 53,086,608,300 | 53,086,480,645 | 53,086,480,645 |
| H7 | 2nd | 339,154,583,740 | 338,919,545,776 | 338,801,841,140 | 338,747,815,826 | 338,740,018,358 | 338,740,018,358 |
| H7 | 4th(new_2) | 100,225,100,304 | 100,210,593,672 | 100,203,170,886 | 100,199,939,658 | 100,199,374,758 | 100,199,374,758 |
| H8 | 2nd | 820,704,728,992 | 820,264,537,416 | 820,090,951,936 | 820,014,362,312 | 820,002,701,608 | 820,002,701,608 |
| H8 | 4th(new_2) | 207,111,351,930 | 207,089,354,325 | 207,081,190,680 | 207,077,276,420 | 207,076,954,700 | 207,076,954,700 |
| H9 | 2nd | 1,264,981,771,298 | 1,264,583,076,479 | 1,264,377,956,224 | 1,264,281,660,248 | 1,264,264,955,844 | 1,264,264,955,844 |
| H9 | 4th(new_2) | 331,394,860,440 | 331,373,775,000 | 331,363,154,760 | 331,357,948,000 | 331,357,457,040 | 331,357,457,040 |
| H10 | 2nd | 2,422,161,855,663 | 2,421,562,341,279 | 2,421,288,403,509 | 2,421,158,676,657 | 2,421,136,320,816 | 2,421,136,320,816 |
| H10 | 4th(new_2) | 553,468,604,976 | 553,441,820,706 | 553,429,695,114 | 553,423,978,368 | 553,422,954,060 | 553,422,954,060 |

## Runtime Improvement

Positive values mean lower runtime in the later regime.

| molecule | PF | p15->p8 | p8->p4 | p4->p2 | p2->p1 | p8->p1 | p15->p1 |
|---|---|---:|---:|---:|---:|---:|---:|
| H2 | 2nd | 10.1974% | 0.0486% | 0.0243% | 0.0122% | 0.0850% | 10.2737% |
| H2 | 4th(new_2) | 6.4787% | 0.0140% | 0.0070% | 0.0035% | 0.0245% | 6.5016% |
| H3 | 2nd | 1.8513% | 0.1548% | 0.0000% | 0.0000% | 0.1548% | 2.0032% |
| H3 | 4th(new_2) | 0.4125% | 0.0368% | 0.0005% | 0.0000% | 0.0372% | 0.4495% |
| H4 | 2nd | 0.5354% | 0.2194% | 0.0152% | 0.0000% | 0.2346% | 0.7688% |
| H4 | 4th(new_2) | 0.1011% | 0.0496% | 0.0038% | 0.0000% | 0.0534% | 0.1544% |
| H5 | 2nd | 0.2105% | 0.0987% | 0.0428% | 0.0011% | 0.1426% | 0.3527% |
| H5 | 4th(new_2) | 0.0424% | 0.0193% | 0.0086% | 0.0003% | 0.0281% | 0.0705% |
| H6 | 2nd | 0.1318% | 0.0461% | 0.0196% | 0.0006% | 0.0664% | 0.1981% |
| H6 | 4th(new_2) | 0.0273% | 0.0096% | 0.0038% | 0.0002% | 0.0137% | 0.0410% |
| H7 | 2nd | 0.0693% | 0.0347% | 0.0159% | 0.0023% | 0.0530% | 0.1222% |
| H7 | 4th(new_2) | 0.0145% | 0.0074% | 0.0032% | 0.0006% | 0.0112% | 0.0257% |
| H8 | 2nd | 0.0536% | 0.0212% | 0.0093% | 0.0014% | 0.0319% | 0.0855% |
| H8 | 4th(new_2) | 0.0106% | 0.0039% | 0.0019% | 0.0002% | 0.0060% | 0.0166% |
| H9 | 2nd | 0.0315% | 0.0162% | 0.0076% | 0.0013% | 0.0252% | 0.0567% |
| H9 | 4th(new_2) | 0.0064% | 0.0032% | 0.0016% | 0.0001% | 0.0049% | 0.0113% |
| H10 | 2nd | 0.0248% | 0.0113% | 0.0054% | 0.0009% | 0.0176% | 0.0423% |
| H10 | 4th(new_2) | 0.0048% | 0.0022% | 0.0010% | 0.0002% | 0.0034% | 0.0082% |

## Qubit Volume Improvement

Positive values mean lower `total_qubit_volume` in the later regime.

| molecule | PF | p15->p8 | p8->p4 | p4->p2 | p2->p1 | p8->p1 | p15->p1 |
|---|---|---:|---:|---:|---:|---:|---:|
| H2 | 2nd | 9.3777% | 2.0601% | 0.2834% | 0.0017% | 2.3393% | 11.4977% |
| H2 | 4th(new_2) | 7.2251% | 1.7904% | 0.1458% | 0.0005% | 1.9341% | 9.0194% |
| H3 | 2nd | 2.8827% | 1.2119% | 0.0371% | 0.0000% | 1.2486% | 4.0953% |
| H3 | 4th(new_2) | 1.7468% | 1.0106% | 0.0065% | 0.0000% | 1.0171% | 2.7461% |
| H4 | 2nd | 1.3609% | 0.6662% | 0.0339% | 0.0000% | 0.6999% | 2.0512% |
| H4 | 4th(new_2) | 0.9607% | 0.5379% | 0.0075% | 0.0000% | 0.5454% | 1.5008% |
| H5 | 2nd | 0.8810% | 0.3752% | 0.0307% | 0.0063% | 0.4121% | 1.2894% |
| H5 | 4th(new_2) | 0.7537% | 0.3298% | 0.0061% | 0.0015% | 0.3373% | 1.0885% |
| H6 | 2nd | 0.7492% | 0.2638% | 0.0114% | 0.0026% | 0.2778% | 1.0249% |
| H6 | 4th(new_2) | 0.6576% | 0.2303% | 0.0024% | 0.0006% | 0.2333% | 0.8894% |
| H7 | 2nd | 0.5047% | 0.1067% | 0.0110% | 0.0031% | 0.1209% | 0.6250% |
| H7 | 4th(new_2) | 0.4550% | 0.0793% | 0.0023% | 0.0007% | 0.0822% | 0.5368% |
| H8 | 2nd | 0.3785% | 0.0520% | 0.0059% | 0.0015% | 0.0594% | 0.4377% |
| H8 | 4th(new_2) | 0.3474% | 0.0428% | 0.0012% | 0.0002% | 0.0442% | 0.3914% |
| H9 | 2nd | 0.3224% | 0.0125% | 0.0051% | 0.0014% | 0.0190% | 0.3413% |
| H9 | 4th(new_2) | 0.3059% | 0.0032% | 0.0011% | 0.0002% | 0.0045% | 0.3104% |
| H10 | 2nd | 0.2696% | 0.0071% | 0.0046% | 0.0008% | 0.0125% | 0.2821% |
| H10 | 4th(new_2) | 0.2655% | 0.0014% | 0.0009% | 0.0002% | 0.0024% | 0.2679% |

## Runtime Ratios

| molecule | PF | p8/p15 | p4/p15 | p2/p15 | p1/p15 | p4/p8 | p2/p8 | p1/p8 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| H2 | 2nd | 0.898026 | 0.897590 | 0.897372 | 0.897263 | 0.999514 | 0.999271 | 0.999150 |
| H2 | 4th(new_2) | 0.935213 | 0.935082 | 0.935016 | 0.934984 | 0.999860 | 0.999790 | 0.999755 |
| H3 | 2nd | 0.981487 | 0.979968 | 0.979968 | 0.979968 | 0.998452 | 0.998452 | 0.998452 |
| H3 | 4th(new_2) | 0.995875 | 0.995509 | 0.995505 | 0.995505 | 0.999632 | 0.999628 | 0.999628 |
| H4 | 2nd | 0.994646 | 0.992463 | 0.992312 | 0.992312 | 0.997806 | 0.997654 | 0.997654 |
| H4 | 4th(new_2) | 0.998989 | 0.998494 | 0.998456 | 0.998456 | 0.999504 | 0.999466 | 0.999466 |
| H5 | 2nd | 0.997895 | 0.996910 | 0.996484 | 0.996473 | 0.999013 | 0.998586 | 0.998574 |
| H5 | 4th(new_2) | 0.999576 | 0.999383 | 0.999297 | 0.999295 | 0.999807 | 0.999721 | 0.999719 |
| H6 | 2nd | 0.998682 | 0.998221 | 0.998025 | 0.998019 | 0.999539 | 0.999343 | 0.999336 |
| H6 | 4th(new_2) | 0.999727 | 0.999631 | 0.999593 | 0.999590 | 0.999904 | 0.999865 | 0.999863 |
| H7 | 2nd | 0.999307 | 0.998960 | 0.998801 | 0.998778 | 0.999653 | 0.999493 | 0.999470 |
| H7 | 4th(new_2) | 0.999855 | 0.999781 | 0.999749 | 0.999743 | 0.999926 | 0.999894 | 0.999888 |
| H8 | 2nd | 0.999464 | 0.999252 | 0.999159 | 0.999145 | 0.999788 | 0.999695 | 0.999681 |
| H8 | 4th(new_2) | 0.999894 | 0.999854 | 0.999835 | 0.999834 | 0.999961 | 0.999942 | 0.999940 |
| H9 | 2nd | 0.999685 | 0.999523 | 0.999447 | 0.999433 | 0.999838 | 0.999762 | 0.999748 |
| H9 | 4th(new_2) | 0.999936 | 0.999904 | 0.999889 | 0.999887 | 0.999968 | 0.999952 | 0.999951 |
| H10 | 2nd | 0.999752 | 0.999639 | 0.999586 | 0.999577 | 0.999887 | 0.999833 | 0.999824 |
| H10 | 4th(new_2) | 0.999952 | 0.999930 | 0.999919 | 0.999918 | 0.999978 | 0.999968 | 0.999966 |

## Qubit Volume Ratios vs p8

| molecule | PF | p15/p8 | p4/p8 | p2/p8 | p1/p8 | p1 large/p8 |
|---|---|---:|---:|---:|---:|---:|
| H2 | 2nd | 1.103482 | 0.979399 | 0.976624 | 0.976607 | 0.976607 |
| H2 | 4th(new_2) | 1.077877 | 0.982096 | 0.980664 | 0.980659 | 0.980659 |
| H3 | 2nd | 1.029683 | 0.987881 | 0.987514 | 0.987514 | 0.987514 |
| H3 | 4th(new_2) | 1.017779 | 0.989894 | 0.989829 | 0.989829 | 0.989829 |
| H4 | 2nd | 1.013796 | 0.993338 | 0.993001 | 0.993001 | 0.993001 |
| H4 | 4th(new_2) | 1.009700 | 0.994621 | 0.994546 | 0.994546 | 0.994546 |
| H5 | 2nd | 1.008888 | 0.996248 | 0.995942 | 0.995879 | 0.995879 |
| H5 | 4th(new_2) | 1.007595 | 0.996702 | 0.996642 | 0.996627 | 0.996627 |
| H6 | 2nd | 1.007549 | 0.997362 | 0.997248 | 0.997222 | 0.997222 |
| H6 | 4th(new_2) | 1.006619 | 0.997697 | 0.997673 | 0.997667 | 0.997667 |
| H7 | 2nd | 1.005073 | 0.998933 | 0.998822 | 0.998791 | 0.998791 |
| H7 | 4th(new_2) | 1.004571 | 0.999207 | 0.999185 | 0.999178 | 0.999178 |
| H8 | 2nd | 1.003800 | 0.999480 | 0.999421 | 0.999406 | 0.999406 |
| H8 | 4th(new_2) | 1.003486 | 0.999572 | 0.999560 | 0.999558 | 0.999558 |
| H9 | 2nd | 1.003235 | 0.999875 | 0.999824 | 0.999810 | 0.999810 |
| H9 | 4th(new_2) | 1.003068 | 0.999968 | 0.999957 | 0.999955 | 0.999955 |
| H10 | 2nd | 1.002703 | 0.999929 | 0.999883 | 0.999875 | 0.999875 |
| H10 | 4th(new_2) | 1.002662 | 0.999986 | 0.999977 | 0.999976 | 0.999976 |

## PF Means

Weighted values are weighted by absolute resource totals across H2-H10. The unweighted value averages molecule-level percentages.

| PF | metric | p15->p8 weighted | p8->p1 weighted | p15->p1 weighted | p15->p1 unweighted avg |
|---|---|---:|---:|---:|---:|
| 2nd | total_runtime_with_topology | 0.0466% | 0.0287% | 0.0753% | 1.5448% |
| 2nd | total_qubit_volume | 0.3336% | 0.0395% | 0.3729% | 2.4050% |
| 4th(new_2) | total_runtime_with_topology | 0.0109% | 0.0061% | 0.0169% | 0.8088% |
| 4th(new_2) | total_qubit_volume | 0.3212% | 0.0274% | 0.3485% | 1.8612% |

## p1 vs p1 Large Stock

`cheap_p1_center` and `cheap_p1_large_stock_center` match exactly for:

- `total_runtime_with_topology`
- `total_qubit_volume`
- `runtime_with_topology`
- `qubit_volume`
- exposed spatial fields checked in this analysis

Observed result: increasing the fixed magic stock from 10000 to 1000000 has no effect once the generation period is already 1 in this setup.

## Interpretation

### Observed

- The sweep completed all 108 expected cases with no failures.
- Magic count and magic depth are unchanged across architecture cases for the same molecule/PF.
- `p15 -> p8` captures most of the visible runtime improvement for H2 and H3.
- Further reducing period from 8 to 4, 2, and 1 has very small marginal impact, especially from H8-H10.
- `chip_cells`, `physical_qubits`, and `code_distance` do not vary across magic regimes within any molecule/PF group.

### Inferred

- Since magic count/depth are invariant, the cheap-magic assumption changes scheduling/resource estimates rather than logical circuit demand.
- For larger H-chains, current results suggest magic-state supply is not the dominant runtime bottleneck under this fixed center topology and fixed factory-count setup.
- The larger qubit-volume movement in small-H cases likely reflects runtime and qret-internal scheduling/layout occupancy effects, because exposed chip/cell/code-distance fields are unchanged.
- 4th(new_2) appears less sensitive to magic supply than 2nd PF in runtime.

### Unresolved

- The exposed fields do not fully explain why qubit-volume percentages can exceed runtime percentages. Additional compile-info or mapping diagnostics would be needed to separate internal occupancy from scheduling effects.
- `total_runtime_difference_vs_topology_free` changes non-monotonically in some cases and should not be over-interpreted without a separate topology-free diagnostic.
- These results are for `factory_center_block` only. They do not say whether left/right topologies respond differently to cheap magic.
- These results do not evaluate STAR itself. They only evaluate a cheap magic supply assumption.

## Not Changed

- No full QPE circuit was generated.
- Topology was fixed to `factory_center_block`.
- Factory count and grid size were fixed by the topology file.
- Logical circuit scope was fixed to `efficient_controlled_pf_one_step`.
- Target error was fixed at `0.00015936001019904`.
- QEC conditions were fixed.
