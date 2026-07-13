# Fixed-Circuit Factory Count x Magic Period Interaction

All comparisons are within one molecule and one rotation precision. The optimized IR is fixed; only factory count and generation period change.

| precision | molecule | 3-factory penalty at period 15 | 3-factory penalty at period 30 | interaction | period-30 penalty with 4 factories | worst beat runtime vs f4/p15 | worst physical runtime vs f4/p15 | worst QV vs f4/p15 |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1e-05 | H4 | +13.3823% | +33.3333% | +19.9510 pp | +70.0719% | +126.7625% | +161.6490% | +109.3246% |
| 1e-05 | H5 | +12.1222% | +33.3330% | +21.2109 pp | +68.1830% | +124.2435% | +124.2435% | +109.2275% |
| 1e-05 | H6 | +12.0433% | +33.3332% | +21.2899 pp | +68.0647% | +124.0861% | +153.9643% | +110.1540% |
| 1e-05 | H7 | +11.1237% | +33.3333% | +22.2096 pp | +66.6854% | +122.2471% | +122.2471% | +110.6003% |
| 1e-02 | H4 | +1.1249% | +2.1931% | +1.0682 pp | +3.3959% | +5.6635% | +5.6635% | +3.7071% |
| 1e-02 | H5 | +0.6699% | +1.3203% | +0.6504 pp | +2.0182% | +3.3651% | +3.3651% | +2.3193% |
| 1e-02 | H6 | +0.4897% | +1.0272% | +0.5375 pp | +1.5340% | +2.5770% | +2.5770% | +1.7859% |
| 1e-02 | H7 | +0.3176% | +0.7154% | +0.3977 pp | +1.0398% | +1.7626% | +1.7626% | +1.2738% |

- Interaction is the period-30 three-factory penalty minus the period-15 three-factory penalty.
- Physical runtime uses `runtime * code_distance * code_cycle_time`; the fixed cycle time cancels in percentages.
- fixed-workload checks passed: `True`
- peak per-case RSS: `3.47 GiB`; maximum swaps: `0`
