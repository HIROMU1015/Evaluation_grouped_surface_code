from __future__ import annotations

import hashlib
import json
import math
import os
import re
import resource
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

import numpy as np

from .config import (
    BETA,
    DEFAULT_BASIS,
    DEFAULT_DISTANCE,
    DECOMPO_NUM,
    PFLabel,
    PF_RZ_LAYER,
    P_DIR,
    SURFACE_CODE_CACHE_DIR,
    SURFACE_CODE_COMPILE_MODE,
    SURFACE_CODE_COMPILE_SKIP_OUTPUT,
    SURFACE_CODE_COMPILE_SKIP_REDUNDANT_IR_PREPROCESS,
    SURFACE_CODE_ENTANGLEMENT_GENERATION_PERIOD,
    SURFACE_CODE_FIXED_ROTATION_PRECISION,
    SURFACE_CODE_GRIDSYNTH_PATH,
    SURFACE_CODE_MACHINE_TYPE,
    SURFACE_CODE_MAGIC_GENERATION_PERIOD,
    SURFACE_CODE_MAX_ENTANGLED_STATE_STOCK,
    SURFACE_CODE_MAX_MAGIC_STATE_STOCK,
    SURFACE_CODE_QASM_BASIS_GATES,
    SURFACE_CODE_QASM_DECOMPOSE_REPS,
    SURFACE_CODE_QCSF_PATH,
    SURFACE_CODE_QEC_ALLOWED_FAILURE_PROB,
    SURFACE_CODE_QEC_CODE_CYCLE_TIME_SECONDS,
    SURFACE_CODE_QEC_DROP_RATE,
    SURFACE_CODE_QEC_PHYSICAL_ERROR_RATE,
    SURFACE_CODE_REACTION_TIME,
    SURFACE_CODE_RZ_CALL_CACHE,
    SURFACE_CODE_RZ_CALL_CACHE_ROUND_DIGITS,
    SURFACE_CODE_SAVE_MAPPING_RESULT,
    SURFACE_CODE_ROTATION_ERROR_BUDGET_FRACTION,
    SURFACE_CODE_ROTATION_PRECISION_FLOOR,
    SURFACE_CODE_ROTATION_PRECISION_MODE,
    SURFACE_CODE_TOPOLOGY_PATH,
    TARGET_ERROR,
    normalize_pf_label,
)
from .io_cache import load_data


@dataclass(frozen=True)
class SurfaceCodeArchitecture:
    name: str = "default"
    compile_mode: str = SURFACE_CODE_COMPILE_MODE
    qret_path: Path = field(default_factory=lambda: Path(SURFACE_CODE_QCSF_PATH))
    topology_path: Path = field(default_factory=lambda: Path(SURFACE_CODE_TOPOLOGY_PATH))
    machine_type: str = SURFACE_CODE_MACHINE_TYPE
    magic_generation_period: int = SURFACE_CODE_MAGIC_GENERATION_PERIOD
    maximum_magic_state_stock: int = SURFACE_CODE_MAX_MAGIC_STATE_STOCK
    entanglement_generation_period: int = SURFACE_CODE_ENTANGLEMENT_GENERATION_PERIOD
    maximum_entangled_state_stock: int = SURFACE_CODE_MAX_ENTANGLED_STATE_STOCK
    reaction_time: int = SURFACE_CODE_REACTION_TIME
    physical_error_rate: float = SURFACE_CODE_QEC_PHYSICAL_ERROR_RATE
    drop_rate: float = SURFACE_CODE_QEC_DROP_RATE
    code_cycle_time_sec: float = SURFACE_CODE_QEC_CODE_CYCLE_TIME_SECONDS
    allowed_failure_prob: float = SURFACE_CODE_QEC_ALLOWED_FAILURE_PROB
    skip_compile_output: bool = SURFACE_CODE_COMPILE_SKIP_OUTPUT
    save_mapping_result: bool = SURFACE_CODE_SAVE_MAPPING_RESULT

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "compile_mode": self.compile_mode,
            "qret_path": str(Path(self.qret_path).expanduser()),
            "topology_path": str(Path(self.topology_path).expanduser()),
            "machine_type": self.machine_type,
            "magic_generation_period": int(self.magic_generation_period),
            "maximum_magic_state_stock": int(self.maximum_magic_state_stock),
            "entanglement_generation_period": int(self.entanglement_generation_period),
            "maximum_entangled_state_stock": int(self.maximum_entangled_state_stock),
            "reaction_time": int(self.reaction_time),
            "physical_error_rate": float(self.physical_error_rate),
            "drop_rate": float(self.drop_rate),
            "code_cycle_time_sec": float(self.code_cycle_time_sec),
            "allowed_failure_prob": float(self.allowed_failure_prob),
            "skip_compile_output": bool(self.skip_compile_output),
            "save_mapping_result": bool(self.save_mapping_result),
        }

    def cache_tag(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


SurfaceCodeArchitectureConfig = SurfaceCodeArchitecture


@dataclass(frozen=True)
class SurfaceCodeStepArtifact:
    ham_name: str
    molecule: str
    num_logical_qubits: int
    pf_label: PFLabel
    target_error: float
    step_time: float
    rotation_precision: float
    runtime_root: Path
    qasm_path: Path
    ir_path: Path
    optimized_ir_path: Path
    qasm_hash: str
    optimized_ir_hash: str
    qret_path: Path
    qret_hash: str
    step_rz_count: int
    step_rz_layer: int | None
    step_magic_state_count: int
    step_magic_state_depth: int
    peak_magic_layer: int
    instruction_count: int
    gate_depth: int
    rz_call_cache: dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ham_name": self.ham_name,
            "molecule": self.molecule,
            "num_logical_qubits": int(self.num_logical_qubits),
            "pf_label": self.pf_label,
            "target_error": float(self.target_error),
            "step_time": float(self.step_time),
            "rotation_precision": float(self.rotation_precision),
            "runtime_root": str(self.runtime_root),
            "qasm_path": str(self.qasm_path),
            "ir_path": str(self.ir_path),
            "optimized_ir_path": str(self.optimized_ir_path),
            "qasm_hash": self.qasm_hash,
            "optimized_ir_hash": self.optimized_ir_hash,
            "qret_path": str(self.qret_path),
            "qret_hash": self.qret_hash,
            "step_rz_count": int(self.step_rz_count),
            "step_rz_layer": self.step_rz_layer,
            "step_magic_state_count": int(self.step_magic_state_count),
            "step_magic_state_depth": int(self.step_magic_state_depth),
            "peak_magic_layer": int(self.peak_magic_layer),
            "instruction_count": int(self.instruction_count),
            "gate_depth": int(self.gate_depth),
            "rz_call_cache": dict(self.rz_call_cache),
        }


def surface_code_step_artifact_from_dict(payload: Mapping[str, Any]) -> SurfaceCodeStepArtifact:
    return SurfaceCodeStepArtifact(
        ham_name=str(payload["ham_name"]),
        molecule=str(payload["molecule"]),
        num_logical_qubits=int(payload["num_logical_qubits"]),
        pf_label=str(payload["pf_label"]),
        target_error=float(payload["target_error"]),
        step_time=float(payload["step_time"]),
        rotation_precision=float(payload["rotation_precision"]),
        runtime_root=Path(payload["runtime_root"]).expanduser(),
        qasm_path=Path(payload["qasm_path"]).expanduser(),
        ir_path=Path(payload["ir_path"]).expanduser(),
        optimized_ir_path=Path(payload["optimized_ir_path"]).expanduser(),
        qasm_hash=str(payload["qasm_hash"]),
        optimized_ir_hash=str(payload["optimized_ir_hash"]),
        qret_path=Path(payload["qret_path"]).expanduser(),
        qret_hash=str(payload["qret_hash"]),
        step_rz_count=int(payload["step_rz_count"]),
        step_rz_layer=(
            None if payload.get("step_rz_layer") is None else int(payload["step_rz_layer"])
        ),
        step_magic_state_count=int(payload["step_magic_state_count"]),
        step_magic_state_depth=int(payload["step_magic_state_depth"]),
        peak_magic_layer=int(payload["peak_magic_layer"]),
        instruction_count=int(payload["instruction_count"]),
        gate_depth=int(payload["gate_depth"]),
        rz_call_cache=dict(payload.get("rz_call_cache") or {}),
    )


def load_prepared_surface_code_step_artifact(
    runtime_root: str | Path,
) -> SurfaceCodeStepArtifact | None:
    root = Path(runtime_root).expanduser()
    metadata_path = root / "step_artifact.json"
    opt_path = root / "step_opt.json"
    if not metadata_path.exists() or not opt_path.exists():
        return None
    with metadata_path.open("r", encoding="utf-8") as f:
        artifact = surface_code_step_artifact_from_dict(json.load(f))
    if not Path(artifact.optimized_ir_path).expanduser().exists():
        return None
    if file_sha256(artifact.optimized_ir_path) != artifact.optimized_ir_hash:
        return None
    return artifact


def file_sha256(path: str | Path) -> str:
    resolved = Path(path).expanduser().resolve()
    digest = hashlib.sha256()
    with resolved.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_temp_path(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    os.close(fd)
    return Path(tmp_name)


def _atomic_write_json(path: Path, payload: Any, *, indent: int | None = 2) -> None:
    tmp_path = _atomic_temp_path(path)
    try:
        with tmp_path.open("w", encoding="utf-8") as f:
            if indent is None:
                json.dump(payload, f, ensure_ascii=True, separators=(",", ":"))
            else:
                json.dump(payload, f, ensure_ascii=True, indent=indent)
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


_PREPARE_STAGE_METRICS_VERSION = "surface_code_prepare_stage_metrics_v1"
_GNU_TIME_MAXRSS_RE = re.compile(
    r"Maximum resident set size \(kbytes\):\s*(?P<rss>\d+)"
)


def _resource_rss_snapshot() -> dict[str, int]:
    self_usage = resource.getrusage(resource.RUSAGE_SELF)
    child_usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {
        "self_maxrss_kb": int(self_usage.ru_maxrss),
        "children_maxrss_kb": int(child_usage.ru_maxrss),
    }


def _file_size_bytes(path: str | Path | None) -> int | None:
    if path is None:
        return None
    try:
        return int(Path(path).expanduser().stat().st_size)
    except FileNotFoundError:
        return None


def _existing_file_sizes(paths: Mapping[str, str | Path | None]) -> dict[str, int]:
    sizes: dict[str, int] = {}
    for key, path in paths.items():
        size = _file_size_bytes(path)
        if size is not None:
            sizes[str(key)] = size
    return sizes


def _parse_gnu_time_maxrss_kb(stderr_text: str) -> int | None:
    matches = list(_GNU_TIME_MAXRSS_RE.finditer(stderr_text))
    if not matches:
        return None
    return int(matches[-1].group("rss"))


class _StageMetricsRecorder:
    def __init__(self, *, scope: str, metadata: Mapping[str, Any]) -> None:
        self._scope = str(scope)
        self._metadata = dict(metadata)
        self._started_monotonic = time.perf_counter()
        self._started_unix = time.time()
        self._stages: list[dict[str, Any]] = []

    def stage(self, name: str, **details: Any) -> "_StageSpan":
        return _StageSpan(self, str(name), details)

    def _finish_stage(self, span: "_StageSpan", exc: BaseException | None) -> None:
        ended = time.perf_counter()
        rss_after = _resource_rss_snapshot()
        rss_before = span.rss_before
        event = {
            "index": len(self._stages),
            "name": span.name,
            "status": "failed" if exc is not None else "ok",
            "elapsed_seconds": float(ended - span.started),
            "rss_before": rss_before,
            "rss_after": rss_after,
            "self_maxrss_delta_kb": max(
                0,
                int(rss_after["self_maxrss_kb"]) - int(rss_before["self_maxrss_kb"]),
            ),
            "children_maxrss_delta_kb": max(
                0,
                int(rss_after["children_maxrss_kb"])
                - int(rss_before["children_maxrss_kb"]),
            ),
        }
        if span.details:
            event["details"] = dict(span.details)
        if span.result:
            event["result"] = dict(span.result)
        if exc is not None:
            event["error_type"] = type(exc).__name__
            event["error_message"] = str(exc)
        self._stages.append(event)

    def summary(
        self,
        *,
        status: str,
        files: Mapping[str, str | Path | None] | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        rss = _resource_rss_snapshot()
        payload: dict[str, Any] = {
            "version": _PREPARE_STAGE_METRICS_VERSION,
            "scope": self._scope,
            "status": str(status),
            "metadata": dict(self._metadata),
            "started_unix_seconds": float(self._started_unix),
            "elapsed_seconds": float(time.perf_counter() - self._started_monotonic),
            "rss": rss,
            "stage_count": int(len(self._stages)),
            "stages": list(self._stages),
            "rss_semantics": {
                "self_maxrss_kb": "Python process high-water mark after the stage",
                "self_maxrss_delta_kb": (
                    "increase in Python process high-water mark during the stage"
                ),
                "children_maxrss_kb": (
                    "cumulative high-water mark reported by RUSAGE_CHILDREN"
                ),
                "subprocess_maxrss_kb": (
                    "per-qret command max RSS from /usr/bin/time -v when available"
                ),
            },
        }
        if files is not None:
            payload["file_sizes_bytes"] = _existing_file_sizes(files)
        if extra:
            payload.update(dict(extra))
        return payload

    def write(
        self,
        path: Path,
        *,
        status: str,
        files: Mapping[str, str | Path | None] | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        _atomic_write_json(path, self.summary(status=status, files=files, extra=extra))


class _StageSpan:
    def __init__(
        self,
        recorder: _StageMetricsRecorder,
        name: str,
        details: Mapping[str, Any],
    ) -> None:
        self._recorder = recorder
        self.name = name
        self.details = dict(details)
        self.result: dict[str, Any] = {}
        self.started = 0.0
        self.rss_before: dict[str, int] = {}

    def __enter__(self) -> "_StageSpan":
        self.started = time.perf_counter()
        self.rss_before = _resource_rss_snapshot()
        return self

    def add_result(self, **items: Any) -> None:
        self.result.update(items)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: Any,
    ) -> bool:
        self._recorder._finish_stage(self, exc)
        return False


class _NullStageSpan:
    def __enter__(self) -> "_NullStageSpan":
        return self

    def add_result(self, **items: Any) -> None:
        return None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: Any,
    ) -> bool:
        return False


def _null_stage() -> _NullStageSpan:
    return _NullStageSpan()


def grouped_hchain_ham_name(chain_length: int) -> str:
    molecule = f"H{int(chain_length)}"
    num_qubits = 2 * int(chain_length)
    if num_qubits % 4 == 0:
        return f"{molecule}_sto-3g_singlet_distance_100_charge_0_grouping"
    return f"{molecule}_sto-3g_triplet_1+_distance_100_charge_1_grouping"


def grouped_surface_code_hchain_targets(max_chain_length: int) -> list[dict[str, Any]]:
    if int(max_chain_length) < 2:
        raise ValueError("max_chain_length must be >= 2")
    return [
        {
            "molecule": f"H{chain}",
            "num_qubits": 2 * chain,
            "ham_name": grouped_hchain_ham_name(chain),
        }
        for chain in range(2, int(max_chain_length) + 1)
    ]


def _artifact_positive_scalar(value: Any, *, field: str, context: str) -> float:
    try:
        scalar = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field}={value!r} in {context}") from exc
    if not np.isfinite(scalar) or scalar <= 0:
        raise ValueError(f"Invalid {field}={scalar!r} in {context}")
    return scalar


def _artifact_nonnegative_int(value: Any, *, field: str, context: str) -> int:
    try:
        scalar = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field}={value!r} in {context}") from exc
    if not np.isfinite(scalar) or scalar < 0:
        raise ValueError(f"Invalid {field}={scalar!r} in {context}")
    rounded = int(round(scalar))
    if not math.isclose(scalar, rounded, rel_tol=0.0, abs_tol=1.0e-9):
        raise ValueError(f"Invalid non-integer {field}={scalar!r} in {context}")
    return rounded


def load_grouped_alpha_and_order(
    ham_name: str,
    pf_label: PFLabel,
    *,
    use_original: bool = False,
) -> tuple[float, float]:
    pf_label = normalize_pf_label(pf_label)
    target_name = f"{ham_name}_Operator_{pf_label}_ave"
    try:
        raw = load_data(target_name, gr=True, use_original=use_original)
        if isinstance(raw, Mapping):
            raw = raw.get("coeff")
        alpha = _artifact_positive_scalar(
            raw,
            field="coeff(_ave)",
            context=target_name,
        )
        return alpha, float(P_DIR[pf_label])
    except FileNotFoundError:
        legacy_name = f"{ham_name}_Operator_{pf_label}"
        payload = load_data(legacy_name, gr=True, use_original=use_original)
        if not isinstance(payload, Mapping):
            raise ValueError(f"Invalid grouped artifact: {legacy_name}")
        alpha = _artifact_positive_scalar(
            payload.get("coeff"),
            field="coeff",
            context=legacy_name,
        )
        return alpha, float(P_DIR[pf_label])


def qpe_iteration_factor(alpha: float, p: float, epsilon_e: float) -> float:
    if alpha <= 0 or p <= 0 or epsilon_e <= 0:
        raise ValueError("alpha, p, and epsilon_e must be positive")
    return float(
        BETA
        * ((1.0 + p) / (p * epsilon_e))
        * ((alpha * (1.0 + p) / epsilon_e) ** (1.0 / p))
    )


def surface_code_step_time(
    ham_name: str,
    pf_label: PFLabel,
    *,
    target_error: float = TARGET_ERROR,
    use_original: bool = False,
) -> float:
    alpha, p = load_grouped_alpha_and_order(
        ham_name,
        pf_label,
        use_original=use_original,
    )
    return float((target_error / alpha * (p + 1.0)) ** (1.0 / p))


def surface_code_rotation_precision(
    ham_name: str,
    pf_label: PFLabel,
    *,
    target_error: float = TARGET_ERROR,
    step_time: float | None = None,
    use_original: bool = False,
) -> float:
    mode = str(SURFACE_CODE_ROTATION_PRECISION_MODE)
    if mode == "fixed":
        return float(SURFACE_CODE_FIXED_ROTATION_PRECISION)
    if mode != "layer_linear_floor":
        raise ValueError("Only fixed and layer_linear_floor precision modes are supported")

    pf_label = normalize_pf_label(pf_label)
    alpha, p = load_grouped_alpha_and_order(
        ham_name,
        pf_label,
        use_original=use_original,
    )
    step_t = (
        float(step_time)
        if step_time is not None
        else surface_code_step_time(
            ham_name,
            pf_label,
            target_error=target_error,
            use_original=use_original,
        )
    )
    qpe_factor = qpe_iteration_factor(alpha, p, target_error)
    mol_label = f"H{_parse_hchain_length(ham_name)}"
    denominator = float(PF_RZ_LAYER[mol_label][pf_label]) * qpe_factor
    precision = (
        step_t
        * float(SURFACE_CODE_ROTATION_ERROR_BUDGET_FRACTION)
        * float(target_error)
    ) / denominator
    return max(float(SURFACE_CODE_ROTATION_PRECISION_FLOOR), float(precision))


def _parse_hchain_length(ham_name: str) -> int:
    match = re.match(r"H(?P<chain>\d+)_", str(ham_name))
    if match is None:
        raise ValueError(f"Could not parse H-chain length from {ham_name!r}")
    return int(match.group("chain"))


def _parse_distance(ham_name: str) -> float:
    match = re.search(r"_distance_(?P<dist>\d+)", str(ham_name))
    if match is None:
        return float(DEFAULT_DISTANCE)
    return float(int(match.group("dist"))) / 100.0


def _surface_code_integrals(chain_length: int, *, distance: float) -> tuple[float, Any, Any]:
    import pyscf
    from pyscf import gto, scf

    from .chemistry_hamiltonian import geo

    geometry, multiplicity, charge = geo(chain_length, distance)
    mol = gto.Mole()
    mol.atom = geometry
    mol.basis = DEFAULT_BASIS
    mol.spin = multiplicity - 1
    mol.charge = charge
    mol.symmetry = False
    mol.build()

    mf = scf.RHF(mol)
    mf.verbose = 0
    mf.kernel()
    constant = float(mf.energy_nuc())
    mo_coeff = mf.mo_coeff
    h_core = mf.get_hcore()
    one_body = mo_coeff.T @ h_core @ mo_coeff
    eri_mo = pyscf.ao2mo.kernel(mf.mol, mo_coeff)
    eri_mo = pyscf.ao2mo.restore(1, eri_mo, mo_coeff.shape[0])
    two_body = np.asarray(eri_mo.transpose(0, 2, 3, 1), order="C")
    return constant, one_body, two_body


def build_grouped_surface_code_step_circuit(
    ham_name: str,
    pf_label: PFLabel,
    *,
    step_time: float,
) -> Any:
    from openfermion import InteractionOperator
    from openfermion.chem.molecular_data import spinorb_from_spatial
    from openfermion.transforms import get_fermion_operator, jordan_wigner
    from qiskit import QuantumCircuit

    from .chemistry_hamiltonian import min_hamiltonian_grouper
    from .qiskit_time_evolution_grouping import w_trotter_grouper
    from .qiskit_time_evolution_pyscf import _build_grouped_jw_list

    chain_length = _parse_hchain_length(ham_name)
    constant, one_body, two_body = _surface_code_integrals(
        chain_length,
        distance=_parse_distance(ham_name),
    )

    if chain_length in (2, 3):
        h1s, h2s = spinorb_from_spatial(one_body, two_body * 0.5)
        jw_hamiltonian = jordan_wigner(
            get_fermion_operator(InteractionOperator(constant, h1s, h2s))
        )
        num_qubits = int(h1s.shape[0])
        grouped_ops, _grouped_name = min_hamiltonian_grouper(jw_hamiltonian, ham_name)
        commuting_cliques = [[op] for op in grouped_ops]
    else:
        commuting_cliques = _build_grouped_jw_list(constant, one_body, two_body)
        num_qubits = int(2 * np.asarray(one_body).shape[0])

    qc = QuantumCircuit(num_qubits)
    w_trotter_grouper(
        qc,
        commuting_cliques,
        float(step_time),
        num_qubits,
        normalize_pf_label(pf_label),
    )
    qc.global_phase = 0.0
    return qc


def _prepare_runtime_env(
    runtime_root: Path,
    *,
    binary_path: Path | None = None,
    rotation_precision: float | None = None,
) -> dict[str, str]:
    tmp_dir = runtime_root / "tmp"
    mpl_dir = runtime_root / "mplconfig"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    mpl_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["TMPDIR"] = str(tmp_dir)
    env["TMP"] = str(tmp_dir)
    env["TEMP"] = str(tmp_dir)
    env["MPLCONFIGDIR"] = str(mpl_dir)
    if binary_path is not None:
        lib_dir = str(binary_path.parent)
        for key in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
            current = env.get(key, "")
            env[key] = lib_dir + (os.pathsep + current if current else "")
    gridsynth_path = Path(SURFACE_CODE_GRIDSYNTH_PATH).expanduser().resolve()
    if gridsynth_path.exists():
        env["GRIDSYNTH_PATH"] = str(gridsynth_path)
    if rotation_precision is not None:
        env["QSVT_OPENQASM_ROTATION_PRECISION"] = f"{float(rotation_precision):.17g}"
    if SURFACE_CODE_COMPILE_SKIP_REDUNDANT_IR_PREPROCESS:
        env["QSVT_COMPILE_SKIP_IR_PREPROCESS"] = "1"
    if SURFACE_CODE_COMPILE_SKIP_OUTPUT:
        env["QSVT_COMPILE_SKIP_OUTPUT"] = "1"
    return env


def _basis_circuit(qc: Any, *, runtime_root: Path) -> Any:
    env = _prepare_runtime_env(runtime_root)
    os.environ.update(
        {
            "TMPDIR": env["TMPDIR"],
            "TMP": env["TMP"],
            "TEMP": env["TEMP"],
            "MPLCONFIGDIR": env["MPLCONFIGDIR"],
        }
    )
    tempfile.tempdir = env["TMPDIR"]

    from .qiskit_time_evolution_utils import _decompose_to_basis

    basis = _decompose_to_basis(
        qc,
        basis_gates=SURFACE_CODE_QASM_BASIS_GATES,
        decompose_reps=int(SURFACE_CODE_QASM_DECOMPOSE_REPS),
        optimization_level=0,
    )
    basis.global_phase = 0.0
    return basis


def _qasm2_text(qc: Any) -> str:
    try:
        from qiskit import qasm2

        return str(qasm2.dumps(qc))
    except Exception:
        if hasattr(qc, "qasm"):
            return str(qc.qasm())
        raise RuntimeError("Failed to export circuit to OpenQASM2")


def _safe_path_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value))


def _count_qasm_rz(qasm_text: str) -> int:
    return sum(1 for line in str(qasm_text).splitlines() if _RZ_QASM_LINE_RE.match(line))


def _ir_instruction_qubits(inst: Mapping[str, Any]) -> list[int]:
    opcode = str(inst.get("opcode"))
    if opcode in _INLINE_ONE_QUBIT_OPS:
        return [int(inst["q"])]
    if opcode in _INLINE_TWO_QUBIT_OPS:
        return [int(inst["q0"]), int(inst["q1"])]
    if opcode in _INLINE_THREE_QUBIT_OPS:
        return [int(inst["q0"]), int(inst["q1"]), int(inst["q2"])]
    if "operate" in inst and isinstance(inst["operate"], list):
        return [int(q) for q in inst["operate"]]
    return []


def _canonical_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_json_value(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, list):
        return [_canonical_json_value(item) for item in value]
    return value


def _normalized_instruction_line(inst: Mapping[str, Any]) -> str:
    return json.dumps(
        _canonical_json_value(inst),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


class _InstructionStreamRecorder:
    def __init__(self, *, num_qubits: int) -> None:
        if int(num_qubits) < 0:
            raise ValueError(f"Invalid num_qubits={num_qubits}")
        self._stream_hash = hashlib.sha256()
        self._qubit_depth = [0] * int(num_qubits)
        self._magic_layers: dict[int, int] = {}
        self._opcode_count: dict[str, int] = {}
        self._emitted_instruction_count = 0
        self._scheduled_instruction_count = 0
        self._call_count = 0
        self._magic_count = 0

    def observe(self, inst: Mapping[str, Any]) -> None:
        opcode = str(inst.get("opcode"))
        self._stream_hash.update(_normalized_instruction_line(inst).encode("utf-8"))
        self._stream_hash.update(b"\n")
        self._emitted_instruction_count += 1
        self._opcode_count[opcode] = self._opcode_count.get(opcode, 0) + 1

        if opcode in _INLINE_IGNORED_OPS:
            return
        if opcode == "Call":
            self._call_count += 1
            return

        qargs = _ir_instruction_qubits(inst)
        if not qargs:
            return
        if max(qargs) >= len(self._qubit_depth):
            self._qubit_depth.extend([0] * (max(qargs) + 1 - len(self._qubit_depth)))
        layer = max(self._qubit_depth[q] for q in qargs) + 1
        for q in qargs:
            self._qubit_depth[q] = layer
        self._scheduled_instruction_count += 1
        if opcode in {"T", "TDag"}:
            self._magic_count += 1
            self._magic_layers[layer] = self._magic_layers.get(layer, 0) + 1

    def summary(self) -> dict[str, Any]:
        return {
            "version": _IR_STREAM_SUMMARY_VERSION,
            "normalized_instruction_stream_hash": self._stream_hash.hexdigest(),
            "emitted_instruction_count": int(self._emitted_instruction_count),
            "scheduled_instruction_count": int(self._scheduled_instruction_count),
            "call_count": int(self._call_count),
            "opcode_count": dict(sorted(self._opcode_count.items())),
            "num_logical_qubits": int(len(self._qubit_depth)),
            "gate_depth": int(max(self._qubit_depth, default=0)),
            "step_magic_state_count": int(self._magic_count),
            "step_magic_state_depth": int(len(self._magic_layers)),
            "peak_magic_layer": int(max(self._magic_layers.values(), default=0)),
        }


def _optimized_ir_summary_from_stream(
    stream_summary: Mapping[str, Any],
) -> dict[str, Any]:
    scheduled_instruction_count = int(stream_summary["scheduled_instruction_count"])
    return {
        "num_logical_qubits": int(stream_summary["num_logical_qubits"]),
        "instruction_count": scheduled_instruction_count,
        "instruction_count_semantics": "scheduled_non_control_instructions",
        "emitted_instruction_count": int(stream_summary["emitted_instruction_count"]),
        "scheduled_instruction_count": scheduled_instruction_count,
        "gate_depth": int(stream_summary["gate_depth"]),
        "step_magic_state_count": int(stream_summary["step_magic_state_count"]),
        "step_magic_state_depth": int(stream_summary["step_magic_state_depth"]),
        "peak_magic_layer": int(stream_summary["peak_magic_layer"]),
        "unresolved_call_count": int(stream_summary["call_count"]),
        "instruction_stream": dict(stream_summary),
    }


def summarize_optimized_ir(ir_path: str | Path, *, function_name: str = "main") -> Dict[str, Any]:
    path = Path(ir_path).expanduser().resolve()
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    target: Mapping[str, Any] | None = None
    for circuit in data.get("circuit_list", []):
        if isinstance(circuit, Mapping) and circuit.get("name") == function_name:
            target = circuit
            break
    if target is None:
        raise ValueError(f"Circuit '{function_name}' not found in {path}")

    argument = target.get("argument")
    if not isinstance(argument, Mapping):
        raise ValueError(f"Missing argument for '{function_name}' in {path}")
    num_qubits = int(argument.get("num_qubits", 0))
    if num_qubits < 0:
        raise ValueError(f"Invalid num_qubits={num_qubits} in {path}")

    bb_list = target.get("bb_list")
    if not isinstance(bb_list, list) or len(bb_list) != 1:
        raise ValueError(f"Expected one basic block for '{function_name}' in {path}")
    inst_list = bb_list[0].get("inst_list", [])
    if not isinstance(inst_list, list):
        raise ValueError(f"Invalid inst_list for '{function_name}' in {path}")

    recorder = _InstructionStreamRecorder(num_qubits=num_qubits)
    for inst in inst_list:
        if not isinstance(inst, Mapping):
            continue
        recorder.observe(inst)

    stream_summary = recorder.summary()

    return _optimized_ir_summary_from_stream(stream_summary)


def _optimized_ir_summary_from_inline_or_file(
    opt_path: Path,
    cached_opt: Any,
) -> dict[str, Any]:
    inline_summary = (
        cached_opt.get("inline_summary") if isinstance(cached_opt, Mapping) else None
    )
    instruction_stream = (
        inline_summary.get("instruction_stream")
        if isinstance(inline_summary, Mapping)
        else None
    )
    if isinstance(instruction_stream, Mapping):
        return _optimized_ir_summary_from_stream(instruction_stream)
    return summarize_optimized_ir(opt_path)


_RZ_QASM_LINE_RE = re.compile(
    r"^(?P<indent>\s*)rz\((?P<theta>[^;\n]+)\)\s+"
    r"(?P<target>[A-Za-z_][A-Za-z0-9_]*(?:\[\d+\])?)\s*;\s*$"
)
_IR_ROTATION_PRECISION_REWRITE_VERSION = "ir_param_rotation_precision_v1"
_IR_STREAM_SUMMARY_VERSION = "ir_instruction_stream_summary_v1"
_PYTHON_INLINE_IR_VERSION = "python_streaming_inline_ir_v1"
_PARAMETRIZED_ROTATION_OPS = {"RX", "RY", "RZ"}


def _eval_qasm_angle(theta: str) -> float:
    return float(
        eval(
            str(theta).replace("^", "**"),
            {"__builtins__": {}},
            {"pi": math.pi},
        )
    )


def _rz_cache_key(theta: str) -> str:
    theta_text = str(theta).strip()
    round_digits = SURFACE_CODE_RZ_CALL_CACHE_ROUND_DIGITS
    if round_digits is None:
        return theta_text
    return f"{_eval_qasm_angle(theta_text):.{int(round_digits)}g}"


def _rewrite_qasm_rz_as_calls(qasm_text: str) -> tuple[str, dict[str, Any]]:
    lines = str(qasm_text).splitlines()
    rewritten: list[str] = []
    key_to_gate: dict[str, dict[str, Any]] = {}
    rz_count = 0

    for line in lines:
        match = _RZ_QASM_LINE_RE.match(line)
        if match is None:
            rewritten.append(line)
            continue
        theta = match.group("theta").strip()
        key = _rz_cache_key(theta)
        entry = key_to_gate.get(key)
        if entry is None:
            gate_name = f"sc_rz_{len(key_to_gate):04d}"
            entry = {
                "gate_name": gate_name,
                "function_name": f"__import_from_openqasm2__{gate_name}()",
                "theta": theta,
                "key": key,
                "count": 0,
            }
            key_to_gate[key] = entry
        entry["count"] = int(entry["count"]) + 1
        rz_count += 1
        rewritten.append(
            f"{match.group('indent')}{entry['gate_name']} {match.group('target')};"
        )

    if rz_count == 0:
        return str(qasm_text), {
            "enabled": False,
            "rz_count": 0,
            "unique_rotation_count": 0,
            "helpers": [],
        }

    gate_definitions = [
        f"gate {entry['gate_name']} a {{ rz({entry['theta']}) a; }}"
        for entry in key_to_gate.values()
    ]
    insert_index = 0
    for index, line in enumerate(rewritten):
        stripped = line.strip()
        if stripped.startswith("OPENQASM ") or stripped.startswith("include "):
            insert_index = index + 1
            continue
        break
    rewritten[insert_index:insert_index] = gate_definitions
    return "\n".join(rewritten) + "\n", {
        "enabled": True,
        "rz_count": int(rz_count),
        "unique_rotation_count": int(len(key_to_gate)),
        "round_digits": SURFACE_CODE_RZ_CALL_CACHE_ROUND_DIGITS,
        "helpers": list(key_to_gate.values()),
    }


def _rewrite_ir_rotation_precision(
    ir_path: Path,
    *,
    rotation_precision: float,
) -> dict[str, Any]:
    precision = float(rotation_precision)
    if not np.isfinite(precision) or precision <= 0:
        raise ValueError(f"rotation precision must be positive: {rotation_precision}")

    with Path(ir_path).open("r", encoding="utf-8") as f:
        data = json.load(f)

    scanned = 0
    rewritten = 0
    for circuit in data.get("circuit_list", []):
        if not isinstance(circuit, Mapping):
            continue
        for bb in circuit.get("bb_list", []):
            if not isinstance(bb, Mapping):
                continue
            inst_list = bb.get("inst_list", [])
            if not isinstance(inst_list, list):
                continue
            for inst in inst_list:
                if not isinstance(inst, Mapping):
                    continue
                if str(inst.get("opcode")) not in _PARAMETRIZED_ROTATION_OPS:
                    continue
                theta = inst.get("theta")
                if not isinstance(theta, Mapping):
                    continue
                scanned += 1
                try:
                    if float(theta.get("precision")) == precision:
                        continue
                except (TypeError, ValueError):
                    pass
                theta["precision"] = precision
                rewritten += 1

    with Path(ir_path).open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=True, separators=(",", ":"))

    return {
        "version": _IR_ROTATION_PRECISION_REWRITE_VERSION,
        "precision": precision,
        "parametrized_rotation_count": int(scanned),
        "rewritten_rotation_count": int(rewritten),
        "opcodes": sorted(_PARAMETRIZED_ROTATION_OPS),
    }


def _run_qret(
    cmd: Sequence[str],
    *,
    runtime_root: Path,
    rotation_precision: float | None = None,
    stage_recorder: _StageMetricsRecorder | None = None,
    stage_name: str | None = None,
    stage_details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    binary_path = Path(cmd[0]).expanduser().resolve()
    env = _prepare_runtime_env(
        runtime_root,
        binary_path=binary_path,
        rotation_precision=rotation_precision,
    )
    details = dict(stage_details or {})
    details.setdefault("command", [str(item) for item in cmd])
    use_gnu_time = bool(stage_recorder is not None and Path("/usr/bin/time").exists())
    run_cmd = (
        ["/usr/bin/time", "-v", *[str(item) for item in cmd]]
        if use_gnu_time
        else [str(item) for item in cmd]
    )

    def run_command(span: _StageSpan | None = None) -> dict[str, Any]:
        completed = subprocess.run(
            run_cmd,
            cwd=str(runtime_root),
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        metrics: dict[str, Any] = {
            "returncode": int(completed.returncode),
            "stdout_bytes": len(stdout.encode("utf-8")),
            "stderr_bytes": len(stderr.encode("utf-8")),
            "gnu_time_used": use_gnu_time,
        }
        subprocess_maxrss = (
            _parse_gnu_time_maxrss_kb(stderr) if use_gnu_time else None
        )
        if subprocess_maxrss is not None:
            metrics["subprocess_maxrss_kb"] = int(subprocess_maxrss)
        output_path = details.get("output_path")
        output_size = _file_size_bytes(output_path) if output_path is not None else None
        if output_size is not None:
            metrics["output_size_bytes"] = int(output_size)
        if span is not None:
            span.add_result(**metrics)
        if completed.returncode == 0:
            return metrics
        failure_details = "\n".join(
            part.strip() for part in (stdout, stderr) if part.strip()
        )
        raise RuntimeError(
            f"quration command failed (code={completed.returncode}): {' '.join(cmd)}"
            + (f"\n{failure_details}" if failure_details else "")
        )

    if stage_recorder is not None and stage_name is not None:
        with stage_recorder.stage(stage_name, **details) as span:
            return run_command(span)
    return run_command()


def _opt_passes() -> list[str]:
    return [
        "ir::recursive_inliner",
        "ir::static_condition_pruning",
        "ir::decompose_inst",
        "ir::ignore_global_phase",
        "ir::delete_consecutive_same_pauli",
        "ir::delete_opt_hint",
    ]


def _compile_uses_topology(compile_mode: str) -> bool:
    return compile_mode in {"ftqc_compile_topology", "ftqc_compile_topology_qec"}


def _compile_uses_qec(compile_mode: str) -> bool:
    return compile_mode == "ftqc_compile_topology_qec"


def sc_ls_fixed_v0_passes(compile_mode: str) -> list[str]:
    passes = ["sc_ls_fixed_v0::init_compile_info"]
    if _compile_uses_topology(compile_mode):
        passes.extend(
            [
                "sc_ls_fixed_v0::mapping",
                "sc_ls_fixed_v0::routing",
                "sc_ls_fixed_v0::calc_info_without_topology",
                "sc_ls_fixed_v0::calc_info_with_topology",
            ]
        )
        if _compile_uses_qec(compile_mode):
            passes.append("sc_ls_fixed_v0::calc_info_with_qec_resource_estimation")
    else:
        passes.append("sc_ls_fixed_v0::calc_info_without_topology")
    passes.append("sc_ls_fixed_v0::dump_compile_info")
    return passes


def opt_pipeline_yaml(
    *,
    ir_path: Path,
    opt_path: Path,
    passes: Sequence[str] | None = None,
    entry_name: str = "main",
) -> str:
    effective_passes = list(passes) if passes is not None else _opt_passes()
    return "\n".join(
        [
            f"input: {ir_path}",
            f"function: {entry_name}",
            f"output: {opt_path}",
            "pass:",
            *[f"- {name}" for name in effective_passes],
            "",
        ]
    )


_INLINE_ONE_QUBIT_OPS = {"I", "X", "Y", "Z", "H", "S", "SDag", "T", "TDag"}
_INLINE_TWO_QUBIT_OPS = {"CX", "CY", "CZ"}
_INLINE_THREE_QUBIT_OPS = {"CCX", "CCY", "CCZ"}
_INLINE_IGNORED_OPS = {"Return", "DirtyBegin", "DirtyEnd", "CleanProb", "Clean"}


def _python_inline_ir(
    input_ir_path: Path,
    output_ir_path: Path,
    *,
    function_name: str = "main",
) -> dict[str, Any]:
    started = time.perf_counter()
    with input_ir_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    functions: dict[str, dict[str, Any]] = {}
    target_item: dict[str, Any] | None = None
    for circuit in data.get("circuit_list", []):
        if not isinstance(circuit, Mapping):
            continue
        name = circuit.get("name")
        if not isinstance(name, str):
            continue
        bb_list = circuit.get("bb_list")
        argument = circuit.get("argument")
        if not isinstance(bb_list, list) or len(bb_list) != 1:
            raise ValueError(f"Python inliner only supports one basic block: {name}")
        if not isinstance(argument, Mapping):
            raise ValueError(f"Missing argument for {name}")
        functions[name] = {
            "inst_list": bb_list[0].get("inst_list", []),
            "num_qubits": int(argument.get("num_qubits", 0)),
        }
        if name == function_name:
            target_item = dict(circuit)

    if function_name not in functions or target_item is None:
        raise ValueError(f"Circuit '{function_name}' not found in {input_ir_path}")

    def map_qubit(qubit_map: Sequence[int], value: Any) -> int:
        return int(qubit_map[int(value)])

    def mapped_instruction(inst: Mapping[str, Any], qubit_map: Sequence[int]) -> dict[str, Any]:
        opcode = str(inst.get("opcode"))
        new_inst = dict(inst)
        if opcode in _INLINE_ONE_QUBIT_OPS:
            new_inst["q"] = map_qubit(qubit_map, new_inst["q"])
        elif opcode in _INLINE_TWO_QUBIT_OPS:
            new_inst["q0"] = map_qubit(qubit_map, new_inst["q0"])
            new_inst["q1"] = map_qubit(qubit_map, new_inst["q1"])
        elif opcode in _INLINE_THREE_QUBIT_OPS:
            new_inst["q0"] = map_qubit(qubit_map, new_inst["q0"])
            new_inst["q1"] = map_qubit(qubit_map, new_inst["q1"])
            new_inst["q2"] = map_qubit(qubit_map, new_inst["q2"])
        else:
            raise ValueError(f"Unsupported opcode '{opcode}'")
        return new_inst

    def iter_unrolled(
        name: str,
        qubit_map: Sequence[int],
        stack: tuple[str, ...],
    ) -> Any:
        if name in stack:
            raise ValueError("Recursive Call cycle detected: " + " -> ".join((*stack, name)))
        function = functions.get(name)
        if function is None:
            raise ValueError(f"Unknown callee '{name}'")
        for inst in function["inst_list"]:
            if not isinstance(inst, Mapping):
                continue
            opcode = str(inst.get("opcode"))
            if opcode == "Call":
                callee = inst.get("callee")
                operate = inst.get("operate")
                if not isinstance(callee, str) or not isinstance(operate, list):
                    raise ValueError(f"Invalid Call in {name}")
                child_map = [map_qubit(qubit_map, q) for q in operate]
                yield from iter_unrolled(callee, child_map, (*stack, name))
                continue
            if opcode in _INLINE_IGNORED_OPS:
                continue
            yield mapped_instruction(inst, qubit_map)

    def write_json_field(
        f: Any,
        key: str,
        value: Any,
        *,
        first: bool,
    ) -> bool:
        if not first:
            f.write(",")
        json.dump(str(key), f, ensure_ascii=True, separators=(",", ":"))
        f.write(":")
        json.dump(value, f, ensure_ascii=True, separators=(",", ":"))
        return False

    def write_streamed_ir(
        *,
        tmp_path: Path,
        recorder: _InstructionStreamRecorder,
    ) -> None:
        target = dict(target_item or {})
        bb_list = target.get("bb_list")
        if not isinstance(bb_list, list) or len(bb_list) != 1:
            raise ValueError(f"Python inliner only supports one basic block: {function_name}")
        target_bb = dict(bb_list[0])
        num_qubits = int(functions[function_name]["num_qubits"])

        with tmp_path.open("w", encoding="utf-8") as f:
            f.write("{")
            first_top = True
            for key, value in data.items():
                if key == "circuit_list":
                    continue
                first_top = write_json_field(f, str(key), value, first=first_top)

            if not first_top:
                f.write(",")
            json.dump("circuit_list", f, ensure_ascii=True, separators=(",", ":"))
            f.write(":[{")

            first_circuit = True
            for key, value in target.items():
                if key == "bb_list":
                    continue
                first_circuit = write_json_field(
                    f,
                    str(key),
                    value,
                    first=first_circuit,
                )

            if not first_circuit:
                f.write(",")
            json.dump("bb_list", f, ensure_ascii=True, separators=(",", ":"))
            f.write(":[{")

            first_bb = True
            for key, value in target_bb.items():
                if key == "inst_list":
                    continue
                first_bb = write_json_field(f, str(key), value, first=first_bb)

            if not first_bb:
                f.write(",")
            json.dump("inst_list", f, ensure_ascii=True, separators=(",", ":"))
            f.write(":[")

            first_inst = True
            for inst in iter_unrolled(function_name, list(range(num_qubits)), ()):
                if not first_inst:
                    f.write(",")
                json.dump(inst, f, ensure_ascii=True, separators=(",", ":"))
                recorder.observe(inst)
                first_inst = False

            return_inst = {"opcode": "Return"}
            if not first_inst:
                f.write(",")
            json.dump(return_inst, f, ensure_ascii=True, separators=(",", ":"))
            recorder.observe(return_inst)
            f.write("]}]}]}")

    num_qubits = int(functions[function_name]["num_qubits"])
    recorder = _InstructionStreamRecorder(num_qubits=num_qubits)
    output_ir_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _atomic_temp_path(output_ir_path)
    try:
        write_streamed_ir(tmp_path=tmp_path, recorder=recorder)
        os.replace(tmp_path, output_ir_path)
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise

    stream_summary = recorder.summary()
    return {
        "version": _PYTHON_INLINE_IR_VERSION,
        "input_path": str(input_ir_path),
        "output_path": str(output_ir_path),
        "function_name": function_name,
        "elapsed_seconds": float(time.perf_counter() - started),
        "emitted_instruction_count": int(stream_summary["emitted_instruction_count"]),
        "scheduled_instruction_count": int(
            stream_summary["scheduled_instruction_count"]
        ),
        "instruction_count_semantics": {
            "emitted_instruction_count": (
                "all emitted flat IR instructions including Return"
            ),
            "scheduled_instruction_count": (
                "non-control instructions included in depth scheduling"
            ),
        },
        "instruction_stream": stream_summary,
    }


def _run_rz_call_cached_opt(
    *,
    qret_path: Path,
    runtime_root: Path,
    ir_path: Path,
    opt_path: Path,
    rz_metadata: Mapping[str, Any],
    rotation_precision: float,
    stage_recorder: _StageMetricsRecorder | None = None,
) -> dict[str, Any]:
    helpers = [
        dict(item)
        for item in rz_metadata.get("helpers", [])
        if isinstance(item, Mapping)
    ]
    if not helpers:
        opt_yaml_path = runtime_root / "opt.yaml"
        opt_yaml_path.write_text(
            opt_pipeline_yaml(ir_path=ir_path, opt_path=opt_path),
            encoding="utf-8",
        )
        _run_qret(
            [str(qret_path), "opt", "--pipeline", str(opt_yaml_path), "--verbose"],
            runtime_root=runtime_root,
            rotation_precision=rotation_precision,
            stage_recorder=stage_recorder,
            stage_name="qret_opt_without_rz_helpers",
            stage_details={
                "input_path": str(ir_path),
                "output_path": str(opt_path),
                "pipeline_path": str(opt_yaml_path),
            },
        )
        return {"mode": "qret_opt_without_rz_helpers"}

    cache_dir = runtime_root / "rz_call_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    with (
        stage_recorder.stage("write_rz_call_cache_metadata")
        if stage_recorder is not None
        else _null_stage()
    ) as span:
        metadata_path = runtime_root / "rz_call_cache_metadata.json"
        _atomic_write_json(metadata_path, rz_metadata)
        span.add_result(output_size_bytes=_file_size_bytes(metadata_path))

    current_input = ir_path
    helper_passes = [
        "ir::decompose_inst",
        "ir::ignore_global_phase",
        "ir::delete_consecutive_same_pauli",
        "ir::delete_opt_hint",
    ]
    for index, helper in enumerate(helpers):
        pass_output = cache_dir / f"rz_helper_{index:04d}.json"
        pass_yaml = cache_dir / f"rz_helper_{index:04d}.yaml"
        pass_yaml.write_text(
            opt_pipeline_yaml(
                ir_path=current_input,
                opt_path=pass_output,
                passes=helper_passes,
                entry_name=str(helper["function_name"]),
            ),
            encoding="utf-8",
        )
        _run_qret(
            [str(qret_path), "opt", "--pipeline", str(pass_yaml), "--verbose"],
            runtime_root=runtime_root,
            rotation_precision=rotation_precision,
            stage_recorder=stage_recorder,
            stage_name=f"qret_opt_rz_helper_{index:04d}",
            stage_details={
                "helper_index": int(index),
                "helper_function_name": str(helper["function_name"]),
                "helper_key": helper.get("key"),
                "helper_theta": helper.get("theta"),
                "input_path": str(current_input),
                "output_path": str(pass_output),
                "pipeline_path": str(pass_yaml),
            },
        )
        current_input = pass_output

    main_pre_inline = cache_dir / "main_before_python_inline.json"
    main_yaml = cache_dir / "main_cleanup.yaml"
    main_yaml.write_text(
        opt_pipeline_yaml(
            ir_path=current_input,
            opt_path=main_pre_inline,
            passes=[
                "ir::static_condition_pruning",
                "ir::ignore_global_phase",
                "ir::delete_consecutive_same_pauli",
                "ir::delete_opt_hint",
            ],
            entry_name="main",
        ),
        encoding="utf-8",
    )
    _run_qret(
        [str(qret_path), "opt", "--pipeline", str(main_yaml), "--verbose"],
        runtime_root=runtime_root,
        rotation_precision=rotation_precision,
        stage_recorder=stage_recorder,
        stage_name="qret_opt_main_cleanup",
        stage_details={
            "input_path": str(current_input),
            "output_path": str(main_pre_inline),
            "pipeline_path": str(main_yaml),
        },
    )
    with (
        stage_recorder.stage(
            "python_streaming_inline",
            input_path=str(main_pre_inline),
            output_path=str(opt_path),
        )
        if stage_recorder is not None
        else _null_stage()
    ) as span:
        inline_summary = _python_inline_ir(
            main_pre_inline,
            opt_path,
            function_name="main",
        )
        span.add_result(
            output_size_bytes=_file_size_bytes(opt_path),
            emitted_instruction_count=inline_summary.get("emitted_instruction_count"),
            scheduled_instruction_count=inline_summary.get(
                "scheduled_instruction_count"
            ),
            normalized_instruction_stream_hash=inline_summary.get(
                "instruction_stream",
                {},
            ).get("normalized_instruction_stream_hash"),
        )
    with (
        stage_recorder.stage("write_python_inline_summary")
        if stage_recorder is not None
        else _null_stage()
    ) as span:
        inline_summary_path = runtime_root / "python_inline_summary.json"
        _atomic_write_json(inline_summary_path, inline_summary)
        span.add_result(output_size_bytes=_file_size_bytes(inline_summary_path))
    return {
        "mode": "rz_call_cached_streaming_python_inline",
        "helper_count": int(len(helpers)),
        "main_pre_inline_path": str(main_pre_inline),
        "inline_summary": inline_summary,
    }


def compile_pipeline_yaml(
    *,
    opt_path: Path,
    compile_output_path: Path,
    compile_info_path: Path,
    architecture: SurfaceCodeArchitecture,
) -> str:
    topology_path = Path(architecture.topology_path).expanduser().resolve()
    lines = [
        "source: IR",
        f"input: {opt_path}",
        "function: main",
        "target: SC_LS_FIXED_V0",
        f"output: {compile_output_path}",
        f"sc_ls_fixed_v0_topology: {topology_path}",
        f"sc_ls_fixed_v0_machine_type: {architecture.machine_type}",
        f"sc_ls_fixed_v0_magic_generation_period: {int(architecture.magic_generation_period)}",
        f"sc_ls_fixed_v0_maximum_magic_state_stock: {int(architecture.maximum_magic_state_stock)}",
        f"sc_ls_fixed_v0_entanglement_generation_period: {int(architecture.entanglement_generation_period)}",
        f"sc_ls_fixed_v0_maximum_entangled_state_stock: {int(architecture.maximum_entangled_state_stock)}",
        f"sc_ls_fixed_v0_reaction_time: {int(architecture.reaction_time)}",
    ]
    if _compile_uses_qec(architecture.compile_mode):
        lines.extend(
            [
                f"sc_ls_fixed_v0_physical_error_rate: {float(architecture.physical_error_rate):.12g}",
                f"sc_ls_fixed_v0_drop_rate: {float(architecture.drop_rate):.12g}",
                f"sc_ls_fixed_v0_code_cycle_time_sec: {float(architecture.code_cycle_time_sec):.12g}",
                f"sc_ls_fixed_v0_allowed_failure_prob: {float(architecture.allowed_failure_prob):.12g}",
            ]
        )
    lines.extend(
        [
            f"sc_ls_fixed_v0_dump_compile_info_to_json: {compile_info_path}",
            "sc_ls_fixed_v0_pass:",
            *[f"  - {name}" for name in sc_ls_fixed_v0_passes(architecture.compile_mode)],
            "",
        ]
    )
    return "\n".join(lines)


def mapping_pipeline_yaml(
    *,
    opt_path: Path,
    mapping_state_path: Path,
    mapping_compile_info_path: Path,
    architecture: SurfaceCodeArchitecture,
) -> str:
    topology_path = Path(architecture.topology_path).expanduser().resolve()
    lines = [
        "source: IR",
        f"input: {opt_path}",
        "function: main",
        "target: SC_LS_FIXED_V0",
        f"output: {mapping_state_path}",
        f"sc_ls_fixed_v0_topology: {topology_path}",
        f"sc_ls_fixed_v0_machine_type: {architecture.machine_type}",
        f"sc_ls_fixed_v0_magic_generation_period: {int(architecture.magic_generation_period)}",
        f"sc_ls_fixed_v0_maximum_magic_state_stock: {int(architecture.maximum_magic_state_stock)}",
        f"sc_ls_fixed_v0_entanglement_generation_period: {int(architecture.entanglement_generation_period)}",
        f"sc_ls_fixed_v0_maximum_entangled_state_stock: {int(architecture.maximum_entangled_state_stock)}",
        f"sc_ls_fixed_v0_reaction_time: {int(architecture.reaction_time)}",
        f"sc_ls_fixed_v0_dump_compile_info_to_json: {mapping_compile_info_path}",
        "sc_ls_fixed_v0_pass:",
        "  - sc_ls_fixed_v0::init_compile_info",
        "  - sc_ls_fixed_v0::mapping",
        "  - sc_ls_fixed_v0::dump_compile_info",
        "",
    ]
    return "\n".join(lines)


def _cache_key(
    *,
    target_error: float,
    rotation_precision: float,
    architecture: SurfaceCodeArchitecture,
) -> str:
    return (
        f"{architecture.compile_mode}"
        f"_arch_{architecture.cache_tag()}"
        f"_rzcache_{int(bool(SURFACE_CODE_RZ_CALL_CACHE))}"
        f"_rot_{float(rotation_precision):.3e}"
        f"_eps_{float(target_error):.12e}"
    )


def _runtime_root(
    ham_name: str,
    pf_label: PFLabel,
    *,
    target_error: float,
    rotation_precision: float,
    architecture: SurfaceCodeArchitecture,
) -> Path:
    safe_ham = re.sub(r"[^A-Za-z0-9_.-]+", "_", ham_name)
    safe_pf = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(pf_label))
    return (
        SURFACE_CODE_CACHE_DIR
        / "gr"
        / architecture.compile_mode
        / f"{safe_ham}__{safe_pf}"
        / _cache_key(
            target_error=target_error,
            rotation_precision=rotation_precision,
            architecture=architecture,
        )
    )


def _step_artifact_cache_key(
    *,
    ham_name: str,
    pf_label: PFLabel,
    target_error: float,
    step_time: float,
    rotation_precision: float,
    qret_hash: str,
) -> str:
    payload = {
        "ham_name": ham_name,
        "pf_label": pf_label,
        "target_error": float(target_error),
        "step_time": float(step_time),
        "rotation_precision": float(rotation_precision),
        "qret_hash": qret_hash,
        "qasm_basis_gates": list(SURFACE_CODE_QASM_BASIS_GATES),
        "qasm_decompose_reps": int(SURFACE_CODE_QASM_DECOMPOSE_REPS),
        "rz_call_cache": bool(SURFACE_CODE_RZ_CALL_CACHE),
        "rz_call_cache_round_digits": SURFACE_CODE_RZ_CALL_CACHE_ROUND_DIGITS,
        "ir_rotation_precision_rewrite": _IR_ROTATION_PRECISION_REWRITE_VERSION,
        "ir_stream_summary": _IR_STREAM_SUMMARY_VERSION,
        "python_inline_ir": _PYTHON_INLINE_IR_VERSION,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _step_artifact_runtime_root(
    ham_name: str,
    pf_label: PFLabel,
    *,
    target_error: float,
    step_time: float,
    rotation_precision: float,
    qret_hash: str,
) -> Path:
    safe_ham = _safe_path_component(ham_name)
    safe_pf = _safe_path_component(str(pf_label))
    return (
        SURFACE_CODE_CACHE_DIR
        / "gr"
        / "prepared_step"
        / f"{safe_ham}__{safe_pf}"
        / _step_artifact_cache_key(
            ham_name=ham_name,
            pf_label=pf_label,
            target_error=target_error,
            step_time=step_time,
            rotation_precision=rotation_precision,
            qret_hash=qret_hash,
        )
    )


def prepare_grouped_surface_code_step_artifact(
    ham_name: str,
    pf_label: PFLabel,
    *,
    target_error: float = TARGET_ERROR,
    architecture: SurfaceCodeArchitecture | None = None,
    step_time: float | None = None,
    rotation_precision: float | None = None,
    use_original: bool = False,
) -> SurfaceCodeStepArtifact:
    architecture = architecture or SurfaceCodeArchitecture()
    pf_label = normalize_pf_label(pf_label)
    step_t = (
        float(step_time)
        if step_time is not None
        else surface_code_step_time(
            ham_name,
            pf_label,
            target_error=target_error,
            use_original=use_original,
        )
    )
    rot_precision = (
        float(rotation_precision)
        if rotation_precision is not None
        else surface_code_rotation_precision(
            ham_name,
            pf_label,
            target_error=target_error,
            step_time=step_t,
            use_original=use_original,
        )
    )
    qret_path = Path(architecture.qret_path).expanduser().resolve()
    if not qret_path.exists():
        raise FileNotFoundError(f"quration binary not found: {qret_path}")
    qret_hash = file_sha256(qret_path)
    runtime_root = _step_artifact_runtime_root(
        ham_name,
        pf_label,
        target_error=target_error,
        step_time=step_t,
        rotation_precision=rot_precision,
        qret_hash=qret_hash,
    )
    runtime_root.mkdir(parents=True, exist_ok=True)

    qasm_path = runtime_root / "step.qasm"
    ir_path = runtime_root / "step_ir.json"
    opt_path = runtime_root / "step_opt.json"
    stage_metrics_path = runtime_root / "prepare_stage_metrics.json"
    stage_files = {
        "qasm": qasm_path,
        "ir": ir_path,
        "optimized_ir": opt_path,
        "python_inline_summary": runtime_root / "python_inline_summary.json",
        "step_instruction_stream_summary": (
            runtime_root / "step_instruction_stream_summary.json"
        ),
        "step_artifact": runtime_root / "step_artifact.json",
    }
    stage_recorder = _StageMetricsRecorder(
        scope="prepare_grouped_surface_code_step_artifact",
        metadata={
            "ham_name": ham_name,
            "pf_label": pf_label,
            "target_error": float(target_error),
            "step_time": float(step_t),
            "rotation_precision": float(rot_precision),
            "qret_path": str(qret_path),
            "qret_hash": qret_hash,
            "rz_call_cache_enabled": bool(SURFACE_CODE_RZ_CALL_CACHE),
        },
    )

    try:
        with stage_recorder.stage("cache_lookup") as span:
            cached_artifact = load_prepared_surface_code_step_artifact(runtime_root)
            span.add_result(cache_hit=cached_artifact is not None)
        if cached_artifact is not None:
            stage_recorder.write(
                stage_metrics_path,
                status="cache_hit",
                files=stage_files,
            )
            return cached_artifact

        with stage_recorder.stage("build_step_circuit") as span:
            qc = build_grouped_surface_code_step_circuit(
                ham_name,
                pf_label,
                step_time=step_t,
            )
            span.add_result(circuit_type=type(qc).__name__)

        with stage_recorder.stage("basis_circuit") as span:
            qc_basis = _basis_circuit(qc, runtime_root=runtime_root)
            span.add_result(circuit_type=type(qc_basis).__name__)

        with stage_recorder.stage("qasm_text") as span:
            qasm_text = _qasm2_text(qc_basis)
            rz_count = _count_qasm_rz(qasm_text)
            span.add_result(
                qasm_bytes=len(qasm_text.encode("utf-8")),
                rz_count=int(rz_count),
            )

        rz_metadata: dict[str, Any] | None = None
        with stage_recorder.stage(
            "rz_helper_rewrite",
            enabled=bool(SURFACE_CODE_RZ_CALL_CACHE),
        ) as span:
            if bool(SURFACE_CODE_RZ_CALL_CACHE):
                qasm_text, rz_metadata = _rewrite_qasm_rz_as_calls(qasm_text)
            if rz_metadata is None:
                rz_metadata = {
                    "enabled": False,
                    "rz_count": int(rz_count),
                    "unique_rotation_count": None,
                    "round_digits": SURFACE_CODE_RZ_CALL_CACHE_ROUND_DIGITS,
                }
            span.add_result(
                rz_count=int(rz_metadata.get("rz_count") or rz_count),
                unique_rotation_count=rz_metadata.get("unique_rotation_count"),
                qasm_bytes=len(qasm_text.encode("utf-8")),
            )

        with stage_recorder.stage("write_qasm", output_path=str(qasm_path)) as span:
            qasm_path.write_text(qasm_text, encoding="utf-8")
            span.add_result(output_size_bytes=_file_size_bytes(qasm_path))

        _run_qret(
            [
                str(qret_path),
                "parse",
                "--input",
                str(qasm_path),
                "--output",
                str(ir_path),
                "--format",
                "OpenQASM2",
                "--verbose",
            ],
            runtime_root=runtime_root,
            rotation_precision=rot_precision,
            stage_recorder=stage_recorder,
            stage_name="qret_parse",
            stage_details={
                "input_path": str(qasm_path),
                "output_path": str(ir_path),
            },
        )

        with stage_recorder.stage(
            "ir_rotation_precision_rewrite",
            input_path=str(ir_path),
        ) as span:
            rz_metadata["ir_rotation_precision"] = _rewrite_ir_rotation_precision(
                ir_path,
                rotation_precision=rot_precision,
            )
            span.add_result(
                **rz_metadata["ir_rotation_precision"],
                output_size_bytes=_file_size_bytes(ir_path),
            )

        if rz_metadata.get("enabled"):
            rz_metadata["cached_opt"] = _run_rz_call_cached_opt(
                qret_path=qret_path,
                runtime_root=runtime_root,
                ir_path=ir_path,
                opt_path=opt_path,
                rz_metadata=rz_metadata,
                rotation_precision=rot_precision,
                stage_recorder=stage_recorder,
            )
        else:
            opt_yaml_path = runtime_root / "opt.yaml"
            opt_yaml_path.write_text(
                opt_pipeline_yaml(ir_path=ir_path, opt_path=opt_path),
                encoding="utf-8",
            )
            _run_qret(
                [
                    str(qret_path),
                    "opt",
                    "--pipeline",
                    str(opt_yaml_path),
                    "--verbose",
                ],
                runtime_root=runtime_root,
                rotation_precision=rot_precision,
                stage_recorder=stage_recorder,
                stage_name="qret_opt",
                stage_details={
                    "input_path": str(ir_path),
                    "output_path": str(opt_path),
                    "pipeline_path": str(opt_yaml_path),
                },
            )

        with stage_recorder.stage("optimized_ir_summary") as span:
            summary = _optimized_ir_summary_from_inline_or_file(
                opt_path,
                rz_metadata.get("cached_opt"),
            )
            span.add_result(
                instruction_count=summary.get("instruction_count"),
                emitted_instruction_count=summary.get("emitted_instruction_count"),
                step_magic_state_count=summary.get("step_magic_state_count"),
                normalized_instruction_stream_hash=summary.get(
                    "instruction_stream",
                    {},
                ).get("normalized_instruction_stream_hash"),
            )
        if isinstance(summary.get("instruction_stream"), Mapping):
            with stage_recorder.stage("write_step_instruction_stream_summary") as span:
                stream_summary_path = (
                    runtime_root / "step_instruction_stream_summary.json"
                )
                _atomic_write_json(stream_summary_path, summary["instruction_stream"])
                span.add_result(output_size_bytes=_file_size_bytes(stream_summary_path))
            rz_metadata["optimized_ir_stream"] = dict(summary["instruction_stream"])
        if int(summary.get("unresolved_call_count", 0)) != 0:
            raise ValueError(
                "Optimized IR still contains Call instructions; "
                "architecture sweep requires a concrete single-step IR."
            )
        molecule = f"H{_parse_hchain_length(ham_name)}"

        with stage_recorder.stage("hash_outputs") as span:
            qasm_hash = file_sha256(qasm_path)
            optimized_ir_hash = file_sha256(opt_path)
            span.add_result(
                qasm_hash=qasm_hash,
                optimized_ir_hash=optimized_ir_hash,
                qasm_size_bytes=_file_size_bytes(qasm_path),
                optimized_ir_size_bytes=_file_size_bytes(opt_path),
            )

        artifact = SurfaceCodeStepArtifact(
            ham_name=ham_name,
            molecule=molecule,
            num_logical_qubits=int(summary["num_logical_qubits"]),
            pf_label=pf_label,
            target_error=float(target_error),
            step_time=float(step_t),
            rotation_precision=float(rot_precision),
            runtime_root=runtime_root,
            qasm_path=qasm_path,
            ir_path=ir_path,
            optimized_ir_path=opt_path,
            qasm_hash=qasm_hash,
            optimized_ir_hash=optimized_ir_hash,
            qret_path=qret_path,
            qret_hash=qret_hash,
            step_rz_count=int(rz_metadata.get("rz_count") or rz_count),
            step_rz_layer=PF_RZ_LAYER.get(molecule, {}).get(pf_label),
            step_magic_state_count=int(summary["step_magic_state_count"]),
            step_magic_state_depth=int(summary["step_magic_state_depth"]),
            peak_magic_layer=int(summary["peak_magic_layer"]),
            instruction_count=int(summary["instruction_count"]),
            gate_depth=int(summary["gate_depth"]),
            rz_call_cache=dict(rz_metadata),
        )
        with stage_recorder.stage("write_step_artifact") as span:
            artifact_path = runtime_root / "step_artifact.json"
            _atomic_write_json(artifact_path, artifact.to_dict())
            span.add_result(output_size_bytes=_file_size_bytes(artifact_path))
        stage_recorder.write(
            stage_metrics_path,
            status="ok",
            files=stage_files,
            extra={
                "artifact_instruction_count": int(artifact.instruction_count),
                "artifact_magic_state_count": int(artifact.step_magic_state_count),
                "artifact_gate_depth": int(artifact.gate_depth),
            },
        )
        return artifact
    except Exception:
        try:
            stage_recorder.write(
                stage_metrics_path,
                status="failed",
                files=stage_files,
            )
        except Exception:
            pass
        raise


def surface_code_compile_cache_payload(
    artifact: SurfaceCodeStepArtifact,
    architecture: SurfaceCodeArchitecture,
) -> Dict[str, Any]:
    qret_path = Path(architecture.qret_path).expanduser().resolve()
    topology_path = Path(architecture.topology_path).expanduser().resolve()
    topology_hash = (
        file_sha256(topology_path) if _compile_uses_topology(architecture.compile_mode) else None
    )
    return {
        "qasm_hash": artifact.qasm_hash,
        "optimized_ir_hash": artifact.optimized_ir_hash,
        "topology_path": str(topology_path) if topology_hash is not None else None,
        "topology_hash": topology_hash,
        "compile_mode": architecture.compile_mode,
        "machine_type": architecture.machine_type,
        "magic_generation_period": int(architecture.magic_generation_period),
        "maximum_magic_state_stock": int(architecture.maximum_magic_state_stock),
        "entanglement_generation_period": int(architecture.entanglement_generation_period),
        "maximum_entangled_state_stock": int(architecture.maximum_entangled_state_stock),
        "reaction_time": int(architecture.reaction_time),
        "physical_error_rate": float(architecture.physical_error_rate),
        "drop_rate": float(architecture.drop_rate),
        "code_cycle_time_sec": float(architecture.code_cycle_time_sec),
        "allowed_failure_prob": float(architecture.allowed_failure_prob),
        "rotation_precision": float(artifact.rotation_precision),
        "qret_path": str(qret_path),
        "qret_hash": file_sha256(qret_path),
        "skip_compile_output": bool(architecture.skip_compile_output),
    }


def surface_code_compile_cache_key(
    artifact: SurfaceCodeStepArtifact,
    architecture: SurfaceCodeArchitecture,
) -> str:
    payload = surface_code_compile_cache_payload(artifact, architecture)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _single_int(values: Any) -> int | None:
    if not isinstance(values, list) or not values:
        return None
    return int(values[0])


def _coord_list(value: Any) -> list[int] | None:
    if not isinstance(value, list):
        return None
    return [int(item) for item in value]


def _extract_mapping_result(
    *,
    mapping_state_path: Path,
    mapping_result_path: Path,
    artifact: SurfaceCodeStepArtifact,
    architecture: SurfaceCodeArchitecture,
) -> None:
    with mapping_state_path.open("r", encoding="utf-8") as f:
        state = json.load(f)

    logical_qubits: list[dict[str, Any]] = []
    magic_factories: list[dict[str, Any]] = []
    entanglement_factories: list[dict[str, Any]] = []
    for inst in state.get("program", []):
        if not isinstance(inst, Mapping):
            continue
        inst_type = str(inst.get("type"))
        coord = _coord_list(inst.get("dest"))
        metadata = inst.get("metadata") if isinstance(inst.get("metadata"), Mapping) else {}
        entry = {
            "coord": coord,
            "beat": metadata.get("beat"),
            "z": metadata.get("z"),
            "raw": inst.get("raw"),
        }
        if inst_type == "ALLOCATE":
            logical_qubit = _single_int(inst.get("qtarget"))
            if logical_qubit is None:
                continue
            logical_qubits.append(
                {
                    "logical_qubit": logical_qubit,
                    "dir": inst.get("dir"),
                    **entry,
                }
            )
        elif inst_type == "ALLOCATE_MAGIC_FACTORY":
            symbol = _single_int(inst.get("mtarget"))
            if symbol is None:
                continue
            magic_factories.append({"symbol": symbol, **entry})
        elif inst_type == "ALLOCATE_ENTANGLEMENT_FACTORY":
            symbol = _single_int(inst.get("etarget"))
            if symbol is None:
                symbol = _single_int(inst.get("ehtarget"))
            if symbol is None:
                continue
            entanglement_factories.append({"symbol": symbol, **entry})

    logical_qubits.sort(key=lambda item: int(item["logical_qubit"]))
    magic_factories.sort(key=lambda item: int(item["symbol"]))
    entanglement_factories.sort(key=lambda item: int(item["symbol"]))

    topology_path = Path(architecture.topology_path).expanduser().resolve()
    payload = {
        "format": "quration_sc_ls_fixed_v0_mapping",
        "schema_version": "0.1",
        "ham_name": artifact.ham_name,
        "molecule": artifact.molecule,
        "pf_label": artifact.pf_label,
        "num_logical_qubits": int(artifact.num_logical_qubits),
        "optimized_ir_hash": artifact.optimized_ir_hash,
        "compile_mode": architecture.compile_mode,
        "topology_path": str(topology_path),
        "topology_hash": file_sha256(topology_path),
        "machine_type": architecture.machine_type,
        "magic_generation_period": int(architecture.magic_generation_period),
        "maximum_magic_state_stock": int(architecture.maximum_magic_state_stock),
        "entanglement_generation_period": int(architecture.entanglement_generation_period),
        "maximum_entangled_state_stock": int(architecture.maximum_entangled_state_stock),
        "reaction_time": int(architecture.reaction_time),
        "logical_qubit_mapping": logical_qubits,
        "magic_factory_mapping": magic_factories,
        "entanglement_factory_mapping": entanglement_factories,
        "logical_qubit_mapping_count": int(len(logical_qubits)),
        "magic_factory_mapping_count": int(len(magic_factories)),
        "entanglement_factory_mapping_count": int(len(entanglement_factories)),
    }
    _atomic_write_json(mapping_result_path, payload)


def save_surface_code_mapping_result(
    *,
    artifact: SurfaceCodeStepArtifact,
    architecture: SurfaceCodeArchitecture,
    runtime_root: Path,
    reuse_cache: bool = True,
) -> dict[str, Any]:
    if not _compile_uses_topology(architecture.compile_mode):
        return {
            "mapping_result_json": None,
            "mapping_result_hash": None,
            "mapping_result_unavailable_reason": "requires_topology_compile_mode",
        }

    mapping_result_path = runtime_root / "mapping.json"
    if reuse_cache and mapping_result_path.exists():
        return {
            "mapping_result_json": str(mapping_result_path),
            "mapping_result_hash": file_sha256(mapping_result_path),
            "mapping_result_unavailable_reason": None,
        }

    qret_path = Path(architecture.qret_path).expanduser().resolve()
    mapping_yaml_path = _atomic_temp_path(runtime_root / "mapping.yaml")
    mapping_state_path = _atomic_temp_path(runtime_root / "mapping_state.json")
    mapping_compile_info_path = _atomic_temp_path(
        runtime_root / "mapping_compile_info.json"
    )
    for output_path in (mapping_state_path, mapping_compile_info_path):
        try:
            output_path.unlink()
        except FileNotFoundError:
            pass
    try:
        mapping_yaml_path.write_text(
            mapping_pipeline_yaml(
                opt_path=artifact.optimized_ir_path,
                mapping_state_path=mapping_state_path,
                mapping_compile_info_path=mapping_compile_info_path,
                architecture=architecture,
            ),
            encoding="utf-8",
        )
        _run_qret(
            [
                str(qret_path),
                "compile",
                "--pipeline",
                str(mapping_yaml_path),
                "--verbose",
            ],
            runtime_root=runtime_root,
            rotation_precision=artifact.rotation_precision,
        )
        _extract_mapping_result(
            mapping_state_path=mapping_state_path,
            mapping_result_path=mapping_result_path,
            artifact=artifact,
            architecture=architecture,
        )
    finally:
        for tmp_path in (
            mapping_state_path,
            mapping_yaml_path,
            mapping_compile_info_path,
        ):
            try:
                tmp_path.unlink()
            except FileNotFoundError:
                pass
    return {
        "mapping_result_json": str(mapping_result_path),
        "mapping_result_hash": file_sha256(mapping_result_path),
        "mapping_result_unavailable_reason": None,
    }


def _compile_runtime_root(
    artifact: SurfaceCodeStepArtifact,
    architecture: SurfaceCodeArchitecture,
) -> Path:
    safe_ham = _safe_path_component(artifact.ham_name)
    safe_pf = _safe_path_component(str(artifact.pf_label))
    return (
        SURFACE_CODE_CACHE_DIR
        / "gr"
        / architecture.compile_mode
        / f"{safe_ham}__{safe_pf}"
        / surface_code_compile_cache_key(artifact, architecture)
    )


def compile_prepared_surface_code_step_artifact(
    artifact: SurfaceCodeStepArtifact,
    architecture: SurfaceCodeArchitecture,
    *,
    reuse_cache: bool = True,
) -> Dict[str, Any]:
    qret_path = Path(architecture.qret_path).expanduser().resolve()
    topology_path = Path(architecture.topology_path).expanduser().resolve()
    if not qret_path.exists():
        raise FileNotFoundError(f"quration binary not found: {qret_path}")
    if _compile_uses_topology(architecture.compile_mode) and not topology_path.exists():
        raise FileNotFoundError(f"quration topology file not found: {topology_path}")

    runtime_root = _compile_runtime_root(artifact, architecture)
    runtime_root.mkdir(parents=True, exist_ok=True)
    compile_info_path = runtime_root / "compile_info.json"
    compile_output_path = runtime_root / "step_sc_ls_fixed_v0.json"
    if architecture.skip_compile_output:
        compile_output_path = Path(os.devnull)

    cache_hit = bool(reuse_cache and compile_info_path.exists())
    started = time.perf_counter()
    if not cache_hit:
        compile_yaml_path = runtime_root / "compile.yaml"
        compile_yaml_path.write_text(
            compile_pipeline_yaml(
                opt_path=artifact.optimized_ir_path,
                compile_output_path=compile_output_path,
                compile_info_path=compile_info_path,
                architecture=architecture,
            ),
            encoding="utf-8",
        )
        _run_qret(
            [
                str(qret_path),
                "compile",
                "--pipeline",
                str(compile_yaml_path),
                "--verbose",
            ],
            runtime_root=runtime_root,
            rotation_precision=artifact.rotation_precision,
        )
    elapsed = float(time.perf_counter() - started)

    if architecture.save_mapping_result:
        mapping_metadata = save_surface_code_mapping_result(
            artifact=artifact,
            architecture=architecture,
            runtime_root=runtime_root,
            reuse_cache=reuse_cache,
        )
    else:
        mapping_metadata = {
            "mapping_result_json": None,
            "mapping_result_hash": None,
            "mapping_result_unavailable_reason": "disabled",
        }
    metrics = surface_code_step_metrics_from_compile_info_json(compile_info_path)
    cache_key = surface_code_compile_cache_key(artifact, architecture)
    metrics.update(
        {
            "target_error": float(artifact.target_error),
            "step_time": float(artifact.step_time),
            "rotation_precision": float(artifact.rotation_precision),
            "cache_key": cache_key,
            "generator": "grouped_surface_code_qret",
            "auto_generated": True,
            "source": "gr",
            "compile_mode": architecture.compile_mode,
            "execution_time_sec": elapsed,
            "compile_cache_hit": cache_hit,
            "compile_runtime_config": architecture.to_dict(),
            "compile_runtime_config_source": "architecture",
            "qasm_hash": artifact.qasm_hash,
            "optimized_ir_hash": artifact.optimized_ir_hash,
            "compiler_executable_path": str(qret_path),
            "compiler_executable_hash": file_sha256(qret_path),
            "topology_hash": file_sha256(topology_path)
            if _compile_uses_topology(architecture.compile_mode)
            else None,
            **mapping_metadata,
            "step_rz_count": int(artifact.step_rz_count),
            "step_rz_layer": artifact.step_rz_layer,
            "step_magic_state_count": int(artifact.step_magic_state_count),
            "step_magic_state_depth": int(artifact.step_magic_state_depth),
            "peak_magic_layer": int(artifact.peak_magic_layer),
            "rz_call_cache": dict(artifact.rz_call_cache),
        }
    )
    normalized = normalize_surface_code_step_metrics(
        metrics,
        context=f"{artifact.ham_name}_Operator_{artifact.pf_label}",
    )
    for key in (
        "compile_cache_hit",
        "qasm_hash",
        "optimized_ir_hash",
        "compiler_executable_path",
        "compiler_executable_hash",
        "topology_hash",
        "mapping_result_json",
        "mapping_result_hash",
        "mapping_result_unavailable_reason",
        "step_rz_count",
        "step_rz_layer",
        "step_magic_state_count",
        "step_magic_state_depth",
        "peak_magic_layer",
    ):
        if key in metrics:
            normalized[key] = metrics[key]
    _atomic_write_json(runtime_root / "step_metrics.json", normalized)
    return normalized


def normalize_surface_code_step_metrics(
    metrics: Mapping[str, Any],
    *,
    context: str = "surface_code_step",
) -> Dict[str, Any]:
    required = (
        "magic_state_consumption_count",
        "magic_state_consumption_depth",
        "runtime",
        "runtime_without_topology",
        "qubit_volume",
    )
    optional = (
        "gate_count",
        "gate_depth",
        "measurement_feedback_count",
        "measurement_feedback_depth",
        "magic_factory_count",
        "chip_cell_count",
        "code_distance",
        "num_physical_qubits",
        "t_count",
        "t_depth",
    )
    out: Dict[str, Any] = {}
    for field_name in required:
        out[field_name] = _artifact_nonnegative_int(
            metrics.get(field_name),
            field=field_name,
            context=context,
        )
    for field_name in optional:
        if field_name in metrics:
            out[field_name] = _artifact_nonnegative_int(
                metrics.get(field_name),
                field=field_name,
                context=context,
            )
    if "execution_time_sec" in metrics:
        out["execution_time_sec"] = float(metrics["execution_time_sec"])
    for key in (
        "source",
        "compile_info_json",
        "compile_mode",
        "generator",
        "cache_key",
        "mapping_result_json",
        "mapping_result_hash",
        "mapping_result_unavailable_reason",
    ):
        if metrics.get(key) is not None:
            out[key] = str(metrics[key])
    for key in ("target_error", "step_time", "rotation_precision"):
        if metrics.get(key) is not None:
            out[key] = float(metrics[key])
    if isinstance(metrics.get("compile_runtime_config"), Mapping):
        out["compile_runtime_config"] = dict(metrics["compile_runtime_config"])
    if metrics.get("compile_runtime_config_source") is not None:
        out["compile_runtime_config_source"] = str(metrics["compile_runtime_config_source"])
    if isinstance(metrics.get("rz_call_cache"), Mapping):
        out["rz_call_cache"] = dict(metrics["rz_call_cache"])
    if "auto_generated" in metrics:
        out["auto_generated"] = bool(metrics["auto_generated"])
    return out


def surface_code_step_metrics_from_compile_info_json(
    compile_info_path: str | Path,
) -> Dict[str, Any]:
    path = Path(compile_info_path).expanduser().resolve()
    with path.open("r", encoding="utf-8") as f:
        compile_info = json.load(f)
    metrics = normalize_surface_code_step_metrics(compile_info, context=str(path))
    metrics["compile_info_json"] = str(path)
    return metrics


def generate_grouped_surface_code_step_metrics(
    ham_name: str,
    pf_label: PFLabel,
    *,
    target_error: float = TARGET_ERROR,
    architecture: SurfaceCodeArchitecture | None = None,
    step_time: float | None = None,
    rotation_precision: float | None = None,
    use_original: bool = False,
) -> Dict[str, Any]:
    architecture = architecture or SurfaceCodeArchitecture()
    artifact = prepare_grouped_surface_code_step_artifact(
        ham_name,
        pf_label,
        target_error=target_error,
        architecture=architecture,
        step_time=step_time,
        rotation_precision=rotation_precision,
        use_original=use_original,
    )
    return compile_prepared_surface_code_step_artifact(artifact, architecture)


def compile_grouped_hchain_step(
    chain_length: int,
    pf_label: PFLabel,
    *,
    target_error: float = TARGET_ERROR,
    architecture: SurfaceCodeArchitecture | None = None,
    use_original: bool = False,
) -> Dict[str, Any]:
    return generate_grouped_surface_code_step_metrics(
        grouped_hchain_ham_name(chain_length),
        pf_label,
        target_error=target_error,
        architecture=architecture,
        use_original=use_original,
    )


_generate_surface_code_step_metrics = generate_grouped_surface_code_step_metrics
_build_grouped_surface_code_step_circuit = build_grouped_surface_code_step_circuit
_surface_code_compile_pipeline_yaml = compile_pipeline_yaml
