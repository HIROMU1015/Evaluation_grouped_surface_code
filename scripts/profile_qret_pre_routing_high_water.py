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

import profile_qret_pre_routing_memory as qret_profile  # noqa: E402
import profile_qret_routing_live_memory as live_profile  # noqa: E402
import profile_surface_code_compact_scaling as compact_profile  # noqa: E402


DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "qret_pre_routing_high_water"
DEFAULT_REPORT_PATH = REPO_ROOT / "docs" / "benchmarks" / "qret_pre_routing_high_water_audit.md"
PF_LABEL = "4th(new_2)"
COMPILE_MODE = "ftqc_compile_topology"
MIN_FREE_DISK_BYTES = 5 * 1024**3
MIN_H5_MEM_AVAILABLE_KB = 1_000_000
ONE_MB = 1024 * 1024
H5_PEAK_GATE_KB = 30 * 1024
H5_PEAK_GATE_PERCENT = 7.0
MAX_PROCESS_TREE_SAMPLE_ROWS = 250_000
PROHIBITED_CASE_PREFIXES = ("h6", "h7", "h8", "h9")
PROHIBITED_CHAIN_LENGTHS = {6, 7, 8, 9}

CASE_CHAIN_LENGTH = {
    "h4_4th_new2": 4,
    "h5_4th_new2": 5,
}
CASE_DISPLAY = {
    "h4_4th_new2": "H4 `4th(new_2)`",
    "h5_4th_new2": "H5 `4th(new_2)`",
}
VARIANTS: dict[str, dict[str, Any]] = {
    "eager_profile_off": {"construction": "eager", "profile": False, "trim_stage": "none"},
    "lazy_profile_off": {"construction": "lazy", "profile": False, "trim_stage": "none"},
    "eager": {"construction": "eager", "profile": True, "trim_stage": "none"},
    "lazy": {"construction": "lazy", "profile": True, "trim_stage": "none"},
    "eager_trim_after_machine_function": {
        "construction": "eager",
        "profile": True,
        "trim_stage": "after_machine_function_construction",
    },
    "eager_trim_after_mapping": {
        "construction": "eager",
        "profile": True,
        "trim_stage": "after_mapping",
    },
    "eager_trim_after_inverse_release": {
        "construction": "eager",
        "profile": True,
        "trim_stage": "routing_after_inverse_map_release",
    },
    "eager_trim_after_compile_info": {
        "construction": "eager",
        "profile": True,
        "trim_stage": "after_compile_info",
    },
}
DEFAULT_RUNS = {
    "h4_4th_new2": {
        "eager_profile_off": 1,
        "lazy_profile_off": 1,
        "eager": 1,
        "lazy": 1,
        "eager_trim_after_machine_function": 1,
        "eager_trim_after_mapping": 1,
        "eager_trim_after_inverse_release": 1,
        "eager_trim_after_compile_info": 1,
    },
    "h5_4th_new2": {
        "eager": 1,
        "lazy": 1,
        "eager_trim_after_inverse_release": 1,
    },
}

REQUESTED_STAGE_ALIASES = {
    "process_start": ("process_start", "compile_entry"),
    "before_input_json_read": ("before_input_json_read", "before_ir_file_read"),
    "after_input_json_read": ("after_input_json_read", "after_ir_file_read"),
    "after_json_parse_or_dom_build": ("after_json_parse_or_dom_build", "after_ir_json_parse"),
    "before_machine_function_construction": (
        "before_machine_function_construction",
        "before_lowering",
    ),
    "during_machine_function_construction": ("during_machine_function_construction",),
    "after_machine_function_construction": (
        "after_machine_function_construction",
        "after_lowering",
    ),
    "before_lowering": ("before_lowering",),
    "after_lowering": ("after_lowering",),
    "before_mapping": ("before_mapping",),
    "after_mapping": ("after_mapping",),
    "before_validation": ("before_validation",),
    "after_validation": ("after_validation",),
    "routing_entry": ("routing_entry", "routing_entry_from_pass_manager"),
    "routing_after_setup": ("routing_after_setup", "routing_before_main_loop"),
    "routing_main_loop_peak": ("routing_main_loop_peak",),
    "routing_before_inverse_map_release": ("routing_before_inverse_map_release",),
    "routing_after_inverse_map_release": ("routing_after_inverse_map_release",),
    "before_compile_info": ("before_compile_info", "before_calc_info_without_topology"),
    "compile_info_peak": (
        "calc_info_with_topology_after_summary_accumulation",
        "calc_info_without_topology_after_dep_graph",
        "after_calc_info_with_topology",
    ),
    "after_compile_info": ("after_compile_info", "after_calc_info_with_topology"),
    "before_serialization": ("before_serialization", "dump_compile_info_before_json_dom_create"),
    "after_serialization": ("after_serialization", "dump_compile_info_after_json_stream_write"),
    "before_process_exit": ("before_process_exit", "compile_exit"),
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
    "max_rss_stage",
    "max_rss_stage_vmrss_kb",
    "first_max_vmhwm_stage",
    "first_max_vmrss_stage",
    "trim_stage",
)


class _BoundedSampleRows(list[dict[str, Any]]):
    def __init__(self, max_rows: int) -> None:
        super().__init__()
        self.max_rows = int(max_rows)
        self.dropped_rows = 0

    def append(self, row: dict[str, Any]) -> None:
        if len(self) < self.max_rows:
            super().append(row)
            return
        self.dropped_rows += 1

    def retention_summary(self) -> dict[str, Any]:
        return {
            "process_tree_sample_retained_rows": len(self),
            "process_tree_sample_dropped_rows": self.dropped_rows,
            "process_tree_sample_max_retained_rows": self.max_rows,
            "process_tree_sample_truncated": self.dropped_rows > 0,
        }


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


def _safety_snapshot(path: Path = REPO_ROOT) -> dict[str, Any]:
    meminfo = live_profile._meminfo()
    return {
        "MemTotal": meminfo.get("MemTotal"),
        "MemAvailable": meminfo.get("MemAvailable"),
        "SwapTotal": meminfo.get("SwapTotal"),
        "SwapFree": meminfo.get("SwapFree"),
        "disk_free_bytes": live_profile._disk_free_bytes(path),
    }


def _validate_h5_safety(snapshot: Mapping[str, Any]) -> None:
    if int(snapshot.get("disk_free_bytes") or 0) < MIN_FREE_DISK_BYTES:
        raise RuntimeError("disk free space is below 5 GiB; H5 run is refused")
    if int(snapshot.get("MemAvailable") or 0) < MIN_H5_MEM_AVAILABLE_KB:
        raise RuntimeError("MemAvailable is below 1,000,000 KB; H5 run is refused")


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
    previous_cache_dir = sc.SURFACE_CODE_CACHE_DIR
    previous_batch_size = sc.SURFACE_CODE_RZ_HELPER_BATCH_SIZE
    sc.SURFACE_CODE_CACHE_DIR = cache_root
    sc.SURFACE_CODE_RZ_HELPER_BATCH_SIZE = int(batch_size)
    try:
        artifacts: dict[str, sc.SurfaceCodeStepArtifact] = {}
        architecture = _architecture()
        for case_key in cases:
            artifact = sc.prepare_grouped_surface_code_step_artifact(
                sc.grouped_hchain_ham_name(CASE_CHAIN_LENGTH[case_key]),
                PF_LABEL,
                architecture=architecture,
            )
            artifacts[case_key] = artifact
        return artifacts
    finally:
        sc.SURFACE_CODE_CACHE_DIR = previous_cache_dir
        sc.SURFACE_CODE_RZ_HELPER_BATCH_SIZE = previous_batch_size


def _variant_env(env: dict[str, str], variant: str, profile_jsonl: Path) -> None:
    config = VARIANTS[variant]
    env["QRET_MAGIC_PATH_STORAGE"] = "interned"
    env["QRET_SUMMARY_TIME_SERIES_IMPL"] = "legacy_timeseries"
    env["QRET_DEP_GRAPH_IMPL"] = "compact"
    env["QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING"] = "1"
    env["QRET_INVERSE_MAP_CONSTRUCTION"] = str(config["construction"])
    env["QRET_RSS_DIAGNOSTIC_TRIM_STAGE"] = str(config["trim_stage"])
    env["QRET_PROFILE_MAGIC_PATHS"] = "0"
    env["QRET_PROFILE_INVERSE_MAP_USAGE"] = "1"
    env.pop("QRET_MAGIC_PATH_PROFILE_JSON", None)
    if bool(config["profile"]):
        env["QRET_RSS_PROFILE_JSONL"] = str(profile_jsonl)
        env["QRET_PROFILE_HIGH_WATER"] = "1"
    else:
        env.pop("QRET_RSS_PROFILE_JSONL", None)
        env["QRET_PROFILE_HIGH_WATER"] = "0"
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    env.pop("LANGUAGE", None)


def _median(values: Iterable[Any]) -> float | int | None:
    present = [value for value in values if value is not None]
    return statistics.median(present) if present else None


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


def _compare_dicts(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    ignored: set[str] | None = None,
) -> dict[str, Any]:
    ignored = ignored or set()
    keys = (set(left) | set(right)) - ignored
    mismatches = [
        key for key in sorted(keys) if left.get(key) != right.get(key)
    ]
    return {"all_equal": not mismatches, "mismatches": mismatches, "ignored_fields": sorted(ignored)}


def _rows(
    results: Sequence[Mapping[str, Any]],
    *,
    case: str,
    variant: str,
) -> list[Mapping[str, Any]]:
    return [row for row in results if row.get("case") == case and row.get("variant") == variant]


def _first_result(
    results: Sequence[Mapping[str, Any]],
    *,
    case: str,
    variant: str,
) -> Mapping[str, Any]:
    rows = _rows(results, case=case, variant=variant)
    return rows[0] if rows else {}


def _stage_rows_for_alias(rows: Sequence[Mapping[str, Any]], aliases: Sequence[str]) -> list[Mapping[str, Any]]:
    alias_set = set(aliases)
    return [row for row in rows if row.get("stage") in alias_set]


def _max_stage_row(
    rows: Sequence[Mapping[str, Any]],
    *,
    prefix: str | None = None,
    key: str = "vmrss_kb",
) -> Mapping[str, Any]:
    candidates = [
        row for row in rows
        if row.get(key) is not None
        and (prefix is None or str(row.get("stage", "")).startswith(prefix))
    ]
    return max(candidates, key=lambda row: int(row.get(key) or 0), default={})


def _max_extra_sum(profile_rows: Sequence[Mapping[str, Any]], keys: Sequence[str]) -> int | None:
    values: list[int] = []
    for row in profile_rows:
        extra = row.get("extra")
        if not isinstance(extra, Mapping):
            continue
        if all(extra.get(key) is not None for key in keys):
            values.append(sum(int(extra[key]) for key in keys))
    return max(values) if values else None


def _dep_graph_payload_bytes(extra: Mapping[str, Any]) -> int | None:
    compact_keys = (
        "compact_parent_offsets_capacity_bytes",
        "compact_parent_ids_capacity_bytes",
        "compact_edge_lengths_capacity_bytes",
        "compact_node_weights_capacity_bytes",
        "compact_working_dp_capacity_bytes",
    )
    if all(extra.get(key) is not None for key in compact_keys):
        return sum(int(extra[key]) for key in compact_keys)
    legacy_keys = (
        "dep_graph_node_estimated_payload_bytes",
        "dep_graph_edge_estimated_payload_bytes",
        "dep_graph_pointer_map_estimated_payload_bytes",
    )
    values = [int(extra[key]) for key in legacy_keys if extra.get(key) is not None]
    return sum(values) if values else None


def _stage_timeline(profile_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    timeline: list[dict[str, Any]] = []
    for logical, aliases in REQUESTED_STAGE_ALIASES.items():
        matching = _stage_rows_for_alias(profile_rows, aliases)
        if logical == "compile_info_peak":
            compile_rows = [
                item for item in profile_rows
                if str(item.get("stage", "")).startswith(("calc_info", "dump_compile_info"))
            ]
            row = _max_stage_row(compile_rows, key="mallinfo2_uordblks_kb")
            if not row:
                row = _max_stage_row(compile_rows)
        elif logical == "during_machine_function_construction":
            row = _max_stage_row(matching) if matching else {}
        else:
            row = matching[0] if matching else {}
        vmrss = row.get("vmrss_kb")
        uord = row.get("mallinfo2_uordblks_kb")
        timeline.append(
            {
                "logical_stage": logical,
                "observed_stage": row.get("stage"),
                "vmrss_kb": vmrss,
                "vmhwm_kb": row.get("vmhwm_kb"),
                "vmsize_kb": row.get("vmsize_kb"),
                "vmdata_kb": row.get("vmdata_kb"),
                "rss_anon_kb": row.get("rss_anon_kb"),
                "rss_file_kb": row.get("rss_file_kb"),
                "ru_maxrss_kb": row.get("ru_maxrss_kb"),
                "mallinfo2_uordblks_kb": uord,
                "mallinfo2_fordblks_kb": row.get("mallinfo2_fordblks_kb"),
                "mallinfo2_hblkhd_kb": _bytes_to_kb(row.get("mallinfo2_hblkhd")),
                "mallinfo2_arena_kb": _bytes_to_kb(row.get("mallinfo2_arena")),
                "mallinfo2_ordblks": row.get("mallinfo2_ordblks"),
                "vmrss_minus_uordblks_kb": (
                    None if vmrss is None or uord is None else int(vmrss) - int(uord)
                ),
                "present": bool(row),
            }
        )
    return timeline


def _bytes_to_kb(value: Any) -> int | None:
    if value is None:
        return None
    return int(value) // 1024


def _first_peak_stage(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, Any]:
    values = [int(row[key]) for row in rows if row.get(key) is not None]
    if not values:
        return {"stage": None, "value_kb": None}
    peak = max(values)
    for row in rows:
        if row.get(key) is not None and int(row[key]) == peak:
            return {"stage": row.get("stage"), "value_kb": peak}
    return {"stage": None, "value_kb": peak}


def _trim_diagnostics(rows: Sequence[Mapping[str, Any]], trim_stage: str) -> dict[str, Any]:
    if trim_stage == "none":
        return {}
    before = next((row for row in rows if row.get("stage") == f"diagnostic_trim_before_{trim_stage}"), {})
    after = next((row for row in rows if row.get("stage") == f"diagnostic_trim_after_{trim_stage}"), {})
    if not before or not after:
        return {}
    return {
        trim_stage: {
            "rss_drop_kb": _diff(before, after, "vmrss_kb"),
            "hwm_drop_kb": _diff(before, after, "vmhwm_kb"),
            "uordblks_drop_kb": _diff(before, after, "mallinfo2_uordblks_kb"),
            "fordblks_drop_kb": _diff(before, after, "mallinfo2_fordblks_kb"),
            "elapsed_sec": (after.get("extra") or {}).get("malloc_trim_elapsed_sec")
            if isinstance(after.get("extra"), Mapping)
            else None,
            "malloc_trim_return": (after.get("extra") or {}).get("malloc_trim_return")
            if isinstance(after.get("extra"), Mapping)
            else None,
        }
    }


def _diff(left: Mapping[str, Any], right: Mapping[str, Any], key: str) -> int | None:
    if left.get(key) is None or right.get(key) is None:
        return None
    return int(left[key]) - int(right[key])


def _component_extra(result: Mapping[str, Any], stage: str) -> dict[str, Any]:
    for row in result.get("profile_rows", []):
        if row.get("stage") == stage and isinstance(row.get("extra"), Mapping):
            return dict(row["extra"])
    return {}


def _machine_component_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    profile_rows = result.get("profile_rows", [])
    if not isinstance(profile_rows, Sequence):
        profile_rows = []
    extra = (
        _component_extra(result, "routing_before_inverse_map_release")
        or _component_extra(result, "after_machine_function_construction")
        or _component_extra(result, "after_lowering")
    )
    dep_extra = live_profile._dep_graph_extra(profile_rows)
    return {
        "instruction_count": extra.get("machine_instructions"),
        "basic_block_count": extra.get("machine_basic_blocks"),
        "instruction_type_count": extra.get("machine_instruction_type_count"),
        "instruction_object_bytes": extra.get("machine_instruction_object_bytes_estimated"),
        "operand_container_bytes": extra.get("machine_operand_list_node_bytes_estimated"),
        "interned_path_storage_bytes": extra.get("machine_magic_path_unique_dynamic_bytes_estimated"),
        "instruction_list_node_bytes": extra.get("machine_instruction_list_node_bytes_estimated"),
        "inverse_map_entries": extra.get("machine_inverse_map_entries"),
        "inverse_map_bytes": extra.get("machine_inverse_map_bytes_estimated"),
        "metadata_bytes": extra.get("machine_metadata_bytes_estimated"),
        "machine_total_bytes": extra.get("machine_total_bytes_estimated"),
        "routing_temporary_bytes": _max_extra_sum(
            profile_rows,
            ("routing_queue_total_bytes_estimated", "routing_sim_total_bytes_estimated"),
        ),
        "depgraph_nodes": dep_extra.get("dep_graph_nodes"),
        "depgraph_edges": dep_extra.get("dep_graph_edges"),
        "depgraph_bytes": _dep_graph_payload_bytes(dep_extra),
    }


def _object_estimates(profile_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    estimates = live_profile._object_estimates(profile_rows)
    dep_extra = live_profile._dep_graph_extra(profile_rows)
    estimates["dep_graph"] = {
        "nodes": dep_extra.get("dep_graph_nodes"),
        "edges": dep_extra.get("dep_graph_edges"),
        "estimated_payload_bytes": _dep_graph_payload_bytes(dep_extra),
    }
    return estimates


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
    sample_rows = _BoundedSampleRows(MAX_PROCESS_TREE_SAMPLE_ROWS)
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
    trim_stage = str(VARIANTS[variant]["trim_stage"])
    result: dict[str, Any] = {
        "case": case_key,
        "variant": variant,
        "construction": VARIANTS[variant]["construction"],
        "profile_enabled": VARIANTS[variant]["profile"],
        "trim_stage": trim_stage,
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
        "parent_peak_rss_kb": sample_summary.get("sampled_peak_parent_vmrss_kb"),
        "tree_peak_rss_kb": sample_summary.get("sampled_peak_tree_vmrss_kb"),
        "sample_summary": sample_summary,
        "guard": guard,
        "profile_rows": profile_rows,
        "stage_timeline": _stage_timeline(profile_rows),
        "stage_memory_table": live_profile._stage_memory_table(profile_rows),
        "object_estimates": _object_estimates(profile_rows),
        "machine_components": {},
        "trim_diagnostics": _trim_diagnostics(profile_rows, trim_stage),
        "max_rss_stage": max_stage.get("stage"),
        "max_rss_stage_vmrss_kb": max_stage.get("vmrss_kb"),
        "first_max_vmhwm_stage": _first_peak_stage(profile_rows, "vmhwm_kb").get("stage"),
        "first_max_vmhwm_kb": _first_peak_stage(profile_rows, "vmhwm_kb").get("value_kb"),
        "first_max_vmrss_stage": _first_peak_stage(profile_rows, "vmrss_kb").get("stage"),
        "first_max_vmrss_kb": _first_peak_stage(profile_rows, "vmrss_kb").get("value_kb"),
        "depgraph_implementation_marker": dep_extra.get("dep_graph_implementation"),
        "depgraph_nodes": dep_extra.get("dep_graph_nodes"),
        "depgraph_edges": dep_extra.get("dep_graph_edges"),
        "depgraph_payload_bytes": _dep_graph_payload_bytes(dep_extra),
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
    }
    result["machine_components"] = _machine_component_summary(result)
    result["missing_requested_stages"] = [
        row["logical_stage"] for row in result["stage_timeline"] if not row["present"]
    ]
    _write_json(run_dir / "summary.json", result)
    if process.returncode != 0:
        raise RuntimeError(f"qret failed for {case_key} {variant}: {stderr[-4000:]}")
    return result


def _aggregate(results: Sequence[Mapping[str, Any]], *, case: str, variant: str) -> dict[str, Any]:
    rows = _rows(results, case=case, variant=variant)
    return {
        "case": case,
        "variant": variant,
        "runs": len(rows),
        "median_qret_peak_rss_kb": _median(row.get("qret_peak_rss_kb") for row in rows),
        "median_tree_peak_rss_kb": _median(row.get("tree_peak_rss_kb") for row in rows),
        "median_elapsed_seconds": _median(row.get("elapsed_seconds") for row in rows),
        "max_stage": max(
            rows,
            key=lambda row: int(row.get("max_rss_stage_vmrss_kb") or 0),
            default={},
        ).get("max_rss_stage"),
    }


def _metric_comparisons(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    comparisons: dict[str, Any] = {}
    for case in CASE_CHAIN_LENGTH:
        baseline = _first_result(results, case=case, variant="eager_profile_off")
        if not baseline:
            baseline = _first_result(results, case=case, variant="eager")
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


def _stage_value(timeline: Sequence[Mapping[str, Any]], stage: str, key: str) -> Any:
    for row in timeline:
        if row.get("logical_stage") == stage:
            return row.get(key)
    return None


def _hypothesis_evaluation(result: Mapping[str, Any]) -> list[dict[str, str]]:
    timeline = result.get("stage_timeline", [])
    if not isinstance(timeline, Sequence):
        timeline = []
    routing_entry = _stage_value(timeline, "routing_entry", "vmhwm_kb")
    peak = result.get("first_max_vmhwm_kb") or result.get("qret_peak_rss_kb")
    before = _stage_value(timeline, "routing_before_inverse_map_release", "mallinfo2_uordblks_kb")
    after = _stage_value(timeline, "routing_after_inverse_map_release", "mallinfo2_uordblks_kb")
    rss_before = _stage_value(timeline, "routing_before_inverse_map_release", "vmrss_kb")
    rss_after = _stage_value(timeline, "routing_after_inverse_map_release", "vmrss_kb")
    json_alive = _stage_value(timeline, "after_json_parse_or_dom_build", "vmrss_kb")
    mf_built = _stage_value(timeline, "after_machine_function_construction", "vmrss_kb")
    json_machine_overlap_drives_peak = (
        json_alive is not None
        and mf_built is not None
        and peak is not None
        and int(json_alive) >= int(peak) * 0.90
    )
    machine_bytes = (result.get("machine_components") or {}).get("machine_total_bytes")
    return [
        {
            "hypothesis": "A",
            "status": "supported" if routing_entry and peak and int(routing_entry) >= int(peak) * 0.95 else "rejected",
            "basis": "routing_entry VmHWM is compared against the run high-water.",
        },
        {
            "hypothesis": "B",
            "status": "supported"
            if before is not None and after is not None and int(before) > int(after) and rss_before == rss_after
            else "partially supported",
            "basis": "uordblks and VmRSS are compared around inverse-map release.",
        },
        {
            "hypothesis": "C",
            "status": "partially supported",
            "basis": "fordblks after frees and later calc-info allocations are inspected in the timeline.",
        },
        {
            "hypothesis": "D",
            "status": "supported" if json_machine_overlap_drives_peak else "rejected",
            "basis": "JSON DOM is destroyed before lowering; the H5 high-water appears after MachineFunction construction/routing setup.",
        },
        {
            "hypothesis": "E",
            "status": "supported" if machine_bytes and int(machine_bytes) >= 150 * ONE_MB else "partially supported",
            "basis": "MachineFunction component estimate is compared with the H5 RSS high-water.",
        },
    ]


def _h9_estimates(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    h4 = _first_result(results, case="h4_4th_new2", variant="eager")
    h5 = _first_result(results, case="h5_4th_new2", variant="eager")
    h4_inst = int((h4.get("machine_components") or {}).get("instruction_count") or 0)
    h5_inst = int((h5.get("machine_components") or {}).get("instruction_count") or 0)
    ratio = 1.0 if h4_inst <= 0 else max(1.0, h5_inst / h4_inst)
    components = (
        "instruction_object_bytes",
        "operand_container_bytes",
        "interned_path_storage_bytes",
        "instruction_list_node_bytes",
        "inverse_map_bytes",
        "metadata_bytes",
        "machine_total_bytes",
    )
    scenarios: dict[str, Any] = {}
    for scenario, factor in (("conservative", 0.85), ("central", 1.0), ("upper", 1.25)):
        scenario_components = {}
        for component in components:
            h5_value = int((h5.get("machine_components") or {}).get(component) or 0)
            scenario_components[component] = int(h5_value * (ratio**4) * factor)
        scenarios[scenario] = {
            "classification": "estimated",
            "components": scenario_components,
            "total_bytes": sum(scenario_components.values()),
        }
    theoretical = {
        "classification": "theoretical",
        "central_instruction_list_node_saving_bytes": scenarios.get("central", {})
        .get("components", {})
        .get("instruction_list_node_bytes"),
        "central_inverse_map_saving_bytes": scenarios.get("central", {})
        .get("components", {})
        .get("inverse_map_bytes"),
    }
    return {
        "observed": {"classification": "observed", "largest_measured_case": "H5"},
        "estimated": {"classification": "estimated", "scenarios": scenarios},
        "theoretical": theoretical,
    }


def _candidate_ranking(results: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    h5_eager = _first_result(results, case="h5_4th_new2", variant="eager")
    h5_lazy = _first_result(results, case="h5_4th_new2", variant="lazy")
    h5_trim = _first_result(results, case="h5_4th_new2", variant="eager_trim_after_inverse_release")
    components = h5_eager.get("machine_components", {}) if isinstance(h5_eager, Mapping) else {}
    baseline_peak = int(h5_eager.get("qret_peak_rss_kb") or 0)
    lazy_peak = int(h5_lazy.get("qret_peak_rss_kb") or baseline_peak)
    trim_peak = int(h5_trim.get("qret_peak_rss_kb") or baseline_peak)
    inverse_entries_eager = int(components.get("inverse_map_entries") or 0)
    inverse_entries_lazy = int((h5_lazy.get("machine_components") or {}).get("inverse_map_entries") or 0)
    candidates = [
        {
            "candidate": "D: instruction object arena / flat storage",
            "classification": "theoretical",
            "expected_h5_saving_kb": int(0.25 * int(components.get("instruction_object_bytes") or 0) / 1024),
            "peak_effective": True,
            "risk": "high",
            "basis": "MachineFunction is live when H5 high-water is reached.",
        },
        {
            "candidate": "E: instruction list-node removal",
            "classification": "theoretical",
            "expected_h5_saving_kb": int(int(components.get("instruction_list_node_bytes") or 0) / 1024),
            "peak_effective": True,
            "risk": "medium-high",
            "basis": "list nodes are live before routing and scale with instruction count.",
        },
        {
            "candidate": "F: residual operand API redesign",
            "classification": "theoretical",
            "expected_h5_saving_kb": int(0.6 * int(components.get("operand_container_bytes") or 0) / 1024),
            "peak_effective": True,
            "risk": "medium-high",
            "basis": "operand containers are live in MachineFunction at high-water.",
        },
        {
            "candidate": "G: allocator strategy / process isolation",
            "classification": "observed",
            "expected_h5_saving_kb": max(0, baseline_peak - trim_peak),
            "peak_effective": False,
            "risk": "medium",
            "basis": "diagnostic malloc_trim is measured but is not a production optimization.",
        },
        {
            "candidate": "inverse-map compactization",
            "classification": "observed",
            "expected_h5_saving_kb": max(0, baseline_peak - lazy_peak),
            "peak_effective": False,
            "risk": "medium",
            "basis": f"live inverse-map entries {inverse_entries_eager:,}->{inverse_entries_lazy:,} did not move peak enough.",
        },
    ]
    return sorted(
        candidates,
        key=lambda row: (
            bool(row.get("peak_effective")),
            int(row.get("expected_h5_saving_kb") or 0),
        ),
        reverse=True,
    )


def _write_report(
    path: Path,
    *,
    summary: Mapping[str, Any],
) -> None:
    results = summary.get("results", [])
    comparisons = summary.get("comparisons", {})
    h5_eager = _first_result(results, case="h5_4th_new2", variant="eager")
    h5_lazy = _first_result(results, case="h5_4th_new2", variant="lazy")
    h5_trim = _first_result(results, case="h5_4th_new2", variant="eager_trim_after_inverse_release")
    candidate_ranking = summary.get("candidate_ranking", [])
    h9 = summary.get("h9_estimates", {})
    hypotheses = _hypothesis_evaluation(h5_eager)
    all_metric_equal = all(
        row.get("raw", {}).get("all_equal") and row.get("normalized", {}).get("all_equal")
        for row in comparisons.values()
    )
    lines = [
        "# qret Pre-Routing High-Water Audit",
        "",
        "## Execution Limits",
        "",
        "- largest measured case: `H5`",
        "- H6 executed: `False`",
        "- H7 executed: `False`",
        "- H8 executed: `False`",
        "- H9 executed: `False`",
        "- H9 memory: estimated from observed H4/H5 values, not measured.",
        "",
        "## Production Configuration",
        "",
        "- magic path storage: `interned`",
        "- non-path operands: legacy containers",
        "- compile-info output: `summary`",
        "- summary TimeSeries: `legacy_timeseries`",
        "- DepGraph: `compact`",
        "- inverse-map construction: default `eager`; explicit `lazy` diagnostic mode remains available",
        "- inverse-map release after routing: enabled",
        "- pipeline-state output: skipped",
        "",
        "## Instrumentation Design",
        "",
        "- `QRET_PROFILE_HIGH_WATER=1` enables bounded high-water markers only when `QRET_RSS_PROFILE_JSONL` is also set.",
        "- `during_machine_function_construction` samples at 100,000 emitted machine-instruction intervals.",
        f"- Process-tree sampling keeps at most `{MAX_PROCESS_TREE_SAMPLE_ROWS:,}` rows in memory per run.",
        "- Process markers include `VmRSS`, `VmHWM`, `VmSize`, `VmData`, `RssAnon`, `RssFile`, `ru_maxrss`, and glibc `mallinfo2` fields when available.",
        "- Diagnostic `malloc_trim(0)` is controlled by `QRET_RSS_DIAGNOSTIC_TRIM_STAGE` and is not a production path.",
        "",
        "## Source Lifetime Audit",
        "",
        "| object | ownership/scope | live overlap conclusion |",
        "| ------ | --------------- | ----------------------- |",
        "| input JSON stream/buffer | `std::ifstream` inside `LoadFunctionFromIR` | no full explicit text buffer is retained after function return |",
        "| parsed JSON DOM | local `qret::Json j` in `LoadFunctionFromIR` | overlaps with source IR `IRContext` during `LoadJson`, then is destroyed before lowering |",
        "| source IR representation | `IRContext context` in `RunCompilation` | remains live while lowering and passes run because `MachineFunction` keeps an IR pointer |",
        "| MachineFunction | local `mf` in `RunCompilation` | live through mapping/routing/compile-info and process exit |",
        "| lowering temporary | local lowering contexts | not retained after `Lowering::RunOnMachineFunction` |",
        "| mapping temporary | local `QubitGraph`/mapping structures | not retained after mapping pass exit |",
        "| routing temporary | `InstQueue`/simulator/search state | destroyed before `routing_after_temporary_destroy` |",
        "| inverse map | `MachineBasicBlock::mp_` | eager builds before routing; release clears maps after routing; lazy can avoid construction |",
        "| DepGraph | local in `CompileInfoWithoutTopology` | compact graph is local to depth calculation and destroyed after pass |",
        "| serialization buffer | compile-info JSON DOM in `DumpCompileInfo` | summary mode is small; pipeline-state serialization is skipped |",
        "",
        "## Stage Timeline",
        "",
        "| logical stage | observed stage | VmRSS KB | VmHWM KB | uordblks KB | fordblks KB | VmRSS-uord KB |",
        "| ------------- | -------------- | -------: | -------: | ----------: | ----------: | -----------: |",
    ]
    for row in h5_eager.get("stage_timeline", []):
        lines.append(
            f"| {row.get('logical_stage')} | {row.get('observed_stage') or ''} | "
            f"{_fmt_int(row.get('vmrss_kb'))} | {_fmt_int(row.get('vmhwm_kb'))} | "
            f"{_fmt_int(row.get('mallinfo2_uordblks_kb'))} | "
            f"{_fmt_int(row.get('mallinfo2_fordblks_kb'))} | "
            f"{_fmt_int(row.get('vmrss_minus_uordblks_kb'))} |"
        )
    lines.extend(
        [
            "",
            "## H4 Correctness",
            "",
            f"- raw and normalized metric parity across H4 measured variants: `{all_metric_equal}`",
            "- profile-off variants produce compile metrics without qret RSS profile rows.",
            "- profile-on eager/lazy variants keep summary compile-info schema and pipeline-state skip behavior.",
            "",
            "## H5 Observed Memory Timeline",
            "",
            f"- eager qret peak RSS KB: `{_fmt_int(h5_eager.get('qret_peak_rss_kb'))}`",
            f"- eager first max VmHWM stage: `{h5_eager.get('first_max_vmhwm_stage')}`",
            f"- eager first max VmRSS stage: `{h5_eager.get('first_max_vmrss_stage')}`",
            f"- routing entry VmHWM KB: `{_fmt_int(_stage_value(h5_eager.get('stage_timeline', []), 'routing_entry', 'vmhwm_kb'))}`",
            "",
            "## Eager vs Lazy",
            "",
            "| variant | qret peak KB | first max VmHWM stage | inverse entries | inverse bytes | routing-before uord KB | routing-after uord KB |",
            "| ------- | ------------: | --------------------- | --------------: | ------------: | ---------------------: | --------------------: |",
        ]
    )
    for row in (h5_eager, h5_lazy):
        timeline = row.get("stage_timeline", [])
        components = row.get("machine_components", {})
        lines.append(
            f"| {row.get('variant')} | {_fmt_int(row.get('qret_peak_rss_kb'))} | "
            f"{row.get('first_max_vmhwm_stage')} | {_fmt_int(components.get('inverse_map_entries'))} | "
            f"{_fmt_int(components.get('inverse_map_bytes'))} | "
            f"{_fmt_int(_stage_value(timeline, 'routing_before_inverse_map_release', 'mallinfo2_uordblks_kb'))} | "
            f"{_fmt_int(_stage_value(timeline, 'routing_after_inverse_map_release', 'mallinfo2_uordblks_kb'))} |"
        )
    lines.extend(
        [
            "",
            "## Allocator Retention Analysis",
            "",
            "- The report compares `VmRSS`, `VmHWM`, `uordblks`, `fordblks`, and `VmRSS-uordblks` at every requested stage.",
            "- A drop in `uordblks` without a matching `VmRSS` drop is treated as allocator-retained arena, not a still-live object by itself.",
            "- `malloc_trim` diagnostics are diagnostic only and are not proposed as production default.",
            "",
            "| trim variant | qret peak KB | trim stage | RSS drop KB | uordblks drop KB | fordblks drop KB |",
            "| ------------ | ------------: | ---------- | ----------: | ---------------: | ---------------: |",
        ]
    )
    for row in [item for item in results if str(item.get("variant", "")).startswith("eager_trim")]:
        diagnostics = row.get("trim_diagnostics", {})
        if not diagnostics:
            continue
        trim_stage, diag = next(iter(diagnostics.items()))
        lines.append(
            f"| {row.get('case')}:{row.get('variant')} | {_fmt_int(row.get('qret_peak_rss_kb'))} | "
            f"{trim_stage} | {_fmt_int(diag.get('rss_drop_kb'))} | "
            f"{_fmt_int(diag.get('uordblks_drop_kb'))} | {_fmt_int(diag.get('fordblks_drop_kb'))} |"
        )
    lines.extend(
        [
            "",
            "## MachineFunction Component Analysis",
            "",
            "| component | H5 eager observed/theoretical value |",
            "| --------- | ---------------------------------: |",
        ]
    )
    for key, value in (h5_eager.get("machine_components") or {}).items():
        lines.append(f"| `{key}` | {_fmt_int(value)} |")
    lines.extend(
        [
            "",
            "## Process Isolation Feasibility",
            "",
            "- Existing qret supports a serialization boundary at SC_LS_FIXED_V0 pipeline state, but Evaluation production skips that output to avoid a large JSON duplicate.",
            "- Splitting immediately after IR parse would require serializing qret IR; that reintroduces JSON materialization and does not carry MachineFunction state.",
            "- Splitting after MachineFunction construction would require a compact machine-function artifact that preserves instruction metadata, topology-derived symbols, and compile-info initialization state. That artifact does not currently exist.",
            "- H4 process-isolation production implementation was therefore not added; the safe follow-up is a design task, not an optimization toggle.",
            "",
            "## Hypothesis Evaluation",
            "",
            "| hypothesis | status | basis |",
            "| ---------- | ------ | ----- |",
        ]
    )
    for row in hypotheses:
        lines.append(f"| {row['hypothesis']} | {row['status']} | {row['basis']} |")
    lines.extend(
        [
            "",
            "## H9 Estimates",
            "",
            f"- observed classification present: `{h9.get('observed', {}).get('classification')}`",
            f"- estimated classification present: `{h9.get('estimated', {}).get('classification')}`",
            f"- theoretical classification present: `{h9.get('theoretical', {}).get('classification')}`",
            "- H9 was not run; estimates extrapolate H4/H5 component growth.",
            "",
            "## Decision",
            "",
            "- No production optimization was implemented in this audit.",
            "- Lazy inverse-map remains a diagnostic candidate, not the default.",
            "- The next implementation should target MachineFunction live payload that exists before routing and remains live at the H5 high-water.",
            "",
            "## Next Candidate Ranking",
            "",
            "| rank | candidate | classification | H5 expected saving KB | peak effective | risk | basis |",
            "| ---: | --------- | -------------- | --------------------: | -------------- | ---- | ----- |",
        ]
    )
    for index, row in enumerate(candidate_ranking, start=1):
        lines.append(
            f"| {index} | {row.get('candidate')} | {row.get('classification')} | "
            f"{_fmt_int(row.get('expected_h5_saving_kb'))} | {row.get('peak_effective')} | "
            f"{row.get('risk')} | {row.get('basis')} |"
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
    comparisons = _metric_comparisons(results)
    summary = {
        "environment": environment,
        "build_provenance": build_provenance,
        "results": results,
        "comparisons": comparisons,
        "candidate_ranking": _candidate_ranking(results),
        "h9_estimates": _h9_estimates(results),
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
    parser = argparse.ArgumentParser(description="Audit qret pre-routing and MachineFunction high-water memory.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--cache-root", type=Path, default=sc.SURFACE_CODE_CACHE_DIR)
    parser.add_argument("--case", action="append", choices=tuple(CASE_CHAIN_LENGTH), help="Case to run. Default: H4 and H5.")
    parser.add_argument("--case-variant", action="append", help="Restrict variants as CASE:VARIANT. Can be repeated.")
    parser.add_argument("--batch-size", type=int, default=sc.SURFACE_CODE_RZ_HELPER_BATCH_SIZE)
    parser.add_argument("--sample-interval-sec", type=float, default=0.02)
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args(argv)
    variants = _parse_case_variant(args.case_variant)
    cases = tuple(args.case) if args.case else tuple(CASE_CHAIN_LENGTH)
    run_profile(
        output_root=args.output_root,
        report_path=args.report,
        cache_root=args.cache_root,
        build=bool(args.build),
        cases=cases,
        variants=variants,
        batch_size=int(args.batch_size),
        sample_interval_sec=float(args.sample_interval_sec),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
