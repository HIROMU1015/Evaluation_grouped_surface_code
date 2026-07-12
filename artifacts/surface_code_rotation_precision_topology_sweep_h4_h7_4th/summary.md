# Cheap RZ Synthesis x Topology Sweep Summary

## Scope

- molecules: H4-H7
- PF: `4th(new_2)`
- circuit scope: `efficient_controlled_pf_one_step`
- rotation precision: `1e-5`, `1e-3`, `3e-3`, `1e-2`
- topology: `factory_left_edge`, `factory_center_block`, `factory_right_edge`
- magic generation period: 15
- factory count: 4
- fixed stock: 10000
- rows: 48 success / 0 failed / 0 skipped

`rotation_precision` は qret 上では回転近似精度を指定するが、この diagnostic では
回転合成誤差を目標エネルギー誤差へ伝播させず、RZ synthesis cost を変える surrogate
として扱う。ここでの結果は observed one-step compile/profile result と、その線形外挿で
ある QPE-scale estimate であり、full QPE compile result ではない。

## Resource reduction

`factory_center_block` で、各 precision を `1e-5` baseline と比較した single-step resource
の変化を示す。

| molecule | precision | magic count | magic depth | runtime | qubit volume | code distance |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| H4 | `1e-3` | -44.85% | -45.05% | -38.69% | -38.01% | 13 |
| H4 | `3e-3` | -60.94% | -61.37% | -53.54% | -52.41% | 13 |
| H4 | `1e-2` | -93.65% | -94.14% | -82.02% | -80.09% | 13 |
| H5 | `1e-3` | -47.60% | -47.47% | -40.42% | -39.46% | 15 |
| H5 | `3e-3` | -67.89% | -67.71% | -58.54% | -56.99% | 15 |
| H5 | `1e-2` | -96.02% | -96.17% | -82.93% | -80.60% | 13 |
| H6 | `1e-3` | -50.86% | -50.58% | -42.93% | -41.92% | 15 |
| H6 | `3e-3` | -77.99% | -77.92% | -66.90% | -65.22% | 15 |
| H6 | `1e-2` | -98.31% | -98.42% | -84.42% | -82.16% | 15 |
| H7 | `1e-3` | -56.50% | -56.23% | -47.80% | -46.59% | 15 |
| H7 | `3e-3` | -84.29% | -84.12% | -71.94% | -70.04% | 15 |
| H7 | `1e-2` | -98.83% | -98.88% | -84.39% | -82.08% | 15 |

## Topology spread

各 molecule / precision 内で次を用いる。

```text
spread = (maximum - minimum) / minimum
```

| molecule | precision | runtime spread | qubit-volume spread | QV minimum | QV maximum |
| --- | ---: | ---: | ---: | --- | --- |
| H4 | `1e-5` | 0.01904% | 12.821% | center | left |
| H4 | `1e-3` | 0.01683% | 11.344% | center | left |
| H4 | `3e-3` | 0.01322% | 10.421% | center | left |
| H4 | `1e-2` | 0.01639% | 4.152% | right | left |
| H5 | `1e-5` | 0.03228% | 9.072% | center | left |
| H5 | `1e-3` | 0.02175% | 7.100% | center | left |
| H5 | `3e-3` | 0.02102% | 5.332% | center | left |
| H5 | `1e-2` | 0.00193% | 1.808% | left | center |
| H6 | `1e-5` | 0.00474% | 7.847% | center | left |
| H6 | `1e-3` | 0.00636% | 6.264% | center | left |
| H6 | `3e-3` | 0.01050% | 4.436% | center | left |
| H6 | `1e-2` | 0.02595% | 0.189% | center | left |
| H7 | `1e-5` | 0.00813% | 6.740% | center | left |
| H7 | `1e-3` | 0.00844% | 4.930% | center | left |
| H7 | `3e-3` | 0.01065% | 2.443% | center | left |
| H7 | `1e-2` | 0.01733% | 1.038% | left | center |

## Interpretation

- precision を粗くすると、magic count / depth、runtime、qubit volume は大幅に低下する。
- qubit-volume topology spread は H4-H7 のすべてで単調に縮小した。cheap RZ によって
  architecture spread が拡大するという仮説は、今回の factory-placement sweep では
  支持されなかった。
- 既存 topology 差のかなりの部分は magic-state delivery geometry に由来すると考えられる。
  RZ synthesis demand を減らすと magic delivery traffic も減り、factory placement の差が
  小さくなるという解釈と整合する。
- runtime spread は全条件で 0.033% 未満であり、引き続き非常に小さい。
- `1e-2` では topology ordering が H4/H5/H7 で変化した。ただし spread 自体が小さいため、
  新しい best topology の強い証拠ではなく、残った Clifford routing / occupancy の差として
  追加確認が必要である。

QEC の離散変化も混ざる。

- H4 `1e-5`: left のみ distance 15、center/right は 13。`1e-3` 以降はすべて 13。
- H5: `1e-5` から `3e-3` は distance 15、`1e-2` はすべて 13。
- H6: 全条件で distance 15。
- H7: `1e-5` は distance 17、`1e-3` 以降は distance 15。

したがって precision 間の qubit-volume reduction には、RZ synthesis cost reduction に加えて
code-distance threshold crossing が含まれる case がある。一方、各 precision 内の topology
spread は、H4 `1e-5` を除けば code distance を固定した比較になっている。

## Next question

cheap RZ regime では factory placement sensitivity が弱くなったため、次は factory位置だけで
なく、外側の Clifford skeleton に直接効く logical-qubit initial placement、logical-cell grid、
system/control qubit communication、Clifford routing congestion を固定 precision 内で比較する
方が、残った architecture bottleneck を調べる上で優先度が高い。

`rotation_precision=1e-2` は magic demand を約94-99%減らす極端な diagnostic 条件であり、
現実の回転精度や STAR 固有 primitive cost を表すものではない。
