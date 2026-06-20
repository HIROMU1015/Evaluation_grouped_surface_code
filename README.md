# Evaluation Grouped Surface Code

H-chain grouped Hamiltonian の Trotter 回路を対象に、quration / surface-code compile による資源見積もりを行うためのリポジトリです。

現段階の主目的は、固定した 1 Trotter step 回路に対して architecture 条件を変え、topology-aware な実行時間、chip cell 数、qubit volume、physical qubit 数などを比較できる状態にすることです。

## 対象範囲

- H-chain grouped Hamiltonian
- deterministic 2nd PF
- optimized 4th PF: `4th(new_2)`
- 1 Trotter step
- uncontrolled time-evolution 回路
- quration の `SC_LS_FIXED_V0` compile
- topology-aware routing
- QEC resource estimation pass

現段階では以下は対象外です。

- DF Hamiltonian
- full QPE 回路の明示的な compile
- controlled-U を含む QPE step compile
- QPE 全体への資源外挿

## 構成

- `src/trotterlib/surface_code.py`
  - grouped H-chain 回路生成
  - quration 用 pipeline YAML 生成
  - OpenQASM2 export
  - qret parse / opt / compile 実行
  - `compile_info.json` からの metrics 抽出
- `src/trotterlib/config.py`
  - default target error
  - product formula 設定
  - quration binary / topology path
  - surface-code architecture default
- `src/trotterlib/cost_extrapolation.py`
  - 互換用の薄い入口
- `artifacts/trotter_expo_coeff_gr*`
  - grouped Hamiltonian の既存 PF 誤差係数 artifact

## quration 依存

quration 本体はこのリポジトリには含めません。

デフォルトでは、同じ親ディレクトリにある quration を探します。

```bash
/home/abe/Project/quration/build/main/qret
/home/abe/Project/quration/quration-core/examples/data/topology/tutorial.yaml
```

別の場所を使う場合は `QURATION_ROOT` を指定します。

```bash
export QURATION_ROOT=/path/to/quration
```

または Python 側で `SurfaceCodeArchitecture` に `qret_path` と `topology_path` を渡します。

## セットアップ

```bash
cd /home/abe/Project/Evaluation_grouped_surface_code
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

既存の作業環境を使う場合は、`PYTHONPATH=src` を付けて実行できます。

## Smoke Test

H3 grouped Hamiltonian の 1 Trotter step を、topology-aware + QEC resource estimation で compile します。

```bash
PYTHONPATH=src python - <<'PY'
from trotterlib import SurfaceCodeArchitecture, compile_grouped_hchain_step

for pf in ("2nd", "4th(new_2)"):
    metrics = compile_grouped_hchain_step(
        3,
        pf,
        architecture=SurfaceCodeArchitecture(),
    )
    print(pf)
    for key in (
        "magic_state_consumption_count",
        "magic_state_consumption_depth",
        "runtime_without_topology",
        "runtime",
        "chip_cell_count",
        "qubit_volume",
        "code_distance",
        "num_physical_qubits",
    ):
        print(f"  {key}: {metrics.get(key)}")
PY
```

ローカル環境では、以下を確認済みです。

- H3 `2nd`
  - `chip_cell_count = 96`
  - `qubit_volume = 424144`
  - `num_physical_qubits = 23232`
- H3 `4th(new_2)`
  - `chip_cell_count = 96`
  - `qubit_volume = 1847043`
  - `num_physical_qubits = 32448`

## 実行結果

quration の中間ファイルと `compile_info.json` は以下に保存されます。

```text
artifacts/surface_code_cache/
```

このディレクトリは `.gitignore` 対象です。比較や図作成に使う要約結果は、今後 `results/` などに別途保存する想定です。

## Architecture 設定

`SurfaceCodeArchitecture` で compile 条件を変更できます。

```python
from pathlib import Path
from trotterlib import SurfaceCodeArchitecture

arch = SurfaceCodeArchitecture(
    compile_mode="ftqc_compile_topology_qec",
    topology_path=Path("/path/to/topology.yaml"),
    magic_generation_period=15,
    maximum_magic_state_stock=10000,
    entanglement_generation_period=100,
    maximum_entangled_state_stock=10,
    reaction_time=1,
    physical_error_rate=1.0e-3,
    drop_rate=0.1,
    code_cycle_time_sec=1.0e-6,
    allowed_failure_prob=1.0e-2,
)
```

主に sweep したい値は以下です。

- topology
- magic-state factory の数・配置
- magic-state generation period
- magic-state stock 上限
- reaction time
- entangled-state generation period
- QEC 条件

## Artifact について

初期移行では、元リポジトリで commit 済みの artifact を一旦そのまま移しています。そのため、解析対象外の DF 関連 artifact も一部含まれています。

コード側では DF Hamiltonian 用の実装は移していません。今後、必要に応じて artifact も grouped / surface-code 用に整理します。
