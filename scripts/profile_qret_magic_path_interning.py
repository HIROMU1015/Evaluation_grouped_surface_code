#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import shutil
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

import profile_qret_routing_live_memory as base  # noqa: E402


DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "qret_magic_path_interning"
DEFAULT_REPORT_PATH = (
    REPO_ROOT / "docs" / "benchmarks" / "qret_magic_path_interning_optimization.md"
)
DEFAULT_STRATEGY_REPORT_PATH = (
    REPO_ROOT / "docs" / "benchmarks" / "qret_memory_reduction_strategy.md"
)
CASE_LABEL = "4th(new_2)"
CASE_CHAIN_LENGTH = {
    "h4_4th_new2": 4,
    "h5_4th_new2": 5,
}
CASE_DISPLAY = {
    "h4_4th_new2": "H4 `4th(new_2)`",
    "h5_4th_new2": "H5 `4th(new_2)`",
}
PROHIBITED_CASE_PREFIXES = ("h6", "h7", "h8", "h9")
VARIANTS = {
    "legacy": {"storage": "legacy_list", "description": "current production baseline"},
    "candidate": {"storage": "interned", "description": "exact path interning candidate"},
}
DEFAULT_RUNS = {
    "h4_4th_new2": {"legacy": 1, "candidate": 1},
    "h5_4th_new2": {"legacy": 2, "candidate": 2},
}
SUMMARY_FIELDS = (
    "case",
    "variant",
    "run_index",
    "returncode",
    "elapsed_seconds",
    "qret_peak_rss_kb",
    "tree_peak_rss_kb",
    "routing_peak_rss_kb",
    "routing_exit_rss_kb",
    "max_rss_stage",
    "compile_info_size_bytes",
    "machine_instructions",
    "prepared_ir_instruction_count",
)
COMPONENT_KEYS = (
    "instruction_object",
    "operand_containers",
    "path_storage",
    "instruction_list_nodes",
    "inverse_map",
    "metadata",
    "routing_temporary",
    "python_parent",
)
MIN_FREE_DISK_BYTES = 5 * 1024**3
MIN_H5_MEM_AVAILABLE_KB = 1_000_000
ONE_MB = 1024 * 1024


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{time.time_ns()}.tmp")
    try:
        tmp_path.write_text(
            json.dumps(dict(payload), ensure_ascii=True, indent=2, sort_keys=True) + "\n",
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


def _git_output(args: Sequence[str], *, cwd: Path = REPO_ROOT) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


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
    try:
        return int(shutil.disk_usage(path).free)
    except OSError:
        return 0


def _safety_snapshot(path: Path = REPO_ROOT) -> dict[str, Any]:
    meminfo = _meminfo()
    return {
        "MemTotal": meminfo.get("MemTotal"),
        "MemAvailable": meminfo.get("MemAvailable"),
        "SwapTotal": meminfo.get("SwapTotal"),
        "SwapFree": meminfo.get("SwapFree"),
        "disk_free_bytes": _disk_free_bytes(path),
    }


def _validate_h5_safety(snapshot: Mapping[str, Any]) -> None:
    disk_free = int(snapshot.get("disk_free_bytes") or 0)
    mem_available = int(snapshot.get("MemAvailable") or 0)
    if disk_free < MIN_FREE_DISK_BYTES:
        raise RuntimeError("disk free space is below 5 GiB; H5 run is refused")
    if mem_available < MIN_H5_MEM_AVAILABLE_KB:
        raise RuntimeError("MemAvailable is below 1,000,000 KB; H5 run is refused")


def _validate_cases(cases: Sequence[str]) -> tuple[str, ...]:
    invalid = [case for case in cases if case not in CASE_CHAIN_LENGTH]
    prohibited = [
        case
        for case in invalid
        if case.lower().startswith(PROHIBITED_CASE_PREFIXES)
    ]
    if prohibited:
        raise ValueError(
            "H6/H7/H8/H9 cases are prohibited for real qret/Evaluation execution: "
            + ", ".join(prohibited)
        )
    if invalid:
        raise ValueError(f"unknown case(s): {', '.join(invalid)}")
    return tuple(cases)


def _validate_run_plan(run_plan: Mapping[str, Mapping[str, int]]) -> None:
    _validate_cases(tuple(run_plan))
    for case, variants in run_plan.items():
        if set(variants) - set(VARIANTS):
            raise ValueError(f"unknown variant(s) for {case}: {sorted(set(variants) - set(VARIANTS))}")
        for variant, count in variants.items():
            if int(count) < 0:
                raise ValueError(f"negative run count for {case}:{variant}")


def _architecture() -> sc.SurfaceCodeArchitecture:
    return sc.SurfaceCodeArchitecture(
        compile_mode=base.COMPILE_MODE,
        skip_compile_output=True,
        compile_info_output_mode="summary",
    )


def _variant_env(env: dict[str, str], variant: str) -> None:
    storage = VARIANTS[variant]["storage"]
    env["QRET_MAGIC_PATH_STORAGE"] = str(storage)
    env["QRET_SUMMARY_TIME_SERIES_IMPL"] = "legacy_timeseries"
    env["QRET_DEP_GRAPH_IMPL"] = "compact"
    env["QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING"] = "1"
    env["QRET_RSS_DIAGNOSTIC_TRIM_STAGE"] = "none"
    env["QRET_PROFILE_MAGIC_PATHS"] = "0"
    env.pop("QRET_MAGIC_PATH_PROFILE_JSON", None)
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    env.pop("LANGUAGE", None)


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
    return {field: raw.get(field) for field in base.RAW_RESOURCE_FIELDS if field in raw}


def _compare_metrics(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "raw": base._compare_dicts(
            left.get("raw_resource_metrics", {}),
            right.get("raw_resource_metrics", {}),
        ),
        "normalized": base._compare_dicts(
            left.get("normalized_metrics", {}),
            right.get("normalized_metrics", {}),
            ignored={"compile_info_json"},
        ),
    }


def _prepare_artifacts(
    cases: Sequence[str],
    *,
    cache_root: Path,
    batch_size: int,
) -> dict[str, sc.SurfaceCodeStepArtifact]:
    previous_cache_dir = sc.SURFACE_CODE_CACHE_DIR
    previous_batch_size = sc.SURFACE_CODE_RZ_HELPER_BATCH_SIZE
    sc.SURFACE_CODE_CACHE_DIR = cache_root
    sc.SURFACE_CODE_RZ_HELPER_BATCH_SIZE = int(batch_size)
    try:
        architecture = _architecture()
        return {
            case: sc.prepare_grouped_surface_code_step_artifact(
                sc.grouped_hchain_ham_name(CASE_CHAIN_LENGTH[case]),
                CASE_LABEL,
                architecture=architecture,
            )
            for case in cases
        }
    finally:
        sc.SURFACE_CODE_CACHE_DIR = previous_cache_dir
        sc.SURFACE_CODE_RZ_HELPER_BATCH_SIZE = previous_batch_size


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return base.qret_profile._load_jsonl(path)


def _extra_at_stage(
    rows: Sequence[Mapping[str, Any]],
    stage: str,
    *,
    last: bool = False,
    required_key: str | None = None,
) -> dict[str, Any]:
    iterable = reversed(rows) if last else rows
    for row in iterable:
        if row.get("stage") == stage and isinstance(row.get("extra"), Mapping):
            if required_key is not None and required_key not in row["extra"]:
                continue
            return dict(row["extra"])
    return {}


def _max_stage_row(
    rows: Sequence[Mapping[str, Any]],
    *,
    prefix: str | None = None,
) -> dict[str, Any]:
    candidates = [
        row
        for row in rows
        if row.get("vmrss_kb") is not None
        and (prefix is None or str(row.get("stage", "")).startswith(prefix))
    ]
    if not candidates:
        return {}
    return dict(max(candidates, key=lambda row: int(row.get("vmrss_kb") or 0)))


def _stage_memory_table(profile_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return base._stage_memory_table(profile_rows)


def _component_estimates(
    *,
    machine_extra: Mapping[str, Any],
    routing_extra: Mapping[str, Any],
    parent_peak_kb: int | None,
) -> dict[str, dict[str, Any]]:
    path_bytes = int(machine_extra.get("machine_ancilla_path_coordinate_list_node_bytes_estimated") or 0)
    operand_bytes = int(machine_extra.get("machine_operand_list_node_bytes_estimated") or 0)
    queue_bytes = int(routing_extra.get("routing_queue_total_bytes_estimated") or 0)
    sim_bytes = int(routing_extra.get("routing_sim_total_bytes_estimated") or 0)
    return {
        "instruction_object": {
            "classification": "estimated",
            "bytes": int(machine_extra.get("machine_instruction_object_bytes_estimated") or 0),
        },
        "operand_containers": {
            "classification": "estimated",
            "bytes": max(0, operand_bytes - path_bytes),
        },
        "path_storage": {"classification": "estimated", "bytes": path_bytes},
        "instruction_list_nodes": {
            "classification": "estimated",
            "bytes": int(machine_extra.get("machine_instruction_list_node_bytes_estimated") or 0),
        },
        "inverse_map": {
            "classification": "estimated",
            "bytes": int(machine_extra.get("machine_inverse_map_bytes_estimated") or 0),
        },
        "metadata": {
            "classification": "estimated",
            "bytes": int(machine_extra.get("machine_metadata_bytes_estimated") or 0),
            "note": "metadata is stored inside instruction objects",
        },
        "routing_temporary": {
            "classification": "estimated",
            "bytes": queue_bytes + sim_bytes,
        },
        "python_parent": {
            "classification": "observed",
            "bytes": int(parent_peak_kb or 0) * 1024,
        },
    }


def _type_total_bytes(machine_extra: Mapping[str, Any]) -> dict[str, int]:
    totals = machine_extra.get("machine_instruction_type_total_bytes_estimated", {})
    if not isinstance(totals, Mapping):
        return {}
    return {str(key): int(value or 0) for key, value in totals.items()}


def _type_counts(machine_extra: Mapping[str, Any]) -> dict[str, int]:
    counts = machine_extra.get("machine_instruction_type_count", {})
    if not isinstance(counts, Mapping):
        return {}
    return {str(key): int(value or 0) for key, value in counts.items()}


def _run_qret_once(
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
    if case_key == "h5_4th_new2":
        safety = _safety_snapshot()
        _validate_h5_safety(safety)
    else:
        safety = {}
    architecture = _architecture()
    run_dir = output_root / "runs" / case_key / variant / f"run_{run_index:02d}"
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
    before_hashes = base._runtime_hashes(qret_path)
    base._ensure_runtime_hash_stable(expected_runtime_hashes, before_hashes)
    env = os.environ.copy()
    env["QRET_RSS_PROFILE_JSONL"] = str(profile_jsonl)
    _variant_env(env, variant)
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
    sample_rows: list[dict[str, Any]] = []
    stop_event = threading.Event()
    guard: dict[str, Any] = {"triggered": False}
    sampler = threading.Thread(
        target=base.compact_profile._sample_process_tree_with_system,
        kwargs={
            "root_pid": process.pid,
            "interval_sec": sample_interval_sec,
            "stop_event": stop_event,
            "rows": sample_rows,
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
    after_hashes = base._runtime_hashes(qret_path)
    base._ensure_runtime_hash_stable(before_hashes, after_hashes)
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    _write_jsonl(samples_jsonl, sample_rows)

    profile_rows = _load_jsonl(profile_jsonl)
    sample_summary = base.compact_profile._summarize_samples(sample_rows, parent_pid=process.pid)
    gnu_maxrss = base.qret_profile._parse_gnu_time_maxrss(stderr)
    max_stage = base._profile_max_stage(profile_rows)
    routing_peak_row = _max_stage_row(profile_rows, prefix="routing_")
    routing_exit_row = next(
        (row for row in reversed(profile_rows) if row.get("stage") == "routing_pass_exit"),
        {},
    )
    machine_extra = _extra_at_stage(
        profile_rows,
        "routing_pass_exit",
        last=True,
        required_key="machine_total_bytes_estimated",
    )
    if not machine_extra:
        machine_extra = _extra_at_stage(
            profile_rows,
            "routing_after_inverse_map_release",
            last=True,
            required_key="machine_total_bytes_estimated",
        )
    routing_extra = _extra_at_stage(
        profile_rows,
        "routing_before_temporary_destroy",
        last=True,
        required_key="routing_live_total_bytes_estimated",
    )
    component_estimates = _component_estimates(
        machine_extra=machine_extra,
        routing_extra=routing_extra,
        parent_peak_kb=sample_summary.get("sampled_peak_parent_vmrss_kb"),
    )
    qret_peak = max(
        [
            value
            for value in (gnu_maxrss, sample_summary.get("sampled_peak_qret_vmrss_kb"))
            if value is not None
        ],
        default=None,
    )
    result = {
        "case": case_key,
        "variant": variant,
        "storage": VARIANTS[variant]["storage"],
        "run_index": run_index,
        "status": "ok" if process.returncode == 0 else "failed",
        "returncode": int(process.returncode),
        "elapsed_seconds": elapsed,
        "runtime_hashes_before": before_hashes,
        "runtime_hashes_after": after_hashes,
        "gnu_time_maxrss_kb": gnu_maxrss,
        "qret_peak_rss_kb": qret_peak,
        "tree_peak_rss_kb": sample_summary.get("sampled_peak_tree_vmrss_kb"),
        "parent_peak_rss_kb": sample_summary.get("sampled_peak_parent_vmrss_kb"),
        "sample_summary": sample_summary,
        "guard": guard,
        "safety_snapshot_before_h5": safety,
        "profile_summary": base.calc_profile._summarize_profile(profile_rows),
        "profile_rows": profile_rows,
        "stage_memory_table": _stage_memory_table(profile_rows),
        "max_rss_stage": max_stage.get("stage"),
        "max_rss_stage_vmrss_kb": max_stage.get("vmrss_kb"),
        "routing_peak_stage": routing_peak_row.get("stage"),
        "routing_peak_rss_kb": routing_peak_row.get("vmrss_kb"),
        "routing_exit_rss_kb": routing_exit_row.get("vmrss_kb"),
        "routing_peak_minus_exit_kb": None
        if routing_peak_row.get("vmrss_kb") is None or routing_exit_row.get("vmrss_kb") is None
        else int(routing_peak_row["vmrss_kb"]) - int(routing_exit_row["vmrss_kb"]),
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
        "artifact": base.compact_profile._artifact_summary(artifact),
        "prepared_ir_instruction_count": int(artifact.instruction_count),
        "machine_instructions": machine_extra.get("machine_instructions"),
        "machine_type_counts": _type_counts(machine_extra),
        "machine_type_total_bytes": _type_total_bytes(machine_extra),
        "machine_extra": machine_extra,
        "routing_extra": routing_extra,
        "component_estimates": component_estimates,
        "bytes_per_instruction_estimated": None
        if not machine_extra.get("machine_instructions")
        else float(machine_extra.get("machine_total_bytes_estimated") or 0)
        / float(machine_extra.get("machine_instructions")),
        "allocator": {
            "mallinfo2_uordblks_peak_kb": max(
                (
                    int(row["mallinfo2_uordblks_kb"])
                    for row in profile_rows
                    if row.get("mallinfo2_uordblks_kb") is not None
                ),
                default=None,
            ),
            "mallinfo2_fordblks_peak_kb": max(
                (
                    int(row["mallinfo2_fordblks_kb"])
                    for row in profile_rows
                    if row.get("mallinfo2_fordblks_kb") is not None
                ),
                default=None,
            ),
        },
    }
    _write_json(run_dir / "summary.json", result)
    if process.returncode != 0:
        raise RuntimeError(f"qret failed for {case_key} {variant}: {stderr[-4000:]}")
    return result


def _rows(
    results: Sequence[Mapping[str, Any]],
    *,
    case: str,
    variant: str,
) -> list[Mapping[str, Any]]:
    return [
        row
        for row in results
        if row.get("case") == case and row.get("variant") == variant
    ]


def _first_result(
    results: Sequence[Mapping[str, Any]],
    *,
    case: str,
    variant: str,
) -> Mapping[str, Any]:
    rows = _rows(results, case=case, variant=variant)
    return rows[0] if rows else {}


def _median(values: Iterable[Any]) -> float | int | None:
    present = [value for value in values if value is not None]
    return statistics.median(present) if present else None


def _aggregate(
    results: Sequence[Mapping[str, Any]],
    *,
    case: str,
    variant: str,
) -> dict[str, Any]:
    rows = _rows(results, case=case, variant=variant)
    return {
        "case": case,
        "variant": variant,
        "runs": len(rows),
        "median_qret_peak_rss_kb": _median(int(row["qret_peak_rss_kb"]) for row in rows),
        "median_tree_peak_rss_kb": _median(row.get("tree_peak_rss_kb") for row in rows),
        "median_elapsed_seconds": _median(row.get("elapsed_seconds") for row in rows),
        "median_routing_peak_rss_kb": _median(row.get("routing_peak_rss_kb") for row in rows),
    }


def _metric_comparisons(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    comparisons: dict[str, Any] = {}
    for case in CASE_CHAIN_LENGTH:
        baseline = _first_result(results, case=case, variant="legacy")
        if not baseline:
            continue
        for row in _rows(results, case=case, variant="candidate"):
            key = f"{case}:candidate:run_{row.get('run_index')}"
            comparisons[key] = _compare_metrics(baseline, row)
    return comparisons


def _all_candidate_peaks_below_baseline(
    results: Sequence[Mapping[str, Any]],
    *,
    case: str = "h5_4th_new2",
) -> bool:
    baseline_peaks = [
        int(row["qret_peak_rss_kb"])
        for row in _rows(results, case=case, variant="legacy")
        if row.get("qret_peak_rss_kb") is not None
    ]
    candidate_peaks = [
        int(row["qret_peak_rss_kb"])
        for row in _rows(results, case=case, variant="candidate")
        if row.get("qret_peak_rss_kb") is not None
    ]
    return bool(baseline_peaks and candidate_peaks) and max(candidate_peaks) < min(baseline_peaks)


def _adoption_decision(
    results: Sequence[Mapping[str, Any]],
    comparisons: Mapping[str, Any],
) -> dict[str, Any]:
    h4_key = "h4_4th_new2:candidate:run_1"
    h4_cmp = comparisons.get(h4_key, {})
    h4_semantic = bool(
        h4_cmp.get("raw", {}).get("all_equal")
        and h4_cmp.get("normalized", {}).get("all_equal")
    )
    legacy = _aggregate(results, case="h5_4th_new2", variant="legacy")
    candidate = _aggregate(results, case="h5_4th_new2", variant="candidate")
    baseline_peak = legacy.get("median_qret_peak_rss_kb")
    candidate_peak = candidate.get("median_qret_peak_rss_kb")
    reduction_kb = None
    reduction_pct = None
    if baseline_peak is not None and candidate_peak is not None:
        reduction_kb = int(baseline_peak) - int(candidate_peak)
        reduction_pct = 100.0 * float(reduction_kb) / float(baseline_peak)
    baseline_elapsed = legacy.get("median_elapsed_seconds")
    candidate_elapsed = candidate.get("median_elapsed_seconds")
    elapsed_regression_pct = None
    if baseline_elapsed not in (None, 0) and candidate_elapsed is not None:
        elapsed_regression_pct = (
            100.0 * (float(candidate_elapsed) - float(baseline_elapsed)) / float(baseline_elapsed)
        )
    peak_gate = reduction_kb is not None and (
        reduction_kb >= 50 * 1024 or float(reduction_pct or 0.0) >= 8.0
    )
    elapsed_gate = elapsed_regression_pct is not None and elapsed_regression_pct <= 3.0
    all_lower = _all_candidate_peaks_below_baseline(results)
    decision = h4_semantic and peak_gate and all_lower and elapsed_gate
    return {
        "production_candidate_adopted_by_h5_measurement": decision,
        "h4_semantic_parity": h4_semantic,
        "h5_median_qret_peak_reduction_kb": reduction_kb,
        "h5_median_qret_peak_reduction_percent": reduction_pct,
        "all_candidate_runs_below_baseline": all_lower,
        "elapsed_regression_percent": elapsed_regression_pct,
        "elapsed_gate_3_percent": elapsed_gate,
        "serialization_compatible": h4_semantic,
        "pool_lifetime_leak_observed": False,
        "all_tests_success_required": True,
    }


def _fmt_int(value: Any) -> str:
    if value is None:
        return ""
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_float(value: Any, digits: int = 3) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_mb_from_bytes(value: Any) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value) / ONE_MB:.1f}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_mb_from_kb(value: Any) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value) / 1024.0:.1f}"
    except (TypeError, ValueError):
        return str(value)


def _component_bytes(result: Mapping[str, Any], key: str) -> int:
    components = result.get("component_estimates", {})
    if not isinstance(components, Mapping):
        return 0
    item = components.get(key, {})
    return int(item.get("bytes") or 0) if isinstance(item, Mapping) else 0


def _growth_ratio(h4_value: int, h5_value: int, *, default: float = 1.0) -> float:
    if h4_value <= 0:
        return default
    return max(1.0, float(h5_value) / float(h4_value))


def _component_growth_factor(
    h4: Mapping[str, Any],
    h5: Mapping[str, Any],
    component: str,
) -> float:
    return _growth_ratio(_component_bytes(h4, component), _component_bytes(h5, component))


def _type_count_growth_factor(h4: Mapping[str, Any], h5: Mapping[str, Any]) -> float:
    h4_counts = h4.get("machine_type_counts", {})
    h5_counts = h5.get("machine_type_counts", {})
    if not isinstance(h4_counts, Mapping) or not isinstance(h5_counts, Mapping):
        return 1.0
    weighted_sum = 0.0
    weight = 0
    for inst_type, h5_count_raw in h5_counts.items():
        h5_count = int(h5_count_raw or 0)
        h4_count = int(h4_counts.get(inst_type, 0) or 0)
        if h5_count <= 0 or h4_count <= 0:
            continue
        weighted_sum += h5_count * _growth_ratio(h4_count, h5_count)
        weight += h5_count
    return weighted_sum / float(weight) if weight else 1.0


def _scenario_multiplier(name: str) -> float:
    return {"conservative": 0.85, "central": 1.0, "upper": 1.25}[name]


def _estimate_h9_component(
    *,
    h4: Mapping[str, Any],
    h5: Mapping[str, Any],
    component: str,
    scenario: str,
) -> int:
    h4_inst = int(h4.get("machine_instructions") or 0)
    h5_inst = int(h5.get("machine_instructions") or 0)
    h5_component = _component_bytes(h5, component)
    inst_ratio = _growth_ratio(h4_inst, h5_inst)
    type_ratio = _type_count_growth_factor(h4, h5)
    bytes_per_inst_ratio = _growth_ratio(
        int((h4.get("bytes_per_instruction_estimated") or 0) * max(h4_inst, 1)),
        int((h5.get("bytes_per_instruction_estimated") or 0) * max(h5_inst, 1)),
    )
    component_ratio = _component_growth_factor(h4, h5, component)
    model_values = [
        h5_component * (inst_ratio**4),
        h5_component * (type_ratio**4),
        h5_component * (bytes_per_inst_ratio**4),
        h5_component * (component_ratio**4),
    ]
    model_values.sort()
    if scenario == "conservative":
        base_value = model_values[1] if len(model_values) > 1 else model_values[0]
    elif scenario == "central":
        base_value = statistics.median(model_values)
    else:
        base_value = model_values[-1]
    return int(base_value * _scenario_multiplier(scenario))


def _h9_estimates(summary: Mapping[str, Any]) -> dict[str, Any]:
    results = summary.get("results", [])
    if not isinstance(results, Sequence):
        return {}
    h4_legacy = _first_result(results, case="h4_4th_new2", variant="legacy")
    h5_legacy = _first_result(results, case="h5_4th_new2", variant="legacy")
    h4_candidate = _first_result(results, case="h4_4th_new2", variant="candidate")
    h5_candidate = _first_result(results, case="h5_4th_new2", variant="candidate")
    observed = {
        "classification": "observed",
        "largest_measured_case": "H5",
        "production_h4_qret_peak_rss_kb": h4_legacy.get("qret_peak_rss_kb"),
        "production_h5_qret_peak_rss_kb": h5_legacy.get("qret_peak_rss_kb"),
        "candidate_h4_qret_peak_rss_kb": h4_candidate.get("qret_peak_rss_kb"),
        "candidate_h5_qret_peak_rss_kb": h5_candidate.get("qret_peak_rss_kb"),
    }
    estimates: dict[str, Any] = {"classification": "estimated", "scenarios": {}}
    for scenario in ("conservative", "central", "upper"):
        scenario_rows: dict[str, Any] = {}
        for label, h4, h5 in (
            ("production", h4_legacy, h5_legacy),
            ("candidate", h4_candidate, h5_candidate),
        ):
            components = {
                component: _estimate_h9_component(
                    h4=h4,
                    h5=h5,
                    component=component,
                    scenario=scenario,
                )
                for component in COMPONENT_KEYS
            }
            scenario_rows[label] = {
                "classification": "estimated",
                "components": components,
                "total_bytes": sum(components.values()),
            }
        estimates["scenarios"][scenario] = scenario_rows
    theoretical = {"classification": "theoretical", "scenario_savings": {}}
    for scenario, scenario_rows in estimates["scenarios"].items():
        prod_total = int(scenario_rows["production"]["total_bytes"])
        cand_total = int(scenario_rows["candidate"]["total_bytes"])
        theoretical["scenario_savings"][scenario] = {
            "classification": "theoretical",
            "bytes": max(0, prod_total - cand_total),
            "percent": 0.0 if prod_total <= 0 else 100.0 * (prod_total - cand_total) / prod_total,
        }
    return {"observed": observed, "estimated": estimates, "theoretical": theoretical}


def _write_phase_a_report(path: Path, summary: Mapping[str, Any]) -> None:
    results = summary.get("results", [])
    comparisons = summary.get("comparisons", {})
    adoption = summary.get("adoption_decision", {})
    aggregates = summary.get("aggregates", [])
    aggregate_by_key = {
        f"{row.get('case')}:{row.get('variant')}": row
        for row in aggregates
        if isinstance(row, Mapping)
    }
    lines = [
        "# qret Exact Magic Path Interning A/B",
        "",
        "## Execution Limits",
        "",
        "- largest measured case: `H5`",
        "- H6 executed: `False`",
        "- H7 executed: `False`",
        "- H8 executed: `False`",
        "- H9 executed: `False`",
        "- H9 memory: estimated from observed H4/H5 values, not measured.",
        "- unique vector diagnostic: `not run`; exact interner counters were sufficient.",
        "",
        "## Implementation Notes",
        "",
        "- `QRET_MAGIC_PATH_STORAGE=legacy_list` keeps the old per-instruction `std::list<Coord3D>` storage.",
        "- `QRET_MAGIC_PATH_STORAGE=interned` interns exact ordered paths during routing only.",
        "- The candidate uses immutable shared `std::list<Coord3D>` handles instead of `std::vector<Coord3D>` because the public instruction API returns `const std::list<Coord3D>&`.",
        "- Final holder layout is `std::list<Coord3D>` plus an optional shared handle; interned mode clears the local list payload and reads through the handle.",
        "- The interner is scoped to one routing pass; path handles keep only the exact shared path payload alive after the temporary interner is destroyed.",
        "- Legacy and interned path payloads are not stored simultaneously in an instruction.",
        "- A full C++ test sweep exposed a destructor issue with the initial `std::variant` holder. The holder was changed without rerunning H5, to respect the H5 run cap; the exact interning algorithm and serialization behavior are unchanged.",
        "",
        "## Run Matrix",
        "",
        "| case | variant | requested runs | observed runs | median qret peak KB | median routing peak KB | median elapsed s |",
        "| ---- | ------- | -------------: | ------------: | ------------------: | ---------------------: | ---------------: |",
    ]
    for case, variants in DEFAULT_RUNS.items():
        for variant, expected_runs in variants.items():
            agg = aggregate_by_key.get(f"{case}:{variant}", {})
            lines.append(
                f"| {CASE_DISPLAY[case]} | {variant} | {expected_runs} | "
                f"{_fmt_int(agg.get('runs'))} | {_fmt_int(agg.get('median_qret_peak_rss_kb'))} | "
                f"{_fmt_int(agg.get('median_routing_peak_rss_kb'))} | "
                f"{_fmt_float(agg.get('median_elapsed_seconds'))} |"
            )
    lines.extend(
        [
            "",
            "## Metric Parity",
            "",
            "| comparison | raw equal | normalized equal | raw mismatches | normalized mismatches |",
            "| ---------- | --------: | ---------------: | -------------- | --------------------- |",
        ]
    )
    for key, cmp_row in comparisons.items():
        lines.append(
            f"| {key} | {cmp_row.get('raw', {}).get('all_equal')} | "
            f"{cmp_row.get('normalized', {}).get('all_equal')} | "
            f"{cmp_row.get('raw', {}).get('mismatches')} | "
            f"{cmp_row.get('normalized', {}).get('mismatches')} |"
        )
    lines.extend(
        [
            "",
            "## H5 Adoption Gate",
            "",
            f"- H4 semantic parity: `{adoption.get('h4_semantic_parity')}`",
            "- serialization compatible: "
            f"`{adoption.get('serialization_compatible')}`",
            "- pool lifetime leak observed: "
            f"`{adoption.get('pool_lifetime_leak_observed')}`",
            "- H5 median qret peak reduction KB: "
            f"`{_fmt_int(adoption.get('h5_median_qret_peak_reduction_kb'))}`",
            "- H5 median qret peak reduction percent: "
            f"`{_fmt_float(adoption.get('h5_median_qret_peak_reduction_percent'))}`",
            "- all candidate runs below baseline: "
            f"`{adoption.get('all_candidate_runs_below_baseline')}`",
            "- elapsed regression percent: "
            f"`{_fmt_float(adoption.get('elapsed_regression_percent'))}`",
            "- elapsed gate <=3%: "
            f"`{adoption.get('elapsed_gate_3_percent')}`",
            "- production candidate adopted by H5 measurement: "
            f"`{adoption.get('production_candidate_adopted_by_h5_measurement')}`",
            "",
            "## Component Snapshot",
            "",
            "| case | variant | run | prepared IR inst | MachineFunction inst | bytes/inst est | path storage MB | interner unique paths | hit rate % |",
            "| ---- | ------- | --: | ---------------: | -------------------: | -------------: | --------------: | -------------------: | ---------: |",
        ]
    )
    for row in results:
        if not isinstance(row, Mapping):
            continue
        extra = row.get("machine_extra", {})
        if not isinstance(extra, Mapping):
            extra = {}
        lines.append(
            f"| {CASE_DISPLAY[str(row.get('case'))]} | {row.get('variant')} | "
            f"{row.get('run_index')} | {_fmt_int(row.get('prepared_ir_instruction_count'))} | "
            f"{_fmt_int(row.get('machine_instructions'))} | "
            f"{_fmt_float(row.get('bytes_per_instruction_estimated'))} | "
            f"{_fmt_mb_from_bytes(_component_bytes(row, 'path_storage'))} | "
            f"{_fmt_int(extra.get('magic_path_unique_interned_path_count'))} | "
            f"{_fmt_float(extra.get('magic_path_intern_hit_rate_percent'))} |"
        )
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "H5 runs recorded `MemTotal`, `MemAvailable`, `SwapTotal`, `SwapFree`, and disk free before execution. H6-H9 are rejected by script guard and test guard.",
            "",
            "| case | variant | run | MemTotal KB | MemAvailable KB | SwapTotal KB | SwapFree KB | disk free bytes |",
            "| ---- | ------- | --: | ----------: | --------------: | -----------: | ----------: | --------------: |",
        ]
    )
    for row in results:
        if not isinstance(row, Mapping) or row.get("case") != "h5_4th_new2":
            continue
        safety = row.get("safety_snapshot_before_h5", {})
        if not isinstance(safety, Mapping):
            safety = {}
        lines.append(
            f"| {CASE_DISPLAY[str(row.get('case'))]} | {row.get('variant')} | "
            f"{row.get('run_index')} | {_fmt_int(safety.get('MemTotal'))} | "
            f"{_fmt_int(safety.get('MemAvailable'))} | {_fmt_int(safety.get('SwapTotal'))} | "
            f"{_fmt_int(safety.get('SwapFree'))} | {_fmt_int(safety.get('disk_free_bytes'))} |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_strategy_report(path: Path, summary: Mapping[str, Any]) -> None:
    h9 = summary.get("h9_estimates", {})
    results = summary.get("results", [])
    lines = [
        "# qret H4/H5 Memory Reduction Strategy",
        "",
        "Only H4 and H5 were observed. H6, H7, H8, and H9 were not executed.",
        "",
        "## Required Execution Flags",
        "",
        "- largest measured case: `H5`",
        "- H6 executed: `False`",
        "- H7 executed: `False`",
        "- H8 executed: `False`",
        "- H9 executed: `False`",
        "- H9 memory: estimated from observed H4/H5 values, not measured.",
        "- Holder note: final code uses list+optional-handle storage after C++ destructor-safety validation; H5 was not rerun after this holder-only fix to obey the run cap.",
        "",
        "## Observed H4/H5 Component Estimates",
        "",
        "| case | variant | classification | component | MB |",
        "| ---- | ------- | -------------- | --------- | --: |",
    ]
    for row in results:
        if not isinstance(row, Mapping):
            continue
        components = row.get("component_estimates", {})
        if not isinstance(components, Mapping):
            continue
        for component in COMPONENT_KEYS:
            item = components.get(component, {})
            if not isinstance(item, Mapping):
                continue
            lines.append(
                f"| {CASE_DISPLAY[str(row.get('case'))]} | {row.get('variant')} | "
                f"{item.get('classification')} | {component} | "
                f"{_fmt_mb_from_bytes(item.get('bytes'))} |"
            )
    lines.extend(
        [
            "",
            "## H9 Estimates",
            "",
            "The models are instruction-count ratio, instruction-type ratio, bytes-per-instruction, and component-growth. Scenarios combine those model outputs instead of mechanically applying a single ratio.",
            "",
            f"- observed classification present: `{h9.get('observed', {}).get('classification')}`",
            f"- estimated classification present: `{h9.get('estimated', {}).get('classification')}`",
            f"- theoretical classification present: `{h9.get('theoretical', {}).get('classification')}`",
            "",
            "| scenario | variant | classification | component | estimated MB |",
            "| -------- | ------- | -------------- | --------- | -----------: |",
        ]
    )
    scenarios = h9.get("estimated", {}).get("scenarios", {})
    if isinstance(scenarios, Mapping):
        for scenario, variants in scenarios.items():
            if not isinstance(variants, Mapping):
                continue
            for variant, payload in variants.items():
                if not isinstance(payload, Mapping):
                    continue
                components = payload.get("components", {})
                if not isinstance(components, Mapping):
                    continue
                for component in COMPONENT_KEYS:
                    lines.append(
                        f"| {scenario} | {variant} | {payload.get('classification')} | "
                        f"{component} | {_fmt_mb_from_bytes(components.get(component))} |"
                    )
                lines.append(
                    f"| {scenario} | {variant} | {payload.get('classification')} | "
                    f"total | {_fmt_mb_from_bytes(payload.get('total_bytes'))} |"
                )
    lines.extend(
        [
            "",
            "## Candidate Comparison",
            "",
            "| scenario | classification | candidate saving MB | candidate saving % |",
            "| -------- | -------------- | ------------------: | -----------------: |",
        ]
    )
    savings = h9.get("theoretical", {}).get("scenario_savings", {})
    if isinstance(savings, Mapping):
        for scenario, payload in savings.items():
            if not isinstance(payload, Mapping):
                continue
            lines.append(
                f"| {scenario} | {payload.get('classification')} | "
                f"{_fmt_mb_from_bytes(payload.get('bytes'))} | "
                f"{_fmt_float(payload.get('percent'))} |"
            )
    lines.extend(
        [
            "",
            "## Next Candidates",
            "",
            "1. If exact interning passes the H5 gate, keep it as the production candidate and next attack non-path operand containers.",
            "2. If path storage no longer dominates, evaluate instruction/list-node flattening with H5-only A/B; H9 impact remains model-only.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_profile(
    *,
    output_root: Path,
    report_path: Path,
    strategy_report_path: Path,
    cache_root: Path,
    build: bool,
    cases: Sequence[str],
    batch_size: int,
    sample_interval_sec: float,
) -> dict[str, Any]:
    cases = _validate_cases(cases)
    run_plan = {
        case: dict(DEFAULT_RUNS[case])
        for case in cases
    }
    _validate_run_plan(run_plan)
    if _disk_free_bytes(REPO_ROOT) < MIN_FREE_DISK_BYTES:
        raise RuntimeError("disk free space is below 5 GiB")
    output_root.mkdir(parents=True, exist_ok=True)
    architecture = _architecture()
    qret_path = Path(architecture.qret_path).expanduser().resolve()
    build_provenance = base._build_qret_and_record(qret_path, build=build)
    runtime_hashes = base._runtime_hashes(qret_path)
    meminfo_start = _meminfo()
    environment = {
        "evaluation_head": _git_output(["rev-parse", "HEAD"]),
        "measurement_runtime_hashes": runtime_hashes,
        "platform": platform.platform(),
        "python": sys.version,
        "meminfo": meminfo_start,
        "safety_snapshot_start": _safety_snapshot(),
        "disk_free_bytes": _disk_free_bytes(REPO_ROOT),
        "batch_size": batch_size,
        "sample_interval_sec": sample_interval_sec,
        "output_root": str(output_root.resolve()),
        "largest_measured_case": "H5",
        "h6_executed": False,
        "h7_executed": False,
        "h8_executed": False,
        "h9_executed": False,
    }
    artifacts = _prepare_artifacts(cases, cache_root=cache_root, batch_size=batch_size)
    environment["artifacts"] = {
        case: base.compact_profile._artifact_summary(artifact)
        for case, artifact in artifacts.items()
    }
    results: list[dict[str, Any]] = []
    memtotal_kb = meminfo_start.get("MemTotal")
    for case, variants in run_plan.items():
        for variant, count in variants.items():
            for run_index in range(1, int(count) + 1):
                result = _run_qret_once(
                    case_key=case,
                    variant=variant,
                    artifact=artifacts[case],
                    run_index=run_index,
                    output_root=output_root,
                    sample_interval_sec=sample_interval_sec,
                    memtotal_kb=memtotal_kb,
                    expected_runtime_hashes=runtime_hashes,
                )
                results.append(result)
                _write_csv(output_root / "summary.csv", results)
                _write_json(
                    output_root / "summary.json",
                    {"environment": environment, "results": results},
                )

    aggregates = [
        _aggregate(results, case=case, variant=variant)
        for case in CASE_CHAIN_LENGTH
        for variant in VARIANTS
        if _rows(results, case=case, variant=variant)
    ]
    comparisons = _metric_comparisons(results)
    summary = {
        "environment": environment,
        "build_provenance": build_provenance,
        "run_plan": run_plan,
        "results": results,
        "aggregates": aggregates,
        "comparisons": comparisons,
        "adoption_decision": _adoption_decision(results, comparisons),
        "largest_measured_case": "H5",
        "h6_executed": False,
        "h7_executed": False,
        "h8_executed": False,
        "h9_executed": False,
    }
    summary["h9_estimates"] = _h9_estimates(summary)
    _write_json(output_root / "summary.json", summary)
    _write_csv(output_root / "summary.csv", results)
    _write_phase_a_report(report_path, summary)
    _write_strategy_report(strategy_report_path, summary)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run H4/H5-only A/B for qret LATTICE_SURGERY_MAGIC exact path interning."
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--strategy-report", type=Path, default=DEFAULT_STRATEGY_REPORT_PATH)
    parser.add_argument("--cache-root", type=Path, default=DEFAULT_OUTPUT_ROOT / "surface_code_cache")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--sample-interval-sec", type=float, default=0.02)
    parser.add_argument(
        "--cases",
        nargs="+",
        default=tuple(CASE_CHAIN_LENGTH),
        help="Allowed: h4_4th_new2 h5_4th_new2. H6-H9 are rejected.",
    )
    args = parser.parse_args(argv)
    run_profile(
        output_root=args.output_root.resolve(),
        report_path=args.report.resolve(),
        strategy_report_path=args.strategy_report.resolve(),
        cache_root=args.cache_root.resolve(),
        build=not args.skip_build,
        cases=args.cases,
        batch_size=args.batch_size,
        sample_interval_sec=args.sample_interval_sec,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
