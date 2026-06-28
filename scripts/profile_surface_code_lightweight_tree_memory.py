#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import shutil
import subprocess
import sys
import time
import tracemalloc
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
for path in (SRC_ROOT, SCRIPTS_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from trotterlib import surface_code as sc  # noqa: E402

import profile_surface_code_parent_memory as parent_profile  # noqa: E402


DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "surface_code_process_isolation"
DEFAULT_REPORT_PATH = (
    REPO_ROOT / "docs" / "benchmarks" / "surface_code_process_isolation_memory.md"
)
DEFAULT_REPRO_REPORT_PATH = (
    REPO_ROOT
    / "docs"
    / "benchmarks"
    / "surface_code_process_isolation_reproducibility.md"
)
BASELINE_COMMIT = "d59270fd41378ec87450e2c6b6c31e0210363e0e"
REPRO_BASELINE_COMMIT = "7c6c681b4bdf17cd9755b48d2d95c7d75ce3b074"
CASE_CHAIN_LENGTH = {"h4_4th_new2": 4, "h5_4th_new2": 5}
CASE_DISPLAY = {"h4_4th_new2": "H4", "h5_4th_new2": "H5"}
H5_CASE = "h5_4th_new2"
H4_CASE = "h4_4th_new2"
PF_LABEL = "4th(new_2)"
SAMPLE_INTERVAL_SEC = 0.02
ONE_MIB_KB = 1024
ISOLATION_PARENT_RSS_GATE_KB = 300 * ONE_MIB_KB
ISOLATION_PARENT_SHARE_GATE = 0.30
ISOLATION_PREPARE_DELTA_GATE_KB = 200 * ONE_MIB_KB
MIN_FREE_DISK_BYTES = 5 * 1024**3
SEMANTIC_IGNORES = {
    "compile_info_json",
    "execution_time_sec",
    "compile_wall_time_sec",
}
CACHE_SEMANTIC_KEYS = (
    "cache_key",
    "qasm_hash",
    "optimized_ir_hash",
    "compiler_executable_hash",
    "compiler_core_library_hash",
    "topology_hash",
)
HASH_COMPARE_KEYS = (
    "qasm_hash",
    "ir_hash",
    "optimized_ir_hash",
    "instruction_count",
    "gate_depth",
)
RELEVANT_ENV_KEYS = (
    "PYTHONPATH",
    "PYTHONHASHSEED",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "SURFACE_CODE_PROFILE_RSS_SAMPLING",
    "SURFACE_CODE_PROFILE_RSS_SAMPLING_INTERVAL_SEC",
    "SURFACE_CODE_PROFILE_CIRCUIT_RELEASE_EXPERIMENT",
    "SURFACE_CODE_COMPILE_INFO_OUTPUT_MODE",
    "SURFACE_CODE_COMPILE_INFO_EXTRACTION_MODE",
    "SURFACE_CODE_INTEGRAL_CACHE_ENABLED",
    "SURFACE_CODE_RZ_HELPER_BATCH_SIZE",
    "QRET_DEP_GRAPH_IMPL",
    "QRET_SUMMARY_TIME_SERIES_IMPL",
    "QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING",
    "QRET_RSS_DIAGNOSTIC_TRIM_STAGE",
    "QRET_PATH",
    "SURFACE_CODE_QRET_PATH",
    "SURFACE_CODE_TOPOLOGY_PATH",
    "GRIDSYNTH_PATH",
    "SURFACE_CODE_GRIDSYNTH_PATH",
)
MARKER_LABELS = (
    "evaluation_entry",
    "before_prepare",
    "after_prepare",
    "before_qret_launch",
    "after_qret_launch",
    "tree_peak_sample",
    "before_qret_exit",
    "after_qret_exit",
    "before_compile_info_read",
    "after_compile_info_read",
    "evaluation_exit",
)
OVERHEAD_AUDIT = [
    {
        "feature": "tracemalloc.start()",
        "light": False,
        "deep": True,
        "production_disabled": True,
        "rss_overhead": "high; metadata tracked for Python allocations",
        "elapsed_overhead": "medium-high during allocation-heavy prepare",
    },
    {
        "feature": "gc.get_objects()",
        "light": False,
        "deep": True,
        "production_disabled": True,
        "rss_overhead": "low direct, can perturb caches",
        "elapsed_overhead": "medium when repeated at markers",
    },
    {
        "feature": "recursive object size estimator",
        "light": False,
        "deep": True,
        "production_disabled": True,
        "rss_overhead": "medium from traversal bookkeeping",
        "elapsed_overhead": "medium-high on nested objects",
    },
    {
        "feature": "NumPy/pandas deep-size traversal",
        "light": False,
        "deep": True,
        "production_disabled": True,
        "rss_overhead": "low-medium",
        "elapsed_overhead": "medium if large containers are present",
    },
    {
        "feature": "all parent marker object audit",
        "light": False,
        "deep": True,
        "production_disabled": True,
        "rss_overhead": "medium",
        "elapsed_overhead": "medium",
    },
    {
        "feature": "process sample memory retention",
        "light": False,
        "deep": False,
        "production_disabled": True,
        "rss_overhead": "none in current streaming samplers",
        "elapsed_overhead": "low",
    },
    {
        "feature": "raw sample history list",
        "light": False,
        "deep": False,
        "production_disabled": True,
        "rss_overhead": "none in current streaming samplers",
        "elapsed_overhead": "none",
    },
    {
        "feature": "JSON serialization buffer",
        "light": True,
        "deep": True,
        "production_disabled": True,
        "rss_overhead": "low; one row at a time",
        "elapsed_overhead": "low at 20 ms sampling",
    },
]


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    parent_profile._write_json(path, payload)


def _append_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    parent_profile._append_jsonl(path, rows)


def _load_json(path: Path) -> dict[str, Any]:
    return parent_profile._load_json(path)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return parent_profile._load_jsonl(path)


def _git_output(args: Sequence[str], *, cwd: Path = REPO_ROOT) -> str:
    return parent_profile._git_output(args, cwd=cwd)


def _fmt_int(value: Any) -> str:
    if value is None:
        return ""
    return f"{int(value):,}"


def _fmt_mb(kb: Any) -> str:
    if kb is None:
        return ""
    return f"{int(kb) / 1024:.1f}"


def _fmt_float(value: Any, digits: int = 3) -> str:
    if value is None:
        return "not evaluated"
    return f"{float(value):.{digits}f}"


def _fmt_int_or_na(value: Any) -> str:
    if value is None:
        return "not evaluated"
    return _fmt_int(value)


def _fmt_mb_or_na(kb: Any) -> str:
    if kb is None:
        return "not evaluated"
    return _fmt_mb(kb)


def _ratio(numerator: int | float | None, denominator: int | float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return float(numerator) / float(denominator)


def _configure_profile_mode(mode: str) -> dict[str, Any]:
    normalized = str(mode).strip().lower()
    if normalized not in {"light", "deep"}:
        raise ValueError("profile mode must be 'light' or 'deep'")
    was_tracing = tracemalloc.is_tracing()
    if normalized == "light":
        if was_tracing:
            tracemalloc.stop()
    else:
        if not was_tracing:
            tracemalloc.start()
    return {
        "mode": normalized,
        "tracemalloc_was_tracing": was_tracing,
        "tracemalloc_is_tracing": tracemalloc.is_tracing(),
    }


def _validate_case(case: str) -> str:
    if case not in CASE_CHAIN_LENGTH:
        raise ValueError(f"Unsupported case {case!r}; H6 is intentionally rejected")
    return case


def _architecture() -> sc.SurfaceCodeArchitecture:
    return parent_profile._architecture()


def _case_parameters(case: str) -> dict[str, Any]:
    case = _validate_case(case)
    ham_name = sc.grouped_hchain_ham_name(CASE_CHAIN_LENGTH[case])
    step_time = sc.surface_code_step_time(ham_name, PF_LABEL)
    rotation_precision = sc.surface_code_rotation_precision(
        ham_name,
        PF_LABEL,
        target_error=sc.TARGET_ERROR,
        step_time=step_time,
    )
    return {
        "case": case,
        "chain_length": CASE_CHAIN_LENGTH[case],
        "ham_name": ham_name,
        "pf_label": PF_LABEL,
        "step_time": step_time,
        "rotation_precision": rotation_precision,
    }


def _runtime_provenance(
    architecture: sc.SurfaceCodeArchitecture,
    artifact: sc.SurfaceCodeStepArtifact | None = None,
) -> dict[str, Any]:
    provenance = parent_profile._runtime_provenance(
        architecture=architecture,
        artifact=artifact,
    )
    if artifact is not None:
        provenance["qasm_hash"] = artifact.qasm_hash
        provenance["ir_hash"] = sc.file_sha256(artifact.ir_path) if artifact.ir_path.exists() else None
        provenance["optimized_ir_hash"] = artifact.optimized_ir_hash
    return provenance


def _pipeline_config_hash(architecture: sc.SurfaceCodeArchitecture) -> str:
    payload = {
        "architecture": architecture.to_dict(),
        "summary_time_series_impl": "legacy_timeseries",
        "inverse_map_release_after_routing": "1",
        "dep_graph_impl": "default_compact",
        "pipeline_state_output": "skipped",
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _canonical_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
            "utf-8"
        )
    ).hexdigest()


def _architecture_hash(architecture: sc.SurfaceCodeArchitecture) -> str:
    return _canonical_hash(architecture.to_dict())


def _random_state_hash() -> str:
    return _canonical_hash(repr(random.getstate()))


def _numpy_random_state_hash() -> str:
    try:
        state = sc.np.random.get_state()  # type: ignore[attr-defined]
    except Exception:
        return "unavailable"
    compact = [state[0], state[1].tolist(), int(state[2]), int(state[3]), float(state[4])]
    return _canonical_hash(compact)


def _relevant_environment() -> dict[str, str | None]:
    return {key: os.environ.get(key) for key in RELEVANT_ENV_KEYS}


def _settings_snapshot(
    *,
    role: str,
    case: str,
    cache_root: Path,
    batch_size: int,
    architecture: sc.SurfaceCodeArchitecture | None = None,
    artifact: sc.SurfaceCodeStepArtifact | None = None,
) -> dict[str, Any]:
    architecture = architecture or _architecture()
    params = _case_parameters(case)
    runtime_hashes = sc.qret_runtime_hashes(Path(architecture.qret_path).expanduser().resolve())
    topology_path = Path(architecture.topology_path).expanduser().resolve()
    return {
        "role": role,
        "case": case,
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "working_directory": str(Path.cwd()),
        "environment": _relevant_environment(),
        "surface_code_cache_dir": str(cache_root),
        "surface_code_rz_helper_batch_size": int(batch_size),
        "target_error": float(sc.TARGET_ERROR),
        "step_time": float(params["step_time"]),
        "rotation_precision": float(params["rotation_precision"]),
        "ham_name": params["ham_name"],
        "pf_label": params["pf_label"],
        "architecture": architecture.to_dict(),
        "architecture_hash": _architecture_hash(architecture),
        "compile_mode": architecture.compile_mode,
        "topology_path": str(topology_path),
        "topology_hash": sc.file_sha256(topology_path) if topology_path.exists() else None,
        "summary_mode": architecture.compile_info_output_mode,
        "pipeline_config_hash": _pipeline_config_hash(architecture),
        "qret_executable_hash": runtime_hashes.get("qret_executable_hash"),
        "libqret_core_hash": runtime_hashes.get("qret_core_library_hash"),
        "inverse_map_release": os.environ.get("QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING", "1"),
        "compact_dep_graph": os.environ.get("QRET_DEP_GRAPH_IMPL", "default_compact"),
        "time_series_impl": os.environ.get("QRET_SUMMARY_TIME_SERIES_IMPL", "legacy_timeseries"),
        "pipeline_state_output": "skipped" if architecture.skip_compile_output else "enabled",
        "python_hash_seed": os.environ.get("PYTHONHASHSEED"),
        "python_random_seed": "not_used",
        "numpy_random_seed": "not_used",
        "python_random_state_hash": _random_state_hash(),
        "numpy_random_state_hash": _numpy_random_state_hash(),
        "qiskit_transpiler_seed": "not_used",
        "rz_synthesis_seed": "not_used",
        "artifact_qasm_hash": None if artifact is None else artifact.qasm_hash,
        "artifact_optimized_ir_hash": None if artifact is None else artifact.optimized_ir_hash,
    }


def _compare_settings(
    *snapshots: Mapping[str, Any],
    labels: Sequence[str],
    context: str = "",
) -> list[dict[str, Any]]:
    keys = [
        "python_executable",
        "python_version",
        "working_directory",
        "surface_code_rz_helper_batch_size",
        "target_error",
        "step_time",
        "rotation_precision",
        "ham_name",
        "pf_label",
        "architecture_hash",
        "compile_mode",
        "topology_hash",
        "summary_mode",
        "inverse_map_release",
        "compact_dep_graph",
        "time_series_impl",
        "pipeline_state_output",
        "python_hash_seed",
        "python_random_seed",
        "numpy_random_seed",
        "qiskit_transpiler_seed",
        "rz_synthesis_seed",
    ]
    rows: list[dict[str, Any]] = []
    for key in keys:
        values = [snapshot.get(key) for snapshot in snapshots]
        rows.append(
            {
                "setting": f"{context}:{key}" if context else key,
                **{label: value for label, value in zip(labels, values)},
                "identical": len({json.dumps(value, sort_keys=True, default=str) for value in values}) == 1,
            }
        )
    env_keys = [
        "PYTHONPATH",
        "PYTHONHASHSEED",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "SURFACE_CODE_RZ_HELPER_BATCH_SIZE",
        "QRET_SUMMARY_TIME_SERIES_IMPL",
        "QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING",
        "QRET_DEP_GRAPH_IMPL",
    ]
    for key in env_keys:
        values = [
            (snapshot.get("environment") if isinstance(snapshot.get("environment"), Mapping) else {}).get(key)
            for snapshot in snapshots
        ]
        rows.append(
            {
                "setting": f"{context}:env:{key}" if context else f"env:{key}",
                **{label: value for label, value in zip(labels, values)},
                "identical": len({json.dumps(value, sort_keys=True, default=str) for value in values}) == 1,
            }
        )
    return rows


def _manifest_hash(payload: Mapping[str, Any]) -> str:
    return _canonical_hash(payload)


def _artifact_semantics_from_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    artifact = sc.surface_code_step_artifact_from_dict(payload)
    ir_hash = sc.file_sha256(artifact.ir_path) if artifact.ir_path.exists() else None
    stream = artifact.rz_call_cache.get("optimized_ir_stream")
    stream_hash = (
        stream.get("normalized_instruction_stream_hash")
        if isinstance(stream, Mapping)
        else None
    )
    integral_cache = artifact.integral_cache if isinstance(artifact.integral_cache, Mapping) else {}
    return {
        "qasm_hash": artifact.qasm_hash,
        "ir_hash": ir_hash,
        "optimized_ir_hash": artifact.optimized_ir_hash,
        "instruction_count": int(artifact.instruction_count),
        "gate_depth": int(artifact.gate_depth),
        "step_magic_state_count": int(artifact.step_magic_state_count),
        "step_magic_state_depth": int(artifact.step_magic_state_depth),
        "peak_magic_layer": int(artifact.peak_magic_layer),
        "step_rz_count": int(artifact.step_rz_count),
        "integral_value_hash": integral_cache.get("integral_value_hash"),
        "integral_cache_key": integral_cache.get("cache_key"),
        "integral_cache_status": integral_cache.get("cache_status"),
        "optimized_instruction_stream_hash": stream_hash,
        "qasm_size_bytes": artifact.qasm_path.stat().st_size if artifact.qasm_path.exists() else None,
        "ir_size_bytes": artifact.ir_path.stat().st_size if artifact.ir_path.exists() else None,
        "optimized_ir_size_bytes": (
            artifact.optimized_ir_path.stat().st_size
            if artifact.optimized_ir_path.exists()
            else None
        ),
    }


def _artifact_semantics_from_result(result: Mapping[str, Any]) -> dict[str, Any]:
    artifact = result.get("artifact")
    if isinstance(artifact, Mapping) and "qret_path" in artifact:
        return _artifact_semantics_from_payload(artifact)
    artifact_summary = artifact if isinstance(artifact, Mapping) else {}
    metrics = result.get("metrics") if isinstance(result.get("metrics"), Mapping) else {}
    return {
        "qasm_hash": artifact_summary.get("qasm_hash") or metrics.get("qasm_hash"),
        "ir_hash": artifact_summary.get("ir_hash"),
        "optimized_ir_hash": artifact_summary.get("optimized_ir_hash")
        or metrics.get("optimized_ir_hash"),
        "instruction_count": artifact_summary.get("instruction_count"),
        "gate_depth": artifact_summary.get("gate_depth"),
        "step_magic_state_count": metrics.get("step_magic_state_count"),
        "step_magic_state_depth": metrics.get("step_magic_state_depth"),
    }


def _qret_command_signature(result: Mapping[str, Any]) -> list[str]:
    stage = result.get("qret_stage") if isinstance(result.get("qret_stage"), Mapping) else {}
    details = stage.get("details") if isinstance(stage.get("details"), Mapping) else {}
    command = details.get("command")
    if not isinstance(command, Sequence) or isinstance(command, (str, bytes)):
        return []
    signature: list[str] = []
    skip_next_path = False
    for index, item in enumerate(command):
        text = str(item)
        if index == 0:
            signature.append(Path(text).name)
            continue
        if skip_next_path:
            signature.append("<path>")
            skip_next_path = False
            continue
        signature.append(text)
        if text in {"--pipeline", "--input", "--output"}:
            skip_next_path = True
    return signature


def _cache_semantics(result: Mapping[str, Any]) -> dict[str, Any]:
    metrics = result.get("metrics") if isinstance(result.get("metrics"), Mapping) else {}
    return {key: metrics.get(key) for key in CACHE_SEMANTIC_KEYS}


def _compile_semantic_comparison(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    semantic = _semantic_comparison(left, right)
    qret_stage_left = left.get("qret_stage") if isinstance(left.get("qret_stage"), Mapping) else {}
    qret_stage_right = right.get("qret_stage") if isinstance(right.get("qret_stage"), Mapping) else {}
    returncode_left = (
        qret_stage_left.get("result", {}).get("returncode")
        if isinstance(qret_stage_left.get("result"), Mapping)
        else None
    )
    returncode_right = (
        qret_stage_right.get("result", {}).get("returncode")
        if isinstance(qret_stage_right.get("result"), Mapping)
        else None
    )
    semantic["cache_semantics"] = _compare_mapping(
        _cache_semantics(left),
        _cache_semantics(right),
        ignored=set(),
    )
    semantic["qret_command"] = {
        "all_equal": _qret_command_signature(left) == _qret_command_signature(right),
        "in_process": _qret_command_signature(left),
        "compile_worker": _qret_command_signature(right),
    }
    semantic["returncode"] = {
        "all_equal": returncode_left == returncode_right == 0,
        "in_process": returncode_left,
        "compile_worker": returncode_right,
    }
    semantic["all_equal"] = all(
        bool(semantic[key]["all_equal"])
        for key in (
            "artifact_hashes",
            "raw_metrics",
            "normalized_metrics",
            "cache_semantics",
            "qret_command",
            "returncode",
        )
    )
    return semantic


def _compare_prepare_artifacts(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    left_artifact = left.get("artifact") if isinstance(left.get("artifact"), Mapping) else {}
    right_artifact = right.get("artifact") if isinstance(right.get("artifact"), Mapping) else {}
    left_sem = _artifact_semantics_from_payload(left_artifact)
    right_sem = _artifact_semantics_from_payload(right_artifact)
    scalar_keys = [
        "qasm_hash",
        "ir_hash",
        "optimized_ir_hash",
        "instruction_count",
        "gate_depth",
        "step_magic_state_count",
        "step_magic_state_depth",
        "step_rz_count",
        "integral_value_hash",
        "optimized_instruction_stream_hash",
    ]
    scalar_cmp = _compare_mapping(
        {key: left_sem.get(key) for key in scalar_keys},
        {key: right_sem.get(key) for key in scalar_keys},
        ignored=set(),
    )
    stages = [
        ("integral_scf_and_transform", "integral_value_hash"),
        ("write_qasm", "qasm_hash"),
        ("qret_parse_or_ir_precision", "ir_hash"),
        ("rz_helper_or_ir_optimization", "optimized_ir_hash"),
        ("optimized_ir_summary", "optimized_instruction_stream_hash"),
    ]
    first_divergent = None
    for stage_name, key in stages:
        if left_sem.get(key) != right_sem.get(key):
            first_divergent = stage_name
            break
    return {
        "all_equal": scalar_cmp["all_equal"],
        "scalar_comparison": scalar_cmp,
        "first_divergent_stage": first_divergent,
        "in_process": left_sem,
        "prepare_worker": right_sem,
        "manifest_hashes": {
            "in_process": _manifest_hash(left_artifact),
            "prepare_worker": _manifest_hash(right_artifact),
            "equal": _manifest_hash(left_artifact) == _manifest_hash(right_artifact),
            "note": "Full manifest hashes include runtime paths and are not the semantic gate.",
        },
    }


@contextmanager
def _surface_code_runtime(
    *,
    cache_root: Path,
    batch_size: int,
    sample_interval_sec: float,
) -> Any:
    previous_cache_dir = sc.SURFACE_CODE_CACHE_DIR
    previous_batch_size = sc.SURFACE_CODE_RZ_HELPER_BATCH_SIZE
    previous_env = {
        key: os.environ.get(key)
        for key in (
            "SURFACE_CODE_PROFILE_RSS_SAMPLING",
            "SURFACE_CODE_PROFILE_RSS_SAMPLING_INTERVAL_SEC",
            "SURFACE_CODE_PROFILE_CIRCUIT_RELEASE_EXPERIMENT",
            "QRET_DEP_GRAPH_IMPL",
            "QRET_SUMMARY_TIME_SERIES_IMPL",
            "QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING",
            "QRET_RSS_DIAGNOSTIC_TRIM_STAGE",
            "SURFACE_CODE_PARENT_PROFILE_MODE",
        )
    }
    sc.SURFACE_CODE_CACHE_DIR = cache_root
    sc.SURFACE_CODE_RZ_HELPER_BATCH_SIZE = int(batch_size)
    os.environ["SURFACE_CODE_PROFILE_RSS_SAMPLING"] = "1"
    os.environ["SURFACE_CODE_PROFILE_RSS_SAMPLING_INTERVAL_SEC"] = str(sample_interval_sec)
    os.environ.pop("SURFACE_CODE_PROFILE_CIRCUIT_RELEASE_EXPERIMENT", None)
    os.environ.pop("QRET_DEP_GRAPH_IMPL", None)
    os.environ["QRET_SUMMARY_TIME_SERIES_IMPL"] = "legacy_timeseries"
    os.environ["QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING"] = "1"
    os.environ["QRET_RSS_DIAGNOSTIC_TRIM_STAGE"] = "none"
    try:
        yield
    finally:
        sc.SURFACE_CODE_CACHE_DIR = previous_cache_dir
        sc.SURFACE_CODE_RZ_HELPER_BATCH_SIZE = previous_batch_size
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _sample_split() -> dict[str, Any]:
    rows = parent_profile._sample_process_tree(os.getpid(), -1)
    return parent_profile._tree_split_for_rows(rows, parent_pid=os.getpid())


def _light_marker(
    label: str,
    *,
    stage_started: float | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    split = _sample_split()
    process = parent_profile._process_memory_detail()
    marker = {
        "label": str(label),
        "timestamp_seconds": time.time(),
        "process": process,
        "tree_vmrss_kb": split.get("tree_vmrss_kb"),
        "qret_vmrss_kb": split.get("qret_vmrss_kb"),
        "parent_vmrss_kb": split.get("parent_vmrss_kb"),
        "stage_elapsed_seconds": None
        if stage_started is None
        else time.perf_counter() - float(stage_started),
    }
    if extra:
        marker["extra"] = dict(extra)
    return marker


def _marker_by_label(markers: Sequence[Mapping[str, Any]], label: str) -> dict[str, Any]:
    for marker in markers:
        if marker.get("label") == label:
            return dict(marker)
    return {}


def _marker_rss(markers: Sequence[Mapping[str, Any]], label: str) -> int | None:
    marker = _marker_by_label(markers, label)
    process = marker.get("process")
    if isinstance(process, Mapping) and process.get("rss_kb") is not None:
        return int(process["rss_kb"])
    return None


def _artifact_summary(artifact: sc.SurfaceCodeStepArtifact) -> dict[str, Any]:
    summary = parent_profile._artifact_summary(artifact)
    summary["ir_hash"] = sc.file_sha256(artifact.ir_path) if artifact.ir_path.exists() else None
    summary["artifact_manifest_path"] = str(artifact.runtime_root / "step_artifact.json")
    return summary


def _raw_metrics_from_compile_info(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    compile_info_path = Path(path)
    if not compile_info_path.exists():
        return {}
    metrics = sc.surface_code_step_metrics_from_compile_info_json(compile_info_path)
    metrics.pop("compile_info_json", None)
    return metrics


def _load_stage_data(
    *,
    artifact: sc.SurfaceCodeStepArtifact,
    architecture: sc.SurfaceCodeArchitecture,
    cache_root: Path,
    case: str,
) -> dict[str, Any]:
    compile_root = parent_profile._compile_runtime_root_for_cache(
        artifact,
        architecture,
        cache_root,
    )
    prepare_metrics_path = parent_profile._stage_metrics_path(
        artifact.runtime_root,
        sc._PREPARE_STAGE_METRICS_FILENAME,
        sc._PREPARE_STAGE_CACHE_HIT_METRICS_FILENAME,
    )
    compile_metrics_path = parent_profile._stage_metrics_path(
        compile_root,
        sc._COMPILE_STAGE_METRICS_FILENAME,
        sc._COMPILE_STAGE_CACHE_HIT_METRICS_FILENAME,
    )
    prepare_metrics = _load_json(prepare_metrics_path) if prepare_metrics_path.exists() else {}
    compile_metrics = _load_json(compile_metrics_path) if compile_metrics_path.exists() else {}
    rows = parent_profile._stage_rows(
        prepare_metrics=prepare_metrics,
        compile_metrics=compile_metrics,
        case_name=case,
    )
    qret_stage = parent_profile._read_stage(compile_metrics, "qret_compile")
    read_stage = parent_profile._read_stage(compile_metrics, "read_compile_info_json")
    compile_info_path = compile_root / "compile_info.json"
    return {
        "compile_root": str(compile_root),
        "compile_info_path": str(compile_info_path),
        "compile_info_size_bytes": compile_info_path.stat().st_size
        if compile_info_path.exists()
        else None,
        "prepare_metrics_path": str(prepare_metrics_path),
        "compile_metrics_path": str(compile_metrics_path),
        "prepare_metrics": prepare_metrics,
        "compile_metrics": compile_metrics,
        "stage_rows": rows,
        "qret_stage": qret_stage,
        "read_compile_info_stage": read_stage,
        "prepare_stage_peak": parent_profile._stage_peak(rows, phase="prepare"),
        "compile_stage_peak": parent_profile._stage_peak(rows, phase="compile"),
        "raw_resource_metrics": _raw_metrics_from_compile_info(compile_info_path),
    }


def _extract_stage_elapsed(stage: Mapping[str, Any]) -> float | None:
    if stage.get("elapsed_seconds") is None:
        return None
    return float(stage["elapsed_seconds"])


def _classify_command(command: str | None) -> str:
    text = command or ""
    if parent_profile._is_qret_command(text):
        return "qret"
    if "--worker prepare" in text:
        return "prepare_worker"
    if "--worker compile" in text:
        return "compile_worker"
    if "profile_surface_code_lightweight_tree_memory.py" in text:
        return "orchestrator"
    return "other"


def _classification_summary(samples_path: Path) -> dict[str, Any]:
    rows = _load_jsonl(samples_path)
    peaks: dict[str, int] = {}
    tree_peak: dict[str, Any] = {}
    for row in rows:
        kind = _classify_command(row.get("command"))
        peaks[kind] = max(peaks.get(kind, 0), int(row.get("vmrss_kb") or 0))
        if int(row.get("tree_vmrss_kb") or 0) > int(tree_peak.get("tree_vmrss_kb") or 0):
            tree_peak = dict(row)
    return {
        "peaks_by_kind_kb": peaks,
        "sample_count_rows": len(rows),
        "tree_peak_row": tree_peak,
    }


def _semantic_metrics(metrics: Mapping[str, Any]) -> dict[str, Any]:
    ret = dict(metrics)
    for key in SEMANTIC_IGNORES:
        ret.pop(key, None)
    return ret


def _compare_mapping(left: Mapping[str, Any], right: Mapping[str, Any], *, ignored: set[str] | None = None) -> dict[str, Any]:
    ignored = set(ignored or set())
    left_norm = {key: value for key, value in left.items() if key not in ignored}
    right_norm = {key: value for key, value in right.items() if key not in ignored}
    keys = sorted(set(left_norm) | set(right_norm))
    mismatches = [key for key in keys if left_norm.get(key, object()) != right_norm.get(key, object())]
    return {
        "all_equal": not mismatches,
        "mismatches": mismatches,
        "field_count": len(keys),
        "ignored_fields": sorted(ignored),
    }


def _hash_semantics(result: Mapping[str, Any]) -> dict[str, Any]:
    artifact = result.get("artifact")
    artifact = artifact if isinstance(artifact, Mapping) else {}
    metrics = result.get("metrics")
    metrics = metrics if isinstance(metrics, Mapping) else {}
    return {
        "qasm_hash": artifact.get("qasm_hash"),
        "ir_hash": artifact.get("ir_hash"),
        "optimized_ir_hash": artifact.get("optimized_ir_hash"),
        "instruction_count": artifact.get("instruction_count"),
        "gate_depth": artifact.get("gate_depth"),
        "cache_key": metrics.get("cache_key"),
        "compiler_executable_hash": metrics.get("compiler_executable_hash"),
        "compiler_core_library_hash": metrics.get("compiler_core_library_hash"),
        "topology_hash": metrics.get("topology_hash"),
    }


def _semantic_comparison(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_hashes": _compare_mapping(
            _hash_semantics(left),
            _hash_semantics(right),
            ignored=set(),
        ),
        "raw_metrics": _compare_mapping(
            left.get("raw_resource_metrics", {}) if isinstance(left.get("raw_resource_metrics"), Mapping) else {},
            right.get("raw_resource_metrics", {}) if isinstance(right.get("raw_resource_metrics"), Mapping) else {},
            ignored=SEMANTIC_IGNORES,
        ),
        "normalized_metrics": _compare_mapping(
            _semantic_metrics(left.get("metrics", {}) if isinstance(left.get("metrics"), Mapping) else {}),
            _semantic_metrics(right.get("metrics", {}) if isinstance(right.get("metrics"), Mapping) else {}),
            ignored=set(),
        ),
    }


def _result_memory_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    split = result.get("tree_peak_split")
    split = split if isinstance(split, Mapping) else {}
    qret_stage = result.get("qret_stage")
    qret_stage = qret_stage if isinstance(qret_stage, Mapping) else {}
    qret_stage_result = qret_stage.get("result") if isinstance(qret_stage.get("result"), Mapping) else {}
    return {
        "tree_peak_kb": result.get("tree_peak_rss_kb"),
        "parent_at_tree_peak_kb": split.get("parent_vmrss_kb"),
        "qret_at_tree_peak_kb": split.get("qret_vmrss_kb"),
        "parent_peak_kb": result.get("parent_peak_rss_kb"),
        "qret_peak_kb": result.get("qret_peak_rss_kb"),
        "qret_gnu_time_kb": qret_stage_result.get("subprocess_maxrss_kb"),
        "elapsed_seconds": result.get("elapsed_seconds"),
    }


def _isolation_gate(result: Mapping[str, Any]) -> dict[str, Any]:
    markers = result.get("markers")
    markers = markers if isinstance(markers, Sequence) else []
    entry = _marker_rss(markers, "evaluation_entry")
    after_prepare = _marker_rss(markers, "after_prepare")
    before_qret = _marker_rss(markers, "before_qret_launch")
    split = result.get("tree_peak_split")
    split = split if isinstance(split, Mapping) else {}
    tree_peak = int(split.get("tree_vmrss_kb") or 0)
    parent_at_tree = int(split.get("parent_vmrss_kb") or 0)
    parent_share = _ratio(parent_at_tree, tree_peak)
    prepare_delta = None if entry is None or after_prepare is None else int(after_prepare) - int(entry)
    reasons: list[str] = []
    if before_qret is not None and before_qret >= ISOLATION_PARENT_RSS_GATE_KB:
        reasons.append("qret_launch_parent_rss_ge_300mb")
    if parent_share is not None and parent_share >= ISOLATION_PARENT_SHARE_GATE:
        reasons.append("parent_share_at_tree_peak_ge_30pct")
    if prepare_delta is not None and prepare_delta >= ISOLATION_PREPARE_DELTA_GATE_KB:
        reasons.append("prepare_delta_ge_200mb")
    return {
        "passes": bool(reasons),
        "reasons": reasons,
        "entry_parent_rss_kb": entry,
        "after_prepare_parent_rss_kb": after_prepare,
        "before_qret_parent_rss_kb": before_qret,
        "prepare_retained_delta_kb": prepare_delta,
        "tree_peak_kb": tree_peak,
        "parent_at_tree_peak_kb": parent_at_tree,
        "parent_share_at_tree_peak": parent_share,
        "thresholds": {
            "before_qret_parent_rss_kb": ISOLATION_PARENT_RSS_GATE_KB,
            "parent_share_at_tree_peak": ISOLATION_PARENT_SHARE_GATE,
            "prepare_delta_kb": ISOLATION_PREPARE_DELTA_GATE_KB,
        },
    }


def _tail_text(path: Path, limit_bytes: int = 8192) -> str:
    if not path.exists():
        return ""
    size = path.stat().st_size
    with path.open("rb") as f:
        if size > limit_bytes:
            f.seek(-limit_bytes, os.SEEK_END)
        data = f.read(limit_bytes)
    return data.decode("utf-8", errors="replace")


def _run_worker_subprocess(
    worker: str,
    *,
    case: str,
    cache_root: Path,
    run_dir: Path,
    batch_size: int,
    sample_interval_sec: float,
    artifact_json: Path | None = None,
    timeout_sec: float | None = None,
    extra_env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    result_json = run_dir / f"{worker}_worker_result.json"
    stdout_path = run_dir / f"{worker}_worker.stdout.log"
    stderr_path = run_dir / f"{worker}_worker.stderr.log"
    run_dir.mkdir(parents=True, exist_ok=True)
    for stale_path in (result_json, stdout_path, stderr_path):
        try:
            stale_path.unlink()
        except FileNotFoundError:
            pass
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        worker,
        "--case",
        case,
        "--cache-root",
        str(cache_root),
        "--result-json",
        str(result_json),
        "--batch-size",
        str(batch_size),
        "--sample-interval-sec",
        str(sample_interval_sec),
    ]
    if artifact_json is not None:
        cmd.extend(["--artifact-json", str(artifact_json)])
    started = time.perf_counter()
    env = os.environ.copy()
    if extra_env:
        env.update({str(key): str(value) for key, value in extra_env.items()})
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        proc = subprocess.Popen(
            cmd,
            cwd=REPO_ROOT,
            env=env,
            stdout=stdout,
            stderr=stderr,
            close_fds=True,
        )
        try:
            returncode = proc.wait(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            proc.kill()
            returncode = proc.wait()
            raise RuntimeError(f"{worker} worker timeout; stderr tail:\n{_tail_text(stderr_path)}")
    elapsed = time.perf_counter() - started
    if returncode != 0:
        raise RuntimeError(
            f"{worker} worker failed with code {returncode}; stderr tail:\n{_tail_text(stderr_path)}"
        )
    if not result_json.exists():
        raise RuntimeError(f"{worker} worker did not create {result_json}")
    result = _load_json(result_json)
    if result.get("status") != "ok":
        raise RuntimeError(f"{worker} worker returned failure: {result}")
    result.update(
        {
            "worker_returncode": int(returncode),
            "worker_elapsed_seconds": elapsed,
            "worker_stdout_path": str(stdout_path),
            "worker_stderr_path": str(stderr_path),
            "worker_stdout_size_bytes": stdout_path.stat().st_size if stdout_path.exists() else None,
            "worker_stderr_size_bytes": stderr_path.stat().st_size if stderr_path.exists() else None,
        }
    )
    return result


def _verify_artifact_dict(payload: Mapping[str, Any]) -> sc.SurfaceCodeStepArtifact:
    artifact = sc.surface_code_step_artifact_from_dict(payload)
    if not artifact.qasm_path.exists():
        raise FileNotFoundError(f"Missing qasm path: {artifact.qasm_path}")
    if not artifact.ir_path.exists():
        raise FileNotFoundError(f"Missing IR path: {artifact.ir_path}")
    if not artifact.optimized_ir_path.exists():
        raise FileNotFoundError(f"Missing optimized IR path: {artifact.optimized_ir_path}")
    if sc.file_sha256(artifact.qasm_path) != artifact.qasm_hash:
        raise ValueError("qasm hash mismatch")
    if sc.file_sha256(artifact.optimized_ir_path) != artifact.optimized_ir_hash:
        raise ValueError("optimized IR hash mismatch")
    return artifact


def _worker_prepare(
    *,
    case: str,
    cache_root: Path,
    result_json: Path,
    batch_size: int,
    sample_interval_sec: float,
) -> int:
    _configure_profile_mode("light")
    params = _case_parameters(case)
    architecture = _architecture()
    started = time.perf_counter()
    try:
        with _surface_code_runtime(
            cache_root=cache_root,
            batch_size=batch_size,
            sample_interval_sec=sample_interval_sec,
        ):
            artifact = sc.prepare_grouped_surface_code_step_artifact(
                params["ham_name"],
                params["pf_label"],
                architecture=architecture,
                step_time=params["step_time"],
                rotation_precision=params["rotation_precision"],
            )
        artifact = _verify_artifact_dict(artifact.to_dict())
        payload = {
            "status": "ok",
            "worker": "prepare",
            "case": case,
            "elapsed_seconds": time.perf_counter() - started,
            "artifact": artifact.to_dict(),
            "artifact_summary": _artifact_summary(artifact),
            "artifact_manifest_path": str(artifact.runtime_root / "step_artifact.json"),
            "artifact_manifest_hash": _manifest_hash(artifact.to_dict()),
            "settings": _settings_snapshot(
                role="prepare_worker",
                case=case,
                cache_root=cache_root,
                batch_size=batch_size,
                architecture=architecture,
                artifact=artifact,
            ),
            "runtime_provenance": _runtime_provenance(architecture, artifact),
        }
        _write_json(result_json, payload)
        return 0
    except Exception as exc:
        _write_json(
            result_json,
            {
                "status": "failed",
                "worker": "prepare",
                "case": case,
                "elapsed_seconds": time.perf_counter() - started,
                "error": repr(exc),
            },
        )
        return 1


def _worker_compile(
    *,
    case: str,
    cache_root: Path,
    result_json: Path,
    artifact_json: Path,
    batch_size: int,
    sample_interval_sec: float,
) -> int:
    _configure_profile_mode("light")
    architecture = _architecture()
    started = time.perf_counter()
    try:
        artifact_payload = _load_json(artifact_json)
        artifact_dict = artifact_payload.get("artifact", artifact_payload)
        if not isinstance(artifact_dict, Mapping):
            raise ValueError("artifact manifest missing artifact object")
        artifact = _verify_artifact_dict(artifact_dict)
        with _surface_code_runtime(
            cache_root=cache_root,
            batch_size=batch_size,
            sample_interval_sec=sample_interval_sec,
        ):
            metrics = sc.compile_prepared_surface_code_step_artifact(
                artifact,
                architecture,
                reuse_cache=False,
            )
        stage_data = _load_stage_data(
            artifact=artifact,
            architecture=architecture,
            cache_root=cache_root,
            case=case,
        )
        payload = {
            "status": "ok",
            "worker": "compile",
            "case": case,
            "elapsed_seconds": time.perf_counter() - started,
            "artifact": _artifact_summary(artifact),
            "metrics": metrics,
            "settings": _settings_snapshot(
                role="compile_worker",
                case=case,
                cache_root=cache_root,
                batch_size=batch_size,
                architecture=architecture,
                artifact=artifact,
            ),
            "runtime_provenance": _runtime_provenance(architecture, artifact),
            **stage_data,
        }
        _write_json(result_json, payload)
        return 0
    except Exception as exc:
        _write_json(
            result_json,
            {
                "status": "failed",
                "worker": "compile",
                "case": case,
                "elapsed_seconds": time.perf_counter() - started,
                "error": repr(exc),
            },
        )
        return 1


def _run_in_process_once(
    *,
    case: str,
    run_dir: Path,
    cache_root: Path,
    profile_mode: str,
    batch_size: int,
    sample_interval_sec: float,
) -> dict[str, Any]:
    _configure_profile_mode(profile_mode)
    params = _case_parameters(case)
    architecture = _architecture()
    run_dir.mkdir(parents=True, exist_ok=True)
    samples_path = run_dir / "process_tree_samples.jsonl"
    markers_path = run_dir / "parent_markers.jsonl"
    for path in (samples_path, markers_path, run_dir / "stage_metrics.jsonl"):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    markers: list[dict[str, Any]] = []
    artifact: sc.SurfaceCodeStepArtifact | None = None
    metrics: dict[str, Any] = {}
    started = time.perf_counter()
    prepare_started = 0.0
    compile_started = 0.0

    def add_marker(label: str, *, stage_started: float | None = None, extra: Mapping[str, Any] | None = None) -> None:
        marker = _light_marker(label, stage_started=stage_started, extra=extra)
        markers.append(marker)
        _append_jsonl(markers_path, [marker])

    def work() -> dict[str, Any]:
        nonlocal artifact, metrics, prepare_started, compile_started
        add_marker("evaluation_entry", extra={"case": case, "variant": "in_process"})
        prepare_started = time.perf_counter()
        add_marker("before_prepare")
        with _surface_code_runtime(
            cache_root=cache_root,
            batch_size=batch_size,
            sample_interval_sec=sample_interval_sec,
        ):
            artifact = sc.prepare_grouped_surface_code_step_artifact(
                params["ham_name"],
                params["pf_label"],
                architecture=architecture,
                step_time=params["step_time"],
                rotation_precision=params["rotation_precision"],
            )
        artifact = _verify_artifact_dict(artifact.to_dict())
        add_marker("after_prepare", stage_started=prepare_started)
        compile_started = time.perf_counter()
        add_marker("before_qret_launch")
        with _surface_code_runtime(
            cache_root=cache_root,
            batch_size=batch_size,
            sample_interval_sec=sample_interval_sec,
        ):
            metrics = sc.compile_prepared_surface_code_step_artifact(
                artifact,
                architecture,
                reuse_cache=False,
            )
        add_marker("after_qret_launch", stage_started=compile_started)
        add_marker("before_qret_exit", stage_started=compile_started)
        add_marker("after_qret_exit", stage_started=compile_started)
        add_marker("before_compile_info_read", stage_started=compile_started)
        add_marker("after_compile_info_read", stage_started=compile_started)
        add_marker("evaluation_exit", stage_started=started)
        return metrics

    metrics_result, sample_summary, guard = parent_profile._run_with_streaming_tree_sampler(
        work,
        samples_path=samples_path,
        interval_sec=sample_interval_sec,
        memtotal_kb=parent_profile._meminfo().get("MemTotal"),
    )
    metrics = dict(metrics_result)
    if sample_summary.get("tree_peak_split"):
        add_marker(
            "tree_peak_sample",
            extra=sample_summary.get("tree_peak_split"),
        )
    if artifact is None:
        raise RuntimeError("in-process run did not produce an artifact")
    stage_data = _load_stage_data(
        artifact=artifact,
        architecture=architecture,
        cache_root=cache_root,
        case=case,
    )
    if stage_data["stage_rows"]:
        _append_jsonl(run_dir / "stage_metrics.jsonl", stage_data["stage_rows"])
    classification = _classification_summary(samples_path)
    result = {
        "status": "ok",
        "case": case,
        "variant": "in_process",
        "profile_mode": profile_mode,
        "elapsed_seconds": time.perf_counter() - started,
        "prepare_elapsed_seconds": _extract_stage_elapsed(stage_data["prepare_metrics"].get("stages", [{}])[-1])
        if isinstance(stage_data.get("prepare_metrics"), Mapping)
        and isinstance(stage_data["prepare_metrics"].get("stages"), list)
        and stage_data["prepare_metrics"].get("stages")
        else None,
        "qret_elapsed_seconds": _extract_stage_elapsed(stage_data["qret_stage"]),
        "compile_info_read_elapsed_seconds": _extract_stage_elapsed(stage_data["read_compile_info_stage"]),
        "batch_size": int(batch_size),
        "sample_interval_sec": float(sample_interval_sec),
        "markers": markers,
        "markers_path": str(markers_path),
        "samples_path": str(samples_path),
        "guard": guard,
        "sample_summary": sample_summary,
        "tree_peak_rss_kb": sample_summary.get("sampled_peak_tree_vmrss_kb"),
        "parent_peak_rss_kb": sample_summary.get("sampled_peak_parent_vmrss_kb"),
        "qret_peak_rss_kb": sample_summary.get("sampled_peak_qret_vmrss_kb"),
        "tree_peak_split": sample_summary.get("tree_peak_split"),
        "qret_window": sample_summary.get("qret_window"),
        "artifact": _artifact_summary(artifact),
        "metrics": metrics,
        "runtime_provenance": _runtime_provenance(architecture, artifact),
        "pipeline_config_hash": _pipeline_config_hash(architecture),
        "classification": classification,
        **stage_data,
        "h6_run": False,
    }
    _write_json(run_dir / "summary.json", result)
    return result


def _run_process_isolated_once(
    *,
    case: str,
    run_dir: Path,
    cache_root: Path,
    profile_mode: str,
    batch_size: int,
    sample_interval_sec: float,
) -> dict[str, Any]:
    _configure_profile_mode(profile_mode)
    architecture = _architecture()
    run_dir.mkdir(parents=True, exist_ok=True)
    samples_path = run_dir / "process_tree_samples.jsonl"
    markers_path = run_dir / "parent_markers.jsonl"
    for path in (samples_path, markers_path):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    markers: list[dict[str, Any]] = []
    started = time.perf_counter()
    prepare_result: dict[str, Any] = {}
    compile_result: dict[str, Any] = {}

    def add_marker(label: str, *, stage_started: float | None = None, extra: Mapping[str, Any] | None = None) -> None:
        marker = _light_marker(label, stage_started=stage_started, extra=extra)
        markers.append(marker)
        _append_jsonl(markers_path, [marker])

    def work() -> dict[str, Any]:
        nonlocal prepare_result, compile_result
        add_marker("evaluation_entry", extra={"case": case, "variant": "process_isolated"})
        prepare_started = time.perf_counter()
        add_marker("before_prepare")
        prepare_result = _run_worker_subprocess(
            "prepare",
            case=case,
            cache_root=cache_root,
            run_dir=run_dir,
            batch_size=batch_size,
            sample_interval_sec=sample_interval_sec,
        )
        add_marker("after_prepare", stage_started=prepare_started)
        artifact_manifest = run_dir / "prepare_worker_result.json"
        compile_started = time.perf_counter()
        add_marker("before_qret_launch")
        compile_result = _run_worker_subprocess(
            "compile",
            case=case,
            cache_root=cache_root,
            run_dir=run_dir,
            batch_size=batch_size,
            sample_interval_sec=sample_interval_sec,
            artifact_json=artifact_manifest,
        )
        add_marker("after_qret_launch", stage_started=compile_started)
        add_marker("before_qret_exit", stage_started=compile_started)
        add_marker("after_qret_exit", stage_started=compile_started)
        add_marker("before_compile_info_read", stage_started=compile_started)
        add_marker("after_compile_info_read", stage_started=compile_started)
        add_marker("evaluation_exit", stage_started=started)
        return compile_result

    compile_result, sample_summary, guard = parent_profile._run_with_streaming_tree_sampler(
        work,
        samples_path=samples_path,
        interval_sec=sample_interval_sec,
        memtotal_kb=parent_profile._meminfo().get("MemTotal"),
    )
    if sample_summary.get("tree_peak_split"):
        add_marker("tree_peak_sample", extra=sample_summary.get("tree_peak_split"))
    stage_rows = compile_result.get("stage_rows")
    if isinstance(stage_rows, list) and stage_rows:
        _append_jsonl(run_dir / "stage_metrics.jsonl", stage_rows)
    classification = _classification_summary(samples_path)
    result = {
        "status": "ok",
        "case": case,
        "variant": "process_isolated",
        "profile_mode": profile_mode,
        "elapsed_seconds": time.perf_counter() - started,
        "prepare_elapsed_seconds": prepare_result.get("elapsed_seconds"),
        "qret_elapsed_seconds": _extract_stage_elapsed(compile_result.get("qret_stage", {})),
        "compile_info_read_elapsed_seconds": _extract_stage_elapsed(
            compile_result.get("read_compile_info_stage", {})
        ),
        "batch_size": int(batch_size),
        "sample_interval_sec": float(sample_interval_sec),
        "markers": markers,
        "markers_path": str(markers_path),
        "samples_path": str(samples_path),
        "guard": guard,
        "sample_summary": sample_summary,
        "tree_peak_rss_kb": sample_summary.get("sampled_peak_tree_vmrss_kb"),
        "parent_peak_rss_kb": sample_summary.get("sampled_peak_parent_vmrss_kb"),
        "qret_peak_rss_kb": sample_summary.get("sampled_peak_qret_vmrss_kb"),
        "tree_peak_split": sample_summary.get("tree_peak_split"),
        "qret_window": sample_summary.get("qret_window"),
        "prepare_worker": prepare_result,
        "compile_worker": compile_result,
        "artifact": compile_result.get("artifact"),
        "metrics": compile_result.get("metrics", {}),
        "raw_resource_metrics": compile_result.get("raw_resource_metrics", {}),
        "runtime_provenance": compile_result.get("runtime_provenance", {}),
        "pipeline_config_hash": _pipeline_config_hash(architecture),
        "classification": classification,
        "compile_root": compile_result.get("compile_root"),
        "compile_info_path": compile_result.get("compile_info_path"),
        "compile_info_size_bytes": compile_result.get("compile_info_size_bytes"),
        "qret_stage": compile_result.get("qret_stage", {}),
        "read_compile_info_stage": compile_result.get("read_compile_info_stage", {}),
        "prepare_stage_peak": compile_result.get("prepare_stage_peak", {}),
        "compile_stage_peak": compile_result.get("compile_stage_peak", {}),
        "stage_rows": stage_rows if isinstance(stage_rows, list) else [],
        "h6_run": False,
    }
    _write_json(run_dir / "summary.json", result)
    return result


def _prepare_in_process_only(
    *,
    case: str,
    run_dir: Path,
    cache_root: Path,
    profile_mode: str,
    batch_size: int,
    sample_interval_sec: float,
) -> dict[str, Any]:
    _configure_profile_mode(profile_mode)
    params = _case_parameters(case)
    architecture = _architecture()
    run_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with _surface_code_runtime(
        cache_root=cache_root,
        batch_size=batch_size,
        sample_interval_sec=sample_interval_sec,
    ):
        artifact = sc.prepare_grouped_surface_code_step_artifact(
            params["ham_name"],
            params["pf_label"],
            architecture=architecture,
            step_time=params["step_time"],
            rotation_precision=params["rotation_precision"],
        )
    artifact = _verify_artifact_dict(artifact.to_dict())
    prepare_metrics_path = parent_profile._stage_metrics_path(
        artifact.runtime_root,
        sc._PREPARE_STAGE_METRICS_FILENAME,
        sc._PREPARE_STAGE_CACHE_HIT_METRICS_FILENAME,
    )
    prepare_metrics = _load_json(prepare_metrics_path) if prepare_metrics_path.exists() else {}
    payload = {
        "status": "ok",
        "variant": "in_process_prepare_only",
        "case": case,
        "elapsed_seconds": time.perf_counter() - started,
        "artifact": artifact.to_dict(),
        "artifact_summary": _artifact_summary(artifact),
        "artifact_manifest_path": str(artifact.runtime_root / "step_artifact.json"),
        "artifact_manifest_hash": _manifest_hash(artifact.to_dict()),
        "prepare_metrics_path": str(prepare_metrics_path),
        "prepare_metrics": prepare_metrics,
        "settings": _settings_snapshot(
            role="in_process_prepare",
            case=case,
            cache_root=cache_root,
            batch_size=batch_size,
            architecture=architecture,
            artifact=artifact,
        ),
        "runtime_provenance": _runtime_provenance(architecture, artifact),
    }
    _write_json(run_dir / "prepare_in_process_result.json", payload)
    return payload


def _compile_artifact_in_process_only(
    *,
    case: str,
    artifact: sc.SurfaceCodeStepArtifact,
    run_dir: Path,
    cache_root: Path,
    profile_mode: str,
    batch_size: int,
    sample_interval_sec: float,
) -> dict[str, Any]:
    _configure_profile_mode(profile_mode)
    architecture = _architecture()
    run_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with _surface_code_runtime(
        cache_root=cache_root,
        batch_size=batch_size,
        sample_interval_sec=sample_interval_sec,
    ):
        metrics = sc.compile_prepared_surface_code_step_artifact(
            artifact,
            architecture,
            reuse_cache=False,
        )
    stage_data = _load_stage_data(
        artifact=artifact,
        architecture=architecture,
        cache_root=cache_root,
        case=case,
    )
    payload = {
        "status": "ok",
        "variant": "same_artifact_in_process_compile",
        "case": case,
        "elapsed_seconds": time.perf_counter() - started,
        "artifact": _artifact_summary(artifact),
        "metrics": metrics,
        "settings": _settings_snapshot(
            role="in_process_compile",
            case=case,
            cache_root=cache_root,
            batch_size=batch_size,
            architecture=architecture,
            artifact=artifact,
        ),
        "runtime_provenance": _runtime_provenance(architecture, artifact),
        "pipeline_config_hash": _pipeline_config_hash(architecture),
        **stage_data,
    }
    _write_json(run_dir / "compile_in_process_result.json", payload)
    return payload


def run_case_once(
    *,
    case: str,
    variant: str,
    output_root: Path,
    run_group: str,
    run_index: int,
    profile_mode: str = "light",
    batch_size: int = 2,
    sample_interval_sec: float = SAMPLE_INTERVAL_SEC,
) -> dict[str, Any]:
    _validate_case(case)
    if variant not in {"in_process", "process_isolated"}:
        raise ValueError("variant must be in_process or process_isolated")
    output_root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(output_root).free < MIN_FREE_DISK_BYTES:
        raise RuntimeError(f"Free disk below 5 GiB for {output_root}")
    run_dir = output_root / run_group / case / variant / f"run_{run_index:02d}"
    cache_root = output_root / "surface_code_cache" / run_group / case / variant / f"run_{run_index:02d}"
    if variant == "in_process":
        return _run_in_process_once(
            case=case,
            run_dir=run_dir,
            cache_root=cache_root,
            profile_mode=profile_mode,
            batch_size=batch_size,
            sample_interval_sec=sample_interval_sec,
        )
    return _run_process_isolated_once(
        case=case,
        run_dir=run_dir,
        cache_root=cache_root,
        profile_mode=profile_mode,
        batch_size=batch_size,
        sample_interval_sec=sample_interval_sec,
    )


def _median(values: Sequence[int | float | None]) -> float | int | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    ordered = sorted(present)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _aggregate_variant(rows: Sequence[Mapping[str, Any]], *, variant: str, case: str) -> dict[str, Any]:
    selected = [row for row in rows if row.get("variant") == variant and row.get("case") == case]
    return {
        "case": case,
        "variant": variant,
        "runs": len(selected),
        "median_tree_peak_kb": _median([row.get("tree_peak_rss_kb") for row in selected]),
        "median_parent_peak_kb": _median([row.get("parent_peak_rss_kb") for row in selected]),
        "median_qret_peak_kb": _median([row.get("qret_peak_rss_kb") for row in selected]),
        "median_elapsed_seconds": _median([row.get("elapsed_seconds") for row in selected]),
        "all_tree_peaks_kb": [row.get("tree_peak_rss_kb") for row in selected],
        "all_elapsed_seconds": [row.get("elapsed_seconds") for row in selected],
    }


def _ab_decision(
    baseline_rows: Sequence[Mapping[str, Any]],
    isolated_rows: Sequence[Mapping[str, Any]],
    *,
    semantic_ok: bool,
) -> dict[str, Any]:
    baseline_tree = _median([row.get("tree_peak_rss_kb") for row in baseline_rows])
    isolated_tree = _median([row.get("tree_peak_rss_kb") for row in isolated_rows])
    baseline_elapsed = _median([row.get("elapsed_seconds") for row in baseline_rows])
    isolated_elapsed = _median([row.get("elapsed_seconds") for row in isolated_rows])
    tree_saved = None if baseline_tree is None or isolated_tree is None else float(baseline_tree) - float(isolated_tree)
    tree_saved_ratio = _ratio(tree_saved, baseline_tree) if tree_saved is not None else None
    elapsed_delta_ratio = (
        None
        if baseline_elapsed is None or isolated_elapsed is None
        else (float(isolated_elapsed) - float(baseline_elapsed)) / float(baseline_elapsed)
    )
    all_lower = all(
        iso.get("tree_peak_rss_kb") is not None
        and base.get("tree_peak_rss_kb") is not None
        and int(iso["tree_peak_rss_kb"]) < int(base["tree_peak_rss_kb"])
        for base, iso in zip(baseline_rows, isolated_rows)
    )
    passes = bool(
        semantic_ok
        and tree_saved is not None
        and (tree_saved >= 50 * ONE_MIB_KB or (tree_saved_ratio or 0.0) >= 0.05)
        and all_lower
        and (elapsed_delta_ratio is None or elapsed_delta_ratio <= 0.05)
    )
    return {
        "passes_production_acceptance": passes,
        "median_tree_saved_kb": tree_saved,
        "median_tree_saved_ratio": tree_saved_ratio,
        "median_elapsed_delta_ratio": elapsed_delta_ratio,
        "all_tree_peaks_lower": all_lower,
        "semantic_ok": semantic_ok,
        "production_default": False,
        "production_default_reason": (
            "profiling prototype only; no production API default was changed"
            if passes
            else "acceptance criteria not fully met"
        ),
    }


def _write_report(report_path: Path, payload: Mapping[str, Any]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    light = payload.get("light_baseline", {})
    deep = payload.get("deep_reference", {})
    gate = payload.get("process_isolation_gate", {})
    h4 = payload.get("h4_correctness", {})
    ab = payload.get("h5_ab", {})
    decision = payload.get("process_isolation_decision", {})
    comparison = payload.get("deep_vs_light", {})
    split = light.get("tree_peak_split") if isinstance(light, Mapping) else {}
    split = split if isinstance(split, Mapping) else {}
    lines = [
        "# Surface Code Process Isolation Memory",
        "",
        "## Profiling Overhead Audit",
        "",
        "| feature | light | deep | estimated overhead |",
        "|---|---|---|---:|",
    ]
    for row in OVERHEAD_AUDIT:
        lines.append(
            "| {feature} | {light} | {deep} | RSS: {rss}; elapsed: {elapsed} |".format(
                feature=row["feature"],
                light="on" if row["light"] else "off",
                deep="on" if row["deep"] else "off",
                rss=row["rss_overhead"],
                elapsed=row["elapsed_overhead"],
            )
        )
    lines.extend(
        [
            "",
            "## Lightweight Baseline",
            "",
            "| metric | value |",
            "|---|---:|",
            f"| prepare peak KB | {_fmt_int(light.get('prepare_stage_peak', {}).get('python_sampled_peak_rss_kb') if isinstance(light.get('prepare_stage_peak'), Mapping) else None)} |",
            f"| qret launch before parent KB | {_fmt_int(gate.get('before_qret_parent_rss_kb'))} |",
            f"| tree peak KB | {_fmt_int(light.get('tree_peak_rss_kb'))} |",
            f"| parent at tree peak KB | {_fmt_int(split.get('parent_vmrss_kb'))} |",
            f"| qret at tree peak KB | {_fmt_int(split.get('qret_vmrss_kb'))} |",
            f"| elapsed sec | {_fmt_float(light.get('elapsed_seconds'))} |",
            "",
            "## Comparison With Deep Profiling",
            "",
            "| metric | light | deep | difference |",
            "|---|---:|---:|---:|",
            f"| tree peak KB | {_fmt_int(light.get('tree_peak_rss_kb'))} | {_fmt_int(deep.get('tree_peak_rss_kb'))} | {_fmt_int(comparison.get('tree_peak_delta_kb'))} |",
            f"| parent at tree peak KB | {_fmt_int(split.get('parent_vmrss_kb'))} | {_fmt_int(deep.get('parent_at_tree_peak_kb'))} | {_fmt_int(comparison.get('parent_at_tree_delta_kb'))} |",
            f"| elapsed sec | {_fmt_float(light.get('elapsed_seconds'))} | {_fmt_float(deep.get('elapsed_seconds'))} | {_fmt_float(comparison.get('elapsed_delta_seconds'))} |",
            "",
            "## Gate Decision",
            "",
            f"process isolation gate passed: `{gate.get('passes')}`",
            f"reasons: `{', '.join(gate.get('reasons') or []) or 'none'}`",
            "",
        ]
    )
    if ab:
        lines.extend(
            [
                "## Process-Isolation A/B",
                "",
                "| variant | tree peak KB | orchestrator KB | worker KB | qret KB | elapsed sec |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for row in ab.get("results", []):
            if not isinstance(row, Mapping):
                continue
            peaks = row.get("classification", {}).get("peaks_by_kind_kb", {}) if isinstance(row.get("classification"), Mapping) else {}
            split_row = row.get("tree_peak_split") if isinstance(row.get("tree_peak_split"), Mapping) else {}
            worker_peak = max(
                int(peaks.get("prepare_worker") or 0),
                int(peaks.get("compile_worker") or 0),
            )
            lines.append(
                f"| {row.get('case')} {row.get('variant')} | {_fmt_int(row.get('tree_peak_rss_kb'))} | {_fmt_int(peaks.get('orchestrator') or split_row.get('parent_vmrss_kb'))} | {_fmt_int(worker_peak)} | {_fmt_int(row.get('qret_peak_rss_kb'))} | {_fmt_float(row.get('elapsed_seconds'))} |"
            )
    else:
        reason = payload.get("h5_ab_not_run_reason")
        if not reason:
            reason = (
                "Not run because H4 semantic correctness failed."
                if gate.get("passes") and payload.get("process_isolation_implemented")
                else "Not run because the gate did not pass."
            )
        lines.extend(["## Process-Isolation A/B", "", reason, ""])
    if h4:
        lines.extend(
            [
                "",
                "## H4 Correctness",
                "",
                "| variant | tree peak KB | qret peak KB | elapsed sec |",
                "|---|---:|---:|---:|",
            ]
        )
        for key, label in (("in_process", "in_process"), ("process_isolated", "process_isolated")):
            row = h4.get(key)
            row = row if isinstance(row, Mapping) else {}
            lines.append(
                f"| {label} | {_fmt_int(row.get('tree_peak_kb'))} | {_fmt_int(row.get('qret_peak_kb'))} | {_fmt_float(row.get('elapsed_seconds'))} |"
            )
        lines.extend(
            [
                "",
                f"- artifact hashes equal: `{h4.get('artifact_hashes_equal')}`",
                f"- raw qret metrics equal: `{h4.get('raw_metrics_equal')}`",
                f"- normalized metrics equal: `{h4.get('normalized_metrics_equal')}`",
            ]
        )
    lines.extend(
        [
            "",
            "## Semantic Comparison",
            "",
            "```text",
            json.dumps(payload.get("semantic_comparisons", {}), indent=2, sort_keys=True),
            "```",
            "",
            "## Final Answers",
            "",
            f"1. tracemallocなしH5 tree peak: {_fmt_mb(light.get('tree_peak_rss_kb'))} MB.",
            f"2. deep profileとの差: {_fmt_mb(comparison.get('tree_peak_delta_kb'))} MB.",
            f"3. qret起動前parent RSS: {_fmt_mb(gate.get('before_qret_parent_rss_kb'))} MB.",
            f"4. parent gate: {gate.get('passes')} ({', '.join(gate.get('reasons') or []) or 'none'}).",
            f"5. prepare後retained memory: {_fmt_mb(gate.get('prepare_retained_delta_kb'))} MB observed.",
            f"6. process分離実装: {bool(payload.get('process_isolation_implemented'))}.",
            f"7. process分離tree peak削減: {_fmt_mb_or_na(decision.get('median_tree_saved_kb'))} MB.",
            f"8. qret peak変化: {_fmt_int_or_na(decision.get('qret_peak_delta_kb'))} KB.",
            f"9. elapsed差: {_fmt_float(decision.get('median_elapsed_delta_ratio'))}.",
            f"10. artifact hashes一致: {h4.get('artifact_hashes_equal')}.",
            f"11. raw metrics一致: {h4.get('raw_metrics_equal')}.",
            f"12. normalized metrics一致: {h4.get('normalized_metrics_equal')}.",
            f"13. process分離production default: {decision.get('production_default')}.",
            f"14. defaultにしなかった理由: {decision.get('production_default_reason')}.",
            "15. 次はqret `LATTICE_SURGERY_MAGIC` operand/ancilla/path監査を推奨: "
            + ("yes" if not decision.get("production_default") else "after integration follow-up"),
            "16. H6は実行していません。",
            "",
            "## qret Next Candidate",
            "",
            "- `LATTICE_SURGERY_MAGIC` count: 236,736.",
            "- Total estimated: 123.1 MB; operand 79.7 MB; ancilla/path 63.5 MB.",
            "- Next audit should inspect duplicate paths, path length distribution, coordinate ranges, consecutive path compression, `std::list` node overhead, routing-time operations, random insertion/erase requirements, and vector/small-vector/pool options.",
            "",
            "## Validation",
            "",
        ]
    )
    validation = payload.get("validation", {})
    if isinstance(validation, Mapping):
        for key, value in validation.items():
            lines.append(f"- {key}: {value}")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _deep_reference_from_previous_report() -> dict[str, Any]:
    return {
        "tree_peak_rss_kb": 1_231_464,
        "qret_at_tree_peak_kb": 572_936,
        "parent_at_tree_peak_kb": 658_528,
        "parent_peak_rss_kb": 726_692,
        "elapsed_seconds": 199.27387038478628,
        "tracemalloc_current_kb": 151_470,
        "tracemalloc_peak_kb": 270_607,
        "source": "docs/benchmarks/surface_code_parent_memory_optimization.md",
    }


def _deep_vs_light(light: Mapping[str, Any], deep: Mapping[str, Any]) -> dict[str, Any]:
    split = light.get("tree_peak_split") if isinstance(light.get("tree_peak_split"), Mapping) else {}
    return {
        "tree_peak_delta_kb": None
        if light.get("tree_peak_rss_kb") is None
        else int(light["tree_peak_rss_kb"]) - int(deep["tree_peak_rss_kb"]),
        "parent_at_tree_delta_kb": None
        if not split or split.get("parent_vmrss_kb") is None
        else int(split["parent_vmrss_kb"]) - int(deep["parent_at_tree_peak_kb"]),
        "elapsed_delta_seconds": None
        if light.get("elapsed_seconds") is None
        else float(light["elapsed_seconds"]) - float(deep["elapsed_seconds"]),
    }


def _format_bool(value: Any) -> str:
    return "True" if bool(value) else "False"


def _short(value: Any, limit: int = 18) -> str:
    if value is None:
        return ""
    text = str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _write_reproducibility_report(report_path: Path, payload: Mapping[str, Any]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    same = payload.get("same_artifact_compile", {})
    same = same if isinstance(same, Mapping) else {}
    prepare = payload.get("prepare_reproducibility", {})
    prepare = prepare if isinstance(prepare, Mapping) else {}
    environment_rows = payload.get("environment_comparison", [])
    same_cmp = same.get("comparison") if isinstance(same.get("comparison"), Mapping) else {}
    prepare_cmp = prepare.get("comparison") if isinstance(prepare.get("comparison"), Mapping) else {}
    h4 = payload.get("h4_end_to_end", {})
    h4 = h4 if isinstance(h4, Mapping) else {}
    h5 = payload.get("h5_ab", {})
    h5 = h5 if isinstance(h5, Mapping) else {}
    root = payload.get("root_cause", {})
    root = root if isinstance(root, Mapping) else {}
    validation = payload.get("validation", {})
    validation = validation if isinstance(validation, Mapping) else {}

    same_in = same.get("in_process") if isinstance(same.get("in_process"), Mapping) else {}
    same_worker = same.get("compile_worker") if isinstance(same.get("compile_worker"), Mapping) else {}
    same_in_artifact = _artifact_semantics_from_result(same_in) if same_in else {}
    same_worker_artifact = _artifact_semantics_from_result(same_worker) if same_worker else {}
    same_rows = [
        ("qasm_hash", same_in_artifact.get("qasm_hash"), same_worker_artifact.get("qasm_hash")),
        ("ir_hash", same_in_artifact.get("ir_hash"), same_worker_artifact.get("ir_hash")),
        (
            "optimized_ir_hash",
            same_in_artifact.get("optimized_ir_hash"),
            same_worker_artifact.get("optimized_ir_hash"),
        ),
        (
            "instruction_count",
            same_in_artifact.get("instruction_count"),
            same_worker_artifact.get("instruction_count"),
        ),
        ("gate_depth", same_in_artifact.get("gate_depth"), same_worker_artifact.get("gate_depth")),
        (
            "cache_key",
            same_in.get("metrics", {}).get("cache_key") if isinstance(same_in.get("metrics"), Mapping) else None,
            same_worker.get("metrics", {}).get("cache_key")
            if isinstance(same_worker.get("metrics"), Mapping)
            else None,
        ),
        (
            "qret_command",
            " ".join(_qret_command_signature(same_in)),
            " ".join(_qret_command_signature(same_worker)),
        ),
        (
            "raw_metrics",
            same_cmp.get("raw_metrics", {}).get("all_equal")
            if isinstance(same_cmp.get("raw_metrics"), Mapping)
            else None,
            same_cmp.get("raw_metrics", {}).get("all_equal")
            if isinstance(same_cmp.get("raw_metrics"), Mapping)
            else None,
        ),
        (
            "normalized_metrics",
            same_cmp.get("normalized_metrics", {}).get("all_equal")
            if isinstance(same_cmp.get("normalized_metrics"), Mapping)
            else None,
            same_cmp.get("normalized_metrics", {}).get("all_equal")
            if isinstance(same_cmp.get("normalized_metrics"), Mapping)
            else None,
        ),
        (
            "returncode",
            same_cmp.get("returncode", {}).get("in_process")
            if isinstance(same_cmp.get("returncode"), Mapping)
            else None,
            same_cmp.get("returncode", {}).get("compile_worker")
            if isinstance(same_cmp.get("returncode"), Mapping)
            else None,
        ),
    ]

    prep_in = prepare_cmp.get("in_process") if isinstance(prepare_cmp.get("in_process"), Mapping) else {}
    prep_worker = (
        prepare_cmp.get("prepare_worker")
        if isinstance(prepare_cmp.get("prepare_worker"), Mapping)
        else {}
    )
    prepare_rows = [
        ("integral_scf_and_transform", "integral_value_hash"),
        ("write_qasm", "qasm_hash"),
        ("qret_parse_or_ir_precision", "ir_hash"),
        ("rz_helper_or_ir_optimization", "optimized_ir_hash"),
        ("optimized_ir_summary", "optimized_instruction_stream_hash"),
        ("artifact_instruction_count", "instruction_count"),
        ("artifact_gate_depth", "gate_depth"),
    ]

    lines = [
        "# Surface Code Process-Isolation Reproducibility",
        "",
        "## Scope",
        "",
        f"- Evaluation baseline: `{payload.get('baseline_commit_required')}`.",
        f"- Evaluation HEAD at run: `{payload.get('evaluation_head')}`.",
        "- H6 was not run.",
        "",
        "## Call Graph Audit",
        "",
        "| path | call sequence | notes |",
        "|---|---|---|",
        "| in-process prepare | `_prepare_in_process_only` -> `prepare_grouped_surface_code_step_artifact` | Generates one `SurfaceCodeStepArtifact`; cache root is explicit. |",
        "| prepare worker | `_run_worker_subprocess(prepare)` -> `--worker prepare` -> `_worker_prepare` | Fresh Python process; writes result JSON and logs. |",
        "| in-process compile | `_compile_artifact_in_process_only` -> `compile_prepared_surface_code_step_artifact` | Uses a prebuilt artifact; `reuse_cache=False`. |",
        "| compile worker | `_run_worker_subprocess(compile)` -> `--worker compile` -> `_worker_compile` | Reconstructs the exact artifact manifest and verifies file hashes. |",
        "| artifact serialization | `SurfaceCodeStepArtifact.to_dict` / `surface_code_step_artifact_from_dict` | Manifest contains paths and semantic scalars; semantic compare ignores temporary output path. |",
        "| runtime/cache roots | `_surface_code_runtime` and per-run cache roots | Same-artifact compile shares input artifact; compile output roots are separated. |",
        "",
        "## Same-Artifact Compile",
        "",
        "| field | in-process | compile worker | equal |",
        "|---|---|---|---:|",
    ]
    for field, left, right in same_rows:
        lines.append(f"| {field} | `{_short(left)}` | `{_short(right)}` | {_format_bool(left == right)} |")
    lines.extend(
        [
            "",
            f"same-artifact compile all equal: `{same_cmp.get('all_equal')}`",
            "",
            "## Prepare Reproducibility",
            "",
            "| stage | in-process hash | worker hash | equal |",
            "|---|---|---|---:|",
        ]
    )
    for stage, key in prepare_rows:
        left = prep_in.get(key)
        right = prep_worker.get(key)
        lines.append(f"| {stage} | `{_short(left)}` | `{_short(right)}` | {_format_bool(left == right)} |")
    lines.extend(
        [
            "",
            "## Environment Comparison",
            "",
            "| setting | in-process | worker | equal |",
            "|---|---|---|---:|",
        ]
    )
    for row in environment_rows:
        if not isinstance(row, Mapping):
            continue
        left = row.get("in_process")
        worker = row.get("compile_worker")
        if worker is None:
            worker = row.get("prepare_worker")
        lines.append(
            f"| {row.get('setting')} | `{_short(left, 32)}` | `{_short(worker, 32)}` | {_format_bool(row.get('identical'))} |"
        )
    lines.extend(
        [
            "",
            "## Root Cause",
            "",
            "```text",
            f"first divergent stage: {root.get('first_divergent_stage')}",
            f"root cause: {root.get('root_cause')}",
            f"fix: {root.get('fix')}",
            "```",
            "",
            "## H4 End-To-End",
            "",
        ]
    )
    if h4.get("results"):
        lines.extend(
            [
                "| variant | qasm hash | optimized IR hash | raw equal | normalized equal |",
                "|---|---|---|---:|---:|",
            ]
        )
        for row in h4.get("results", []):
            if not isinstance(row, Mapping):
                continue
            artifact = row.get("artifact") if isinstance(row.get("artifact"), Mapping) else {}
            comparison = h4.get("comparison") if isinstance(h4.get("comparison"), Mapping) else {}
            lines.append(
                f"| {row.get('variant')} | `{_short(artifact.get('qasm_hash'))}` | `{_short(artifact.get('optimized_ir_hash'))}` | {_format_bool(comparison.get('raw_metrics', {}).get('all_equal') if isinstance(comparison.get('raw_metrics'), Mapping) else False)} | {_format_bool(comparison.get('normalized_metrics', {}).get('all_equal') if isinstance(comparison.get('normalized_metrics'), Mapping) else False)} |"
            )
    else:
        lines.append(str(h4.get("not_run_reason") or "Not run."))
    lines.extend(["", "## H5 A/B", ""])
    if h5.get("results"):
        lines.extend(
            [
                "| variant | tree peak | parent/orchestrator | workers | qret | elapsed |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for row in h5.get("results", []):
            if not isinstance(row, Mapping):
                continue
            peaks = (
                row.get("classification", {}).get("peaks_by_kind_kb", {})
                if isinstance(row.get("classification"), Mapping)
                else {}
            )
            split = row.get("tree_peak_split") if isinstance(row.get("tree_peak_split"), Mapping) else {}
            worker_peak = max(
                int(peaks.get("prepare_worker") or 0),
                int(peaks.get("compile_worker") or 0),
            )
            lines.append(
                f"| {row.get('variant')} | {_fmt_int(row.get('tree_peak_rss_kb'))} | {_fmt_int(peaks.get('orchestrator') or split.get('parent_vmrss_kb'))} | {_fmt_int(worker_peak)} | {_fmt_int(row.get('qret_peak_rss_kb'))} | {_fmt_float(row.get('elapsed_seconds'))} |"
            )
    else:
        lines.append(str(h5.get("not_run_reason") or "Not run."))
    decision = payload.get("process_isolation_decision", {})
    decision = decision if isinstance(decision, Mapping) else {}
    h4_artifact_equal = h4.get("artifact_hashes_equal")
    h4_raw_equal = h4.get("raw_metrics_equal")
    h4_normalized_equal = h4.get("normalized_metrics_equal")
    lines.extend(
        [
            "",
            "## Final Answers",
            "",
            f"1. 同一artifact compileは一致したか: {same_cmp.get('all_equal')}.",
            f"2. compile worker分離自体は安全か: {bool(same_cmp.get('all_equal'))}.",
            f"3. prepareの最初の不一致stage: {root.get('first_divergent_stage')}.",
            f"4. 不一致原因: {root.get('root_cause')}",
            f"5. seed/environment/orderのどれが原因だったか: {root.get('cause_class')}.",
            f"6. 修正後H4 artifact hashは一致したか: {h4_artifact_equal if h4_artifact_equal is not None else 'not run'}.",
            f"7. raw metricsは一致したか: {h4_raw_equal if h4_raw_equal is not None else 'not run'}.",
            f"8. normalized metricsは一致したか: {h4_normalized_equal if h4_normalized_equal is not None else 'not run'}.",
            f"9. H5 A/Bを実行したか: {bool(h5.get('results'))}.",
            f"10. H5 tree peak削減量: {_fmt_mb_or_na(decision.get('median_tree_saved_kb'))} MB.",
            f"11. elapsed差: {_fmt_float(decision.get('median_elapsed_delta_ratio'))}.",
            f"12. process isolationをproduction defaultにしたか: {decision.get('production_default')}.",
            f"13. defaultにしなかった理由: {decision.get('production_default_reason')}.",
            "14. 次にqret ancilla/pathへ進むべきか: yes.",
            "15. H6を実行していないこと: yes.",
            "",
            "## qret Next Candidate",
            "",
            "- `LATTICE_SURGERY_MAGIC` count: 236,736.",
            "- Total estimated: 123.1 MB; operand 79.7 MB; ancilla/path 63.5 MB; all MachineFunction ancilla/path 68.4 MB.",
            "- Next task candidates: path length distribution, duplicate path ratio, exact duplicate sequence ratio, shared prefix/suffix ratio, coordinate range, delta encoding, straight-line segment compression, `std::list` node overhead, routing insert/erase requirements, vector/pool/offset representation.",
            "",
            "## Validation",
            "",
        ]
    )
    for key, value in validation.items():
        lines.append(f"- {key}: {value}")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_reproducibility_diagnosis(
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    report_path: Path = DEFAULT_REPRO_REPORT_PATH,
    sample_interval_sec: float = SAMPLE_INTERVAL_SEC,
    batch_size: int = 2,
    run_h5_if_accepted: bool = True,
) -> dict[str, Any]:
    output_root = output_root.resolve()
    report_path = report_path.resolve()
    run_id = time.strftime("%Y%m%d_%H%M%S")
    repro_root = output_root / "reproducibility" / run_id
    cache_root_base = output_root / "surface_code_cache" / "reproducibility" / run_id
    repro_root.mkdir(parents=True, exist_ok=True)
    safety_before = {
        "meminfo": parent_profile._meminfo(),
        "disk_free_bytes": shutil.disk_usage(output_root).free,
    }
    if int(safety_before["disk_free_bytes"]) < MIN_FREE_DISK_BYTES:
        raise RuntimeError(f"Free disk below 5 GiB for {output_root}")

    architecture = _architecture()
    runtime_before = _runtime_provenance(architecture)
    source_prepare = _prepare_in_process_only(
        case=H4_CASE,
        run_dir=repro_root / "same_artifact" / "source_prepare",
        cache_root=cache_root_base / "same_artifact" / "source_prepare",
        profile_mode="light",
        batch_size=batch_size,
        sample_interval_sec=sample_interval_sec,
    )
    source_artifact = _verify_artifact_dict(source_prepare["artifact"])
    artifact_manifest_path = Path(source_prepare["artifact_manifest_path"])
    same_in = _compile_artifact_in_process_only(
        case=H4_CASE,
        artifact=source_artifact,
        run_dir=repro_root / "same_artifact" / "in_process_compile",
        cache_root=cache_root_base / "same_artifact" / "in_process_compile",
        profile_mode="light",
        batch_size=batch_size,
        sample_interval_sec=sample_interval_sec,
    )
    same_worker = _run_worker_subprocess(
        "compile",
        case=H4_CASE,
        cache_root=cache_root_base / "same_artifact" / "compile_worker",
        run_dir=repro_root / "same_artifact" / "compile_worker",
        batch_size=batch_size,
        sample_interval_sec=sample_interval_sec,
        artifact_json=artifact_manifest_path,
    )
    same_comparison = _compile_semantic_comparison(same_in, same_worker)
    results: list[dict[str, Any]] = [source_prepare, same_in, same_worker]

    prepare_in: dict[str, Any] = {}
    prepare_worker: dict[str, Any] = {}
    prepare_comparison: dict[str, Any] = {}
    h4: dict[str, Any] = {"not_run_reason": "Not run because prepare reproducibility was not accepted."}
    h5_ab: dict[str, Any] = {"not_run_reason": "Not run because H4 acceptance did not pass."}
    decision: dict[str, Any] = {
        "production_default": False,
        "production_default_reason": "H4 acceptance did not pass",
    }
    root_cause: dict[str, Any] = {
        "first_divergent_stage": None,
        "root_cause": "not evaluated",
        "cause_class": "not evaluated",
        "fix": "not evaluated",
    }

    if same_comparison["all_equal"]:
        prepare_in = _prepare_in_process_only(
            case=H4_CASE,
            run_dir=repro_root / "prepare_reproducibility" / "in_process_prepare",
            cache_root=cache_root_base / "prepare_reproducibility" / "in_process_prepare",
            profile_mode="light",
            batch_size=batch_size,
            sample_interval_sec=sample_interval_sec,
        )
        prepare_worker = _run_worker_subprocess(
            "prepare",
            case=H4_CASE,
            cache_root=cache_root_base / "prepare_reproducibility" / "prepare_worker",
            run_dir=repro_root / "prepare_reproducibility" / "prepare_worker",
            batch_size=batch_size,
            sample_interval_sec=sample_interval_sec,
        )
        prepare_comparison = _compare_prepare_artifacts(prepare_in, prepare_worker)
        results.extend([prepare_in, prepare_worker])
        if prepare_comparison["all_equal"]:
            h4_in = run_case_once(
                case=H4_CASE,
                variant="in_process",
                output_root=output_root,
                run_group=f"reproducibility/{run_id}/h4_end_to_end",
                run_index=0,
                profile_mode="light",
                batch_size=batch_size,
                sample_interval_sec=sample_interval_sec,
            )
            h4_iso = run_case_once(
                case=H4_CASE,
                variant="process_isolated",
                output_root=output_root,
                run_group=f"reproducibility/{run_id}/h4_end_to_end",
                run_index=0,
                profile_mode="light",
                batch_size=batch_size,
                sample_interval_sec=sample_interval_sec,
            )
            h4_comparison = _compile_semantic_comparison(h4_in, h4_iso)
            h4 = {
                "results": [h4_in, h4_iso],
                "comparison": h4_comparison,
                "artifact_hashes_equal": h4_comparison["artifact_hashes"]["all_equal"],
                "raw_metrics_equal": h4_comparison["raw_metrics"]["all_equal"],
                "normalized_metrics_equal": h4_comparison["normalized_metrics"]["all_equal"],
            }
            results.extend([h4_in, h4_iso])
            if h4_comparison["all_equal"] and run_h5_if_accepted:
                h5_in_rows = [
                    run_case_once(
                        case=H5_CASE,
                        variant="in_process",
                        output_root=output_root,
                        run_group=f"reproducibility/{run_id}/h5_ab",
                        run_index=index,
                        profile_mode="light",
                        batch_size=batch_size,
                        sample_interval_sec=sample_interval_sec,
                    )
                    for index in range(2)
                ]
                h5_iso_rows = [
                    run_case_once(
                        case=H5_CASE,
                        variant="process_isolated",
                        output_root=output_root,
                        run_group=f"reproducibility/{run_id}/h5_ab",
                        run_index=index,
                        profile_mode="light",
                        batch_size=batch_size,
                        sample_interval_sec=sample_interval_sec,
                    )
                    for index in range(2)
                ]
                semantic_comparisons = {
                    f"h5_run{index}": _compile_semantic_comparison(h5_in_rows[index], h5_iso_rows[index])
                    for index in range(2)
                }
                semantic_ok = all(item["all_equal"] for item in semantic_comparisons.values())
                decision = _ab_decision(h5_in_rows, h5_iso_rows, semantic_ok=semantic_ok)
                qret_base = _median([row.get("qret_peak_rss_kb") for row in h5_in_rows])
                qret_iso = _median([row.get("qret_peak_rss_kb") for row in h5_iso_rows])
                decision["qret_peak_delta_kb"] = (
                    None
                    if qret_base is None or qret_iso is None
                    else float(qret_iso) - float(qret_base)
                )
                h5_ab = {
                    "results": [*h5_in_rows, *h5_iso_rows],
                    "semantic_comparisons": semantic_comparisons,
                    "in_process_aggregate": _aggregate_variant(
                        h5_in_rows,
                        variant="in_process",
                        case=H5_CASE,
                    ),
                    "process_isolated_aggregate": _aggregate_variant(
                        h5_iso_rows,
                        variant="process_isolated",
                        case=H5_CASE,
                    ),
                }
                results.extend([*h5_in_rows, *h5_iso_rows])
            else:
                h5_ab = {"not_run_reason": "Not run because H4 semantic correctness failed."}
        else:
            first_stage = prepare_comparison.get("first_divergent_stage")
            if first_stage == "integral_scf_and_transform":
                root = (
                    "Independent cache-miss prepare recomputed PySCF/MO integrals with "
                    "different low-bit floating values; persisted QASM/IR diverged before "
                    "compile. This is prepare nondeterminism, not compile-worker isolation."
                )
                cause_class = "floating-point/global numeric state"
                fix = (
                    "No low-risk production fix applied. Deterministic MO canonicalization "
                    "or integral-cache policy would be required and can change floating-point "
                    "generation semantics."
                )
            else:
                root = "Prepare artifacts diverged before H4 acceptance; see stage hashes."
                cause_class = "prepare ordering/environment/cache"
                fix = "No low-risk fix applied in this run."
            root_cause = {
                "first_divergent_stage": first_stage,
                "root_cause": root,
                "cause_class": cause_class,
                "fix": fix,
            }
    else:
        root_cause = {
            "first_divergent_stage": "same_artifact_compile",
            "root_cause": "Same-artifact compile differs between in-process and worker.",
            "cause_class": "compile worker environment/cache/path",
            "fix": "No H5 run; inspect compile worker environment and cache path differences.",
        }
        h4 = {"not_run_reason": "Not run because same-artifact compile failed."}
        h5_ab = {"not_run_reason": "Not run because same-artifact compile failed."}
        decision = {
            "production_default": False,
            "production_default_reason": "same-artifact compile failed",
        }

    runtime_after = _runtime_provenance(architecture)
    if (
        runtime_before.get("qret_executable_hash") != runtime_after.get("qret_executable_hash")
        or runtime_before.get("qret_core_library_hash") != runtime_after.get("qret_core_library_hash")
    ):
        raise RuntimeError("qret executable or library hash changed during reproducibility diagnosis")

    env_rows: list[dict[str, Any]] = []
    if same_in.get("settings") and same_worker.get("settings"):
        env_rows.extend(
            _compare_settings(
                same_in["settings"],
                same_worker["settings"],
                labels=("in_process", "compile_worker"),
                context="same_artifact_compile",
            )
        )
    if prepare_in.get("settings") and prepare_worker.get("settings"):
        env_rows.extend(
            _compare_settings(
                prepare_in["settings"],
                prepare_worker["settings"],
                labels=("in_process", "prepare_worker"),
                context="prepare_reproducibility",
            )
        )

    payload = {
        "evaluation_head": _git_output(["rev-parse", "HEAD"]),
        "baseline_commit_required": REPRO_BASELINE_COMMIT,
        "platform": {"python": sys.version, "system": platform.platform()},
        "python_executable": sys.executable,
        "run_id": run_id,
        "safety_before": safety_before,
        "runtime_provenance_before": runtime_before,
        "runtime_provenance_after": runtime_after,
        "same_artifact_compile": {
            "source_prepare": source_prepare,
            "in_process": same_in,
            "compile_worker": same_worker,
            "comparison": same_comparison,
        },
        "prepare_reproducibility": {
            "in_process": prepare_in,
            "prepare_worker": prepare_worker,
            "comparison": prepare_comparison,
        },
        "environment_comparison": env_rows,
        "root_cause": root_cause,
        "h4_end_to_end": h4,
        "h5_ab": h5_ab,
        "process_isolation_decision": decision,
        "results": results,
        "validation": {},
        "h6_run": False,
    }
    _write_json(output_root / "surface_code_process_isolation_reproducibility_summary.json", payload)
    _write_reproducibility_report(report_path, payload)
    return payload


def run_profile(
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    report_path: Path = DEFAULT_REPORT_PATH,
    sample_interval_sec: float = SAMPLE_INTERVAL_SEC,
    batch_size: int = 2,
    run_ab: bool = True,
) -> dict[str, Any]:
    output_root = output_root.resolve()
    report_path = report_path.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    safety_before = {
        "meminfo": parent_profile._meminfo(),
        "disk_free_bytes": shutil.disk_usage(output_root).free,
    }
    light = run_case_once(
        case=H5_CASE,
        variant="in_process",
        output_root=output_root,
        run_group="h5_light_baseline",
        run_index=0,
        profile_mode="light",
        batch_size=batch_size,
        sample_interval_sec=sample_interval_sec,
    )
    gate = _isolation_gate(light)
    results: list[dict[str, Any]] = [light]
    h4_comparison: dict[str, Any] = {}
    semantic_comparisons: dict[str, Any] = {}
    h5_ab: dict[str, Any] = {}
    decision: dict[str, Any] = {
        "production_default": False,
        "production_default_reason": "gate did not pass",
    }
    if gate["passes"] and run_ab:
        h4_in = run_case_once(
            case=H4_CASE,
            variant="in_process",
            output_root=output_root,
            run_group="h4_correctness",
            run_index=0,
            profile_mode="light",
            batch_size=batch_size,
            sample_interval_sec=sample_interval_sec,
        )
        h4_iso = run_case_once(
            case=H4_CASE,
            variant="process_isolated",
            output_root=output_root,
            run_group="h4_correctness",
            run_index=0,
            profile_mode="light",
            batch_size=batch_size,
            sample_interval_sec=sample_interval_sec,
        )
        h4_sem = _semantic_comparison(h4_in, h4_iso)
        h4_comparison = {
            "in_process": _result_memory_summary(h4_in),
            "process_isolated": _result_memory_summary(h4_iso),
            "artifact_hashes_equal": h4_sem["artifact_hashes"]["all_equal"],
            "raw_metrics_equal": h4_sem["raw_metrics"]["all_equal"],
            "normalized_metrics_equal": h4_sem["normalized_metrics"]["all_equal"],
            "details": h4_sem,
        }
        results.extend([h4_in, h4_iso])
        if not (
            h4_comparison["artifact_hashes_equal"]
            and h4_comparison["raw_metrics_equal"]
            and h4_comparison["normalized_metrics_equal"]
        ):
            decision = {
                "passes_production_acceptance": False,
                "production_default": False,
                "production_default_reason": "H4 semantic correctness failed; H5 A/B was not run",
            }
            deep = _deep_reference_from_previous_report()
            payload = {
                "evaluation_head": _git_output(["rev-parse", "HEAD"]),
                "baseline_commit_required": BASELINE_COMMIT,
                "platform": {"python": sys.version, "system": platform.platform()},
                "python_executable": sys.executable,
                "safety_before": safety_before,
                "light_baseline": light,
                "deep_reference": deep,
                "deep_vs_light": _deep_vs_light(light, deep),
                "process_isolation_gate": gate,
                "process_isolation_implemented": True,
                "h4_correctness": h4_comparison,
                "h5_ab": {},
                "h5_ab_not_run_reason": "Not run because H4 semantic correctness failed.",
                "semantic_comparisons": {"h4": h4_sem},
                "process_isolation_decision": decision,
                "results": results,
                "validation": {},
                "h6_run": False,
            }
            _write_json(output_root / "surface_code_process_isolation_summary.json", payload)
            _write_report(report_path, payload)
            return payload

        h5_in_rows = [light]
        h5_in_rows.append(
            run_case_once(
                case=H5_CASE,
                variant="in_process",
                output_root=output_root,
                run_group="h5_ab",
                run_index=1,
                profile_mode="light",
                batch_size=batch_size,
                sample_interval_sec=sample_interval_sec,
            )
        )
        h5_iso_rows = [
            run_case_once(
                case=H5_CASE,
                variant="process_isolated",
                output_root=output_root,
                run_group="h5_ab",
                run_index=index,
                profile_mode="light",
                batch_size=batch_size,
                sample_interval_sec=sample_interval_sec,
            )
            for index in range(2)
        ]
        results.extend(h5_in_rows[1:])
        results.extend(h5_iso_rows)
        semantic_comparisons = {
            "h4": h4_sem,
            "h5_run0": _semantic_comparison(h5_in_rows[0], h5_iso_rows[0]),
            "h5_run1": _semantic_comparison(h5_in_rows[1], h5_iso_rows[1]),
        }
        semantic_ok = all(
            section["artifact_hashes"]["all_equal"]
            and section["raw_metrics"]["all_equal"]
            and section["normalized_metrics"]["all_equal"]
            for section in semantic_comparisons.values()
        )
        decision = _ab_decision(h5_in_rows, h5_iso_rows, semantic_ok=semantic_ok)
        qret_base = _median([row.get("qret_peak_rss_kb") for row in h5_in_rows])
        qret_iso = _median([row.get("qret_peak_rss_kb") for row in h5_iso_rows])
        decision["qret_peak_delta_kb"] = None if qret_base is None or qret_iso is None else float(qret_iso) - float(qret_base)
        h5_ab = {
            "results": [*h5_in_rows, *h5_iso_rows],
            "in_process_aggregate": _aggregate_variant(h5_in_rows, variant="in_process", case=H5_CASE),
            "process_isolated_aggregate": _aggregate_variant(h5_iso_rows, variant="process_isolated", case=H5_CASE),
        }
    deep = _deep_reference_from_previous_report()
    payload = {
        "evaluation_head": _git_output(["rev-parse", "HEAD"]),
        "baseline_commit_required": BASELINE_COMMIT,
        "platform": {"python": sys.version, "system": platform.platform()},
        "python_executable": sys.executable,
        "safety_before": safety_before,
        "light_baseline": light,
        "deep_reference": deep,
        "deep_vs_light": _deep_vs_light(light, deep),
        "process_isolation_gate": gate,
        "process_isolation_implemented": bool(gate["passes"] and run_ab),
        "h4_correctness": h4_comparison,
        "h5_ab": h5_ab,
        "h5_ab_not_run_reason": (
            "Not run because --no-ab was requested."
            if gate["passes"] and not run_ab
            else "Not run because the gate did not pass."
            if not gate["passes"]
            else None
        ),
        "semantic_comparisons": semantic_comparisons,
        "process_isolation_decision": decision,
        "results": results,
        "validation": {},
        "h6_run": False,
    }
    _write_json(output_root / "surface_code_process_isolation_summary.json", payload)
    _write_report(report_path, payload)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure lightweight H5 parent memory and process isolation."
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--repro-report-path", type=Path, default=DEFAULT_REPRO_REPORT_PATH)
    parser.add_argument("--diagnose-reproducibility", action="store_true")
    parser.add_argument("--sample-interval-sec", type=float, default=SAMPLE_INTERVAL_SEC)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--no-ab", action="store_true")
    parser.add_argument("--case", default=H5_CASE)
    parser.add_argument("--variant", choices=("in_process", "process_isolated"), default=None)
    parser.add_argument("--worker", choices=("prepare", "compile"), default=None)
    parser.add_argument("--cache-root", type=Path, default=None)
    parser.add_argument("--result-json", type=Path, default=None)
    parser.add_argument("--artifact-json", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.worker:
        if args.cache_root is None or args.result_json is None:
            raise SystemExit("--worker requires --cache-root and --result-json")
        if args.worker == "prepare":
            return _worker_prepare(
                case=args.case,
                cache_root=args.cache_root,
                result_json=args.result_json,
                batch_size=args.batch_size,
                sample_interval_sec=args.sample_interval_sec,
            )
        if args.artifact_json is None:
            raise SystemExit("--worker compile requires --artifact-json")
        return _worker_compile(
            case=args.case,
            cache_root=args.cache_root,
            result_json=args.result_json,
            artifact_json=args.artifact_json,
            batch_size=args.batch_size,
            sample_interval_sec=args.sample_interval_sec,
        )

    if args.diagnose_reproducibility:
        payload = run_reproducibility_diagnosis(
            output_root=args.output_root,
            report_path=args.repro_report_path,
            sample_interval_sec=args.sample_interval_sec,
            batch_size=args.batch_size,
            run_h5_if_accepted=not args.no_ab,
        )
        same = payload["same_artifact_compile"]["comparison"]
        prepare = payload["prepare_reproducibility"]["comparison"]
        h5 = payload["h5_ab"]
        print(
            "repro same_artifact={same} prepare_equal={prepare} h5_run={h5}".format(
                same=same.get("all_equal"),
                prepare=prepare.get("all_equal") if isinstance(prepare, Mapping) else None,
                h5=bool(h5.get("results")) if isinstance(h5, Mapping) else False,
            )
        )
        return 0

    if args.variant is not None:
        result = run_case_once(
            case=args.case,
            variant=args.variant,
            output_root=args.output_root,
            run_group="manual",
            run_index=0,
            profile_mode="light",
            batch_size=args.batch_size,
            sample_interval_sec=args.sample_interval_sec,
        )
        print(
            "{variant} {case}: tree_peak={tree}KB elapsed={elapsed:.3f}s".format(
                variant=result["variant"],
                case=result["case"],
                tree=result.get("tree_peak_rss_kb"),
                elapsed=float(result.get("elapsed_seconds") or 0.0),
            )
        )
        return 0

    payload = run_profile(
        output_root=args.output_root,
        report_path=args.report_path,
        sample_interval_sec=args.sample_interval_sec,
        batch_size=args.batch_size,
        run_ab=not args.no_ab,
    )
    light = payload["light_baseline"]
    gate = payload["process_isolation_gate"]
    print(
        "H5 light tree_peak={tree}KB parent_before_qret={parent}KB gate={gate}".format(
            tree=light.get("tree_peak_rss_kb"),
            parent=gate.get("before_qret_parent_rss_kb"),
            gate=gate.get("passes"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
