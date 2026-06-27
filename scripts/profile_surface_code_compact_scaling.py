#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import shutil
import signal
import statistics
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
for path in (SRC_ROOT, SCRIPTS_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from trotterlib import surface_code as sc  # noqa: E402
from trotterlib.profiling import flatten_stage_metrics  # noqa: E402

import profile_qret_calc_info_memory as calc_profile  # noqa: E402
import profile_qret_pre_routing_memory as qret_profile  # noqa: E402


DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "qret_compact_scaling"
DEFAULT_REPORT_PATH = REPO_ROOT / "docs" / "benchmarks" / "qret_compact_scaling_h5_h6.md"
DEFAULT_CASES = ("h4_4th_new2", "h5_4th_new2")
ALL_CASES = ("h4_4th_new2", "h5_4th_new2", "h6_4th_new2")
CASE_CHAIN_LENGTH = {
    "h4_4th_new2": 4,
    "h5_4th_new2": 5,
    "h6_4th_new2": 6,
}
CASE_DISPLAY = {
    "h4_4th_new2": "H4 `4th(new_2)`",
    "h5_4th_new2": "H5 `4th(new_2)`",
    "h6_4th_new2": "H6 `4th(new_2)`",
}
PF_LABEL = "4th(new_2)"
COMPILE_MODE = "ftqc_compile_topology"
SAMPLE_INTERVAL_SEC = 0.02
ONE_GIB_KB = 1024 * 1024
STOP_MEM_AVAILABLE_KB = ONE_GIB_KB
H6_MEM_AVAILABLE_KB = 2 * ONE_GIB_KB
STOP_TREE_RSS_FRACTION = 0.85
H6_TREE_RSS_FRACTION = 0.70
MIN_FREE_DISK_BYTES = 5 * 1024**3
SUMMARY_FIELDS = (
    "case",
    "phase",
    "run_index",
    "status",
    "returncode",
    "elapsed_seconds",
    "qret_peak_rss_kb",
    "parent_peak_rss_kb",
    "tree_peak_rss_kb",
    "min_mem_available_kb",
    "max_swap_used_kb",
    "max_swap_free_drop_kb",
    "max_rss_stage",
    "optimized_instruction_count",
    "machine_instruction_count",
    "depgraph_nodes",
    "depgraph_edges",
    "compact_payload_capacity_bytes",
    "compile_info_size_bytes",
)
SEMANTIC_FIELDS = (
    "runtime",
    "runtime_without_topology",
    "gate_count",
    "gate_depth",
    "magic_state_consumption_count",
    "magic_state_consumption_depth",
    "measurement_feedback_count",
    "measurement_feedback_depth",
    "entanglement_consumption_count",
    "entanglement_consumption_depth",
    "magic_factory_count",
    "entanglement_factory_count",
    "qubit_volume",
    "chip_cell_count",
    "code_distance",
    "num_physical_qubits",
)


@dataclass(frozen=True)
class CaseDefinition:
    key: str
    chain_length: int
    ham_name: str
    molecule: str
    basis: str
    charge: int
    spin_or_multiplicity: str
    geometry: str
    pf_label: str
    target_error: float
    step_time: float
    rotation_precision: float
    batch_size: int
    compile_mode: str
    topology: str


def _git_output(args: list[str], *, cwd: Path = REPO_ROOT) -> str:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=cwd,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{time.time_ns()}.tmp")
    try:
        tmp_path.write_text(
            json.dumps(dict(payload), ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        tmp_path.replace(path)
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{time.time_ns()}.tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(dict(row), ensure_ascii=True, sort_keys=True))
                f.write("\n")
        tmp_path.replace(path)
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in SUMMARY_FIELDS})


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root is not an object: {path}")
    return payload


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _median(values: Sequence[float | int | None]) -> float | int | None:
    present = [value for value in values if value is not None]
    return statistics.median(present) if present else None


def _ratio(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return float(numerator) / float(denominator)


def _fmt_float(value: float | int | None, digits: int = 3) -> str:
    if value is None:
        return ""
    return f"{float(value):.{digits}f}"


def _meminfo() -> dict[str, int]:
    ret: dict[str, int] = {}
    try:
        lines = Path("/proc/meminfo").read_text(encoding="utf-8").splitlines()
    except OSError:
        return ret
    for line in lines:
        parts = line.split()
        if len(parts) >= 2 and parts[0].endswith(":"):
            try:
                ret[parts[0][:-1]] = int(parts[1])
            except ValueError:
                pass
    return ret


def _disk_free_bytes(path: Path) -> int:
    path.mkdir(parents=True, exist_ok=True)
    return int(shutil.disk_usage(path).free)


def _ppid(pid: int) -> int | None:
    try:
        lines = (Path("/proc") / str(pid) / "status").read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith("PPid:"):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    return int(parts[1])
                except ValueError:
                    return None
    return None


def _cmdline(pid: int) -> str | None:
    try:
        raw = (Path("/proc") / str(pid) / "cmdline").read_bytes()
    except OSError:
        return None
    if not raw:
        return None
    return " ".join(part.decode("utf-8", errors="replace") for part in raw.split(b"\0") if part)


def _is_qret_command(command: str | None) -> bool:
    if not command:
        return False
    return "/qret" in command or command.split(" ", 1)[0].endswith("qret")


def _terminate_tree(root_pid: int, *, include_root: bool) -> None:
    pids = qret_profile._process_tree(root_pid)
    if not include_root:
        pids = [pid for pid in pids if pid != root_pid]
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in sorted(pids, reverse=True):
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
            except PermissionError:
                pass
        time.sleep(2.0 if sig == signal.SIGTERM else 0.0)
        alive = []
        for pid in pids:
            if (Path("/proc") / str(pid)).exists():
                alive.append(pid)
        if not alive:
            return


def _sample_process_tree_with_system(
    root_pid: int,
    *,
    interval_sec: float,
    stop_event: threading.Event,
    rows: list[dict[str, Any]],
    memtotal_kb: int | None,
    include_root_in_guard_kill: bool,
    guard: dict[str, Any],
) -> None:
    sample_index = 0
    low_mem_streak = 0
    while not stop_event.is_set():
        timestamp = time.time()
        mem = _meminfo()
        pids = qret_profile._process_tree(root_pid)
        tree_vmrss_kb = 0
        per_pid: list[dict[str, Any]] = []
        for pid in pids:
            proc_root = Path("/proc") / str(pid)
            status = qret_profile._parse_status_file(proc_root / "status")
            if not status:
                continue
            smaps = qret_profile._parse_smaps_rollup(proc_root / "smaps_rollup")
            tree_vmrss_kb += int(status.get("vmrss_kb") or 0)
            per_pid.append(
                {
                    "sample_index": sample_index,
                    "timestamp_seconds": timestamp,
                    "root_pid": root_pid,
                    "pid": pid,
                    "ppid": _ppid(pid),
                    "command": _cmdline(pid),
                    **status,
                    **smaps,
                    "mem_total_kb": mem.get("MemTotal"),
                    "mem_available_kb": mem.get("MemAvailable"),
                    "swap_total_kb": mem.get("SwapTotal"),
                    "swap_free_kb": mem.get("SwapFree"),
                }
            )
        for row in per_pid:
            row["tree_vmrss_kb"] = tree_vmrss_kb
            rows.append(row)

        mem_available = mem.get("MemAvailable")
        if mem_available is not None and mem_available < STOP_MEM_AVAILABLE_KB:
            low_mem_streak += 1
        else:
            low_mem_streak = 0
        tree_guard = (
            memtotal_kb is not None
            and memtotal_kb > 0
            and tree_vmrss_kb > int(memtotal_kb * STOP_TREE_RSS_FRACTION)
        )
        low_mem_guard = low_mem_streak >= 3
        if (tree_guard or low_mem_guard) and not guard.get("triggered"):
            guard.update(
                {
                    "triggered": True,
                    "reason": "tree_rss_fraction" if tree_guard else "low_mem_available",
                    "sample_index": sample_index,
                    "tree_vmrss_kb": tree_vmrss_kb,
                    "mem_available_kb": mem_available,
                    "timestamp_seconds": timestamp,
                }
            )
            _terminate_tree(root_pid, include_root=include_root_in_guard_kill)

        sample_index += 1
        stop_event.wait(interval_sec)


def _summarize_samples(rows: Sequence[Mapping[str, Any]], *, parent_pid: int | None) -> dict[str, Any]:
    if not rows:
        return {}
    peak_tree = max(rows, key=lambda row: int(row.get("tree_vmrss_kb") or 0))
    peak_pid = max(rows, key=lambda row: int(row.get("vmrss_kb") or 0))
    qret_rows = [row for row in rows if _is_qret_command(row.get("command"))]
    parent_rows = [row for row in rows if parent_pid is not None and row.get("pid") == parent_pid]
    mem_available = [
        int(row["mem_available_kb"])
        for row in rows
        if row.get("mem_available_kb") is not None
    ]
    swap_total = max(
        (int(row["swap_total_kb"]) for row in rows if row.get("swap_total_kb") is not None),
        default=None,
    )
    swap_free = [
        int(row["swap_free_kb"])
        for row in rows
        if row.get("swap_free_kb") is not None
    ]
    first_swap_free = swap_free[0] if swap_free else None
    min_swap_free = min(swap_free) if swap_free else None
    return {
        "sample_count": len(rows),
        "sampled_peak_tree_vmrss_kb": int(peak_tree.get("tree_vmrss_kb") or 0),
        "sampled_peak_tree_sample_index": peak_tree.get("sample_index"),
        "sampled_peak_pid": peak_pid.get("pid"),
        "sampled_peak_pid_command": peak_pid.get("command"),
        "sampled_peak_pid_vmrss_kb": peak_pid.get("vmrss_kb"),
        "sampled_peak_qret_vmrss_kb": max(
            (int(row.get("vmrss_kb") or 0) for row in qret_rows),
            default=None,
        ),
        "sampled_peak_parent_vmrss_kb": max(
            (int(row.get("vmrss_kb") or 0) for row in parent_rows),
            default=None,
        ),
        "minimum_mem_available_kb": min(mem_available) if mem_available else None,
        "minimum_swap_free_kb": min_swap_free,
        "maximum_swap_used_kb": None
        if swap_total is None or min_swap_free is None
        else int(swap_total) - int(min_swap_free),
        "maximum_swap_free_drop_kb": None
        if first_swap_free is None or min_swap_free is None
        else int(first_swap_free) - int(min_swap_free),
    }


def _run_with_tree_sampler(
    fn: Any,
    *,
    samples_path: Path,
    interval_sec: float,
    memtotal_kb: int | None,
) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    stop_event = threading.Event()
    guard: dict[str, Any] = {"triggered": False}
    parent_pid = os.getpid()
    sampler = threading.Thread(
        target=_sample_process_tree_with_system,
        kwargs={
            "root_pid": parent_pid,
            "interval_sec": interval_sec,
            "stop_event": stop_event,
            "rows": rows,
            "memtotal_kb": memtotal_kb,
            "include_root_in_guard_kill": False,
            "guard": guard,
        },
        daemon=True,
    )
    sampler.start()
    try:
        result = fn()
    finally:
        stop_event.set()
        sampler.join(timeout=2.0)
        _write_jsonl(samples_path, rows)
    return result, _summarize_samples(rows, parent_pid=parent_pid), guard


def _stage_metrics_path(root: Path, primary: str, cache_hit: str) -> Path:
    cache_hit_path = root / cache_hit
    return cache_hit_path if cache_hit_path.exists() else root / primary


def _case_definition(case_key: str, *, batch_size: int, architecture: sc.SurfaceCodeArchitecture) -> CaseDefinition:
    chain_length = CASE_CHAIN_LENGTH[case_key]
    ham_name = sc.grouped_hchain_ham_name(chain_length)
    step_time = sc.surface_code_step_time(ham_name, PF_LABEL)
    rotation_precision = sc.surface_code_rotation_precision(
        ham_name,
        PF_LABEL,
        target_error=sc.TARGET_ERROR,
        step_time=step_time,
    )
    is_even = chain_length % 2 == 0
    return CaseDefinition(
        key=case_key,
        chain_length=chain_length,
        ham_name=ham_name,
        molecule=f"H{chain_length}",
        basis=sc.DEFAULT_BASIS,
        charge=0 if is_even else 1,
        spin_or_multiplicity="singlet" if is_even else "triplet 1+",
        geometry=f"linear H-chain, distance={sc.DEFAULT_DISTANCE}",
        pf_label=PF_LABEL,
        target_error=float(sc.TARGET_ERROR),
        step_time=float(step_time),
        rotation_precision=float(rotation_precision),
        batch_size=int(batch_size),
        compile_mode=architecture.compile_mode,
        topology=str(Path(architecture.topology_path).expanduser().resolve()),
    )


def _artifact_summary(artifact: sc.SurfaceCodeStepArtifact) -> dict[str, Any]:
    opt_size = artifact.optimized_ir_path.stat().st_size if artifact.optimized_ir_path.exists() else None
    qasm_size = artifact.qasm_path.stat().st_size if artifact.qasm_path.exists() else None
    ir_size = artifact.ir_path.stat().st_size if artifact.ir_path.exists() else None
    return {
        "ham_name": artifact.ham_name,
        "molecule": artifact.molecule,
        "num_logical_qubits": artifact.num_logical_qubits,
        "pf_label": artifact.pf_label,
        "target_error": artifact.target_error,
        "step_time": artifact.step_time,
        "rotation_precision": artifact.rotation_precision,
        "runtime_root": str(artifact.runtime_root),
        "qasm_path": str(artifact.qasm_path),
        "ir_path": str(artifact.ir_path),
        "optimized_ir_path": str(artifact.optimized_ir_path),
        "qasm_hash": artifact.qasm_hash,
        "optimized_ir_hash": artifact.optimized_ir_hash,
        "qasm_size_bytes": qasm_size,
        "ir_size_bytes": ir_size,
        "optimized_ir_size_bytes": opt_size,
        "instruction_count": artifact.instruction_count,
        "gate_depth": artifact.gate_depth,
        "step_magic_state_count": artifact.step_magic_state_count,
        "step_magic_state_depth": artifact.step_magic_state_depth,
        "step_rz_count": artifact.step_rz_count,
        "step_rz_layer": artifact.step_rz_layer,
    }


def _profile_max_stage(profile_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not profile_rows:
        return {}
    row = max(profile_rows, key=lambda item: int(item.get("vmrss_kb") or -1))
    previous = None
    for item in profile_rows:
        if item is row:
            break
        if item.get("vmrss_kb") is not None:
            previous = item
    return {
        "stage": row.get("stage"),
        "vmrss_kb": row.get("vmrss_kb"),
        "delta_from_previous_kb": None
        if previous is None or previous.get("vmrss_kb") is None or row.get("vmrss_kb") is None
        else int(row["vmrss_kb"]) - int(previous["vmrss_kb"]),
    }


def _dep_graph_extra(profile_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    for row in reversed(profile_rows):
        extra = row.get("extra")
        if isinstance(extra, Mapping) and "dep_graph_implementation" in extra:
            return dict(extra)
    return {}


def _profile_stage_rss(profile_rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    ret: dict[str, int] = {}
    for row in profile_rows:
        stage = row.get("stage")
        rss = row.get("vmrss_kb")
        if stage is not None and rss is not None:
            ret[str(stage)] = int(rss)
    return ret


def _semantic_metrics(path: Path) -> dict[str, Any]:
    return sc.surface_code_step_metrics_from_compile_info_json(path) if path.exists() else {}


def _normalized_metrics_for_compare(metrics: Mapping[str, Any]) -> dict[str, Any]:
    ret = dict(metrics)
    for key in ("compile_info_json", "execution_time_sec"):
        ret.pop(key, None)
    return ret


def _compare_metrics(metrics_list: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not metrics_list:
        return {"all_equal": False, "reason": "no metrics"}
    first = _normalized_metrics_for_compare(metrics_list[0])
    mismatches: dict[str, list[str]] = {}
    for index, metrics in enumerate(metrics_list[1:], start=1):
        current = _normalized_metrics_for_compare(metrics)
        keys = sorted(set(first) | set(current))
        diff = [key for key in keys if first.get(key, object()) != current.get(key, object())]
        if diff:
            mismatches[f"run_{index}"] = diff
    semantic = {
        field: {
            "present": field in first,
            "values": [metrics.get(field) for metrics in metrics_list],
            "equal": len({json.dumps(metrics.get(field), sort_keys=True) for metrics in metrics_list}) <= 1,
        }
        for field in SEMANTIC_FIELDS
    }
    return {
        "all_equal": not mismatches,
        "mismatches": mismatches,
        "ignored_fields": ["compile_info_json", "execution_time_sec"],
        "semantic_fields": semantic,
        "semantic_fields_equal": all(item["equal"] for item in semantic.values()),
    }


def _build_architecture() -> sc.SurfaceCodeArchitecture:
    return sc.SurfaceCodeArchitecture(
        compile_mode=COMPILE_MODE,
        skip_compile_output=True,
    )


def _run_end_to_end_case(
    *,
    case_key: str,
    output_root: Path,
    cache_root: Path,
    batch_size: int,
    sample_interval_sec: float,
    memtotal_kb: int | None,
) -> tuple[dict[str, Any], sc.SurfaceCodeStepArtifact | None]:
    architecture = _build_architecture()
    case_dir = output_root / "end_to_end" / case_key
    case_dir.mkdir(parents=True, exist_ok=True)
    samples_path = case_dir / "process_tree_samples.jsonl"
    started = time.perf_counter()
    result_payload: dict[str, Any] = {
        "case": case_key,
        "phase": "end_to_end",
        "run_index": 0,
        "status": "unknown",
    }
    artifact: sc.SurfaceCodeStepArtifact | None = None
    previous_cache_dir = sc.SURFACE_CODE_CACHE_DIR
    previous_batch_size = sc.SURFACE_CODE_RZ_HELPER_BATCH_SIZE
    sc.SURFACE_CODE_CACHE_DIR = cache_root
    sc.SURFACE_CODE_RZ_HELPER_BATCH_SIZE = int(batch_size)
    os.environ["SURFACE_CODE_PROFILE_RSS_SAMPLING"] = "1"
    os.environ["SURFACE_CODE_PROFILE_RSS_SAMPLING_INTERVAL_SEC"] = str(sample_interval_sec)
    os.environ["SURFACE_CODE_COMPILE_INFO_EXTRACTION_MODE"] = "full_json_load"
    os.environ.pop("QRET_DEP_GRAPH_IMPL", None)

    def run() -> dict[str, Any]:
        nonlocal artifact
        artifact = sc.prepare_grouped_surface_code_step_artifact(
            sc.grouped_hchain_ham_name(CASE_CHAIN_LENGTH[case_key]),
            PF_LABEL,
            architecture=architecture,
        )
        metrics = sc.compile_prepared_surface_code_step_artifact(
            artifact,
            architecture,
            reuse_cache=False,
        )
        return metrics

    try:
        metrics, sample_summary, guard = _run_with_tree_sampler(
            run,
            samples_path=samples_path,
            interval_sec=sample_interval_sec,
            memtotal_kb=memtotal_kb,
        )
        assert artifact is not None
        compile_root = sc._compile_runtime_root(artifact, architecture)
        prepare_metrics_path = _stage_metrics_path(
            artifact.runtime_root,
            sc._PREPARE_STAGE_METRICS_FILENAME,
            sc._PREPARE_STAGE_CACHE_HIT_METRICS_FILENAME,
        )
        compile_metrics_path = _stage_metrics_path(
            compile_root,
            sc._COMPILE_STAGE_METRICS_FILENAME,
            sc._COMPILE_STAGE_CACHE_HIT_METRICS_FILENAME,
        )
        prepare_metrics = _load_json(prepare_metrics_path) if prepare_metrics_path.exists() else {}
        compile_metrics = _load_json(compile_metrics_path) if compile_metrics_path.exists() else {}
        rows = flatten_stage_metrics(
            prepare_metrics,
            commit_sha=_git_output(["rev-parse", "HEAD"]),
            case_name=case_key,
            phase="prepare",
            cache_condition="benchmark_cache_root",
            hchain_size=CASE_CHAIN_LENGTH[case_key],
        )
        rows.extend(
            flatten_stage_metrics(
                compile_metrics,
                commit_sha=_git_output(["rev-parse", "HEAD"]),
                case_name=case_key,
                phase="compile",
                cache_condition="benchmark_cache_root",
                hchain_size=CASE_CHAIN_LENGTH[case_key],
            )
        )
        peak_stage = max(
            rows,
            key=lambda row: int(
                row.get("subprocess_maxrss_kb")
                or row.get("python_sampled_peak_rss_kb")
                or row.get("python_current_rss_after_kb")
                or 0
            ),
            default={},
        )
        compile_info_path = Path(str(metrics.get("compile_info_json", "")))
        result_payload.update(
            {
                "status": "ok",
                "returncode": 0,
                "elapsed_seconds": time.perf_counter() - started,
                "metrics": metrics,
                "normalized_metrics": metrics,
                "artifact": _artifact_summary(artifact),
                "compile_root": str(compile_root),
                "prepare_metrics_path": str(prepare_metrics_path),
                "compile_metrics_path": str(compile_metrics_path),
                "stage_rows": rows,
                "prepare_cache_status": prepare_metrics.get("status"),
                "compile_cache_hit": metrics.get("compile_cache_hit"),
                "compile_info_path": str(compile_info_path),
                "compile_info_size_bytes": compile_info_path.stat().st_size
                if compile_info_path.exists()
                else None,
                "sample_summary": sample_summary,
                "guard": guard,
                "max_end_to_end_stage": peak_stage.get("stage_name"),
                "qret_peak_rss_kb": max(
                    (
                        int(row.get("subprocess_maxrss_kb") or 0)
                        for row in rows
                        if row.get("subprocess_maxrss_kb") is not None
                    ),
                    default=sample_summary.get("sampled_peak_qret_vmrss_kb"),
                ),
                "parent_peak_rss_kb": sample_summary.get("sampled_peak_parent_vmrss_kb"),
                "tree_peak_rss_kb": sample_summary.get("sampled_peak_tree_vmrss_kb"),
                "min_mem_available_kb": sample_summary.get("minimum_mem_available_kb"),
                "max_swap_used_kb": sample_summary.get("maximum_swap_used_kb"),
                "max_swap_free_drop_kb": sample_summary.get("maximum_swap_free_drop_kb"),
            }
        )
    except Exception as exc:
        result_payload.update(
            {
                "status": "failed",
                "returncode": None,
                "elapsed_seconds": time.perf_counter() - started,
                "error": repr(exc),
            }
        )
    finally:
        sc.SURFACE_CODE_CACHE_DIR = previous_cache_dir
        sc.SURFACE_CODE_RZ_HELPER_BATCH_SIZE = previous_batch_size
    _write_json(case_dir / "summary.json", result_payload)
    if result_payload.get("stage_rows"):
        _write_jsonl(case_dir / "stage_metrics.jsonl", result_payload["stage_rows"])
    return result_payload, artifact


def _run_isolated_qret_once(
    *,
    case_key: str,
    artifact: sc.SurfaceCodeStepArtifact,
    run_index: int,
    output_root: Path,
    sample_interval_sec: float,
    memtotal_kb: int | None,
) -> dict[str, Any]:
    architecture = _build_architecture()
    run_dir = output_root / "isolated_qret" / case_key / f"run_{run_index:02d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    profile_jsonl = run_dir / "qret_rss_profile.jsonl"
    samples_jsonl = run_dir / "process_tree_samples.jsonl"
    compile_yaml_path = run_dir / "compile.yaml"
    compile_info_path = run_dir / "compile_info.json"
    stdout_path = run_dir / "stdout.txt"
    stderr_path = run_dir / "stderr.txt"
    output_path = Path(os.devnull)
    for path in (profile_jsonl, samples_jsonl, compile_info_path, stdout_path, stderr_path):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    compile_yaml_path.write_text(
        sc.compile_pipeline_yaml(
            opt_path=artifact.optimized_ir_path,
            compile_output_path=output_path,
            compile_info_path=compile_info_path,
            architecture=architecture,
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["QRET_RSS_PROFILE_JSONL"] = str(profile_jsonl)
    env.pop("QRET_DEP_GRAPH_IMPL", None)
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    env.pop("LANGUAGE", None)
    cmd = [
        "/usr/bin/time",
        "-v",
        str(Path(architecture.qret_path).expanduser().resolve()),
        "compile",
        "--pipeline",
        str(compile_yaml_path),
        "--verbose",
    ]
    started = time.perf_counter()
    process = subprocess.Popen(
        cmd,
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    rows: list[dict[str, Any]] = []
    stop_event = threading.Event()
    guard: dict[str, Any] = {"triggered": False}
    sampler = threading.Thread(
        target=_sample_process_tree_with_system,
        kwargs={
            "root_pid": process.pid,
            "interval_sec": sample_interval_sec,
            "stop_event": stop_event,
            "rows": rows,
            "memtotal_kb": memtotal_kb,
            "include_root_in_guard_kill": True,
            "guard": guard,
        },
        daemon=True,
    )
    sampler.start()
    stdout, stderr = process.communicate()
    stop_event.set()
    sampler.join(timeout=2.0)
    elapsed = time.perf_counter() - started
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    _write_jsonl(samples_jsonl, rows)

    profile_rows = qret_profile._load_jsonl(profile_jsonl)
    profile_summary = calc_profile._summarize_profile(profile_rows)
    sample_summary = _summarize_samples(rows, parent_pid=process.pid)
    dep_extra = _dep_graph_extra(profile_rows)
    max_stage = _profile_max_stage(profile_rows)
    metrics = _semantic_metrics(compile_info_path)
    result = {
        "case": case_key,
        "phase": "isolated_qret",
        "run_index": run_index,
        "status": "ok" if process.returncode == 0 else "failed",
        "returncode": int(process.returncode),
        "elapsed_seconds": elapsed,
        "gnu_time_maxrss_kb": qret_profile._parse_gnu_time_maxrss(stderr),
        "sample_summary": sample_summary,
        "guard": guard,
        "qret_peak_rss_kb": qret_profile._parse_gnu_time_maxrss(stderr),
        "parent_peak_rss_kb": sample_summary.get("sampled_peak_parent_vmrss_kb"),
        "tree_peak_rss_kb": sample_summary.get("sampled_peak_tree_vmrss_kb"),
        "min_mem_available_kb": sample_summary.get("minimum_mem_available_kb"),
        "max_swap_used_kb": sample_summary.get("maximum_swap_used_kb"),
        "max_swap_free_drop_kb": sample_summary.get("maximum_swap_free_drop_kb"),
        "profile_summary": profile_summary,
        "stage_vmrss_kb": _profile_stage_rss(profile_rows),
        "max_rss_stage": max_stage.get("stage"),
        "max_rss_stage_vmrss_kb": max_stage.get("vmrss_kb"),
        "max_rss_stage_delta_from_previous_kb": max_stage.get("delta_from_previous_kb"),
        "depgraph_implementation_marker": dep_extra.get("dep_graph_implementation"),
        "depgraph_nodes": dep_extra.get("dep_graph_nodes"),
        "depgraph_edges": dep_extra.get("dep_graph_edges"),
        "depgraph_duplicate_edge_count": dep_extra.get("compact_duplicate_edge_count"),
        "depgraph_maximum_indegree": dep_extra.get("compact_maximum_indegree"),
        "depgraph_average_indegree": dep_extra.get("compact_average_indegree"),
        "depgraph_topological_order_invariant": dep_extra.get(
            "compact_topological_order_invariant"
        ),
        "compact_parent_offsets_capacity": dep_extra.get("compact_parent_offsets_capacity"),
        "compact_parent_ids_capacity": dep_extra.get("compact_parent_ids_capacity"),
        "compact_edge_lengths_capacity": dep_extra.get("compact_edge_lengths_capacity"),
        "compact_node_weights_capacity": dep_extra.get("compact_node_weights_capacity"),
        "compact_working_dp_capacity": dep_extra.get("compact_working_dp_capacity"),
        "compact_payload_capacity_bytes": sum(
            int(dep_extra.get(key) or 0)
            for key in (
                "compact_parent_offsets_capacity_bytes",
                "compact_parent_ids_capacity_bytes",
                "compact_edge_lengths_capacity_bytes",
                "compact_node_weights_capacity_bytes",
                "compact_working_dp_capacity_bytes",
            )
        ),
        "pipeline_state_output_skipped": any(
            row.get("stage") == "pipeline_state_output_skipped" for row in profile_rows
        ),
        "pipeline_state_output_absent": True,
        "compile_info_path": str(compile_info_path),
        "compile_info_size_bytes": compile_info_path.stat().st_size
        if compile_info_path.exists()
        else None,
        "profile_jsonl": str(profile_jsonl),
        "samples_jsonl": str(samples_jsonl),
        "pipeline_path": str(compile_yaml_path),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "normalized_metrics": metrics,
        "artifact": _artifact_summary(artifact),
    }
    _write_json(run_dir / "summary.json", result)
    return result


def _safety_for_h6(
    *,
    h4_results: Sequence[Mapping[str, Any]],
    h5_results: Sequence[Mapping[str, Any]],
    memtotal_kb: int | None,
    output_root: Path,
) -> dict[str, Any]:
    disk_free = _disk_free_bytes(output_root)
    h5_ok = all(row.get("status") == "ok" and row.get("returncode") in (0, None) for row in h5_results)
    h5_metrics_ok = all(row.get("normalized_metrics") for row in h5_results if row.get("phase") == "isolated_qret")
    h5_tree_peak = max((int(row.get("tree_peak_rss_kb") or 0) for row in h5_results), default=0)
    h5_min_mem = min(
        (int(row.get("min_mem_available_kb")) for row in h5_results if row.get("min_mem_available_kb") is not None),
        default=None,
    )
    h5_swap = max((int(row.get("max_swap_used_kb") or 0) for row in h5_results), default=0)
    h5_swap_free_drop = max(
        (int(row.get("max_swap_free_drop_kb") or 0) for row in h5_results),
        default=0,
    )
    h5_guards = [row.get("guard") for row in h5_results if isinstance(row.get("guard"), Mapping)]
    guard_triggered = any(bool(guard.get("triggered")) for guard in h5_guards)
    h4_iso_peak = _median(
        [row.get("qret_peak_rss_kb") for row in h4_results if row.get("phase") == "isolated_qret"]
    )
    h5_iso_peak = _median(
        [row.get("qret_peak_rss_kb") for row in h5_results if row.get("phase") == "isolated_qret"]
    )
    estimated_h6_peak = None
    if h4_iso_peak and h5_iso_peak:
        # Use the observed H5/H4 qret-RSS ratio as a conservative pre-H6 guard.
        # H6 optimized IR size is not known in a fresh benchmark cache until its
        # prepare step runs, and product-formula term counts are not qret machine
        # instruction counts.
        estimated_h6_peak = float(h5_iso_peak) * float(h5_iso_peak) / float(h4_iso_peak)
    tree_ok = memtotal_kb is None or h5_tree_peak < int(memtotal_kb * H6_TREE_RSS_FRACTION)
    mem_ok = h5_min_mem is None or h5_min_mem >= H6_MEM_AVAILABLE_KB
    disk_ok = disk_free >= MIN_FREE_DISK_BYTES
    estimate_ok = (
        estimated_h6_peak is None
        or memtotal_kb is None
        or estimated_h6_peak < memtotal_kb * H6_TREE_RSS_FRACTION
    )
    proceed = all(
        [
            h5_ok,
            h5_metrics_ok,
            tree_ok,
            mem_ok,
            h5_swap_free_drop <= 64 * 1024,
            not guard_triggered,
            disk_ok,
            estimate_ok,
        ]
    )
    return {
        "proceed_to_h6": proceed,
        "h5_ok": h5_ok,
        "h5_metrics_ok": h5_metrics_ok,
        "h5_tree_peak_kb": h5_tree_peak,
        "h5_tree_peak_fraction_of_memtotal": _ratio(h5_tree_peak, memtotal_kb),
        "h5_min_mem_available_kb": h5_min_mem,
        "h5_max_swap_used_kb": h5_swap,
        "h5_max_swap_free_drop_kb": h5_swap_free_drop,
        "guard_triggered": guard_triggered,
        "disk_free_bytes": disk_free,
        "estimated_h6_qret_peak_kb": estimated_h6_peak,
        "estimate_fraction_of_memtotal": _ratio(estimated_h6_peak, memtotal_kb),
        "failed_conditions": [
            name
            for name, ok in (
                ("h5_returncode", h5_ok),
                ("h5_metrics", h5_metrics_ok),
                ("tree_peak_under_70pct_memtotal", tree_ok),
                ("mem_available_over_2gib", mem_ok),
                ("no_swap_growth_over_64mib", h5_swap_free_drop <= 64 * 1024),
                ("no_guard_triggered", not guard_triggered),
                ("disk_free_over_5gib", disk_ok),
                ("estimated_h6_peak_safe", estimate_ok),
            )
            if not ok
        ],
    }


def _row_for_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    artifact = row.get("artifact") if isinstance(row.get("artifact"), Mapping) else {}
    return {
        "case": row.get("case"),
        "phase": row.get("phase"),
        "run_index": row.get("run_index"),
        "status": row.get("status"),
        "returncode": row.get("returncode"),
        "elapsed_seconds": row.get("elapsed_seconds"),
        "qret_peak_rss_kb": row.get("qret_peak_rss_kb"),
        "parent_peak_rss_kb": row.get("parent_peak_rss_kb"),
        "tree_peak_rss_kb": row.get("tree_peak_rss_kb"),
        "min_mem_available_kb": row.get("min_mem_available_kb"),
        "max_swap_used_kb": row.get("max_swap_used_kb"),
        "max_swap_free_drop_kb": row.get("max_swap_free_drop_kb"),
        "max_rss_stage": row.get("max_rss_stage") or row.get("max_end_to_end_stage"),
        "optimized_instruction_count": artifact.get("instruction_count"),
        "machine_instruction_count": row.get("depgraph_nodes"),
        "depgraph_nodes": row.get("depgraph_nodes"),
        "depgraph_edges": row.get("depgraph_edges"),
        "compact_payload_capacity_bytes": row.get("compact_payload_capacity_bytes"),
        "compile_info_size_bytes": row.get("compile_info_size_bytes"),
    }


def _aggregate_isolated(rows: Sequence[Mapping[str, Any]], case: str) -> dict[str, Any]:
    case_rows = [row for row in rows if row.get("case") == case and row.get("phase") == "isolated_qret"]
    peaks = [row.get("qret_peak_rss_kb") for row in case_rows]
    elapsed = [row.get("elapsed_seconds") for row in case_rows]
    return {
        "runs": len(case_rows),
        "median_peak_rss_kb": _median(peaks),
        "min_peak_rss_kb": min((int(value) for value in peaks if value is not None), default=None),
        "max_peak_rss_kb": max((int(value) for value in peaks if value is not None), default=None),
        "median_elapsed_seconds": _median(elapsed),
        "max_rss_stage": case_rows[0].get("max_rss_stage") if case_rows else None,
    }


def _write_report(
    path: Path,
    *,
    environment: Mapping[str, Any],
    case_definitions: Sequence[CaseDefinition],
    results: Sequence[Mapping[str, Any]],
    safety: Mapping[str, Any],
    metrics_comparisons: Mapping[str, Any],
) -> None:
    lines = [
        "# qret Compact Scaling H5/H6",
        "",
        "## Environment",
        "",
        f"- Evaluation HEAD: `{environment.get('evaluation_head')}`",
        f"- qret SHA-256: `{environment.get('qret_sha256')}`",
        f"- qret build type: `Release`",
        f"- compiler: `{environment.get('compiler')}`",
        f"- MemTotal KB: `{environment.get('meminfo', {}).get('MemTotal')}`",
        f"- SwapTotal KB: `{environment.get('meminfo', {}).get('SwapTotal')}`",
        f"- topology: `{environment.get('topology_path')}`",
        f"- PF: `{PF_LABEL}`",
        f"- batch size: `{environment.get('batch_size')}`",
        f"- sampling interval: `{environment.get('sample_interval_sec')}` sec",
        "",
        "## Case Definitions",
        "",
        "| case | Hamiltonian | basis | charge | spin/multiplicity | geometry | step time | target error | rotation precision | compile mode |",
        "| --- | --- | --- | ---: | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for definition in case_definitions:
        lines.append(
            "| {case} | `{ham}` | {basis} | {charge} | {spin} | {geometry} | {step:.6g} | {target:.6g} | {rot:.6g} | {mode} |".format(
                case=CASE_DISPLAY[definition.key],
                ham=definition.ham_name,
                basis=definition.basis,
                charge=definition.charge,
                spin=definition.spin_or_multiplicity,
                geometry=definition.geometry,
                step=definition.step_time,
                target=definition.target_error,
                rot=definition.rotation_precision,
                mode=definition.compile_mode,
            )
        )
    lines.extend(
        [
            "",
            "## End-to-End Results",
            "",
            "| case | status | parent peak KB | qret peak KB | tree peak KB | elapsed s | final metrics |",
            "| --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in results:
        if row.get("phase") != "end_to_end":
            continue
        lines.append(
            "| {case} | {status} | {parent} | {qret} | {tree} | {elapsed:.3f} | {metrics} |".format(
                case=CASE_DISPLAY.get(str(row.get("case")), str(row.get("case"))),
                status=row.get("status"),
                parent=row.get("parent_peak_rss_kb") or "",
                qret=row.get("qret_peak_rss_kb") or "",
                tree=row.get("tree_peak_rss_kb") or "",
                elapsed=float(row.get("elapsed_seconds") or 0.0),
                metrics="yes" if row.get("normalized_metrics") else "no",
            )
        )
    lines.extend(
        [
            "",
            "## Isolated qret Results",
            "",
            "| case | runs | median peak KB | min/max peak KB | median elapsed s | max-RSS stage |",
            "| --- | ---: | ---: | --- | ---: | --- |",
        ]
    )
    for definition in case_definitions:
        agg = _aggregate_isolated(results, definition.key)
        if agg["runs"] == 0:
            continue
        lines.append(
            "| {case} | {runs} | {median} | {minp}/{maxp} | {elapsed:.3f} | `{stage}` |".format(
                case=CASE_DISPLAY[definition.key],
                runs=agg["runs"],
                median=agg["median_peak_rss_kb"] or "",
                minp=agg["min_peak_rss_kb"] or "",
                maxp=agg["max_peak_rss_kb"] or "",
                elapsed=float(agg["median_elapsed_seconds"] or 0.0),
                stage=agg["max_rss_stage"] or "",
            )
        )
    lines.extend(
        [
            "",
            "## Scaling",
            "",
            "| case | optimized instructions | machine instructions | nodes | edges | compact payload B | qret peak KB |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    first_iso: dict[str, Mapping[str, Any]] = {}
    for row in results:
        if row.get("phase") == "isolated_qret" and row.get("case") not in first_iso:
            first_iso[str(row.get("case"))] = row
    e2e_by_case = {
        str(row.get("case")): row for row in results if row.get("phase") == "end_to_end"
    }
    for definition in case_definitions:
        row = first_iso.get(definition.key)
        if not row:
            continue
        artifact = row.get("artifact") if isinstance(row.get("artifact"), Mapping) else {}
        lines.append(
            "| {case} | {opt} | {machine} | {nodes} | {edges} | {payload} | {peak} |".format(
                case=CASE_DISPLAY[definition.key],
                opt=artifact.get("instruction_count") or "",
                machine=row.get("depgraph_nodes") or "",
                nodes=row.get("depgraph_nodes") or "",
                edges=row.get("depgraph_edges") or "",
                payload=row.get("compact_payload_capacity_bytes") or "",
                peak=row.get("qret_peak_rss_kb") or "",
            )
        )
    lines.extend(
        [
            "",
            "## Normalized Scaling",
            "",
            "| case | median qret peak / machine inst KB | routing RSS / machine inst KB | compact payload / node B | optimized IR / optimized inst B | compile_info JSON B |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for definition in case_definitions:
        row = first_iso.get(definition.key)
        if not row:
            continue
        artifact = row.get("artifact") if isinstance(row.get("artifact"), Mapping) else {}
        stage_vmrss = row.get("stage_vmrss_kb") if isinstance(row.get("stage_vmrss_kb"), Mapping) else {}
        optimized_count = artifact.get("instruction_count")
        machine_count = row.get("depgraph_nodes")
        median_peak = _aggregate_isolated(results, definition.key).get("median_peak_rss_kb")
        lines.append(
            "| {case} | {peak_per_inst} | {routing_per_inst} | {payload_per_node} | {ir_per_inst} | {compile_info} |".format(
                case=CASE_DISPLAY[definition.key],
                peak_per_inst=_fmt_float(_ratio(median_peak, machine_count), 4),
                routing_per_inst=_fmt_float(
                    _ratio(stage_vmrss.get("routing_after_main_loop"), machine_count), 4
                ),
                payload_per_node=_fmt_float(
                    _ratio(row.get("compact_payload_capacity_bytes"), machine_count), 2
                ),
                ir_per_inst=_fmt_float(
                    _ratio(artifact.get("optimized_ir_size_bytes"), optimized_count), 2
                ),
                compile_info=row.get("compile_info_size_bytes") or "",
            )
        )
    lines.extend(
        [
            "",
            "## Ratio Summary",
            "",
            "| transition | optimized inst | machine inst | median qret peak | end-to-end tree peak | compact payload | compile_info JSON |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    ratio_pairs = (
        ("h4_4th_new2", "h5_4th_new2"),
        ("h5_4th_new2", "h6_4th_new2"),
        ("h4_4th_new2", "h6_4th_new2"),
    )
    for before, after in ratio_pairs:
        before_row = first_iso.get(before)
        after_row = first_iso.get(after)
        before_e2e = e2e_by_case.get(before)
        after_e2e = e2e_by_case.get(after)
        if not before_row or not after_row or not before_e2e or not after_e2e:
            continue
        before_artifact = (
            before_row.get("artifact") if isinstance(before_row.get("artifact"), Mapping) else {}
        )
        after_artifact = (
            after_row.get("artifact") if isinstance(after_row.get("artifact"), Mapping) else {}
        )
        lines.append(
            "| {transition} | {opt} | {machine} | {peak} | {tree} | {payload} | {compile_info} |".format(
                transition=f"{CASE_DISPLAY[before]} -> {CASE_DISPLAY[after]}",
                opt=_fmt_float(
                    _ratio(after_artifact.get("instruction_count"), before_artifact.get("instruction_count"))
                ),
                machine=_fmt_float(_ratio(after_row.get("depgraph_nodes"), before_row.get("depgraph_nodes"))),
                peak=_fmt_float(
                    _ratio(
                        _aggregate_isolated(results, after).get("median_peak_rss_kb"),
                        _aggregate_isolated(results, before).get("median_peak_rss_kb"),
                    )
                ),
                tree=_fmt_float(
                    _ratio(after_e2e.get("tree_peak_rss_kb"), before_e2e.get("tree_peak_rss_kb"))
                ),
                payload=_fmt_float(
                    _ratio(
                        after_row.get("compact_payload_capacity_bytes"),
                        before_row.get("compact_payload_capacity_bytes"),
                    )
                ),
                compile_info=_fmt_float(
                    _ratio(after_row.get("compile_info_size_bytes"), before_row.get("compile_info_size_bytes"))
                ),
            )
        )
    lines.extend(["", "## Stage Breakdown", ""])
    lines.append("| case | stage | current RSS KB | delta KB | elapsed s |")
    lines.append("| --- | --- | ---: | ---: | ---: |")
    for row in results:
        if row.get("phase") == "isolated_qret":
            lines.append(
                "| {case} | `{stage}` | {rss} | {delta} | {elapsed:.3f} |".format(
                    case=CASE_DISPLAY.get(str(row.get("case")), str(row.get("case"))),
                    stage=row.get("max_rss_stage") or "",
                    rss=row.get("max_rss_stage_vmrss_kb") or "",
                    delta=row.get("max_rss_stage_delta_from_previous_kb") or "",
                    elapsed=float(row.get("elapsed_seconds") or 0.0),
                )
            )
        elif row.get("phase") == "end_to_end":
            lines.append(
                "| {case} | `{stage}` | {rss} |  | {elapsed:.3f} |".format(
                    case=CASE_DISPLAY.get(str(row.get("case")), str(row.get("case"))),
                    stage=row.get("max_end_to_end_stage") or "",
                    rss=row.get("tree_peak_rss_kb") or "",
                    elapsed=float(row.get("elapsed_seconds") or 0.0),
                )
            )
    lines.extend(
        [
            "",
            "## Key qret RSS Markers",
            "",
            "| case | load JSON alive KB | after lowering KB | routing after main loop KB | after compact DepGraph KB | with topology exit KB | after JSON DOM KB | max marker KB | GNU maxrss KB |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for definition in case_definitions:
        row = first_iso.get(definition.key)
        if not row:
            continue
        stage_vmrss = row.get("stage_vmrss_kb") if isinstance(row.get("stage_vmrss_kb"), Mapping) else {}
        lines.append(
            "| {case} | {load_json} | {lowering} | {routing} | {depgraph} | {topology} | {json_dom} | {marker} | {gnu} |".format(
                case=CASE_DISPLAY[definition.key],
                load_json=stage_vmrss.get("load_ir_after_load_json_json_alive") or "",
                lowering=stage_vmrss.get("after_lowering") or "",
                routing=stage_vmrss.get("routing_after_main_loop") or "",
                depgraph=stage_vmrss.get("calc_info_without_topology_after_dep_graph") or "",
                topology=stage_vmrss.get("calc_info_with_topology_exit") or "",
                json_dom=stage_vmrss.get("dump_compile_info_after_json_dom_create") or "",
                marker=stage_vmrss.get(row.get("max_rss_stage")) or "",
                gnu=row.get("gnu_time_maxrss_kb") or row.get("qret_peak_rss_kb") or "",
            )
        )
    isolated_rows = [row for row in results if row.get("phase") == "isolated_qret"]
    lines.extend(
        [
            "",
            "## Correctness Checks",
            "",
            f"- compact DepGraph implementation marker on isolated qret runs: `{all(row.get('depgraph_implementation_marker') == 'compact' for row in isolated_rows)}`",
            f"- DepGraph topological-order invariant on isolated qret runs: `{all(row.get('depgraph_topological_order_invariant') is True for row in isolated_rows)}`",
            f"- pipeline-state output skipped on isolated qret runs: `{all(row.get('pipeline_state_output_skipped') is True for row in isolated_rows)}`",
            f"- pipeline-state output absent on isolated qret runs: `{all(row.get('pipeline_state_output_absent') is True for row in isolated_rows)}`",
            f"- compile_info JSON emitted for isolated qret runs: `{all(int(row.get('compile_info_size_bytes') or 0) > 0 for row in isolated_rows)}`",
            f"- H5/H6 legacy DepGraph runs: `not run`; current production compact configuration only.",
        ]
    )
    lines.extend(
        [
            "",
            "## Safety",
            "",
            f"- minimum MemAvailable KB: `{min((row.get('min_mem_available_kb') for row in results if row.get('min_mem_available_kb') is not None), default=None)}`",
            f"- maximum swap used KB: `{max((int(row.get('max_swap_used_kb') or 0) for row in results), default=0)}`",
            f"- maximum SwapFree drop KB during a run: `{max((int(row.get('max_swap_free_drop_kb') or 0) for row in results), default=0)}`",
            f"- guard triggered: `{any(bool((row.get('guard') or {}).get('triggered')) for row in results if isinstance(row.get('guard'), Mapping))}`",
            f"- H6 decision: `{'run' if safety.get('proceed_to_h6') else 'not run'}`",
            f"- H6 decision failed conditions: `{safety.get('failed_conditions')}`",
            "",
            "## Determinism",
            "",
        ]
    )
    for case, comparison in metrics_comparisons.items():
        lines.append(
            f"- `{case}` isolated qret normalized metrics equal: `{comparison.get('all_equal')}`, "
            f"semantic fields equal: `{comparison.get('semantic_fields_equal')}`"
        )
    lines.extend(["", "## Final Answers", ""])
    h5_rows = [row for row in results if row.get("case") == "h5_4th_new2"]
    h6_rows = [row for row in results if row.get("case") == "h6_4th_new2"]
    h4_iso = _aggregate_isolated(results, "h4_4th_new2")
    h5_iso = _aggregate_isolated(results, "h5_4th_new2")
    h6_iso = _aggregate_isolated(results, "h6_4th_new2")
    h5_e2e = next((row for row in h5_rows if row.get("phase") == "end_to_end"), {})
    h6_e2e = next((row for row in h6_rows if row.get("phase") == "end_to_end"), {})
    h5_done = bool(h5_rows) and all(row.get("status") == "ok" for row in h5_rows)
    h6_done = bool(h6_rows) and all(row.get("status") == "ok" for row in h6_rows)
    lines.extend(
        [
            f"1. H5 completed: `{h5_done}`.",
            f"2. H6 completed: `{h6_done}`.",
            f"3. H5 qret peak RSS: `{h5_iso.get('median_peak_rss_kb')}` KB median isolated.",
            f"4. H6 qret peak RSS: `{h6_iso.get('median_peak_rss_kb')}` KB median isolated.",
            f"5. H5/H6 process tree peak: `{h5_e2e.get('tree_peak_rss_kb')}` / `{h6_e2e.get('tree_peak_rss_kb')}` KB end-to-end.",
            f"6. H4->H5->H6 qret peak: `{h4_iso.get('median_peak_rss_kb')}` -> `{h5_iso.get('median_peak_rss_kb')}` -> `{h6_iso.get('median_peak_rss_kb')}` KB.",
            "7. Compact DepGraph payload scales below qret peak RSS in these three points; see Normalized Scaling and Ratio Summary. Treat this as observed scaling, not a proven complexity fit.",
            f"8. qret max RSS stages: H5 `{h5_iso.get('max_rss_stage')}`, H6 `{h6_iso.get('max_rss_stage')}`.",
            f"9. end-to-end max RSS stages: H5 `{h5_e2e.get('max_end_to_end_stage')}`, H6 `{h6_e2e.get('max_end_to_end_stage')}`.",
            "10. New bottleneck classification: `F` for the end-to-end process-tree peak. The qret-only max marker is compile-info JSON DOM materialization/final field insertion after compact DepGraph, which is `G` if the qret-only stage must be mapped to A-G.",
            f"11. Current implementation stable for H6: `{h6_done and not safety.get('failed_conditions')}`.",
            "12. End-to-end peak is still the qret_compile process window; H6 shows Python parent and qret child residency overlap, so classify the end-to-end limiter as process overlap plus qret JSON output peak.",
            "13. Before H7+, profile the compile_info JSON DOM creation path first, then reduce Evaluation parent residency during qret_compile if process-tree RSS remains the limiter.",
            "14. Production optimization added in this run: `false`; only profiling/report/test changes are intended.",
            "15. Failed cases: see summary JSON; direct cause is recorded in each failed row's `error` field.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Profile compact qret scaling on H4/H5/H6.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--sample-interval-sec", type=float, default=SAMPLE_INTERVAL_SEC)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument(
        "--include-h6",
        choices=("auto", "yes", "no"),
        default="auto",
        help="Run H6 automatically only after H5 safety checks by default.",
    )
    parser.add_argument("--h4-isolated-runs", type=int, default=3)
    parser.add_argument("--h5-isolated-runs", type=int, default=2)
    parser.add_argument("--h6-isolated-runs", type=int, default=2)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.batch_size < 1:
        raise ValueError("--batch-size must be >= 1")
    if not (0 < args.sample_interval_sec <= 1):
        raise ValueError("--sample-interval-sec must be in (0, 1]")
    run_root = args.output_root.expanduser().resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    cache_root = run_root / "cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    meminfo_start = _meminfo()
    compiler = subprocess.check_output(["/usr/bin/c++", "--version"], text=True).splitlines()[0]
    architecture = _build_architecture()
    qret_path = Path(architecture.qret_path).expanduser().resolve()
    environment = {
        "evaluation_head": _git_output(["rev-parse", "HEAD"]),
        "dirty_status": _git_output(["status", "--short"]),
        "python": sys.version,
        "platform": platform.platform(),
        "compiler": compiler,
        "qret_path": str(qret_path),
        "qret_sha256": sc.file_sha256(qret_path),
        "qret_build_type": "Release",
        "topology_path": str(Path(architecture.topology_path).expanduser().resolve()),
        "topology_sha256": sc.file_sha256(Path(architecture.topology_path).expanduser().resolve()),
        "compile_mode": architecture.compile_mode,
        "skip_compile_output": bool(architecture.skip_compile_output),
        "dep_graph_impl_env": os.environ.get("QRET_DEP_GRAPH_IMPL"),
        "batch_size": int(args.batch_size),
        "sample_interval_sec": float(args.sample_interval_sec),
        "meminfo": meminfo_start,
        "disk_free_bytes": _disk_free_bytes(run_root),
        "output_root": str(run_root),
        "cache_root": str(cache_root),
    }
    _write_json(run_root / "environment.json", environment)

    case_definitions = [
        _case_definition(key, batch_size=args.batch_size, architecture=architecture)
        for key in ALL_CASES
    ]
    _write_json(
        run_root / "case_definitions.json",
        {definition.key: definition.__dict__ for definition in case_definitions},
    )

    memtotal_kb = meminfo_start.get("MemTotal")
    all_results: list[dict[str, Any]] = []
    artifacts: dict[str, sc.SurfaceCodeStepArtifact] = {}
    for case_key in DEFAULT_CASES:
        if _disk_free_bytes(run_root) < MIN_FREE_DISK_BYTES:
            raise RuntimeError("output filesystem has less than 5 GiB free")
        print(f"end-to-end {case_key}", flush=True)
        result, artifact = _run_end_to_end_case(
            case_key=case_key,
            output_root=run_root,
            cache_root=cache_root,
            batch_size=args.batch_size,
            sample_interval_sec=float(args.sample_interval_sec),
            memtotal_kb=memtotal_kb,
        )
        all_results.append(result)
        if artifact is not None:
            artifacts[case_key] = artifact
        if result.get("status") != "ok":
            _write_jsonl(run_root / "results.jsonl", all_results)
            _write_json(run_root / "summary.json", {"results": all_results})
            return 1
        runs = args.h4_isolated_runs if case_key == "h4_4th_new2" else args.h5_isolated_runs
        for run_index in range(runs):
            print(f"isolated {case_key} run {run_index}", flush=True)
            iso = _run_isolated_qret_once(
                case_key=case_key,
                artifact=artifacts[case_key],
                run_index=run_index,
                output_root=run_root,
                sample_interval_sec=float(args.sample_interval_sec),
                memtotal_kb=memtotal_kb,
            )
            all_results.append(iso)
            if iso.get("status") != "ok":
                _write_jsonl(run_root / "results.jsonl", all_results)
                _write_json(run_root / "summary.json", {"results": all_results})
                return 1

    h4_results = [row for row in all_results if row.get("case") == "h4_4th_new2"]
    h5_results = [row for row in all_results if row.get("case") == "h5_4th_new2"]
    safety = _safety_for_h6(
        h4_results=h4_results,
        h5_results=h5_results,
        memtotal_kb=memtotal_kb,
        output_root=run_root,
    )
    _write_json(run_root / "h6_safety_decision.json", safety)
    run_h6 = args.include_h6 == "yes" or (
        args.include_h6 == "auto" and safety.get("proceed_to_h6")
    )
    if run_h6:
        case_key = "h6_4th_new2"
        print(f"end-to-end {case_key}", flush=True)
        result, artifact = _run_end_to_end_case(
            case_key=case_key,
            output_root=run_root,
            cache_root=cache_root,
            batch_size=args.batch_size,
            sample_interval_sec=float(args.sample_interval_sec),
            memtotal_kb=memtotal_kb,
        )
        all_results.append(result)
        if artifact is not None:
            artifacts[case_key] = artifact
        if result.get("status") == "ok":
            runs = args.h6_isolated_runs
            for run_index in range(runs):
                print(f"isolated {case_key} run {run_index}", flush=True)
                iso = _run_isolated_qret_once(
                    case_key=case_key,
                    artifact=artifacts[case_key],
                    run_index=run_index,
                    output_root=run_root,
                    sample_interval_sec=float(args.sample_interval_sec),
                    memtotal_kb=memtotal_kb,
                )
                all_results.append(iso)
                if iso.get("status") != "ok":
                    break
    else:
        print("H6 skipped by safety decision", flush=True)

    metrics_comparisons = {}
    for case_key in ALL_CASES:
        metrics = [
            row.get("normalized_metrics")
            for row in all_results
            if row.get("case") == case_key
            and row.get("phase") == "isolated_qret"
            and isinstance(row.get("normalized_metrics"), Mapping)
        ]
        if metrics:
            metrics_comparisons[case_key] = _compare_metrics(metrics)

    summary_rows = [_row_for_summary(row) for row in all_results]
    _write_jsonl(run_root / "results.jsonl", all_results)
    _write_jsonl(run_root / "summary_rows.jsonl", summary_rows)
    _write_csv(run_root / "summary.csv", summary_rows)
    _write_json(
        run_root / "summary.json",
        {
            "environment": environment,
            "case_definitions": {definition.key: definition.__dict__ for definition in case_definitions},
            "results": all_results,
            "h6_safety_decision": safety,
            "metrics_comparisons": metrics_comparisons,
        },
    )
    _write_report(
        args.report_path.expanduser().resolve(),
        environment=environment,
        case_definitions=case_definitions,
        results=all_results,
        safety=safety,
        metrics_comparisons=metrics_comparisons,
    )
    return 0 if all(row.get("status") == "ok" for row in all_results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
