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
import profile_surface_code_compact_scaling as compact_profile  # noqa: E402


DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "qret_compile_info_output_modes"
DEFAULT_REPORT_PATH = (
    REPO_ROOT / "docs" / "benchmarks" / "qret_compile_info_summary_optimization.md"
)
PF_LABEL = "4th(new_2)"
COMPILE_MODE = "ftqc_compile_topology"
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
OUTPUT_MODES = ("summary", "full")
TIME_SERIES_KEYS = (
    "gate_throughput",
    "measurement_feedback_rate",
    "magic_state_consumption_rate",
    "entanglement_consumption_rate",
    "chip_cell_algorithmic_qubit",
    "chip_cell_algorithmic_qubit_ratio",
    "chip_cell_active_qubit_area",
    "chip_cell_active_qubit_area_ratio",
)
IMPORTANT_MARKERS = (
    "routing_after_main_loop",
    "calc_info_without_topology_after_dep_graph",
    "calc_info_with_topology_exit",
    "dump_compile_info_before_json_dom_create",
    "dump_compile_info_after_json_dom_create",
    "compile_info_json_after_assign_chip_cell_active_qubit_area_ratio",
    "compile_info_summary_after_stats_chip_cell_active_qubit_area_ratio",
    "dump_compile_info_after_json_stream_write",
    "dump_compile_info_after_json_dom_destroy",
    "run_compilation_end",
)
SEMANTIC_COMPARE_IGNORES = {"compile_info_json", "execution_time_sec"}
SAMPLE_INTERVAL_SEC = 0.02
MIN_FREE_DISK_BYTES = 5 * 1024**3


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
    fields = (
        "case",
        "phase",
        "output_mode",
        "run_index",
        "status",
        "returncode",
        "elapsed_seconds",
        "qret_peak_rss_kb",
        "parent_peak_rss_kb",
        "tree_peak_rss_kb",
        "compile_info_size_bytes",
        "max_rss_stage",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root is not an object: {path}")
    return payload


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


def _fmt_int(value: Any) -> str:
    if value is None:
        return ""
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return str(value)


def _architecture(output_mode: str) -> sc.SurfaceCodeArchitecture:
    return sc.SurfaceCodeArchitecture(
        compile_mode=COMPILE_MODE,
        skip_compile_output=True,
        compile_info_output_mode=output_mode,
    )


def _artifact_summary(artifact: sc.SurfaceCodeStepArtifact) -> dict[str, Any]:
    return compact_profile._artifact_summary(artifact)


def _metric_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload, _field_count, _mode = sc._load_compile_info_metrics_json(
        path,
        extraction_mode="top_level_metric_fields",
    )
    metrics = sc.normalize_surface_code_step_metrics(payload, context=str(path))
    metrics["compile_info_json"] = str(path.resolve())
    return metrics


def _profile_stage_rss(profile_rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    ret: dict[str, int] = {}
    for row in profile_rows:
        stage = row.get("stage")
        rss = row.get("vmrss_kb")
        if stage is not None and rss is not None:
            ret[str(stage)] = int(rss)
    return ret


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


def _max_present(*values: int | None) -> int | None:
    present = [int(value) for value in values if value is not None]
    return max(present) if present else None


def _is_qret_command(command: str | None) -> bool:
    return compact_profile._is_qret_command(command)


def _tree_peak_split(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    root_pid = rows[0].get("root_pid")
    by_sample: dict[Any, list[Mapping[str, Any]]] = {}
    for row in rows:
        by_sample.setdefault(row.get("sample_index"), []).append(row)
    peak_index, peak_rows = max(
        by_sample.items(),
        key=lambda item: max(int(row.get("tree_vmrss_kb") or 0) for row in item[1]),
    )
    tree_peak = max(int(row.get("tree_vmrss_kb") or 0) for row in peak_rows)
    parent_rows = [row for row in peak_rows if row.get("pid") == root_pid]
    qret_rows = [row for row in peak_rows if _is_qret_command(row.get("command"))]
    parent_vmrss = max((int(row.get("vmrss_kb") or 0) for row in parent_rows), default=None)
    qret_vmrss = max((int(row.get("vmrss_kb") or 0) for row in qret_rows), default=None)
    return {
        "sample_index": peak_index,
        "tree_vmrss_kb": tree_peak,
        "root_pid": root_pid,
        "parent_vmrss_kb": parent_vmrss,
        "qret_vmrss_kb": qret_vmrss,
        "other_vmrss_kb": None
        if parent_vmrss is None and qret_vmrss is None
        else tree_peak - int(parent_vmrss or 0) - int(qret_vmrss or 0),
        "commands": [
            {
                "pid": row.get("pid"),
                "ppid": row.get("ppid"),
                "vmrss_kb": row.get("vmrss_kb"),
                "command": row.get("command"),
            }
            for row in sorted(peak_rows, key=lambda item: int(item.get("vmrss_kb") or 0), reverse=True)
        ],
    }


def _read_stage(compile_metrics: Mapping[str, Any], stage_name: str) -> dict[str, Any]:
    for stage in compile_metrics.get("stages", []):
        if isinstance(stage, Mapping) and stage.get("name") == stage_name:
            return dict(stage)
    return {}


def _semantic_normalized(metrics: Mapping[str, Any]) -> dict[str, Any]:
    ret = dict(metrics)
    for key in SEMANTIC_COMPARE_IGNORES:
        ret.pop(key, None)
    return ret


def _compare_metrics(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    left = _semantic_normalized(baseline)
    right = _semantic_normalized(candidate)
    keys = sorted(set(left) | set(right))
    mismatches = [key for key in keys if left.get(key, object()) != right.get(key, object())]
    return {
        "all_equal": not mismatches,
        "mismatches": mismatches,
        "ignored_fields": sorted(SEMANTIC_COMPARE_IGNORES),
        "field_count": len(keys),
    }


def _run_isolated_qret_once(
    *,
    case_key: str,
    output_mode: str,
    artifact: sc.SurfaceCodeStepArtifact,
    run_index: int,
    output_root: Path,
    sample_interval_sec: float,
    memtotal_kb: int | None,
) -> dict[str, Any]:
    architecture = _architecture(output_mode)
    run_dir = output_root / "isolated_qret" / case_key / output_mode / f"run_{run_index:02d}"
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
        target=compact_profile._sample_process_tree_with_system,
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
    sample_summary = compact_profile._summarize_samples(rows, parent_pid=process.pid)
    gnu_maxrss = qret_profile._parse_gnu_time_maxrss(stderr)
    dep_extra = _dep_graph_extra(profile_rows)
    max_stage = _profile_max_stage(profile_rows)
    metrics = _metric_summary(compile_info_path)
    result = {
        "case": case_key,
        "phase": "isolated_qret",
        "output_mode": output_mode,
        "run_index": run_index,
        "status": "ok" if process.returncode == 0 else "failed",
        "returncode": int(process.returncode),
        "elapsed_seconds": elapsed,
        "gnu_time_maxrss_kb": gnu_maxrss,
        "qret_peak_rss_kb": _max_present(
            gnu_maxrss,
            sample_summary.get("sampled_peak_qret_vmrss_kb"),
        ),
        "parent_peak_rss_kb": sample_summary.get("sampled_peak_parent_vmrss_kb"),
        "tree_peak_rss_kb": sample_summary.get("sampled_peak_tree_vmrss_kb"),
        "tree_peak_split": _tree_peak_split(rows),
        "min_mem_available_kb": sample_summary.get("minimum_mem_available_kb"),
        "max_swap_used_kb": sample_summary.get("maximum_swap_used_kb"),
        "max_swap_free_drop_kb": sample_summary.get("maximum_swap_free_drop_kb"),
        "sample_summary": sample_summary,
        "guard": guard,
        "profile_summary": calc_profile._summarize_profile(profile_rows),
        "stage_vmrss_kb": _profile_stage_rss(profile_rows),
        "max_rss_stage": max_stage.get("stage"),
        "max_rss_stage_vmrss_kb": max_stage.get("vmrss_kb"),
        "max_rss_stage_delta_from_previous_kb": max_stage.get("delta_from_previous_kb"),
        "depgraph_implementation_marker": dep_extra.get("dep_graph_implementation"),
        "depgraph_nodes": dep_extra.get("dep_graph_nodes"),
        "depgraph_edges": dep_extra.get("dep_graph_edges"),
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
    if process.returncode != 0:
        raise RuntimeError(f"isolated qret failed for {case_key} {output_mode}: {stderr[-4000:]}")
    return result


def _run_end_to_end_case(
    *,
    case_key: str,
    output_mode: str,
    output_root: Path,
    cache_root: Path,
    batch_size: int,
    sample_interval_sec: float,
    memtotal_kb: int | None,
) -> tuple[dict[str, Any], sc.SurfaceCodeStepArtifact | None]:
    architecture = _architecture(output_mode)
    case_dir = output_root / "end_to_end" / case_key / output_mode
    case_dir.mkdir(parents=True, exist_ok=True)
    samples_path = case_dir / "process_tree_samples.jsonl"
    started = time.perf_counter()
    result_payload: dict[str, Any] = {
        "case": case_key,
        "phase": "end_to_end",
        "output_mode": output_mode,
        "run_index": 0,
        "status": "unknown",
    }
    artifact: sc.SurfaceCodeStepArtifact | None = None
    previous_cache_dir = sc.SURFACE_CODE_CACHE_DIR
    previous_batch_size = sc.SURFACE_CODE_RZ_HELPER_BATCH_SIZE
    previous_env = {
        key: os.environ.get(key)
        for key in (
            "SURFACE_CODE_PROFILE_RSS_SAMPLING",
            "SURFACE_CODE_PROFILE_RSS_SAMPLING_INTERVAL_SEC",
            "SURFACE_CODE_COMPILE_INFO_EXTRACTION_MODE",
            "QRET_DEP_GRAPH_IMPL",
        )
    }
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
        return sc.compile_prepared_surface_code_step_artifact(
            artifact,
            architecture,
            reuse_cache=False,
        )

    try:
        metrics, sample_summary, guard = compact_profile._run_with_tree_sampler(
            run,
            samples_path=samples_path,
            interval_sec=sample_interval_sec,
            memtotal_kb=memtotal_kb,
        )
        sample_rows = qret_profile._load_jsonl(samples_path)
        assert artifact is not None
        compile_root = sc._compile_runtime_root(artifact, architecture)
        prepare_metrics_path = compact_profile._stage_metrics_path(
            artifact.runtime_root,
            sc._PREPARE_STAGE_METRICS_FILENAME,
            sc._PREPARE_STAGE_CACHE_HIT_METRICS_FILENAME,
        )
        compile_metrics_path = compact_profile._stage_metrics_path(
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
        qret_stage = _read_stage(compile_metrics, "qret_compile")
        read_stage = _read_stage(compile_metrics, "read_compile_info_json")
        normalize_stage = _read_stage(compile_metrics, "normalize_compile_info")
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
                "qret_stage": qret_stage,
                "read_compile_info_stage": read_stage,
                "normalize_compile_info_stage": normalize_stage,
                "compile_cache_hit": metrics.get("compile_cache_hit"),
                "compile_info_path": str(compile_info_path),
                "compile_info_size_bytes": compile_info_path.stat().st_size
                if compile_info_path.exists()
                else None,
                "sample_summary": sample_summary,
                "tree_peak_split": _tree_peak_split(sample_rows),
                "guard": guard,
                "qret_peak_rss_kb": _max_present(
                    qret_stage.get("result", {}).get("subprocess_maxrss_kb")
                    if isinstance(qret_stage.get("result"), Mapping)
                    else None,
                    sample_summary.get("sampled_peak_qret_vmrss_kb"),
                ),
                "parent_peak_rss_kb": sample_summary.get("sampled_peak_parent_vmrss_kb"),
                "tree_peak_rss_kb": sample_summary.get("sampled_peak_tree_vmrss_kb"),
                "min_mem_available_kb": sample_summary.get("minimum_mem_available_kb"),
                "max_swap_used_kb": sample_summary.get("maximum_swap_used_kb"),
                "max_swap_free_drop_kb": sample_summary.get("maximum_swap_free_drop_kb"),
                "max_rss_stage": max(
                    rows,
                    key=lambda row: int(
                        row.get("subprocess_maxrss_kb")
                        or row.get("python_sampled_peak_rss_kb")
                        or row.get("python_current_rss_after_kb")
                        or 0
                    ),
                    default={},
                ).get("stage_name"),
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
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    _write_json(case_dir / "summary.json", result_payload)
    if result_payload.get("stage_rows"):
        _write_jsonl(case_dir / "stage_metrics.jsonl", result_payload["stage_rows"])
    if result_payload.get("status") != "ok":
        return result_payload, artifact
    return result_payload, artifact


def _aggregate(rows: Sequence[Mapping[str, Any]], *, case: str, phase: str, mode: str) -> dict[str, Any]:
    selected = [
        row
        for row in rows
        if row.get("case") == case and row.get("phase") == phase and row.get("output_mode") == mode
    ]
    peaks = [row.get("qret_peak_rss_kb") for row in selected]
    elapsed = [row.get("elapsed_seconds") for row in selected]
    sizes = [row.get("compile_info_size_bytes") for row in selected]
    return {
        "runs": len(selected),
        "median_qret_peak_rss_kb": _median(peaks),
        "min_qret_peak_rss_kb": min((int(value) for value in peaks if value is not None), default=None),
        "max_qret_peak_rss_kb": max((int(value) for value in peaks if value is not None), default=None),
        "median_elapsed_seconds": _median(elapsed),
        "median_compile_info_size_bytes": _median(sizes),
        "max_rss_stage": selected[0].get("max_rss_stage") if selected else None,
    }


def _first_result(
    rows: Sequence[Mapping[str, Any]],
    *,
    case: str,
    phase: str,
    mode: str,
) -> Mapping[str, Any]:
    return next(
        (
            row
            for row in rows
            if row.get("case") == case
            and row.get("phase") == phase
            and row.get("output_mode") == mode
        ),
        {},
    )


def _consumer_audit_lines() -> list[str]:
    lines = [
        "## Consumer Audit",
        "",
        "The eight time-series fields have the same consumer pattern in this repository:",
        "",
        "| field | production metric full array use | `_ave` use | `_peak` use | report/visualization | public/API full array use | decision |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for key in TIME_SERIES_KEYS:
        lines.append(
            f"| `{key}` | no | yes, normalized when present | yes, normalized when present | historical reports mention files/stages only | yes, qret/pyqret full JSON schema | omit only in `summary`; keep in `full` |"
        )
    lines.extend(
        [
            "",
            "| consumer | full array | ave | peak | existence/test only | report/visualization | production metric | note |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
            "| `surface_code_step_metrics_from_compile_info_json` -> `_load_compile_info_metrics_json` -> `normalize_surface_code_step_metrics` | no | yes | yes | no | no | yes | summary fields are enough for Evaluation metrics |",
            "| `architecture_sweep._compile_info_row` | no | no | no | no | no | yes | uses scalar runtime, chip cells, qubit volume, physical qubits, code distance |",
            "| compile cache payload/key | no | no | no | no | no | yes | mode is part of the cache key to avoid full/summary artifact reuse |",
            "| benchmark/profiling scripts | no | no | no | stage markers/file sizes only | yes | no | use normalized metrics for correctness comparisons |",
            "| docs and historical reports | no runtime read | no | no | yes | yes | no | textual references only |",
            "| qret C++ `Json()` / `from_json` and pyqret bindings | yes | yes | yes | no | no | public API | qret default remains `full` for compatibility |",
            "| tests | yes | yes | yes | yes | no | no | new tests cover both schemas and invalid mode |",
            "",
            "Conclusion: Evaluation production resource evaluation does not require the full arrays. Public qret/pyqret consumers do, so the implementation keeps full output as the qret default and switches Evaluation production to explicit summary output.",
            "",
        ]
    )
    return lines


def _write_report(
    path: Path,
    *,
    environment: Mapping[str, Any],
    results: Sequence[Mapping[str, Any]],
    semantic_comparisons: Mapping[str, Any],
) -> None:
    lines = [
        "# qret Compile Info Summary Output Optimization",
        "",
        "## Environment",
        "",
        f"- Evaluation HEAD at run start: `{environment.get('evaluation_head')}`",
        f"- dirty status at run start: `{environment.get('dirty_status')}`",
        f"- qret path: `{environment.get('qret_path')}`",
        f"- qret SHA-256: `{environment.get('qret_sha256')}`",
        f"- compiler: `{environment.get('compiler')}`",
        f"- platform: `{environment.get('platform')}`",
        f"- MemTotal KB: `{environment.get('meminfo', {}).get('MemTotal')}`",
        f"- SwapTotal KB: `{environment.get('meminfo', {}).get('SwapTotal')}`",
        f"- compile mode: `{COMPILE_MODE}`",
        f"- topology: `{environment.get('topology_path')}`",
        f"- batch size: `{environment.get('batch_size')}`",
        f"- sampling interval: `{environment.get('sample_interval_sec')}` sec",
        f"- `QRET_DEP_GRAPH_IMPL`: `{environment.get('dep_graph_impl_env')}` (unset means compact)",
        f"- pipeline-state output skip: `{environment.get('skip_compile_output')}`",
        "",
    ]
    lines.extend(_consumer_audit_lines())
    lines.extend(
        [
            "## Design",
            "",
            "- qret option: `sc_ls_fixed_v0_compile_info_output_mode` with values `full` and `summary`.",
            "- qret default: `full`, preserving the existing JSON schema and pyqret/C++ full-array consumers.",
            "- Evaluation default: `SurfaceCodeArchitecture.compile_info_output_mode='summary'` and pipeline YAML emits the option explicitly.",
            "- `summary` omits the eight full time-series arrays and keeps scalar fields plus `_ave` and `_peak` fields.",
            "- The compile cache key includes `compile_info_output_mode` so full and summary outputs cannot collide.",
            "- Evaluation parser accepts both schemas; top-level metric extraction skips omitted arrays and still parses `gate_count_detail`.",
            "",
            "## Isolated qret A/B",
            "",
            "| case | mode | runs | median qret peak KB | min/max qret peak KB | median elapsed s | median compile_info B | max RSS stage |",
            "| --- | --- | ---: | ---: | --- | ---: | ---: | --- |",
        ]
    )
    for case in CASE_CHAIN_LENGTH:
        for mode in OUTPUT_MODES:
            agg = _aggregate(results, case=case, phase="isolated_qret", mode=mode)
            if not agg["runs"]:
                continue
            lines.append(
                "| {case} | `{mode}` | {runs} | {median} | {minp}/{maxp} | {elapsed} | {size} | `{stage}` |".format(
                    case=CASE_DISPLAY[case],
                    mode=mode,
                    runs=agg["runs"],
                    median=_fmt_int(agg["median_qret_peak_rss_kb"]),
                    minp=_fmt_int(agg["min_qret_peak_rss_kb"]),
                    maxp=_fmt_int(agg["max_qret_peak_rss_kb"]),
                    elapsed=_fmt_float(agg["median_elapsed_seconds"], 3),
                    size=_fmt_int(agg["median_compile_info_size_bytes"]),
                    stage=agg["max_rss_stage"] or "",
                )
            )
    lines.extend(
        [
            "",
            "## Isolated Summary Savings",
            "",
            "| case | qret peak full KB | qret peak summary KB | saved KB | saved % | compile_info full B | compile_info summary B | file saved % |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for case in CASE_CHAIN_LENGTH:
        full = _aggregate(results, case=case, phase="isolated_qret", mode="full")
        summary = _aggregate(results, case=case, phase="isolated_qret", mode="summary")
        if not full["runs"] or not summary["runs"]:
            continue
        full_peak = full["median_qret_peak_rss_kb"]
        summary_peak = summary["median_qret_peak_rss_kb"]
        full_size = full["median_compile_info_size_bytes"]
        summary_size = summary["median_compile_info_size_bytes"]
        lines.append(
            "| {case} | {full_peak} | {summary_peak} | {saved} | {saved_pct} | {full_size} | {summary_size} | {file_saved_pct} |".format(
                case=CASE_DISPLAY[case],
                full_peak=_fmt_int(full_peak),
                summary_peak=_fmt_int(summary_peak),
                saved=_fmt_int(None if full_peak is None or summary_peak is None else full_peak - summary_peak),
                saved_pct=_fmt_float(
                    None
                    if full_peak is None or summary_peak is None
                    else 100.0 * (float(full_peak) - float(summary_peak)) / float(full_peak),
                    2,
                ),
                full_size=_fmt_int(full_size),
                summary_size=_fmt_int(summary_size),
                file_saved_pct=_fmt_float(
                    None
                    if full_size is None or summary_size is None
                    else 100.0 * (float(full_size) - float(summary_size)) / float(full_size),
                    2,
                ),
            )
        )
    lines.extend(
        [
            "",
            "## Key qret RSS Markers",
            "",
            "| case | mode | routing KB | compact DepGraph KB | with topology exit KB | JSON DOM KB | full-array final KB | summary final KB | DOM destroyed KB | max marker KB |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for case in CASE_CHAIN_LENGTH:
        for mode in OUTPUT_MODES:
            row = _first_result(results, case=case, phase="isolated_qret", mode=mode)
            if not row:
                continue
            stage_vmrss = row.get("stage_vmrss_kb") if isinstance(row.get("stage_vmrss_kb"), Mapping) else {}
            lines.append(
                "| {case} | `{mode}` | {routing} | {dep} | {topo} | {dom} | {full_final} | {summary_final} | {destroy} | {maxrss} |".format(
                    case=CASE_DISPLAY[case],
                    mode=mode,
                    routing=_fmt_int(stage_vmrss.get("routing_after_main_loop")),
                    dep=_fmt_int(stage_vmrss.get("calc_info_without_topology_after_dep_graph")),
                    topo=_fmt_int(stage_vmrss.get("calc_info_with_topology_exit")),
                    dom=_fmt_int(stage_vmrss.get("dump_compile_info_after_json_dom_create")),
                    full_final=_fmt_int(
                        stage_vmrss.get(
                            "compile_info_json_after_assign_chip_cell_active_qubit_area_ratio"
                        )
                    ),
                    summary_final=_fmt_int(
                        stage_vmrss.get(
                            "compile_info_summary_after_stats_chip_cell_active_qubit_area_ratio"
                        )
                    ),
                    destroy=_fmt_int(stage_vmrss.get("dump_compile_info_after_json_dom_destroy")),
                    maxrss=_fmt_int(row.get("max_rss_stage_vmrss_kb")),
                )
            )
    lines.extend(
        [
            "",
            "## End-to-End Parent Process A/B",
            "",
            "| case | mode | tree peak KB | qret peak KB | parent peak KB | parent at tree peak KB | qret at tree peak KB | read JSON sampled peak KB | read JSON delta KB | compile_info B |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for case in ("h5_4th_new2", "h6_4th_new2"):
        for mode in OUTPUT_MODES:
            row = _first_result(results, case=case, phase="end_to_end", mode=mode)
            if not row:
                continue
            split = row.get("tree_peak_split") if isinstance(row.get("tree_peak_split"), Mapping) else {}
            read_stage = (
                row.get("read_compile_info_stage")
                if isinstance(row.get("read_compile_info_stage"), Mapping)
                else {}
            )
            lines.append(
                "| {case} | `{mode}` | {tree} | {qret} | {parent} | {parent_at} | {qret_at} | {read_peak} | {read_delta} | {size} |".format(
                    case=CASE_DISPLAY[case],
                    mode=mode,
                    tree=_fmt_int(row.get("tree_peak_rss_kb")),
                    qret=_fmt_int(row.get("qret_peak_rss_kb")),
                    parent=_fmt_int(row.get("parent_peak_rss_kb")),
                    parent_at=_fmt_int(split.get("parent_vmrss_kb")),
                    qret_at=_fmt_int(split.get("qret_vmrss_kb")),
                    read_peak=_fmt_int(read_stage.get("python_sampled_peak_rss_kb")),
                    read_delta=_fmt_int(read_stage.get("python_current_rss_delta_kb")),
                    size=_fmt_int(row.get("compile_info_size_bytes")),
                )
            )
    lines.extend(
        [
            "",
            "## End-to-End Summary Savings",
            "",
            "| case | tree full KB | tree summary KB | tree saved KB | tree saved % | parent read full KB | parent read summary KB |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for case in ("h5_4th_new2", "h6_4th_new2"):
        full = _first_result(results, case=case, phase="end_to_end", mode="full")
        summary = _first_result(results, case=case, phase="end_to_end", mode="summary")
        if not full or not summary:
            continue
        full_read = full.get("read_compile_info_stage")
        summary_read = summary.get("read_compile_info_stage")
        full_read_peak = (
            full_read.get("python_sampled_peak_rss_kb") if isinstance(full_read, Mapping) else None
        )
        summary_read_peak = (
            summary_read.get("python_sampled_peak_rss_kb")
            if isinstance(summary_read, Mapping)
            else None
        )
        full_tree = full.get("tree_peak_rss_kb")
        summary_tree = summary.get("tree_peak_rss_kb")
        lines.append(
            "| {case} | {full_tree} | {summary_tree} | {saved} | {saved_pct} | {full_read} | {summary_read} |".format(
                case=CASE_DISPLAY[case],
                full_tree=_fmt_int(full_tree),
                summary_tree=_fmt_int(summary_tree),
                saved=_fmt_int(None if full_tree is None or summary_tree is None else int(full_tree) - int(summary_tree)),
                saved_pct=_fmt_float(
                    None
                    if full_tree is None or summary_tree is None
                    else 100.0 * (float(full_tree) - float(summary_tree)) / float(full_tree),
                    2,
                ),
                full_read=_fmt_int(full_read_peak),
                summary_read=_fmt_int(summary_read_peak),
            )
        )
    lines.extend(
        [
            "",
            "## Semantic A/B",
            "",
        ]
    )
    for case, comparison in semantic_comparisons.items():
        lines.append(
            f"- `{case}` full vs summary normalized compile-info metrics equal: `{comparison.get('all_equal')}`; mismatches: `{comparison.get('mismatches')}`; ignored: `{comparison.get('ignored_fields')}`."
        )
    isolated_rows = [row for row in results if row.get("phase") == "isolated_qret"]
    lines.extend(
        [
            "",
            "## Correctness And Safety",
            "",
            f"- isolated qret compact DepGraph marker on all runs: `{all(row.get('depgraph_implementation_marker') == 'compact' for row in isolated_rows)}`",
            f"- isolated pipeline-state output skipped on all runs: `{all(row.get('pipeline_state_output_skipped') is True for row in isolated_rows)}`",
            f"- all recorded runs succeeded: `{all(row.get('status') == 'ok' for row in results)}`",
            f"- guard triggered: `{any(bool((row.get('guard') or {}).get('triggered')) for row in results if isinstance(row.get('guard'), Mapping))}`",
            f"- maximum swap used KB: `{max((int(row.get('max_swap_used_kb') or 0) for row in results), default=0)}`",
            f"- minimum MemAvailable KB: `{min((row.get('min_mem_available_kb') for row in results if row.get('min_mem_available_kb') is not None), default=None)}`",
            "",
            "## Final Answers",
            "",
            "1. Evaluation production does not need the full compile-info arrays; it now emits summary compile-info by default.",
            "2. qret keeps full output as the default for backward compatibility and public full-array consumers.",
            "3. H4 semantic A/B compares full and summary normalized compile-info metrics; see `Semantic A/B`.",
            "4. H5/H6 isolated qret and end-to-end parent-process A/B are recorded above.",
            "5. The remaining peak, after summary mode, is outside full-array JSON duplication when the max marker is before or at compact/topology stages.",
            "",
            "## Artifacts",
            "",
            f"- output root: `{environment.get('output_root')}`",
            "- `results.jsonl`: one JSON object per run.",
            "- `summary.csv`: compact table for quick spreadsheet checks.",
            "- per-run directories contain `compile.yaml`, qret RSS JSONL, process-tree samples, stdout/stderr, and run summaries.",
            "",
            "## Verification",
            "",
            "Verification commands are listed in the commit/final response after this report is generated.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _prepare_artifacts(
    *,
    cases: Sequence[str],
    cache_root: Path,
    batch_size: int,
) -> dict[str, sc.SurfaceCodeStepArtifact]:
    previous_cache_dir = sc.SURFACE_CODE_CACHE_DIR
    previous_batch_size = sc.SURFACE_CODE_RZ_HELPER_BATCH_SIZE
    sc.SURFACE_CODE_CACHE_DIR = cache_root
    sc.SURFACE_CODE_RZ_HELPER_BATCH_SIZE = int(batch_size)
    try:
        artifacts: dict[str, sc.SurfaceCodeStepArtifact] = {}
        architecture = _architecture("summary")
        for case_key in cases:
            artifacts[case_key] = sc.prepare_grouped_surface_code_step_artifact(
                sc.grouped_hchain_ham_name(CASE_CHAIN_LENGTH[case_key]),
                PF_LABEL,
                architecture=architecture,
            )
        return artifacts
    finally:
        sc.SURFACE_CODE_CACHE_DIR = previous_cache_dir
        sc.SURFACE_CODE_RZ_HELPER_BATCH_SIZE = previous_batch_size


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Profile qret compile-info full vs summary output modes."
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--sample-interval-sec", type=float, default=SAMPLE_INTERVAL_SEC)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--h4-isolated-runs", type=int, default=3)
    parser.add_argument("--h5-isolated-runs", type=int, default=2)
    parser.add_argument("--h6-isolated-runs", type=int, default=2)
    parser.add_argument(
        "--cases",
        nargs="+",
        choices=tuple(CASE_CHAIN_LENGTH),
        default=list(CASE_CHAIN_LENGTH),
    )
    parser.add_argument(
        "--skip-end-to-end",
        action="store_true",
        help="Only run isolated qret A/B.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.batch_size < 1:
        raise ValueError("--batch-size must be >= 1")
    if not (0 < args.sample_interval_sec <= 1):
        raise ValueError("--sample-interval-sec must be in (0, 1]")
    run_root = args.output_root.expanduser().resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(run_root).free < MIN_FREE_DISK_BYTES:
        raise RuntimeError("output filesystem has less than 5 GiB free")
    cache_root = run_root / "cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    meminfo = compact_profile._meminfo()
    architecture = _architecture("summary")
    qret_path = Path(architecture.qret_path).expanduser().resolve()
    compiler = subprocess.check_output(["/usr/bin/c++", "--version"], text=True).splitlines()[0]
    environment = {
        "evaluation_head": _git_output(["rev-parse", "HEAD"]),
        "dirty_status": _git_output(["status", "--short"]),
        "python": sys.version,
        "platform": platform.platform(),
        "compiler": compiler,
        "qret_path": str(qret_path),
        "qret_sha256": sc.file_sha256(qret_path),
        "topology_path": str(Path(architecture.topology_path).expanduser().resolve()),
        "topology_sha256": sc.file_sha256(Path(architecture.topology_path).expanduser().resolve()),
        "compile_mode": COMPILE_MODE,
        "skip_compile_output": bool(architecture.skip_compile_output),
        "dep_graph_impl_env": os.environ.get("QRET_DEP_GRAPH_IMPL"),
        "batch_size": int(args.batch_size),
        "sample_interval_sec": float(args.sample_interval_sec),
        "meminfo": meminfo,
        "output_root": str(run_root),
        "cache_root": str(cache_root),
    }
    _write_json(run_root / "environment.json", environment)

    memtotal_kb = meminfo.get("MemTotal")
    cases = list(args.cases)
    artifacts = _prepare_artifacts(cases=cases, cache_root=cache_root, batch_size=args.batch_size)
    _write_json(
        run_root / "artifacts.json",
        {case: _artifact_summary(artifact) for case, artifact in artifacts.items()},
    )

    results: list[dict[str, Any]] = []
    run_counts = {
        "h4_4th_new2": int(args.h4_isolated_runs),
        "h5_4th_new2": int(args.h5_isolated_runs),
        "h6_4th_new2": int(args.h6_isolated_runs),
    }
    for case_key in cases:
        for mode in OUTPUT_MODES:
            for run_index in range(run_counts[case_key]):
                print(f"isolated {case_key} {mode} run {run_index}", flush=True)
                result = _run_isolated_qret_once(
                    case_key=case_key,
                    output_mode=mode,
                    artifact=artifacts[case_key],
                    run_index=run_index,
                    output_root=run_root,
                    sample_interval_sec=float(args.sample_interval_sec),
                    memtotal_kb=memtotal_kb,
                )
                results.append(result)
                _write_jsonl(run_root / "results.jsonl", results)
                _write_csv(run_root / "summary.csv", results)

    if not args.skip_end_to_end:
        for case_key in [case for case in ("h5_4th_new2", "h6_4th_new2") if case in cases]:
            for mode in OUTPUT_MODES:
                print(f"end-to-end {case_key} {mode}", flush=True)
                result, artifact = _run_end_to_end_case(
                    case_key=case_key,
                    output_mode=mode,
                    output_root=run_root,
                    cache_root=cache_root,
                    batch_size=int(args.batch_size),
                    sample_interval_sec=float(args.sample_interval_sec),
                    memtotal_kb=memtotal_kb,
                )
                results.append(result)
                if artifact is not None:
                    artifacts[case_key] = artifact
                _write_jsonl(run_root / "results.jsonl", results)
                _write_csv(run_root / "summary.csv", results)
                if result.get("status") != "ok":
                    _write_json(run_root / "summary.json", {"results": results})
                    return 1

    semantic_comparisons: dict[str, Any] = {}
    for case_key in cases:
        full_row = _first_result(results, case=case_key, phase="isolated_qret", mode="full")
        summary_row = _first_result(results, case=case_key, phase="isolated_qret", mode="summary")
        if full_row and summary_row:
            semantic_comparisons[case_key] = _compare_metrics(
                full_row.get("normalized_metrics", {}),
                summary_row.get("normalized_metrics", {}),
            )
    _write_json(run_root / "semantic_comparisons.json", semantic_comparisons)
    _write_json(run_root / "summary.json", {"environment": environment, "results": results})
    _write_report(
        args.report_path.expanduser().resolve(),
        environment=environment,
        results=results,
        semantic_comparisons=semantic_comparisons,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
