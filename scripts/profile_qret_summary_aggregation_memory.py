#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import shutil
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


DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "qret_summary_aggregation"
DEFAULT_REPORT_PATH = (
    REPO_ROOT / "docs" / "benchmarks" / "qret_summary_aggregation_optimization.md"
)
PF_LABEL = "4th(new_2)"
COMPILE_MODE = "ftqc_compile_topology"
SAMPLE_INTERVAL_SEC = 0.02
MIN_FREE_DISK_BYTES = 5 * 1024**3
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
VARIANTS = {
    "full": {"output_mode": "full", "summary_impl": None},
    "summary_baseline": {"output_mode": "summary", "summary_impl": "vector"},
    "summary_aggregate": {"output_mode": "summary", "summary_impl": "aggregate"},
}
VARIANT_ORDER = ("full", "summary_baseline", "summary_aggregate")
DEFAULT_ISOLATED_RUNS = {
    "h4_4th_new2": {"full": 2, "summary_baseline": 2, "summary_aggregate": 3},
    "h5_4th_new2": {"full": 1, "summary_baseline": 2, "summary_aggregate": 2},
    "h6_4th_new2": {"full": 1, "summary_baseline": 2, "summary_aggregate": 2},
}
RAW_RESOURCE_FIELDS = (
    "runtime",
    "runtime_without_topology",
    "gate_count",
    "gate_count_detail",
    "gate_depth",
    "gate_throughput_ave",
    "gate_throughput_peak",
    "measurement_feedback_count",
    "measurement_feedback_depth",
    "measurement_feedback_rate_ave",
    "measurement_feedback_rate_peak",
    "magic_state_consumption_count",
    "magic_state_consumption_depth",
    "magic_state_consumption_rate_ave",
    "magic_state_consumption_rate_peak",
    "entanglement_consumption_count",
    "entanglement_consumption_depth",
    "entanglement_consumption_rate_ave",
    "entanglement_consumption_rate_peak",
    "magic_factory_count",
    "entanglement_factory_count",
    "chip_cell_count",
    "chip_cell_algorithmic_qubit_ave",
    "chip_cell_algorithmic_qubit_peak",
    "chip_cell_algorithmic_qubit_ratio_ave",
    "chip_cell_algorithmic_qubit_ratio_peak",
    "chip_cell_active_qubit_area_ave",
    "chip_cell_active_qubit_area_peak",
    "chip_cell_active_qubit_area_ratio_ave",
    "chip_cell_active_qubit_area_ratio_peak",
    "qubit_volume",
    "code_distance",
    "execution_time_sec",
    "num_physical_qubits",
)


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
        "variant",
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


def _runtime_hashes(qret_path: Path) -> dict[str, Any]:
    return sc.qret_runtime_hashes(qret_path)


def _hashes_equal(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    keys = (
        "qret_executable_hash",
        "qret_core_library_path",
        "qret_core_library_hash",
    )
    return all(left.get(key) == right.get(key) for key in keys)


def _ensure_runtime_hash_stable(before: Mapping[str, Any], after: Mapping[str, Any]) -> None:
    if not _hashes_equal(before, after):
        raise RuntimeError(
            "qret runtime hash changed during measurement: "
            f"before={dict(before)}, after={dict(after)}"
        )


def _build_qret_and_record(qret_path: Path, *, build: bool) -> dict[str, Any]:
    before = _runtime_hashes(qret_path) if qret_path.exists() else None
    payload: dict[str, Any] = {
        "build_requested": bool(build),
        "build_before_head": _git_output(["rev-parse", "HEAD"]),
        "build_before_runtime_hashes": before,
        "build_returncode": None,
        "build_stdout_tail": "",
        "build_stderr_tail": "",
    }
    if build:
        completed = subprocess.run(
            [str(REPO_ROOT / "scripts" / "build_qret.sh")],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        payload.update(
            {
                "build_returncode": int(completed.returncode),
                "build_stdout_tail": completed.stdout[-4000:],
                "build_stderr_tail": completed.stderr[-4000:],
            }
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "scripts/build_qret.sh failed:\n"
                + (completed.stdout or "")
                + "\n"
                + (completed.stderr or "")
            )
    after = _runtime_hashes(qret_path)
    payload.update(
        {
            "build_after_head": _git_output(["rev-parse", "HEAD"]),
            "build_after_runtime_hashes": after,
            "executable_hash_changed_by_build": (
                before is not None
                and before.get("qret_executable_hash") != after.get("qret_executable_hash")
            ),
            "core_library_hash_changed_by_build": (
                before is not None
                and before.get("qret_core_library_hash") != after.get("qret_core_library_hash")
            ),
        }
    )
    return payload


def _architecture(variant: str) -> sc.SurfaceCodeArchitecture:
    return sc.SurfaceCodeArchitecture(
        compile_mode=COMPILE_MODE,
        skip_compile_output=True,
        compile_info_output_mode=str(VARIANTS[variant]["output_mode"]),
    )


def _variant_env(env: dict[str, str], variant: str) -> None:
    impl = VARIANTS[variant]["summary_impl"]
    if impl is None:
        env.pop("QRET_SUMMARY_TIME_SERIES_IMPL", None)
    else:
        env["QRET_SUMMARY_TIME_SERIES_IMPL"] = str(impl)
    env.pop("QRET_DEP_GRAPH_IMPL", None)


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


def _raw_resource_metrics(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    return {field: raw.get(field) for field in RAW_RESOURCE_FIELDS if field in raw}


def _compare_dicts(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    ignored: set[str] | None = None,
) -> dict[str, Any]:
    ignored = set(ignored or set())
    keys = sorted((set(baseline) | set(candidate)) - ignored)
    mismatches = [key for key in keys if baseline.get(key, object()) != candidate.get(key, object())]
    return {
        "all_equal": not mismatches,
        "mismatches": mismatches,
        "field_count": len(keys),
        "ignored_fields": sorted(ignored),
    }


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
    qret_rows = [
        row for row in peak_rows if compact_profile._is_qret_command(row.get("command"))
    ]
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
    }


def _read_stage(compile_metrics: Mapping[str, Any], stage_name: str) -> dict[str, Any]:
    for stage in compile_metrics.get("stages", []):
        if isinstance(stage, Mapping) and stage.get("name") == stage_name:
            return dict(stage)
    return {}


def _run_isolated_qret_once(
    *,
    case_key: str,
    variant: str,
    artifact: sc.SurfaceCodeStepArtifact,
    run_index: int,
    output_root: Path,
    sample_interval_sec: float,
    memtotal_kb: int | None,
    expected_runtime_hashes: Mapping[str, Any],
) -> dict[str, Any]:
    architecture = _architecture(variant)
    run_dir = output_root / "isolated_qret" / case_key / variant / f"run_{run_index:02d}"
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
    qret_path = Path(architecture.qret_path).expanduser().resolve()
    before_hashes = _runtime_hashes(qret_path)
    _ensure_runtime_hash_stable(expected_runtime_hashes, before_hashes)
    env = os.environ.copy()
    env["QRET_RSS_PROFILE_JSONL"] = str(profile_jsonl)
    _variant_env(env, variant)
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    env.pop("LANGUAGE", None)
    cmd = [
        "/usr/bin/time",
        "-v",
        str(qret_path),
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
    after_hashes = _runtime_hashes(qret_path)
    _ensure_runtime_hash_stable(before_hashes, after_hashes)
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    _write_jsonl(samples_jsonl, rows)

    profile_rows = qret_profile._load_jsonl(profile_jsonl)
    sample_summary = compact_profile._summarize_samples(rows, parent_pid=process.pid)
    gnu_maxrss = qret_profile._parse_gnu_time_maxrss(stderr)
    dep_extra = _dep_graph_extra(profile_rows)
    max_stage = _profile_max_stage(profile_rows)
    result = {
        "case": case_key,
        "phase": "isolated_qret",
        "variant": variant,
        "output_mode": VARIANTS[variant]["output_mode"],
        "summary_impl": VARIANTS[variant]["summary_impl"],
        "run_index": run_index,
        "status": "ok" if process.returncode == 0 else "failed",
        "returncode": int(process.returncode),
        "elapsed_seconds": elapsed,
        "runtime_hashes_before": before_hashes,
        "runtime_hashes_after": after_hashes,
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
        "normalized_metrics": _metric_summary(compile_info_path),
        "raw_resource_metrics": _raw_resource_metrics(compile_info_path),
        "artifact": compact_profile._artifact_summary(artifact),
    }
    _write_json(run_dir / "summary.json", result)
    if process.returncode != 0:
        raise RuntimeError(f"isolated qret failed for {case_key} {variant}: {stderr[-4000:]}")
    return result


def _run_end_to_end_case(
    *,
    case_key: str,
    variant: str,
    output_root: Path,
    cache_root: Path,
    batch_size: int,
    sample_interval_sec: float,
    memtotal_kb: int | None,
    expected_runtime_hashes: Mapping[str, Any],
) -> tuple[dict[str, Any], sc.SurfaceCodeStepArtifact | None]:
    architecture = _architecture(variant)
    qret_path = Path(architecture.qret_path).expanduser().resolve()
    before_hashes = _runtime_hashes(qret_path)
    _ensure_runtime_hash_stable(expected_runtime_hashes, before_hashes)
    case_dir = output_root / "end_to_end" / case_key / variant
    case_dir.mkdir(parents=True, exist_ok=True)
    samples_path = case_dir / "process_tree_samples.jsonl"
    started = time.perf_counter()
    result_payload: dict[str, Any] = {
        "case": case_key,
        "phase": "end_to_end",
        "variant": variant,
        "output_mode": VARIANTS[variant]["output_mode"],
        "summary_impl": VARIANTS[variant]["summary_impl"],
        "run_index": 0,
        "status": "unknown",
        "runtime_hashes_before": before_hashes,
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
            "QRET_SUMMARY_TIME_SERIES_IMPL",
        )
    }
    sc.SURFACE_CODE_CACHE_DIR = cache_root
    sc.SURFACE_CODE_RZ_HELPER_BATCH_SIZE = int(batch_size)
    os.environ["SURFACE_CODE_PROFILE_RSS_SAMPLING"] = "1"
    os.environ["SURFACE_CODE_PROFILE_RSS_SAMPLING_INTERVAL_SEC"] = str(sample_interval_sec)
    os.environ["SURFACE_CODE_COMPILE_INFO_EXTRACTION_MODE"] = "full_json_load"
    _variant_env(os.environ, variant)

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
        after_hashes = _runtime_hashes(qret_path)
        _ensure_runtime_hash_stable(before_hashes, after_hashes)
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
        compile_info_path = Path(str(metrics.get("compile_info_json", "")))
        result_payload.update(
            {
                "status": "ok",
                "returncode": 0,
                "elapsed_seconds": time.perf_counter() - started,
                "runtime_hashes_after": after_hashes,
                "metrics": metrics,
                "normalized_metrics": metrics,
                "raw_resource_metrics": _raw_resource_metrics(compile_info_path),
                "artifact": compact_profile._artifact_summary(artifact),
                "compile_root": str(compile_root),
                "prepare_metrics_path": str(prepare_metrics_path),
                "compile_metrics_path": str(compile_metrics_path),
                "stage_rows": rows,
                "qret_stage": qret_stage,
                "read_compile_info_stage": read_stage,
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
                "max_rss_stage": "qret_compile",
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
    return result_payload, artifact


def _median(values: Sequence[float | int | None]) -> float | int | None:
    present = [value for value in values if value is not None]
    return sorted(present)[len(present) // 2] if present and len(present) % 2 == 1 else (
        (sorted(present)[len(present) // 2 - 1] + sorted(present)[len(present) // 2]) / 2
        if present
        else None
    )


def _fmt_int(value: Any) -> str:
    if value is None:
        return ""
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return str(value)


def _fmt_float(value: float | int | None, digits: int = 3) -> str:
    if value is None:
        return ""
    return f"{float(value):.{digits}f}"


def _aggregate(rows: Sequence[Mapping[str, Any]], *, case: str, phase: str, variant: str) -> dict[str, Any]:
    selected = [
        row
        for row in rows
        if row.get("case") == case and row.get("phase") == phase and row.get("variant") == variant
    ]
    peaks = [row.get("qret_peak_rss_kb") for row in selected]
    elapsed = [row.get("elapsed_seconds") for row in selected]
    sizes = [row.get("compile_info_size_bytes") for row in selected]
    return {
        "runs": len(selected),
        "median_qret_peak_rss_kb": _median(peaks),
        "median_elapsed_seconds": _median(elapsed),
        "median_compile_info_size_bytes": _median(sizes),
        "max_rss_stage": selected[0].get("max_rss_stage") if selected else None,
    }


def _first_result(
    rows: Sequence[Mapping[str, Any]],
    *,
    case: str,
    phase: str,
    variant: str,
) -> Mapping[str, Any]:
    return next(
        (
            row
            for row in rows
            if row.get("case") == case
            and row.get("phase") == phase
            and row.get("variant") == variant
        ),
        {},
    )


def _write_report(
    path: Path,
    *,
    environment: Mapping[str, Any],
    build_provenance: Mapping[str, Any],
    results: Sequence[Mapping[str, Any]],
    comparisons: Mapping[str, Any],
) -> None:
    lines = [
        "# qret Summary Aggregation Optimization",
        "",
        "## Environment",
        "",
        f"- Evaluation HEAD at run start: `{environment.get('evaluation_head')}`",
        f"- qret executable hash used: `{environment.get('measurement_runtime_hashes', {}).get('qret_executable_hash')}`",
        f"- qret core library hash used: `{environment.get('measurement_runtime_hashes', {}).get('qret_core_library_hash')}`",
        f"- qret core library path: `{environment.get('measurement_runtime_hashes', {}).get('qret_core_library_path')}`",
        f"- compiler: `{environment.get('compiler')}`",
        f"- platform: `{environment.get('platform')}`",
        f"- MemTotal KB: `{environment.get('meminfo', {}).get('MemTotal')}`",
        f"- SwapTotal KB: `{environment.get('meminfo', {}).get('SwapTotal')}`",
        f"- compile mode: `{COMPILE_MODE}`",
        f"- batch size: `{environment.get('batch_size')}`",
        f"- sampling interval: `{environment.get('sample_interval_sec')}` sec",
        "",
        "## qret Hash Provenance",
        "",
        f"- build before executable hash: `{(build_provenance.get('build_before_runtime_hashes') or {}).get('qret_executable_hash')}`",
        f"- build before core hash: `{(build_provenance.get('build_before_runtime_hashes') or {}).get('qret_core_library_hash')}`",
        f"- build after executable hash: `{(build_provenance.get('build_after_runtime_hashes') or {}).get('qret_executable_hash')}`",
        f"- build after core hash: `{(build_provenance.get('build_after_runtime_hashes') or {}).get('qret_core_library_hash')}`",
        f"- executable hash changed by build: `{build_provenance.get('executable_hash_changed_by_build')}`",
        f"- core library hash changed by build: `{build_provenance.get('core_library_hash_changed_by_build')}`",
        "",
        "The qret executable is a small dynamically linked launcher. Most SC_LS_FIXED_V0 C++ changes live in `libqret-core.so`, so executable SHA-256 alone can stay unchanged after qret C++ changes. This run records both hashes and treats either changing during measurement as a failure.",
        "",
        "## Time-Series Formula Audit",
        "",
        "| field | element type | source | average | peak | sum use | derived metric |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        "| `gate_throughput` | `uint64_t` | `time_series.GetInstructions(beat).size()` | `uint64_t` sum in beat order / runtime | max | no separate derived sum | throughput stats |",
        "| `measurement_feedback_rate` | `uint64_t` | first use of measurement-created c-symbol, counted at `creation beat + StartCorrecting()` | counted-event sum / runtime | max sparse beat count | sum is counted feedback events | feedback stats |",
        "| `magic_state_consumption_rate` | `uint64_t` | per-beat `UseMagicState()` count | `uint64_t` sum in beat order / runtime | max | no separate derived sum | magic consumption stats |",
        "| `entanglement_consumption_rate` | `uint64_t` | per-beat `CountEntanglement()` | `uint64_t` sum in beat order / runtime | max | no separate derived sum | entanglement stats |",
        "| `chip_cell_algorithmic_qubit` | `uint64_t` | `TimeSeries::ChipInfo::ChipCellAlgorithmicQubit()` | `uint64_t` sum in beat order / runtime | max | no | cell stats |",
        "| `chip_cell_algorithmic_qubit_ratio` | `double` | algorithmic qubits / chip cells | `double` sum in beat order / runtime | max | no | ratio stats |",
        "| `chip_cell_active_qubit_area` | `uint64_t` | used ancilla + algorithmic qubits | `uint64_t` sum in beat order / runtime | max | yes | `qubit_volume` |",
        "| `chip_cell_active_qubit_area_ratio` | `double` | active area / chip cells | `double` sum in beat order / runtime | max | no | ratio stats |",
        "",
        "## Isolated qret A/B",
        "",
        "| case | variant | runs | median qret peak KB | median elapsed s | median compile_info B | max RSS stage |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for case in CASE_CHAIN_LENGTH:
        for variant in VARIANT_ORDER:
            agg = _aggregate(results, case=case, phase="isolated_qret", variant=variant)
            if not agg["runs"]:
                continue
            lines.append(
                "| {case} | `{variant}` | {runs} | {peak} | {elapsed} | {size} | `{stage}` |".format(
                    case=CASE_DISPLAY[case],
                    variant=variant,
                    runs=agg["runs"],
                    peak=_fmt_int(agg["median_qret_peak_rss_kb"]),
                    elapsed=_fmt_float(agg["median_elapsed_seconds"], 3),
                    size=_fmt_int(agg["median_compile_info_size_bytes"]),
                    stage=agg["max_rss_stage"] or "",
                )
            )
    lines.extend(
        [
            "",
            "## Summary Aggregate Savings",
            "",
            "| case | baseline peak KB | aggregate peak KB | saved KB | saved % |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for case in CASE_CHAIN_LENGTH:
        baseline = _aggregate(results, case=case, phase="isolated_qret", variant="summary_baseline")
        aggregate = _aggregate(results, case=case, phase="isolated_qret", variant="summary_aggregate")
        if not baseline["runs"] or not aggregate["runs"]:
            continue
        base_peak = baseline["median_qret_peak_rss_kb"]
        agg_peak = aggregate["median_qret_peak_rss_kb"]
        lines.append(
            "| {case} | {base} | {agg} | {saved} | {pct} |".format(
                case=CASE_DISPLAY[case],
                base=_fmt_int(base_peak),
                agg=_fmt_int(agg_peak),
                saved=_fmt_int(None if base_peak is None or agg_peak is None else base_peak - agg_peak),
                pct=_fmt_float(
                    None
                    if base_peak is None or agg_peak is None
                    else 100.0 * (float(base_peak) - float(agg_peak)) / float(base_peak),
                    2,
                ),
            )
        )
    lines.extend(
        [
            "",
            "## End-to-End A/B",
            "",
            "| case | variant | tree peak KB | qret peak KB | parent peak KB | parent at tree peak KB | qret at tree peak KB | read JSON sampled peak KB | compile_info B |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for case in ("h5_4th_new2", "h6_4th_new2"):
        for variant in ("summary_baseline", "summary_aggregate"):
            row = _first_result(results, case=case, phase="end_to_end", variant=variant)
            if not row:
                continue
            split = row.get("tree_peak_split") if isinstance(row.get("tree_peak_split"), Mapping) else {}
            read_stage = (
                row.get("read_compile_info_stage")
                if isinstance(row.get("read_compile_info_stage"), Mapping)
                else {}
            )
            lines.append(
                "| {case} | `{variant}` | {tree} | {qret} | {parent} | {parent_at} | {qret_at} | {read_peak} | {size} |".format(
                    case=CASE_DISPLAY[case],
                    variant=variant,
                    tree=_fmt_int(row.get("tree_peak_rss_kb")),
                    qret=_fmt_int(row.get("qret_peak_rss_kb")),
                    parent=_fmt_int(row.get("parent_peak_rss_kb")),
                    parent_at=_fmt_int(split.get("parent_vmrss_kb")),
                    qret_at=_fmt_int(split.get("qret_vmrss_kb")),
                    read_peak=_fmt_int(read_stage.get("python_sampled_peak_rss_kb")),
                    size=_fmt_int(row.get("compile_info_size_bytes")),
                )
            )
    lines.extend(["", "## Semantic Comparisons", ""])
    for key, comparison in comparisons.items():
        lines.append(
            f"- `{key}`: normalized equal `{comparison.get('normalized', {}).get('all_equal')}`, raw resource equal `{comparison.get('raw', {}).get('all_equal')}`, raw mismatches `{comparison.get('raw', {}).get('mismatches')}`."
        )
    isolated = [row for row in results if row.get("phase") == "isolated_qret"]
    lines.extend(
        [
            "",
            "## Correctness And Safety",
            "",
            f"- compact DepGraph marker on isolated runs: `{all(row.get('depgraph_implementation_marker') == 'compact' for row in isolated)}`",
            f"- pipeline-state output skipped on isolated runs: `{all(row.get('pipeline_state_output_skipped') is True for row in isolated)}`",
            f"- all runs succeeded: `{all(row.get('status') == 'ok' for row in results)}`",
            f"- guard triggered: `{any(bool((row.get('guard') or {}).get('triggered')) for row in results if isinstance(row.get('guard'), Mapping))}`",
            f"- maximum swap used KB: `{max((int(row.get('max_swap_used_kb') or 0) for row in results), default=0)}`",
            f"- minimum MemAvailable KB: `{min((row.get('min_mem_available_kb') for row in results if row.get('min_mem_available_kb') is not None), default=None)}`",
            "",
            "## Execution Time Naming",
            "",
            "`compile_info.json` field `execution_time_sec` is qret's physical execution-time estimate from QEC resource estimation. Evaluation-generated step metrics now preserve it as `estimated_execution_time_sec` and store wall-clock compile elapsed as `compile_wall_time_sec`. The legacy generated-step alias `execution_time_sec` remains wall-clock elapsed for existing consumers.",
            "",
            "## Artifacts",
            "",
            f"- output root: `{environment.get('output_root')}`",
            "- `results.jsonl`: one JSON object per run.",
            "- `summary.csv`: compact spreadsheet table.",
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
        architecture = _architecture("summary_aggregate")
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
    parser = argparse.ArgumentParser(description="Profile summary aggregate compile-info memory.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--sample-interval-sec", type=float, default=SAMPLE_INTERVAL_SEC)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument(
        "--cases",
        nargs="+",
        choices=tuple(CASE_CHAIN_LENGTH),
        default=list(CASE_CHAIN_LENGTH),
    )
    parser.add_argument("--skip-end-to-end", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_root = args.output_root.expanduser().resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(run_root).free < MIN_FREE_DISK_BYTES:
        raise RuntimeError("output filesystem has less than 5 GiB free")
    cache_root = run_root / "cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    architecture = _architecture("summary_aggregate")
    qret_path = Path(architecture.qret_path).expanduser().resolve()
    build_provenance = _build_qret_and_record(qret_path, build=not args.skip_build)
    measurement_hashes = _runtime_hashes(qret_path)
    _ensure_runtime_hash_stable(build_provenance["build_after_runtime_hashes"], measurement_hashes)
    meminfo = compact_profile._meminfo()
    compiler = subprocess.check_output(["/usr/bin/c++", "--version"], text=True).splitlines()[0]
    environment = {
        "evaluation_head": _git_output(["rev-parse", "HEAD"]),
        "dirty_status": _git_output(["status", "--short"]),
        "python": sys.version,
        "platform": platform.platform(),
        "compiler": compiler,
        "measurement_runtime_hashes": measurement_hashes,
        "topology_path": str(Path(architecture.topology_path).expanduser().resolve()),
        "topology_sha256": sc.file_sha256(Path(architecture.topology_path).expanduser().resolve()),
        "batch_size": int(args.batch_size),
        "sample_interval_sec": float(args.sample_interval_sec),
        "meminfo": meminfo,
        "output_root": str(run_root),
        "cache_root": str(cache_root),
    }
    _write_json(run_root / "environment.json", environment)
    _write_json(run_root / "qret_hash_provenance.json", build_provenance)

    cases = list(args.cases)
    artifacts = _prepare_artifacts(cases=cases, cache_root=cache_root, batch_size=args.batch_size)
    _write_json(
        run_root / "artifacts.json",
        {case: compact_profile._artifact_summary(artifact) for case, artifact in artifacts.items()},
    )
    memtotal_kb = meminfo.get("MemTotal")
    results: list[dict[str, Any]] = []
    for case_key in cases:
        for variant in VARIANT_ORDER:
            for run_index in range(DEFAULT_ISOLATED_RUNS[case_key][variant]):
                print(f"isolated {case_key} {variant} run {run_index}", flush=True)
                result = _run_isolated_qret_once(
                    case_key=case_key,
                    variant=variant,
                    artifact=artifacts[case_key],
                    run_index=run_index,
                    output_root=run_root,
                    sample_interval_sec=float(args.sample_interval_sec),
                    memtotal_kb=memtotal_kb,
                    expected_runtime_hashes=measurement_hashes,
                )
                results.append(result)
                _write_jsonl(run_root / "results.jsonl", results)
                _write_csv(run_root / "summary.csv", results)

    if not args.skip_end_to_end:
        for case_key in [case for case in ("h5_4th_new2", "h6_4th_new2") if case in cases]:
            for variant in ("summary_baseline", "summary_aggregate"):
                print(f"end-to-end {case_key} {variant}", flush=True)
                result, artifact = _run_end_to_end_case(
                    case_key=case_key,
                    variant=variant,
                    output_root=run_root,
                    cache_root=cache_root,
                    batch_size=int(args.batch_size),
                    sample_interval_sec=float(args.sample_interval_sec),
                    memtotal_kb=memtotal_kb,
                    expected_runtime_hashes=measurement_hashes,
                )
                results.append(result)
                if artifact is not None:
                    artifacts[case_key] = artifact
                _write_jsonl(run_root / "results.jsonl", results)
                _write_csv(run_root / "summary.csv", results)
                if result.get("status") != "ok":
                    _write_json(run_root / "summary.json", {"results": results})
                    return 1

    comparisons: dict[str, Any] = {}
    for case_key in cases:
        full = _first_result(results, case=case_key, phase="isolated_qret", variant="full")
        for variant in ("summary_baseline", "summary_aggregate"):
            other = _first_result(results, case=case_key, phase="isolated_qret", variant=variant)
            if full and other:
                comparisons[f"{case_key}:{variant}"] = {
                    "normalized": _compare_dicts(
                        full.get("normalized_metrics", {}),
                        other.get("normalized_metrics", {}),
                        ignored={"compile_info_json"},
                    ),
                    "raw": _compare_dicts(
                        full.get("raw_resource_metrics", {}),
                        other.get("raw_resource_metrics", {}),
                    ),
                }
    _write_json(run_root / "semantic_comparisons.json", comparisons)
    _write_json(run_root / "summary.json", {"environment": environment, "results": results})
    _write_report(
        args.report_path.expanduser().resolve(),
        environment=environment,
        build_provenance=build_provenance,
        results=results,
        comparisons=comparisons,
    )
    final_hashes = _runtime_hashes(qret_path)
    _ensure_runtime_hash_stable(measurement_hashes, final_hashes)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
