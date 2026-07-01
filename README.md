# Evaluation Grouped Surface Code

H-chain grouped Hamiltonian の product-formula 回路を対象に、quration / qret の surface-code compile による資源見積もりを行うためのリポジトリです。

主目的は、固定した 1 Trotter step 回路に対して architecture 条件を変え、topology-aware な実行時間、chip cell 数、qubit volume、physical qubit 数、code distance などを比較できる状態にすることです。

## 対象範囲

現在の compile 対象は以下です。

- H-chain grouped Hamiltonian
- deterministic 2nd PF
- optimized 4th PF: `4th(new_2)`
- uncontrolled な 1 Trotter step 回路
- 明示的に選択した場合の single controlled product-formula time-evolution block
- quration の `SC_LS_FIXED_V0` compile
- topology-aware routing
- QEC resource estimation pass
- 1 step 結果に基づく QPE-scale の線形外挿

QPE-scale の出力は、PF 誤差係数から action count を見積もり、1 step の runtime / qubit volume / magic-state 数などを線形に掛けたものです。現時点では full QPE 回路を compile しているわけではありません。

デフォルトの回路 scope は引き続き `uncontrolled_pf_one_step` です。controlled block は明示的に `controlled_pf_time_evolution_block` を選択した場合だけ生成されます。

controlled block は、1 つの非負整数 `k` を指定して次を compile します。

```text
C-U_PF(t_k),  t_k = 2^k t
```

ここで `t` は既存の `surface_code_step_time()` で求める base step time です。`U_PF(t_k)` は product-formula 生成へ時間 `t_k` を渡した 1 つの PF sequence であり、`[U_PF(t)]^(2^k)` の反復回路ではありません。各実行では 1 つの `k` だけを compile します。

controlled block に含まれるものは、system logical qubits、最後の index に置く control logical qubit 1 個、controlled product-formula time-evolution です。Hadamard、QPE 位相レジスタ全体、複数の controlled block、inverse QFT、measurement、feed-forward、固有状態準備、追加 work ancilla は含みません。logical qubit 数は常に `system qubits + 1 control qubit` です。

controlled block では Hamiltonian の恒等項を global phase として捨てません。Jordan-Wigner 後または実際の grouped operator に含まれる identity coefficient を product-formula の係数列に沿って集計し、control qubit 上の phase gate として保持します。これにより control=0 branch と control=1 branch の相対位相を保ちます。uncontrolled 1 step の既存挙動は変えていません。

現段階では以下は対象外です。

- DF Hamiltonian
- QPE ancilla、inverse QFT、測定などを含む full QPE 回路の compile
- QPE 反復を明示的に展開した回路の compile
- step 間の factory stock や測定フィードバックを含む QPE 全体の動的評価

controlled block の compile 結果は single controlled PF time-evolution block の実測であり、QPE 全体の resource estimate ではありません。controlled scope では architecture sweep の QPE linear extrapolation total fields は `N/A` として扱います。

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

controlled block を明示的に compile する例です。

```bash
PYTHONPATH=src python - <<'PY'
from trotterlib import SurfaceCodeArchitecture, compile_grouped_hchain_controlled_block

metrics = compile_grouped_hchain_controlled_block(
    2,
    "2nd",
    qpe_power_k=0,
    architecture=SurfaceCodeArchitecture(compile_mode="ftqc_compile"),
)
for key in (
    "compiled_circuit_scope",
    "qpe_power_k",
    "time_multiplier",
    "base_step_time",
    "effective_evolution_time",
    "num_system_qubits",
    "num_control_qubits",
    "num_logical_qubits",
    "step_rz_count",
    "step_rz_depth",
):
    print(f"{key}: {metrics.get(key)}")
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

controlled block を architecture sweep で選択する例です。省略時は uncontrolled です。

```yaml
defaults:
  circuit_scope: controlled_pf_time_evolution_block
  qpe_power_k: 0

architecture_cases:
  - name: controlled_h2_k0
    compile_mode: ftqc_compile
    circuit_scope: controlled_pf_time_evolution_block
    qpe_power_k: 0
```

controlled 行の出力では `compiled_circuit_scope`、`qpe_power_k`、`time_multiplier`、`base_step_time`、`effective_evolution_time`、`num_system_qubits`、`num_control_qubits` が設定され、QPE 全体への線形外挿 field は `N/A` になります。

## Profiling

prepare / compile の stage 別 elapsed、Python parent RSS、qret subprocess RSS、入出力サイズは、以下のレポートにまとめます。

- [Surface-Code Stage Profiling Report](docs/benchmarks/profiling_report.md)
- [Surface-Code RSS Memory Profile](docs/benchmarks/rss_memory_profile_report.md)

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

prepared step artifact の cache key には、回路 scope、`qpe_power_k`、effective evolution time、control qubit 数、qret executable/core library hash、積分 cache identity、積分値 hash、RZ helper mode、IR 処理 version、QASM 分解設定に加えて、回路生成 schema version と主要依存パッケージ version を含めています。これにより、controlled/uncontrolled/k 間の衝突や、Qiskit / OpenFermion などの変更後の古い prepared artifact 誤再利用を避けています。

ただし、回路生成ロジックを変更した場合は、対応する version 定数を更新してください。
