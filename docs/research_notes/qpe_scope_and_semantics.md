# QPE scope and semantics

このファイルは研究日誌ではなく、QPE-scale resource estimate の scope と用語を揃えるための基準メモである。

## 標準対象

標準対象は `efficient_controlled_pf_one_step` である。

これは QPE で使う controlled product-formula time-evolution kernel の one-step compile/profile 対象であり、full QPE compile ではない。

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

- 2026-07-07: 初版。既存 topology sweep と architecture sensitivity note の意味論を分離して整理。
