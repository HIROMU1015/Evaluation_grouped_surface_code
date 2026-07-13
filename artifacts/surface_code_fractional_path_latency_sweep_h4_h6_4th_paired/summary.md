# Dim2 Fractional Path-Latency Sensitivity

Latency is `base + ceil(numerator * max(path_coordinates - 1, 0) / denominator)`. The coefficients are diagnostic sensitivity parameters, not calibrated hardware values. Every comparison keeps the logical circuit fixed within molecule and precision.

| stage | molecule | precision | family | model | intermediate runtime | stress runtime | stress physical runtime | code distances | intermediate QV | stress QV | runtime monotonic |
|---|---|---:|---|---|---:|---:|---:|---|---:|---:|---|
| screening | H4 | 1e-05 | placement | quarter | +4.4430% | +19.6591% | +19.6591% | 15/15/15 | +7.6805% | +44.1717% | True |
| screening | H4 | 1e-05 | placement | half | +8.0389% | +40.9114% | +40.9114% | 15/15/15 | +12.2056% | +75.1691% | True |
| screening | H4 | 1e-05 | placement | unit | +15.6053% | +80.7483% | +80.7483% | 15/15/15 | +20.9959% | +131.6307% | True |
| screening | H4 | 1e-05 | routing | quarter | +0.7970% | +1.3967% | +1.3967% | 15/15/15 | +3.0423% | +5.5913% | True |
| screening | H4 | 1e-05 | routing | half | +2.4297% | +3.7549% | +3.7549% | 15/15/15 | +5.5561% | +10.1275% | True |
| screening | H4 | 1e-05 | routing | unit | +4.7945% | +7.4604% | +7.4604% | 15/15/15 | +9.6678% | +17.6717% | True |
| screening | H4 | 1e-02 | placement | quarter | +2.0188% | +11.3936% | +11.3936% | 13/13/13 | +5.1902% | +30.1774% | True |
| screening | H4 | 1e-02 | placement | half | +4.6821% | +24.6671% | +24.6671% | 13/13/13 | +8.7661% | +49.9125% | True |
| screening | H4 | 1e-02 | placement | unit | +9.1808% | +45.1850% | +45.1850% | 13/13/13 | +14.6658% | +79.8423% | True |
| screening | H4 | 1e-02 | routing | quarter | +3.4527% | +6.7228% | +6.7228% | 13/13/13 | +10.3412% | +22.9670% | True |
| screening | H4 | 1e-02 | routing | half | +7.5948% | +15.3323% | +15.3323% | 13/13/13 | +17.0403% | +39.0930% | True |
| screening | H4 | 1e-02 | routing | unit | +13.0752% | +27.0365% | +27.0365% | 13/13/13 | +25.7282% | +61.4000% | True |
| replication | H5 | 1e-05 | placement | quarter | +3.6082% | +18.3965% | +18.3965% | 15/15/15 | +5.5793% | +36.8183% | True |
| replication | H5 | 1e-05 | placement | unit | +9.4911% | +67.2856% | +67.2856% | 15/15/15 | +12.0181% | +102.4547% | True |
| replication | H5 | 1e-05 | routing | quarter | +1.4486% | +3.0946% | +3.0946% | 15/15/15 | +3.5460% | +7.7860% | True |
| replication | H5 | 1e-05 | routing | unit | +5.2566% | +8.9826% | +8.9826% | 15/15/15 | +10.0256% | +19.7161% | True |
| replication | H5 | 1e-02 | placement | quarter | +2.4145% | +11.6948% | +11.6948% | 13/13/13 | +5.4941% | +28.5860% | True |
| replication | H5 | 1e-02 | placement | unit | +9.0652% | +41.0845% | +62.7898% | 13/13/15 | +14.2708% | +72.5966% | True |
| replication | H5 | 1e-02 | routing | quarter | +3.6144% | +7.5757% | +7.5757% | 13/13/13 | +9.4213% | +21.7689% | True |
| replication | H5 | 1e-02 | routing | unit | +12.6212% | +26.5775% | +46.0510% | 13/13/15 | +23.1439% | +55.8211% | True |
| replication | H6 | 1e-05 | placement | quarter | +3.1983% | +15.2385% | +30.6037% | 15/15/17 | +5.8266% | +29.0206% | True |
| replication | H6 | 1e-05 | placement | unit | +13.8239% | +56.7419% | +77.6408% | 15/17/17 | +17.5855% | +82.0608% | True |
| replication | H6 | 1e-05 | routing | quarter | +4.5913% | +5.7248% | +5.7248% | 15/15/15 | +8.5941% | +11.6099% | True |
| replication | H6 | 1e-05 | routing | unit | +13.1646% | +16.3186% | +31.8278% | 15/17/17 | +20.9905% | +28.3319% | True |
| replication | H6 | 1e-02 | placement | quarter | +2.5740% | +12.1934% | +12.1934% | 15/15/15 | +5.0798% | +26.7951% | True |
| replication | H6 | 1e-02 | placement | unit | +9.6969% | +38.2741% | +38.2741% | 15/15/15 | +13.6573% | +63.5091% | True |
| replication | H6 | 1e-02 | routing | quarter | +4.3484% | +7.9820% | +7.9820% | 15/15/15 | +10.0291% | +20.6079% | True |
| replication | H6 | 1e-02 | routing | unit | +14.8772% | +27.7958% | +27.7958% | 15/15/15 | +25.1526% | +52.4542% | True |

- completed cases: `120`
- fixed-workload checks passed: `True`
- nonfixed runtime-monotonic groups: `28/28`
- nonfixed physical-runtime-monotonic groups: `28/28`
- architecture-metric-monotonic groups: `40/40`
- peak per-case RSS: `1.94 GiB`
- maximum swaps: `0`
- diagnostic patch SHA-256: `be80d0251428081b5970d714b0177a4f6f6dcb7c5a1b3012f6fb426695637d71`
