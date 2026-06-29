#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import platform
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

import profile_qret_pre_routing_high_water as high_water  # noqa: E402
import profile_qret_pre_routing_memory as qret_profile  # noqa: E402
import profile_qret_routing_live_memory as live_profile  # noqa: E402
import profile_surface_code_compact_scaling as compact_profile  # noqa: E402


DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "qret_instruction_arena"
DEFAULT_REPORT_PATH = REPO_ROOT / "docs" / "benchmarks" / "qret_instruction_arena_optimization.md"
PF_LABEL = "4th(new_2)"
COMPILE_MODE = "ftqc_compile_topology"
ONE_MB = 1024 * 1024
H5_PEAK_GATE_KB = 30 * 1024
H5_PEAK_GATE_PERCENT = 7.0
ELAPSED_REGRESSION_GATE_PERCENT = 3.0
MIN_FREE_DISK_BYTES = 5 * 1024**3
MIN_H5_MEM_AVAILABLE_KB = 1_000_000
PROHIBITED_CASE_PREFIXES = ("h6", "h7", "h8", "h9")
PROHIBITED_CHAIN_LENGTHS = {6, 7, 8, 9}

CASE_CHAIN_LENGTH = {
    "h4_4th_new2": 4,
    "h5_4th_new2": 5,
}
VARIANTS = ("legacy", "arena")
DEFAULT_RUNS = {
    "h4_4th_new2": {"legacy": 1, "arena": 1},
    "h5_4th_new2": {"legacy": 2, "arena": 2},
}
SUMMARY_FIELDS = (
    "case",
    "variant",
    "run_index",
    "status",
    "returncode",
    "elapsed_seconds",
    "qret_peak_rss_kb",
    "tree_peak_rss_kb",
    "first_max_vmhwm_stage",
    "max_rss_stage",
    "allocation_count",
    "arena_requested_bytes",
    "arena_used_bytes",
    "arena_reserved_bytes",
    "arena_deallocation_count",
)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(dict(row), ensure_ascii=True, sort_keys=True))
            f.write("\n")


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in SUMMARY_FIELDS})


def _git_output(args: Sequence[str], *, cwd: Path = REPO_ROOT) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def _validate_chain_lengths(chain_lengths: Iterable[int]) -> tuple[int, ...]:
    values = tuple(int(value) for value in chain_lengths)
    prohibited = [value for value in values if value in PROHIBITED_CHAIN_LENGTHS or value > 5]
    if prohibited:
        raise ValueError(
            "H6/H7/H8/H9 chain lengths are prohibited for real qret/Evaluation execution: "
            + ", ".join(str(value) for value in prohibited)
        )
    return values


def _validate_cases(cases: Sequence[str]) -> tuple[str, ...]:
    invalid = [case for case in cases if case not in CASE_CHAIN_LENGTH]
    prohibited = [case for case in invalid if case.lower().startswith(PROHIBITED_CASE_PREFIXES)]
    if prohibited:
        raise ValueError(
            "H6/H7/H8/H9 cases are prohibited for real qret/Evaluation execution: "
            + ", ".join(prohibited)
        )
    if invalid:
        raise ValueError(f"unknown case(s): {', '.join(invalid)}")
    _validate_chain_lengths(CASE_CHAIN_LENGTH[case] for case in cases)
    return tuple(cases)


def _validate_variants(variants: Sequence[str]) -> tuple[str, ...]:
    unknown = [variant for variant in variants if variant not in VARIANTS]
    if unknown:
        raise ValueError(f"unknown variant(s): {', '.join(unknown)}")
    return tuple(variants)


def _architecture() -> sc.SurfaceCodeArchitecture:
    return sc.SurfaceCodeArchitecture(
        compile_mode=COMPILE_MODE,
        skip_compile_output=True,
        compile_info_output_mode="summary",
    )


def _prepare_artifacts(
    cases: Sequence[str],
    *,
    cache_root: Path,
    batch_size: int,
) -> dict[str, sc.SurfaceCodeStepArtifact]:
    return high_water._prepare_artifacts(cases, cache_root=cache_root, batch_size=batch_size)


def _safety_snapshot(path: Path = REPO_ROOT) -> dict[str, Any]:
    return high_water._safety_snapshot(path)


def _validate_h5_safety(snapshot: Mapping[str, Any]) -> None:
    if int(snapshot.get("disk_free_bytes") or 0) < MIN_FREE_DISK_BYTES:
        raise RuntimeError("disk free space is below 5 GiB; H5 run is refused")
    if int(snapshot.get("MemAvailable") or 0) < MIN_H5_MEM_AVAILABLE_KB:
        raise RuntimeError("MemAvailable is below 1,000,000 KB; H5 run is refused")


def _variant_env(env: dict[str, str], variant: str, profile_jsonl: Path) -> None:
    _validate_variants([variant])
    env["QRET_MAGIC_PATH_STORAGE"] = "interned"
    env["QRET_SUMMARY_TIME_SERIES_IMPL"] = "legacy_timeseries"
    env["QRET_DEP_GRAPH_IMPL"] = "compact"
    env["QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING"] = "1"
    env["QRET_INVERSE_MAP_CONSTRUCTION"] = "eager"
    env["QRET_INSTRUCTION_ALLOCATION"] = variant
    env["QRET_RSS_DIAGNOSTIC_TRIM_STAGE"] = "none"
    env["QRET_PROFILE_MAGIC_PATHS"] = "0"
    env["QRET_PROFILE_INVERSE_MAP_USAGE"] = "1"
    env["QRET_PROFILE_HIGH_WATER"] = "1"
    env["QRET_RSS_PROFILE_JSONL"] = str(profile_jsonl)
    env.pop("QRET_MAGIC_PATH_PROFILE_JSON", None)
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    env.pop("LANGUAGE", None)


def _median(values: Iterable[Any]) -> float | int | None:
    present = [value for value in values if value is not None]
    return statistics.median(present) if present else None


def _min(values: Iterable[Any]) -> Any:
    present = [value for value in values if value is not None]
    return min(present) if present else None


def _max(values: Iterable[Any]) -> Any:
    present = [value for value in values if value is not None]
    return max(present) if present else None


def _pct_delta(baseline: Any, candidate: Any) -> float | None:
    if baseline in (None, 0) or candidate is None:
        return None
    return (float(baseline) - float(candidate)) / float(baseline) * 100.0


def _variation_pct(min_value: Any, max_value: Any, median_value: Any) -> float | None:
    if min_value is None or max_value is None or median_value in (None, 0):
        return None
    return (float(max_value) - float(min_value)) / float(median_value) * 100.0


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


def _fmt_mb(value: Any) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value) / ONE_MB:.1f}"
    except (TypeError, ValueError):
        return str(value)


def _compare_dicts(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    ignored: set[str] | None = None,
) -> dict[str, Any]:
    ignored = ignored or set()
    keys = (set(left) | set(right)) - ignored
    mismatches = [key for key in sorted(keys) if left.get(key) != right.get(key)]
    return {"all_equal": not mismatches, "mismatches": mismatches, "ignored_fields": sorted(ignored)}


def _rows(results: Sequence[Mapping[str, Any]], *, case: str, variant: str) -> list[Mapping[str, Any]]:
    return [row for row in results if row.get("case") == case and row.get("variant") == variant]


def _first_result(results: Sequence[Mapping[str, Any]], *, case: str, variant: str) -> Mapping[str, Any]:
    rows = _rows(results, case=case, variant=variant)
    return rows[0] if rows else {}


def _extra_rows(profile_rows: Sequence[Mapping[str, Any]]) -> Iterable[Mapping[str, Any]]:
    for row in profile_rows:
        extra = row.get("extra")
        if isinstance(extra, Mapping):
            yield extra


def _arena_stats(profile_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    best: Mapping[str, Any] = {}
    for extra in _extra_rows(profile_rows):
        if extra.get("machine_instruction_arena_allocation_count") is None:
            continue
        if int(extra.get("machine_instruction_arena_allocation_count") or 0) >= int(
            best.get("machine_instruction_arena_allocation_count") or -1
        ):
            best = extra
    fields = {
        "allocation_mode": "machine_instruction_allocation_mode",
        "arena_enabled": "machine_instruction_arena_enabled",
        "allocation_count": "machine_instruction_arena_allocation_count",
        "deallocation_count": "machine_instruction_arena_deallocation_count",
        "live_allocations": "machine_instruction_arena_live_allocations",
        "requested_bytes": "machine_instruction_arena_requested_bytes",
        "used_bytes": "machine_instruction_arena_used_bytes",
        "reserved_bytes": "machine_instruction_arena_reserved_bytes",
        "internal_fragmentation_bytes": "machine_instruction_arena_internal_fragmentation_bytes",
        "reserved_unused_bytes": "machine_instruction_arena_reserved_unused_bytes",
        "chunk_count": "machine_instruction_arena_chunk_count",
        "legacy_metadata_model_bytes": "machine_instruction_legacy_allocator_metadata_model_bytes",
    }
    return {out_key: best.get(in_key) for out_key, in_key in fields.items()}


def _pass_elapsed_ms(profile_rows: Sequence[Mapping[str, Any]], pass_argument: str) -> int | None:
    values: list[int] = []
    for row in profile_rows:
        extra = row.get("extra")
        if (
            row.get("stage") == "mf_pass_after"
            and isinstance(extra, Mapping)
            and extra.get("pass_argument") == pass_argument
            and extra.get("elapsed_ms") is not None
        ):
            values.append(int(extra["elapsed_ms"]))
    return sum(values) if values else None


def _construction_elapsed_ms(profile_rows: Sequence[Mapping[str, Any]]) -> int | None:
    for row in profile_rows:
        if row.get("stage") == "after_machine_function_construction":
            extra = row.get("extra")
            if isinstance(extra, Mapping) and extra.get("machine_function_construction_elapsed_ms") is not None:
                return int(extra["machine_function_construction_elapsed_ms"])
    return None


def _metric_comparisons(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    comparisons: dict[str, Any] = {}
    for case in CASE_CHAIN_LENGTH:
        baseline = _first_result(results, case=case, variant="legacy")
        if not baseline:
            continue
        for row in results:
            if row.get("case") != case:
                continue
            key = f"{case}:{row.get('variant')}:run_{row.get('run_index')}"
            comparisons[key] = {
                "raw": _compare_dicts(
                    baseline.get("raw_resource_metrics", {}),
                    row.get("raw_resource_metrics", {}),
                ),
                "normalized": _compare_dicts(
                    baseline.get("normalized_metrics", {}),
                    row.get("normalized_metrics", {}),
                    ignored={"compile_info_json", "execution_time_sec"},
                ),
            }
    return comparisons


def _semantic_projection(result: Mapping[str, Any]) -> dict[str, Any]:
    rows = result.get("profile_rows", [])
    extra = {}
    for row in reversed(rows if isinstance(rows, Sequence) else []):
        maybe = row.get("extra") if isinstance(row, Mapping) else None
        if isinstance(maybe, Mapping) and maybe.get("machine_instruction_type_count") is not None:
            extra = maybe
            break
    raw = result.get("raw_resource_metrics", {})
    return {
        "instruction_count": extra.get("machine_instructions"),
        "opcode_counts": extra.get("machine_instruction_type_count"),
        "gate_count": raw.get("gate_count") if isinstance(raw, Mapping) else None,
        "gate_depth": raw.get("gate_depth") if isinstance(raw, Mapping) else None,
        "magic_state_consumption_count": raw.get("magic_state_consumption_count")
        if isinstance(raw, Mapping)
        else None,
        "magic_state_consumption_depth": raw.get("magic_state_consumption_depth")
        if isinstance(raw, Mapping)
        else None,
        "runtime": raw.get("runtime") if isinstance(raw, Mapping) else None,
        "qubit_volume": raw.get("qubit_volume") if isinstance(raw, Mapping) else None,
        "num_physical_qubits": raw.get("num_physical_qubits") if isinstance(raw, Mapping) else None,
        "code_distance": raw.get("code_distance") if isinstance(raw, Mapping) else None,
        "depgraph_nodes": result.get("depgraph_nodes"),
        "depgraph_edges": result.get("depgraph_edges"),
        "pipeline_state_output_skipped": result.get("pipeline_state_output_skipped"),
    }


def _semantic_comparisons(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    comparisons: dict[str, Any] = {}
    for case in CASE_CHAIN_LENGTH:
        baseline = _first_result(results, case=case, variant="legacy")
        if not baseline:
            continue
        base_projection = _semantic_projection(baseline)
        for row in results:
            if row.get("case") != case:
                continue
            key = f"{case}:{row.get('variant')}:run_{row.get('run_index')}"
            comparisons[key] = _compare_dicts(base_projection, _semantic_projection(row))
    return comparisons


def _aggregate(results: Sequence[Mapping[str, Any]], *, case: str, variant: str) -> dict[str, Any]:
    rows = _rows(results, case=case, variant=variant)
    peak_values = [row.get("qret_peak_rss_kb") for row in rows]
    elapsed_values = [row.get("elapsed_seconds") for row in rows]
    tree_values = [row.get("tree_peak_rss_kb") for row in rows]
    return {
        "case": case,
        "variant": variant,
        "runs": len(rows),
        "median_qret_peak_rss_kb": _median(peak_values),
        "min_qret_peak_rss_kb": _min(peak_values),
        "max_qret_peak_rss_kb": _max(peak_values),
        "qret_peak_variation_pct": _variation_pct(_min(peak_values), _max(peak_values), _median(peak_values)),
        "median_tree_peak_rss_kb": _median(tree_values),
        "median_elapsed_seconds": _median(elapsed_values),
        "min_elapsed_seconds": _min(elapsed_values),
        "max_elapsed_seconds": _max(elapsed_values),
        "elapsed_variation_pct": _variation_pct(_min(elapsed_values), _max(elapsed_values), _median(elapsed_values)),
        "median_construction_elapsed_ms": _median(row.get("machine_function_construction_elapsed_ms") for row in rows),
        "median_routing_elapsed_ms": _median(row.get("routing_elapsed_ms") for row in rows),
        "median_compile_info_elapsed_ms": _median(row.get("compile_info_elapsed_ms") for row in rows),
        "median_arena_requested_bytes": _median(row.get("arena_requested_bytes") for row in rows),
        "median_arena_used_bytes": _median(row.get("arena_used_bytes") for row in rows),
        "median_arena_reserved_bytes": _median(row.get("arena_reserved_bytes") for row in rows),
        "median_allocation_count": _median(row.get("allocation_count") for row in rows),
    }


def _gate_decision(
    results: Sequence[Mapping[str, Any]],
    comparisons: Mapping[str, Any],
    semantic_comparisons: Mapping[str, Any],
) -> dict[str, Any]:
    h5_legacy = _aggregate(results, case="h5_4th_new2", variant="legacy")
    h5_arena = _aggregate(results, case="h5_4th_new2", variant="arena")
    peak_legacy = h5_legacy.get("median_qret_peak_rss_kb")
    peak_arena = h5_arena.get("median_qret_peak_rss_kb")
    elapsed_legacy = h5_legacy.get("median_elapsed_seconds")
    elapsed_arena = h5_arena.get("median_elapsed_seconds")
    peak_reduction_kb = None if peak_legacy is None or peak_arena is None else int(peak_legacy) - int(peak_arena)
    peak_reduction_pct = _pct_delta(peak_legacy, peak_arena)
    elapsed_regression_pct = None
    if elapsed_legacy not in (None, 0) and elapsed_arena is not None:
        elapsed_regression_pct = (float(elapsed_arena) - float(elapsed_legacy)) / float(elapsed_legacy) * 100.0
    all_metrics_equal = all(
        item.get("raw", {}).get("all_equal") and item.get("normalized", {}).get("all_equal")
        for item in comparisons.values()
    )
    all_semantic_equal = all(item.get("all_equal") for item in semantic_comparisons.values())
    legacy_peaks = [int(row["qret_peak_rss_kb"]) for row in _rows(results, case="h5_4th_new2", variant="legacy")]
    arena_peaks = [int(row["qret_peak_rss_kb"]) for row in _rows(results, case="h5_4th_new2", variant="arena")]
    every_arena_below_legacy_range = bool(
        legacy_peaks and arena_peaks and max(arena_peaks) < min(legacy_peaks)
    )
    peak_gate = (
        peak_reduction_kb is not None
        and peak_reduction_pct is not None
        and (peak_reduction_kb >= H5_PEAK_GATE_KB or peak_reduction_pct >= H5_PEAK_GATE_PERCENT)
    )
    elapsed_gate = elapsed_regression_pct is not None and elapsed_regression_pct <= ELAPSED_REGRESSION_GATE_PERCENT
    adopted = all_metrics_equal and all_semantic_equal and every_arena_below_legacy_range and peak_gate and elapsed_gate
    return {
        "arena_status": "adopted" if adopted else "rejected",
        "production_default": "arena" if adopted else "legacy",
        "all_metrics_equal": all_metrics_equal,
        "all_semantic_equal": all_semantic_equal,
        "every_arena_run_below_legacy_range": every_arena_below_legacy_range,
        "peak_reduction_kb": peak_reduction_kb,
        "peak_reduction_pct": peak_reduction_pct,
        "elapsed_regression_pct": elapsed_regression_pct,
        "peak_gate": peak_gate,
        "elapsed_gate": elapsed_gate,
        "h5_legacy": h5_legacy,
        "h5_arena": h5_arena,
    }


def _case_parity_passed(
    *,
    case: str,
    comparisons: Mapping[str, Any],
    semantic_comparisons: Mapping[str, Any],
) -> bool:
    prefix = f"{case}:"
    selected = {
        key: value for key, value in comparisons.items()
        if key.startswith(prefix)
    }
    selected_semantic = {
        key: value for key, value in semantic_comparisons.items()
        if key.startswith(prefix)
    }
    return bool(selected) and all(
        item.get("raw", {}).get("all_equal")
        and item.get("normalized", {}).get("all_equal")
        for item in selected.values()
    ) and all(item.get("all_equal") for item in selected_semantic.values())


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
    architecture = _architecture()
    run_dir = output_root / case_key / variant / f"run_{run_index:02d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    profile_jsonl = run_dir / "qret_rss_profile.jsonl"
    samples_jsonl = run_dir / "process_tree_samples.jsonl"
    compile_yaml_path = run_dir / "compile.yaml"
    compile_info_path = run_dir / "compile_info.json"
    stdout_path = run_dir / "stdout.txt"
    stderr_path = run_dir / "stderr.txt"
    for path in (profile_jsonl, samples_jsonl, compile_info_path, stdout_path, stderr_path):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    compile_yaml_path.write_text(
        sc.compile_pipeline_yaml(
            opt_path=artifact.optimized_ir_path,
            compile_output_path=Path(os.devnull),
            compile_info_path=compile_info_path,
            architecture=architecture,
        ),
        encoding="utf-8",
    )
    qret_path = Path(architecture.qret_path).expanduser().resolve()
    before_hashes = live_profile._runtime_hashes(qret_path)
    live_profile._ensure_runtime_hash_stable(expected_runtime_hashes, before_hashes)
    env = os.environ.copy()
    _variant_env(env, variant, profile_jsonl)
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
    sample_rows = high_water._BoundedSampleRows(high_water.MAX_PROCESS_TREE_SAMPLE_ROWS)
    stop_event = threading.Event()
    guard: dict[str, Any] = {"triggered": False}
    sampler = threading.Thread(
        target=compact_profile._sample_process_tree_with_system,
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
    after_hashes = live_profile._runtime_hashes(qret_path)
    live_profile._ensure_runtime_hash_stable(before_hashes, after_hashes)
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    _write_jsonl(samples_jsonl, sample_rows)

    profile_rows = qret_profile._load_jsonl(profile_jsonl) if profile_jsonl.exists() else []
    sample_summary = compact_profile._summarize_samples(sample_rows, parent_pid=process.pid)
    sample_summary.update(sample_rows.retention_summary())
    gnu_maxrss = qret_profile._parse_gnu_time_maxrss(stderr)
    max_stage = live_profile._profile_max_stage(profile_rows)
    dep_extra = live_profile._dep_graph_extra(profile_rows)
    arena = _arena_stats(profile_rows)
    result: dict[str, Any] = {
        "case": case_key,
        "variant": variant,
        "run_index": run_index,
        "status": "ok" if process.returncode == 0 else "failed",
        "returncode": int(process.returncode),
        "elapsed_seconds": elapsed,
        "runtime_hashes_before": before_hashes,
        "runtime_hashes_after": after_hashes,
        "gnu_time_maxrss_kb": gnu_maxrss,
        "qret_peak_rss_kb": live_profile._max_present(
            gnu_maxrss,
            sample_summary.get("sampled_peak_qret_vmrss_kb"),
        ),
        "tree_peak_rss_kb": sample_summary.get("sampled_peak_tree_vmrss_kb"),
        "sample_summary": sample_summary,
        "guard": guard,
        "profile_rows": profile_rows,
        "stage_timeline": high_water._stage_timeline(profile_rows),
        "stage_memory_table": live_profile._stage_memory_table(profile_rows),
        "object_estimates": high_water._object_estimates(profile_rows),
        "max_rss_stage": max_stage.get("stage"),
        "max_rss_stage_vmrss_kb": max_stage.get("vmrss_kb"),
        "first_max_vmhwm_stage": high_water._first_peak_stage(profile_rows, "vmhwm_kb").get("stage"),
        "first_max_vmhwm_kb": high_water._first_peak_stage(profile_rows, "vmhwm_kb").get("value_kb"),
        "first_max_vmrss_stage": high_water._first_peak_stage(profile_rows, "vmrss_kb").get("stage"),
        "first_max_vmrss_kb": high_water._first_peak_stage(profile_rows, "vmrss_kb").get("value_kb"),
        "depgraph_implementation_marker": dep_extra.get("dep_graph_implementation"),
        "depgraph_nodes": dep_extra.get("dep_graph_nodes"),
        "depgraph_edges": dep_extra.get("dep_graph_edges"),
        "depgraph_payload_bytes": high_water._dep_graph_payload_bytes(dep_extra),
        "pipeline_state_output_skipped": any(
            row.get("stage") == "pipeline_state_output_skipped" for row in profile_rows
        ),
        "compile_info_path": str(compile_info_path),
        "compile_info_size_bytes": compile_info_path.stat().st_size if compile_info_path.exists() else None,
        "profile_jsonl": str(profile_jsonl),
        "samples_jsonl": str(samples_jsonl),
        "pipeline_path": str(compile_yaml_path),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "normalized_metrics": live_profile._metric_summary(compile_info_path),
        "raw_resource_metrics": live_profile._raw_resource_metrics(compile_info_path),
        "artifact": compact_profile._artifact_summary(artifact),
        "machine_function_construction_elapsed_ms": _construction_elapsed_ms(profile_rows),
        "routing_elapsed_ms": _pass_elapsed_ms(profile_rows, "sc_ls_fixed_v0::routing"),
        "compile_info_elapsed_ms": sum(
            value
            for value in (
                _pass_elapsed_ms(profile_rows, "sc_ls_fixed_v0::calc_info_without_topology"),
                _pass_elapsed_ms(profile_rows, "sc_ls_fixed_v0::calc_info_with_topology"),
                _pass_elapsed_ms(profile_rows, "sc_ls_fixed_v0::dump_compile_info"),
            )
            if value is not None
        ),
        "arena_stats": arena,
        "allocation_count": arena.get("allocation_count"),
        "arena_requested_bytes": arena.get("requested_bytes"),
        "arena_used_bytes": arena.get("used_bytes"),
        "arena_reserved_bytes": arena.get("reserved_bytes"),
        "arena_deallocation_count": arena.get("deallocation_count"),
    }
    result["machine_components"] = high_water._machine_component_summary(result)
    result["semantic_projection"] = _semantic_projection(result)
    result["missing_requested_stages"] = [
        row["logical_stage"] for row in result["stage_timeline"] if not row["present"]
    ]
    _write_json(run_dir / "summary.json", result)
    if process.returncode != 0:
        raise RuntimeError(f"qret failed for {case_key} {variant}: {stderr[-4000:]}")
    return result


def _write_report(path: Path, *, summary: Mapping[str, Any]) -> None:
    results = summary.get("results", [])
    comparisons = summary.get("comparisons", {})
    semantic_comparisons = summary.get("semantic_comparisons", {})
    decision = summary.get("decision", {})
    h5_legacy = decision.get("h5_legacy", {})
    h5_arena = decision.get("h5_arena", {})
    h5_legacy_first = _first_result(results, case="h5_4th_new2", variant="legacy")
    h5_arena_first = _first_result(results, case="h5_4th_new2", variant="arena")
    lines = [
        "# qret Instruction Arena Allocation Evaluation",
        "",
        "## Execution Limits",
        "",
        "- largest measured case: `H5`",
        "- H6 executed: `False`",
        "- H7 executed: `False`",
        "- H8 executed: `False`",
        "- H9 executed: `False`",
        "- H9 memory: not measured in Phase A.",
        "",
        "## Production Configuration",
        "",
        "- production default after Phase A: `" + str(decision.get("production_default")) + "`",
        "- candidate switch: `QRET_INSTRUCTION_ALLOCATION=legacy|arena`",
        "- magic path storage: `interned`",
        "- non-path operands: legacy containers",
        "- compile-info output: `summary`",
        "- summary TimeSeries: `legacy_timeseries`",
        "- DepGraph: `compact`",
        "- inverse-map construction: default `eager`",
        "- inverse-map release after routing: enabled",
        "- pipeline-state output: skipped",
        "",
        "## Source Audit",
        "",
        "- SC_LS_FIXED_V0 has 24 concrete instruction enum values and all concrete instruction factories return `std::unique_ptr<Derived>(new Derived(...))`.",
        "- `FromJson` delegates to those factories, so deserialization and pipeline-state load use the same allocation path.",
        "- `MachineBasicBlock` remains `std::list<std::unique_ptr<MachineInstruction>>`; list-node storage, iterator stability, and ownership semantics are unchanged.",
        "- `InsertBefore`, `InsertAfter`, `EmplaceBack`, and `Erase` still move or destroy `unique_ptr` nodes; arena mode changes only the object allocation backing `new Derived(...)`.",
        "- Virtual dispatch, `dynamic_cast`/`Cast` style use, instruction classes, operands, metadata, serialization, and routing algorithms are unchanged.",
        "- Arena ownership is MachineFunction-scoped. Routing allocations occur under the same compile-scope arena, and chunks are freed when the MachineFunction is destroyed.",
        "- Erased instructions still run their destructor through `unique_ptr`; arena `operator delete` records the delete and defers raw memory reuse until MachineFunction teardown.",
        "- Arena mode cannot remove object bodies, vptrs, padding, operand containers, or instruction list nodes.",
        "",
        "## Allocation Model",
        "",
        "| item | value | classification |",
        "| ---- | ----: | -------------- |",
    ]
    arena_stats = h5_arena_first.get("arena_stats", {}) if isinstance(h5_arena_first, Mapping) else {}
    legacy_stats = h5_legacy_first.get("arena_stats", {}) if isinstance(h5_legacy_first, Mapping) else {}
    lines.extend(
        [
            f"| H5 legacy allocation count model | {_fmt_int(legacy_stats.get('legacy_metadata_model_bytes'))} bytes | theoretical |",
            f"| H5 arena allocation count | {_fmt_int(arena_stats.get('allocation_count'))} | observed |",
            f"| H5 arena requested bytes | {_fmt_int(arena_stats.get('requested_bytes'))} | observed |",
            f"| H5 arena used bytes | {_fmt_int(arena_stats.get('used_bytes'))} | observed |",
            f"| H5 arena reserved bytes | {_fmt_int(arena_stats.get('reserved_bytes'))} | observed |",
            f"| H5 arena internal fragmentation bytes | {_fmt_int(arena_stats.get('internal_fragmentation_bytes'))} | observed |",
            f"| H5 arena chunks | {_fmt_int(arena_stats.get('chunk_count'))} | observed |",
            "",
            "## H4 Correctness",
            "",
            f"- raw and normalized metric parity: `{decision.get('all_metrics_equal')}`",
            f"- semantic projection parity: `{decision.get('all_semantic_equal')}`",
            "- canonical instruction stream hash was not emitted by the production qret binary; opcode counts, instruction count, raw metrics, normalized metrics, DepGraph counts, schema, and pipeline-state skip marker were compared instead.",
            "",
            "## H5 A/B Results",
            "",
            "| variant | runs | median qret peak KB | min | max | peak variation % | median elapsed s | elapsed variation % | median construction ms | median routing ms | median compile-info ms |",
            "| ------- | ---: | -------------------: | --: | --: | ---------------: | ---------------: | ------------------: | ---------------------: | ----------------: | ---------------------: |",
        ]
    )
    for row in (h5_legacy, h5_arena):
        lines.append(
            f"| {row.get('variant')} | {_fmt_int(row.get('runs'))} | "
            f"{_fmt_int(row.get('median_qret_peak_rss_kb'))} | "
            f"{_fmt_int(row.get('min_qret_peak_rss_kb'))} | "
            f"{_fmt_int(row.get('max_qret_peak_rss_kb'))} | "
            f"{_fmt_float(row.get('qret_peak_variation_pct'))} | "
            f"{_fmt_float(row.get('median_elapsed_seconds'))} | "
            f"{_fmt_float(row.get('elapsed_variation_pct'))} | "
            f"{_fmt_int(row.get('median_construction_elapsed_ms'))} | "
            f"{_fmt_int(row.get('median_routing_elapsed_ms'))} | "
            f"{_fmt_int(row.get('median_compile_info_elapsed_ms'))} |"
        )
    lines.extend(
        [
            "",
            "## Gate Decision",
            "",
            f"- arena status: `{decision.get('arena_status')}`",
            f"- H5 median peak reduction KB: `{_fmt_int(decision.get('peak_reduction_kb'))}`",
            f"- H5 median peak reduction %: `{_fmt_float(decision.get('peak_reduction_pct'))}`",
            f"- elapsed regression %: `{_fmt_float(decision.get('elapsed_regression_pct'))}`",
            f"- every arena run below legacy range: `{decision.get('every_arena_run_below_legacy_range')}`",
            f"- peak gate passed: `{decision.get('peak_gate')}`",
            f"- elapsed gate passed: `{decision.get('elapsed_gate')}`",
            "",
            "## Metric Parity Details",
            "",
            "| comparison | raw equal | normalized equal | semantic projection equal |",
            "| ---------- | --------- | ---------------- | ------------------------- |",
        ]
    )
    for key in sorted(comparisons):
        lines.append(
            f"| {key} | {comparisons[key].get('raw', {}).get('all_equal')} | "
            f"{comparisons[key].get('normalized', {}).get('all_equal')} | "
            f"{semantic_comparisons.get(key, {}).get('all_equal')} |"
        )
    lines.extend(
        [
            "",
            "## Conclusion",
            "",
            "- Phase A evaluated exactly one instruction-storage candidate: MachineFunction-scoped instruction arena allocation.",
            "- It did not implement instruction list-node removal, operand API redesign, inverse-map compactization, instruction-count reduction, flat/tagged instruction representation, or chunk/stream routing.",
            "- Production default changes only if the gate passes; otherwise `legacy` remains the default and `arena` remains an explicit candidate mode.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_profile(
    *,
    output_root: Path,
    report_path: Path,
    cache_root: Path,
    build: bool,
    cases: Sequence[str],
    variants: Mapping[str, Sequence[str]] | None,
    batch_size: int,
    sample_interval_sec: float,
) -> dict[str, Any]:
    cases = _validate_cases(cases)
    if "h5_4th_new2" in cases and "h4_4th_new2" not in cases:
        raise ValueError("H5 measurement requires H4 legacy/arena parity in the same run")
    if live_profile._disk_free_bytes(REPO_ROOT) < MIN_FREE_DISK_BYTES:
        raise RuntimeError("disk free space is below 5 GiB")
    output_root.mkdir(parents=True, exist_ok=True)
    architecture = _architecture()
    qret_path = Path(architecture.qret_path).expanduser().resolve()
    build_provenance = live_profile._build_qret_and_record(qret_path, build=build)
    runtime_hashes = live_profile._runtime_hashes(qret_path)
    meminfo_start = live_profile._meminfo()
    environment = {
        "evaluation_head": _git_output(["rev-parse", "HEAD"]),
        "measurement_runtime_hashes": runtime_hashes,
        "platform": platform.platform(),
        "python": sys.version,
        "compiler": live_profile._compiler_version(),
        "allocator": "glibc malloc/mallinfo2 when mallinfo2_supported=true",
        "meminfo": meminfo_start,
        "disk_free_bytes": live_profile._disk_free_bytes(REPO_ROOT),
        "batch_size": batch_size,
        "sample_interval_sec": sample_interval_sec,
        "output_root": str(output_root.resolve()),
    }
    artifacts = _prepare_artifacts(cases, cache_root=cache_root, batch_size=batch_size)
    environment["artifacts"] = {
        case: compact_profile._artifact_summary(artifact) for case, artifact in artifacts.items()
    }
    results: list[dict[str, Any]] = []
    memtotal_kb = meminfo_start.get("MemTotal")
    for case in cases:
        selected_variants = tuple(variants[case]) if variants and case in variants else tuple(DEFAULT_RUNS[case])
        _validate_variants(selected_variants)
        for variant in selected_variants:
            count = DEFAULT_RUNS.get(case, {}).get(variant, 1)
            for run_index in range(1, count + 1):
                if case == "h5_4th_new2":
                    _validate_h5_safety(_safety_snapshot(REPO_ROOT))
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
                _write_json(output_root / "summary.json", {"environment": environment, "results": results})
        if case == "h4_4th_new2" and "h5_4th_new2" in cases:
            comparisons = _metric_comparisons(results)
            semantic_comparisons = _semantic_comparisons(results)
            if not _case_parity_passed(
                case="h4_4th_new2",
                comparisons=comparisons,
                semantic_comparisons=semantic_comparisons,
            ):
                summary = {
                    "environment": environment,
                    "build_provenance": build_provenance,
                    "results": results,
                    "comparisons": comparisons,
                    "semantic_comparisons": semantic_comparisons,
                    "execution_limits": {
                        "largest_measured_case": "H4",
                        "h6_executed": False,
                        "h7_executed": False,
                        "h8_executed": False,
                        "h9_executed": False,
                    },
                }
                _write_json(output_root / "summary.json", summary)
                _write_report(report_path, summary=summary)
                raise RuntimeError("H4 parity failed; refusing H5 instruction arena measurement")
    comparisons = _metric_comparisons(results)
    semantic_comparisons = _semantic_comparisons(results)
    summary = {
        "environment": environment,
        "build_provenance": build_provenance,
        "results": results,
        "aggregates": {
            f"{case}:{variant}": _aggregate(results, case=case, variant=variant)
            for case in cases
            for variant in VARIANTS
        },
        "comparisons": comparisons,
        "semantic_comparisons": semantic_comparisons,
        "decision": _gate_decision(results, comparisons, semantic_comparisons),
        "execution_limits": {
            "largest_measured_case": "H5" if "h5_4th_new2" in cases else "H4",
            "h6_executed": False,
            "h7_executed": False,
            "h8_executed": False,
            "h9_executed": False,
        },
    }
    _write_json(output_root / "summary.json", summary)
    _write_report(report_path, summary=summary)
    return summary


def _parse_case_variant(values: Sequence[str] | None) -> dict[str, list[str]] | None:
    if not values:
        return None
    ret: dict[str, list[str]] = {}
    for value in values:
        case, sep, variant = value.partition(":")
        if not sep:
            raise ValueError("--case-variant must be CASE:VARIANT")
        _validate_cases([case])
        _validate_variants([variant])
        ret.setdefault(case, []).append(variant)
    return ret


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate qret instruction arena allocation.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--cache-root", type=Path, default=sc.SURFACE_CODE_CACHE_DIR)
    parser.add_argument("--case", action="append", choices=tuple(CASE_CHAIN_LENGTH), help="Case to run. Default: H4 and H5.")
    parser.add_argument("--case-variant", action="append", help="Restrict variants as CASE:VARIANT. Can be repeated.")
    parser.add_argument("--batch-size", type=int, default=sc.SURFACE_CODE_RZ_HELPER_BATCH_SIZE)
    parser.add_argument("--sample-interval-sec", type=float, default=0.02)
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args(argv)
    run_profile(
        output_root=args.output_root,
        report_path=args.report,
        cache_root=args.cache_root,
        build=bool(args.build),
        cases=tuple(args.case) if args.case else tuple(CASE_CHAIN_LENGTH),
        variants=_parse_case_variant(args.case_variant),
        batch_size=int(args.batch_size),
        sample_interval_sec=float(args.sample_interval_sec),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
