from __future__ import annotations

import hashlib
import json
import math
import os
import re
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


def file_sha256(path: str | Path) -> str:
    resolved = Path(path).expanduser().resolve()
    digest = hashlib.sha256()
    with resolved.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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

    qubit_depth = [0] * max(num_qubits, 0)
    magic_layers: dict[int, int] = {}
    magic_count = 0
    scheduled_inst_count = 0
    unsupported_calls = 0

    for inst in inst_list:
        if not isinstance(inst, Mapping):
            continue
        opcode = str(inst.get("opcode"))
        if opcode in _INLINE_IGNORED_OPS:
            continue
        if opcode == "Call":
            unsupported_calls += 1
            continue

        qargs = _ir_instruction_qubits(inst)
        if not qargs:
            continue
        if max(qargs) >= len(qubit_depth):
            qubit_depth.extend([0] * (max(qargs) + 1 - len(qubit_depth)))
        layer = max(qubit_depth[q] for q in qargs) + 1
        for q in qargs:
            qubit_depth[q] = layer
        scheduled_inst_count += 1
        if opcode in {"T", "TDag"}:
            magic_count += 1
            magic_layers[layer] = magic_layers.get(layer, 0) + 1

    return {
        "num_logical_qubits": int(len(qubit_depth)),
        "instruction_count": int(scheduled_inst_count),
        "gate_depth": int(max(qubit_depth, default=0)),
        "step_magic_state_count": int(magic_count),
        "step_magic_state_depth": int(len(magic_layers)),
        "peak_magic_layer": int(max(magic_layers.values(), default=0)),
        "unresolved_call_count": int(unsupported_calls),
    }


_RZ_QASM_LINE_RE = re.compile(
    r"^(?P<indent>\s*)rz\((?P<theta>[^;\n]+)\)\s+"
    r"(?P<target>[A-Za-z_][A-Za-z0-9_]*(?:\[\d+\])?)\s*;\s*$"
)


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


def _run_qret(
    cmd: Sequence[str],
    *,
    runtime_root: Path,
    rotation_precision: float | None = None,
) -> None:
    binary_path = Path(cmd[0]).expanduser().resolve()
    env = _prepare_runtime_env(
        runtime_root,
        binary_path=binary_path,
        rotation_precision=rotation_precision,
    )
    completed = subprocess.run(
        list(cmd),
        cwd=str(runtime_root),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode == 0:
        return
    details = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    )
    raise RuntimeError(
        f"quration command failed (code={completed.returncode}): {' '.join(cmd)}"
        + (f"\n{details}" if details else "")
    )


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

    inlined: list[dict[str, Any]] = []

    def map_qubit(qubit_map: Sequence[int], value: Any) -> int:
        return int(qubit_map[int(value)])

    def unroll(name: str, qubit_map: Sequence[int], stack: tuple[str, ...]) -> None:
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
                unroll(callee, child_map, (*stack, name))
                continue
            if opcode in _INLINE_IGNORED_OPS:
                continue
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
            inlined.append(new_inst)

    num_qubits = int(functions[function_name]["num_qubits"])
    unroll(function_name, list(range(num_qubits)), ())
    inlined.append({"opcode": "Return"})
    target_item["bb_list"][0]["inst_list"] = inlined
    data["circuit_list"] = [target_item]
    output_ir_path.parent.mkdir(parents=True, exist_ok=True)
    with output_ir_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=True, separators=(",", ":"))
    return {"instruction_count": int(len(inlined))}


def _run_rz_call_cached_opt(
    *,
    qret_path: Path,
    runtime_root: Path,
    ir_path: Path,
    opt_path: Path,
    rz_metadata: Mapping[str, Any],
    rotation_precision: float,
) -> None:
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
        )
        return

    cache_dir = runtime_root / "rz_call_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    with (runtime_root / "rz_call_cache_metadata.json").open("w", encoding="utf-8") as f:
        json.dump(rz_metadata, f, ensure_ascii=True, indent=2)

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
    )
    _python_inline_ir(main_pre_inline, opt_path, function_name="main")


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

    qc = build_grouped_surface_code_step_circuit(
        ham_name,
        pf_label,
        step_time=step_t,
    )
    qc_basis = _basis_circuit(qc, runtime_root=runtime_root)
    qasm_text = _qasm2_text(qc_basis)
    rz_count = _count_qasm_rz(qasm_text)
    rz_metadata: dict[str, Any] | None = None
    if bool(SURFACE_CODE_RZ_CALL_CACHE):
        qasm_text, rz_metadata = _rewrite_qasm_rz_as_calls(qasm_text)
    if rz_metadata is None:
        rz_metadata = {
            "enabled": False,
            "rz_count": int(rz_count),
            "unique_rotation_count": None,
            "round_digits": SURFACE_CODE_RZ_CALL_CACHE_ROUND_DIGITS,
        }
    qasm_path.write_text(qasm_text, encoding="utf-8")

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
    )
    if rz_metadata.get("enabled"):
        _run_rz_call_cached_opt(
            qret_path=qret_path,
            runtime_root=runtime_root,
            ir_path=ir_path,
            opt_path=opt_path,
            rz_metadata=rz_metadata,
            rotation_precision=rot_precision,
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
        )

    summary = summarize_optimized_ir(opt_path)
    if int(summary.get("unresolved_call_count", 0)) != 0:
        raise ValueError(
            "Optimized IR still contains Call instructions; "
            "architecture sweep requires a concrete single-step IR."
        )
    molecule = f"H{_parse_hchain_length(ham_name)}"
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
        qasm_hash=file_sha256(qasm_path),
        optimized_ir_hash=file_sha256(opt_path),
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
    with (runtime_root / "step_artifact.json").open("w", encoding="utf-8") as f:
        json.dump(artifact.to_dict(), f, ensure_ascii=True, indent=2)
    return artifact


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
        "step_rz_count",
        "step_rz_layer",
        "step_magic_state_count",
        "step_magic_state_depth",
        "peak_magic_layer",
    ):
        if key in metrics:
            normalized[key] = metrics[key]
    with (runtime_root / "step_metrics.json").open("w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=True, indent=2)
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
    for key in ("source", "compile_info_json", "compile_mode", "generator", "cache_key"):
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
