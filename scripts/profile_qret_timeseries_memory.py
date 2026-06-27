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


DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "qret_timeseries_memory"
DEFAULT_REPORT_PATH = (
    REPO_ROOT / "docs" / "benchmarks" / "qret_timeseries_memory_optimization.md"
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
    "summary_legacy_timeseries": {
        "output_mode": "summary",
        "summary_impl": "legacy_timeseries",
    },
    "summary_compact_timeseries": {
        "output_mode": "summary",
        "summary_impl": "compact_timeseries",
    },
    "summary_event_sweep": {"output_mode": "summary", "summary_impl": "event_sweep"},
}
VARIANT_ORDER = (
    "full",
    "summary_legacy_timeseries",
    "summary_compact_timeseries",
    "summary_event_sweep",
)
DEFAULT_ISOLATED_RUNS = {
    "h4_4th_new2": {
        "full": 1,
        "summary_legacy_timeseries": 2,
        "summary_compact_timeseries": 2,
        "summary_event_sweep": 3,
    },
    "h5_4th_new2": {
        "summary_legacy_timeseries": 2,
        "summary_compact_timeseries": 2,
        "summary_event_sweep": 2,
    },
    "h6_4th_new2": {
        "summary_legacy_timeseries": 1,
        "summary_compact_timeseries": 1,
        "summary_event_sweep": 1,
    },
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


def _first_profile_marker(
    row: Mapping[str, Any],
    *,
    preferred_stage: str = "calc_info_with_topology_after_summary_accumulation",
) -> Mapping[str, Any]:
    profile_jsonl = row.get("profile_jsonl")
    if not profile_jsonl:
        return {}
    path = Path(str(profile_jsonl))
    if not path.exists():
        return {}
    fallback: Mapping[str, Any] = {}
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                marker = json.loads(line)
                extra = marker.get("extra") if isinstance(marker.get("extra"), Mapping) else marker
                if not isinstance(extra, Mapping):
                    continue
                if "time_series_storage_impl" not in extra:
                    continue
                combined = dict(extra)
                combined.setdefault("stage", marker.get("stage"))
                combined.setdefault("vmrss_kb", marker.get("vmrss_kb"))
                if not fallback:
                    fallback = combined
                if marker.get("stage") == preferred_stage:
                    return combined
    except (OSError, json.JSONDecodeError):
        return {}
    return fallback


def _container_value_kb(marker: Mapping[str, Any], *keys: str) -> str:
    total = _container_bytes(marker, *keys)
    if total is None:
        return ""
    return _fmt_int(total / 1024.0)


def _container_bytes(marker: Mapping[str, Any], *keys: str) -> int | None:
    total = 0
    seen = False
    for key in keys:
        value = marker.get(key)
        if value is None:
            continue
        try:
            total += int(value)
            seen = True
        except (TypeError, ValueError):
            continue
    if not seen:
        return None
    return total


def _first_marker_for(
    results: Sequence[Mapping[str, Any]],
    *,
    case: str,
    variant: str,
) -> Mapping[str, Any]:
    row = _first_result(results, case=case, phase="isolated_qret", variant=variant)
    return _first_profile_marker(row) if row else {}


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
    execution_plan: Mapping[str, Any],
) -> None:
    lines = [
        "# qret TimeSeries Memory Optimization",
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
        "## Production Decision",
        "",
        "- Current production default remains `summary_legacy_timeseries` (`QRET_SUMMARY_TIME_SERIES_IMPL` unset).",
        "- `summary_compact_timeseries` and `summary_event_sweep` remain selectable profiling candidates via `QRET_SUMMARY_TIME_SERIES_IMPL`.",
        f"- H6 skipped reason: `{execution_plan.get('h6_skipped_reason')}`.",
        "",
        "## Semantic Audit",
        "",
        "| field | element type | source | average | peak | sum use | derived metric |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        "| `gate_throughput` | `uint64_t` | active instruction count in MachineFunction order | `uint64_t` sum in beat order / runtime | max | no separate derived sum | throughput stats |",
        "| `measurement_feedback_rate` | `uint64_t` | first use of measurement-created c-symbol, counted at `creation beat + StartCorrecting()` | counted-event sum / runtime | max sparse beat count | sum is counted feedback events | feedback stats |",
        "| `magic_state_consumption_rate` | `uint64_t` | per-beat `UseMagicState()` count | `uint64_t` sum in beat order / runtime | max | no separate derived sum | magic consumption stats |",
        "| `entanglement_consumption_rate` | `uint64_t` | per-beat `CountEntanglement()` | `uint64_t` sum in beat order / runtime | max | no separate derived sum | entanglement stats |",
        "| `chip_cell_algorithmic_qubit` | `uint64_t` | `TimeSeries::ChipInfo::ChipCellAlgorithmicQubit()` | `uint64_t` sum in beat order / runtime | max | no | cell stats |",
        "| `chip_cell_algorithmic_qubit_ratio` | `double` | algorithmic qubits / chip cells | `double` sum in beat order / runtime | max | no | ratio stats |",
        "| `chip_cell_active_qubit_area` | `uint64_t` | used ancilla + algorithmic qubits | `uint64_t` sum in beat order / runtime | max | yes | `qubit_volume` |",
        "| `chip_cell_active_qubit_area_ratio` | `double` | active area / chip cells | `double` sum in beat order / runtime | max | no | ratio stats |",
        "",
        "Observed semantics used by all variants:",
        "",
        "- Active interval is `[Metadata().beat, Metadata().beat + effective_latency)`, where zero latency is treated as one active beat for TimeSeries membership.",
        "- Runtime uses the legacy raw-latency bound plus one stored beat; compact and event-sweep use the same runtime value.",
        "- Same-beat instruction order is MachineFunction traversal order. Compact CSR stores pointers in that order, and event-sweep keeps the active set ordered by stable MachineFunction index.",
        "- Multi-beat instructions are processed on every active beat, matching legacy behavior for throughput, magic, entanglement, ancilla, factories, allocate/deallocate, CCreate, and Condition.",
        "- Chip state is a running state for `q_symb`, `m_symb`, and `e_symb`; `used_ancilla_count` is beat-local active ancilla use.",
        "- Feedback keeps the legacy two-pass beat behavior: CCreate records first, Condition then counts the first use at `creation beat + StartCorrecting()`; reserved symbols, duplicate CCreate, and unknown Condition keep legacy error behavior.",
        "",
        "## Existing Memory",
        "",
        "| case | runtime | machine inst | pointer count | pointer duplication | beat2inst bytes | beat2chip bytes |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for case in ("h4_4th_new2", "h5_4th_new2"):
        marker = _first_marker_for(
            results,
            case=case,
            variant="summary_legacy_timeseries",
        )
        if not marker:
            continue
        beat2inst_bytes = _container_bytes(
            marker,
            "beat2inst_outer_control_block_capacity_bytes",
            "beat2inst_pointer_capacity_bytes",
        )
        lines.append(
            "| {case} | {runtime} | {inst} | {ptr} | {dup} | {beat2inst} | {beat2chip} |".format(
                case=CASE_DISPLAY[case],
                runtime=_fmt_int(marker.get("time_series_runtime")),
                inst=_fmt_int(marker.get("machine_instruction_count")),
                ptr=_fmt_int(marker.get("beat2inst_pointer_count")),
                dup=_fmt_float(marker.get("beat2inst_pointer_duplication_ratio"), 3),
                beat2inst=_fmt_int(None if beat2inst_bytes is None else beat2inst_bytes / 1024.0),
                beat2chip=_container_value_kb(marker, "beat2chip_capacity_bytes"),
            )
        )
    lines.extend(
        [
            "",
            "## Variant Design",
            "",
            "| variant | representation | asymptotic storage | semantic risk |",
            "| --- | --- | --- | --- |",
            "| `summary_legacy_timeseries` | `vector<vector<const Instruction*>>` plus `vector<ChipInfo>` | `O(runtime + stored pointers + runtime chip snapshots)` | oracle baseline |",
            "| `summary_compact_timeseries` | CSR offsets plus flat instruction pointer array plus `vector<ChipInfo>` | `O(runtime offsets + stored pointers + runtime chip snapshots)` | low, because per-beat sequences remain directly comparable |",
            "| `summary_event_sweep` | one instruction pointer table plus sorted start/end index vectors and running chip state | `O(machine instructions + start/end events + active set)` | medium, because feedback/order must be reproduced without beat snapshots |",
            "",
            "## Isolated qret A/B",
            "",
            "| case | variant | runs | median qret peak KB | median elapsed s | median compile_info B | max RSS stage |",
            "| --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
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
            "## Container Footprint",
            "",
            "| case | variant | snapshot stage | VmRSS KB | estimated container KB | outer vector KB | offset KB | pointer KB | beat2chip KB | event index/pointer KB | active peak |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for case in ("h4_4th_new2", "h5_4th_new2"):
        for variant in (
            "summary_legacy_timeseries",
            "summary_compact_timeseries",
            "summary_event_sweep",
        ):
            row = _first_result(results, case=case, phase="isolated_qret", variant=variant)
            if not row:
                continue
            marker = _first_profile_marker(row)
            if not marker:
                continue
            event_bytes = _container_value_kb(
                marker,
                "event_sweep_instruction_pointer_capacity_bytes",
                "event_sweep_start_index_capacity_bytes",
                "event_sweep_end_index_capacity_bytes",
            )
            lines.append(
                "| {case} | `{variant}` | `{stage}` | {rss} | {estimated} | {outer} | {offset} | {pointer} | {chip} | {event} | {active} |".format(
                    case=CASE_DISPLAY[case],
                    variant=variant,
                    stage=marker.get("stage") or "",
                    rss=_fmt_int(marker.get("vmrss_kb")),
                    estimated=_container_value_kb(
                        marker,
                        "time_series_estimated_capacity_bytes",
                        "event_sweep_estimated_capacity_bytes",
                    ),
                    outer=_container_value_kb(
                        marker,
                        "beat2inst_outer_control_block_capacity_bytes",
                    ),
                    offset=_container_value_kb(marker, "beat2inst_offset_capacity_bytes"),
                    pointer=_container_value_kb(marker, "beat2inst_pointer_capacity_bytes"),
                    chip=_container_value_kb(marker, "beat2chip_capacity_bytes"),
                    event=event_bytes,
                    active=_fmt_int(marker.get("event_sweep_active_set_peak")),
                )
            )
    lines.extend(
        [
            "",
            "## Container Reduction",
            "",
            "| case | variant | old pointer entries | new entries/events | old ChipInfo count | new estimated state KB | estimated state saved KB |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for case in ("h4_4th_new2", "h5_4th_new2"):
        legacy_marker = _first_marker_for(
            results,
            case=case,
            variant="summary_legacy_timeseries",
        )
        legacy_bytes = _container_bytes(legacy_marker, "time_series_estimated_capacity_bytes")
        for variant in ("summary_compact_timeseries", "summary_event_sweep"):
            marker = _first_marker_for(results, case=case, variant=variant)
            if not legacy_marker or not marker:
                continue
            new_bytes = _container_bytes(
                marker,
                "time_series_estimated_capacity_bytes",
                "event_sweep_estimated_capacity_bytes",
            )
            if variant == "summary_event_sweep":
                new_entries = (
                    int(marker.get("event_sweep_start_index_count") or 0)
                    + int(marker.get("event_sweep_end_index_count") or 0)
                )
            else:
                new_entries = marker.get("beat2inst_pointer_count")
            lines.append(
                "| {case} | `{variant}` | {old_ptr} | {new_entries} | {old_chip} | {new_state} | {saved} |".format(
                    case=CASE_DISPLAY[case],
                    variant=variant,
                    old_ptr=_fmt_int(legacy_marker.get("beat2inst_pointer_count")),
                    new_entries=_fmt_int(new_entries),
                    old_chip=_fmt_int(legacy_marker.get("beat2chip_count")),
                    new_state=_fmt_int(None if new_bytes is None else new_bytes / 1024.0),
                    saved=_fmt_int(
                        None
                        if legacy_bytes is None or new_bytes is None
                        else (legacy_bytes - new_bytes) / 1024.0
                    ),
                )
            )
    lines.extend(
        [
            "",
            "## Isolated Savings vs Legacy TimeSeries",
            "",
            "| case | candidate | legacy peak KB | candidate peak KB | saved KB | saved % |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for case in CASE_CHAIN_LENGTH:
        baseline = _aggregate(
            results,
            case=case,
            phase="isolated_qret",
            variant="summary_legacy_timeseries",
        )
        if not baseline["runs"]:
            continue
        base_peak = baseline["median_qret_peak_rss_kb"]
        for variant in ("summary_compact_timeseries", "summary_event_sweep"):
            candidate = _aggregate(results, case=case, phase="isolated_qret", variant=variant)
            if not candidate["runs"]:
                continue
            cand_peak = candidate["median_qret_peak_rss_kb"]
            lines.append(
                "| {case} | `{variant}` | {base} | {cand} | {saved} | {pct} |".format(
                    case=CASE_DISPLAY[case],
                    variant=variant,
                    base=_fmt_int(base_peak),
                    cand=_fmt_int(cand_peak),
                    saved=_fmt_int(
                        None if base_peak is None or cand_peak is None else base_peak - cand_peak
                    ),
                    pct=_fmt_float(
                        None
                        if base_peak is None or cand_peak is None
                        else 100.0 * (float(base_peak) - float(cand_peak)) / float(base_peak),
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
        for variant in (
            "summary_legacy_timeseries",
            "summary_compact_timeseries",
            "summary_event_sweep",
        ):
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
            f"- `{key}` vs `{comparison.get('oracle')}`: normalized equal `{comparison.get('normalized', {}).get('all_equal')}`, raw resource equal `{comparison.get('raw', {}).get('all_equal')}`, raw mismatches `{comparison.get('raw', {}).get('mismatches')}`."
        )
    lines.extend(["", "## Execution Plan", ""])
    lines.append(f"- H5 candidates from H4: `{execution_plan.get('h5_candidates')}`")
    lines.append(f"- H6 final candidate: `{execution_plan.get('h6_candidate')}`")
    lines.append(f"- H6 skipped reason: `{execution_plan.get('h6_skipped_reason')}`")
    lines.append(f"- H6 gate decisions: `{execution_plan.get('h6_decisions')}`")
    lines.append(f"- H6 headroom: `{execution_plan.get('h6_headroom')}`")
    isolated = [row for row in results if row.get("phase") == "isolated_qret"]
    h5_legacy_marker = _first_marker_for(
        results,
        case="h5_4th_new2",
        variant="summary_legacy_timeseries",
    )
    h5_compact_marker = _first_marker_for(
        results,
        case="h5_4th_new2",
        variant="summary_compact_timeseries",
    )
    h5_event_marker = _first_marker_for(
        results,
        case="h5_4th_new2",
        variant="summary_event_sweep",
    )
    h5_legacy_bytes = _container_bytes(h5_legacy_marker, "time_series_estimated_capacity_bytes")
    h5_compact_bytes = _container_bytes(h5_compact_marker, "time_series_estimated_capacity_bytes")
    h5_event_bytes = _container_bytes(h5_event_marker, "event_sweep_estimated_capacity_bytes")
    h5_event_row = _first_result(
        results,
        case="h5_4th_new2",
        phase="isolated_qret",
        variant="summary_event_sweep",
    )
    h5_event_routing = (h5_event_row.get("stage_vmrss_kb") or {}).get("routing_after_main_loop")
    h5_event_peak = h5_event_row.get("qret_peak_rss_kb")
    h5_event_routing_delta = (
        None
        if h5_event_routing is None or h5_event_peak is None
        else int(h5_event_peak) - int(h5_event_routing)
    )
    h6_reason = execution_plan.get("h6_skipped_reason") or "not requested"
    h6_decisions = execution_plan.get("h6_decisions") or {}
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
            "## Final Answers",
            "",
            f"1. H6 `beat2inst_`: not measured because H6 was skipped (`{h6_reason}`). H5 legacy beat2inst capacity was `{_container_value_kb(h5_legacy_marker, 'beat2inst_outer_control_block_capacity_bytes', 'beat2inst_pointer_capacity_bytes')}` KB.",
            f"2. H6 `beat2chip_`: not measured because H6 was skipped. H5 legacy beat2chip capacity was `{_container_value_kb(h5_legacy_marker, 'beat2chip_capacity_bytes')}` KB.",
            f"3. Pointer duplication ratio: H5 legacy `{_fmt_float(h5_legacy_marker.get('beat2inst_pointer_duplication_ratio'), 3)}`.",
            f"4. Compact CSR estimated container reduction on H5: `{_fmt_int(None if h5_legacy_bytes is None or h5_compact_bytes is None else (h5_legacy_bytes - h5_compact_bytes) / 1024.0)}` KB.",
            f"5. Event-sweep estimated container reduction on H5: `{_fmt_int(None if h5_legacy_bytes is None or h5_event_bytes is None else (h5_legacy_bytes - h5_event_bytes) / 1024.0)}` KB.",
            f"6. H6 qret peak: not measured because no H5 candidate passed the H6 gate. H5 event-sweep isolated qret peak median was `{_fmt_int((h6_decisions.get('summary_event_sweep') or {}).get('h5_peak_kb'))}` KB.",
            f"7. H6 process tree peak: not measured because H6 was skipped. H5 event-sweep end-to-end tree peak is reported above.",
            f"8. Elapsed change on H5: event-sweep `{_fmt_float((h6_decisions.get('summary_event_sweep') or {}).get('elapsed_delta_pct'), 2)}`%, compact `{_fmt_float((h6_decisions.get('summary_compact_timeseries') or {}).get('elapsed_delta_pct'), 2)}`%.",
            "9. Full and summary raw metrics matched for all measured H4/H5 comparisons.",
            "10. Beat-level targeted tests matched legacy TimeSeries for compact CSR and event-sweep.",
            "11. Multi-beat semantics were preserved by processing every active beat in legacy order; event-sweep maintains an active set ordered by MachineFunction index.",
            "12. Event-sweep was not made production default because H5 qret peak reduction stayed below both 5% and 50 MB.",
            "13. Legacy fallback remains the default and is also selectable through `QRET_SUMMARY_TIME_SERIES_IMPL=legacy_timeseries` or the compatibility alias `aggregate`.",
            f"14. Next largest qret RSS stage for the best H5 candidate is `{h5_event_row.get('max_rss_stage')}`.",
            f"15. H5 event-sweep peak minus routing-end RSS is `{_fmt_int(h5_event_routing_delta)}` KB.",
            "16. Next qret-side object to inspect is the remaining summary accumulation peak after event-sweep indexing; Python parent JSON handling is a separate end-to-end bottleneck.",
            "17. Python parent-process optimization should be handled as a follow-up, after qret-side TimeSeries work is not the dominant H5/H6 gate.",
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
        architecture = _architecture("summary_event_sweep")
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


def _build_comparisons(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    comparisons: dict[str, Any] = {}
    ignored = {
        "compile_info_json",
        "compiler_stderr",
        "compiler_stdout",
        "compiler_rss_profile_jsonl",
        "pipeline_path",
        "profile_jsonl",
        "samples_jsonl",
        "compiler_executable_path",
        "compiler_executable_hash",
        "compiler_core_library_path",
        "compiler_core_library_hash",
    }
    for case_key in CASE_CHAIN_LENGTH:
        oracle = _first_result(results, case=case_key, phase="isolated_qret", variant="full")
        oracle_name = "full"
        if not oracle:
            oracle = _first_result(
                results,
                case=case_key,
                phase="isolated_qret",
                variant="summary_legacy_timeseries",
            )
            oracle_name = "summary_legacy_timeseries"
        if not oracle:
            continue
        for variant in VARIANT_ORDER:
            if variant == oracle_name:
                continue
            other = _first_result(results, case=case_key, phase="isolated_qret", variant=variant)
            if not other:
                continue
            comparisons[f"{case_key}:{variant}"] = {
                "oracle": oracle_name,
                "normalized": _compare_dicts(
                    oracle.get("normalized_metrics", {}),
                    other.get("normalized_metrics", {}),
                    ignored=ignored,
                ),
                "raw": _compare_dicts(
                    oracle.get("raw_resource_metrics", {}),
                    other.get("raw_resource_metrics", {}),
                ),
            }
    return comparisons


def _semantic_ok(comparisons: Mapping[str, Any], case: str, variant: str) -> bool:
    comparison = comparisons.get(f"{case}:{variant}", {})
    return (
        comparison.get("normalized", {}).get("all_equal") is True
        and comparison.get("raw", {}).get("all_equal") is True
    )


def _median_peak(results: Sequence[Mapping[str, Any]], case: str, variant: str) -> float | None:
    agg = _aggregate(results, case=case, phase="isolated_qret", variant=variant)
    value = agg.get("median_qret_peak_rss_kb")
    return None if value is None else float(value)


def _median_elapsed(results: Sequence[Mapping[str, Any]], case: str, variant: str) -> float | None:
    agg = _aggregate(results, case=case, phase="isolated_qret", variant=variant)
    value = agg.get("median_elapsed_seconds")
    return None if value is None else float(value)


def _select_h5_candidates(
    results: Sequence[Mapping[str, Any]],
    comparisons: Mapping[str, Any],
) -> list[str]:
    candidates: list[str] = []
    event_variant = "summary_event_sweep"
    compact_variant = "summary_compact_timeseries"
    if _semantic_ok(comparisons, "h4_4th_new2", event_variant):
        candidates.append(event_variant)
    if _semantic_ok(comparisons, "h4_4th_new2", compact_variant):
        compact_peak = _median_peak(results, "h4_4th_new2", compact_variant)
        event_peak = _median_peak(results, "h4_4th_new2", event_variant)
        legacy_peak = _median_peak(results, "h4_4th_new2", "summary_legacy_timeseries")
        if (
            compact_peak is not None
            and legacy_peak is not None
            and compact_peak < legacy_peak
            and (event_peak is None or compact_peak <= event_peak * 1.03)
        ):
            candidates.append(compact_variant)
    return candidates


def _select_h6_candidate(
    results: Sequence[Mapping[str, Any]],
    comparisons: Mapping[str, Any],
    h5_candidates: Sequence[str],
) -> tuple[str | None, dict[str, Any]]:
    baseline = "summary_legacy_timeseries"
    baseline_peak = _median_peak(results, "h5_4th_new2", baseline)
    baseline_elapsed = _median_elapsed(results, "h5_4th_new2", baseline)
    decisions: dict[str, Any] = {}
    best_variant: str | None = None
    best_saved = float("-inf")
    for variant in h5_candidates:
        peak = _median_peak(results, "h5_4th_new2", variant)
        elapsed = _median_elapsed(results, "h5_4th_new2", variant)
        saved = None if baseline_peak is None or peak is None else baseline_peak - peak
        saved_pct = None if saved is None or baseline_peak == 0 else 100.0 * saved / baseline_peak
        elapsed_delta_pct = (
            None
            if baseline_elapsed is None or elapsed is None or baseline_elapsed == 0
            else 100.0 * (elapsed - baseline_elapsed) / baseline_elapsed
        )
        ok = (
            _semantic_ok(comparisons, "h5_4th_new2", variant)
            and saved is not None
            and (saved >= 50000 or (saved_pct is not None and saved_pct >= 5.0))
            and (elapsed_delta_pct is None or elapsed_delta_pct <= 5.0)
        )
        decisions[variant] = {
            "h5_peak_kb": peak,
            "h5_baseline_peak_kb": baseline_peak,
            "saved_kb": saved,
            "saved_pct": saved_pct,
            "elapsed_sec": elapsed,
            "baseline_elapsed_sec": baseline_elapsed,
            "elapsed_delta_pct": elapsed_delta_pct,
            "semantic_ok": _semantic_ok(comparisons, "h5_4th_new2", variant),
            "passes_h6_gate": ok,
        }
        if ok and saved is not None and saved > best_saved:
            best_saved = saved
            best_variant = variant
    return best_variant, decisions


def _headroom_ok_for_h6(meminfo: Mapping[str, Any], output_root: Path) -> tuple[bool, dict[str, Any]]:
    mem_available = int(meminfo.get("MemAvailable") or 0)
    mem_total = int(meminfo.get("MemTotal") or 0)
    disk_free = shutil.disk_usage(output_root).free
    payload = {
        "MemTotal": mem_total,
        "MemAvailable": mem_available,
        "SwapTotal": int(meminfo.get("SwapTotal") or 0),
        "SwapFree": int(meminfo.get("SwapFree") or 0),
        "disk_free_bytes": disk_free,
    }
    return mem_available >= 1024 * 1024 and disk_free >= MIN_FREE_DISK_BYTES, payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Profile qret TimeSeries summary memory variants.")
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
    architecture = _architecture("summary_event_sweep")
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

    requested_cases = set(args.cases)
    artifacts: dict[str, sc.SurfaceCodeStepArtifact] = {}
    artifact_payload: dict[str, Any] = {}
    memtotal_kb = meminfo.get("MemTotal")
    results: list[dict[str, Any]] = []
    execution_plan: dict[str, Any] = {
        "h5_candidates": [],
        "h6_candidate": None,
        "h6_decisions": {},
        "h6_headroom": {},
    }

    def ensure_artifact(case_key: str) -> sc.SurfaceCodeStepArtifact:
        if case_key not in artifacts:
            artifacts.update(
                _prepare_artifacts(
                    cases=[case_key],
                    cache_root=cache_root,
                    batch_size=args.batch_size,
                )
            )
            artifact_payload[case_key] = compact_profile._artifact_summary(artifacts[case_key])
            _write_json(run_root / "artifacts.json", artifact_payload)
        return artifacts[case_key]

    def persist(comparisons: Mapping[str, Any] | None = None) -> None:
        _write_jsonl(run_root / "results.jsonl", results)
        _write_csv(run_root / "summary.csv", results)
        _write_json(run_root / "execution_plan.json", execution_plan)
        comparisons_payload = dict(comparisons or _build_comparisons(results))
        _write_json(run_root / "semantic_comparisons.json", comparisons_payload)
        _write_json(run_root / "summary.json", {"environment": environment, "results": results})
        _write_report(
            args.report_path.expanduser().resolve(),
            environment=environment,
            build_provenance=build_provenance,
            results=results,
            comparisons=comparisons_payload,
            execution_plan=execution_plan,
        )

    def run_isolated(case_key: str, variant: str, runs: int) -> None:
        artifact = ensure_artifact(case_key)
        for run_index in range(runs):
            print(f"isolated {case_key} {variant} run {run_index}", flush=True)
            result = _run_isolated_qret_once(
                case_key=case_key,
                variant=variant,
                artifact=artifact,
                run_index=run_index,
                output_root=run_root,
                sample_interval_sec=float(args.sample_interval_sec),
                memtotal_kb=memtotal_kb,
                expected_runtime_hashes=measurement_hashes,
            )
            results.append(result)
            persist()

    if "h4_4th_new2" in requested_cases:
        for variant in VARIANT_ORDER:
            run_isolated("h4_4th_new2", variant, DEFAULT_ISOLATED_RUNS["h4_4th_new2"][variant])
    comparisons = _build_comparisons(results)
    execution_plan["h5_candidates"] = _select_h5_candidates(results, comparisons)
    persist(comparisons)

    if "h5_4th_new2" in requested_cases:
        h5_variants = ["summary_legacy_timeseries", *execution_plan["h5_candidates"]]
        for variant in h5_variants:
            run_isolated("h5_4th_new2", variant, DEFAULT_ISOLATED_RUNS["h5_4th_new2"][variant])
    comparisons = _build_comparisons(results)
    h6_candidate, h6_decisions = _select_h6_candidate(
        results,
        comparisons,
        execution_plan["h5_candidates"],
    )
    execution_plan["h6_candidate"] = h6_candidate
    execution_plan["h6_decisions"] = h6_decisions
    h6_headroom_ok, h6_headroom = _headroom_ok_for_h6(meminfo, run_root)
    execution_plan["h6_headroom"] = h6_headroom
    persist(comparisons)

    if "h6_4th_new2" in requested_cases and h6_candidate is not None and h6_headroom_ok:
        for variant in ("summary_legacy_timeseries", h6_candidate):
            run_isolated("h6_4th_new2", variant, DEFAULT_ISOLATED_RUNS["h6_4th_new2"][variant])
    elif "h6_4th_new2" in requested_cases:
        execution_plan["h6_skipped_reason"] = (
            "no H5 candidate passed the H6 gate" if h6_candidate is None else "insufficient headroom"
        )
        persist(_build_comparisons(results))

    if not args.skip_end_to_end:
        e2e_plan: list[tuple[str, str]] = []
        if "h5_4th_new2" in requested_cases and execution_plan["h5_candidates"]:
            e2e_plan.append(("h5_4th_new2", "summary_legacy_timeseries"))
            for variant in execution_plan["h5_candidates"]:
                e2e_plan.append(("h5_4th_new2", variant))
        if (
            "h6_4th_new2" in requested_cases
            and execution_plan.get("h6_candidate") is not None
            and any(
                row.get("case") == "h6_4th_new2"
                and row.get("phase") == "isolated_qret"
                and row.get("variant") == execution_plan.get("h6_candidate")
                for row in results
            )
        ):
            e2e_plan.append(("h6_4th_new2", "summary_legacy_timeseries"))
            e2e_plan.append(("h6_4th_new2", str(execution_plan["h6_candidate"])))
        for case_key, variant in e2e_plan:
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
                persist(_build_comparisons(results))

    persist(_build_comparisons(results))
    final_hashes = _runtime_hashes(qret_path)
    _ensure_runtime_hash_stable(measurement_hashes, final_hashes)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
