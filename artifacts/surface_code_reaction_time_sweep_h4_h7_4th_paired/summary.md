# H4-H7 Paired-Precision Reaction-Time Sweep

The logical circuit is fixed within each precision. The 10x10 mapping, four accessible factories, factory egress, magic supply, and QEC inputs are fixed across reaction-time cases. Absolute runtime is not compared across precision as an architecture effect.

## rotation_precision=1e-05

| molecule | reaction | runtime | vs reaction=1 | delta/extra cycle | serial feedback fraction | topology overhead | classical wait | condition wait | no stock | code distance | QV vs reaction=1 | workload match |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| H4 | 1 | 814,084 | +0.0000% | reference | reference | 1 | 0 | 0 | 12,970 | 13 | +0.0000% | yes |
| H4 | 10 | 2,376,771 | +191.9565% | 173,631.889 | 0.999332 | -21 | 0 | 0 | 5,776 | 15 | +162.2269% | yes |
| H4 | 100 | 18,013,891 | +2112.7804% | 173,735.424 | 0.999928 | 1 | 0 | 0 | 12 | 17 | +1790.8448% | yes |
| H5 | 1 | 2,122,291 | +0.0000% | reference | reference | 26 | 0 | 0 | 20,200 | 15 | +0.0000% | yes |
| H5 | 10 | 6,183,023 | +191.3372% | 451,192.444 | 0.999846 | 691 | 0 | 0 | 16,757 | 15 | +165.2321% | yes |
| H5 | 100 | 46,798,623 | +2105.0993% | 451,276.081 | 1.000031 | 3,009 | 0 | 0 | 12 | 17 | +1821.9934% | yes |
| H6 | 1 | 4,576,290 | +0.0000% | reference | reference | 5 | 0 | 0 | 22,270 | 15 | +0.0000% | yes |
| H6 | 10 | 13,272,760 | +190.0332% | 966,274.444 | 0.999882 | 573 | 0 | 0 | 18,723 | 17 | +166.3301% | yes |
| H6 | 100 | 100,249,393 | +2090.6259% | 966,394.980 | 1.000007 | 2,671 | 0 | 0 | 26 | 19 | +1834.2090% | yes |
| H7 | 1 | 8,871,700 | +0.0000% | reference | reference | 838 | 0 | 0 | 39,040 | 17 | +0.0000% | yes |
| H7 | 10 | 25,625,849 | +188.8494% | 1,861,572.111 | 0.999980 | 2,485 | 0 | 0 | 34,781 | 17 | +168.2936% | yes |
| H7 | 100 | 193,177,237 | +2077.4546% | 1,861,672.091 | 1.000033 | 9,437 | 0 | 0 | 10 | 19 | +1853.2788% | yes |

## rotation_precision=1e-02

| molecule | reaction | runtime | vs reaction=1 | delta/extra cycle | serial feedback fraction | topology overhead | classical wait | condition wait | no stock | code distance | QV vs reaction=1 | workload match |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| H4 | 1 | 146,410 | +0.0000% | reference | reference | 1 | 0 | 0 | 1,333 | 13 | +0.0000% | yes |
| H4 | 10 | 236,025 | +61.2083% | 9,957.222 | 0.978501 | -75 | 0 | 0 | 14 | 13 | +44.3277% | yes |
| H4 | 100 | 1,150,155 | +685.5713% | 10,138.838 | 0.996348 | 1 | 0 | 0 | 14 | 15 | +496.9503% | yes |
| H5 | 1 | 362,312 | +0.0000% | reference | reference | 1 | 0 | 0 | 1,235 | 13 | +0.0000% | yes |
| H5 | 10 | 516,983 | +42.6900% | 17,185.667 | 0.994311 | -76 | 0 | 0 | 12 | 13 | +32.0481% | yes |
| H5 | 100 | 2,072,543 | +472.0327% | 17,275.061 | 0.999483 | 1 | 0 | 0 | 12 | 15 | +354.6010% | yes |
| H6 | 1 | 712,896 | +0.0000% | reference | reference | -176 | 0 | 0 | 1,328 | 15 | +0.0000% | yes |
| H6 | 10 | 847,851 | +18.9305% | 14,995.000 | 0.980706 | -134 | 0 | 0 | 14 | 15 | +14.2096% | yes |
| H6 | 100 | 2,219,007 | +211.2666% | 15,213.242 | 0.994980 | 1 | 0 | 0 | 14 | 15 | +158.5199% | yes |
| H7 | 1 | 1,385,877 | +0.0000% | reference | reference | 684 | 0 | 0 | 1,229 | 15 | +0.0000% | yes |
| H7 | 10 | 1,571,793 | +13.4150% | 20,657.333 | 0.990664 | 719 | 0 | 0 | 14 | 15 | +10.3015% | yes |
| H7 | 100 | 3,446,223 | +148.6673% | 20,811.576 | 0.998061 | 841 | 0 | 0 | 14 | 15 | +114.1552% | yes |

## Precision-Regime Sensitivity

| molecule | reaction=10 penalty at 1e-5 | reaction=10 penalty at 1e-2 | reaction=100 penalty at 1e-5 | reaction=100 penalty at 1e-2 |
|---|---:|---:|---:|---:|
| H4 | +191.9565% | +61.2083% | +2112.7804% | +685.5713% |
| H5 | +191.3372% | +42.6900% | +2105.0993% | +472.0327% |
| H6 | +190.0332% | +18.9305% | +2090.6259% | +211.2666% |
| H7 | +188.8494% | +13.4150% | +2077.4546% | +148.6673% |

## Validity and Execution

- Fixed logical workload must match within each molecule/precision; reaction time may change only architecture-dependent runtime fields.
- Feedback count/depth are fixed within each molecule/precision and are coupled to magic-state injection in the current circuit.
- Reaction values 1/10/100 are diagnostic cycle counts, not a claim about a specific controller implementation.
- peak qret RSS: 11,482,852 KiB (10.95 GiB)
- maximum GNU-time swaps: 0
- intended execution: sequential tmux session with `MemoryHigh=44G`, `MemoryMax=48G`
- diagnostic `libqret-core.so` SHA-256: `f833e2b5dc5f8449ea8522d71699e209c6c3c94638333c6d930f4d6475eefd90`
- local diagnostic patch SHA-256: `65180e945107e8f68eda3fea8561655a1f9dc5e0ff3f349065d1c0585bcf722c`
