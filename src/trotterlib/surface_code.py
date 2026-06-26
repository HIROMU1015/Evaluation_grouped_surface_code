from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import re
import resource
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from importlib import metadata as importlib_metadata
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
    SURFACE_CODE_INTEGRAL_CACHE_ENABLED,
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
    SURFACE_CODE_RZ_HELPER_BATCH_SIZE,
    SURFACE_CODE_RZ_HELPER_OPT_MODE,
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
    integral_cache: dict[str, Any] = field(default_factory=dict)

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
            "integral_cache": dict(self.integral_cache),
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
        integral_cache=dict(payload.get("integral_cache") or {}),
    )


@dataclass(frozen=True)
class _ResolvedSurfaceCodeIntegrals:
    constant: Any
    one_body: np.ndarray
    two_body: np.ndarray
    cache_enabled: bool
    schema_version: str
    cache_key: str
    integral_value_hash: str
    cache_status: str
    filled_by_other_process: bool
    initial_invalid_reason: str | None
    locked_invalid_reason: str | None
    cache_dir: Path
    npz_path: Path
    npz_sha256: str | None

    def provenance(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.cache_enabled),
            "schema_version": self.schema_version,
            "cache_key": self.cache_key,
            "integral_value_hash": self.integral_value_hash,
            "cache_status": self.cache_status,
            "filled_by_other_process": bool(self.filled_by_other_process),
            "npz_sha256": self.npz_sha256,
            "cache_dir": str(self.cache_dir),
        }


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


class _FileLock:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._file: Any | None = None

    def __enter__(self) -> "_FileLock":
        import fcntl

        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self._path.open("a+", encoding="utf-8")
        fcntl.flock(self._file.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: Any,
    ) -> bool:
        del exc_type, exc, traceback
        if self._file is not None:
            import fcntl

            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
            self._file.close()
            self._file = None
        return False


_PREPARE_STAGE_METRICS_VERSION = "surface_code_prepare_stage_metrics_v1"
_PREPARE_STAGE_METRICS_FILENAME = "prepare_stage_metrics.json"
_PREPARE_STAGE_CACHE_HIT_METRICS_FILENAME = "prepare_stage_cache_hit_metrics.json"
_COMPILE_STAGE_METRICS_FILENAME = "compile_stage_metrics.json"
_COMPILE_STAGE_CACHE_HIT_METRICS_FILENAME = "compile_stage_cache_hit_metrics.json"
_SURFACE_CODE_INTEGRAL_CACHE_VERSION = "surface_code_integral_cache_v2"
_SURFACE_CODE_STEP_ARTIFACT_CACHE_VERSION = "surface_code_step_artifact_cache_v2"
_SURFACE_CODE_CIRCUIT_GENERATION_VERSION = "grouped_hchain_pf_step_circuit_v2"
_SURFACE_CODE_STEP_DEPENDENCY_PACKAGES = (
    "numpy",
    "scipy",
    "pyscf",
    "openfermion",
    "openfermionpyscf",
    "qiskit",
)
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


def _current_rss_kb() -> int | None:
    status_path = Path("/proc/self/status")
    try:
        with status_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(parts[1])
                    return None
    except (OSError, ValueError):
        return None
    return None


def _rss_sampling_enabled() -> bool:
    value = os.environ.get("SURFACE_CODE_PROFILE_RSS_SAMPLING", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _rss_sampling_interval_seconds() -> float:
    raw = os.environ.get("SURFACE_CODE_PROFILE_RSS_SAMPLING_INTERVAL_SEC", "0.02")
    try:
        interval = float(raw)
    except ValueError:
        interval = 0.02
    return max(0.001, interval)


class _CurrentRssSampler:
    def __init__(self, interval_seconds: float) -> None:
        self._interval_seconds = float(interval_seconds)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._peak_kb: int | None = None
        self._sample_count = 0

    def start(self) -> None:
        first_sample = _current_rss_kb()
        if first_sample is not None:
            self._peak_kb = int(first_sample)
            self._sample_count = 1
        self._thread = threading.Thread(
            target=self._run,
            name="surface-code-rss-sampler",
            daemon=True,
        )
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            sample = _current_rss_kb()
            if sample is None:
                continue
            self._sample_count += 1
            if self._peak_kb is None or int(sample) > self._peak_kb:
                self._peak_kb = int(sample)

    def stop(self) -> dict[str, int | bool | None]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self._interval_seconds * 4.0))
        final_sample = _current_rss_kb()
        if final_sample is not None:
            self._sample_count += 1
            if self._peak_kb is None or int(final_sample) > self._peak_kb:
                self._peak_kb = int(final_sample)
        return {
            "enabled": True,
            "sample_count": int(self._sample_count),
            "sampled_peak_rss_kb": self._peak_kb,
            "thread_alive_after_stop": (
                self._thread.is_alive() if self._thread is not None else False
            ),
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
        sampler_result = span.stop_sampler()
        current_rss_after = _current_rss_kb()
        rss_after = _resource_rss_snapshot()
        rss_before = span.rss_before
        current_rss_before = span.current_rss_before_kb
        current_delta = (
            None
            if current_rss_before is None or current_rss_after is None
            else int(current_rss_after) - int(current_rss_before)
        )
        sampled_peak = sampler_result.get("sampled_peak_rss_kb")
        event = {
            "index": len(self._stages),
            "name": span.name,
            "status": "failed" if exc is not None else "ok",
            "elapsed_seconds": float(ended - span.started),
            "rss_before": rss_before,
            "rss_after": rss_after,
            "python_current_rss_before_kb": current_rss_before,
            "python_current_rss_after_kb": current_rss_after,
            "python_current_rss_delta_kb": current_delta,
            "python_sampled_peak_rss_kb": sampled_peak,
            "python_rss_sampling": sampler_result,
            "python_self_maxrss_before_kb": int(rss_before["self_maxrss_kb"]),
            "python_self_maxrss_after_kb": int(rss_after["self_maxrss_kb"]),
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
                "python_current_rss_kb": (
                    "current parent Python process RSS from /proc/self/status VmRSS"
                ),
                "python_current_rss_delta_kb": (
                    "stage end current RSS minus stage start current RSS"
                ),
                "python_sampled_peak_rss_kb": (
                    "sampled current RSS peak during the stage when "
                    "SURFACE_CODE_PROFILE_RSS_SAMPLING=1"
                ),
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
        self.current_rss_before_kb: int | None = None
        self._sampler: _CurrentRssSampler | None = None

    def __enter__(self) -> "_StageSpan":
        self.started = time.perf_counter()
        self.rss_before = _resource_rss_snapshot()
        self.current_rss_before_kb = _current_rss_kb()
        if _rss_sampling_enabled():
            self._sampler = _CurrentRssSampler(_rss_sampling_interval_seconds())
            self._sampler.start()
        return self

    def add_result(self, **items: Any) -> None:
        self.result.update(items)

    def stop_sampler(self) -> dict[str, int | bool | None]:
        if self._sampler is None:
            return {
                "enabled": False,
                "sample_count": 0,
                "sampled_peak_rss_kb": None,
                "thread_alive_after_stop": False,
            }
        return self._sampler.stop()

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


def _integral_cache_json_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _pyscf_version() -> str:
    import pyscf

    return str(getattr(pyscf, "__version__", "unknown"))


def _package_version(package_name: str) -> str:
    try:
        return str(importlib_metadata.version(package_name))
    except importlib_metadata.PackageNotFoundError:
        return "not-installed"


def _surface_code_step_dependency_versions() -> dict[str, str]:
    return {
        package_name: _package_version(package_name)
        for package_name in _SURFACE_CODE_STEP_DEPENDENCY_PACKAGES
    }


def _normalized_geometry_for_cache(
    geometry: Sequence[tuple[str, Sequence[float]]],
) -> list[list[Any]]:
    return [
        [str(atom), [float(coord) for coord in coords]]
        for atom, coords in geometry
    ]


def _surface_code_integral_cache_payload(
    *,
    chain_length: int,
    geometry: Sequence[tuple[str, Sequence[float]]],
    distance: float,
    basis: str,
    charge: int,
    multiplicity: int,
    pyscf_version: str,
) -> dict[str, Any]:
    return {
        "schema_version": _SURFACE_CODE_INTEGRAL_CACHE_VERSION,
        "chain_length": int(chain_length),
        "geometry": _normalized_geometry_for_cache(geometry),
        "distance": float(distance),
        "basis": str(basis),
        "charge": int(charge),
        "spin": int(multiplicity) - 1,
        "multiplicity": int(multiplicity),
        "pyscf_version": str(pyscf_version),
    }


def _surface_code_integral_cache_key(payload: Mapping[str, Any]) -> str:
    return _integral_cache_json_hash(payload)


def _surface_code_integral_cache_root(cache_key: str) -> Path:
    return (
        SURFACE_CODE_CACHE_DIR
        / "gr"
        / "integral_cache"
        / str(cache_key)[:2]
        / str(cache_key)
    )


_INTEGRAL_ARRAY_ORDER = ("constant", "one_body", "two_body")


def _update_sha256_with_array_c_order_bytes(
    digest: Any,
    array: np.ndarray,
    *,
    chunk_bytes: int = 1024 * 1024,
) -> None:
    if int(chunk_bytes) <= 0:
        raise ValueError(f"chunk_bytes must be positive: {chunk_bytes}")
    array = np.asarray(array)
    if int(array.nbytes) == 0:
        return
    if array.flags.c_contiguous:
        byte_view = memoryview(array).cast("B")
        for offset in range(0, len(byte_view), int(chunk_bytes)):
            digest.update(byte_view[offset : offset + int(chunk_bytes)])
        return

    itemsize = int(array.dtype.itemsize)
    buffersize = max(1, int(chunk_bytes) // max(1, itemsize))
    iterator = np.nditer(
        array,
        flags=["external_loop", "buffered", "zerosize_ok"],
        op_flags=["readonly"],
        order="C",
        buffersize=buffersize,
    )
    for chunk in iterator:
        chunk_view = memoryview(np.ascontiguousarray(chunk)).cast("B")
        digest.update(chunk_view)


def _surface_code_integral_value_hash(
    *,
    constant: Any,
    one_body: Any,
    two_body: Any,
    chunk_bytes: int = 1024 * 1024,
) -> str:
    digest = hashlib.sha256()
    arrays = {
        "constant": np.asarray(constant),
        "one_body": np.asarray(one_body),
        "two_body": np.asarray(two_body),
    }
    for name in _INTEGRAL_ARRAY_ORDER:
        array = arrays[name]
        header = json.dumps(
            {
                "name": name,
                "dtype": array.dtype.str,
                "shape": list(array.shape),
                "nbytes": int(array.nbytes),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digest.update(len(header).to_bytes(8, "big"))
        digest.update(header)
        digest.update(int(array.nbytes).to_bytes(8, "big"))
        _update_sha256_with_array_c_order_bytes(
            digest,
            array,
            chunk_bytes=chunk_bytes,
        )
    return digest.hexdigest()


def _np_array_metadata(value: Any) -> dict[str, Any]:
    array = np.asarray(value)
    return {
        "shape": list(array.shape),
        "dtype": array.dtype.str,
        "nbytes": int(array.nbytes),
    }


def _surface_code_integral_cache_array_metadata(
    *,
    constant: Any,
    one_body: Any,
    two_body: Any,
) -> dict[str, dict[str, Any]]:
    return {
        "constant": _np_array_metadata(constant),
        "one_body": _np_array_metadata(one_body),
        "two_body": _np_array_metadata(two_body),
    }


def _validate_surface_code_integral_arrays(
    *,
    constant: Any,
    one_body: Any,
    two_body: Any,
    expected_arrays: Mapping[str, Any] | None = None,
    expected_integral_value_hash: str | None = None,
) -> tuple[dict[str, np.ndarray], dict[str, dict[str, Any]], str, str | None]:
    arrays = {
        "constant": np.asarray(constant),
        "one_body": np.asarray(one_body),
        "two_body": np.asarray(two_body),
    }
    metadata = _surface_code_integral_cache_array_metadata(
        constant=arrays["constant"],
        one_body=arrays["one_body"],
        two_body=arrays["two_body"],
    )
    if expected_arrays is not None:
        if not isinstance(expected_arrays, Mapping):
            return arrays, metadata, "", "missing_array_metadata"
        for name in _INTEGRAL_ARRAY_ORDER:
            expected = expected_arrays.get(name)
            if not isinstance(expected, Mapping):
                return arrays, metadata, "", f"missing_{name}_metadata"
            actual = metadata[name]
            if list(actual["shape"]) != list(expected.get("shape", [])):
                return arrays, metadata, "", f"{name}_shape_mismatch"
            if str(actual["dtype"]) != str(expected.get("dtype")):
                return arrays, metadata, "", f"{name}_dtype_mismatch"
            if int(actual["nbytes"]) != int(expected.get("nbytes", -1)):
                return arrays, metadata, "", f"{name}_nbytes_mismatch"

    if list(arrays["constant"].shape) != []:
        return arrays, metadata, "", "constant_shape_mismatch"
    if arrays["one_body"].ndim != 2:
        return arrays, metadata, "", "one_body_shape_mismatch"
    if arrays["one_body"].shape[0] != arrays["one_body"].shape[1]:
        return arrays, metadata, "", "one_body_not_square"
    n_orb = int(arrays["one_body"].shape[0])
    if arrays["two_body"].shape != (n_orb, n_orb, n_orb, n_orb):
        return arrays, metadata, "", "two_body_dimension_mismatch"

    try:
        if not bool(np.isfinite(arrays["constant"]).all()):
            return arrays, metadata, "", "nonfinite_constant"
        if not bool(np.isfinite(arrays["one_body"]).all()):
            return arrays, metadata, "", "nonfinite_one_body"
        if not bool(np.isfinite(arrays["two_body"]).all()):
            return arrays, metadata, "", "nonfinite_two_body"
    except TypeError as exc:
        return arrays, metadata, "", f"invalid:{type(exc).__name__}"

    integral_value_hash = _surface_code_integral_value_hash(
        constant=arrays["constant"],
        one_body=arrays["one_body"],
        two_body=arrays["two_body"],
    )
    if (
        expected_integral_value_hash is not None
        and integral_value_hash != str(expected_integral_value_hash)
    ):
        return arrays, metadata, integral_value_hash, "integral_value_hash_mismatch"
    return arrays, metadata, integral_value_hash, None


def _checked_surface_code_integral_arrays(
    *,
    constant: Any,
    one_body: Any,
    two_body: Any,
) -> tuple[dict[str, np.ndarray], dict[str, dict[str, Any]], str]:
    arrays, metadata, integral_value_hash, invalid_reason = (
        _validate_surface_code_integral_arrays(
            constant=constant,
            one_body=one_body,
            two_body=two_body,
        )
    )
    if invalid_reason is not None:
        raise ValueError(f"Invalid surface-code integrals: {invalid_reason}")
    return arrays, metadata, integral_value_hash


def _write_surface_code_integral_npz_atomic(
    path: Path,
    *,
    constant: Any,
    one_body: Any,
    two_body: Any,
) -> None:
    tmp_path = _atomic_temp_path(path)
    try:
        with tmp_path.open("wb") as f:
            np.savez(
                f,
                constant=np.asarray(constant),
                one_body=np.asarray(one_body),
                two_body=np.asarray(two_body),
            )
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def _load_valid_surface_code_integral_cache(
    *,
    cache_dir: Path,
    cache_key: str,
) -> tuple[Any, np.ndarray | None, np.ndarray | None, dict[str, Any], str | None]:
    metadata_path = cache_dir / "metadata.json"
    npz_path = cache_dir / "integrals.npz"
    if not metadata_path.exists() or not npz_path.exists():
        return None, None, None, {}, "missing"
    try:
        with metadata_path.open("r", encoding="utf-8") as f:
            metadata = json.load(f)
        if not isinstance(metadata, Mapping):
            return None, None, None, {}, "metadata_not_object"
        if metadata.get("schema_version") != _SURFACE_CODE_INTEGRAL_CACHE_VERSION:
            return None, None, None, {}, "schema_version_mismatch"
        if metadata.get("cache_key") != cache_key:
            return None, None, None, {}, "cache_key_mismatch"
        cache_payload = metadata.get("cache_payload")
        if not isinstance(cache_payload, Mapping):
            return None, None, None, {}, "cache_payload_mismatch"
        if _surface_code_integral_cache_key(cache_payload) != cache_key:
            return None, None, None, {}, "cache_payload_mismatch"
        expected_hash = metadata.get("npz_sha256")
        if not isinstance(expected_hash, str):
            return None, None, None, {}, "missing_npz_sha256"
        actual_hash = file_sha256(npz_path)
        if actual_hash != expected_hash:
            return None, None, None, {}, "npz_hash_mismatch"
        expected_arrays = metadata.get("arrays")
        if not isinstance(expected_arrays, Mapping):
            return None, None, None, {}, "missing_array_metadata"
        with np.load(npz_path, allow_pickle=False) as data:
            if set(data.files) != set(_INTEGRAL_ARRAY_ORDER):
                return None, None, None, {}, "npz_keys_mismatch"
            arrays = {
                "constant": data["constant"],
                "one_body": data["one_body"],
                "two_body": data["two_body"],
            }
        expected_integral_value_hash = metadata.get("integral_value_hash")
        if not isinstance(expected_integral_value_hash, str):
            return None, None, None, {}, "missing_integral_value_hash"
        _, _, integral_value_hash, invalid_reason = (
            _validate_surface_code_integral_arrays(
                constant=arrays["constant"],
                one_body=arrays["one_body"],
                two_body=arrays["two_body"],
                expected_arrays=expected_arrays,
                expected_integral_value_hash=expected_integral_value_hash,
            )
        )
        if invalid_reason is not None:
            return None, None, None, {}, invalid_reason
        metadata["integral_value_hash"] = integral_value_hash
        return (
            arrays["constant"][()],
            arrays["one_body"],
            arrays["two_body"],
            dict(metadata),
            None,
        )
    except Exception as exc:
        return None, None, None, {}, f"invalid:{type(exc).__name__}"


def _surface_code_integral_cache_metadata(
    *,
    cache_key: str,
    payload: Mapping[str, Any],
    npz_path: Path,
    constant: Any,
    one_body: Any,
    two_body: Any,
    integral_value_hash: str,
    cache_status: str,
) -> dict[str, Any]:
    arrays = _surface_code_integral_cache_array_metadata(
        constant=constant,
        one_body=one_body,
        two_body=two_body,
    )
    return {
        "schema_version": _SURFACE_CODE_INTEGRAL_CACHE_VERSION,
        "cache_key": cache_key,
        "cache_payload": dict(payload),
        "cache_status": cache_status,
        "created_unix_seconds": time.time(),
        "pyscf_version": str(payload.get("pyscf_version")),
        "integral_value_hash": str(integral_value_hash),
        "arrays": arrays,
        "npz_path": str(npz_path),
        "npz_sha256": file_sha256(npz_path),
        "npz_size_bytes": _file_size_bytes(npz_path),
        "reproducibility_note": (
            "This cache preserves and reuses the first generated integral values for "
            "this exact cache entry. It does not claim that a newly created cache "
            "entry on another environment or run will produce identical values."
        ),
    }


def _compute_surface_code_integrals_uncached(
    chain_length: int,
    *,
    distance: float,
) -> tuple[float, Any, Any]:
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
    if not bool(getattr(mf, "converged", False)):
        raise RuntimeError(
            "PySCF RHF did not converge: "
            f"chain_length={chain_length}, distance={distance}"
        )
    constant = float(mf.energy_nuc())
    mo_coeff = mf.mo_coeff
    h_core = mf.get_hcore()
    one_body = mo_coeff.T @ h_core @ mo_coeff
    eri_mo = pyscf.ao2mo.kernel(mf.mol, mo_coeff)
    eri_mo = pyscf.ao2mo.restore(1, eri_mo, mo_coeff.shape[0])
    two_body = np.asarray(eri_mo.transpose(0, 2, 3, 1), order="C")
    return constant, one_body, two_body


def _resolve_surface_code_integrals(
    chain_length: int,
    *,
    distance: float,
    stage_recorder: _StageMetricsRecorder | None = None,
) -> _ResolvedSurfaceCodeIntegrals:
    from .chemistry_hamiltonian import geo

    geometry, multiplicity, charge = geo(chain_length, distance)
    payload = _surface_code_integral_cache_payload(
        chain_length=chain_length,
        geometry=geometry,
        distance=distance,
        basis=DEFAULT_BASIS,
        charge=charge,
        multiplicity=multiplicity,
        pyscf_version=_pyscf_version(),
    )
    cache_key = _surface_code_integral_cache_key(payload)
    cache_dir = _surface_code_integral_cache_root(cache_key)
    npz_path = cache_dir / "integrals.npz"
    metadata_path = cache_dir / "metadata.json"
    lock_path = cache_dir / "cache.lock"

    if not bool(SURFACE_CODE_INTEGRAL_CACHE_ENABLED):
        with (
            stage_recorder.stage(
                "integral_cache_lookup",
                enabled=False,
                cache_key=cache_key,
                cache_dir=str(cache_dir),
            )
            if stage_recorder is not None
            else _null_stage()
        ) as span:
            span.add_result(
                cache_status="disabled",
                invalid_reason="disabled",
                integral_value_hash=None,
                npz_sha256=None,
                arrays=None,
            )
        with (
            stage_recorder.stage(
                "integral_scf_and_transform",
                cache_status="disabled",
                chain_length=int(chain_length),
                distance=float(distance),
            )
            if stage_recorder is not None
            else _null_stage()
        ) as span:
            constant, one_body, two_body = _compute_surface_code_integrals_uncached(
                chain_length,
                distance=distance,
            )
            arrays, array_metadata, integral_value_hash = (
                _checked_surface_code_integral_arrays(
                    constant=constant,
                    one_body=one_body,
                    two_body=two_body,
                )
            )
            span.add_result(
                cache_status="disabled",
                converged=True,
                pyscf_version=payload["pyscf_version"],
                arrays=array_metadata,
                integral_value_hash=integral_value_hash,
            )
        return _ResolvedSurfaceCodeIntegrals(
            constant=arrays["constant"][()],
            one_body=arrays["one_body"],
            two_body=arrays["two_body"],
            cache_enabled=False,
            schema_version=_SURFACE_CODE_INTEGRAL_CACHE_VERSION,
            cache_key=cache_key,
            integral_value_hash=integral_value_hash,
            cache_status="disabled",
            filled_by_other_process=False,
            initial_invalid_reason="disabled",
            locked_invalid_reason=None,
            cache_dir=cache_dir,
            npz_path=npz_path,
            npz_sha256=None,
        )

    cache_dir.mkdir(parents=True, exist_ok=True)
    constant: Any
    one_body: np.ndarray | None
    two_body: np.ndarray | None
    cached_metadata: dict[str, Any]
    invalid_reason: str | None
    with (
        stage_recorder.stage(
            "integral_cache_lookup",
            enabled=True,
            cache_key=cache_key,
            cache_dir=str(cache_dir),
            npz_path=str(npz_path),
            metadata_path=str(metadata_path),
        )
        if stage_recorder is not None
        else _null_stage()
    ) as span:
        constant, one_body, two_body, cached_metadata, invalid_reason = (
            _load_valid_surface_code_integral_cache(
                cache_dir=cache_dir,
                cache_key=cache_key,
            )
        )
        hit = invalid_reason is None
        span.add_result(
            cache_status="hit" if hit else "miss",
            invalid_reason=invalid_reason,
            npz_size_bytes=_file_size_bytes(npz_path),
            integral_value_hash=cached_metadata.get("integral_value_hash"),
            npz_sha256=cached_metadata.get("npz_sha256"),
            arrays=cached_metadata.get("arrays"),
        )
    if invalid_reason is None:
        assert one_body is not None and two_body is not None
        return _ResolvedSurfaceCodeIntegrals(
            constant=constant,
            one_body=one_body,
            two_body=two_body,
            cache_enabled=True,
            schema_version=_SURFACE_CODE_INTEGRAL_CACHE_VERSION,
            cache_key=cache_key,
            integral_value_hash=str(cached_metadata["integral_value_hash"]),
            cache_status="hit",
            filled_by_other_process=False,
            initial_invalid_reason=None,
            locked_invalid_reason=None,
            cache_dir=cache_dir,
            npz_path=npz_path,
            npz_sha256=str(cached_metadata.get("npz_sha256")),
        )

    with (
        stage_recorder.stage(
            "integral_cache_lock_wait_and_relookup",
            enabled=True,
            cache_key=cache_key,
            cache_dir=str(cache_dir),
            lock_path=str(lock_path),
            initial_invalid_reason=invalid_reason,
        )
        if stage_recorder is not None
        else _null_stage()
    ) as lock_span:
        lock_wait_started = time.perf_counter()
        with _FileLock(lock_path):
            lock_wait_seconds = float(time.perf_counter() - lock_wait_started)
            constant, one_body, two_body, cached_metadata, locked_invalid_reason = (
                _load_valid_surface_code_integral_cache(
                    cache_dir=cache_dir,
                    cache_key=cache_key,
                )
            )
            if locked_invalid_reason is None:
                assert one_body is not None and two_body is not None
                lock_span.add_result(
                    cache_status="hit",
                    filled_by_other_process=True,
                    invalid_reason=None,
                    locked_invalid_reason=None,
                    lock_wait_seconds=lock_wait_seconds,
                    integral_value_hash=cached_metadata.get("integral_value_hash"),
                    npz_sha256=cached_metadata.get("npz_sha256"),
                    npz_size_bytes=_file_size_bytes(npz_path),
                    arrays=cached_metadata.get("arrays"),
                )
                return _ResolvedSurfaceCodeIntegrals(
                    constant=constant,
                    one_body=one_body,
                    two_body=two_body,
                    cache_enabled=True,
                    schema_version=_SURFACE_CODE_INTEGRAL_CACHE_VERSION,
                    cache_key=cache_key,
                    integral_value_hash=str(cached_metadata["integral_value_hash"]),
                    cache_status="hit",
                    filled_by_other_process=True,
                    initial_invalid_reason=invalid_reason,
                    locked_invalid_reason=None,
                    cache_dir=cache_dir,
                    npz_path=npz_path,
                    npz_sha256=str(cached_metadata.get("npz_sha256")),
                )
            lock_span.add_result(
                cache_status="miss",
                invalid_reason=locked_invalid_reason,
                locked_invalid_reason=locked_invalid_reason,
                lock_wait_seconds=lock_wait_seconds,
            )

            with (
                stage_recorder.stage(
                    "integral_scf_and_transform",
                    cache_status="miss",
                    invalid_reason=locked_invalid_reason,
                    chain_length=int(chain_length),
                    distance=float(distance),
                )
                if stage_recorder is not None
                else _null_stage()
            ) as scf_span:
                constant, one_body, two_body = _compute_surface_code_integrals_uncached(
                    chain_length,
                    distance=distance,
                )
                arrays, array_metadata, integral_value_hash = (
                    _checked_surface_code_integral_arrays(
                        constant=constant,
                        one_body=one_body,
                        two_body=two_body,
                    )
                )
                scf_span.add_result(
                    chain_length=int(chain_length),
                    distance=float(distance),
                    pyscf_version=payload["pyscf_version"],
                    converged=True,
                    arrays=array_metadata,
                    integral_value_hash=integral_value_hash,
                )

            with (
                stage_recorder.stage(
                    "integral_cache_write",
                    cache_key=cache_key,
                    cache_dir=str(cache_dir),
                    npz_path=str(npz_path),
                    metadata_path=str(metadata_path),
                )
                if stage_recorder is not None
                else _null_stage()
            ) as write_span:
                _write_surface_code_integral_npz_atomic(
                    npz_path,
                    constant=arrays["constant"],
                    one_body=arrays["one_body"],
                    two_body=arrays["two_body"],
                )
                metadata = _surface_code_integral_cache_metadata(
                    cache_key=cache_key,
                    payload=payload,
                    npz_path=npz_path,
                    constant=arrays["constant"],
                    one_body=arrays["one_body"],
                    two_body=arrays["two_body"],
                    integral_value_hash=integral_value_hash,
                    cache_status="created",
                )
                _atomic_write_json(metadata_path, metadata)
                write_span.add_result(
                    cache_status="created",
                    integral_value_hash=integral_value_hash,
                    npz_sha256=metadata.get("npz_sha256"),
                    npz_size_bytes=_file_size_bytes(npz_path),
                    metadata_size_bytes=_file_size_bytes(metadata_path),
                    arrays=metadata["arrays"],
                )

    return _ResolvedSurfaceCodeIntegrals(
        constant=arrays["constant"][()],
        one_body=arrays["one_body"],
        two_body=arrays["two_body"],
        cache_enabled=True,
        schema_version=_SURFACE_CODE_INTEGRAL_CACHE_VERSION,
        cache_key=cache_key,
        integral_value_hash=integral_value_hash,
        cache_status="miss",
        filled_by_other_process=False,
        initial_invalid_reason=invalid_reason,
        locked_invalid_reason=locked_invalid_reason,
        cache_dir=cache_dir,
        npz_path=npz_path,
        npz_sha256=str(metadata.get("npz_sha256")),
    )


def _surface_code_integrals(
    chain_length: int,
    *,
    distance: float,
    stage_recorder: _StageMetricsRecorder | None = None,
) -> tuple[Any, Any, Any]:
    resolved = _resolve_surface_code_integrals(
        chain_length,
        distance=distance,
        stage_recorder=stage_recorder,
    )
    return resolved.constant, resolved.one_body, resolved.two_body


def _build_grouped_surface_code_step_circuit_from_integrals(
    ham_name: str,
    pf_label: PFLabel,
    *,
    step_time: float,
    constant: Any,
    one_body: Any,
    two_body: Any,
) -> Any:
    from openfermion import InteractionOperator
    from openfermion.chem.molecular_data import spinorb_from_spatial
    from openfermion.transforms import get_fermion_operator, jordan_wigner
    from qiskit import QuantumCircuit

    from .chemistry_hamiltonian import min_hamiltonian_grouper
    from .qiskit_time_evolution_grouping import w_trotter_grouper
    from .qiskit_time_evolution_pyscf import _build_grouped_jw_list

    chain_length = _parse_hchain_length(ham_name)

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


def build_grouped_surface_code_step_circuit(
    ham_name: str,
    pf_label: PFLabel,
    *,
    step_time: float,
    stage_recorder: _StageMetricsRecorder | None = None,
) -> Any:
    chain_length = _parse_hchain_length(ham_name)
    resolved = _resolve_surface_code_integrals(
        chain_length,
        distance=_parse_distance(ham_name),
        stage_recorder=stage_recorder,
    )
    return _build_grouped_surface_code_step_circuit_from_integrals(
        ham_name,
        pf_label,
        step_time=step_time,
        constant=resolved.constant,
        one_body=resolved.one_body,
        two_body=resolved.two_body,
    )


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
_IR_METADATA_NORMALIZATION_VERSION = "ir_metadata_normalization_v1"
_IR_STREAM_SUMMARY_VERSION = "ir_instruction_stream_summary_v1"
_PYTHON_INLINE_IR_VERSION = "python_streaming_inline_ir_v1"
_RZ_HELPER_INDEPENDENT_CACHE_VERSION = "rz_helper_independent_cache_v2"
_RZ_HELPER_OPT_MODES = {"legacy_full_ir", "independent_helper"}
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

    metadata_created_at_normalized = False
    metadata = data.get("metadata")
    if isinstance(metadata, dict) and "created_at" in metadata:
        if metadata.get("created_at") != "1970-01-01T00:00:00":
            metadata_created_at_normalized = True
        metadata["created_at"] = "1970-01-01T00:00:00"

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
        "metadata_normalization_version": _IR_METADATA_NORMALIZATION_VERSION,
        "metadata_created_at_normalized": bool(metadata_created_at_normalized),
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
    if use_gnu_time:
        env["LC_ALL"] = "C"
        env["LANG"] = "C"
        env.pop("LANGUAGE", None)
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


def opt_pipeline_yaml_functions(
    *,
    ir_path: Path,
    opt_path: Path,
    passes: Sequence[str],
    entry_names: Sequence[str],
) -> str:
    names = [str(name) for name in entry_names]
    if not names:
        raise ValueError("entry_names must be non-empty")
    effective_passes = list(passes)
    return "\n".join(
        [
            f"input: {ir_path}",
            "functions:",
            *[f"- {json.dumps(name, ensure_ascii=True)}" for name in names],
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
    circuit_overrides: Mapping[str, Mapping[str, Any]] | None = None,
    incremental_input: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    if incremental_input:
        return _python_inline_ir_incremental(
            input_ir_path,
            output_ir_path,
            function_name=function_name,
            circuit_overrides=circuit_overrides,
            started=started,
        )

    with input_ir_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    overrides = dict(circuit_overrides or {})
    if function_name in overrides:
        raise ValueError(f"Override for entry function '{function_name}' is not supported")
    for name, circuit in overrides.items():
        if not isinstance(name, str):
            raise ValueError("Override function names must be strings")
        if not isinstance(circuit, Mapping):
            raise ValueError(f"Override for '{name}' must be a mapping")
        if circuit.get("name") != name:
            raise ValueError(
                f"Override circuit name mismatch for '{name}': {circuit.get('name')!r}"
            )

    def function_record(name: str, circuit: Mapping[str, Any]) -> dict[str, Any]:
        bb_list = circuit.get("bb_list")
        argument = circuit.get("argument")
        if not isinstance(argument, Mapping):
            raise ValueError(f"Missing argument for {name}")
        if not isinstance(bb_list, list) or len(bb_list) != 1:
            raise ValueError(f"Python inliner only supports one basic block: {name}")
        inst_list = bb_list[0].get("inst_list", [])
        if not isinstance(inst_list, list):
            raise ValueError(f"Invalid inst_list for {name}")
        num_qubits = int(argument.get("num_qubits", 0))
        if num_qubits < 0:
            raise ValueError(f"Invalid num_qubits={num_qubits} for {name}")
        return {
            "inst_list": inst_list,
            "num_qubits": num_qubits,
        }

    top_level_fields = {key: value for key, value in data.items() if key != "circuit_list"}
    functions: dict[str, dict[str, Any]] = {}
    target_circuit_fields: dict[str, Any] | None = None
    target_bb_fields: dict[str, Any] | None = None
    input_function_names: set[str] = set()
    circuit_list = data.get("circuit_list", [])
    if not isinstance(circuit_list, list):
        raise ValueError(f"Invalid circuit_list in {input_ir_path}")
    for circuit in circuit_list:
        if not isinstance(circuit, Mapping):
            continue
        name = circuit.get("name")
        if not isinstance(name, str):
            continue
        if name in input_function_names:
            raise ValueError(f"Duplicate circuit name in input IR: {name}")
        input_function_names.add(name)
        source_circuit = overrides.get(name, circuit)
        functions[name] = function_record(name, source_circuit)
        if name == function_name:
            bb_list = circuit.get("bb_list")
            if not isinstance(bb_list, list) or len(bb_list) != 1:
                raise ValueError(f"Python inliner only supports one basic block: {name}")
            target_circuit_fields = {
                key: value for key, value in circuit.items() if key != "bb_list"
            }
            target_bb_fields = {
                key: value for key, value in bb_list[0].items() if key != "inst_list"
            }

    for name, circuit in overrides.items():
        if name not in functions:
            functions[name] = function_record(name, circuit)
    if function_name not in functions or target_circuit_fields is None:
        raise ValueError(f"Circuit '{function_name}' not found in {input_ir_path}")
    if target_bb_fields is None:
        raise ValueError(f"Missing entry block for '{function_name}' in {input_ir_path}")
    del data
    del circuit_list

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
        used_overrides: set[str],
    ) -> Any:
        if name in stack:
            raise ValueError("Recursive Call cycle detected: " + " -> ".join((*stack, name)))
        function = functions.get(name)
        if function is None:
            raise ValueError(f"Unknown callee '{name}'")
        if name in overrides:
            used_overrides.add(name)
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
                yield from iter_unrolled(
                    callee,
                    child_map,
                    (*stack, name),
                    used_overrides,
                )
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
        target = dict(target_circuit_fields or {})
        target_bb = dict(target_bb_fields or {})
        num_qubits = int(functions[function_name]["num_qubits"])
        used_overrides: set[str] = set()

        with tmp_path.open("w", encoding="utf-8") as f:
            f.write("{")
            first_top = True
            for key, value in top_level_fields.items():
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
            for inst in iter_unrolled(
                function_name,
                list(range(num_qubits)),
                (),
                used_overrides,
            ):
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
        unused_overrides = sorted(set(overrides) - used_overrides)
        if unused_overrides:
            raise ValueError(
                "Override circuit(s) were not used during inline: "
                + ", ".join(unused_overrides)
            )

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
        "circuit_override_count": int(len(overrides)),
        "input_mode": "json_load",
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


class _IncrementalJsonReader:
    def __init__(
        self,
        path: Path,
        *,
        chunk_size: int = 65536,
        compact_threshold: int = 65536,
    ) -> None:
        self._path = path
        self._file = path.open("r", encoding="utf-8")
        self._decoder = json.JSONDecoder()
        self._chunk_size = int(chunk_size)
        self._compact_threshold = int(compact_threshold)
        self._buffer = ""
        self._pos = 0
        self._eof = False
        self.max_buffer_chars = 0

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> "_IncrementalJsonReader":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def _compact(self) -> None:
        if self._pos > self._compact_threshold:
            self._buffer = self._buffer[self._pos :]
            self._pos = 0

    def _fill(self) -> bool:
        if self._eof:
            return False
        chunk = self._file.read(self._chunk_size)
        if not chunk:
            self._eof = True
            return False
        self._buffer += chunk
        self.max_buffer_chars = max(self.max_buffer_chars, len(self._buffer))
        return True

    def _ensure_char(self) -> bool:
        while self._pos >= len(self._buffer):
            if not self._fill():
                return False
        return True

    def skip_ws(self) -> None:
        while True:
            while self._pos < len(self._buffer) and self._buffer[self._pos].isspace():
                self._pos += 1
            self._compact()
            if self._pos < len(self._buffer) or not self._fill():
                return

    def peek(self) -> str:
        self.skip_ws()
        if not self._ensure_char():
            raise ValueError(f"Unexpected end of JSON while reading {self._path}")
        return self._buffer[self._pos]

    def consume_if(self, expected: str) -> bool:
        if self.peek() == expected:
            self._pos += len(expected)
            self._compact()
            return True
        return False

    def expect(self, expected: str) -> None:
        actual = self.peek()
        if actual != expected:
            raise ValueError(
                f"Expected {expected!r} while reading {self._path}, got {actual!r}"
            )
        self._pos += len(expected)
        self._compact()

    def decode_value(self) -> Any:
        self.skip_ws()
        while True:
            try:
                value, end = self._decoder.raw_decode(self._buffer, self._pos)
            except json.JSONDecodeError:
                if self._eof:
                    raise
                self._fill()
                continue
            self._pos = int(end)
            self._compact()
            return value

    def decode_string(self) -> str:
        value = self.decode_value()
        if not isinstance(value, str):
            raise ValueError(f"Expected JSON string while reading {self._path}")
        return value

    def object_members(self) -> Any:
        self.expect("{")
        if self.consume_if("}"):
            return
        while True:
            key = self.decode_string()
            self.expect(":")
            yield key
            if self.consume_if(","):
                continue
            self.expect("}")
            break

    def array_items(self) -> Any:
        self.expect("[")
        if self.consume_if("]"):
            return
        index = 0
        while True:
            yield index
            index += 1
            if self.consume_if(","):
                continue
            self.expect("]")
            break


def _inline_function_record(name: str, circuit: Mapping[str, Any]) -> dict[str, Any]:
    bb_list = circuit.get("bb_list")
    argument = circuit.get("argument")
    if not isinstance(argument, Mapping):
        raise ValueError(f"Missing argument for {name}")
    if not isinstance(bb_list, list) or len(bb_list) != 1:
        raise ValueError(f"Python inliner only supports one basic block: {name}")
    inst_list = bb_list[0].get("inst_list", [])
    if not isinstance(inst_list, list):
        raise ValueError(f"Invalid inst_list for {name}")
    num_qubits = int(argument.get("num_qubits", 0))
    if num_qubits < 0:
        raise ValueError(f"Invalid num_qubits={num_qubits} for {name}")
    return {
        "inst_list": inst_list,
        "num_qubits": num_qubits,
    }


def _validate_inline_overrides(
    circuit_overrides: Mapping[str, Mapping[str, Any]] | None,
    *,
    function_name: str,
) -> dict[str, Mapping[str, Any]]:
    overrides = dict(circuit_overrides or {})
    if function_name in overrides:
        raise ValueError(f"Override for entry function '{function_name}' is not supported")
    for name, circuit in overrides.items():
        if not isinstance(name, str):
            raise ValueError("Override function names must be strings")
        if not isinstance(circuit, Mapping):
            raise ValueError(f"Override for '{name}' must be a mapping")
        if circuit.get("name") != name:
            raise ValueError(
                f"Override circuit name mismatch for '{name}': {circuit.get('name')!r}"
            )
        _inline_function_record(name, circuit)
    return overrides


def _write_json_field(
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


def _inline_map_qubit(qubit_map: Sequence[int], value: Any) -> int:
    if not qubit_map:
        return int(value)
    return int(qubit_map[int(value)])


def _inline_mapped_instruction(
    inst: Mapping[str, Any],
    qubit_map: Sequence[int],
) -> dict[str, Any]:
    opcode = str(inst.get("opcode"))
    new_inst = dict(inst)
    if opcode in _INLINE_ONE_QUBIT_OPS:
        new_inst["q"] = _inline_map_qubit(qubit_map, new_inst["q"])
    elif opcode in _INLINE_TWO_QUBIT_OPS:
        new_inst["q0"] = _inline_map_qubit(qubit_map, new_inst["q0"])
        new_inst["q1"] = _inline_map_qubit(qubit_map, new_inst["q1"])
    elif opcode in _INLINE_THREE_QUBIT_OPS:
        new_inst["q0"] = _inline_map_qubit(qubit_map, new_inst["q0"])
        new_inst["q1"] = _inline_map_qubit(qubit_map, new_inst["q1"])
        new_inst["q2"] = _inline_map_qubit(qubit_map, new_inst["q2"])
    else:
        raise ValueError(f"Unsupported opcode '{opcode}'")
    return new_inst


def _python_inline_ir_incremental(
    input_ir_path: Path,
    output_ir_path: Path,
    *,
    function_name: str,
    circuit_overrides: Mapping[str, Mapping[str, Any]] | None,
    started: float,
) -> dict[str, Any]:
    overrides = _validate_inline_overrides(
        circuit_overrides,
        function_name=function_name,
    )
    functions: dict[str, dict[str, Any]] = {
        name: _inline_function_record(name, circuit)
        for name, circuit in overrides.items()
    }
    input_function_names: set[str] = set()
    target_circuit_fields: dict[str, Any] | None = None
    target_bb_fields: dict[str, Any] | None = None
    top_level_fields: dict[str, Any] = {}
    main_num_qubits: int | None = None
    used_overrides: set[str] = set()
    emitted_any = False

    def emit_flat_instruction(f: Any, recorder: _InstructionStreamRecorder, inst: Mapping[str, Any]) -> None:
        nonlocal emitted_any
        if emitted_any:
            f.write(",")
        json.dump(dict(inst), f, ensure_ascii=True, separators=(",", ":"))
        recorder.observe(inst)
        emitted_any = True

    def emit_from_function(
        f: Any,
        recorder: _InstructionStreamRecorder,
        name: str,
        qubit_map: Sequence[int],
        stack: tuple[str, ...],
    ) -> None:
        if name in stack:
            raise ValueError("Recursive Call cycle detected: " + " -> ".join((*stack, name)))
        function = functions.get(name)
        if function is None:
            raise ValueError(f"Unknown callee '{name}'")
        if name in overrides:
            used_overrides.add(name)
        for inst in function["inst_list"]:
            if not isinstance(inst, Mapping):
                continue
            emit_from_instruction(f, recorder, inst, qubit_map, (*stack, name))

    def emit_from_instruction(
        f: Any,
        recorder: _InstructionStreamRecorder,
        inst: Mapping[str, Any],
        qubit_map: Sequence[int],
        stack: tuple[str, ...],
    ) -> None:
        opcode = str(inst.get("opcode"))
        if opcode == "Call":
            callee = inst.get("callee")
            operate = inst.get("operate")
            if not isinstance(callee, str) or not isinstance(operate, list):
                raise ValueError(f"Invalid Call in {stack[-1] if stack else function_name}")
            child_map = [_inline_map_qubit(qubit_map, q) for q in operate]
            emit_from_function(f, recorder, callee, child_map, stack)
            return
        if opcode in _INLINE_IGNORED_OPS:
            return
        emit_flat_instruction(
            f,
            recorder,
            _inline_mapped_instruction(inst, qubit_map),
        )

    def parse_main_inst_list(
        reader: _IncrementalJsonReader,
        f: Any,
        recorder: _InstructionStreamRecorder,
        *,
        emit: bool,
    ) -> None:
        for _index in reader.array_items():
            inst = reader.decode_value()
            if emit and isinstance(inst, Mapping):
                emit_from_instruction(f, recorder, inst, (), (function_name,))

    def parse_main_bb_list(
        reader: _IncrementalJsonReader,
        f: Any,
        recorder: _InstructionStreamRecorder,
        *,
        collect_metadata: bool,
        emit: bool,
    ) -> dict[str, Any]:
        bb_fields: dict[str, Any] | None = None
        for index in reader.array_items():
            if index != 0:
                raise ValueError(f"Python inliner only supports one basic block: {function_name}")
            current_bb: dict[str, Any] = {}
            saw_inst_list = False
            for key in reader.object_members():
                if key == "inst_list":
                    saw_inst_list = True
                    parse_main_inst_list(reader, f, recorder, emit=emit)
                else:
                    value = reader.decode_value()
                    if collect_metadata:
                        current_bb[key] = value
            if not saw_inst_list:
                raise ValueError(f"Invalid inst_list for {function_name}")
            bb_fields = current_bb
        if bb_fields is None:
            raise ValueError(f"Python inliner only supports one basic block: {function_name}")
        return bb_fields

    def parse_circuit_list(
        reader: _IncrementalJsonReader,
        f: Any,
        recorder: _InstructionStreamRecorder,
        *,
        collect_metadata: bool,
        emit_main: bool,
    ) -> None:
        nonlocal target_circuit_fields, target_bb_fields, main_num_qubits
        for _index in reader.array_items():
            circuit_name: str | None = None
            is_main = False
            circuit_fields: dict[str, Any] = {}
            saw_bb_list = False
            for key in reader.object_members():
                if key == "name":
                    value = reader.decode_value()
                    if not isinstance(value, str):
                        raise ValueError("Circuit name must be a string")
                    if collect_metadata:
                        if value in input_function_names:
                            raise ValueError(f"Duplicate circuit name in input IR: {value}")
                        input_function_names.add(value)
                    circuit_name = value
                    is_main = value == function_name
                    if collect_metadata:
                        circuit_fields[key] = value
                    continue
                if key == "bb_list":
                    if circuit_name is None:
                        raise ValueError(
                            "Circuit name must appear before bb_list for incremental inline"
                        )
                    saw_bb_list = True
                    if is_main:
                        parsed_bb_fields = parse_main_bb_list(
                            reader,
                            f,
                            recorder,
                            collect_metadata=collect_metadata,
                            emit=emit_main,
                        )
                        if collect_metadata:
                            target_bb_fields = parsed_bb_fields
                    else:
                        value = reader.decode_value()
                        if collect_metadata and circuit_name not in overrides:
                            circuit_fields[key] = value
                    continue
                value = reader.decode_value()
                if collect_metadata and (
                    is_main
                    or circuit_name is None
                    or circuit_name not in overrides
                ):
                    circuit_fields[key] = value
                    if is_main and key == "argument":
                        if not isinstance(value, Mapping):
                            raise ValueError(f"Missing argument for {function_name}")
                        parsed_num_qubits = int(value.get("num_qubits", 0))
                        if parsed_num_qubits < 0:
                            raise ValueError(
                                f"Invalid num_qubits={parsed_num_qubits} for {function_name}"
                            )
                        main_num_qubits = parsed_num_qubits
            if circuit_name is None:
                raise ValueError("Circuit without name in input IR")
            if collect_metadata and is_main:
                if not saw_bb_list:
                    raise ValueError(f"Missing entry block for '{function_name}' in {input_ir_path}")
                argument = circuit_fields.get("argument")
                if not isinstance(argument, Mapping):
                    raise ValueError(f"Missing argument for {function_name}")
                parsed_num_qubits = int(argument.get("num_qubits", 0))
                if parsed_num_qubits < 0:
                    raise ValueError(
                        f"Invalid num_qubits={parsed_num_qubits} for {function_name}"
                    )
                main_num_qubits = parsed_num_qubits
                target_circuit_fields = circuit_fields
            elif collect_metadata and circuit_name not in overrides:
                functions[circuit_name] = _inline_function_record(
                    circuit_name,
                    circuit_fields,
                )

    output_ir_path.parent.mkdir(parents=True, exist_ok=True)
    output_tmp = _atomic_temp_path(output_ir_path)
    inst_tmp = _atomic_temp_path(output_ir_path.with_name(output_ir_path.name + ".inst"))
    try:
        with _IncrementalJsonReader(input_ir_path) as reader:
            for key in reader.object_members():
                if key == "circuit_list":
                    parse_circuit_list(
                        reader,
                        f=None,
                        recorder=_InstructionStreamRecorder(num_qubits=0),
                        collect_metadata=True,
                        emit_main=False,
                    )
                else:
                    top_level_fields[key] = reader.decode_value()
            if target_circuit_fields is None or main_num_qubits is None:
                raise ValueError(f"Circuit '{function_name}' not found in {input_ir_path}")
            if target_bb_fields is None:
                raise ValueError(f"Missing entry block for '{function_name}' in {input_ir_path}")
            first_pass_max_buffer_chars = reader.max_buffer_chars

        recorder = _InstructionStreamRecorder(num_qubits=main_num_qubits)
        with (
            _IncrementalJsonReader(input_ir_path) as reader,
            inst_tmp.open("w", encoding="utf-8") as inst_file,
        ):
            for key in reader.object_members():
                if key == "circuit_list":
                    parse_circuit_list(
                        reader,
                        inst_file,
                        recorder,
                        collect_metadata=False,
                        emit_main=True,
                    )
                else:
                    reader.decode_value()
            return_inst = {"opcode": "Return"}
            emit_flat_instruction(inst_file, recorder, return_inst)
            max_buffer_chars = max(first_pass_max_buffer_chars, reader.max_buffer_chars)

        unused_overrides = sorted(set(overrides) - used_overrides)
        if unused_overrides:
            raise ValueError(
                "Override circuit(s) were not used during inline: "
                + ", ".join(unused_overrides)
            )

        with output_tmp.open("w", encoding="utf-8") as out:
            out.write("{")
            first_top = True
            for key, value in top_level_fields.items():
                first_top = _write_json_field(out, str(key), value, first=first_top)
            if not first_top:
                out.write(",")
            json.dump("circuit_list", out, ensure_ascii=True, separators=(",", ":"))
            out.write(":[{")

            first_circuit = True
            for key, value in target_circuit_fields.items():
                if key == "bb_list":
                    continue
                first_circuit = _write_json_field(
                    out,
                    str(key),
                    value,
                    first=first_circuit,
                )
            if not first_circuit:
                out.write(",")
            json.dump("bb_list", out, ensure_ascii=True, separators=(",", ":"))
            out.write(":[{")

            first_bb = True
            for key, value in target_bb_fields.items():
                if key == "inst_list":
                    continue
                first_bb = _write_json_field(out, str(key), value, first=first_bb)
            if not first_bb:
                out.write(",")
            json.dump("inst_list", out, ensure_ascii=True, separators=(",", ":"))
            out.write(":[")
            with inst_tmp.open("r", encoding="utf-8") as inst_file:
                for chunk in iter(lambda: inst_file.read(1024 * 1024), ""):
                    out.write(chunk)
            out.write("]}]}]}")

        os.replace(output_tmp, output_ir_path)
    except Exception:
        try:
            output_tmp.unlink()
        except FileNotFoundError:
            pass
        raise
    finally:
        try:
            inst_tmp.unlink()
        except FileNotFoundError:
            pass

    stream_summary = recorder.summary()
    return {
        "version": _PYTHON_INLINE_IR_VERSION,
        "input_path": str(input_ir_path),
        "output_path": str(output_ir_path),
        "function_name": function_name,
        "circuit_override_count": int(len(overrides)),
        "input_mode": "incremental_json",
        "incremental_parser": {
            "backend": "json.JSONDecoder.raw_decode",
            "max_buffer_chars": int(max_buffer_chars),
        },
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


def _rz_helper_opt_mode() -> str:
    mode = str(SURFACE_CODE_RZ_HELPER_OPT_MODE)
    if mode not in _RZ_HELPER_OPT_MODES:
        raise ValueError(
            f"Unsupported SURFACE_CODE_RZ_HELPER_OPT_MODE={mode!r}; "
            f"expected one of {sorted(_RZ_HELPER_OPT_MODES)}"
        )
    return mode


def _rz_helper_batch_size() -> int:
    try:
        batch_size = int(SURFACE_CODE_RZ_HELPER_BATCH_SIZE)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "SURFACE_CODE_RZ_HELPER_BATCH_SIZE must be an integer >= 1"
        ) from exc
    if batch_size < 1:
        raise ValueError(
            "SURFACE_CODE_RZ_HELPER_BATCH_SIZE must be an integer >= 1"
        )
    return batch_size


def _rz_helper_passes() -> list[str]:
    return [
        "ir::decompose_inst",
        "ir::ignore_global_phase",
        "ir::delete_consecutive_same_pauli",
        "ir::delete_opt_hint",
    ]


def _rz_main_cleanup_passes() -> list[str]:
    return [
        "ir::static_condition_pruning",
        "ir::ignore_global_phase",
        "ir::delete_consecutive_same_pauli",
        "ir::delete_opt_hint",
    ]


def _canonical_json_hash(value: Any) -> str:
    encoded = json.dumps(
        _canonical_json_value(value),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _ir_circuit_by_name(data: Mapping[str, Any], function_name: str) -> Mapping[str, Any]:
    for circuit in data.get("circuit_list", []):
        if isinstance(circuit, Mapping) and circuit.get("name") == function_name:
            return circuit
    raise KeyError(f"Circuit '{function_name}' not found")


def _single_circuit_ir(data: Mapping[str, Any], function_name: str) -> dict[str, Any]:
    target = _ir_circuit_by_name(data, function_name)
    small = {key: value for key, value in data.items() if key != "circuit_list"}
    small["circuit_list"] = [target]
    return small


def _helper_input_ir_cache_value(helper_input_ir: Mapping[str, Any]) -> Any:
    value = _canonical_json_value(helper_input_ir)
    if isinstance(value, dict):
        metadata = value.get("metadata")
        if isinstance(metadata, dict):
            stable_metadata = dict(metadata)
            stable_metadata.pop("created_at", None)
            value["metadata"] = stable_metadata
        circuit_list = value.get("circuit_list")
        if (
            isinstance(circuit_list, list)
            and len(circuit_list) == 1
            and isinstance(circuit_list[0], dict)
        ):
            stable_circuit = dict(circuit_list[0])
            stable_circuit["name"] = "__rz_helper_cache_entry__()"
            value["circuit_list"] = [stable_circuit]
    return value


def _write_compact_json_atomic(path: Path, payload: Any) -> None:
    _atomic_write_json(path, payload, indent=None)


def _load_ir_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid IR JSON: {path}")
    return data


def _helper_circuit_summary(circuit: Mapping[str, Any]) -> dict[str, Any]:
    argument = circuit.get("argument")
    if not isinstance(argument, Mapping):
        raise ValueError(f"Missing argument for helper circuit {circuit.get('name')}")
    bb_list = circuit.get("bb_list")
    if not isinstance(bb_list, list) or len(bb_list) != 1:
        raise ValueError(f"Expected one basic block for helper circuit {circuit.get('name')}")
    inst_list = bb_list[0].get("inst_list", [])
    if not isinstance(inst_list, list):
        raise ValueError(f"Invalid inst_list for helper circuit {circuit.get('name')}")
    recorder = _InstructionStreamRecorder(
        num_qubits=int(argument.get("num_qubits", 0))
    )
    for inst in inst_list:
        if isinstance(inst, Mapping):
            recorder.observe(inst)
    stream = recorder.summary()
    opcode_count = dict(stream["opcode_count"])
    t_count = int(opcode_count.get("T", 0)) + int(opcode_count.get("TDag", 0))
    return {
        "instruction_stream": stream,
        "normalized_instruction_stream_hash": stream[
            "normalized_instruction_stream_hash"
        ],
        "opcode_count": opcode_count,
        "emitted_instruction_count": int(stream["emitted_instruction_count"]),
        "scheduled_instruction_count": int(stream["scheduled_instruction_count"]),
        "t_count": t_count,
        "gate_depth": int(stream["gate_depth"]),
        "step_magic_state_count": int(stream["step_magic_state_count"]),
        "step_magic_state_depth": int(stream["step_magic_state_depth"]),
        "peak_magic_layer": int(stream["peak_magic_layer"]),
    }


def _helper_output_summary(path: Path, function_name: str) -> dict[str, Any]:
    data = _load_ir_json(path)
    circuit = _ir_circuit_by_name(data, function_name)
    return _helper_circuit_summary(circuit)


def _single_ir_circuit(data: Mapping[str, Any]) -> Mapping[str, Any]:
    circuits = [
        circuit
        for circuit in data.get("circuit_list", [])
        if isinstance(circuit, Mapping)
    ]
    if len(circuits) != 1:
        raise ValueError(f"Expected one circuit, found {len(circuits)}")
    return circuits[0]


def _renamed_helper_circuit(
    circuit: Mapping[str, Any],
    function_name: str,
) -> dict[str, Any]:
    renamed = dict(circuit)
    renamed["name"] = function_name
    return renamed


def _replace_ir_circuits(
    data: Mapping[str, Any],
    replacements: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    out = {key: value for key, value in data.items() if key != "circuit_list"}
    circuits: list[Any] = []
    for circuit in data.get("circuit_list", []):
        if isinstance(circuit, Mapping) and isinstance(circuit.get("name"), str):
            replacement = replacements.get(str(circuit["name"]))
            circuits.append(dict(replacement) if replacement is not None else circuit)
        else:
            circuits.append(circuit)
    out["circuit_list"] = circuits
    return out


def _gridsynth_cache_identity() -> dict[str, Any]:
    path = Path(SURFACE_CODE_GRIDSYNTH_PATH).expanduser().resolve()
    return {
        "path": str(path),
        "hash": file_sha256(path) if path.exists() else None,
        "exists": path.exists(),
    }


def _rz_helper_cache_payload(
    *,
    helper_input_hash: str,
    helper: Mapping[str, Any],
    rotation_precision: float,
    qret_hash: str,
    helper_passes: Sequence[str],
) -> dict[str, Any]:
    return {
        "schema_version": _RZ_HELPER_INDEPENDENT_CACHE_VERSION,
        "helper_input_ir_hash": str(helper_input_hash),
        "theta": helper.get("theta"),
        "rotation_precision": float(rotation_precision),
        "qret_hash": str(qret_hash),
        "gridsynth": _gridsynth_cache_identity(),
        "passes": list(helper_passes),
        "ignore_global_phase": "ir::ignore_global_phase" in set(helper_passes),
    }


def _rz_helper_cache_key(payload: Mapping[str, Any]) -> str:
    return _canonical_json_hash(payload)


def _rz_helper_cache_root(cache_key: str) -> Path:
    return (
        SURFACE_CODE_CACHE_DIR
        / "gr"
        / "rz_helper_independent_cache"
        / str(cache_key)[:2]
        / str(cache_key)
    )


@dataclass(frozen=True)
class _RZHelperDescriptor:
    helper_index: int
    function_name: str
    helper: Mapping[str, Any]
    helper_input_ir: Mapping[str, Any]
    helper_input_hash: str
    cache_payload: Mapping[str, Any]
    cache_key: str
    cache_dir: Path

    @property
    def input_path(self) -> Path:
        return self.cache_dir / "helper_input.json"

    @property
    def output_path(self) -> Path:
        return self.cache_dir / "helper_opt.json"

    @property
    def metadata_path(self) -> Path:
        return self.cache_dir / "metadata.json"

    @property
    def lock_path(self) -> Path:
        return self.cache_dir / "cache.lock"


def _rz_helper_descriptor(
    *,
    full_ir_data: Mapping[str, Any],
    helper: Mapping[str, Any],
    helper_index: int,
    rotation_precision: float,
    qret_hash: str,
    helper_passes: Sequence[str],
) -> _RZHelperDescriptor:
    function_name = str(helper["function_name"])
    helper_input_ir = _single_circuit_ir(full_ir_data, function_name)
    helper_input_hash = _canonical_json_hash(
        _helper_input_ir_cache_value(helper_input_ir)
    )
    payload = _rz_helper_cache_payload(
        helper_input_hash=helper_input_hash,
        helper=helper,
        rotation_precision=rotation_precision,
        qret_hash=qret_hash,
        helper_passes=helper_passes,
    )
    cache_key = _rz_helper_cache_key(payload)
    cache_dir = _rz_helper_cache_root(cache_key)
    cache_dir.mkdir(parents=True, exist_ok=True)
    return _RZHelperDescriptor(
        helper_index=int(helper_index),
        function_name=function_name,
        helper=helper,
        helper_input_ir=helper_input_ir,
        helper_input_hash=helper_input_hash,
        cache_payload=payload,
        cache_key=cache_key,
        cache_dir=cache_dir,
    )


def _single_helper_output_ir(
    batch_output_ir: Mapping[str, Any],
    circuit: Mapping[str, Any],
) -> dict[str, Any]:
    out = {key: value for key, value in batch_output_ir.items() if key != "circuit_list"}
    out["circuit_list"] = [circuit]
    return out


def _batch_helper_input_ir(
    full_ir_data: Mapping[str, Any],
    descriptors: Sequence[_RZHelperDescriptor],
) -> dict[str, Any]:
    out = {key: value for key, value in full_ir_data.items() if key != "circuit_list"}
    circuits: list[Any] = []
    for descriptor in descriptors:
        circuit_list = descriptor.helper_input_ir.get("circuit_list", [])
        if not isinstance(circuit_list, list) or len(circuit_list) != 1:
            raise ValueError(
                f"Invalid helper input IR for {descriptor.function_name}"
            )
        circuits.append(circuit_list[0])
    out["circuit_list"] = circuits
    return out


def _chunked_sequence(
    items: Sequence[_RZHelperDescriptor],
    size: int,
) -> list[list[_RZHelperDescriptor]]:
    if size < 1:
        raise ValueError("chunk size must be >= 1")
    return [list(items[index : index + size]) for index in range(0, len(items), size)]


def _load_valid_rz_helper_cache(
    *,
    cache_dir: Path,
    cache_key: str,
    function_name: str,
) -> tuple[Mapping[str, Any], dict[str, Any], str | None]:
    metadata_path = cache_dir / "metadata.json"
    output_path = cache_dir / "helper_opt.json"
    if not metadata_path.exists() or not output_path.exists():
        return {}, {}, "missing"
    try:
        metadata = _load_ir_json(metadata_path)
        if metadata.get("cache_key") != cache_key:
            return {}, {}, "cache_key_mismatch"
        cached_summary = metadata.get("output_summary")
        if not isinstance(cached_summary, Mapping):
            return {}, {}, "missing_output_summary"
        output = _load_ir_json(output_path)
        try:
            circuit = _ir_circuit_by_name(output, function_name)
        except KeyError:
            circuit = _single_ir_circuit(output)
        actual_summary = _helper_circuit_summary(circuit)
        if _canonical_json_hash(cached_summary) != _canonical_json_hash(actual_summary):
            return {}, {}, "output_summary_mismatch"
        return _renamed_helper_circuit(circuit, function_name), dict(metadata), None
    except Exception as exc:
        return {}, {}, f"invalid:{type(exc).__name__}"


def _rz_helper_cache_hit_metadata(
    *,
    helper_index: int,
    function_name: str,
    cache_key: str,
    cache_dir: Path,
    cached_metadata: Mapping[str, Any],
    filled_by_other_process: bool = False,
) -> dict[str, Any]:
    metadata = {
        "helper_index": int(helper_index),
        "function_name": function_name,
        "cache_key": cache_key,
        "cache_status": "hit",
        "cache_dir": str(cache_dir),
        "output_summary": dict(cached_metadata.get("output_summary", {})),
    }
    if filled_by_other_process:
        metadata["filled_by_other_process"] = True
    return metadata


def _optimize_rz_helper_independent_cached(
    *,
    qret_path: Path,
    runtime_root: Path,
    full_ir_data: Mapping[str, Any],
    helper: Mapping[str, Any],
    helper_index: int,
    rotation_precision: float,
    qret_hash: str,
    helper_passes: Sequence[str],
    stage_recorder: _StageMetricsRecorder | None,
) -> tuple[Mapping[str, Any], dict[str, Any]]:
    function_name = str(helper["function_name"])
    helper_input_ir = _single_circuit_ir(full_ir_data, function_name)
    helper_input_hash = _canonical_json_hash(
        _helper_input_ir_cache_value(helper_input_ir)
    )
    payload = _rz_helper_cache_payload(
        helper_input_hash=helper_input_hash,
        helper=helper,
        rotation_precision=rotation_precision,
        qret_hash=qret_hash,
        helper_passes=helper_passes,
    )
    cache_key = _rz_helper_cache_key(payload)
    cache_dir = _rz_helper_cache_root(cache_key)
    cache_dir.mkdir(parents=True, exist_ok=True)

    cached_circuit: Mapping[str, Any]
    cached_metadata: dict[str, Any]
    invalid_reason: str | None
    with (
        stage_recorder.stage(
            f"rz_helper_independent_cache_lookup_{helper_index:04d}",
            helper_index=int(helper_index),
            helper_function_name=function_name,
            helper_key=helper.get("key"),
            helper_theta=helper.get("theta"),
            cache_key=cache_key,
            cache_dir=str(cache_dir),
        )
        if stage_recorder is not None
        else _null_stage()
    ) as span:
        cached_circuit, cached_metadata, invalid_reason = _load_valid_rz_helper_cache(
            cache_dir=cache_dir,
            cache_key=cache_key,
            function_name=function_name,
        )
        hit = invalid_reason is None
        span.add_result(
            cache_status="hit" if hit else "miss",
            invalid_reason=invalid_reason,
        )
    if invalid_reason is None:
        return cached_circuit, _rz_helper_cache_hit_metadata(
            helper_index=helper_index,
            function_name=function_name,
            cache_key=cache_key,
            cache_dir=cache_dir,
            cached_metadata=cached_metadata,
        )

    input_path = cache_dir / "helper_input.json"
    output_path = cache_dir / "helper_opt.json"
    metadata_path = cache_dir / "metadata.json"
    lock_path = cache_dir / "cache.lock"
    with (
        stage_recorder.stage(
            f"rz_helper_independent_cache_lock_{helper_index:04d}",
            helper_index=int(helper_index),
            helper_function_name=function_name,
            helper_key=helper.get("key"),
            helper_theta=helper.get("theta"),
            cache_key=cache_key,
            cache_dir=str(cache_dir),
            lock_path=str(lock_path),
            initial_invalid_reason=invalid_reason,
        )
        if stage_recorder is not None
        else _null_stage()
    ) as lock_span:
        with _FileLock(lock_path):
            cached_circuit, cached_metadata, locked_invalid_reason = (
                _load_valid_rz_helper_cache(
                    cache_dir=cache_dir,
                    cache_key=cache_key,
                    function_name=function_name,
                )
            )
            if locked_invalid_reason is None:
                lock_span.add_result(
                    cache_status="hit",
                    filled_by_other_process=True,
                    invalid_reason=None,
                )
                return cached_circuit, _rz_helper_cache_hit_metadata(
                    helper_index=helper_index,
                    function_name=function_name,
                    cache_key=cache_key,
                    cache_dir=cache_dir,
                    cached_metadata=cached_metadata,
                    filled_by_other_process=True,
                )

            lock_span.add_result(
                cache_status="miss",
                invalid_reason=locked_invalid_reason,
            )
            output_tmp = _atomic_temp_path(output_path)
            yaml_tmp = _atomic_temp_path(cache_dir / "helper_opt.yaml")
            try:
                try:
                    output_tmp.unlink()
                except FileNotFoundError:
                    pass
                _write_compact_json_atomic(input_path, helper_input_ir)
                yaml_tmp.write_text(
                    opt_pipeline_yaml(
                        ir_path=input_path,
                        opt_path=output_tmp,
                        passes=helper_passes,
                        entry_name=function_name,
                    ),
                    encoding="utf-8",
                )
                qret_metrics = _run_qret(
                    [str(qret_path), "opt", "--pipeline", str(yaml_tmp), "--verbose"],
                    runtime_root=cache_dir,
                    rotation_precision=rotation_precision,
                    stage_recorder=stage_recorder,
                    stage_name=f"qret_opt_rz_helper_independent_{helper_index:04d}",
                    stage_details={
                        "helper_index": int(helper_index),
                        "helper_function_name": function_name,
                        "helper_key": helper.get("key"),
                        "helper_theta": helper.get("theta"),
                        "cache_key": cache_key,
                        "cache_status": "miss",
                        "invalid_reason": locked_invalid_reason,
                        "input_path": str(input_path),
                        "output_path": str(output_tmp),
                        "pipeline_path": str(yaml_tmp),
                    },
                )
                output_summary = _helper_output_summary(output_tmp, function_name)
                os.replace(output_tmp, output_path)
                metadata = {
                    "schema_version": _RZ_HELPER_INDEPENDENT_CACHE_VERSION,
                    "cache_key": cache_key,
                    "cache_payload": payload,
                    "cache_status": "created",
                    "created_unix_seconds": time.time(),
                    "helper_index": int(helper_index),
                    "function_name": function_name,
                    "input_path": str(input_path),
                    "output_path": str(output_path),
                    "input_size_bytes": _file_size_bytes(input_path),
                    "output_size_bytes": _file_size_bytes(output_path),
                    "output_summary": output_summary,
                    "qret_metrics": qret_metrics,
                }
                _atomic_write_json(metadata_path, metadata)
            finally:
                for tmp_path in (output_tmp, yaml_tmp):
                    try:
                        tmp_path.unlink()
                    except FileNotFoundError:
                        pass

    output_data = _load_ir_json(output_path)
    circuit = _ir_circuit_by_name(output_data, function_name)
    run_metadata = {
        "helper_index": int(helper_index),
        "function_name": function_name,
        "cache_key": cache_key,
        "cache_status": "miss",
        "invalid_reason": locked_invalid_reason,
        "cache_dir": str(cache_dir),
        "input_size_bytes": _file_size_bytes(input_path),
        "output_size_bytes": _file_size_bytes(output_path),
        "output_summary": output_summary,
        "qret_metrics": qret_metrics,
    }
    return circuit, run_metadata


def _optimize_rz_helpers_independent_cached_batch(
    *,
    qret_path: Path,
    runtime_root: Path,
    full_ir_data: Mapping[str, Any],
    helpers: Sequence[Mapping[str, Any]],
    rotation_precision: float,
    qret_hash: str,
    helper_passes: Sequence[str],
    batch_size: int,
    stage_recorder: _StageMetricsRecorder | None,
) -> tuple[dict[str, Mapping[str, Any]], list[dict[str, Any]]]:
    configured_batch_size = int(batch_size)
    if configured_batch_size < 1:
        raise ValueError("batch_size must be >= 1")

    descriptors = [
        _rz_helper_descriptor(
            full_ir_data=full_ir_data,
            helper=helper,
            helper_index=index,
            rotation_precision=rotation_precision,
            qret_hash=qret_hash,
            helper_passes=helper_passes,
        )
        for index, helper in enumerate(helpers)
    ]
    replacements: dict[str, Mapping[str, Any]] = {}
    helper_results: list[dict[str, Any] | None] = [None] * len(descriptors)
    initial_misses: list[tuple[_RZHelperDescriptor, str | None]] = []

    for descriptor in descriptors:
        cached_circuit: Mapping[str, Any]
        cached_metadata: dict[str, Any]
        invalid_reason: str | None
        with (
            stage_recorder.stage(
                f"rz_helper_independent_cache_lookup_{descriptor.helper_index:04d}",
                helper_index=int(descriptor.helper_index),
                helper_function_name=descriptor.function_name,
                helper_key=descriptor.helper.get("key"),
                helper_theta=descriptor.helper.get("theta"),
                cache_key=descriptor.cache_key,
                cache_dir=str(descriptor.cache_dir),
            )
            if stage_recorder is not None
            else _null_stage()
        ) as span:
            cached_circuit, cached_metadata, invalid_reason = (
                _load_valid_rz_helper_cache(
                    cache_dir=descriptor.cache_dir,
                    cache_key=descriptor.cache_key,
                    function_name=descriptor.function_name,
                )
            )
            hit = invalid_reason is None
            span.add_result(
                cache_status="hit" if hit else "miss",
                invalid_reason=invalid_reason,
            )
        if invalid_reason is None:
            replacements[descriptor.function_name] = cached_circuit
            helper_results[descriptor.helper_index] = _rz_helper_cache_hit_metadata(
                helper_index=descriptor.helper_index,
                function_name=descriptor.function_name,
                cache_key=descriptor.cache_key,
                cache_dir=descriptor.cache_dir,
                cached_metadata=cached_metadata,
            )
        else:
            initial_misses.append((descriptor, invalid_reason))

    unique_misses: list[_RZHelperDescriptor] = []
    seen_cache_keys: set[str] = set()
    duplicate_misses = 0
    for descriptor, _ in initial_misses:
        if descriptor.cache_key in seen_cache_keys:
            duplicate_misses += 1
            continue
        seen_cache_keys.add(descriptor.cache_key)
        unique_misses.append(descriptor)

    batches = _chunked_sequence(unique_misses, configured_batch_size)
    with (
        stage_recorder.stage(
            "rz_helper_batch_plan",
            configured_batch_size=configured_batch_size,
            helper_count=len(descriptors),
            initial_miss_count=len(initial_misses),
            unique_miss_count=len(unique_misses),
            duplicate_cache_key_miss_count=duplicate_misses,
            batch_count=len(batches),
        )
        if stage_recorder is not None
        else _null_stage()
    ) as span:
        span.add_result(
            initial_hit_count=len(descriptors) - len(initial_misses),
            planned_qret_invocation_count=len(batches),
        )

    batch_runtime = runtime_root / "rz_call_cache" / "helper_batches"
    batch_runtime.mkdir(parents=True, exist_ok=True)
    for batch_index, batch in enumerate(batches):
        lock_stack = contextlib.ExitStack()
        still_miss: list[tuple[_RZHelperDescriptor, str | None]] = []
        filled_by_other = 0
        try:
            with (
                stage_recorder.stage(
                    f"rz_helper_batch_lock_{batch_index:04d}",
                    batch_index=int(batch_index),
                    configured_batch_size=configured_batch_size,
                    planned_helper_count=len(batch),
                    function_names=[item.function_name for item in batch],
                    cache_keys=[item.cache_key for item in batch],
                )
                if stage_recorder is not None
                else _null_stage()
            ) as lock_span:
                for descriptor in sorted(batch, key=lambda item: item.cache_key):
                    lock_stack.enter_context(_FileLock(descriptor.lock_path))
                for descriptor in batch:
                    cached_circuit, cached_metadata, locked_invalid_reason = (
                        _load_valid_rz_helper_cache(
                            cache_dir=descriptor.cache_dir,
                            cache_key=descriptor.cache_key,
                            function_name=descriptor.function_name,
                        )
                    )
                    if locked_invalid_reason is None:
                        replacements[descriptor.function_name] = cached_circuit
                        helper_results[descriptor.helper_index] = (
                            _rz_helper_cache_hit_metadata(
                                helper_index=descriptor.helper_index,
                                function_name=descriptor.function_name,
                                cache_key=descriptor.cache_key,
                                cache_dir=descriptor.cache_dir,
                                cached_metadata=cached_metadata,
                                filled_by_other_process=True,
                            )
                        )
                        filled_by_other += 1
                    else:
                        still_miss.append((descriptor, locked_invalid_reason))
                lock_span.add_result(
                    lock_acquired_count=len(batch),
                    filled_by_other_process_count=filled_by_other,
                    still_miss_count=len(still_miss),
                )

            if not still_miss:
                continue

            still_descriptors = [item[0] for item in still_miss]
            for descriptor in still_descriptors:
                _write_compact_json_atomic(
                    descriptor.input_path,
                    descriptor.helper_input_ir,
                )

            batch_input = _atomic_temp_path(
                batch_runtime / f"rz_helper_batch_{batch_index:04d}_input.json"
            )
            batch_output = _atomic_temp_path(
                batch_runtime / f"rz_helper_batch_{batch_index:04d}_output.json"
            )
            batch_yaml = _atomic_temp_path(
                batch_runtime / f"rz_helper_batch_{batch_index:04d}.yaml"
            )
            try:
                batch_input.write_text(
                    json.dumps(
                        _batch_helper_input_ir(full_ir_data, still_descriptors),
                        ensure_ascii=True,
                        separators=(",", ":"),
                    ),
                    encoding="utf-8",
                )
                batch_yaml.write_text(
                    opt_pipeline_yaml_functions(
                        ir_path=batch_input,
                        opt_path=batch_output,
                        passes=helper_passes,
                        entry_names=[
                            descriptor.function_name
                            for descriptor in still_descriptors
                        ],
                    ),
                    encoding="utf-8",
                )
                qret_metrics = _run_qret(
                    [str(qret_path), "opt", "--pipeline", str(batch_yaml), "--verbose"],
                    runtime_root=batch_runtime,
                    rotation_precision=rotation_precision,
                    stage_recorder=stage_recorder,
                    stage_name=f"qret_opt_rz_helper_batch_{batch_index:04d}",
                    stage_details={
                        "batch_index": int(batch_index),
                        "configured_batch_size": configured_batch_size,
                        "planned_helper_count": len(batch),
                        "still_miss_count": len(still_descriptors),
                        "function_names": [
                            descriptor.function_name
                            for descriptor in still_descriptors
                        ],
                        "cache_keys": [
                            descriptor.cache_key for descriptor in still_descriptors
                        ],
                        "input_path": str(batch_input),
                        "output_path": str(batch_output),
                        "pipeline_path": str(batch_yaml),
                        "input_size_bytes": _file_size_bytes(batch_input),
                    },
                )
                with (
                    stage_recorder.stage(
                        f"rz_helper_batch_validate_{batch_index:04d}",
                        batch_index=int(batch_index),
                        function_names=[
                            descriptor.function_name
                            for descriptor in still_descriptors
                        ],
                    )
                    if stage_recorder is not None
                    else _null_stage()
                ) as validate_span:
                    batch_output_ir = _load_ir_json(batch_output)
                    validated: list[
                        tuple[
                            _RZHelperDescriptor,
                            Mapping[str, Any],
                            dict[str, Any],
                            dict[str, Any],
                            str | None,
                        ]
                    ] = []
                    for descriptor, locked_invalid_reason in still_miss:
                        circuit = _ir_circuit_by_name(
                            batch_output_ir,
                            descriptor.function_name,
                        )
                        output_summary = _helper_circuit_summary(circuit)
                        single_output = _single_helper_output_ir(
                            batch_output_ir,
                            circuit,
                        )
                        validated.append(
                            (
                                descriptor,
                                circuit,
                                single_output,
                                output_summary,
                                locked_invalid_reason,
                            )
                        )
                    validate_span.add_result(
                        validated_count=len(validated),
                        output_size_bytes=_file_size_bytes(batch_output),
                    )

                with (
                    stage_recorder.stage(
                        f"rz_helper_batch_commit_{batch_index:04d}",
                        batch_index=int(batch_index),
                        function_names=[
                            descriptor.function_name
                            for descriptor in still_descriptors
                        ],
                    )
                    if stage_recorder is not None
                    else _null_stage()
                ) as commit_span:
                    for (
                        descriptor,
                        circuit,
                        single_output,
                        output_summary,
                        locked_invalid_reason,
                    ) in validated:
                        _write_compact_json_atomic(
                            descriptor.output_path,
                            single_output,
                        )
                        metadata = {
                            "schema_version": _RZ_HELPER_INDEPENDENT_CACHE_VERSION,
                            "cache_key": descriptor.cache_key,
                            "cache_payload": dict(descriptor.cache_payload),
                            "cache_status": "created",
                            "created_unix_seconds": time.time(),
                            "helper_index": int(descriptor.helper_index),
                            "function_name": descriptor.function_name,
                            "input_path": str(descriptor.input_path),
                            "output_path": str(descriptor.output_path),
                            "input_size_bytes": _file_size_bytes(
                                descriptor.input_path
                            ),
                            "output_size_bytes": _file_size_bytes(
                                descriptor.output_path
                            ),
                            "output_summary": output_summary,
                            "qret_metrics": qret_metrics,
                            "batch": {
                                "batch_index": int(batch_index),
                                "configured_batch_size": configured_batch_size,
                                "still_miss_count": len(still_descriptors),
                            },
                        }
                        _atomic_write_json(descriptor.metadata_path, metadata)
                        replacements[descriptor.function_name] = circuit
                        helper_results[descriptor.helper_index] = {
                            "helper_index": int(descriptor.helper_index),
                            "function_name": descriptor.function_name,
                            "cache_key": descriptor.cache_key,
                            "cache_status": "miss",
                            "invalid_reason": locked_invalid_reason,
                            "cache_dir": str(descriptor.cache_dir),
                            "input_size_bytes": _file_size_bytes(
                                descriptor.input_path
                            ),
                            "output_size_bytes": _file_size_bytes(
                                descriptor.output_path
                            ),
                            "output_summary": output_summary,
                            "qret_metrics": qret_metrics,
                            "batch_index": int(batch_index),
                            "configured_batch_size": configured_batch_size,
                        }
                    commit_span.add_result(committed_count=len(validated))
            finally:
                for tmp_path in (batch_input, batch_output, batch_yaml):
                    try:
                        tmp_path.unlink()
                    except FileNotFoundError:
                        pass
        finally:
            lock_stack.close()

    for descriptor in descriptors:
        if helper_results[descriptor.helper_index] is not None:
            continue
        cached_circuit, cached_metadata, invalid_reason = _load_valid_rz_helper_cache(
            cache_dir=descriptor.cache_dir,
            cache_key=descriptor.cache_key,
            function_name=descriptor.function_name,
        )
        if invalid_reason is not None:
            raise RuntimeError(
                f"RZ helper cache entry was not generated for "
                f"{descriptor.function_name}: {invalid_reason}"
            )
        replacements[descriptor.function_name] = cached_circuit
        metadata = _rz_helper_cache_hit_metadata(
            helper_index=descriptor.helper_index,
            function_name=descriptor.function_name,
            cache_key=descriptor.cache_key,
            cache_dir=descriptor.cache_dir,
            cached_metadata=cached_metadata,
        )
        metadata["duplicate_cache_key"] = True
        helper_results[descriptor.helper_index] = metadata

    return replacements, [dict(item) for item in helper_results if item is not None]


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
        return {
            "mode": "qret_opt_without_rz_helpers",
            "helper_opt_mode": _rz_helper_opt_mode(),
        }

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
    helper_passes = _rz_helper_passes()
    helper_opt_mode = _rz_helper_opt_mode()
    qret_hash = file_sha256(qret_path)
    helper_cache_results: list[dict[str, Any]] = []
    circuit_overrides: Mapping[str, Mapping[str, Any]] | None = None
    helper_integration_mode = "legacy_full_ir"
    if helper_opt_mode == "legacy_full_ir":
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
            qret_metrics = _run_qret(
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
                    "helper_opt_mode": helper_opt_mode,
                    "input_path": str(current_input),
                    "output_path": str(pass_output),
                    "pipeline_path": str(pass_yaml),
                },
            )
            helper_cache_results.append(
                {
                    "helper_index": int(index),
                    "function_name": str(helper["function_name"]),
                    "cache_status": "legacy_full_ir",
                    "qret_metrics": qret_metrics,
                }
            )
            current_input = pass_output
    else:
        helper_integration_mode = "python_inline_overrides"
        with (
            stage_recorder.stage("load_rz_helper_full_ir", input_path=str(ir_path))
            if stage_recorder is not None
            else _null_stage()
        ) as span:
            full_ir_data = _load_ir_json(ir_path)
            span.add_result(
                input_size_bytes=_file_size_bytes(ir_path),
                circuit_count=len(full_ir_data.get("circuit_list", [])),
            )
        replacements: dict[str, Mapping[str, Any]] = {}
        helper_batch_size = _rz_helper_batch_size()
        if helper_batch_size == 1:
            for index, helper in enumerate(helpers):
                helper_circuit, helper_result = _optimize_rz_helper_independent_cached(
                    qret_path=qret_path,
                    runtime_root=runtime_root,
                    full_ir_data=full_ir_data,
                    helper=helper,
                    helper_index=index,
                    rotation_precision=rotation_precision,
                    qret_hash=qret_hash,
                    helper_passes=helper_passes,
                    stage_recorder=stage_recorder,
                )
                replacements[str(helper["function_name"])] = helper_circuit
                helper_cache_results.append(helper_result)
        else:
            replacements, helper_cache_results = (
                _optimize_rz_helpers_independent_cached_batch(
                    qret_path=qret_path,
                    runtime_root=runtime_root,
                    full_ir_data=full_ir_data,
                    helpers=helpers,
                    rotation_precision=rotation_precision,
                    qret_hash=qret_hash,
                    helper_passes=helper_passes,
                    batch_size=helper_batch_size,
                    stage_recorder=stage_recorder,
                )
            )
        circuit_overrides = replacements
        with (
            stage_recorder.stage(
                "prepare_rz_helper_overrides",
                input_path=str(ir_path),
                helper_integration_mode=helper_integration_mode,
            )
            if stage_recorder is not None
            else _null_stage()
        ) as span:
            span.add_result(
                helper_override_count=len(replacements),
                source_ir_size_bytes=_file_size_bytes(ir_path),
                old_merged_ir_generated=False,
                integration_mode=helper_integration_mode,
                helper_batch_size=helper_batch_size,
            )
        del full_ir_data
        try:
            del helper_circuit
        except UnboundLocalError:
            pass

    main_pre_inline = cache_dir / "main_before_python_inline.json"
    main_yaml = cache_dir / "main_cleanup.yaml"
    main_yaml.write_text(
        opt_pipeline_yaml(
            ir_path=current_input,
            opt_path=main_pre_inline,
            passes=_rz_main_cleanup_passes(),
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
            "input_size_bytes": _file_size_bytes(current_input),
            "output_path": str(main_pre_inline),
            "pipeline_path": str(main_yaml),
            "helper_opt_mode": helper_opt_mode,
            "helper_integration_mode": helper_integration_mode,
        },
    )
    with (
        stage_recorder.stage(
            "python_streaming_inline",
            input_path=str(main_pre_inline),
            output_path=str(opt_path),
            helper_override_count=len(circuit_overrides or {}),
            input_size_bytes=_file_size_bytes(main_pre_inline),
        )
        if stage_recorder is not None
        else _null_stage()
    ) as span:
        inline_summary = _python_inline_ir(
            main_pre_inline,
            opt_path,
            function_name="main",
            circuit_overrides=circuit_overrides,
            incremental_input=bool(circuit_overrides),
        )
        span.add_result(
            helper_override_count=len(circuit_overrides or {}),
            input_mode=inline_summary.get("input_mode"),
            input_size_bytes=_file_size_bytes(main_pre_inline),
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
        "helper_opt_mode": helper_opt_mode,
        "helper_integration_mode": helper_integration_mode,
        "helper_count": int(len(helpers)),
        "helper_batch_size": (
            _rz_helper_batch_size()
            if helper_opt_mode == "independent_helper"
            else None
        ),
        "helper_cache": {
            "hit_count": sum(
                1 for item in helper_cache_results if item.get("cache_status") == "hit"
            ),
            "miss_count": sum(
                1 for item in helper_cache_results if item.get("cache_status") == "miss"
            ),
            "legacy_full_ir_count": sum(
                1
                for item in helper_cache_results
                if item.get("cache_status") == "legacy_full_ir"
            ),
            "helpers": helper_cache_results,
        },
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
    integral_cache_enabled: bool,
    integral_cache_schema_version: str,
    integral_cache_key: str,
    integral_value_hash: str,
) -> str:
    payload = {
        "step_artifact_cache_schema_version": _SURFACE_CODE_STEP_ARTIFACT_CACHE_VERSION,
        "circuit_generation_version": _SURFACE_CODE_CIRCUIT_GENERATION_VERSION,
        "ham_name": ham_name,
        "pf_label": pf_label,
        "target_error": float(target_error),
        "step_time": float(step_time),
        "rotation_precision": float(rotation_precision),
        "qret_hash": qret_hash,
        "integral_cache_enabled": bool(integral_cache_enabled),
        "integral_cache_schema_version": str(integral_cache_schema_version),
        "integral_cache_key": str(integral_cache_key),
        "integral_value_hash": str(integral_value_hash),
        "qasm_basis_gates": list(SURFACE_CODE_QASM_BASIS_GATES),
        "qasm_decompose_reps": int(SURFACE_CODE_QASM_DECOMPOSE_REPS),
        "rz_call_cache": bool(SURFACE_CODE_RZ_CALL_CACHE),
        "rz_call_cache_round_digits": SURFACE_CODE_RZ_CALL_CACHE_ROUND_DIGITS,
        "rz_helper_opt_mode": _rz_helper_opt_mode(),
        "rz_helper_independent_cache": _RZ_HELPER_INDEPENDENT_CACHE_VERSION,
        "ir_rotation_precision_rewrite": _IR_ROTATION_PRECISION_REWRITE_VERSION,
        "ir_metadata_normalization": _IR_METADATA_NORMALIZATION_VERSION,
        "ir_stream_summary": _IR_STREAM_SUMMARY_VERSION,
        "python_inline_ir": _PYTHON_INLINE_IR_VERSION,
        "dependency_versions": _surface_code_step_dependency_versions(),
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
    integral_cache_enabled: bool,
    integral_cache_schema_version: str,
    integral_cache_key: str,
    integral_value_hash: str,
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
            integral_cache_enabled=integral_cache_enabled,
            integral_cache_schema_version=integral_cache_schema_version,
            integral_cache_key=integral_cache_key,
            integral_value_hash=integral_value_hash,
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
            "rz_helper_opt_mode": _rz_helper_opt_mode(),
            "rz_helper_batch_size": _rz_helper_batch_size(),
            "integral_cache_enabled": bool(SURFACE_CODE_INTEGRAL_CACHE_ENABLED),
            "integral_cache_schema_version": _SURFACE_CODE_INTEGRAL_CACHE_VERSION,
            "step_artifact_cache_schema_version": (
                _SURFACE_CODE_STEP_ARTIFACT_CACHE_VERSION
            ),
            "circuit_generation_version": _SURFACE_CODE_CIRCUIT_GENERATION_VERSION,
            "dependency_versions": _surface_code_step_dependency_versions(),
        },
    )
    stage_metrics_path: Path | None = None
    stage_files: dict[str, Path] = {}

    try:
        resolved_integrals = _resolve_surface_code_integrals(
            _parse_hchain_length(ham_name),
            distance=_parse_distance(ham_name),
            stage_recorder=stage_recorder,
        )
        runtime_root = _step_artifact_runtime_root(
            ham_name,
            pf_label,
            target_error=target_error,
            step_time=step_t,
            rotation_precision=rot_precision,
            qret_hash=qret_hash,
            integral_cache_enabled=resolved_integrals.cache_enabled,
            integral_cache_schema_version=resolved_integrals.schema_version,
            integral_cache_key=resolved_integrals.cache_key,
            integral_value_hash=resolved_integrals.integral_value_hash,
        )
        runtime_root.mkdir(parents=True, exist_ok=True)

        qasm_path = runtime_root / "step.qasm"
        ir_path = runtime_root / "step_ir.json"
        opt_path = runtime_root / "step_opt.json"
        stage_metrics_path = runtime_root / _PREPARE_STAGE_METRICS_FILENAME
        stage_cache_hit_metrics_path = (
            runtime_root / _PREPARE_STAGE_CACHE_HIT_METRICS_FILENAME
        )
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

        with stage_recorder.stage("cache_lookup") as span:
            cached_artifact = load_prepared_surface_code_step_artifact(runtime_root)
            span.add_result(cache_hit=cached_artifact is not None)
        if cached_artifact is not None:
            stage_recorder.write(
                stage_cache_hit_metrics_path,
                status="cache_hit",
                files=stage_files,
                extra={
                    "cold_run_stage_metrics_path": str(stage_metrics_path),
                    "cold_run_stage_metrics_exists": stage_metrics_path.exists(),
                },
            )
            return cached_artifact

        with stage_recorder.stage("build_step_circuit") as span:
            qc = _build_grouped_surface_code_step_circuit_from_integrals(
                ham_name,
                pf_label,
                step_time=step_t,
                constant=resolved_integrals.constant,
                one_body=resolved_integrals.one_body,
                two_body=resolved_integrals.two_body,
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
            integral_cache=resolved_integrals.provenance(),
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
        if stage_metrics_path is not None:
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
    compile_yaml_path = runtime_root / "compile.yaml"
    step_metrics_path = runtime_root / "step_metrics.json"
    stage_metrics_path = runtime_root / _COMPILE_STAGE_METRICS_FILENAME
    stage_cache_hit_metrics_path = (
        runtime_root / _COMPILE_STAGE_CACHE_HIT_METRICS_FILENAME
    )
    stage_files = {
        "optimized_ir": artifact.optimized_ir_path,
        "compile_pipeline": compile_yaml_path,
        "compile_info": compile_info_path,
        "compile_output": None
        if architecture.skip_compile_output
        else compile_output_path,
        "step_metrics": step_metrics_path,
    }
    stage_recorder = _StageMetricsRecorder(
        scope="compile_prepared_surface_code_step_artifact",
        metadata={
            "ham_name": artifact.ham_name,
            "molecule": artifact.molecule,
            "pf_label": artifact.pf_label,
            "target_error": float(artifact.target_error),
            "step_time": float(artifact.step_time),
            "rotation_precision": float(artifact.rotation_precision),
            "compile_mode": architecture.compile_mode,
            "qret_path": str(qret_path),
            "qret_hash": file_sha256(qret_path),
            "topology_path": str(topology_path)
            if _compile_uses_topology(architecture.compile_mode)
            else None,
            "topology_hash": file_sha256(topology_path)
            if _compile_uses_topology(architecture.compile_mode)
            else None,
            "architecture": architecture.to_dict(),
            "mapping_routing_stage_granularity": (
                "qret exposes mapping/routing elapsed only as part of qret_compile"
            ),
        },
    )

    started = time.perf_counter()
    cache_hit = False
    try:
        with stage_recorder.stage(
            "compile_cache_lookup",
            compile_info_path=str(compile_info_path),
        ) as span:
            cache_hit = bool(reuse_cache and compile_info_path.exists())
            span.add_result(cache_hit=cache_hit)
        if not cache_hit:
            with stage_recorder.stage(
                "compile_pipeline_generate",
                input_path=str(artifact.optimized_ir_path),
                output_path=str(compile_output_path),
                compile_info_path=str(compile_info_path),
            ) as span:
                compile_yaml = compile_pipeline_yaml(
                    opt_path=artifact.optimized_ir_path,
                    compile_output_path=compile_output_path,
                    compile_info_path=compile_info_path,
                    architecture=architecture,
                )
                span.add_result(
                    pipeline_bytes=len(compile_yaml.encode("utf-8")),
                    input_size_bytes=_file_size_bytes(artifact.optimized_ir_path),
                )
            with stage_recorder.stage(
                "write_compile_pipeline",
                output_path=str(compile_yaml_path),
            ) as span:
                yaml_tmp = _atomic_temp_path(compile_yaml_path)
                try:
                    yaml_tmp.write_text(compile_yaml, encoding="utf-8")
                    os.replace(yaml_tmp, compile_yaml_path)
                except Exception:
                    try:
                        yaml_tmp.unlink()
                    except FileNotFoundError:
                        pass
                    raise
                span.add_result(output_size_bytes=_file_size_bytes(compile_yaml_path))
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
                stage_recorder=stage_recorder,
                stage_name="qret_compile",
                stage_details={
                    "input_path": str(artifact.optimized_ir_path),
                    "output_path": str(compile_output_path),
                    "compile_info_path": str(compile_info_path),
                    "pipeline_path": str(compile_yaml_path),
                    "compile_mode": architecture.compile_mode,
                    "mapping_routing_elapsed_available": False,
                },
            )
        elapsed = float(time.perf_counter() - started)

        if architecture.save_mapping_result:
            with stage_recorder.stage("save_mapping_result") as span:
                mapping_metadata = save_surface_code_mapping_result(
                    artifact=artifact,
                    architecture=architecture,
                    runtime_root=runtime_root,
                    reuse_cache=reuse_cache,
                )
                span.add_result(**mapping_metadata)
        else:
            mapping_metadata = {
                "mapping_result_json": None,
                "mapping_result_hash": None,
                "mapping_result_unavailable_reason": "disabled",
            }

        with stage_recorder.stage(
            "read_compile_info_json",
            input_path=str(compile_info_path),
        ) as span:
            with compile_info_path.open("r", encoding="utf-8") as f:
                compile_info = json.load(f)
            compile_info_field_count = (
                len(compile_info) if isinstance(compile_info, Mapping) else None
            )
            span.add_result(
                input_size_bytes=_file_size_bytes(compile_info_path),
                field_count=compile_info_field_count,
            )
        with stage_recorder.stage("normalize_compile_info") as span:
            metrics = normalize_surface_code_step_metrics(
                compile_info,
                context=str(compile_info_path.resolve()),
            )
            metrics["compile_info_json"] = str(compile_info_path.resolve())
            span.add_result(
                normalized_field_count=len(metrics),
                magic_state_consumption_count=metrics.get(
                    "magic_state_consumption_count"
                ),
                runtime=metrics.get("runtime"),
                runtime_without_topology=metrics.get("runtime_without_topology"),
            )

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
        with stage_recorder.stage("normalize_step_metrics") as span:
            normalized = normalize_surface_code_step_metrics(
                metrics,
                context=f"{artifact.ham_name}_Operator_{artifact.pf_label}",
            )
            span.add_result(normalized_field_count=len(normalized))
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
        with stage_recorder.stage("collect_compile_outputs") as span:
            span.add_result(
                compile_info_size_bytes=_file_size_bytes(compile_info_path),
                compile_output_size_bytes=(
                    None
                    if architecture.skip_compile_output
                    else _file_size_bytes(compile_output_path)
                ),
                qret_compile_granularity=(
                    "mapping, routing, and QEC resource estimation are included "
                    "inside qret_compile unless qret exposes finer metrics"
                ),
            )
        with stage_recorder.stage("write_step_metrics") as span:
            _atomic_write_json(step_metrics_path, normalized)
            span.add_result(output_size_bytes=_file_size_bytes(step_metrics_path))

        write_path = stage_cache_hit_metrics_path if cache_hit else stage_metrics_path
        stage_recorder.write(
            write_path,
            status="cache_hit" if cache_hit else "ok",
            files=stage_files,
            extra={
                "cold_run_stage_metrics_path": str(stage_metrics_path),
                "cold_run_stage_metrics_exists": stage_metrics_path.exists(),
                "compile_cache_hit": bool(cache_hit),
            }
            if cache_hit
            else {"compile_cache_hit": bool(cache_hit)},
        )
        return normalized
    except Exception:
        try:
            stage_recorder.write(
                stage_metrics_path,
                status="failed",
                files=stage_files,
                extra={
                    "compile_cache_hit": bool(cache_hit),
                    "failed_stage_recorded": any(
                        item.get("status") == "failed"
                        for item in stage_recorder.summary(status="failed").get(
                            "stages",
                            [],
                        )
                    ),
                },
            )
        except Exception:
            pass
        raise


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
