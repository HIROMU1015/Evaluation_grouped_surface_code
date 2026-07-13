# Dim2 Distance-Sensitive Routing Runtime

The routed operations use `base_latency + factor * max(path_coordinates - 1, 0)` during routing, resource occupancy, dependency release, runtime, and qubit-volume calculation. Factor 0 is the compatibility control; factor 1 is a diagnostic model, not a calibrated hardware latency.

| precision | molecule | family | stress | factor-0 runtime penalty | factor-1 runtime penalty | proxy depth penalty | full minus proxy | stress runtime increase vs factor 0 | physical runtime penalty | factor-1 QV penalty |
|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1e-05 | H4 | placement | perimeter | +0.0016% | +80.7483% | +82.8581% | -2.1098 pp | +115.1651% | +80.7483% | +131.6307% |
| 1e-05 | H4 | routing | choke | +0.0016% | +7.4604% | +16.8753% | -9.4149 pp | +27.9223% | +7.4604% | +17.6717% |
| 1e-05 | H7 | placement | perimeter | -0.0058% | +51.8940% | +56.6752% | -4.7812 pp | +102.8120% | +51.8940% | +71.5820% |
| 1e-05 | H7 | routing | choke | +0.0092% | +14.5733% | +16.4404% | -1.8671 pp | +52.9553% | +14.5733% | +25.9887% |
| 1e-02 | H4 | placement | perimeter | +0.0328% | +45.1850% | +44.7803% | +0.4047 pp | +101.4735% | +45.1850% | +79.8423% |
| 1e-02 | H4 | routing | choke | +0.0055% | +27.0365% | +27.6570% | -0.6205 pp | +76.3369% | +27.0365% | +61.4000% |
| 1e-02 | H7 | placement | perimeter | -0.0509% | +33.8576% | +33.9994% | -0.1417 pp | +119.1995% | +33.8576% | +54.4422% |
| 1e-02 | H7 | routing | choke | +0.0421% | +38.3090% | +38.0453% | +0.2638 pp | +126.2381% | +38.3090% | +70.1817% |

- factor-0 exact runtime matches: `13/16`
- factor-0 maximum runtime delta: `7 beats (0.000079%)`
- factor-0 exact qubit-volume matches: `13/16`
- factor-0 maximum qubit-volume delta: `0.001112%`
- factor-0 compatibility within `0.002%`: `True`
- fixed-workload checks passed: `True`
- peak per-case RSS: `3.71 GiB`
- maximum swaps: `0`
- diagnostic patch SHA-256: `975e76209bc2117385ad1e657ec270263045a2ceb47a062b1905b2f91bd57120`
