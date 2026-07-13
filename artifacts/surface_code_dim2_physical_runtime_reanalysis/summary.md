# Dim2 Physical-Runtime Reanalysis and Beat Calibration

The logical workload is fixed inside every contrast. Beat runtime and physical runtime are both reported relative to the architecture baseline; cross-precision runtime reduction is excluded.

Physical runtime is recomputed as `runtime_beats * code_distance * code_cycle_time_sec`. With the fixed cycle time, the relative ratio is `(runtime * d) / (runtime_baseline * d_baseline)`.

## Existing-sweep ranges

| experiment | precision | beat-runtime change | physical-runtime change | QV change | max |physical - beat| | distance changed |
|---|---:|---:|---:|---:|---:|---|
| accessible_factory_count_1e-2 | 1e-02 | +0.3176% to +24.3173% | +0.3176% to +24.3173% | +0.2525% to +17.8283% | 0.0000 pp | no |
| accessible_factory_count_1e-5 | 1e-05 | +11.1237% to +240.1390% | +11.1237% to +292.4681% | +11.4768% to +209.9176% | 52.3291 pp | yes |
| factory_placement | 1e-02 | -0.0004% to +0.0255% | -0.0004% to +0.0255% | -1.7757% to +4.0744% | 0.0000 pp | no |
| factory_placement | 1e-03 | -0.0013% to +0.0217% | -0.0013% to +0.0217% | +1.6087% to +11.3445% | 0.0000 pp | no |
| factory_placement | 1e-05 | -0.0007% to +0.0323% | -0.0007% to +15.3845% | +2.2066% to +12.8205% | 15.3846 pp | yes |
| factory_placement | 3e-03 | -0.0016% to +0.0210% | -0.0016% to +0.0210% | +1.1038% to +10.4208% | 0.0000 pp | no |
| factory_saturation | 1e-02 | -0.4501% to -0.1697% | -0.4501% to -0.1697% | -1.0699% to -0.4687% | 0.0000 pp | no |
| factory_saturation | 1e-05 | -0.0970% to -0.0279% | -0.0970% to -0.0279% | -5.6195% to -3.0711% | 0.0000 pp | no |
| grid_capacity_explicit | 1e-02 | -0.0610% to +0.1974% | -0.0610% to +0.1974% | -0.0238% to +1.6480% | 0.0000 pp | no |
| grid_capacity_explicit | 1e-05 | -0.0076% to +11.1215% | -0.0076% to +11.1215% | +0.3417% to +14.0575% | 0.0000 pp | no |
| logical_placement | 1e-02 | -0.0610% to +0.0328% | -0.0610% to +0.0328% | +1.7386% to +8.9832% | 0.0000 pp | no |
| logical_placement | 1e-05 | -0.0073% to +0.0021% | -0.0073% to +0.0021% | +1.2414% to +10.9380% | 0.0000 pp | no |
| magic_period_1e-2 | 1e-02 | -0.4569% to +100.0751% | -0.4569% to +100.0751% | -0.3425% to +71.4470% | 0.0000 pp | no |
| magic_stock | 1e-02 | +0.0000% to +2.1822% | +0.0000% to +2.1822% | +0.0303% to +2.4612% | 0.0000 pp | no |
| magic_stock | 1e-05 | +0.1011% to +4.2633% | +0.1011% to +4.2633% | +1.0135% to +6.3568% | 0.0000 pp | no |
| reaction_time | 1e-02 | +13.4150% to +685.5713% | +13.4150% to +806.4285% | +10.3015% to +496.9503% | 120.8571 pp | yes |
| reaction_time | 1e-05 | +188.8494% to +2112.7804% | +188.8494% to +2793.6359% | +162.2269% to +1853.2788% | 680.8555 pp | yes |
| routing_capacity | 1e-02 | -0.0013% to +0.1080% | -0.0013% to +0.1080% | +0.1232% to +6.8424% | 0.0000 pp | no |
| routing_capacity | 1e-05 | +0.0000% to +0.0093% | +0.0000% to +0.0093% | +0.0326% to +2.7232% | 0.0000 pp | no |

## Largest code-distance corrections

| experiment | precision | molecule | condition vs baseline | d | beat change | physical change | correction |
|---|---:|---|---|---:|---:|---:|---:|
| reaction_time | 1e-05 | H4 | 100 vs 1 | 17 vs 13 | +2112.7804% | +2793.6359% | +680.8555 pp |
| reaction_time | 1e-05 | H6 | 100 vs 1 | 19 vs 15 | +2090.6259% | +2674.7928% | +584.1669 pp |
| reaction_time | 1e-05 | H5 | 100 vs 1 | 17 vs 15 | +2105.0993% | +2399.1125% | +294.0132 pp |
| reaction_time | 1e-05 | H7 | 100 vs 1 | 19 vs 17 | +2077.4546% | +2333.6257% | +256.1711 pp |
| reaction_time | 1e-02 | H4 | 100 vs 1 | 15 vs 13 | +685.5713% | +806.4285% | +120.8571 pp |
| reaction_time | 1e-02 | H5 | 100 vs 1 | 15 vs 13 | +472.0327% | +560.0377% | +88.0050 pp |
| accessible_factory_count_1e-5 | 1e-05 | H4 | 1 vs 4 | 15 vs 13 | +240.1390% | +292.4681% | +52.3291 pp |
| reaction_time | 1e-05 | H4 | 10 vs 1 | 15 vs 13 | +191.9565% | +236.8729% | +44.9164 pp |
| accessible_factory_count_1e-5 | 1e-05 | H6 | 1 vs 4 | 17 vs 15 | +236.1285% | +280.9457% | +44.8171 pp |
| reaction_time | 1e-05 | H6 | 10 vs 1 | 17 vs 15 | +190.0332% | +228.7043% | +38.6711 pp |
| accessible_factory_count_1e-5 | 1e-05 | H4 | 2 vs 4 | 15 vs 13 | +70.0709% | +96.2357% | +26.1648 pp |
| accessible_factory_count_1e-5 | 1e-05 | H6 | 2 vs 4 | 17 vs 15 | +68.0646% | +90.4732% | +22.4086 pp |

## Model-internal beat calibration

Current sweeps use `code_cycle_time_sec = 1 us`, so one qret beat is `d` code cycles and maps to `d us`.

| code distance | one beat | reaction 1 | reaction 10 | reaction 100 |
|---:|---:|---:|---:|---:|
| 13 | 13 us | 13 us | 130 us | 1.300 ms |
| 15 | 15 us | 15 us | 150 us | 1.500 ms |
| 17 | 17 us | 17 us | 170 us | 1.700 ms |
| 19 | 19 us | 19 us | 190 us | 1.900 ms |

### Magic generation per factory

| d | period 1 | period 4 | period 15 | period 30 | period 100 |
|---:|---:|---:|---:|---:|---:|
| 13 | 13 us (76,923.1/s) | 52 us (19,230.8/s) | 195 us (5,128.2/s) | 390 us (2,564.1/s) | 1300 us (769.2/s) |
| 15 | 15 us (66,666.7/s) | 60 us (16,666.7/s) | 225 us (4,444.4/s) | 450 us (2,222.2/s) | 1500 us (666.7/s) |
| 17 | 17 us (58,823.5/s) | 68 us (14,705.9/s) | 255 us (3,921.6/s) | 510 us (1,960.8/s) | 1700 us (588.2/s) |
| 19 | 19 us (52,631.6/s) | 76 us (13,157.9/s) | 285 us (3,508.8/s) | 570 us (1,754.4/s) | 1900 us (526.3/s) |

These are internal-model conversions, not evidence that a physical factory actually achieves these rates. Hardware realism requires an independently justified code-cycle time and factory protocol latency.
