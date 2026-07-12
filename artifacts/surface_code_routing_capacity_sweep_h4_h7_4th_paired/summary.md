# H4-H7 Paired-Precision Routing-Capacity Sweep

The logical circuit is fixed within each precision. All routing conditions use the same 10x10 logical mapping, four factories, eight banned cells, 88 usable non-factory cells, and two initial egress cells per factory. Absolute runtime is not compared across precision as an architecture effect.

## rotation_precision=1e-05

| molecule | condition | runtime | vs remote | topology overhead | static CNOT delta | CNOT fail share | CNOT mean path | magic fail share | magic mean path | egress blocked | route disconnected | code distance | QV vs remote | semantic match |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| H4 | remote_ban_control | 814,084 | +0.0000% | 1 | +0 | 68.188% | 4.561 | 0.000% | 1.846 | 0 | 1 | 13 | +0.0000% | yes |
| H4 | distributed_obstacles | 814,085 | +0.0001% | 2 | +0 | 68.157% | 4.630 | 0.000% | 1.850 | 0 | 10 | 13 | +0.0326% | yes |
| H4 | central_choke | 814,097 | +0.0016% | 14 | +51,296 | 68.271% | 8.028 | 0.006% | 2.550 | 13 | 184 | 13 | +2.7232% | yes |
| H5 | remote_ban_control | 2,122,291 | +0.0000% | 26 | +0 | 68.714% | 4.771 | 0.000% | 2.152 | 1 | 5 | 15 | +0.0000% | yes |
| H5 | distributed_obstacles | 2,122,292 | +0.0000% | 27 | +1,648 | 68.694% | 5.027 | 0.000% | 2.285 | 1 | 5 | 15 | +0.3177% | yes |
| H5 | central_choke | 2,122,340 | +0.0023% | 75 | +134,192 | 68.823% | 8.201 | 0.001% | 2.460 | 5 | 348 | 15 | +1.6733% | yes |
| H6 | remote_ban_control | 4,576,315 | +0.0000% | 30 | +0 | 69.526% | 4.853 | 0.000% | 2.394 | 4 | 211 | 15 | +0.0000% | yes |
| H6 | distributed_obstacles | 4,576,329 | +0.0003% | 44 | +19,128 | 69.492% | 5.394 | 0.002% | 2.456 | 27 | 243 | 15 | +0.2672% | yes |
| H6 | central_choke | 4,576,622 | +0.0067% | 337 | +294,520 | 69.612% | 7.861 | 0.059% | 3.335 | 671 | 3,856 | 15 | +2.3909% | yes |
| H7 | remote_ban_control | 8,871,700 | +0.0000% | 838 | +0 | 70.283% | 5.086 | 0.000% | 2.265 | 0 | 290 | 17 | +0.0000% | yes |
| H7 | distributed_obstacles | 8,871,899 | +0.0022% | 1,037 | +61,680 | 70.321% | 5.651 | 0.000% | 2.336 | 0 | 1,571 | 17 | +0.2687% | yes |
| H7 | central_choke | 8,872,521 | +0.0093% | 1,659 | +851,760 | 70.049% | 9.053 | 0.000% | 2.857 | 2 | 4,185 | 17 | +2.0053% | yes |

## rotation_precision=1e-02

| molecule | condition | runtime | vs remote | topology overhead | static CNOT delta | CNOT fail share | CNOT mean path | magic fail share | magic mean path | egress blocked | route disconnected | code distance | QV vs remote | semantic match |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| H4 | remote_ban_control | 146,410 | +0.0000% | 1 | +0 | 70.220% | 4.529 | 0.000% | 1.858 | 0 | 0 | 13 | +0.0000% | yes |
| H4 | distributed_obstacles | 146,412 | +0.0014% | 3 | +0 | 70.188% | 4.586 | 0.000% | 1.895 | 0 | 4 | 13 | +0.1232% | yes |
| H4 | central_choke | 146,418 | +0.0055% | 9 | +51,296 | 70.139% | 8.229 | 0.006% | 2.235 | 1 | 50 | 13 | +6.5875% | yes |
| H5 | remote_ban_control | 362,312 | +0.0000% | 1 | +0 | 70.641% | 4.721 | 0.000% | 2.196 | 0 | 5 | 13 | +0.0000% | yes |
| H5 | distributed_obstacles | 362,312 | +0.0000% | 1 | +1,648 | 70.608% | 4.972 | 0.000% | 2.376 | 0 | 0 | 13 | +0.4924% | yes |
| H5 | central_choke | 362,430 | +0.0326% | 119 | +134,192 | 70.750% | 7.966 | 0.000% | 2.571 | 0 | 5 | 13 | +5.6837% | yes |
| H6 | remote_ban_control | 712,906 | +0.0000% | -166 | +0 | 71.535% | 4.841 | 0.000% | 2.484 | 0 | 0 | 15 | +0.0000% | yes |
| H6 | distributed_obstacles | 712,897 | -0.0013% | -175 | +19,128 | 71.568% | 5.390 | 0.000% | 2.642 | 0 | 10 | 15 | +1.0081% | yes |
| H6 | central_choke | 713,676 | +0.1080% | 604 | +294,520 | 72.175% | 7.851 | 0.000% | 3.058 | 0 | 233 | 15 | +5.5701% | yes |
| H7 | remote_ban_control | 1,385,876 | +0.0000% | 683 | +0 | 71.880% | 5.010 | 0.000% | 2.626 | 0 | 75 | 15 | +0.0000% | yes |
| H7 | distributed_obstacles | 1,385,983 | +0.0077% | 790 | +61,680 | 71.942% | 5.612 | 0.000% | 2.707 | 0 | 292 | 15 | +1.0524% | yes |
| H7 | central_choke | 1,386,459 | +0.0421% | 1,266 | +851,760 | 71.582% | 8.927 | 0.000% | 3.103 | 0 | 208 | 15 | +6.8424% | yes |

## Central-Choke Precision Comparison

| molecule | runtime penalty at 1e-5 | runtime penalty at 1e-2 | CNOT path increase at 1e-5 | CNOT path increase at 1e-2 |
|---|---:|---:|---:|---:|
| H4 | +0.0016% | +0.0055% | +76.0356% | +81.6760% |
| H5 | +0.0023% | +0.0326% | +71.8996% | +68.7326% |
| H6 | +0.0067% | +0.1080% | +61.9945% | +62.1956% |
| H7 | +0.0093% | +0.0421% | +78.0033% | +78.1659% |

## Validity and Execution

- Static preflight confirms a route for every weighted CNOT pair and keeps all logical qubits in a connected routing graph.
- The central choke preserves two initial egress cells per factory; runtime differences are not caused by the zero-egress pathology.
- The detailed diagnostic reports operation-specific CNOT and magic attempt/path aggregates; it does not retain per-attempt traces.
- peak qret RSS: 3,362,304 KiB (3.21 GiB)
- maximum GNU-time swaps: 0
- intended execution: sequential tmux session with `MemoryHigh=44G`, `MemoryMax=48G`
- diagnostic `libqret-core.so` SHA-256: `f833e2b5dc5f8449ea8522d71699e209c6c3c94638333c6d930f4d6475eefd90`
- local diagnostic patch SHA-256: `65180e945107e8f68eda3fea8561655a1f9dc5e0ff3f349065d1c0585bcf722c`
