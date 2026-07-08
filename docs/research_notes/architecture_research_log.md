# Architecture research log

## このノートの目的

このノートは、surface-code architecture 条件が resource metrics に与える影響について、研究の進行に沿って記録する日誌である。

主題は PF 次数差そのものではなく、同一 PF・同一 molecule・同一 logical circuit を固定したときに、topology、factory placement、magic-state supply、routing / mapping、grid size、factory count が runtime、qubit volume、chip cells、physical qubits、code distance、magic-state metrics にどう効くかを調べることである。

各追記では、目的、条件、観測、解釈、未解決点、次の作業を分けて書く。

## 2026-07-07: H2-H11 topology sweep の同一PF固定解析

### 目的

PF差ではなく、同一 molecule / PF / magic regime 内で topology 条件が resource metrics にどう効くかを見る。

### 条件

- molecules: H2-H11
- PF: 2nd, 4th(new_2)
- magic regime:
  - baseline: `magic_generation_period=15`
  - fast_supply: `magic_generation_period=8`
- topology:
  - `factory_left_edge`
  - `factory_center_block`
  - `factory_right_edge`
- grid size: 10x10
- factory count: 4
- circuit scope: `efficient_controlled_pf_one_step`
- full QPE: なし
- QPE-scale: one-step result からの線形外挿

### 観測

- 120行すべて `success`。
- runtime spread は全体として非常に小さい。
- PF=`2nd`:
  - baseline: runtime spread avg/max = `0.0095% / 0.0287%`
  - fast_supply: runtime spread avg/max = `0.0112% / 0.0364%`
  - baseline: qubit volume spread avg/max = `9.21% / 21.98%`
  - fast_supply: qubit volume spread avg/max = `9.24% / 24.40%`
- PF=`4th(new_2)`:
  - baseline: runtime spread avg/max = `0.0100% / 0.0323%`
  - fast_supply: runtime spread avg/max = `0.0087% / 0.0286%`
  - baseline: qubit volume spread avg/max = `9.16% / 21.38%`
  - fast_supply: qubit volume spread avg/max = `9.08% / 23.21%`
- `chip_cells` は全120行で96固定。
- `physical_qubits` / `code_distance` はほぼ固定。例外は H4 `4th(new_2)`。
- qubit volume 最小は `center_block` が 40/40。
- qubit volume 最大は `left_edge` が 40/40。
- runtime best topology は case ごとに揺れる。

### 解釈

- 今回の topology 条件では、factory placement は runtime にはほぼ効いていない。
- 一方で、qubit volume には一貫して効いている。
- runtime差が小さいことを architecture効果がないことと混同してはいけない。
- qubit volume差は runtime / chip_cells / physical_qubits だけでは説明しにくく、layout / routing / active area 側の違いが疑われる。
- fast_supply=`period 8` は STAR-like cheap magic と呼ぶには弱く、moderate fast-supply condition として扱うのが妥当。

### 未解決点

- なぜ `center_block` が全条件で qubit volume 最小になるのか。
- qubit volume 差はどの cell / path / operation に由来するのか。
- factory 4個が実効的に使われているのか。
- H4 `4th(new_2)` の code distance / physical qubits 例外をどう扱うか。

### 次の作業

- mapping-only diagnostic で active area / magic delivery geometry を見る。

### 参照

- `docs/benchmarks/surface_code_topology_sweep_h2_h11_baseline_fast.md`
- `artifacts/surface_code_topology_sweep_h2_h11_baseline_fast/results.csv`
- `artifacts/surface_code_topology_sweep_h2_h11_baseline_fast/results.jsonl`

---

## 2026-07-07: H4/H5 mapping-only diagnostic

### 目的

`center_block` が qubit volume 最小になる原因を mapping / layout / active area 側から確認する。

### 条件

- molecules: H4, H5
- PF: `4th(new_2)`
- magic:
  - baseline
  - fast_supply
- topology:
  - `factory_left_edge`
  - `factory_center_block`
  - `factory_right_edge`
- case数: 12
- 新規 full compile: なし
- 既存 `compile_info.json` を使用
- mapping-only diagnostic を実行
- raw `mapping_state.json` は大きいため解析後に削除

### 観測

- `center_block` が常に qubit volume 最小になる主因は `chip_cell_active_qubit_area_ave` が最小になるため。
- runtime はほぼ変わっていない。
- H4/H5 の全caseで `LATTICE_SURGERY_MAGIC` は magic factory symbol `0` のみを使用。
- factory 4個を置いていても、この条件では実効的には `m0` の位置が効いている。
- `left_edge`: `m0=(0,0)`, logical qubit cluster から遠い。
- `center_block`: `m0=(4,4)`, logical qubit cluster に近い。
- `right_edge`: `m0=(9,0)`, 中間的。

代表値:

| case | center magic dist mean | left magic dist mean | center active area | left active area |
|---|---:|---:|---:|---:|
| H4 baseline | 6.78 | 13.56 | 11.300 | 12.749 |
| H5 baseline | 6.83 | 12.84 | 13.416 | 14.632 |

center vs left:

- H4 baseline: volume差 `12.82%`, active-area差 `12.82%`
- H4 fast: volume差 `12.38%`, active-area差 `12.38%`
- H5 baseline: volume差 `9.07%`, active-area差 `9.07%`
- H5 fast: volume差 `8.76%`, active-area差 `8.76%`

### 解釈

- H4/H5 `4th(new_2)` では、qubit volume差は runtimeではなく active area差で説明できる。
- `center_block` が有利なのは、`m0` が logical qubit cluster に近く、magic delivery geometry が改善するためと推定できる。
- この結果は H4/H5 についての observed result であり、H2-H11全体への一般化はまだ未検証。
- H4 `left_edge` では code_distance / physical_qubits の例外があるが、H5ではそれらが固定のまま同じ `center < right < left` の ordering が出るため、一般的な原因は physical_qubits だけではない。

### 未解決点

- H2-H11全体で `m0` のみ使用か。
- 2nd PFでも同じか。
- quration/qret がなぜ symbol `0` のみを使うのか。
- symbol順序を入れ替えると結果が変わるか。
- 複数factoryを実効的に使わせる設定があるか。
- H8/H11など大きい系でも active area差が同じ原因で出るか。

### 次の作業

- H8/H11 mapping-only diagnostic。
- factory symbol / `m0` diagnostic。
- cheap_magic diagnostic。
- topology variants 追加。

### 参照

- `artifacts/surface_code_mapping_diagnostics_h4_h5_4th_new2/summary.md`
- `artifacts/surface_code_mapping_diagnostics_h4_h5_4th_new2/diagnostics.csv`
- `artifacts/surface_code_mapping_diagnostics_h4_h5_4th_new2/diagnostics.jsonl`

## 2026-07-07: H2-H10 cheap magic supply diagnostic

### Purpose

Evaluate whether surface-code QPE-scale resource estimates are still limited by
magic-state supply when the topology is fixed to `factory_center_block` and the
magic generation period is reduced below the previous fast-supply setting.

### Conditions

- Molecules: H2-H10.
- PF labels: `2nd` and `4th(new_2)`.
- Circuit scope: `efficient_controlled_pf_one_step`.
- Topology: fixed `factory_center_block`.
- Magic regimes: period 15, 8, 4, 2, 1 with stock 10000, plus period 1 with stock 1000000.
- Rows: 108 expected, 108 success, 0 failed, 0 skipped.

This is not a full QPE compile. QPE-scale totals are linear extrapolations from
one compiled/profiled efficient controlled PF step.

### Observations

- Magic count and magic depth are invariant across all magic regimes for each
  molecule/PF group.
- `cheap_p1_center` and `cheap_p1_large_stock_center` are identical in runtime
  and qubit volume for all 18 molecule/PF groups.
- Runtime improvement saturates strongly with H-chain size. From `fast_p8_center`
  to `cheap_p1_center`, H10 improves by 0.0176% for 2nd PF and 0.0034% for
  4th(new_2).
- Weighted across H2-H10, `p15 -> p1` improves runtime by 0.0753% for 2nd PF
  and 0.0169% for 4th(new_2).
- Exposed spatial fields (`chip_cells`, `physical_qubits`, `code_distance`) do
  not vary across regimes within a molecule/PF group.

### Interpretation

- The cheap magic assumptions affect scheduling/resource estimates, not logical
  magic demand.
- For larger H-chains under this fixed topology and factory-count setup, magic
  supply does not appear to be the dominant runtime bottleneck.
- Qubit-volume changes larger than runtime changes are not explained by the
  exposed spatial fields and likely require compile-info or mapping diagnostics
  to separate internal occupancy from scheduling effects.

### Unresolved

- Why qret qubit-volume percentages can exceed runtime percentages when exposed
  spatial fields are fixed.
- Whether left/right topology variants respond differently to cheap magic.
- How these diagnostics would change under a real STAR architecture model.

### Next Work

- If needed, run mapping/compile-info diagnostics for small and large H cases
  under p8 and p1.
- Repeat the same magic supply diagnostic for other topology placements only if
  topology/supply interaction becomes the focus.

### References

- `docs/benchmarks/surface_code_magic_supply_cheap_h2_h10_center.md`
- `artifacts/surface_code_magic_supply_cheap_h2_h10_center/results.csv`
- `artifacts/surface_code_magic_supply_cheap_h2_h10_center/results.jsonl`
- `artifacts/surface_code_magic_supply_cheap_h2_h10_center/results.md`
- `artifacts/surface_code_magic_supply_cheap_h2_h10_center/logs/run.log`

---

## 2026-07-08: architecture sensitivity の解釈更新と優先順位

### 目的

topology sweep、H4/H5 mapping-only diagnostic、H2-H10 cheap magic supply
diagnostic を踏まえて、今後の解析軸を明確にする。

### 研究方針の再確認

現在の主題は、PF=`2nd` と PF=`4th(new_2)` のどちらが小さいかを単純に
比較することではない。

PF は層別条件として扱い、主解析では同一 PF・同一 molecule・同一 logical
circuit を固定した上で、topology、factory placement、magic-state supply、
mapping geometry が resource metrics にどう効くかを見る。

特に重視する metric は次である。

- runtime
- qubit volume
- active area
- mapping / magic delivery geometry
- magic-state scheduling

### 解釈の更新

H2-H11 topology sweep では、factory placement の left/center/right 変更は
runtime にはほぼ現れなかった。一方で、qubit volume には一貫した ordering が出た。
`center_block` は qubit volume 最小、`left_edge` は最大になりやすい。

したがって、現時点では「runtime差が小さいので architecture 効果がない」とは
解釈しない。むしろ topology / factory placement の効果は、今回の条件では
時間資源よりも qubit volume、active area、mapping geometry 側に出ている可能性が高い。

H4/H5 mapping-only diagnostic では、`center_block` の qubit volume 最小が
`chip_cell_active_qubit_area_ave` の最小と対応していた。また、この条件では
`LATTICE_SURGERY_MAGIC` が全 case で magic factory symbol `0` のみを使っていた。

このため、factory 4個を置いた topology sweep は、少なくとも H4/H5 では
factory set 全体の比較ではなく、実効的には `m0` placement sweep として効いていた
可能性がある。これは今後の topology 設計と結果解釈を左右する重要な仮説である。

cheap magic supply diagnostic では、period を 15, 8, 4, 2, 1 まで下げても、
大きい H-chain の runtime 改善は小さかった。weighted `p15 -> p1` 改善は
PF=`2nd` で `0.0753%`、PF=`4th(new_2)` で `0.0169%` だった。
また、`cheap_p1_center` と `cheap_p1_large_stock_center` は全 molecule/PF group で
一致した。

この結果により、以前の「period 8 が弱すぎたため大きい H-chain で効果が見えない」
という解釈は弱くなった。少なくとも center topology、factory count 4、現行 qret
設定では、大きい H-chain の runtime 律速は magic generation period ではない可能性が高い。

### 方針決定

- PF 間比較を主題にしない。
- PF は architecture 効果を見るための層別条件として扱う。
- topology / factory placement / `m0` selection / active area / mapping diagnostics を優先する。
- cheap magic supply は diagnostic condition として扱う。
- `cheap_p1` や `cheap_p1_large_stock` を STAR architecture そのものの実装・評価と書かない。
- full QPE compile ではなく、`efficient_controlled_pf_one_step` からの QPE-scale 線形外挿であることを引き続き明記する。

### 次の優先作業

1. factory symbol / `m0` diagnostic

同じ factory 座標集合で symbol 順序だけを入れ替え、qret が symbol `0` を優先して
使っているのか、座標・距離・別の rule で factory を選んでいるのかを確認する。

2. 大きい H-chain の mapping-only diagnostic

H8/H10 または H8/H11 で、H4/H5 と同じ `m0` 使用・active area ordering が維持されるかを
確認する。H5 mapping-only diagnostic でも peak RSS が大きかったため、H8 以上では
memory を監視しながら小さく始める。

3. cheap magic と topology の相互作用確認

必要になった場合だけ、left/right topology で p8 と p1 を少数 case 比較する。
現時点では、factory symbol / `m0` diagnostic より優先度は低い。

### 優先度を下げる作業

`cheap_p1_center` と `cheap_p1_large_stock_center` が全条件で一致したため、
同じ条件で stock だけをさらに大きくする検証の優先度は低い。

cheap magic condition を全 topology に広げる作業も、topology/supply interaction を
主題にすると決めるまでは保留でよい。

### 未解決点

- H2-H11 全体で `m0` のみが使われるか。
- PF=`2nd` でも H4/H5 `4th(new_2)` と同じ mapping 構造が出るか。
- qret が magic factory symbol `0` を使う理由。
- factory symbol 順序を変えると qubit volume ordering が変わるか。
- 複数 factory を実効的に使わせる設定があるか。
- qubit volume 変化が runtime 変化より大きく出る case で、内部 occupancy がどう変わっているか。
- STAR-like cheap magic condition を quration/qret 上でどの程度表現できるか。
