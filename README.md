# Evaluation Grouped Surface Code

H-chain grouped Hamiltonian の product-formula 回路を対象に、quration / qret の surface-code compile による資源見積もりを行うためのリポジトリです。

主目的は、固定した 1 Trotter step 回路に対して architecture 条件を変え、topology-aware な実行時間、chip cell 数、qubit volume、physical qubit 数、code distance などを比較できる状態にすることです。

## 対象範囲

現在の compile 対象は以下です。

- H-chain grouped Hamiltonian
- deterministic 2nd PF
- optimized 4th PF: `4th(new_2)`
- uncontrolled な 1 Trotter step 回路
- quration の `SC_LS_FIXED_V0` compile
- topology-aware routing
- QEC resource estimation pass
- 1 step 結果に基づく QPE-scale の線形外挿

QPE-scale の出力は、PF 誤差係数から action count を見積もり、1 step の runtime / qubit volume / magic-state 数などを線形に掛けたものです。現時点では full QPE 回路を compile しているわけではありません。

現段階では以下は対象外です。

- DF Hamiltonian
- QPE ancilla、controlled-U、inverse QFT、測定などを含む full QPE 回路の compile
- QPE 反復を明示的に展開した回路の compile
- step 間の factory stock や測定フィードバックを含む QPE 全体の動的評価

将来的には ancilla や controlled-U を含む QPE 回路を扱う可能性があります。ただし、QPE の反復まで回路として展開するか、1 回路ブロックを別途スケールするかは未定です。

## H-chain の物理条件

`grouped_hchain_ham_name()` では、偶数長と奇数長で異なる電子状態を使います。

- 偶数長 H-chain: neutral singlet, `charge_0`
- 奇数長 H-chain: triplet `1+`, `charge_1`

そのため、H2, H3, H4, ... を横並びにするときは、単純な neutral H-chain の原子数スケーリングではない点に注意してください。

## 構成

- `src/trotterlib/surface_code.py`
  - grouped H-chain 回路生成
  - OpenQASM2 export
  - qret parse / opt / compile 実行
  - RZ helper cache、integral cache、prepared step cache
  - `compile_info.json` からの metrics 抽出
- `src/trotterlib/architecture_sweep.py`
  - molecule / PF / architecture 条件の sweep
  - JSONL / CSV / Markdown 出力
  - 1 step 結果からの QPE-scale 線形外挿
- `src/trotterlib/config.py`
  - default target error
  - product formula 設定
  - vendored qret / topology path
  - surface-code architecture default
- `scripts/build_qret.sh`
  - vendored quration から `build/quration/qret` を生成
- `third_party/quration`
  - Evaluation 内で確認・ビルドする quration / qret ソース
- `artifacts/trotter_expo_coeff_gr*`
  - grouped Hamiltonian の既存 PF 誤差係数 artifact

## quration / qret 依存

quration / qret のソースは `third_party/quration` に同梱しています。qret binary は生成物なので commit せず、必要に応じて Evaluation リポジトリ内でビルドします。

```bash
./scripts/build_qret.sh
```

デフォルトの qret 実行ファイルは以下です。

```text
build/quration/qret
```

デフォルトの topology は vendored quration の tutorial topology です。

```text
third_party/quration/quration-core/examples/data/topology/tutorial.yaml
```

別の qret や topology を使う場合は、環境変数または `SurfaceCodeArchitecture` で明示します。

```bash
export QRET_PATH=/path/to/qret
export SURFACE_CODE_TOPOLOGY_PATH=/path/to/topology.yaml
```

`gridsynth` は変更対象ではないため、このリポジトリには同梱していません。必要なら以下で指定してください。

```bash
export GRIDSYNTH_PATH=/path/to/gridsynth
```

未指定の場合は、`externals/bin/gridsynth` や既存のローカル quration checkout 内の `externals/bin/gridsynth` を探索します。

## セットアップ

```bash
cd /home/abe/Project/Evaluation_grouped_surface_code
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./scripts/build_qret.sh
```

既存の作業環境を使う場合は、`PYTHONPATH=src` を付けて実行できます。

## Smoke Test

H3 grouped Hamiltonian の 1 Trotter step を topology-aware + QEC resource estimation で compile します。

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

## Architecture Sweep

標準設定は以下です。

```bash
PYTHONPATH=src python -m trotterlib.architecture_sweep \
  configs/surface_code_architecture_sweep.yaml
```

`configs/surface_code_architecture_sweep.yaml` の default は `ftqc_compile_topology_qec` です。これにより、physical qubits、code distance、failure probability などの QEC 依存指標を標準出力に含めます。

routing / topology の比較だけを軽く行う場合は、local config または個別 case で `compile_mode: ftqc_compile_topology` に変更してください。その場合、QEC 依存指標は `N/A` になります。

結果は以下へ出力されます。

```text
artifacts/surface_code_architecture_sweep/
```

Markdown の QPE-scale 表は、full QPE circuit compile ではなく、uncontrolled PF 1 step からの線形外挿です。

## Profiling

prepare / compile の stage 別 elapsed、Python parent RSS、qret subprocess RSS、入出力サイズは、以下のレポートにまとめます。

- [Surface-Code Stage Profiling Report](docs/benchmarks/profiling_report.md)

ローカルで再測定する場合は、以下を使います。生成される `benchmark_results/` は `.gitignore` 対象です。

```bash
PYTHONPATH=src python scripts/profile_surface_code_stages.py \
  --case H2:2nd \
  --case 'H2:4th(new_2)' \
  --compile-mode ftqc_compile_topology \
  --cache-condition current-cache-state \
  --batch-size 2
```

## Cache と Artifact

qret の中間ファイル、prepared step、integral cache、RZ helper cache、compile 結果は以下に保存されます。

```text
artifacts/surface_code_cache/
```

このディレクトリは `.gitignore` 対象です。

prepared step artifact の cache key には、qret hash、積分 cache identity、積分値 hash、RZ helper mode、IR 処理 version、QASM 分解設定に加えて、回路生成 schema version と主要依存パッケージ version を含めています。これにより、Qiskit / OpenFermion などの変更後に古い prepared artifact を誤再利用しにくくしています。

ただし、回路生成ロジックを変更した場合は、対応する version 定数を更新してください。
