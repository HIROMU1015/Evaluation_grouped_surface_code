# qret軽量化レビュー相談メモ

## 1. 相談の目的

共通optimized IRを入力したH5 qret direct compileにおいて、対象observableの観測的同値性を維持しながら、peak RSSを約92%削減した。quration/qretの設計上、この軽量化方針に問題がないかを確認いただきたい。

ここでの軽量化前は`baseline`、軽量化後は`final production`を指す。対象処理は`qret direct compile`、対象回路は`uncontrolled single Trotter step`である。

## 2. 主要削減結果

**表1: H5 `4th(new_2)` qret direct compileの主要削減結果**

| 指標 | baseline | final production | 改善率 |
| ---- | -------: | ---------------: | -----: |
| qret peak RSS | 5,484,042 KB | 435,258 KB | 92.06%削減 |
| process-tree peak RSS | 5,473,618 KB | 436,410 KB | 92.03%削減 |
| compile時間 cold | 20.893秒 | 19.169秒 | 8.25%短縮 |
| compile時間 warm | 20.889秒 | 18.979秒 | 9.14%短縮 |
| 最大中間ファイル | 57.91 MB | 22.05 MB | 61.93%削減 |
| 中間ファイル合計 | 102.45 MB | 44.54 MB | 56.53%削減 |

```text
baseline 5.48 GB
  -> final production 0.44 GB
```

この比較は、共通のfinal optimized IRを入力したqret direct compileのbaseline対final比較である。Python側の積分生成、回路生成、RZ helper生成を含む完全なend-to-end pipelineの92%削減を意味しない。

## 3. Benchmark条件

- 対象: H5 `4th(new_2)`、`uncontrolled single Trotter step`
- 入力: baseline/final productionで共通のfinal optimized IR
- baseline: production qretメモリ最適化前の安定版
- final production: pipeline-state output省略、compile-info summary化、compact DepGraph、magic-path exact interning、routing後inverse-map解放を有効化
- 測定: qret direct compileのcold/warm、`/usr/bin/time -v`、process-tree sampler、compile-info size、中間ファイルサイズ
- 実測範囲: H4/H5のみ。H6-H9は未実測

## 4. 主な変更

**表2: 変更と確認事項**

| 変更 | 何を削減したか | 同値性の根拠 | 確認したい点 |
| ---- | -------------- | ------------ | ------------ |
| pipeline-state outputの省略 | 未使用のpipeline-state構築とserialization | pass manager、routing、compile-info計算後に出力だけ省略 | 構築処理に副作用やvalidation責務がないか |
| compile-info summary化 | 8本のTimeSeries full vectorと大きなJSON | scalarと`_ave`/`_peak`を保持しraw/normalized metrics一致 | 将来必要なobservableを失っていないか |
| compact DepGraph | legacy graphのptr/id mapと集合ベース隣接表 | node/edge規則とdepth metric一致 | quration設計上保持すべきgraph属性を削っていないか |
| magic-path exact interning | 重複した`LATTICE_SURGERY_MAGIC` path list | 座標列完全一致時のみ共有しmetrics一致 | path identity、ownership、mutation前提がないか |
| routing後のinverse-map解放 | routing後も残るinstruction pointer map | 後段はinstruction列を直接走査しmetrics一致 | custom pipelineや将来passがrouting後に必要としないか |

### 1. Pipeline-state outputの省略

- 変更前の問題: Evaluationでは後続処理がpipeline-state JSONを参照しないが、qretは大きなprogram JSONを構築して保存していた。
- 変更内容: pass manager完了後、compile-info dumpは維持したまま`BuildPipelineState`/`SavePipelineState`だけを省略する。
- 意味論を維持すると考える根拠: routing、compile-info計算、compile-info JSON出力はskip前に完了し、H4/H5でraw/normalized metricsが一致した。
- エンジニアへ確認したい点: pipeline-state構築が、出力以外のvalidationや状態更新を兼ねていないか。

### 2. Compile-info summary化

- 変更前の問題: full modeは8本のTimeSeries vectorをJSONへ出力し、H5ではcompile-infoが最大中間ファイルになっていた。
- 変更内容: Evaluationが使用するscalar、detail、`_ave`、`_peak`を保持し、full vector本体はsummary modeで省略する。
- 意味論を維持すると考える根拠: 使用observableは同じ集約値として保持し、H4/H5でraw/normalized metricsが一致した。
- エンジニアへ確認したい点: 全TimeSeriesを保持せず必要な集約値を逐次計算する設計が、現在のresource metricsに対して妥当か。

| 指標 | Full | Summary | Evaluationで使用 | 同値確認 |
| ---- | ---: | ------: | ---------------: | -------: |
| runtime、gate/magic/entanglement/QEC scalar | 保持 | 保持 | yes | yes |
| gate_count_detail | 保持 | 保持 | yes | yes |
| 8本のTimeSeries vector本体 | 保持 | 省略 | no | 対象外 |
| 8本の`_ave`/`_peak` | vectorから計算 | summary statsから計算 | yes | yes |
| qubit_volume | 保持 | 保持 | yes | yes |

### 3. Compact DepGraph

- 変更前の問題: compile-info用DepGraphがpointer map、id map、集合ベースの隣接表を保持していた。
- 変更内容: dense idとflat vectorでparent offsets、parent ids、edge lengths、node weightsだけを保持する。
- 意味論を維持すると考える根拠: qtarget、Move/MoveTrans、Condition/CDepend、duplicate edgeの規則を維持し、depth関連metricsが一致した。
- エンジニアへ確認したい点: 現在のdepth metricには不要でも、将来passで必要なgraph属性を削除していないか。

### 4. Magic-path exact interning

- 変更前の問題: `LATTICE_SURGERY_MAGIC`が同一pathを命令ごとに`std::list<Coord3D>`として保持していた。
- 変更内容: routing中に座標列全体が完全一致するpathのみを共有し、命令側はimmutableな共有handleを参照する。
- 意味論を維持すると考える根拠: hash後に実値比較を行い、pathの値、順序、routing判断は変更していない。H4/H5でraw/normalized metricsが一致した。
- エンジニアへ確認したい点: magic path objectのidentityや個別ownershipに意味がある箇所、または共有後にpathを変更する処理が存在しないか。

### 5. Routing後のinverse-map解放

- 変更前の問題: routing中のmutation用inverse mapが、routing後のcompile-info計算や出力段階まで残っていた。
- 変更内容: routing main loopと一時構造破棄後に各blockのinverse mapを解放する。必要時は既存API経由で再構築できる。
- 意味論を維持すると考える根拠: 標準後段はMachineFunctionのinstruction列を直接走査し、inverse mapを使用しない。H5でmetrics一致を確認した。
- エンジニアへ確認したい点: custom pipelineや将来passを考えた場合、routing後に解放する設計で問題ないか。

| Stage | inverse map使用 | release後に実行 |
| ----- | --------------: | --------------: |
| IR load / lowering / mapping | no | no |
| routing setup / main loop | yes | no |
| calc-info without topology | no | yes |
| calc-info with topology | no | yes |
| dump compile-info | no | yes |
| pipeline-state serialization | no、instruction列を直接走査 | Evaluationではskip |

## 5. 同値性確認

| 対象 | raw metrics | normalized metrics | semantic projection |
| ---- | ----------- | ------------------ | ------------------- |
| H4 2nd | equal | equal | equal |
| H4 `4th(new_2)` | equal | equal | equal |
| H5 `4th(new_2)` | equal | equal | equal |

- pytest: 186 passed
- CTest: 519 passed, 0 failed

これは対象H4/H5 pipelineとtest範囲での観測的同値性であり、全入力に対する形式証明ではない。

## 6. 確認いただきたい点

1. Evaluationでpipeline-stateを利用しない場合、その構築およびserializationを省略しても、qretの設計意図上問題ないでしょうか。
2. summary modeで保持するscalarと`_ave`/`_peak`だけで、現在使用しているresource metricsとして十分でしょうか。
3. compact DepGraphは現在のdepthおよびdependency metricには同値ですが、qurationの設計上保持すべきgraph属性を削除していないでしょうか。
4. magic pathのidentity、個別ownership、後続mutationに依存する箇所は存在しないでしょうか。
5. 標準Evaluation pipelineではrouting後に不要と確認していますが、custom pipelineや将来passを考えた場合、inverse mapをrouting後に解放してよいでしょうか。

## 7. 対象外・制限

- full QPE circuitではない
- controlled-Uを含まない
- QPE ancillaを含まない
- inverse QFTを含まない
- measurement feed-forwardを含まない
- 複数Trotter stepの非加法効果は未評価
- H6-H9は未実測

複数の候補も評価したが、採用基準未達のためproductionには入れていない。詳細なsource auditと根拠は[qret_engineer_review_evidence.md](qret_engineer_review_evidence.md)に分けた。
