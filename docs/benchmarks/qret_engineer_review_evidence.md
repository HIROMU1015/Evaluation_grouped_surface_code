# qret軽量化レビュー相談メモ 付録

この付録は、[qret_engineer_review_brief.md](qret_engineer_review_brief.md)の根拠を確認するためのsource auditと既存artifact索引である。新しい最適化は実装していない。

## 参照した主なreport

- `docs/benchmarks/qret_optimization_integrity_and_performance_summary.md`
- `docs/benchmarks/qret_optimization_summary.json`
- `docs/benchmarks/qret_instruction_arena_optimization.md`
- `docs/benchmarks/qret_pre_routing_high_water_audit.md`
- `docs/benchmarks/qret_lazy_inverse_map_optimization.md`
- `docs/benchmarks/qret_memory_reduction_strategy.md`
- `docs/benchmarks/qret_skip_pipeline_state_output.md`
- `docs/benchmarks/qret_compile_info_summary_optimization.md`
- `docs/benchmarks/qret_dep_graph_memory_optimization.md`
- `docs/benchmarks/qret_inverse_map_memory_optimization.md`
- `docs/benchmarks/qret_magic_path_interning_optimization.md`

## 主要結果の出典

H5 `4th(new_2)`のbaseline対final production比較は、`qret_optimization_integrity_and_performance_summary.md`のH5 cold/warm medianから転記した。比較対象は共通final optimized IRを入力したqret direct compileであり、end-to-end pipelineの測定ではない。

| 項目 | baseline | final production | 出典 |
| ---- | -------: | ---------------: | ---- |
| qret peak RSS cold | 5,484,042 KB | 435,258 KB | H5 cold table |
| process-tree peak RSS cold | 5,473,618 KB | 436,410 KB | H5 cold table |
| elapsed cold | 20.893 s | 19.169 s | H5 cold table |
| elapsed warm | 20.889 s | 18.979 s | H5 warm table |
| largest intermediate | 57.91 MB | 22.05 MB | H5 cold/warm table |
| total intermediate | 102.45 MB | 44.54 MB | H5 cold/warm table |

## Source Audit

| 変更 | 確認した主なsource | 確認した挙動 | レビュー観点 |
| ---- | ------------------ | ------------ | ------------ |
| pipeline-state output省略 | `sc_ls_fixed_v0_compile_backend.cpp`, `pipeline_state.cpp`, `surface_code.py` | pass manager完了後にskip分岐し、`BuildPipelineState`/`SavePipelineState`を呼ばない。Evaluationはcompile yamlにskip flagを出す | BuildPipelineStateが副作用やvalidationを兼ねないか |
| compile-info summary化 | `compile_info.cpp`, `calc_compile_info.cpp`, `compile_info.h` | full modeはvector本体をJSONへ書き、summary modeは`_ave`/`_peak`を保持してvector本体を省略する | 省略vectorを将来consumerが必要としないか |
| compact DepGraph | `calc_compile_info.h`, `calc_compile_info.cpp` | dense id、parent offsets、parent ids、edge lengths、node weightsでdepth計算する | ptr/id mapやlegacy graph属性の削除が将来passに影響しないか |
| magic-path exact interning | `magic_path_storage.h`, `magic_path_storage.cpp`, `instruction.h`, `routing.cpp` | hash bucket内で座標列全体を比較し、一致時だけ`shared_ptr<const list>`を共有する | path identity、ownership、mutation依存がないか |
| routing後inverse-map解放 | `routing.cpp`, `machine_function.h`, `machine_function.cpp`, `calc_compile_info.cpp`, `pipeline_state.cpp` | routing setupで構築し、routing後に解放する。mutation APIは必要時に再構築する | custom pipelineや将来passでrouting後のmapを期待しないか |

## 個別根拠

### Pipeline-state output省略

`RunCompilation()`はIR load、lowering、pass manager実行、`MaybeWriteLatticeSurgeryMagicPathProfile()`の後に`skip_pipeline_state_output`を判定する。skip時は`pipeline_state_output_skipped`を記録して終了し、`BuildPipelineState()`と`SavePipelineState()`は呼ばない。

`BuildPipelineState()`はpass履歴、target情報、compile-info、program JSONをまとめる。program JSONはMachineFunction instructionを走査して構築する。標準Evaluationではcompile-info JSONを別出力として読むため、pipeline-state JSONは後続observableに含めていない。

### Compile-info summary化

`ScLsFixedV0CompileInfo::Json(CompileInfoOutputMode)`は、full modeでは8本のTimeSeries vector本体と`_ave`/`_peak`を出す。summary modeではvector本体を出さず、summary statsから同じ`_ave`/`_peak`を出す。

`calc_compile_info.cpp`ではsummary経路でrate、chip cell、qubit_volumeを逐次集約する。duplicate/unknown classical symbolの検査、StartCorrectingを含むfeedback beat計算、magic/entanglement rate集計は既存semantic testsとH4/H5 parityで確認済みである。

### Compact DepGraph

legacy DepGraphはpointer/id mapと`DiGraph`を保持していた。compact DepGraphはdense id前提で、parent offsets、parent ids、edge lengths、node weights、DP作業領域に絞る。

構築時のedge規則は、qtargetの直前writer、Move/MoveTransのowner更新、Condition/CDependのreaction-time edge、reserved classical symbolの扱い、duplicate edge上書きを維持する。既存reportではlegacy系実装とcompact実装のnode/edge/depth metrics parityが確認されている。

### Magic-path exact interning

`HashPath()`はpath長と各`Coord3D`のx/y/zをhashへ混ぜる。hash衝突時もbucket内の候補に対して`EqualPath()`で座標列全体を比較するため、共有されるのは完全一致pathのみである。

interned modeでは命令側のlocal list payloadをclearし、`shared_ptr<const MagicPathList>`を保持する。interner自体はrouting pass scopeで消えるが、共有payloadはhandleにより生存する。既存H5 profileではunique paths 320、hit rate 99.865%、raw/normalized metrics parityが確認されている。

### Routing後inverse-map解放

`Routing::RunOnMachineFunction()`はeager defaultで各blockのinverse mapを構築し、routing main loop完了後に`mf.ReleaseInverseMaps()`を呼ぶ。`MachineBasicBlock::ReleaseInverseMap()`はmapを空mapとswapし、valid flagを落とす。

`Contain`、`InsertBefore`、`InsertAfter`、`Erase`は`EnsureInverseMap()`を通るため、release後にmutation APIが使われた場合は再構築される。標準後段のcompile-info計算とpipeline-state serializationはinstruction列を直接走査し、inverse mapを必要としない。

## 同値性確認の出典

`qret_optimization_integrity_and_performance_summary.md`と`qret_optimization_summary.json`では、H4 2nd、H4 `4th(new_2)`、H5 `4th(new_2)`についてraw metrics equal、normalized metrics equalがtrueである。semantic projectionも最終検証ログでequalとして扱っている。

最終検証ログのテスト結果:

- pytest: 186 passed
- CTest: 519 passed, 0 failed

この確認は対象H4/H5 pipelineとtest範囲での対象observableの観測的同値性であり、全入力への形式証明ではない。

## 本文から外した項目

本文では、qretエンジニアに判断してほしい5変更に絞った。streaming Python inliner、incremental JSON parsing、RZ helper cache、integral cache、prepared artifact cache、compile result cache、singleton operand compaction、lazy inverse-map、instruction arenaは、今回のレビュー主題から外した。
