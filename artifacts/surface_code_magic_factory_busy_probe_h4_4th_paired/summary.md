# Dim2 Fractional Path-Latency Sensitivity

Latency is `base + ceil(numerator * max(path_coordinates - 1, 0) / denominator)`. The coefficients are diagnostic sensitivity parameters, not calibrated hardware values. Every comparison keeps the logical circuit fixed within molecule and precision.

| stage | molecule | precision | family | model | intermediate runtime | stress runtime | stress physical runtime | code distances | intermediate QV | stress QV | runtime monotonic |
|---|---|---:|---|---|---:|---:|---:|---|---:|---:|---|
| factory_busy_probe | H4 | 1e-05 | placement | quarter | +4.4357% | +19.6748% | +19.6748% | 15/15/15 | +7.6701% | +44.1445% | True |
| factory_busy_probe | H4 | 1e-05 | placement | unit | +15.5776% | +80.7589% | +80.7589% | 15/15/15 | +20.9589% | +131.6131% | True |
| factory_busy_probe | H4 | 1e-02 | placement | quarter | +2.0077% | +11.3860% | +11.3860% | 13/13/13 | +5.2029% | +30.1855% | True |
| factory_busy_probe | H4 | 1e-02 | placement | unit | +9.1798% | +45.2431% | +45.2431% | 13/13/13 | +14.6816% | +79.9248% | True |

## Factory endpoint busy comparison

| precision | model | reference overhead | stress overhead | unconstrained stress penalty | constrained stress penalty | penalty delta |
|---:|---|---:|---:|---:|---:|---:|
| 1e-05 | fixed | +0.0000% | +0.0000% | +0.0016% | +0.0016% | +0.0000 pp |
| 1e-05 | quarter | +0.0177% | +0.0309% | +19.6591% | +19.6748% | +0.0157 pp |
| 1e-05 | unit | +0.0290% | +0.0349% | +80.7483% | +80.7589% | +0.0106 pp |
| 1e-02 | fixed | +0.0000% | +0.0000% | +0.0328% | +0.0328% | +0.0000 pp |
| 1e-02 | quarter | +0.0257% | +0.0189% | +11.3936% | +11.3860% | -0.0076 pp |
| 1e-02 | unit | +0.0108% | +0.0508% | +45.1850% | +45.2431% | +0.0581 pp |

- completed cases: `18`
- fixed-workload checks passed: `True`
- nonfixed runtime-monotonic groups: `4/4`
- nonfixed physical-runtime-monotonic groups: `4/4`
- architecture-metric-monotonic groups: `6/6`
- peak per-case RSS: `0.35 GiB`
- maximum swaps: `0`
- diagnostic patch SHA-256: `adb997c8d5cff5cbcf3b87e360e410659d575eaa5ade4bd5c405f85b1f50f9fc`
