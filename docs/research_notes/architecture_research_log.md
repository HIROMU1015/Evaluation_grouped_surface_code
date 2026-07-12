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

## 2026-07-08: factory symbol / m0 diagnostic

### Purpose

Test whether qret chooses magic factories by symbol number or by geometry for
`LATTICE_SURGERY_MAGIC`, using a fixed factory coordinate set and only changing
the symbol-to-coordinate assignment.

### Conditions

- Molecules: H4-H7.
- PF: `4th(new_2)`.
- Circuit scope: `efficient_controlled_pf_one_step`.
- Compile mode: `ftqc_compile_topology_qec`.
- Magic period: 15.
- Magic stock: fixed 10000.
- Topology variants: `m0_left`, `m0_center`, `m0_right`, `m0_far_corner`.
- Factory coordinate set fixed to `(0,0)`, `(4,4)`, `(9,0)`, `(9,9)`.
- H4/H5 were mandatory; H6/H7 were run after safety checks.
- H8 or larger was not executed.

This is not a full QPE compile. No QPE phase register, inverse QFT,
measurement, feed-forward, or repeated QPE circuit was generated.

### Observations

- All 16 executed cases succeeded.
- All `LATTICE_SURGERY_MAGIC` operations used magic factory symbol `0`.
- The used magic factory coordinate always followed the coordinate assigned to
  `m0`.
- Mean magic-delivery distance changed with the m0 coordinate.
- Active area and qubit volume were mostly invariant under symbol-only
  permutations; the far-corner m0 case caused only a small increase.
- Peak RSS by phase: H4/H5 `7,732,048 KB`, H6 `16,812,476 KB`, H7
  `32,465,496 KB`.
- Raw `mapping_state.json` files were not retained.

### Interpretation

- The result is consistent with qret selecting magic factory symbol `0`, rather
  than selecting the nearest available magic factory by geometry.
- Earlier topology-sweep resource differences cannot be attributed to symbol
  assignment alone, because this symbol-only permutation leaves active area and
  qubit volume nearly unchanged.
- The earlier differences likely involve the full factory coordinate set,
  layout occupancy, or other qret scheduling details.

### Unresolved

- The implementation reason for symbol-0 selection in quration/qret.
- Whether a qret setting exists to make multiple magic factories effective.
- Whether the same behavior holds for other PF labels or larger molecules.

### Next Work

- Audit quration/qret factory-selection logic for `LATTICE_SURGERY_MAGIC`.
- Test whether changing factory count or removing nonzero factories changes
  scheduling/resource metrics.
- If needed, construct a diagnostic where only `m0` exists at each candidate
  coordinate.

### References

- `docs/benchmarks/surface_code_factory_symbol_m0_diagnostic_h4_h7.md`
- `artifacts/surface_code_factory_symbol_m0_diagnostic_h4_h7/diagnostics.csv`
- `artifacts/surface_code_factory_symbol_m0_diagnostic_h4_h7/diagnostics.jsonl`
- `artifacts/surface_code_factory_symbol_m0_diagnostic_h4_h7/summary.md`
- `artifacts/surface_code_factory_symbol_m0_diagnostic_h4_h7/logs/h4_h5_run.log`
- `artifacts/surface_code_factory_symbol_m0_diagnostic_h4_h7/logs/h6_run.log`
- `artifacts/surface_code_factory_symbol_m0_diagnostic_h4_h7/logs/h7_run.log`

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

---

## 2026-07-08: qret factory selection audit and m0-only diagnostic

### 目的

直近の factory symbol / m0 diagnostic で、compact `mapping.json` 上の
`LATTICE_SURGERY_MAGIC` が全 case で magic factory symbol `0` を使っていた理由を、
quration/qret source と小規模 diagnostic で確認する。

### 条件

- Source audit は vendored `third_party/quration` を read-only で実施。
- quration/qret 実装変更なし。
- Optional diagnostic は H4/H5、PF=`4th(new_2)`、`efficient_controlled_pf_one_step` のみ。
- full QPE compile ではない。
- QPE phase register、inverse QFT、measurement、feed-forward、repeated QPE circuit は生成していない。
- H6 以上は今回実行していない。

### Source Audit の観測

- standard non-PBC lowering では、T/TDag が `LATTICE_SURGERY_MAGIC` に落ちるとき
  `MSymbol{0}` が初期値として入る。
- Evaluation の compact `mapping.json` は `init_compile_info -> mapping -> dump_compile_info`
  の mapping-only artifact であり、後続の `routing` pass を含まない。
- そのため、前回の `used factory symbol = 0` は pre-routing/lowering の観測であって、
  final routed factory usage の証拠ではない。
- qret routing 側には、同一 plane 上の全 available magic factory から BFS / Steiner search を行い、
  選ばれた factory symbol を `LATTICE_SURGERY_MAGIC` に書き戻す処理がある。
- CLI / machine option には topology、PBC mode、cultivation、global period、global stock はあるが、
  factory selection policy を明示的に切り替える option は見つからなかった。
- topology YAML は `magic_factory: [{symbol, coord}, ...]` で symbol と coordinate を直接表す。
  per-factory period / stock / capacity field は見つからなかった。

### Optional Diagnostic の観測

H4/H5 で、同じ m0 coordinate の `m0-only topology` と `4-factory topology` を比較した。

- success: 16
- failed: 0
- skipped: 0
- elapsed wall time: 4:04.20
- outer peak RSS: 7,731,864 KB
- swaps: 0

主な結果:

- H4 runtime: m0-only `2,769,017`、four-factory `814,084`。
- H5 runtime: m0-only `7,138,609`、four-factory `2,122,295`。
- H4 qubit volume: m0-only 約 `26.7M-28.3M`、four-factory 約 `9.26M`。
- H5 qubit volume: m0-only 約 `83.7M-87.1M`、four-factory 約 `28.18M`。
- compact mapping artifact は m0-only / four-factory の両方で symbol `0` を報告する。

### 解釈

`LATTICE_SURGERY_MAGIC` が source 上「常に symbol 0 を使う」とは言えない。
正確には、standard lowering は symbol 0 を初期値にするが、routing は複数 factory から
経路探索して factory symbol を更新できる。

したがって、前回の m0 diagnostic は pre-routing mapping の観測としては正しいが、
final routed execution が非0 factory を使わない証拠ではない。

H4/H5 の m0-only vs four-factory では、four-factory が runtime と qubit volume を大きく下げた。
これは、pre-routing artifact が symbol 0 だけを示していても、非0 factory が routed resource に
実効的に効いていることを示す。

### 未解決点

- final routed factory usage を compact に抽出する Evaluation 側 artifact はまだない。
- 同じ効果が PF=`2nd` や H6 以上でも同程度かは未確認。
- four-factory 内での coordinate set / layout / scheduling 効果を、factory count 効果から分離する必要がある。

### 次の作業

- H4/H5 に限定して、final routed instruction から factory usage を compact 抽出する方法を検討する。
- 今後の topology sweep は、factory count と magic supply を固定したうえで coordinate/layout 効果を見る。
- PF=`2nd` でも小規模に同じ source/dynamic 解釈が成り立つか確認する。

### 参照

- `docs/benchmarks/qret_magic_factory_selection_audit.md`
- `artifacts/surface_code_factory_count_m0_only_vs_four_h4_h5/summary.md`
- `artifacts/surface_code_factory_count_m0_only_vs_four_h4_h5/diagnostics.csv`
- `artifacts/surface_code_factory_count_m0_only_vs_four_h4_h5/diagnostics.jsonl`
- `artifacts/surface_code_factory_count_m0_only_vs_four_h4_h5/logs/run.log`

---

## 2026-07-08: post-routing magic factory usage diagnostic

### 目的

Evaluation の compact `mapping.json` は pre-routing / lowering 段階の情報であり、
final routed `LATTICE_SURGERY_MAGIC` の factory usage を示さない。H4/H5 の小規模
case に限定し、qret の post-routing pipeline-state から final factory symbol / coordinate
usage を compact に抽出した。

### 条件

- H4/H5 only。
- PF=`4th(new_2)` only。
- circuit_scope=`efficient_controlled_pf_one_step` only。
- compile_mode=`ftqc_compile_topology_qec`。
- magic_generation_period=15、stock fixed 10000。
- four-factory topology variants のみ。
- full QPE compile ではない。
- QPE phase register、inverse QFT、measurement、feed-forward、repeated QPE circuit は生成していない。
- H6 以上は実行していない。
- quration/qret 実装変更なし。

### Schema Probe

H4 `four_factory_m0_center` で `skip_compile_output=false` を使い、
qret の `step_sc_ls_fixed_v0.json` を確認した。

- final routed instructions は `program[*]` にある。
- magic instruction は `type: LATTICE_SURGERY_MAGIC` を持つ。
- final routed factory symbol は `mtarget` に入る。
- H4 probe では `mtarget` が全 magic instruction にあり、confidence は high。

### 観測

H4/H5 x 4 topology の 8 case はすべて成功した。missing factory symbol count は全 case で 0。

H4:

- magic ops: 184600 / case。
- coordinate counts は全 symbol permutation で
  `(0,0):21789`, `(4,4):54270`, `(9,0):54271`, `(9,9):54270`。
- symbol counts は coordinate に割り当てた symbol に応じて入れ替わる。

H5:

- magic ops: 475906 / case。
- coordinate counts は全 symbol permutation で
  `(0,0):51466`, `(4,4):141485`, `(9,0):141471`, `(9,9):141484`。
- symbol counts は coordinate に割り当てた symbol に応じて入れ替わる。

### 解釈

post-routing では symbols 0, 1, 2, 3 がすべて使われている。したがって、
以前の compact `mapping.json` 上の symbol 0 only は pre-routing artifact の観測であり、
final routed execution が symbol 0 だけを使うという意味ではない。

m0-only vs four-factory の runtime / qubit-volume gap は、非0 factory が実際に
final routed instruction に使われていることと整合する。少なくとも H4/H5、
PF=`4th(new_2)`、`efficient_controlled_pf_one_step` では、four-factory resource row は
実効的な multi-factory routed usage を含む。

### 未解決点

- H6 以上や他 PF label で同じ分布になるかは未確認。
- route distance、queue ordering、stock tie-break の詳細は今回の compact artifact からは読めない。
- production sweep で post-routing factory usage を常時保存する場合の最小 artifact schema は
  まだ実装していない。

### 次の作業

- future architecture sweep に compact post-routing factory usage artifact を追加するか検討する。
- topology / factory placement 解析では、symbol counts より coordinate counts を主指標にする。
- 必要なら route distance / stock state まで踏み込む diagnostic を別途設計する。

### Artifacts

- `docs/benchmarks/post_routing_magic_factory_usage_h4_h5.md`
- `artifacts/post_routing_magic_factory_usage_h4_h5/post_routing_factory_usage.csv`
- `artifacts/post_routing_magic_factory_usage_h4_h5/post_routing_factory_usage.jsonl`
- `artifacts/post_routing_magic_factory_usage_h4_h5/summary.md`
- `artifacts/post_routing_magic_factory_usage_h4_h5/logs/run.log`
- raw_tmp は compact extraction 後に削除済み。

---

## 2026-07-11: cheap RZ synthesis surrogate の研究上の位置付け

### 背景と目的

現在の surface-code resource evaluation では、任意角 RZ を Clifford+T 命令列へ
近似分解する。この合成に由来する T / T-dagger、magic-state 消費と depth、
magic-state の供給・配送・待機、および合成後の命令列が、runtime や qubit volume を
大きく支配する可能性がある。

この共通コストが支配的な場合、topology、factory placement、logical-qubit placement、
mapping、routing、communication などの architecture 条件を変えても、その差が total
resource に表れにくい可能性がある。そのため、RZ synthesis cost を意図的に小さくした
条件を設け、non-Clifford cost の背後にある architecture-side bottleneck を観測しやすく
する。

RZ を安くすること自体が最終目的ではない。non-Clifford synthesis cost が支配的で
なくなった場合に、何が runtime、qubit volume、空間資源を決めるかを調べるための
diagnostic condition である。

模式的には次のように捉える。

```text
C_total ~= C_RZ_synthesis + C_architecture + C_interaction
```

ただし、これは厳密な加算分解ではない。runtime は critical path、qubit volume は
時間・配置・routing・QEC の相互作用を含むため、`C_interaction` を無視できない。

### rotation_precision の扱い

qret の `rotation_precision` は、実装上は任意角回転の近似合成精度を指定する
パラメータである。本 diagnostic では、その近似誤差を目標エネルギー誤差へ伝播させず、
RZ synthesis の実効コストを変える形式的な surrogate parameter として用いる。

precision を粗くしたことによる回転合成誤差は、現在の理想化した architecture
sensitivity 評価では目標エネルギー誤差へ寄与しないと仮定する。これは誤差が物理的に
ゼロであることを検証した結果ではない。また、product-formula approximation error、
QPE error、QEC failure model など、既存の誤差要因までゼロとする仮定ではない。

precision regime 間で固定する高水準の回路条件は次である。

- Hamiltonian
- grouping
- PF order / coefficient
- step time
- circuit scope
- 任意角 RZ を含む pre-synthesis logical circuit

一方、`rotation_precision` を変えると、合成後の Clifford+T 命令列、magic count / depth、
optimized IR hash は変わる。したがって、precision regime 間で「合成後も同一 logical
circuit」とは表現しない。

architecture sensitivity を比較するときは、各 precision regime 内で molecule、
Hamiltonian、grouping、PF、step time、circuit scope、`rotation_precision` を固定し、
architecture 条件だけを変える。

### cheap RZ で安くする範囲

cheap RZ synthesis condition では、従来の Clifford+T による RZ 近似合成に由来する
次の要素がまとめて小さくなり得るものとして扱う。

- T / T-dagger 数
- magic-state count
- magic-state depth
- magic-state の供給・配送要求
- RZ 近似合成内部の Clifford 命令
- 合成後の総命令数
- それらに起因する runtime、routing traffic、qubit volume

これは「T gate 1個の単価だけを下げるモデル」ではなく、「従来の Clifford+T による
RZ 近似合成全体を安くするモデル」である。RZ 合成内部の Clifford も減少し得ることを
current working assumption として許容する。ただし、既存の rotation precision sweep
では総 Clifford 命令数を独立 metric として集計していないため、その減少自体を
observed result とは扱わない。

### 維持する Clifford skeleton と architecture 処理

次の要素は RZ 近似合成の外側にあり、cheap RZ condition でも維持する。

- Pauli basis change
- parity compute / uncompute
- grouped evolution の基底変換
- system qubit 間の Clifford interaction
- control qubit と system qubit の interaction
- mapping と routing
- logical-cell occupation と routing congestion
- architecture 上必要な communication

したがって、回路全体を無料化または削除するモデルではない。RZ synthesis という
大きな共通コストを弱めた後も、外側の Clifford skeleton と architecture-dependent
processing は残す。

### magic supply diagnostic との区別

これまでの `magic_generation_period` sweep と cheap RZ synthesis surrogate は異なる
介入である。

```text
magic_generation_period change:
  magic-state の供給速度を変える
  合成後の magic demand / count / depth は基本的に変えない

rotation_precision change:
  RZ synthesis の需要と命令列を変える
  magic count / depth と合成内部 Clifford が変わり得る
```

period を 15 から 1 まで短くしても大規模 H-chain の runtime 改善が小さかった結果は、
現行条件で magic-state supply wait が主律速ではない可能性を示す。一方、それだけでは
RZ synthesis demand や合成命令列そのものが支配的でないとは結論できない。

### STAR との関係

STAR のように、将来の partially fault-tolerant architecture で non-Clifford operation
や任意角回転のコストが低下する可能性を研究動機としている。ただし、現在のモデルは
STAR architecture の実装でも STAR resource estimate でもない。

現在の quration / qret evaluation では、STAR 固有の次の要素をモデル化しない。

- analog rotation resource-state generation
- state injection と joint measurement
- repeat-until-success と feed-forward / correction
- angle-dependent success probability / fidelity
- STAR 固有の factory layout と rotation-state delivery
- STAR 固有 primitive の residual space-time cost

したがって、表現には `cheap RZ synthesis surrogate`、`low-non-Clifford-cost regime`、
または「任意角回転合成が安価になった理想化条件」を用いる。「STAR を実装した」または
「STAR の resource を測定した」とは書かない。

### 最低コストと limitations

各 RZ または RZ layer に対する非ゼロの residual execution time / qubit volume を加える
補正は、現段階では導入しない。STAR 固有 primitive に対応する最低 space-time cost も
追加しない。

この判断は unresolved implementation task ではなく、現在の diagnostic scope で意図的に
採用しないモデル範囲である。cheap RZ condition は特定の現実 architecture を定量再現する
ものではなく、RZ synthesis cost を段階的に弱める理想化された感度分析条件として扱う。
既存 sweep の最も粗い `rotation_precision=1e-3` でも RZ cost がゼロになったわけではない。

状態は次のように分類する。

- rotation precision sweep: implemented / observed one-step compile-profile result
- cheap RZ interpretation: current working assumption / diagnostic evaluation policy
- STAR-specific primitive model: unimplemented / out of current scope
- nonzero minimum RZ cost: not adopted at this stage
- STAR resource estimate: not performed

### 実装済み検証と未検証の問い

H2-H7、PF=`4th(new_2)`、scope=`efficient_controlled_pf_one_step`、
topology=`factory_center_block`、`magic_generation_period=15` の固定条件で、
`rotation_precision=1e-5, 3e-5, 1e-4, 3e-4, 1e-3` の sweep は実装・実行済みである。
30 case はすべて成功した。

この sweep で observed なのは、precision を粗くすると magic count / depth、runtime、
qubit volume が低下したことである。H7 の `1e-3` では code distance と physical qubits の
離散的変化も混ざる。結果は observed one-step compile/profile result と、その線形外挿で
ある QPE-scale estimate を区別する。full QPE compile result ではない。

一方、この既存 sweep は topology を `factory_center_block` に固定しているため、cheap RZ
condition で architecture case 間の spread がどう変化するかは未測定である。今後の主な
研究上の問いは次である。

> RZ synthesis と magic-state 関連コストが支配的でなくなったとき、topology、factory
> placement、logical-qubit placement、mapping、routing、communication が runtime と
> qubit volume にどの程度影響するか。

conventional RZ synthesis condition と cheap RZ synthesis condition を分け、各 regime
内では同じ合成条件と pre-synthesis logical circuit を使って architecture 条件だけを
変更する。主に確認する metric は次である。

- runtime と qubit volume
- magic-state count / depth
- chip cells、physical qubits、code distance
- routing-related metrics
- logical-cell usage / active area
- architecture case 間の spread と case ordering

cheap RZ condition で architecture spread が拡大した場合は、従来条件で RZ/T synthesis
cost に隠れていた architecture bottleneck が顕在化した可能性を検討する。spread が
小さいままなら、現在変更している architecture 条件は、その回路と規模では主要因でない
可能性を検討する。case ordering が変わる場合は、non-Clifford cost regime によって
有利な architecture が変わる可能性を検討する。

これらは今後の仮説と解釈方針であり、まだ observed result とは扱わない。

### 参照

- `configs/surface_code_rotation_precision_sweep_h2_h7_4th_center.yaml`
- `artifacts/surface_code_rotation_precision_sweep_h2_h7_4th_center/results.md`
- `artifacts/surface_code_rotation_precision_sweep_h2_h7_4th_center/results.csv`
- `artifacts/surface_code_rotation_precision_sweep_h2_h7_4th_center/results.jsonl`
- `docs/research_notes/qpe_scope_and_semantics.md`
- `docs/research_notes/surface_code_architecture_sensitivity_note.md`

---

## 2026-07-11: cheap RZ 条件での factory-placement sensitivity

### 目的

直前に定義した cheap RZ synthesis surrogate を用い、RZ synthesis cost を下げたときに
factory placement による architecture spread が拡大するかを検証した。

当初の仮説は、共通の RZ/T synthesis cost を弱めることで、その背後にある architecture
差が観測しやすくなる可能性がある、というものだった。今回の検証では architecture 変数を
factory placement に限定し、この仮説が成立するかを調べた。

### 条件

- molecules: H4-H7
- PF: `4th(new_2)`
- circuit scope: `efficient_controlled_pf_one_step`
- rotation precision: `1e-5`, `1e-3`, `3e-3`, `1e-2`
- topology: `factory_left_edge`, `factory_center_block`, `factory_right_edge`
- grid: 10x10
- factory count: 4
- magic generation period: 15
- fixed magic stock: 10000
- compile mode: `ftqc_compile_topology_qec`
- rows: 48

全 48 case が成功し、failed / skipped は 0 だった。実行 wall time は 13分08秒、外側で
観測した peak RSS は約 2.90 GiB で、実行中に swap 使用量は増加しなかった。

この結果は observed one-step compile/profile result と、その線形外挿である QPE-scale
estimate を含む。full QPE circuit の compile result ではない。

### Resource reduction の観測

`factory_center_block` で `rotation_precision=1e-5` から `1e-2` へ粗くしたときの
single-step resource reduction は次の通りだった。

| molecule | magic count | magic depth | runtime | qubit volume |
| --- | ---: | ---: | ---: | ---: |
| H4 | -93.65% | -94.14% | -82.02% | -80.09% |
| H5 | -96.02% | -96.17% | -82.93% | -80.60% |
| H6 | -98.31% | -98.42% | -84.42% | -82.16% |
| H7 | -98.83% | -98.88% | -84.39% | -82.08% |

したがって、`1e-2` は magic demand を約94-99%減らす極端な low-non-Clifford-cost
diagnostic として機能した。ただし、これは実際の回転近似誤差を目標エネルギー誤差へ
伝播させた結果ではなく、現実の回転精度または STAR 固有 primitive cost を表さない。

### Topology spread の観測

各 molecule / precision 内で、次の定義を用いた。

```text
spread = (maximum - minimum) / minimum
```

qubit-volume topology spread は、sampled precision を粗くするにつれて全分子で単調に
縮小した。

| molecule | `1e-5` | `1e-3` | `3e-3` | `1e-2` |
| --- | ---: | ---: | ---: | ---: |
| H4 | 12.821% | 11.344% | 10.421% | 4.152% |
| H5 | 9.072% | 7.100% | 5.332% | 1.808% |
| H6 | 7.847% | 6.264% | 4.436% | 0.189% |
| H7 | 6.740% | 4.930% | 2.443% | 1.038% |

runtime spread は全条件で 0.033% 未満であり、引き続き非常に小さかった。したがって、
factory placement は baseline でも主に runtime critical path ではなく、qubit volume / active
area / delivery geometry 側へ影響する architecture 変数だったと考えられる。

### 解釈と仮説更新

今回の factory-placement sweep では、cheap RZ によって architecture spread が拡大する
という当初仮説は支持されなかった。反対に、RZ synthesis demand を減らすほど factory
placement sensitivity は弱くなった。

この結果は、既存の factory-placement差のかなりの部分が magic-state delivery geometry
に由来する、という解釈と整合する。

```text
RZ synthesis demand decreases
  -> magic-state demand and delivery traffic decrease
  -> factory access and magic-routing occupancy decrease
  -> factory-placement sensitivity decreases
```

ただし、今回直接観測したのは magic count / depth、runtime、qubit volume と topology
spread である。factory access frequency、route length、routing cell occupancy は今回の
sweep では直接集計していない。そのため、magic delivery が主因であることは、今回の
spread 縮小と過去の mapping / post-routing diagnostic を合わせた inferred explanation と
して扱う。

更新後の仮説は次である。

> cheap RZ によってすべての architecture 差が一律に顕在化するわけではない。
> architecture sensitivity の変化は、その architecture 変数が削減対象の non-Clifford
> demand に依存するか、cheap RZ 後も残る Clifford skeleton に作用するかで異なる。

factory placement のように magic delivery へ直接結び付く要因は、magic demand の減少と
ともに影響も縮小する。一方、logical-qubit placement、parity network、data-qubit routing、
mapping policy、grid geometry など、残存する Clifford skeleton に直接作用する要因の感度は
今回の結果からは分からない。

### Code-distance threshold の注意

precision 間の qubit-volume reduction には QEC の離散変化が混ざる。

- H4 `1e-5`: left のみ distance 15、center / right は 13。`1e-3` 以降はすべて 13。
- H5: `1e-5` から `3e-3` は distance 15、`1e-2` はすべて 13。
- H6: 全条件で distance 15。
- H7: `1e-5` は distance 17、`1e-3` 以降は distance 15。

したがって、`1e-5 -> 1e-2` の絶対的な qubit-volume reduction を、RZ synthesis短縮または
magic削減だけへ帰属してはならない。synthesis、routing / occupancy、code distance とその
相互作用が含まれる。

一方、各 precision 内の topology spread は、H4 `1e-5` を除けば code distance / physical
qubits が3 topologyで共通である。このため、factory-placement sensitivity を見る比較として
precision間の絶対値比較より解釈しやすい。

### Topology ordering

`rotation_precision=1e-2` では qubit-volume minimum topology が次のように変化した。

- H4: right
- H5: left
- H6: center
- H7: left

ただし、`1e-2` での spread は H4を除き約2%以下まで縮小している。したがって、cheap RZ
によって別topologyが本質的に優位になったとはまだ言えない。現時点では weak rank change /
unresolved とし、残った Clifford routing / occupancy差を直接計測するまで強い順位主張を
行わない。

### 状態分類

| 内容 | 分類 |
| --- | --- |
| H4-H7 precision x topology sweep | observed |
| cheap RZでmagic count / depthが大幅減少 | observed |
| cheap RZでruntime / qubit volumeが大幅減少 | observed |
| sampled precisionでQV topology spreadが単調縮小 | observed |
| factory placement感度がmagic delivery需要に由来する | inferred |
| cheap RZでfactory-placement差が拡大する仮説 | evaluated and rejected |
| topology順位の本質的逆転 | unresolved |
| QV低下におけるcode-distance寄与の分離 | unresolved |
| data / logical-qubit placement sensitivity | unevaluated |
| mapping / routing algorithm sensitivity | qret feature exists; Evaluation sweep unevaluated |

### 次の作業

cheap RZ 後に残る architecture bottleneck を調べるため、主眼を factory-side architecture
から data-side / Clifford-side architecture へ移す。

優先候補は次である。

1. logical-qubit initial placement / mapping policy
2. system-control qubit distance と parity-network communication
3. logical-cell grid size / aspect ratio
4. Clifford routing congestion と active-area metric
5. factory count と data-cell budget の trade-off

最初の matched sweep では、conventional `rotation_precision=1e-5` と extreme diagnostic
`1e-2` を分け、各 precision 内で同じ pre-synthesis logical circuit と synthesis condition を
固定した上で mapping / logical-qubit placement だけを変更する。

### 参照

- `configs/surface_code_rotation_precision_topology_sweep_h4_h7_4th.yaml`
- `artifacts/surface_code_rotation_precision_topology_sweep_h4_h7_4th/summary.md`
- `artifacts/surface_code_rotation_precision_topology_sweep_h4_h7_4th/results.md`
- `artifacts/surface_code_rotation_precision_topology_sweep_h4_h7_4th/results.csv`
- `artifacts/surface_code_rotation_precision_topology_sweep_h4_h7_4th/results.jsonl`

## 2026-07-11: auto baseline + explicit logical-placement sweep

### Question

cheap RZ 条件で factory-placement sensitivity が弱くなった後も、logical-qubit initial
placement と data-side / Clifford-side routing は qubit volume へ影響するかを調べた。

H4-H7、`4th(new_2)`、`rotation_precision=1e-5, 1e-2` について、center-block factory と
10 x 10 grid を固定し、次の4条件を比較した。

- qret `auto_greedy_soft` baseline
- compact cellsへのnumeric-order explicit assignment
- 同じcompact cellsへのinteraction-aware explicit assignment
- perimeterへのnumeric-order explicit assignment stress case

これは4種類のmapping algorithm比較ではない。qretのMETIS partitionは現実装で
`Partition by METIS is not implemented.` を送出するため対象外とし、auto mapping baselineと
explicit logical-placement diagnosticを比較した。

### Observed results

32 caseはすべて成功した。各 molecule / precision 内で、code distance、physical qubits、
chip cells は4配置で共通だった。

| molecule | precision | runtime spread | QV spread | QV minimum | QV maximum |
| --- | ---: | ---: | ---: | --- | --- |
| H4 | `1e-5` | 0.00160% | 10.938% | interaction-aware | perimeter |
| H4 | `1e-2` | 0.03278% | 8.983% | interaction-aware | perimeter |
| H5 | `1e-5` | 0.00165% | 8.233% | interaction-aware | perimeter |
| H5 | `1e-2` | 0.00883% | 7.793% | interaction-aware | perimeter |
| H6 | `1e-5` | 0.00223% | 6.431% | interaction-aware | perimeter |
| H6 | `1e-2` | 0.01375% | 7.087% | interaction-aware | perimeter |
| H7 | `1e-5` | 0.00735% | 5.357% | interaction-aware | perimeter |
| H7 | `1e-2` | 0.06101% | 5.901% | interaction-aware | perimeter |

同一cell集合を使うcompact numericとinteraction-awareの比較では、pre-synthesis QASMから
計算したweighted CNOT Manhattan objectiveが約16.8-18.4%減少し、compiled qubit volumeは
全8 groupで1.2-2.2%減少した。runtimeはほぼ不変だった。

auto baselineはinteraction-aware explicit placementより全8 groupでqubit volumeが高く、差は
3.5-6.6%だった。perimeter stress caseは全8 groupで最大qubit volumeとなった。

### Interpretation

logical-qubit placement sensitivityはcheap RZ後にも残り、`1e-2`で5.90-8.98%のQV spreadが
観測された。一方、factory-placement sweepの`1e-2` spreadは0.19-4.15%まで縮小していた。
この差は、magic需要の削減後もdata-side / Clifford-side placementとroutingがspace-time
resourceへ作用する、という解釈を支持する。

ただし、cheap RZによってplacement sensitivityが一律に拡大したわけではない。H4/H5では
spreadが縮小し、H6/H7では小幅に拡大した。したがって、残存architecture sensitivityは
molecule interaction graph、routing余裕、congestionの相互作用に依存すると考える。

runtime spreadが最大0.061%なのに対しQV spreadは数%残り、QVの順位とaverage active areaの
順位は一致した。このため、今回のplacement差はcritical-path beat数ではなく、主として
occupied cell-time / active-area側へ現れたと判断する。

compact numeric対interaction-awareは同じcell集合なのでlogical-ID assignmentの比較として
解釈しやすい。一方、perimeter caseは配置形状とfactory距離を同時に変えるため、Clifford
routingとmagic deliveryの寄与を分離した比較ではない。

### State classification

| item | classification |
| --- | --- |
| H4-H7 placement x precision sweep | observed |
| cheap RZ後も5.90-8.98%のQV placement spreadが残る | observed |
| interaction-aware assignmentが全groupでQV最小 | observed |
| placement差が主にactive-area / occupied cell-timeへ現れる | observed結果に基づくinference |
| auto mappingが最適でない | evaluated for this fixed grid/circuit set |
| cheap RZでplacement感度が一律に拡大する | evaluated and rejected |
| perimeter差におけるClifford routingとmagic deliveryの寄与分離 | unresolved |
| grid capacity / aspect ratioとplacement感度の関係 | unevaluated |

### References

- `configs/surface_code_logical_placement_sweep_h4_h7_4th.yaml`
- `configs/topologies/logical_placement_h4_h7/placement_manifest.json`
- `artifacts/surface_code_logical_placement_sweep_h4_h7_4th/summary.md`
- `artifacts/surface_code_logical_placement_sweep_h4_h7_4th/results.csv`
- `artifacts/surface_code_logical_placement_sweep_h4_h7_4th/results.jsonl`

## 2026-07-12: logical-cell grid capacity sweep

### Question

logical-placement sweepで残ったQV差が、routing容量不足、通信距離、またはmapping policyの
どれに由来するかを調べるため、H4-H7、`4th(new_2)`、`rotation_precision=1e-5, 1e-2`で
8x8、10x10、12x12 gridを比較した。各gridでcenter-block factoryを4個に固定し、qret
`auto_greedy_soft`とexplicit interaction-aware placementを使った。48 case中44 caseが成功し、
4 caseがmapping failureとなった。

### Auto-mapping capacity boundary

8x8 center-factory topologyではsoft candidateが12 cellである。H4は9 logical qubits、H5は11
なのでauto mappingに成功したが、H6の13とH7の15はconventional/cheap RZの両方で
`Failed to find partition` / `Failed to find place to map qubits`となった。

同じ8x8でexplicit H6/H7は成功した。したがって、この失敗は単純なcell総数不足ではなく、
auto-soft candidate generation / mapping policyの容量限界である。explicit側はsoft候補外の
non-factory cellをH6で1個、H7で3個補完し、この介入をmanifestへ記録した。

### Explicit placement results

interaction-aware 10x10を基準にしたgrid変更は次のとおりだった。

| molecule | precision | 8x8 runtime | 8x8 QV | 12x12 runtime | 12x12 QV |
| --- | ---: | ---: | ---: | ---: | ---: |
| H4 | `1e-5` | +0.000% | +0.645% | +0.000% | +0.646% |
| H4 | `1e-2` | +0.000% | +0.794% | +0.000% | +0.796% |
| H5 | `1e-5` | +0.000% | +0.342% | +0.000% | +0.342% |
| H5 | `1e-2` | +0.000% | +0.754% | +0.000% | +0.745% |
| H6 | `1e-5` | +0.000% | +1.593% | -0.000% | +0.350% |
| H6 | `1e-2` | +0.005% | -0.024% | +0.000% | +0.602% |
| H7 | `1e-5` | +11.122% | +14.057% | -0.008% | +0.929% |
| H7 | `1e-2` | +0.197% | +1.648% | -0.061% | +0.304% |

H4-H6はexplicit policyではgrid capacity感度が弱く、runtimeはほぼ不変、QV差は約1.6%以内
だった。一方、H7 conventionalの8x8は明確なcapacity/congestion boundaryを示した。
topology-free runtimeからの増分は10x10の838 beatに対し8x8で987,508 beatとなり、QVは
14.06%増加した。

H7 cheap RZでは同じ8x8 penaltyがruntime +0.20%、QV +1.65%まで縮小した。8x8 explicitの
pre-synthesis weighted CNOT distanceは10x10より小さいため、静的なpair distanceだけでは
conventional条件の悪化を説明できない。大きなRZ synthesis / magic workloadと狭いgridの
routing congestion / cell occupancyが相互作用したという説明と整合するが、direct congestion
counterは未取得なのでinferenceとして扱う。

### Automatic placement on a larger grid

auto mappingでは12x12のQVが10x10より全成功groupで1.34-5.87%増加した。mapping_resultから、
12x12ではCNOT平均距離、nearest-factory平均距離、magic-operation平均距離がすべて10x10より
増えていることを確認した。追加cellをrouting slackとして使うのではなく、初期配置自体が
広がったためである。

このため、autoとinteraction-awareのQV差は概ねgridとともに拡大し、12x12ではconventional
で4.43-9.20%、cheap RZで6.59-8.86%となった。大きいgridはmapping objectiveが通信距離を
抑えない限り、自動的にresourceを改善しない。

### Static footprint distinction

non-factory chip cellsは8x8で60、10x10で96、12x12で140である。code distanceが同じなら
physical qubitsもこの比率で増える。10x10から12x12への変更はstatic physical-qubit footprintを
45.8%増やすが、explicit runtime/QVの改善は観測されなかった。active-area ratio低下は主に
grid denominator増加によるため、absolute active areaと区別する。

各molecule/precision内では成功grid間のcode distanceは共通だった。したがってgrid差にQEC
threshold crossingは混ざっていない。

### Updated conclusion

今回の範囲では10x10が最もrobustなgridだった。8x8はH4/H5には十分だが、auto mapperは
H6/H7で候補上限に達し、explicit H7 conventionalでもrouting-capacity penaltyが現れた。
12x12はstatic footprintを増やし、auto mappingでは距離とQVも増やした。

cheap RZはgrid sensitivityを一律に顕在化せず、H7 8x8 congestion penaltyを大幅に弱めた。
architecture sensitivityはcell数だけでなく、そのcell上を通るRZ synthesis / magic routing
workloadとの相互作用で決まる。

### State classification

| item | classification |
| --- | --- |
| H4-H7 grid x precision x placement sweep | observed |
| 8x8 autoがH6/H7でmapping failure | observed |
| explicit H6/H7が8x8でmapping success | observed |
| H7 conventional 8x8でruntime/QV penalty | observed |
| cheap RZでH7 8x8 penaltyが縮小 | observed |
| H7 penaltyの主因がrouting congestion / occupancy | inferred |
| 12x12 autoで距離とQVが増加 | observed |
| 10x10が今回のtested setで最もrobust | evaluated for tested policies |
| fixed-area aspect-ratio sensitivity | unevaluated |

### References

- `configs/surface_code_grid_capacity_sweep_h4_h7_4th.yaml`
- `configs/topologies/logical_grid_capacity_h4_h7/grid_capacity_manifest.json`
- `artifacts/surface_code_grid_capacity_sweep_h4_h7_4th/summary.md`
- `artifacts/surface_code_grid_capacity_sweep_h4_h7_4th/results.csv`
- `artifacts/surface_code_grid_capacity_sweep_h4_h7_4th/results.jsonl`

## 2026-07-12: fixed-circuit runtime grid threshold

### Question

回路合成条件を変えず、architecture条件だけでruntimeが大きく変化するcaseがあるかを調べた。
H5をcontrol、H7をtargetとし、`4th(new_2)`、`rotation_precision=1e-5`、explicit
interaction-aware placementを固定して、8x8、8x10、9x9、10x8、10x10、10x12、12x10を
比較した。

各molecule内でQASM hash、optimized IR hash、RZ count/depth、magic count/depth、
topology-free runtime、code distanceが全gridで一致することを確認した。したがって以下の
runtime差はrotation precisionやT gate数変更によるものではない。

### Observed runtime

14 caseはすべて成功した。H5の最大runtime差は10x10比0.016%で、実質的に不変だった。

H7では8x8だけが明確な外れ値となった。

| grid | runtime | vs 10x10 | topology overhead |
| --- | ---: | ---: | ---: |
| 8x8 | 9,858,370 | +11.121544% | 987,508 |
| 8x10 | 8,871,631 | -0.000778% | 769 |
| 9x9 | 8,871,647 | -0.000597% | 785 |
| 10x8 | 8,871,614 | -0.000969% | 752 |
| 10x10 | 8,871,700 | reference | 838 |
| 10x12 | 8,871,167 | -0.006008% | 305 |
| 12x10 | 8,871,184 | -0.005816% | 322 |

8x8を除くH7のruntime spreadは約0.006%である。grid面積やaspect ratioに対してruntimeが
連続的に変化したのではなく、8x8でのみcritical-path penaltyが現れた。

### Interpretation

8x8のsoft placement candidateは12 cellで、15 logical qubitsを持つH7 explicit placementは
3個のnon-soft cell補完を必要とする。8x10、9x9、10x8では補完が不要になり、runtimeは直ちに
通常値へ戻った。

H7 8x8のpre-synthesis weighted CNOT distanceは1,032,100で、10x10の1,182,008より小さい。
したがって11.12%のruntime penaltyは静的なpair distance増加では説明できない。center factory
周辺へlogical qubitを詰めたことでrouting slackが不足し、occupied-cell congestionがcritical
pathへ入ったという説明と整合する。ただしdirect routing-wait / congestion counterは未取得の
ため、機構はinferredとする。

H7 8x8のQVは10x10比14.057%増加した。runtime +11.122%とaverage active area +2.642%が
同時に寄与している。他のH7 gridではruntimeが不変で、QV差は-0.255%から+1.220%だったため、
主にactive-area差である。

### Updated direction

固定回路に対する大きなarchitecture runtime effectは存在する。ただし、通常配置で広く現れる
効果ではなく、routing容量が閾値を下回ったときに急にcritical pathへ現れるthreshold effectで
ある。

次はgrid sweepを広げるより、H7 8x8と8x10または10x10について、routing wait、route retry、
operation別path length、同時cell occupancyを直接取得し、congestion inferenceをobservedへ
変えることを優先する。

### State classification

| item | classification |
| --- | --- |
| H5/H7 fixed-circuit grid sweep | observed |
| H7 8x8 runtime +11.12% | observed |
| 8x10 / 9x9 / 10x8でpenalty解消 | observed |
| H5がruntime-insensitive control | observed |
| H7 8x8 penaltyがrouting congestionに由来する | inferred |
| direct routing-wait / congestion breakdown | unresolved |

### References

- `configs/surface_code_runtime_grid_threshold_h5_h7_4th.yaml`
- `configs/topologies/runtime_grid_threshold_h5_h7/runtime_grid_threshold_manifest.json`
- `artifacts/surface_code_runtime_grid_threshold_h5_h7_4th/summary.md`
- `artifacts/surface_code_runtime_grid_threshold_h5_h7_4th/results.csv`
- `artifacts/surface_code_runtime_grid_threshold_h5_h7_4th/results.jsonl`

## 2026-07-12: H7 8x8 routing diagnostic

### Question

fixed-circuit runtime grid sweepで観測したH7 8x8の`+11.121544%` penaltyが、どのoperationの
routing挙動と対応するかを調べた。H5 8x8をcontrolとし、H7 8x8、8x10、10x10を同じ
optimized IRから再compileした。qretへaggregate diagnosticをローカルに追加し、operation別の
`ScLsSimulator::Run` attempt / rejectionと、routing後ancilla path長を取得した。

診断有効時のruntime、topology-free runtime、gate count/depth、magic count/depth、QV、
code distance、physical qubitsが既存compile_infoと一致することを全4 caseで確認した。

### Observed results

| case | runtime | topology overhead | magic rejection rate | magic mean path | CNOT rejection rate | CNOT mean path |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| H5 8x8 | 2,122,291 | 26 | 52.634% | 2.281 | 68.681% | 5.117 |
| H7 8x8 | 9,858,370 | 987,508 | 66.860% | 5.258 | 70.001% | 5.674 |
| H7 8x10 | 8,871,631 | 769 | 52.488% | 2.052 | 70.241% | 5.255 |
| H7 10x10 | 8,871,700 | 838 | 52.482% | 2.265 | 70.283% | 5.086 |

H7のtopology-free runtimeは全条件で8,870,862 beatだった。8x8と10x10の総runtime差
986,670 beatは、topology overhead差986,670 beatと完全に一致する。

H7 8x8では10x10に対してmagic path平均が132.1%増え、rejected magic attempt数が82.7%
増えた。magic rejection rateも52.48%から66.86%へ14.38 percentage point増加した。
一方、CNOT rejection rateは70.28%から70.00%で増えておらず、CNOT path平均の増加は11.6%
だった。8x10ではmagic pathとrejection rateが通常域へ戻り、runtime penaltyも消えた。

全caseで最大連続no-run streakは12 beatだった。したがって8x8 penaltyは単一の長い停止では
なく、routing/scheduling rejectionが広い実行期間で反復した結果と整合する。

### Interpretation

前回のgenericなrouting-capacity / congestion inferenceを、より限定した形で更新する。
H7 8x8のruntime penaltyは、長いmagic-delivery pathと大幅に増えた
`LATTICE_SURGERY_MAGIC` rejectionに対応している。CNOT側のrejection増加は観測されないため、
少なくともoperation別aggregate counterではmagic deliveryが主要な差分である。

ただし`failed_attempts`は、runnable queue candidateに対して`ScLsSimulator::Run`がfalseを
返した回数である。route search failure、occupied cell、factory access、timing reservationなどの
内部理由は分解していない。同時cell occupancyも未取得であるため、「特定cellの競合まで直接
観測した」とは主張しない。

### State classification

| item | classification |
| --- | --- |
| diagnostic有効時のresource semantics一致 | observed |
| H7 runtime差とtopology-overhead差の一致 | observed |
| H7 8x8でmagic path平均+132.1% | observed |
| H7 8x8でmagic rejected attempts+82.7% | observed |
| H7 8x8でCNOT rejection rateが増えない | observed |
| runtime penaltyがmagic-delivery routing負荷と結び付く | observed結果に基づくinference |
| simulator内部failure reasonの分解 | unresolved |
| simultaneous cell occupancy / congestion map | unresolved |

### Execution resources

- 4 caseをtmux内で逐次実行
- qret peak RSS: 3,381,192 KiB（約3.22 GiB）
- GNU timeのswap count: 0
- cgroup guard: `MemoryHigh=44G`, `MemoryMax=48G`

### References

- `artifacts/qret_runtime_routing_diagnostic_h5_h7_4th/summary.md`
- `artifacts/qret_runtime_routing_diagnostic_h5_h7_4th/results.csv`
- `artifacts/qret_runtime_routing_diagnostic_h5_h7_4th/results.jsonl`

## 2026-07-12: H7 magic rejection reason diagnostic

### Question

前節でH7 8x8のruntime penaltyが長いmagic pathと多い
`LATTICE_SURGERY_MAGIC` rejectionに対応することを確認したが、`Run=false`の内部理由は未分解
だった。そこで同じfixed circuitを使い、H7 8x8、8x10、10x10について、magic rejectionを
次のtop-level branchへ分類した。

- logical qubit busy
- magic-state stockなし
- available factory周辺にfree ancilla出口なし
- target qubit周辺に接続可能なfree ancillaなし
- factory側とtarget側に入口はあるがBFS経路が分断
- classical dependency / condition / other

保存するのはaggregate count、stock集約、path-length histogram、factory symbol別利用回数のみで、
per-attempt event logやcell occupancy traceは生成していない。

### Observed results

全3 caseで、診断有効時のruntime、topology-free runtime、gate count/depth、magic count/depth、
QV、code distance、physical qubitsが既存compile_infoと一致した。また各caseで理由別countの
合計がmagic failed-attempt総数と一致した。

| case | magic failures | qubit busy | no stock | factory egress blocked | target blocked | route disconnected |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| H7 8x8 | 3,977,917 | 2,125,010 | 215 | 1,838,510 | 8,592 | 5,590 |
| H7 8x10 | 2,178,179 | 2,138,084 | 39,037 | 0 | 551 | 507 |
| H7 10x10 | 2,177,693 | 2,138,103 | 39,040 | 0 | 295 | 255 |

H7 8x8ではmagic failureの46.218%が`factory_egress_blocked`だった。8x10と10x10では同じ
理由は0回である。8x8と10x10の差では、この理由が1,838,510回増えており、reason category中
最大の差だった。

一方、`no_magic_stock`は8x8で215回、magic failureの0.005%にすぎない。10x10では39,040回
発生しているがruntime penaltyはない。したがって、今回のH7 8x8 penaltyをfactory生成速度や
stock不足で説明することはできない。

### Factory access geometry

初期topologyで各factoryの四近傍にあるfree cell数と、成功したmagic operationのfactory利用数は
次のとおりだった。

| case | initial free neighbors m0/m1/m2/m3 | successful uses m0/m1/m2/m3 |
| --- | ---: | ---: |
| H7 8x8 | 0 / 1 / 2 / 2 | 82 / 657,223 / 657,182 / 657,219 |
| H7 8x10 | 2 / 2 / 2 / 2 | 526,933 / 380,541 / 474,892 / 589,340 |
| H7 10x10 | 2 / 2 / 2 / 2 | 590,364 / 591,445 / 328,050 / 461,847 |

8x8では`m0=(3,3)`の四近傍が、`m1=(3,4)`、`m2=(4,3)`、logical qubit 1 at
`(2,3)`、logical qubit 2 at `(3,2)`で全て占有される。m0の成功利用は82回で、全
1,971,706 magic operationの約0.004%だった。8x10と10x10では全factoryに初期free出口が2個
ある。

### Interpretation

H7 8x8のruntime penaltyについて、genericなmagic-delivery congestionから一段具体化できる。
主差分はmagic-state supply待ちではなく、available magic factoryからroutingを開始するfree
ancilla cellを確保できない`factory egress`制約である。これは8x8でのみ約184万回観測され、
8x10へ一辺を拡張すると0回になり、約11.12%のruntime penaltyも同時に消える。

m0の初期出口が0で実効的にほぼ利用不能であることは、8x8 topologyの明確な構造的弱点である。
ただし`factory_egress_blocked`は、そのbeatでstockを持つ全factoryからBFS queueを開始できない
場合の分類であり、約184万回をすべてm0単独へ帰属することはできない。動的なpath occupancyが
他factoryの出口も同時に塞ぐ寄与は残る。

stock平均はroutingが成功して消費される頻度にも依存するため、8x8と10x10のstock平均差を
独立な供給能力差として解釈しない。直接判断できるのは、8x8で`no_magic_stock`がほぼ発生せず、
供給待ちがruntime penaltyの主因ではないことである。

### State classification

| item | classification |
| --- | --- |
| diagnostic有効時のresource semantics一致 | observed |
| reason count合計とmagic failure総数の一致 | observed |
| H7 8x8でfactory-egress rejection 1,838,510回 | observed |
| H7 8x10 / 10x10でfactory-egress rejection 0回 | observed |
| H7 8x8でno-stock rejectionが0.005% | observed |
| H7 8x8のm0初期free出口が0、成功利用82回 | observed |
| 8x8 runtime penaltyの主差分がfactory egress制約 | observed結果に基づくinference |
| egress rejectionごとの具体的blocked cell | unresolved |
| m0閉塞と他factoryの動的閉塞の寄与分離 | unresolved |

### Next causal test

同じH7 8x8 fixed circuit、同じ4 factory座標を保ち、m0に隣接するlogical qubitを最小限だけ
外側へ移してm0の初期free出口を0、1、2と変えるmicro-sweepが次の候補である。これにより、
factory egress countとruntimeが出口数に応じて減るかを直接確認できる。ただしlogical placement
距離も同時に変わるため、移動量を最小化し、weighted CNOT distanceとmagic target distanceを
併記する。

### Execution resources

- H7 3 caseをtmux内で逐次実行
- qret peak RSS: 3,381,836 KiB（約3.23 GiB）
- GNU timeのswap count: 0
- cgroup guard: `MemoryHigh=44G`, `MemoryMax=48G`

### References

- `artifacts/surface_code_magic_failure_reason_diagnostic_h7_4th/summary.md`
- `artifacts/surface_code_magic_failure_reason_diagnostic_h7_4th/results.csv`
- `artifacts/surface_code_magic_failure_reason_diagnostic_h7_4th/results.jsonl`

## 2026-07-12: H7 8x8 factory-egress causal micro-sweep

### Question

前節では、H7 8x8のruntime penaltyと`factory_egress_blocked`が対応し、物理座標`(3,3)`の
factoryが初期free出口0でほぼ利用不能であることを確認した。ただし相関だけでは、出口閉塞を
解消すればruntimeが戻るかは未確認だった。

そこでlogical circuit、8x8 grid、4 factoryの座標集合、magic period/stock、QEC条件を固定し、
`(3,3)`に隣接するlogical qubitだけを最小距離移動して初期free出口を0、1、2へ変えた。

| case | intervention |
| --- | --- |
| `egress_0_baseline` | original H7 8x8、出口0 |
| `egress_1_left` | q1を`(2,3)`から`(1,3)`へ移動、左出口を1つ開く |
| `egress_1_down` | q2を`(3,2)`から`(3,1)`へ移動、下出口を1つ開く |
| `egress_2_both` | q1とq2を両方移動、出口2 |
| `egress_0_symbol_rotate` | 物理配置は変えずfactory symbolだけrotation |

全caseでQASM hash、optimized IR hash、topology-free runtime、gate count/depth、magic
count/depthが一致した。factory座標集合も同一である。

### Static-distance control

出口を開くqubit移動は、静的距離を改善していない。

| case | weighted CNOT distance delta | weighted nearest-factory distance delta |
| --- | ---: | ---: |
| `egress_1_left` | +37,316 | +377,908 |
| `egress_1_down` | +32,264 | +275,220 |
| `egress_2_both` | +69,580 | +653,128 |

したがってopen-egress caseでruntimeが短くなった場合、短い静的通信距離を原因にはできない。

### Observed results

| case | egress | runtime | vs baseline | topology overhead | egress rejection | magic mean path | trapped-coordinate uses |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `egress_0_baseline` | 0 | 9,858,370 | reference | 987,508 | 1,838,510 | 5.258 | 82 |
| `egress_1_left` | 1 | 8,871,838 | -10.0070% | 976 | 25 | 3.081 | 417,199 |
| `egress_1_down` | 1 | 8,871,822 | -10.0072% | 960 | 56 | 3.045 | 378,690 |
| `egress_2_both` | 2 | 8,872,721 | -9.9981% | 1,859 | 13 | 3.018 | 518,585 |
| `egress_0_symbol_rotate` | 0 | 9,858,370 | +0.0000% | 987,508 | 1,838,510 | 5.258 | 82 |

出口1を左・下のどちらに開いても、egress rejectionは約184万回から25-56回へ減り、runtimeは
約10.01%短縮した。10x10 baselineの8,871,700 beatに対して差は122-138 beat、約0.0014-
0.0016%であり、8x8 penaltyはほぼ完全に解消した。

出口2ではegress rejectionが13回まで減ったが、runtimeは出口1より899-883 beat長かった。
追加出口によるruntime改善はなく、0から1の間にあるthreshold responseだった。2つ目のqubit
移動によるdistance/routing変化が小さい残差へ混ざるため、出口数とruntimeの単調関係は主張しない。

symbol-only controlはruntime、topology overhead、egress rejection、magic pathがbaselineと完全
一致した。塞がれた物理座標の利用も82回のままで、factory label 0から3へ移っただけだった。
したがって現象はfactory IDやtie-breakではなく、物理access geometryに追随する。

QVはopen-egress 3 caseでbaseline比11.15-11.26%減少した。code distance=17、physical
qubits=34,680は全caseで共通なので、QEC threshold crossingは混ざっていない。

### Interpretation

今回のtested interventionでは、H7 8x8の約11.12% runtime penaltyがfactory出口閉塞によって
生じていたという因果解釈が強く支持された。根拠は次の組み合わせである。

- 独立な左・下の1-cell移動がほぼ同じruntime回復を生んだ
- egress rejectionが同時にほぼ0へ減った
- static CNOT / nearest-factory distanceは改善せず、むしろ悪化した
- factory symbolだけの変更では結果が完全一致した
- circuit-level workloadとQEC条件は固定された

したがって、この条件で重要なのはfactory countそのものではなく、各factoryがrouting networkへ
接続できるfree egressを持つことである。出口0のfactoryは配置上存在していても、実効的な供給源
としてほぼ機能しない。

ただし、logical qubitを移動するinterventionなので、dynamic routing全体にも局所的変化は入る。
今回のcontrol群により単純な距離改善とfactory ID効果は除外できたが、個々のblocked cell時系列を
直接追跡したわけではない。

### Updated architecture direction

今後のmapping / topology評価では、factory数に加えて次を明示的に記録する。

- factoryごとの初期free egress数
- egress 1以上のaccessible factory数
- factory egress rejection count
- factory座標別の実利用数

mapperへfactory周囲のrouting reserveを入れる場合、最低1つのfree egressをhard constraintまたは
強いpenaltyとして扱う候補が得られた。出口2は今回追加runtime改善を生まなかったため、最初の
設計仮説は「factoryごとに最低1出口を保証する」とする。

### State classification

| item | classification |
| --- | --- |
| H7 8x8 egress 0/1/2 micro-sweep | observed |
| 出口1でegress rejectionが約184万回から25-56回へ減少 | observed |
| 出口1でruntimeが約10.01%短縮 | observed |
| 出口1で10x10 runtime水準へ回復 | observed |
| 出口2に追加runtime改善がない | observed for tested placements |
| symbol-only controlがbaselineと完全一致 | observed |
| static distance悪化下でもruntimeが回復 | observed |
| H7 8x8 penaltyの主因がfactory egress制約 | strongly supported causal inference |
| mapperへのminimum-one-egress constraintの一般性 | proposed / unevaluated |

### Execution resources

- 5 caseをtmux内で逐次実行
- qret peak RSS: 3,381,536 KiB（約3.22 GiB）
- GNU timeのswap count: 0
- cgroup guard: `MemoryHigh=44G`, `MemoryMax=48G`

### References

- `configs/surface_code_factory_egress_micro_sweep_h7_4th.yaml`
- `configs/topologies/factory_egress_micro_h7_4th/factory_egress_manifest.json`
- `artifacts/surface_code_factory_egress_micro_sweep_h7_4th/summary.md`
- `artifacts/surface_code_factory_egress_micro_sweep_h7_4th/results.csv`
- `artifacts/surface_code_factory_egress_micro_sweep_h7_4th/results.jsonl`
