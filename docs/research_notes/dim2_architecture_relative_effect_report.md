# single-plane Dim2 architecture 条件の相対効果レポート

## 1. 目的

このレポートは、これまでのsurface-code resource sweepを横断し、**同一の論理回路を保ったまま
architecture条件だけを変えたとき、runtimeとqubit volume (QV) が基準条件から何%変化したか**を
整理する。

主な研究質問は次の2点である。

1. single-plane `Dim2` に、固定回路のruntimeを大きく変えるarchitecture条件があるか。
2. runtimeが変わらない場合でも、QVへ影響するarchitecture条件は何か。

`rotation_precision`の変更はRZ合成後の回路自体を変える。そのため、`1e-5`から`1e-2`へ変更した
ことによるruntime/QV削減はarchitecture効果として数えない。`1e-5`と`1e-2`は、それぞれ固定された
別workloadとして扱い、各regime内でarchitecture条件を比較する。

## 2. 対象範囲

主対象は、特記しない限り次の条件で実行したsingle-plane `Dim2` sweepである。

- molecule: H4-H7
- PF: `4th(new_2)`
- circuit scope: `efficient_controlled_pf_one_step`
- grid: 10x10
- factory: center block、4 factory
- magic generation period: 15
- maximum magic-state stock: 10000
- reaction time: 1
- rotation precision:
  - `1e-5`: conventional-RZ workload
  - `1e-2`: cheap-RZ diagnostic workload

結果はone-step compile/profileと、その同一stepを用いたQPE-scale線形外挿に基づく。full QPE circuitを
一括compileした結果ではない。相対値の中心はH4-H7だが、magic供給速度については既存のH2-H10
結果も補助的に参照する。同一molecule/PF内ではQPE action multiplierがarchitecture case間で共通なため、
one-stepと線形外挿totalの相対比は同じである。

`DistributedDim2`はplane間通信という別のarchitecture modelを持つため、single-planeの順位表には
混ぜない。結果は[paired-precision DistributedDim2 summary](../../artifacts/surface_code_distributed_dim2_sweep_h4_h7_4th_paired/summary.md)
に分離してある。

加えて、current qretのfixed path latencyを変更したdistance-sensitive diagnosticを別枠で扱う。この
diagnosticは「経路長がoperation latencyへ入る場合にgeometry感度がどう変わるか」を調べる感度分析で
あり、標準Dim2の実測結果やcalibrated hardware predictionとは混ぜない。変更は保存patchから一時build
したqretだけへ適用し、vendored quration sourceは検証後に復元している。

## 3. 相対値の定義

各metric `M`の相対変化を次で定義する。

```text
delta_M [%] = (M_case / M_reference - 1) * 100
```

- 正: 基準より増加。runtime/QVでは原則として悪化。
- 負: 基準より減少。runtime/QVでは原則として改善。
- `spread`: `(maximum - minimum) / minimum * 100`。明確な単一baselineを置かない配置比較で使う。

このレポートでは便宜上、runtime変化を次のように分類する。

| 分類 | 相対変化の絶対値 | 用途 |
| --- | ---: | --- |
| large | 10%以上 | runtime-primaryなarchitecture候補 |
| medium | 1%以上10%未満 | 条件依存で無視できない |
| small | 1%未満 | 現在の研究目的では副次的 |

これは本レポート内の探索基準であり、一般的な有意差基準ではない。

## 4. 結論の要約

### 4.1 runtime

single-plane Dim2でruntimeを大きく変えたのは、通常の距離や配置ではなく、次のような**供給・
feed-forward・accessibilityの閾値条件**だった。

| architecture介入 | 基準 | runtime変化 | 判定 |
| --- | --- | ---: | --- |
| reaction time 1 -> 10, `1e-5` | reaction=1 | +188.849%から+191.957% | large |
| reaction time 1 -> 10, `1e-2` | reaction=1 | +13.415%から+61.208% | large |
| factory 4 -> 1, `1e-5` | 4 factory | +233.370%から+240.139% | large |
| factory 4 -> 1, `1e-2` | 4 factory | +3.206%から+24.317% | mediumからlarge |
| factory egress 1本以上 -> 0本 | egressあり | +11.109%から+12.122% | large |
| magic period 15 -> 100, `1e-2` | period=15 | +6.096%から+100.075% | mediumからlarge |
| stock 10000 -> 1, `1e-5` | stock=10000 | +3.763%から+4.263% | medium |
| stock 10000 -> 1, `1e-2` | stock=10000 | +0.643%から+2.182% | smallからmedium |

一方、接続性とfactory egressを保った通常のgeometry変更は、runtimeをほとんど変えなかった。

| geometry介入 | runtime変化 |
| --- | ---: |
| factory placement spread | 全caseで0.033%未満 |
| logical placement spread | 最大0.061% |
| central routing choke | 最大+0.108% |
| H5/H7 grid形状、8x8 pathologyを除外 | 最大約0.016% |
| factory 4 -> 8 | 最大0.450%の短縮 |

したがって、現在のqret single-plane Dim2モデルでは、**通常のconnected layout内で距離を増減するだけで
runtimeが大幅に変わる、という証拠は得られていない**。大きな差は、供給能力を下回る、feedback
latencyを増やす、またはfactory出口を完全に失う場合に現れた。

ただし、この結論はcurrent fixed-latency machine modelに限定される。route長をlatencyへ入れて再routing・
reschedulingしたdiagnosticでは、H4-H6の同一固定回路に対して次のstress penaltyが得られた。

| diagnostic介入 | quarter係数 | unit係数 |
| --- | ---: | ---: |
| compactからperimeter placement | +11.394%から+19.659% | +38.274%から+80.748% |
| remote banからcentral choke | +1.397%から+7.982% | +7.460%から+27.796% |

reference、intermediate、stressのruntime順序はnonfixed 28 groupすべてで単調だった。従って、通常
geometryがruntimeに本質的に無関係なのではなく、**current fixed-latency仮定がdistance sensitivityを
隠している**と解釈する。ただしquarter/unitはhardware校正値ではないため、この表は定性的な感度と
相対的な強弱を示すdiagnostic resultである。

### 4.2 qubit volume

QVはruntimeよりgeometryへ敏感だった。代表的な相対変化をまとめる。

| architecture介入 | QV変化 `1e-5` | QV変化 `1e-2` |
| --- | ---: | ---: |
| reaction 1 -> 10 | +162.227%から+168.294% | +10.302%から+44.328% |
| reaction 1 -> 100 | +1790.845%から+1853.279% | +114.155%から+496.950% |
| factory 4 -> 1 | +205.058%から+209.918% | +2.398%から+17.828% |
| magic period 15 -> 100 | 未実施 | +4.318%から+71.447% |
| egressあり -> zero egress | +12.319%から+12.694% | 未実施 |
| factory placement spread | 6.740%から12.821% | 0.189%から4.152% |
| logical placement spread | 5.357%から10.938% | 5.901%から8.983% |
| central routing choke | +1.673%から+2.723% | +5.570%から+6.842% |
| stock 10000 -> 1, H4-H6 | +5.243%から+6.357% | +0.668%から+2.461% |
| factory 4 -> 8, H4-H6 | -5.620%から-3.487% | -1.070%から-0.515% |

特にlogical placementとrouting chokeでは、runtime変化が0.1%以下でもQVが数%変化した。これは
architectureがcritical-path長よりも、routing path、ancilla利用、cell-time occupancy、平均active
areaへ作用したことを示す。

distance-sensitive diagnosticではQV差も拡大した。quarter係数のstress QV penaltyはplacementで
+26.795%から+44.172%、routingで+5.591%から+22.967%だった。unit係数ではplacementが+63.509%から
+131.631%、routingが+17.672%から+61.400%だった。code distanceが変わる一部caseでは、これらにQEC
threshold crossingも含まれるため、主結論はfixed-circuit beat runtimeから導く。

## 5. Geometryとmapping

### 5.1 Factory placement

#### 初期H2-H11 sweep

初期のH2-H11、2 PF、period=15/8、3 topologyの120 caseは全件成功した。各molecule/PF/magic
regime内のtopology spreadを集約すると次のとおりだった。

| PF | supply regime | runtime spread平均 | runtime spread最大 | QV spread平均 | QV spread最大 |
| --- | --- | ---: | ---: | ---: | ---: |
| `2nd` | period 15 | 0.0095% | 0.0287% | 9.21% | 21.98% |
| `2nd` | period 8 | 0.0112% | 0.0364% | 9.24% | 24.40% |
| `4th(new_2)` | period 15 | 0.0100% | 0.0323% | 9.16% | 21.38% |
| `4th(new_2)` | period 8 | 0.0087% | 0.0286% | 9.08% | 23.21% |

40 groupすべてでQV最小はcenter block、最大はleft edgeだった。一方、runtime best topologyはgroupごとに
変わった。この広いmolecule/PF sweepの段階で、factory placementがruntimeではなくQVへ効く傾向が
確認された。

H4/H5のcompile-info診断では、centerとleftのQV差がaverage active-area差とほぼ一致した。初期の
pre-routing artifactではmagic factory symbol 0だけが見えたため、一時的にm0位置が原因と推定したが、
後のpost-routing `program[*].mtarget`抽出では4 factoryの全symbolが使われていた。symbol名だけを座標間で
入れ替えてもruntimeは不変で、QV変化も最大約0.05%だった。

従って現在の解釈は、「m0だけが使われる」ではなく、**factory座標集合とlogical clusterの相対geometryが
magic deliveryを含むactive-area occupancyへ作用する**である。pre-routingのm0-only観測は最終factory
usageを表さないため、最終結論には使わない。

#### H4-H7 paired-precision sweep

比較条件は`factory_left_edge`、`factory_center_block`、`factory_right_edge`である。各molecule/
precision内の最小値を基準としたspreadを示す。

| molecule | runtime spread `1e-5` | runtime spread `1e-2` | QV spread `1e-5` | QV spread `1e-2` |
| --- | ---: | ---: | ---: | ---: |
| H4 | 0.01904% | 0.01639% | 12.821% | 4.152% |
| H5 | 0.03228% | 0.00193% | 9.072% | 1.808% |
| H6 | 0.00474% | 0.02595% | 7.847% | 0.189% |
| H7 | 0.00813% | 0.01733% | 6.740% | 1.038% |

観測結果は次のとおりである。

- factory位置はruntime critical pathを変えず、主にQVを変えた。
- conventional workloadではcenter blockがQV最小、left edgeが最大となる傾向が強かった。
- cheap-RZではQV spreadが全分子で縮小した。factory placement感度は強まらず、弱まった。
- magic需要を減らすとfactory access頻度とdelivery occupancyも減るため、factory geometryの重要度が
  下がる、という解釈と整合する。
- H4 `1e-5`だけはtopology間でcode distanceが異なるため、12.821%のQV spreadにはQECの離散変化も
  混在する。他の掲載groupは同一precision内でcode distanceが共通である。

従って、factory placementはconventional workloadにおけるspace-time resource要因ではあるが、
tested conditionではruntime最適化要因ではない。

### 5.2 Logical-qubit placement

基準候補は`explicit_compact_interaction_aware`であり、同一compact cell集合上でCNOT interactionを
考慮してlogical IDを割り当てた。比較対象はauto mapping、numeric compact、perimeter stressである。

| molecule | runtime spread `1e-5` | runtime spread `1e-2` | QV spread `1e-5` | QV spread `1e-2` |
| --- | ---: | ---: | ---: | ---: |
| H4 | 0.00160% | 0.03278% | 10.938% | 8.983% |
| H5 | 0.00165% | 0.00883% | 8.233% | 7.793% |
| H6 | 0.00223% | 0.01375% | 6.431% | 7.087% |
| H7 | 0.00735% | 0.06101% | 5.357% | 5.901% |

interaction-aware配置を基準としたauto mappingのQV penaltyは次のとおりだった。

| molecule | auto QV penalty `1e-5` | auto QV penalty `1e-2` |
| --- | ---: | ---: |
| H4 | +6.578% | +3.641% |
| H5 | +5.626% | +6.073% |
| H6 | +4.126% | +4.471% |
| H7 | +3.472% | +4.631% |

同一cell集合のnumeric assignmentとinteraction-aware assignmentだけを比較すると、static weighted
CNOT objectiveは16.78%から18.41%改善し、QVは次の範囲で減少した。

- `1e-5`: -2.170%から-1.226%
- `1e-2`: -1.922%から-1.709%

perimeter stressはnumeric compact比でQVを次の範囲だけ増やした。

- `1e-5`: +3.620%から+8.531%
- `1e-2`: +3.943%から+6.889%

全groupでcode distance、physical-qubit count、chip-cell countは配置間で一致した。従ってQV差は
QEC threshold crossingではなく、主にactive area / occupied cell-time差である。logical placementは
cheap-RZ後にも残るspace-time最適化軸だが、runtime差は最大0.061%に留まった。

### 5.3 Grid capacityとaspect ratio

明示interaction-aware配置について、matched 10x10を基準に8x8と12x12を比較した。

| molecule | precision | 8x8 runtime | 8x8 QV | 12x12 runtime | 12x12 QV |
| --- | --- | ---: | ---: | ---: | ---: |
| H4 | `1e-5` | +0.000% | +0.645% | +0.000% | +0.646% |
| H4 | `1e-2` | +0.000% | +0.794% | +0.000% | +0.796% |
| H5 | `1e-5` | +0.000% | +0.342% | +0.000% | +0.342% |
| H5 | `1e-2` | +0.000% | +0.754% | +0.000% | +0.745% |
| H6 | `1e-5` | +0.000% | +1.593% | -0.000% | +0.350% |
| H6 | `1e-2` | +0.005% | -0.024% | +0.000% | +0.602% |
| H7 | `1e-5` | +11.122% | +14.057% | -0.008% | +0.929% |
| H7 | `1e-2` | +0.197% | +1.648% | -0.061% | +0.304% |

H7 `1e-5`の8x8だけがlarge runtime effectを示したが、この結果を「gridが狭いため一般的なrouting
congestionが増えた」と解釈するのは不正確だった。後述のfactory-egress検証で、8x8配置が特定factory
のfree egressを0本にしたことが主因と分かった。

追加のH5/H7 grid-threshold sweepでは、10x10基準に対して次を観測した。

- H5: 8x8、8x10、9x9、10x8、10x12、12x10の最大runtime差は+0.015596%。
- H7: 8x8を除く同じgrid群は約0.006%以内。
- H7 8x8以外のQVは10x10比-0.255%から+1.220%。

従って、factory egressを確保したadequate-capacity regimeでは、tested grid size/aspect ratioの
runtime感度は小さい。

auto mappingでは8x8のsoft candidateが12 cellしかなく、13 logical qubitのH6と15 logical qubitの
H7はmappingに失敗した。一方、明示配置では成功したため、これはraw grid capacity不足ではなく
auto mapperのcandidate-generation policy境界である。

また、固定code distanceで静的physical-qubit footprintは10x10に対して次のように変わる。

- 8x8: -37.5%
- 12x12: +45.8%

12x12はruntimeを改善せず、明示配置QVも改善しなかった。auto mapperでは余剰面積にqubitを広げ、
10x10比QVが最大+5.868%となった。単純にgridを大きくすることはruntime/QV改善を保証しない。

### 5.4 Connected routing choke

10x10、factory数、usable-cell budget、factory egressを固定し、同数のbanを遠隔へ置いた
`remote_ban_control`を基準として、中央へ集約した`central_choke`を比較した。

| molecule | runtime penalty `1e-5` | runtime penalty `1e-2` | QV penalty `1e-5` | QV penalty `1e-2` |
| --- | ---: | ---: | ---: | ---: |
| H4 | +0.0016% | +0.0055% | +2.7232% | +6.5875% |
| H5 | +0.0023% | +0.0326% | +1.6733% | +5.6837% |
| H6 | +0.0067% | +0.1080% | +2.3909% | +5.5701% |
| H7 | +0.0093% | +0.0421% | +2.0053% | +6.8424% |

central chokeによりmean CNOT pathはcontrol比で約61.99%から81.68%増えた。それでもruntime penaltyは
最大+0.1080%だったため、「経路差を十分作れなかったからruntimeが変わらなかった」という説明は
支持されない。

同じ条件でQVは+1.673%から+6.842%増えた。code distanceは各molecule/precision内で共通なので、
この差はQEC離散変化を含まない。current Dim2 modelではpath lengthとretry増加が主にcell-time
occupancyへ現れ、critical-path beat数にはほぼ現れない。

### 5.5 Factory egress threshold

factoryに隣接するfree routing cell数を変え、usable-cell減少だけを模したremote-ban controlと比較した。

| molecule | 参照egress | 変更egress | runtime変化 | QV変化 |
| --- | ---: | ---: | ---: | ---: |
| H5 | 2 | 1 | 0.0000% | +0.5660% |
| H5 | 2 | 0 | +12.1222% | +12.3193% |
| H6 | 1 | 0 | +12.0406% | +12.4810% |
| H6 | 1 | 2 | -0.0001% | -0.6843% |
| H7 | 1 | 0 | +11.1198%から+11.1200% | +12.552%から+12.694% |
| H7 | 2 | 0 | +11.1088% | +12.642% |

H5/H6ではegressを0本にするとruntimeが約12%増え、remote banは最大+0.0016%だった。H7ではegress
ありを基準に0本へ閉じると約11.1%増え、逆方向に0本から1本を開くと約10.0%減った。2本目を追加しても
runtimeは改善しなかった。H6の2-egress caseはq0も移動するため、QV差は純粋なegress本数効果ではない。

この結果から、tested conditionのresponseは連続的な「出口数が多いほど速い」効果ではなく、
**0本と1本の間の閾値**である。H7 8x8の+11.122% runtime penaltyは、このzero-egress pathologyで
ほぼ説明できる。

## 6. Magic-state supply architecture

### 6.1 Accessible factory count: 1から4

4-cellのfactory/ban budgetを固定し、4 factoryを基準にaccessible factory数だけを1、2、3へ減らした。
全factoryでegressを確保しており、zero-egress効果とは分離している。

#### Conventional workload (`1e-5`)

| molecule | 1 factory runtime | 2 factory runtime | 3 factory runtime | 1 factory QV | 2 factory QV | 3 factory QV |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| H4 | +240.1390% | +70.0709% | +13.3823% | +205.0581% | +62.4146% | +13.2237% |
| H5 | +236.3633% | +68.1823% | +12.1222% | +205.8094% | +61.4690% | +12.1879% |
| H6 | +236.1285% | +68.0646% | +12.0433% | +208.0304% | +61.8494% | +11.8417% |
| H7 | +233.3703% | +66.6853% | +11.1237% | +209.9176% | +61.5228% | +11.4768% |

1から3 factoryではruntimeが`magic count * period / factory count`の供給floorにほぼ一致し、明確な
magic-supply bottleneckだった。4 factoryで単純な逆数則から外れ、残りのdependency scheduleへ
critical pathが移った。3から4への追加でもruntimeは約10%から12%短縮する。

QVにはfactory数によるruntime変化に加えてcode-distance threshold crossingが含まれるcaseがある。
従ってこの表のQV全量をdelivery occupancyだけに帰属できない。

#### Cheap-RZ workload (`1e-2`)

| molecule | 1 factory runtime | 2 factory runtime | 3 factory runtime | 1 factory QV | 2 factory QV | 3 factory QV |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| H4 | +24.3173% | +3.3891% | +1.1249% | +17.8283% | +2.5493% | +0.8147% |
| H5 | +6.0586% | +2.0154% | +0.6699% | +4.5167% | +1.5908% | +0.5053% |
| H6 | +4.6634% | +1.5326% | +0.4897% | +3.3452% | +1.1363% | +0.3599% |
| H7 | +3.2058% | +1.0393% | +0.3176% | +2.3977% | +0.7838% | +0.2525% |

cheap-RZではmagic demandが小さいためfactory不足の感度も小さい。4 factory比1%以内となる最小countは
H4が4、H5-H7が3だった。architecture sensitivityはarchitecture要因と残存workloadの結合に依存し、
cheap-RZが常に差を拡大するわけではない。

### 6.2 Factory count saturation: 4から8

factory + banを8 cellで固定し、4 factoryを基準に6、8へ増やした。8 factoryの4 factory比を示す。

| molecule | runtime `1e-5` | runtime `1e-2` | QV `1e-5` | QV `1e-2` |
| --- | ---: | ---: | ---: | ---: |
| H4 | -0.0970% | -0.4501% | -5.6195% | -1.0699% |
| H5 | -0.0409% | -0.1697% | -3.4865% | -0.6227% |
| H6 | -0.0752% | -0.4344% | -4.3135% | -0.5154% |

全runtime改善が1%未満であり、6から8の残差は`1e-5`で最大0.0306%、`1e-2`では0%だった。H7は
事前に設定した追加実行条件を満たさなかったため実行していない。

4 factoryはtested H4-H6でruntime上ほぼ飽和している。一方、conventional QVは最大5.620%減った。
追加factoryはruntimeよりもnearest-source geometryやdelivery occupancyを改善した可能性がある。
ただし、このsweepは通常の4-cell budgetではなく全caseで8 cellを予約しているため、通常baselineとの
絶対比較には使わない。

### 6.3 Maximum magic-state stock

stock=10000を基準にstockを1、4、16、64へ制限した。H4-H6の結果である。

| precision | stock | runtime penaltyの範囲 | QV penaltyの範囲 |
| --- | ---: | ---: | ---: |
| `1e-5` | 1 | +3.7625%から+4.2633% | +5.2427%から+6.3568% |
| `1e-5` | 4 | +2.2427%から+2.8154% | +3.6564%から+4.7263% |
| `1e-5` | 16 | +1.3438%から+1.8610% | +2.4454%から+3.4675% |
| `1e-5` | 64 | +0.1011%から+0.3427% | +1.0135%から+1.6364% |
| `1e-2` | 1 | +0.6434%から+2.1822% | +0.6681%から+2.4612% |
| `1e-2` | 4 | +0.3872%から+1.3681% | +0.4456%から+1.6711% |
| `1e-2` | 16 | +0.0675%から+0.2992% | +0.1420%から+0.6150% |
| `1e-2` | 64 | 0.0000% | +0.0303%から+0.0844% |

runtime差が1%未満になる最小stockは、`1e-5`では全分子64、`1e-2`ではH4が16、H5が4、H6が1だった。
stock=10000はruntime探索用baselineとして十分に飽和しており、これ以上のstock増加を調べる価値は
低い。

### 6.4 Magic generation period

#### Conventional workloadのfast-supply側

既存H2-H10 `4th(new_2)`結果でperiod=15を基準にperiod=1へ高速化した相対変化を示す。logical
magic demandは不変である。

| molecule | runtime変化 | QV変化 |
| --- | ---: | ---: |
| H2 | -6.502% | -9.019% |
| H3 | -0.450% | -2.746% |
| H4 | -0.154% | -1.501% |
| H5 | -0.071% | -1.088% |
| H6 | -0.041% | -0.889% |
| H7 | -0.026% | -0.537% |
| H8 | -0.017% | -0.391% |
| H9 | -0.011% | -0.310% |
| H10 | -0.008% | -0.268% |

H2を除けばperiod=15から1への高速化によるruntime改善は0.5%未満であり、分子が大きいほど小さい。
standard period=15はlarge-H側で既にcritical pathを決めていない。

#### Cheap-RZ workloadのslow-supply側

period=15をstandard baselineとして、period=1、30、100を比較した。

| molecule | period 1 runtime | period 1 QV | period 30 runtime | period 30 QV | period 100 runtime | period 100 QV |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| H4 | -0.4569% | -0.3425% | +3.3959% | +2.1555% | +100.0751% | +71.4470% |
| H5 | -0.1731% | -0.1447% | +2.0182% | +1.3648% | +32.8849% | +24.3318% |
| H6 | -0.0899% | -0.0584% | +1.5340% | +1.0595% | +8.8394% | +6.0507% |
| H7 | -0.0437% | -0.0301% | +1.0398% | +0.7438% | +6.0958% | +4.3175% |

period=15から1への高速化は全分子で0.5%未満だが、15から30への低速化は+1.040%から+3.396%、
100への低速化は+6.096%から+100.075%となった。従ってstandard baselineより速いfactoryの追加価値は
小さい一方、十分に遅いfactoryは明確なruntime bottleneckになる。

period値はqret beat単位の生成周期であり、特定hardwareの物理時間を直接表すものではない。period=100
はsensitivity境界を調べるdiagnosticであり、現実的factory速度の主張ではない。

#### Factory countとgeneration periodの相互作用

factory countを4から3へ減らす効果をperiod=15と30で比較した。各molecule/precision内ではoptimized IRを
固定しており、countとperiodだけを変更している。

| precision | 3-factory penalty at period 15 | at period 30 | interaction |
| --- | ---: | ---: | ---: |
| `1e-5` | +11.124%から+13.382% | 約+33.333% | +19.951から+22.210 pp |
| `1e-2` | +0.318%から+1.125% | +0.715%から+2.193% | +0.398から+1.068 pp |

conventional workloadでは、factory数不足と供給低速化が同時に入るとworst beat-runtime penaltyが
+122.247%から+126.763%まで増えた。cheap-RZでは同じ組合せでも+1.763%から+5.664%だった。従って
factory countの感度は独立した定数ではなく、generation periodとmagic demandの組合せで決まる。
cheap-RZの4-factory/period-15はdata-side architecture探索用baselineとして十分な供給側にある。

## 7. Classical reaction time

reaction=1を基準に10、100へ増やした。回路、mapping、factory、magic supply、QEC入力は各
molecule/precision内で固定している。

### Conventional workload (`1e-5`)

| molecule | reaction 10 runtime | reaction 10 QV | reaction 100 runtime | reaction 100 QV |
| --- | ---: | ---: | ---: | ---: |
| H4 | +191.9565% | +162.2269% | +2112.7804% | +1790.8448% |
| H5 | +191.3372% | +165.2321% | +2105.0993% | +1821.9934% |
| H6 | +190.0332% | +166.3301% | +2090.6259% | +1834.2090% |
| H7 | +188.8494% | +168.2936% | +2077.4546% | +1853.2788% |

### Cheap-RZ workload (`1e-2`)

| molecule | reaction 10 runtime | reaction 10 QV | reaction 100 runtime | reaction 100 QV |
| --- | ---: | ---: | ---: | ---: |
| H4 | +61.2083% | +44.3277% | +685.5713% | +496.9503% |
| H5 | +42.6900% | +32.0481% | +472.0327% | +354.6010% |
| H6 | +18.9305% | +14.2096% | +211.2666% | +158.5199% |
| H7 | +13.4150% | +10.3015% | +148.6673% | +114.1552% |

reaction-timeは、ここまでにsingle-plane Dim2で見つかった最も強いruntime architecture parameterで
ある。追加1 reaction cycle当たりのruntime増分はfeedback depthから得られる予測にほぼ一致し、
serial feedback fractionは約0.979から1.000だった。現在の回路ではmeasurement feedbackがほぼ直列の
dependency pathへ入るためである。

ただしreaction=1/10/100はdiagnostic cycle countであり、特定のclassical controllerの実測値ではない。
またreaction増加でcode distanceが変わるcaseがあるため、QV増加にはruntime増加とQEC threshold
crossingの両方が含まれる。

## 8. Conventionalとcheap-RZの役割

`rotation_precision=1e-2`はSTARそのものではなく、arbitrary rotation synthesis costを下げた
diagnostic surrogateである。architecture sensitivityの使い分けは次のように整理できる。

| architecture要因 | cheap-RZでの感度変化 | 解釈 |
| --- | --- | --- |
| factory placement | QV spreadが縮小 | magic delivery需要と直接結合していた |
| factory count不足 | runtime penaltyが縮小 | magic demand自体が減った |
| magic stock不足 | runtime penaltyが縮小 | 必要stockが減った |
| routing choke | runtimeは依然小さいがQV penaltyは拡大 | data-side occupancyが相対的に見えやすい |
| reaction time | conventionalより相対penaltyは小さいが依然large | 残ったfeedback dependencyがcritical pathへ入る |
| slow magic period | 分子依存でmediumからlarge | supplyを十分遅くすれば再び律速になる |

従って「cheap-RZにすると全architecture差が大きくなる」ではない。需要を削減した対象に直接結び付く
factory-side要因は弱くなり、残存するdata-side/feedback要因が相対的に見えやすくなる場合がある。

precision間のruntime/QV差は、このレポートのarchitectureランキングから意図的に除外した。今後も
architecture比較は、各precision内でQASM hash、optimized IR hash、gate/magic/feedback demandが一致
することを確認して行う。

## 9. Distanceとruntime model

### 9.1 Current fixed-latency Dim2

qretのcurrent `sc_ls_fixed_v0`では、主なroute付き命令のbeat latencyがpath lengthに比例しない。

- `LATTICE_SURGERY`: latency 1
- `LATTICE_SURGERY_MAGIC`: latency 1
- `MOVE`: latency 1
- `CNOT`: latency 2

実装は[sc_ls_fixed_v0/instruction.h](../../third_party/quration/quration-core/src/qret/target/sc_ls_fixed_v0/instruction.h)
で確認できる。長いpathは同時に占有するancilla cellやrouting conflictを増やすが、その命令自身のlatencyを
直接増やさない。

このため、connected topologyでschedulerがconflictを他のdependencyの背後へ隠せる限り、distance増加は
QVへ現れやすく、runtimeへは現れにくい。runtimeが大きく変わるには、次のいずれかが必要になる。

1. factory supply、stock、egress、reactionのような待ちがcritical pathへ入る。
2. routing競合が隠蔽不能なほど強くなる。
3. path length自体にlatencyを持つ別machine modelを使う。
4. plane間entanglementのような明示的通信供給を導入する。

### 9.2 Distance-sensitive full-runtime diagnostic

path lengthをrouting、resource occupancy、dependency release、runtime、QVへ一貫して反映する診断patchを
一時buildへ適用した。追加latencyは次で定義した。

```text
base + ceil(numerator * max(path_coordinates - 1, 0) / denominator)
```

係数はfixed=`0/1`、quarter=`1/4`、half=`1/2`、unit=`1/1`である。まずH4/H7のunit係数でfull
rerouting runtimeを確認し、その後H4-H6、両precision、placement/routing family、3段階geometryへ
fractional係数を展開した。120 caseは全件成功し、QASM/optimized IR/gate/magic demandを各固定回路
group内で一致させた。

| family | quarter stress runtime | unit stress runtime | quarter stress QV | unit stress QV |
| --- | ---: | ---: | ---: | ---: |
| placement | +11.394%から+19.659% | +38.274%から+80.748% | +26.795%から+44.172% | +63.509%から+131.631% |
| routing | +1.397%から+7.982% | +7.460%から+27.796% | +5.591%から+22.967% | +17.672%から+61.400% |

nonfixed 28 groupすべてでreference、intermediate、stressのbeat runtimeとphysical runtimeが単調に
増加し、geometry側の静的metricも40/40 groupで単調だった。H4ではfixed、quarter、half、unitの係数
増加に対して全topologyのruntimeが単調に増えた。従って、distance感度はunit係数または単一分子だけの
現象ではない。

selected magic factory endpointがbusyなら待機する保守的制約もH4の18 caseで追加確認した。同一topology
runtime増加は最大+0.0508%、placement stress penaltyの変化は-0.0076から+0.0581 ppだった。この制約は
distance-sensitive placement差の主要因ではない。

### 9.3 Physical runtimeと校正範囲

このレポートのprimary runtimeはqretのbeat countである。current profile設定ではphysical runtimeを
次で換算する。

```text
physical_runtime = runtime_beats * code_distance * code_cycle_time
```

既存設定の`code_cycle_time=1 us`を使うと、1 beatはcode distance `d` code cycle、すなわち`d us`に
対応する。同一比較でcode distanceが固定ならphysical-runtime相対比はbeat-runtime相対比と一致する。
一方、QEC threshold crossingがあるcaseでは差が増幅する。例えばH6 `1e-5` placement quarterはbeat
runtimeが+15.239%だが、`d=15 -> 17`によりphysical runtimeは+30.604%となった。

この換算はrepository内modelの内部整合性を示すもので、1セル移動の追加latencyやfactory protocol速度を
実機から校正した結果ではない。quarter/half/unit係数からhardware上の絶対runtimeを主張してはならない。
定量的な実機予測には、1 path coordinateが何code cycleに相当するかを独立に定義する必要がある。

## 10. QV解釈上の注意

QVの相対差は、常に単一の原因を表すわけではない。

```text
QVの相対差に含まれ得る要因:
  runtime ratio
  average active-area / occupied cell-time ratio
  code-distance threshold crossing
  physical footprint definition
```

QVを概念的に`runtime * spatial resource`とみなす場合も、比は乗算であり、相対変化率が厳密に加算
できるわけではない。以下では、各sweepで固定できた要因に基づいて解釈する。

比較ごとの分離状態は次のとおりである。

| sweep | 同一group内のcode distance | QVの主な読み方 |
| --- | --- | --- |
| logical placement | 固定 | placement/occupancy効果を比較的きれいに反映 |
| routing choke | 固定 | path/occupancy効果を比較的きれいに反映 |
| magic stock | 固定 | stock waitとoccupancyの合成効果 |
| cheap magic period | 固定 | supply waitとoccupancyの合成効果 |
| factory saturation 4-8 | 固定 | delivery geometry/occupancyの推定が可能 |
| factory placement | H4 `1e-5`のみ不一致 | H4 conventionalはQEC効果が混在 |
| factory count 1-4 | 一部で変化 | supply効果とQEC効果を分離できないcaseあり |
| reaction time | 一部で変化 | feedback waitとQEC効果が混在 |
| fractional path latency | 一部で変化 | beat runtimeを主指標とし、physical runtime/QVではQEC変化を併記 |

runtime-primaryな結論にはbeat runtimeを使い、QVを原因分解する際はcode distance固定比較を優先する。

## 11. 現時点で支持される研究上の主張

### 観測から直接支持されること

1. current fixed-latency single-plane Dim2の通常connected geometryでは、factory/logical placement、
   grid shape、routing distanceを変えてもruntime差は概ね0.1%以下である。
2. 同じfixed-latency geometry変更でもQVは数%から約13%変わり得る。
3. distance-sensitive diagnosticではquarter係数でもplacement stressが+11.394%から+19.659%、routing
   stressが+1.397%から+7.982%となり、geometry段階に対する単調性が再現した。
4. accessible factory数を供給kneeより減らすとruntimeは10%から240%超増える。
5. 4 factoryを超える追加はH4-H6 runtimeを0.5%以上改善しない。
6. factory egressは0本と1本の間に約10%から12%のruntime thresholdを持つ。
7. stock=10000、period=15、4 factoryは、通常baselineとしてfast/sufficient側にある。
8. reaction timeはtested standard single-plane条件で最も強いruntime感度を示す。

### 観測に基づく推定

1. fixed-latency modelではplacement/path差がcritical pathよりoccupied cell-timeへ作用するため、runtime
   よりQVへ強く現れる。
2. conventional workloadのfactory placement差はmagic delivery geometryの寄与が大きい。
3. fixed instruction latencyがdistanceのruntime感度を弱くしているという説明は、full-runtime
   diagnosticの再現性によって支持される。
4. 4 factory以降のQV改善はnearest-source distanceとdelivery occupancy短縮に由来する可能性が高い。

### 未解決または未実装

1. 1 path coordinate当たりの追加latencyを物理的に校正したsingle-plane model。
2. realistic reaction time、cycle time、factory periodのhardware calibration。
3. individual routing waitをdependency critical pathへ帰属するtrace。
4. QVをdata、ancilla、magic delivery、factory occupancyへ分解する集計。
5. arbitrary-rotation resource stateを含むSTAR固有model。

## 12. 検証終了条件と残課題

主目的である「同一の合成済み回路を固定し、architecture条件だけでruntimeが大きく変わる条件があるか」
については、current qret modelとdistance-sensitive diagnosticの双方で必要な検証を完了した。通常配置、
供給、reaction、factory accessibility、grid threshold、routing capacity、距離依存latencyを相互に区別でき、
H4-H6と両precisionでfractional係数の再現性も確認した。この目的のために通常Dim2の配置組合せ、H7の
fractional case、factory/magic条件をさらに総当たりする必要はない。

今後の作業は次の3種類に分ける。

1. **物理的な増加率を主張する場合のみ必須:** 1 path coordinate、reaction、factory periodをcode cycleへ
   対応付ける根拠を定義し、その校正値で最小限の代表caseを再評価する。
2. **因果説明を強める場合の任意補強:** instruction種類別path length、routing wait、congestion、critical
   path contributionを代表caseでtraceする。これは主結論の成立条件ではない。
3. **実装上の保護:** topology preflightでaccessible factoryに最低1本のfree egressを要求し、zero-egress
   pathologyを通常grid効果と誤認しないようにする。

QV最適化はruntime探索とは別目的として扱う。magic生成成功確率を恣意的に下げる検証や、未校正係数を
さらに細分化するsweepは、hardware根拠がない限り追加architecture mechanismを示さないため実施しない。

## 13. 参照artifact

- [Initial H2-H11 topology sweep](../../artifacts/surface_code_topology_sweep_h2_h11_baseline_fast/results.md)
- [H4/H5 mapping diagnostics](../../artifacts/surface_code_mapping_diagnostics_h4_h5_4th_new2/summary.md)
- [Post-routing factory usage](../../artifacts/post_routing_magic_factory_usage_h4_h5/summary.md)
- [Factory placement x rotation precision](../../artifacts/surface_code_rotation_precision_topology_sweep_h4_h7_4th/summary.md)
- [Logical-qubit placement](../../artifacts/surface_code_logical_placement_sweep_h4_h7_4th/summary.md)
- [Grid capacity](../../artifacts/surface_code_grid_capacity_sweep_h4_h7_4th/summary.md)
- [Grid runtime threshold](../../artifacts/surface_code_runtime_grid_threshold_h5_h7_4th/summary.md)
- [H7 factory-egress micro-sweep](../../artifacts/surface_code_factory_egress_micro_sweep_h7_4th/summary.md)
- [H5/H6 factory-egress generalization](../../artifacts/surface_code_factory_egress_generalization_h5_h6_4th/summary.md)
- [Routing-capacity choke](../../artifacts/surface_code_routing_capacity_sweep_h4_h7_4th_paired/summary.md)
- [Accessible factory count, conventional](../../artifacts/surface_code_accessible_factory_count_sweep_h4_h7_4th/summary.md)
- [Accessible factory count, cheap-RZ](../../artifacts/surface_code_accessible_factory_count_sweep_h4_h7_4th_cheap_rz/summary.md)
- [Factory saturation above four](../../artifacts/surface_code_factory_saturation_sweep_h4_h6_4th_paired/summary.md)
- [Magic stock](../../artifacts/surface_code_magic_stock_sweep_h4_h6_4th_paired/summary.md)
- [Magic period, cheap-RZ](../../artifacts/surface_code_magic_period_sweep_h4_h7_4th_cheap_rz/summary.md)
- [Factory count x magic period](../../artifacts/surface_code_factory_period_interaction_sweep_h4_h7_4th_paired/summary.md)
- [Reaction time](../../artifacts/surface_code_reaction_time_sweep_h4_h7_4th_paired/summary.md)
- [Physical-runtime reanalysis](../../artifacts/surface_code_dim2_physical_runtime_reanalysis/summary.md)
- [Distance-sensitive critical-path proxy](../../artifacts/surface_code_distance_sensitive_latency_sweep_h4_h7_4th_paired/summary.md)
- [Distance-sensitive full runtime](../../artifacts/surface_code_distance_sensitive_runtime_sweep_h4_h7_4th_paired/summary.md)
- [Fractional path-latency sensitivity](../../artifacts/surface_code_fractional_path_latency_sweep_h4_h6_4th_paired/summary.md)
- [Factory endpoint busy probe](../../artifacts/surface_code_magic_factory_busy_probe_h4_4th_paired/summary.md)
- [Chronological architecture research log](architecture_research_log.md)
