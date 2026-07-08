# QPE scope and semantics

このファイルは研究日誌ではなく、QPE-scale resource estimate の scope と用語を揃えるための基準メモである。

## 標準対象

標準対象は `efficient_controlled_pf_one_step` である。

これは QPE で使う controlled product-formula time-evolution kernel の one-step compile/profile 対象であり、full QPE compile ではない。

## controlled 化の実装詳細

標準評価で使う controlled 化は、generic な「system PF circuit 全体を
controlled gate 化する」方式ではなく、各 Pauli rotation の中央の
controlled-RZ だけに control qubit を関与させる方式である。

標準 scope は次である。

```text
efficient_controlled_pf_one_step
```

この scope では `qpe_power_k=0` の one-step block だけを扱う。各 Pauli
rotation は概念的に次の形で合成する。

```text
system basis change
system parity compute
controlled-RZ
system parity uncompute
system basis change back
```

system-only な basis change、parity CNOT、uncompute まで control するわけではない。
したがって、QPE-scale total に掛ける one-step cost は、この efficient controlled
one-step の compile/profile result を基準にする。

control qubit は system logical qubits の末尾に 1 個追加する。

```text
num_logical_qubits = num_system_qubits + 1
control_qubit_index = num_system_qubits
```

これは QPE phase register ではなく、controlled time-evolution kernel を評価するための
単一 control qubit である。

比較用に、次の generic controlled baseline も存在する。

```text
controlled_pf_time_evolution_block
```

これは

```text
C-U_PF(t_k),  t_k = 2^k t
```

を作る diagnostic / correctness baseline である。実装上は、system PF circuit を
`effective_evolution_time = t_k` で 1 回生成し、それを `to_gate().control(1)` で
まとめて controlled gate 化する。これは `[U_PF(t)]^(2^k)` を明示反復する実装ではない。

generic controlled baseline では、Pauli rotation 中央の RZ だけでなく、basis change、
parity compute、uncompute などの system-only Clifford scaffolding も controlled gate
の内側に入る。そのため、標準の QPE-scale resource estimate に使う one-step cost としては
過大評価になりやすい。この baseline の結果を `qpe_action_count` で単純に掛けた値を
標準結果として扱ってはならない。

controlled evolution では、Hamiltonian の identity term を単なる global phase として
捨てない。uncontrolled evolution では global phase になる項でも、controlled evolution
では control=0 branch と control=1 branch の相対位相になるためである。

identity phase は product-formula の係数列に沿って次のように集計する。

```text
theta = -sum_j w_j * c_identity,j * t_k
```

この `theta` は control qubit 上の phase gate として実装する。`efficient_controlled_pf_one_step`
では `t_k=t` である。これにより、final circuit の global phase が正規化されても、
control branch 間の相対位相は実ゲートとして保持される。

実装詳細、API 名、cache metadata、smoke test の結果は
`docs/benchmarks/controlled_pf_block_implementation_report.md` を参照する。

## full QPE ではないもの

標準評価には次を含めない。

- QPE phase register
- inverse QFT
- measurement
- feed-forward
- repeated QPE circuit
- QPE 反復回路の明示展開

したがって、標準の architecture sweep 結果を「full QPE compile result」と表現してはならない。

## QPE-scale total の意味

QPE-scale total は、one-step result に action count を掛けた線形外挿である。

区別すべきものは次である。

- observed one-step compile/profile result
- estimated QPE-scale extrapolation
- unimplemented full-QPE compile result

`runtime`, `qubit_volume`, `magic-state count` などの total field は、対象 row が `efficient_controlled_pf_one_step` のときに QPE-scale estimate として扱う。

## diagnostic regime の扱い

`fast_supply`、`cheap_p1`、`cheap_p1_large_stock` などは、architecture sensitivity
を見るための diagnostic condition である。

`cheap_p1` や `cheap_p1_large_stock` は STAR-like cheap magic assumption を意識した
条件だが、STAR architecture そのものを実装・評価した結果ではない。

diagnostic condition は production adopted な標準条件と区別する。特に cheap magic
condition で得た傾向を、標準 architecture result や STAR architecture result として
表現してはならない。

## architecture sweep の意味論

architecture sweep では logical circuit を変えない。

architecture case 間で次が変わる場合、それは architecture effect ではなく circuit-generation change として扱う。

- Hamiltonian
- grouping
- PF order
- target error
- rotation precision
- circuit scope
- controlled / uncontrolled synthesis scope

architecture effect を主張する場合は、同一 molecule / 同一 PF / 同一 logical circuit / 同一 non-architecture condition が揃っていることを確認する。

## 更新履歴

- 2026-07-08: diagnostic regime の扱いを追記。
- 2026-07-08: controlled 化の実装詳細、generic controlled baseline と efficient controlled one-step の区別、identity phase の扱いを追記。
- 2026-07-07: 初版。既存 topology sweep と architecture sensitivity note の意味論を分離して整理。
