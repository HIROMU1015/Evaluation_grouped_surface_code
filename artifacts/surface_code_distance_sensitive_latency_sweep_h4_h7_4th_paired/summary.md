# Dim2 Distance-Sensitive Latency Diagnostic

This is a diagnostic critical-path proxy, not a rerouted runtime, STAR, or hardware implementation. Factor 0 uses fixed instruction latency; factor 1 adds one node-weight beat per path coordinate after the first and recomputes the routed instruction DAG's longest dependency depth.

| precision | molecule | family | stress condition | fixed-latency depth penalty | distance-sensitive depth penalty | amplification | stress depth increase from latency model | physical-depth penalty | existing QV penalty |
|---:|---|---|---|---:|---:|---:|---:|---:|---:|
| 1e-05 | H4 | placement | perimeter | +0.0000% | +82.8581% | +82.8581 pp | +126.9064% | +82.8581% | +10.9380% |
| 1e-05 | H4 | routing | choke | +0.0000% | +16.8753% | +16.8753 pp | +45.0292% | +16.8753% | +2.7232% |
| 1e-05 | H7 | placement | perimeter | +0.0000% | +56.6752% | +56.6752 pp | +113.2757% | +56.6752% | +5.3565% |
| 1e-05 | H7 | routing | choke | +0.0000% | +16.4404% | +16.4404 pp | +58.5056% | +16.4404% | +2.0053% |
| 1e-02 | H4 | placement | perimeter | +0.0000% | +44.7803% | +44.7803 pp | +102.0269% | +44.7803% | +8.9832% |
| 1e-02 | H4 | routing | choke | +0.0000% | +27.6570% | +27.6570 pp | +78.1330% | +27.6570% | +6.5875% |
| 1e-02 | H7 | placement | perimeter | +0.0000% | +33.9994% | +33.9994 pp | +118.7366% | +33.9994% | +5.9014% |
| 1e-02 | H7 | routing | choke | +0.0000% | +38.0453% | +38.0453 pp | +125.3412% | +38.0453% | +6.8424% |

- fixed-workload checks passed: `True`
- peak per-case RSS: `3.44 GiB`
- maximum swaps: `0`
- diagnostic patch SHA-256: `f7a0cfe2b4216da0cc25faa565d2f5eb44684edd03200ced8a6572ed353b69d7`
