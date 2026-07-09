# Surface-code architecture sensitivity note

> このノートは初期の統合メモである。今後の主な追記は `architecture_research_log.md` に日付付きエントリとして行う。

## 1. このノートの目的

このノートは、`Evaluation_grouped_surface_code` で現在調べている研究方針、既存実験結果、解釈、未解決点、次の作業方針をまとめるための引き継ぎメモである。

主題は PF 次数差そのものではなく、同一 PF・同一 molecule・同一 logical circuit を固定したときに、surface-code / lattice-surgery 側の architecture 条件が resource metrics にどう効くかを調べることである。

今後 Codex や人間がこの repository を見たときに、次をすぐ把握できるようにする。

- 何を調べているのか
- どの結果が観測済みか
- どの解釈が推定か
- 何が未解決か
- 次に何をすべきか

## 2. 研究目的

この repository では、grouped H-chain product-formula circuit を対象に、quration / qret を用いて surface-code / lattice-surgery resource estimation を行う。

主な関心は、algorithm 側の PF 比較だけではなく、次のような architecture-side condition が runtime、qubit volume、chip cells、physical qubits、code distance、magic-state metrics にどう影響するかである。

- topology
- factory placement
- magic-state supply
- routing / mapping
- grid size
- factory count
- magic-state stock / buffer
- QEC resource estimation condition

現在の中心対象は、QPE で使う controlled product-formula one-step kernel である。full QPE circuit を compile しているわけではない。

## 3. Scope と意味論上の注意

標準対象は `efficient_controlled_pf_one_step` である。これは QPE-scale total を見積もるための efficient controlled PF one-step compile/profile 対象であり、full QPE compile ではない。

QPE-scale total は、one-step result に action count を掛けた線形外挿値として扱う。QPE phase register、inverse QFT、measurement、feed-forward、repeated QPE circuit は含まない。

結果を読むときは、次を必ず区別する。

- observed one-step compile/profile result
- estimated QPE-scale extrapolation
- unimplemented full-QPE compile result

topology sweep では logical circuit を変えない。architecture case 間で、Hamiltonian、grouping、PF order、target error、rotation precision、circuit scope が暗黙に変わってはいけない。これらが変わる場合は architecture effect ではなく circuit-generation change として扱う。

## 4. これまでの実験の流れ

### 4.1 Magic-state supply sweep

baseline / fast_supply / slow_supply / buffer 系の条件を比較してきた。

- baseline: `magic_generation_period=15`
- fast_supply: `magic_generation_period=8`
- slow_supply: より遅い magic-state supply
- buffer 系: magic-state stock / buffer を変える条件

観測済みの傾向として、fast_supply は小さい系では runtime 改善が出るが、大きい H-chain では効果が小さい。したがって `magic_generation_period=8` は STAR-like cheap magic と呼ぶには弱く、moderate fast-supply condition と扱うのが妥当である。

STAR-like cheap magic を見たい場合は、`magic_generation_period=1` または `2`、十分大きい stock などを持つ diagnostic 条件を別 regime として設計する必要がある。ただし、これは STAR architecture そのものを実装したという意味ではなく、cheap magic supply assumption の diagnostic として扱うべきである。

### 4.2 Topology / factory placement sweep

既存の topology / factory placement sweep では、H2-H11、PF=`2nd` / `4th(new_2)`、magic=baseline / fast_supply を対象にした。

topology 条件は次の 3 つである。

- `factory_left_edge`
- `factory_center_block`
- `factory_right_edge`

この sweep では、grid size=`10x10`、factory count=`4`、QEC 条件、routing algorithm は固定した。結果は 120 行すべて `success` である。

この結果も full QPE ではなく、`efficient_controlled_pf_one_step` からの QPE-scale extrapolation である。

| PF | magic | runtime spread avg / max | qubit volume spread avg / max | chip_cells | physical_qubits / code_distance |
|---|---:|---:|---:|---:|---:|
| 2nd | baseline | 0.0095% / 0.0287% | 9.21% / 21.98% | 0% | 0% |
| 2nd | fast_supply | 0.0112% / 0.0364% | 9.24% / 24.40% | 0% | 0% |
| 4th(new_2) | baseline | 0.0100% / 0.0323% | 9.16% / 21.38% | 0% | H4 のみ変化 |
| 4th(new_2) | fast_supply | 0.0087% / 0.0286% | 9.08% / 23.21% | 0% | H4 のみ変化 |

解釈上重要な点は次である。

- runtime spread は最大でも `0.04%` 未満で非常に小さい。
- qubit volume spread は平均約 `9%`、最大約 `24%` で明確に出る。
- qubit volume 最小は `center_block` が `40/40`。
- qubit volume 最大は `left_edge` が `40/40`。
- runtime best topology は case ごとに揺れる。
- `chip_cells` は全 120 行で `96` 固定。
- `physical_qubits` / `code_distance` はほぼ固定。ただし H4 `4th(new_2)` のみ例外がある。

参照 artifact:

- `docs/benchmarks/surface_code_topology_sweep_h2_h11_baseline_fast.md`
- `configs/surface_code_topology_sweep_h2_h11_baseline_fast.yaml`
- `artifacts/surface_code_topology_sweep_h2_h11_baseline_fast/results.md`
- `artifacts/surface_code_topology_sweep_h2_h11_baseline_fast/results.csv`
- `artifacts/surface_code_topology_sweep_h2_h11_baseline_fast/results.jsonl`

### 4.3 Mapping-only diagnostics

H4/H5、PF=`4th(new_2)`、magic=baseline / fast_supply、topology=left / center / right の 12 case について mapping-only diagnostic を行った。

この diagnostic では新規 full compile は走らせず、既存 `compile_info.json` を使った。mapping-only qret run により `mapping.json`、`mapping_compile_info.json`、`mapping_summary.json` を取得した。raw `mapping_state.json` は大きいため、解析後に削除済みである。

保存 artifact:

- `artifacts/surface_code_mapping_diagnostics_h4_h5_4th_new2/summary.md`
- `artifacts/surface_code_mapping_diagnostics_h4_h5_4th_new2/diagnostics.csv`
- `artifacts/surface_code_mapping_diagnostics_h4_h5_4th_new2/diagnostics.jsonl`

artifact size は約 `476KB`。mapping-only qret の peak RSS は H4 約 `3.0GB`、H5 約 `7.7GB` だった。保存対象は summary、diagnostics CSV/JSONL、per-case の小さい `mapping.json` / `mapping_summary.json` / `mapping_compile_info.json` であり、raw `mapping_state.json`、一時 pipeline YAML、run log JSON は含めない。

観測結果は次である。

- `center_block` が常に qubit volume 最小になる主因は、`chip_cell_active_qubit_area_ave` が最小になること。
- runtime はほぼ変わらない。
- H4/H5 の全 case で `LATTICE_SURGERY_MAGIC` は magic factory symbol `0` のみを使用。
- factory 4 個を置いていても、この条件では実効的には `m0` の位置が効いている。
- `left_edge`: `m0=(0,0)`、logical qubit cluster から遠い。
- `center_block`: `m0=(4,4)`、logical qubit cluster に近い。
- `right_edge`: `m0=(9,0)`、中間的。

代表値:

| case | center magic dist mean | left magic dist mean | center active area | left active area |
|---|---:|---:|---:|---:|
| H4 baseline | 6.78 | 13.56 | 11.300 | 12.749 |
| H5 baseline | 6.83 | 12.84 | 13.416 | 14.632 |

center vs left の差:

- H4 baseline: volume 差 `12.82%`, active-area 差 `12.82%`
- H4 fast: volume 差 `12.38%`, active-area 差 `12.38%`
- H5 baseline: volume 差 `9.07%`, active-area 差 `9.07%`
- H5 fast: volume 差 `8.76%`, active-area 差 `8.76%`

## 5. 現時点の解釈

### Observed

- 120 行 topology sweep は全行 `success`。
- runtime spread は非常に小さい。
- qubit volume spread は明確。
- `center_block` が全条件で qubit volume 最小。
- `left_edge` が全条件で qubit volume 最大。
- H4/H5 mapping diagnostic では `center_block` の active area が小さい。
- H4/H5 mapping diagnostic では `LATTICE_SURGERY_MAGIC` が `m0` のみを使用。

### Inferred / Estimated

- qubit volume 差の主因は runtime ではなく、factory placement による layout / routing / magic delivery geometry の違いと推定できる。
- 特に `m0` の位置が logical qubit cluster との距離を変え、`chip_cell_active_qubit_area_ave` を変えている可能性が高い。
- H4/H5 の結果から H2-H11 全体でも同様の構造がある可能性はあるが、これは未検証であり、断定してはいけない。

### Unresolved

- H2-H11 全体で `m0` のみを使っているか。
- `2nd` PF でも同じ mapping 構造か。
- quration / qret がなぜ factory symbol `0` のみを使うのか。
- factory symbol の順序を入れ替えると結果が変わるか。
- 複数 factory を実効的に使わせる設定があるか。
- H8/H11 など大きい系でも active area 差が同じ原因で出るか。
- STAR-like cheap magic condition をどう定義するか。
- `mapping_result_json` / `mapping_state` をどの粒度で保存すべきか。

## 6. H4 `4th(new_2)` 例外の扱い

H4 `4th(new_2)` では、`left_edge` で `code_distance=15`, `physical_qubits=43200`、`center_block` / `right_edge` で `code_distance=13`, `physical_qubits=32448` となる例外がある。

この case では、QEC resource estimation の離散的な code distance / physical qubits 選択が qubit volume 差に混ざる。

ただし H5 では code distance / physical qubits が固定のまま、同じ `center < right < left` の qubit volume ordering が出ている。したがって一般的な原因は physical qubits だけではなく、active area / magic delivery geometry と見るのが妥当である。

## 7. 今後の方針

### Phase A: 既存 artifact の commit / report 化

- mapping diagnostic artifact が未コミットなら、`summary.md`, `diagnostics.csv`, `diagnostics.jsonl` は commit 候補。
- raw `mapping_state.json` は巨大なので commit しない。
- `docs/benchmarks` に mapping diagnostic の短い報告を置くとよい。

### Phase B: H8/H11 mapping-only diagnostic

対象:

- H8, H11
- PF=`4th(new_2)`
- magic=baseline
- topology=`left_edge`, `center_block`, `right_edge`

目的:

- 大きい系でも `m0` のみ使用か確認する。
- `center_block` の active area 最小が維持されるか確認する。

注意:

- H5 mapping-only peak RSS が約 `7.7GB` だったため、H8/H11 はメモリに注意する。
- 実行する場合は tmux、RSS 監視、空きメモリ確認、raw state 削除方針が必要。

### Phase C: factory symbol / `m0` diagnostic

factory 座標は同じ集合のまま、symbol 順序だけを入れ替える。

目的は、quration / qret が symbol `0` を優先しているのか、座標や距離で選んでいるのかを確認することである。

これは topology 設計上重要である。もし `m0` のみ使うなら、現在の factory placement sweep は factory set placement sweep ではなく、実質 `m0` placement sweep である。

### Phase D: STAR-like cheap magic diagnostic

現在の fast_supply `magic_generation_period=8` は weak / moderate fast supply である。

STAR-like cheap magic を見るには、`magic_generation_period=1` または `2`、stock very large などを別 regime として設定する必要がある。

ただし、これは STAR architecture そのものを実装しているとは書かない。`cheap_magic` は diagnostic only として扱う。

### Phase E: STAR-like cheap arbitrary-rotation diagnostic

これまでの cheap magic sweep は、T magic state の生成周期を短くする diagnostic であり、logical magic demand、magic count、magic depth は基本的に変わらない。

STAR-like な任意角回転方式を疑似的に見るには、供給周期だけではなく、arbitrary rotation の Clifford+T synthesis cost 自体を下げる介入の方が本質に近い。

次の検証では、`magic_generation_period=15`、factory count、stock、topology を固定したまま、`rotation_precision` を緩めることで arbitrary-rotation synthesis cost を下げた diagnostic を行う。

この検証で見る指標は次である。

- magic count
- magic depth
- runtime with topology
- qubit volume
- active area
- code distance
- physical qubits

この検証は STAR implementation ではなく、`STAR-like cheap arbitrary rotation assumption` または `diagnostic reduction of arbitrary-rotation synthesis cost` として扱う。

### Phase F: topology variants 追加

`center_block` が有利である理由を確認した後、次の variant を検討する。

- `center_line_horizontal`
- `center_line_vertical`
- `top_edge`
- `bottom_edge`
- `distributed_corners`
- `corner_block`

最初は PF=`4th(new_2)`、H4/H6/H8/H10 など代表分子でよい。

## 8. 書き方・主張上の注意

- full QPE compile と書かない。
- QPE-scale estimated totals と observed one-step compile/profile result を区別する。
- H4/H5 mapping-only diagnostic の結果を H2-H11 全体へ断定的に一般化しない。
- STAR-like と書く場合は、cheap magic supply assumption または cheap arbitrary-rotation assumption の diagnostic であり、STAR topology そのものではないと明記する。
- 「factory 4 個を使った」と書く場合、現行 diagnostic では `m0` のみ使用だった点を併記する。
- runtime 差が小さいことと、architecture 効果がないことを混同しない。qubit volume には明確に効いている。

## 9. 参照ファイル

確認済み:

- `README.md`
- `AGENT_v1.md`
- `docs/benchmarks/surface_code_topology_sweep_h2_h11_baseline_fast.md`
- `configs/surface_code_topology_sweep_h2_h11_baseline_fast.yaml`
- `configs/topologies/tutorial_factory_left_edge.yaml`
- `configs/topologies/tutorial_factory_center_block.yaml`
- `configs/topologies/tutorial_factory_right_edge.yaml`
- `artifacts/surface_code_topology_sweep_h2_h11_baseline_fast/results.md`
- `artifacts/surface_code_topology_sweep_h2_h11_baseline_fast/results.csv`
- `artifacts/surface_code_topology_sweep_h2_h11_baseline_fast/results.jsonl`
- `artifacts/surface_code_mapping_diagnostics_h4_h5_4th_new2/summary.md`
- `artifacts/surface_code_mapping_diagnostics_h4_h5_4th_new2/diagnostics.csv`
- `artifacts/surface_code_mapping_diagnostics_h4_h5_4th_new2/diagnostics.jsonl`

存在しなかったもの:

- `AGENTS.md`
- `AGENT.md`

## 10. 現在の作業状態

このノート作成時点の HEAD は `7cc0d719c15a7f30a2b42a2926cca52545a45b26`。

このノート作成時点では、新規 compile、qret architecture sweep、full QPE 生成、H-chain benchmark 実行は行っていない。

`artifacts/surface_code_mapping_diagnostics_h4_h5_4th_new2/` は raw `mapping_state.json` を含まない小さい diagnostic artifact として保存する。raw `mapping_state.json` は保存されていない。
