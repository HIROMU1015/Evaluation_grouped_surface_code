# Artifact Directory Guide

`artifacts/` には、GitHub で共有する研究結果と、ローカルで再生成できる
cache / profile run が共存しています。この README を入口として、名前だけでは
用途を判断しにくいディレクトリを区別します。

## 区分

### Published results

Git 管理する成果物です。原則として、結論を確認できる最小限のファイルだけを
残します。

- architecture sweep: `surface_code_topology_sweep_*`,
  `surface_code_magic_supply_*`, `surface_code_rotation_precision_sweep_*`,
  `surface_code_grid_capacity_sweep_*`
- mapping / factory diagnostics: `surface_code_mapping_diagnostics_*`,
  `surface_code_factory_*`, `post_routing_*`
- compact experiment summaries: `surface_code_experiment_summaries/`,
  `surface_code_timing/`
- chemistry inputs and fitted coefficients: `df_*`, `trotter_expo_coeff_*`
- external diagnosis bundles: `surface_code_share/`

公開 sweep は、基本的に以下の 3 形式を 1 組として扱います。

- `results.md`: 人が読む要約
- `results.csv`: 表計算・集計用
- `results.jsonl`: 全フィールドを保持する機械処理用

raw cache、プロセスごとの一時ファイル、再現可能な巨大 IR は公開結果へ含めません。

### Local generated data

`.gitignore` 対象で、必要なら再生成できる作業領域です。

- `surface_code_cache/`: prepared step、integral、RZ helper、qret compile cache
- `qret_*_memory/`, `qret_*_scaling/`, `qret_*_optimization_*`: profiler の raw run
- `surface_code_process_isolation/`, `surface_code_parent_memory/`: memory 計測の raw run
- `surface_code_basis_decompose_ab/`, `h*_memory_speed_audit/`,
  `h*_compile_trial/`: 個別調査の中間生成物

これらは GitHub には送られません。削除すると再実行時間が増えるため、容量確保時は
実行中プロセスがないことと、対応する要約が `docs/benchmarks/` または Published
results に残っていることを確認してから対象単位で削除します。

## Current size snapshot

2026-07-11 時点では、`artifacts/` 全体が約 92 GiB、Git 管理対象は約 117 MiB です。
大半は `surface_code_cache/` の約 84 GiB で、そのうち `gr/prepared_step/` が約
73 GiB を占めます。したがって、Git 管理ファイルを細かく削るより、不要になった
prepared step cache を case 単位で整理する方が容量には効きます。

最新の内訳は次のコマンドで確認できます。ファイル内容は読み込まず、逐次走査するため、
大きなメモリを消費しません。

```bash
python scripts/artifact_inventory.py
python scripts/artifact_inventory.py --all
python scripts/artifact_inventory.py --json
```

表示上の区分は次の通りです。

- `published`: その直下ディレクトリに Git 管理対象ファイルがある
- `local`: 直下ディレクトリ全体が `.gitignore` 対象
- `untracked`: Git 管理も ignore もされておらず、整理判断が必要

## Retention rules

新しい検証では次のルールを使います。

1. 1 検証につき 1 ディレクトリとし、名前に対象と比較軸を含める。
2. Git には要約、表、再現条件、解釈に必要な diagnostics だけを追加する。
3. cache、raw logs、PID、lock、巨大な中間 IR/QASM は `.gitignore` 対象にする。
4. archive と展開済み bundle の二重保存は、外部共有に必要な場合だけ許容する。
5. 100 MiB を超える新規ファイルは、追加前に GitHub で保持する必要性を確認する。
