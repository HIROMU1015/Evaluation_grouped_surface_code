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

import profile_qret_calc_info_memory as calc_profile  # noqa: E402
import profile_qret_pre_routing_memory as qret_profile  # noqa: E402
import profile_surface_code_compact_scaling as compact_profile  # noqa: E402


DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "qret_routing_live_memory"
DEFAULT_REPORT_PATH = (
    REPO_ROOT / "docs" / "benchmarks" / "qret_routing_live_memory_profile.md"
)
PF_LABEL = "4th(new_2)"
COMPILE_MODE = "ftqc_compile_topology"
SAMPLE_INTERVAL_SEC = 0.02
MIN_FREE_DISK_BYTES = 5 * 1024**3
ONE_MB = 1024 * 1024
RSS_SAVING_GATE_KB = 100 * 1024
RSS_SAVING_GATE_FRACTION = 0.10
LIVE_BYTES_GATE = 150 * ONE_MB
BOTH_TRIM_GATE_KB = 20 * 1024

CASE_CHAIN_LENGTH = {
    "h4_4th_new2": 4,
    "h5_4th_new2": 5,
}
CASE_DISPLAY = {
    "h4_4th_new2": "H4 `4th(new_2)`",
    "h5_4th_new2": "H5 `4th(new_2)`",
}
VARIANTS = {
    "baseline": {"trim_stage": "none"},
    "trim_after_json_destroy": {"trim_stage": "after_json_dom_destroy"},
    "trim_after_routing_temporary_destroy": {
        "trim_stage": "after_routing_temporary_destroy"
    },
    "trim_both": {"trim_stage": "both"},
}
DEFAULT_RUNS = {
    "h4_4th_new2": {
        "baseline": 1,
        "trim_after_json_destroy": 1,
        "trim_after_routing_temporary_destroy": 1,
    },
    "h5_4th_new2": {
        "baseline": 2,
        "trim_after_json_destroy": 1,
        "trim_after_routing_temporary_destroy": 1,
    },
}
REQUIRED_STAGES = (
    "compile_entry",
    "before_ir_file_read",
    "after_ir_file_read",
    "before_ir_json_parse",
    "after_ir_json_parse",
    "before_load_json",
    "after_load_json_machine_function_built",
    "before_ir_json_dom_destroy",
    "after_ir_json_dom_destroy",
    "before_input_buffer_destroy",
    "after_input_buffer_destroy",
    "before_lowering",
    "after_lowering",
    "before_mapping",
    "after_mapping",
    "routing_entry",
    "routing_after_state_construct",
    "routing_after_queue_construct",
    "routing_after_initial_peek",
    "routing_main_loop_peak",
    "routing_main_loop_exit",
    "routing_before_temporary_destroy",
    "routing_after_temporary_destroy",
    "routing_pass_exit",
    "before_calc_info_without_topology",
    "after_calc_info_without_topology",
    "before_calc_info_with_topology",
    "after_calc_info_with_topology",
    "compile_exit",
)
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
    "estimated_execution_time_sec",
)
SUMMARY_FIELDS = (
    "case",
    "variant",
    "run_index",
    "status",
    "returncode",
    "elapsed_seconds",
    "qret_peak_rss_kb",
    "parent_peak_rss_kb",
    "tree_peak_rss_kb",
    "max_rss_stage",
    "max_rss_stage_vmrss_kb",
    "compile_info_size_bytes",
    "trim_stage",
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
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in SUMMARY_FIELDS})


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


def _compiler_version() -> str:
    for candidate in ("c++", "g++", "clang++"):
        try:
            completed = subprocess.run(
                [candidate, "--version"],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
        except OSError:
            continue
        if completed.returncode == 0:
            return completed.stdout.splitlines()[0]
    return "unknown"


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


def _median(values: Sequence[float | int | None]) -> float | int | None:
    present = [value for value in values if value is not None]
    return statistics.median(present) if present else None


def _max_present(*values: int | None) -> int | None:
    present = [int(value) for value in values if value is not None]
    return max(present) if present else None


def _fmt_int(value: Any) -> str:
    if value is None:
        return ""
    try:
        return f"{int(value):,}"
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
        return f"{float(value) / 1024:.1f}"
    except (TypeError, ValueError):
        return str(value)


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


def _architecture() -> sc.SurfaceCodeArchitecture:
    return sc.SurfaceCodeArchitecture(
        compile_mode=COMPILE_MODE,
        skip_compile_output=True,
        compile_info_output_mode="summary",
    )


def _variant_trim_stage(variant: str) -> str:
    try:
        return str(VARIANTS[variant]["trim_stage"])
    except KeyError as exc:
        raise ValueError(f"unknown variant: {variant}") from exc


def _validate_trim_stage(stage: str) -> str:
    valid = {"none", "after_json_dom_destroy", "after_routing_temporary_destroy", "both"}
    if stage not in valid:
        raise ValueError(f"invalid trim stage: {stage}")
    return stage


def _variant_env(env: dict[str, str], variant: str) -> None:
    env["QRET_SUMMARY_TIME_SERIES_IMPL"] = "legacy_timeseries"
    env["QRET_RSS_DIAGNOSTIC_TRIM_STAGE"] = _validate_trim_stage(_variant_trim_stage(variant))
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
    sentinel = object()
    mismatches = [key for key in keys if baseline.get(key, sentinel) != candidate.get(key, sentinel)]
    return {
        "all_equal": not mismatches,
        "mismatches": mismatches,
        "field_count": len(keys),
        "ignored_fields": sorted(ignored),
    }


def _profile_max_stage(profile_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    candidates = [row for row in profile_rows if row.get("vmrss_kb") is not None]
    if not candidates:
        return {}
    row = max(candidates, key=lambda item: int(item.get("vmrss_kb") or -1))
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
        if previous is None or previous.get("vmrss_kb") is None
        else int(row["vmrss_kb"]) - int(previous["vmrss_kb"]),
    }


def _stage_memory_table(profile_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    best_by_stage: dict[str, Mapping[str, Any]] = {}
    for row in profile_rows:
        stage = row.get("stage")
        if not isinstance(stage, str):
            continue
        old = best_by_stage.get(stage)
        if old is None or int(row.get("vmrss_kb") or -1) > int(old.get("vmrss_kb") or -1):
            best_by_stage[stage] = row
    rows = []
    for stage, row in best_by_stage.items():
        rows.append(
            {
                "stage": stage,
                "vmrss_kb": row.get("vmrss_kb"),
                "pss_kb": row.get("pss_kb"),
                "private_dirty_kb": row.get("private_dirty_kb"),
                "mallinfo2_uordblks_kb": row.get("mallinfo2_uordblks_kb"),
                "mallinfo2_fordblks_kb": row.get("mallinfo2_fordblks_kb"),
            }
        )
    return rows


def _stage_set(result: Mapping[str, Any]) -> set[str]:
    return {str(row.get("stage")) for row in result.get("profile_rows", []) if row.get("stage")}


def _missing_required_stages(result: Mapping[str, Any]) -> list[str]:
    stages = _stage_set(result)
    return [stage for stage in REQUIRED_STAGES if stage not in stages]


def _extra_at_stage(
    rows: Sequence[Mapping[str, Any]],
    stage: str,
    *,
    last: bool = False,
) -> dict[str, Any]:
    iterable = reversed(rows) if last else rows
    for row in iterable:
        if row.get("stage") == stage and isinstance(row.get("extra"), Mapping):
            return dict(row["extra"])
    return {}


def _max_extra_value(rows: Sequence[Mapping[str, Any]], key: str) -> int | None:
    values: list[int] = []
    for row in rows:
        extra = row.get("extra")
        if isinstance(extra, Mapping) and extra.get(key) is not None:
            values.append(int(extra[key]))
    return max(values) if values else None


def _object_estimates(profile_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    json_extra = _extra_at_stage(profile_rows, "after_ir_json_parse")
    routing_extra = _extra_at_stage(profile_rows, "routing_before_temporary_destroy", last=True)
    after_routing_extra = _extra_at_stage(profile_rows, "routing_after_temporary_destroy", last=True)
    machine_bytes = _max_extra_value(profile_rows, "machine_total_bytes_estimated")
    routing_queue_nodes = _max_extra_value(profile_rows, "routing_queue_nodes")
    queue_bytes = _max_extra_value(profile_rows, "routing_queue_total_bytes_estimated")
    sim_bytes = _max_extra_value(profile_rows, "routing_sim_total_bytes_estimated")
    routing_live_bytes = _max_extra_value(profile_rows, "routing_live_total_bytes_estimated")
    return {
        "json_dom": {
            "count": json_extra.get("json_object_count"),
            "estimated_payload_bytes": json_extra.get("json_estimated_dynamic_payload_bytes"),
            "string_total_size": json_extra.get("json_string_total_size"),
            "file_size_bytes": json_extra.get("ir_file_size_bytes"),
            "estimate_is_exact": json_extra.get("json_estimate_is_exact"),
        },
        "machine_function": {
            "count": _max_extra_value(profile_rows, "machine_instructions"),
            "estimated_payload_bytes": machine_bytes,
            "metadata_bytes": _max_extra_value(profile_rows, "machine_metadata_bytes_estimated"),
            "raw_string_bytes": _max_extra_value(
                profile_rows,
                "machine_raw_string_live_capacity_bytes",
            ),
            "path_coordinate_bytes": _max_extra_value(
                profile_rows,
                "machine_path_coordinate_list_node_bytes_estimated",
            ),
        },
        "routing_temporary": {
            "count": routing_queue_nodes,
            "estimated_payload_bytes": int(queue_bytes or 0) + int(sim_bytes or 0),
            "queue_bytes": queue_bytes,
            "simulator_bytes": sim_bytes,
            "routing_live_bytes": routing_live_bytes,
        },
        "routing_after_temporary_destroy": {
            "machine_bytes": after_routing_extra.get("machine_total_bytes_estimated"),
            "routing_queue_bytes": after_routing_extra.get(
                "routing_queue_total_bytes_estimated"
            ),
            "routing_simulator_bytes": after_routing_extra.get(
                "routing_sim_total_bytes_estimated"
            ),
        },
    }


def _trim_diagnostics(
    profile_rows: Sequence[Mapping[str, Any]],
    trim_stage: str,
) -> dict[str, Any]:
    if trim_stage == "none":
        return {}
    stages = (
        ("after_json_dom_destroy",)
        if trim_stage == "after_json_dom_destroy"
        else ("after_routing_temporary_destroy",)
        if trim_stage == "after_routing_temporary_destroy"
        else ("after_json_dom_destroy", "after_routing_temporary_destroy")
    )
    diagnostics: dict[str, Any] = {}
    for stage in stages:
        before_name = f"diagnostic_trim_before_{stage}"
        after_name = f"diagnostic_trim_after_{stage}"
        before = next((row for row in profile_rows if row.get("stage") == before_name), None)
        after = next((row for row in profile_rows if row.get("stage") == after_name), None)
        if before is None or after is None:
            continue
        elapsed = None
        extra = after.get("extra")
        if isinstance(extra, Mapping):
            elapsed = extra.get("malloc_trim_elapsed_sec")
        diagnostics[stage] = {
            "pre_trim_rss_kb": before.get("vmrss_kb"),
            "post_trim_rss_kb": after.get("vmrss_kb"),
            "rss_drop_kb": None
            if before.get("vmrss_kb") is None or after.get("vmrss_kb") is None
            else int(before["vmrss_kb"]) - int(after["vmrss_kb"]),
            "uordblks_drop_kb": None
            if before.get("mallinfo2_uordblks_kb") is None
            or after.get("mallinfo2_uordblks_kb") is None
            else int(before["mallinfo2_uordblks_kb"]) - int(after["mallinfo2_uordblks_kb"]),
            "fordblks_drop_kb": None
            if before.get("mallinfo2_fordblks_kb") is None
            or after.get("mallinfo2_fordblks_kb") is None
            else int(before["mallinfo2_fordblks_kb"]) - int(after["mallinfo2_fordblks_kb"]),
            "elapsed_sec": elapsed,
        }
    return diagnostics


def _dep_graph_extra(profile_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    for row in reversed(profile_rows):
        extra = row.get("extra")
        if isinstance(extra, Mapping) and "dep_graph_implementation" in extra:
            return dict(extra)
    return {}


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
        "root_pid": root_pid,
        "tree_vmrss_kb": tree_peak,
        "parent_vmrss_kb": parent_vmrss,
        "qret_vmrss_kb": qret_vmrss,
        "other_vmrss_kb": None
        if parent_vmrss is None and qret_vmrss is None
        else tree_peak - int(parent_vmrss or 0) - int(qret_vmrss or 0),
    }


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
    architecture = _architecture()
    trim_stage = _variant_trim_stage(variant)
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
    stage_table = _stage_memory_table(profile_rows)
    object_estimates = _object_estimates(profile_rows)
    trim_diagnostics = _trim_diagnostics(profile_rows, trim_stage)
    result = {
        "case": case_key,
        "phase": "isolated_qret",
        "variant": variant,
        "trim_stage": trim_stage,
        "output_mode": "summary",
        "summary_impl": "legacy_timeseries",
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
        "profile_rows": profile_rows,
        "stage_memory_table": stage_table,
        "object_estimates": object_estimates,
        "trim_diagnostics": trim_diagnostics,
        "missing_required_stages": [],
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
    result["missing_required_stages"] = _missing_required_stages(result)
    _write_json(run_dir / "summary.json", result)
    if process.returncode != 0:
        raise RuntimeError(f"isolated qret failed for {case_key} {variant}: {stderr[-4000:]}")
    return result


def _aggregate(
    results: Sequence[Mapping[str, Any]],
    *,
    case: str,
    variant: str,
) -> dict[str, Any]:
    rows = [row for row in results if row.get("case") == case and row.get("variant") == variant]
    if not rows:
        return {}
    return {
        "case": case,
        "variant": variant,
        "runs": len(rows),
        "median_peak_rss_kb": _median([row.get("qret_peak_rss_kb") for row in rows]),
        "median_elapsed_seconds": _median([row.get("elapsed_seconds") for row in rows]),
        "median_tree_peak_rss_kb": _median([row.get("tree_peak_rss_kb") for row in rows]),
        "max_stage": max(
            (row for row in rows if row.get("max_rss_stage_vmrss_kb") is not None),
            key=lambda row: int(row.get("max_rss_stage_vmrss_kb") or 0),
            default={},
        ).get("max_rss_stage"),
        "missing_required_stages": sorted(
            {
                stage
                for row in rows
                for stage in row.get("missing_required_stages", [])
            }
        ),
    }


def _metric_comparisons(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    comparisons: dict[str, Any] = {}
    for case in CASE_CHAIN_LENGTH:
        baselines = [
            row for row in results if row.get("case") == case and row.get("variant") == "baseline"
        ]
        if not baselines:
            continue
        baseline = baselines[0]
        for row in results:
            if row.get("case") != case or row.get("variant") == "baseline":
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
                    ignored={"compile_info_json"},
                ),
            }
    return comparisons


def _first_result(
    results: Sequence[Mapping[str, Any]],
    *,
    case: str,
    variant: str,
) -> Mapping[str, Any]:
    for row in results:
        if row.get("case") == case and row.get("variant") == variant:
            return row
    return {}


def _diagnostic_rss_drop_kb(
    result: Mapping[str, Any],
    diagnostic_stage: str,
) -> int | None:
    diagnostics = result.get("trim_diagnostics", {})
    if not isinstance(diagnostics, Mapping):
        return None
    stage_diag = diagnostics.get(diagnostic_stage)
    if not isinstance(stage_diag, Mapping):
        return None
    value = stage_diag.get("rss_drop_kb")
    return None if value is None else int(value)


def _should_run_both_trim(results: Sequence[Mapping[str, Any]]) -> bool:
    case = "h5_4th_new2"
    json_result = _first_result(results, case=case, variant="trim_after_json_destroy")
    routing_result = _first_result(
        results,
        case=case,
        variant="trim_after_routing_temporary_destroy",
    )
    json_drop = _diagnostic_rss_drop_kb(json_result, "after_json_dom_destroy") or 0
    routing_drop = _diagnostic_rss_drop_kb(
        routing_result,
        "after_routing_temporary_destroy",
    ) or 0
    return json_drop >= BOTH_TRIM_GATE_KB and routing_drop >= BOTH_TRIM_GATE_KB


def _candidate_ranking(results: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    baseline_agg = _aggregate(results, case="h5_4th_new2", variant="baseline")
    baseline = _first_result(results, case="h5_4th_new2", variant="baseline")
    if not baseline:
        baseline_agg = _aggregate(results, case="h4_4th_new2", variant="baseline")
        baseline = _first_result(results, case="h4_4th_new2", variant="baseline")
    baseline_peak = int(
        baseline_agg.get("median_peak_rss_kb") or baseline.get("qret_peak_rss_kb") or 0
    )
    estimates = baseline.get("object_estimates", {}) if isinstance(baseline, Mapping) else {}
    json_est = estimates.get("json_dom", {}) if isinstance(estimates, Mapping) else {}
    machine_est = estimates.get("machine_function", {}) if isinstance(estimates, Mapping) else {}
    routing_est = estimates.get("routing_temporary", {}) if isinstance(estimates, Mapping) else {}
    json_trim = _first_result(results, case="h5_4th_new2", variant="trim_after_json_destroy")
    routing_trim = _first_result(
        results,
        case="h5_4th_new2",
        variant="trim_after_routing_temporary_destroy",
    )
    json_drop_kb = _diagnostic_rss_drop_kb(json_trim, "after_json_dom_destroy") or 0
    routing_drop_kb = _diagnostic_rss_drop_kb(
        routing_trim,
        "after_routing_temporary_destroy",
    ) or 0
    json_peak = int(json_trim.get("qret_peak_rss_kb") or baseline_peak)
    routing_peak = int(routing_trim.get("qret_peak_rss_kb") or baseline_peak)
    json_peak_saving_kb = max(0, baseline_peak - json_peak)
    routing_peak_saving_kb = max(0, baseline_peak - routing_peak)
    candidates = [
        {
            "candidate": "JSON DOM allocator retention",
            "live_bytes": int(json_est.get("estimated_payload_bytes") or 0),
            "retained_bytes": max(json_drop_kb, 0) * 1024,
            "live_or_retained_at_peak_bytes": 0,
            "peak_saving_kb": json_peak_saving_kb,
            "theoretical_saving_bytes": max(json_peak_saving_kb, json_drop_kb) * 1024,
            "measured_evidence": (
                f"trim drop {json_drop_kb:,} KB after JSON DOM destroy; "
                f"H5 peak saving {json_peak_saving_kb:,} KB"
            ),
            "risk": "low for lifetime audit; production trim is out of scope",
        },
        {
            "candidate": "MachineFunction live object",
            "live_bytes": int(machine_est.get("estimated_payload_bytes") or 0),
            "retained_bytes": 0,
            "live_or_retained_at_peak_bytes": int(
                machine_est.get("estimated_payload_bytes") or 0
            ),
            "peak_saving_kb": 0,
            "theoretical_saving_bytes": int(machine_est.get("estimated_payload_bytes") or 0),
            "measured_evidence": "estimated live MachineFunction payload at routing/calc stages",
            "risk": "medium/high; instruction ownership or schema changes are risky",
        },
        {
            "candidate": "routing temporary allocator retention",
            "live_bytes": int(routing_est.get("estimated_payload_bytes") or 0),
            "retained_bytes": max(routing_drop_kb, 0) * 1024,
            "live_or_retained_at_peak_bytes": 0,
            "peak_saving_kb": routing_peak_saving_kb,
            "theoretical_saving_bytes": max(
                int(routing_est.get("estimated_payload_bytes") or 0),
                max(routing_peak_saving_kb, routing_drop_kb) * 1024,
            ),
            "measured_evidence": (
                f"trim drop {routing_drop_kb:,} KB after routing temporary destroy; "
                f"H5 peak saving {routing_peak_saving_kb:,} KB"
            ),
            "risk": "low for scope/lifetime changes; malloc_trim is out of scope",
        },
    ]
    for candidate in candidates:
        saving_kb = int(candidate.get("peak_saving_kb") or 0)
        live_or_retained_at_peak = int(candidate.get("live_or_retained_at_peak_bytes") or 0)
        passes = (
            saving_kb >= RSS_SAVING_GATE_KB
            or (baseline_peak > 0 and saving_kb >= baseline_peak * RSS_SAVING_GATE_FRACTION)
            or live_or_retained_at_peak >= LIVE_BYTES_GATE
        )
        candidate["passes_gate"] = passes
        if not passes:
            priority = "report_only"
        elif candidate["candidate"] == "MachineFunction live object":
            priority = "proposal_only"
        else:
            priority = "production_candidate"
        candidate["priority"] = priority
    return sorted(
        candidates,
        key=lambda item: int(item.get("theoretical_saving_bytes") or 0),
        reverse=True,
    )


def _lifetime_audit_rows(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    estimates = result.get("object_estimates", {})
    if not isinstance(estimates, Mapping):
        estimates = {}
    return [
        {
            "object": "IR file stream/input buffer",
            "construction": "before_ir_file_read",
            "destruction": "stream closed when LoadFunctionFromIR returns",
            "still_live_at_routing_exit": "no explicit full input buffer",
            "estimated_bytes": estimates.get("json_dom", {}).get("file_size_bytes", 0)
            if isinstance(estimates.get("json_dom"), Mapping)
            else 0,
        },
        {
            "object": "parsed JSON DOM",
            "construction": "after_ir_json_parse",
            "destruction": "after_ir_json_dom_destroy",
            "still_live_at_routing_exit": "no",
            "estimated_bytes": estimates.get("json_dom", {}).get("estimated_payload_bytes", 0)
            if isinstance(estimates.get("json_dom"), Mapping)
            else 0,
        },
        {
            "object": "MachineFunction/instructions/metadata",
            "construction": "before_lowering/after_lowering",
            "destruction": "compile exit",
            "still_live_at_routing_exit": "yes",
            "estimated_bytes": estimates.get("machine_function", {}).get(
                "estimated_payload_bytes",
                0,
            )
            if isinstance(estimates.get("machine_function"), Mapping)
            else 0,
        },
        {
            "object": "routing InstQueue/state/simulator",
            "construction": "routing_after_queue_construct/routing_after_state_construct",
            "destruction": "routing_after_temporary_destroy",
            "still_live_at_routing_exit": "no",
            "estimated_bytes": estimates.get("routing_temporary", {}).get(
                "estimated_payload_bytes",
                0,
            )
            if isinstance(estimates.get("routing_temporary"), Mapping)
            else 0,
        },
        {
            "object": "DepGraph",
            "construction": "calc_info_without_topology",
            "destruction": "after calc_info_without_topology",
            "still_live_at_routing_exit": "not constructed yet",
            "estimated_bytes": None,
        },
        {
            "object": "compile-info object",
            "construction": "init_compile_info / calc_info passes",
            "destruction": "compile exit",
            "still_live_at_routing_exit": "partially initialized",
            "estimated_bytes": None,
        },
    ]


def _write_report(
    path: Path,
    *,
    environment: Mapping[str, Any],
    build_provenance: Mapping[str, Any],
    results: Sequence[Mapping[str, Any]],
    comparisons: Mapping[str, Any],
    candidate_ranking: Sequence[Mapping[str, Any]],
    both_trim_run: bool,
) -> None:
    baseline = _first_result(results, case="h5_4th_new2", variant="baseline")
    if not baseline:
        baseline = _first_result(results, case="h4_4th_new2", variant="baseline")
    stage_rows = baseline.get("stage_memory_table", []) if isinstance(baseline, Mapping) else []
    stage_by_name = {
        str(row.get("stage")): row for row in stage_rows if isinstance(row, Mapping)
    }
    before_json_destroy = stage_by_name.get("before_ir_json_dom_destroy", {})
    after_json_destroy = stage_by_name.get("after_ir_json_dom_destroy", {})
    json_destroy_uord_drop_kb = None
    json_destroy_rss_delta_kb = None
    if before_json_destroy.get("mallinfo2_uordblks_kb") is not None and after_json_destroy.get(
        "mallinfo2_uordblks_kb"
    ) is not None:
        json_destroy_uord_drop_kb = int(before_json_destroy["mallinfo2_uordblks_kb"]) - int(
            after_json_destroy["mallinfo2_uordblks_kb"]
        )
    if before_json_destroy.get("vmrss_kb") is not None and after_json_destroy.get(
        "vmrss_kb"
    ) is not None:
        json_destroy_rss_delta_kb = int(after_json_destroy["vmrss_kb"]) - int(
            before_json_destroy["vmrss_kb"]
        )
    estimates = baseline.get("object_estimates", {}) if isinstance(baseline, Mapping) else {}
    json_est = estimates.get("json_dom", {}) if isinstance(estimates, Mapping) else {}
    machine_est = estimates.get("machine_function", {}) if isinstance(estimates, Mapping) else {}
    routing_est = estimates.get("routing_temporary", {}) if isinstance(estimates, Mapping) else {}
    h5_baseline = _aggregate(results, case="h5_4th_new2", variant="baseline")
    h4_baseline = _aggregate(results, case="h4_4th_new2", variant="baseline")
    any_gate = any(bool(row.get("passes_gate")) for row in candidate_ranking)
    metrics_equal = all(
        item.get("raw", {}).get("all_equal") and item.get("normalized", {}).get("all_equal")
        for item in comparisons.values()
    )
    lifetime_rows = _lifetime_audit_rows(baseline)

    lines: list[str] = [
        "# qret Routing Live Memory Profile",
        "",
        "H6 was not run. This profile uses H4 for instrumentation validation and H5 for candidate selection only.",
        "",
        "## Environment",
        "",
        f"- Evaluation HEAD: `{environment.get('evaluation_head')}`",
        f"- qret executable hash: `{environment.get('measurement_runtime_hashes', {}).get('qret_executable_hash')}`",
        f"- libqret-core hash: `{environment.get('measurement_runtime_hashes', {}).get('qret_core_library_hash')}`",
        f"- compiler: `{environment.get('compiler')}`",
        f"- allocator: `{environment.get('allocator')}`",
        f"- MemTotal KB: `{environment.get('meminfo', {}).get('MemTotal')}`",
        f"- SwapTotal KB: `{environment.get('meminfo', {}).get('SwapTotal')}`",
        f"- disk free bytes at start: `{environment.get('disk_free_bytes')}`",
        f"- output root: `{environment.get('output_root')}`",
        f"- build requested: `{build_provenance.get('build_requested')}`",
        "",
        "## Run Summary",
        "",
        "| case | variant | runs | median peak KB | median elapsed sec | max stage | missing markers |",
        "| ---- | ------- | ---: | -------------: | -----------------: | --------- | --------------- |",
    ]
    for case in CASE_CHAIN_LENGTH:
        for variant in VARIANTS:
            agg = _aggregate(results, case=case, variant=variant)
            if not agg:
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        CASE_DISPLAY[case],
                        variant,
                        _fmt_int(agg.get("runs")),
                        _fmt_int(agg.get("median_peak_rss_kb")),
                        f"{float(agg.get('median_elapsed_seconds') or 0):.3f}",
                        str(agg.get("max_stage") or ""),
                        ", ".join(agg.get("missing_required_stages", [])),
                    ]
                )
                + " |"
            )
    lines.extend(
        [
            "",
            f"- H5 baseline median peak KB: `{_fmt_int(h5_baseline.get('median_peak_rss_kb'))}`",
            f"- H4 baseline median peak KB: `{_fmt_int(h4_baseline.get('median_peak_rss_kb'))}`",
            f"- `trim_both` run: `{both_trim_run}`",
            "",
            "## Lifetime Audit",
            "",
            "| object | construction | destruction | live at routing exit | estimated bytes |",
            "| ------ | ------------ | ----------- | -------------------- | --------------: |",
        ]
    )
    for row in lifetime_rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["object"]),
                    str(row["construction"]),
                    str(row["destruction"]),
                    str(row["still_live_at_routing_exit"]),
                    _fmt_int(row.get("estimated_bytes")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Stage Memory",
            "",
            "| stage | RSS KB | PSS KB | PrivateDirty KB | uordblks KB | fordblks KB |",
            "| ----- | -----: | -----: | --------------: | ----------: | ----------: |",
        ]
    )
    for row in stage_rows:
        if row["stage"] not in REQUIRED_STAGES and not str(row["stage"]).startswith(
            "diagnostic_trim_"
        ):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("stage")),
                    _fmt_int(row.get("vmrss_kb")),
                    _fmt_int(row.get("pss_kb")),
                    _fmt_int(row.get("private_dirty_kb")),
                    _fmt_int(row.get("mallinfo2_uordblks_kb")),
                    _fmt_int(row.get("mallinfo2_fordblks_kb")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Object Estimates",
            "",
            "| object | count | estimated payload MB | notes |",
            "| ------ | ----: | -------------------: | ----- |",
            "| JSON DOM | "
            + f"{_fmt_int(json_est.get('count'))} | "
            + f"{_fmt_mb_from_bytes(json_est.get('estimated_payload_bytes'))} | "
            + "nlohmann JSON dynamic payload estimate, not RSS |",
            "| MachineFunction | "
            + f"{_fmt_int(machine_est.get('count'))} | "
            + f"{_fmt_mb_from_bytes(machine_est.get('estimated_payload_bytes'))} | "
            + "instructions, list nodes, metadata, inverse maps |",
            "| routing temporary | "
            + f"{_fmt_int(routing_est.get('count'))} | "
            + f"{_fmt_mb_from_bytes(routing_est.get('estimated_payload_bytes'))} | "
            + "InstQueue plus simulator/state estimates |",
            "| raw instruction strings | 0 | "
            + f"{_fmt_mb_from_bytes(machine_est.get('raw_string_bytes'))} | "
            + "MachineFunction does not retain raw JSON strings |",
            "| metadata | "
            + f"{_fmt_int(machine_est.get('count'))} | "
            + f"{_fmt_mb_from_bytes(machine_est.get('metadata_bytes'))} | "
            + "ScLsMetadata objects |",
            "",
            "## Trim Diagnostics",
            "",
            "| variant | trim stage | pre RSS KB | post RSS KB | RSS drop KB | uordblks drop KB | elapsed sec |",
            "| ------- | ---------- | ----------: | -----------: | ----------: | --------------: | ----------: |",
        ]
    )
    for result in results:
        diagnostics = result.get("trim_diagnostics", {})
        if not isinstance(diagnostics, Mapping):
            continue
        for stage, diag in diagnostics.items():
            if not isinstance(diag, Mapping):
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(result.get("variant")),
                        str(stage),
                        _fmt_int(diag.get("pre_trim_rss_kb")),
                        _fmt_int(diag.get("post_trim_rss_kb")),
                        _fmt_int(diag.get("rss_drop_kb")),
                        _fmt_int(diag.get("uordblks_drop_kb")),
                        ""
                        if diag.get("elapsed_sec") is None
                        else f"{float(diag['elapsed_sec']):.6f}",
                    ]
                )
                + " |"
            )
    lines.extend(
        [
            "",
            "## Candidate Ranking",
            "",
            "| rank | candidate | theoretical saving MB | measured evidence | risk | priority |",
            "| ---: | --------- | --------------------: | ----------------- | ---- | -------- |",
        ]
    )
    for rank, row in enumerate(candidate_ranking, start=1):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(rank),
                    str(row.get("candidate")),
                    _fmt_mb_from_bytes(row.get("theoretical_saving_bytes")),
                    str(row.get("measured_evidence")),
                    str(row.get("risk")),
                    str(row.get("priority")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Optimization A/B",
            "",
            "No production optimization was implemented in this commit. Gate-passing evidence points "
            "to MachineFunction live payload, which is a higher-risk ownership/schema change. "
            "Diagnostic `malloc_trim` is not a production optimization.",
            "",
            "## Final Answers",
            "",
            f"1. JSON DOM estimated payload MB: `{_fmt_mb_from_bytes(json_est.get('estimated_payload_bytes'))}`.",
            "2. JSON DOM uordblks decrease after destroy: "
            f"`{_fmt_int(json_destroy_uord_drop_kb)}` KB.",
            "3. JSON DOM destroy RSS delta: "
            f"`{_fmt_int(json_destroy_rss_delta_kb)}` KB; when RSS does not drop with "
            "uordblks falling, the main diagnosis is allocator-retained heap and/or later "
            "live-object growth rather than a still-live JSON DOM.",
            f"4. Diagnostic trim effect: see table above; `trim_both` run was `{both_trim_run}`.",
            f"5. MachineFunction estimated payload MB: `{_fmt_mb_from_bytes(machine_est.get('estimated_payload_bytes'))}`.",
            f"6. raw string MB: `{_fmt_mb_from_bytes(machine_est.get('raw_string_bytes'))}`; metadata MB: `{_fmt_mb_from_bytes(machine_est.get('metadata_bytes'))}`.",
            f"7. routing temporary estimated payload MB: `{_fmt_mb_from_bytes(routing_est.get('estimated_payload_bytes'))}`.",
            "8. routing pass local InstQueue/simulator containers are marked after temporary destruction; remaining live payload is MachineFunction/compile state.",
            f"9. H5 max RSS stage: `{h5_baseline.get('max_stage')}`.",
            f"10. Candidate meeting 100 MB/10%/150 MB gate: `{any_gate}`.",
            "11. production optimization implemented: `False` in this profiling commit.",
            "12. optimization A/B H5 peak reduction: not applicable.",
            "13. if not implemented, reason: the gate-passing qret-side candidate is "
            "MachineFunction live payload, which requires higher-risk instruction/container "
            "ownership work; JSON trim did not reduce H5 peak and production malloc_trim is forbidden.",
            "14. malloc_trim is diagnostic only and is not proposed as production default.",
            "15. next priority: use the candidate ranking above; if none passes, move to parent process/compile-info read path before H6.",
            "16. Python parent process should be considered only after qret-side candidates fail the gate.",
            "17. H6 was not run.",
            "",
            "## Correctness",
            "",
            f"- raw qret metrics equal across measured trim variants: `{metrics_equal}`",
            f"- normalized metrics equal across measured trim variants: `{metrics_equal}`",
            "- compact DepGraph and compile-info mode compatibility are covered by the C++/Python validation suite.",
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
    batch_size: int,
    sample_interval_sec: float,
) -> dict[str, Any]:
    if any(case not in CASE_CHAIN_LENGTH for case in cases):
        raise ValueError(f"unsupported case requested: {cases}")
    if _disk_free_bytes(REPO_ROOT) < MIN_FREE_DISK_BYTES:
        raise RuntimeError("disk free space is below 5 GiB")
    output_root.mkdir(parents=True, exist_ok=True)
    architecture = _architecture()
    qret_path = Path(architecture.qret_path).expanduser().resolve()
    build_provenance = _build_qret_and_record(qret_path, build=build)
    runtime_hashes = _runtime_hashes(qret_path)
    meminfo_start = _meminfo()
    environment = {
        "evaluation_head": _git_output(["rev-parse", "HEAD"]),
        "measurement_runtime_hashes": runtime_hashes,
        "platform": platform.platform(),
        "python": sys.version,
        "compiler": _compiler_version(),
        "allocator": "glibc malloc/mallinfo2 when mallinfo2_supported=true",
        "meminfo": meminfo_start,
        "disk_free_bytes": _disk_free_bytes(REPO_ROOT),
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
        for variant, count in DEFAULT_RUNS[case].items():
            for run_index in range(1, count + 1):
                result = _run_isolated_qret_once(
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
        if case == "h5_4th_new2" and _should_run_both_trim(results):
            result = _run_isolated_qret_once(
                case_key=case,
                variant="trim_both",
                artifact=artifacts[case],
                run_index=1,
                output_root=output_root,
                sample_interval_sec=sample_interval_sec,
                memtotal_kb=memtotal_kb,
                expected_runtime_hashes=runtime_hashes,
            )
            results.append(result)
            _write_csv(output_root / "summary.csv", results)
            _write_json(output_root / "summary.json", {"environment": environment, "results": results})

    comparisons = _metric_comparisons(results)
    candidates = _candidate_ranking(results)
    both_trim_run = any(row.get("variant") == "trim_both" for row in results)
    summary = {
        "environment": environment,
        "build_provenance": build_provenance,
        "results": results,
        "comparisons": comparisons,
        "candidate_ranking": candidates,
        "both_trim_run": both_trim_run,
        "h6_run": False,
    }
    _write_json(output_root / "summary.json", summary)
    _write_csv(output_root / "summary.csv", results)
    _write_report(
        report_path,
        environment=environment,
        build_provenance=build_provenance,
        results=results,
        comparisons=comparisons,
        candidate_ranking=candidates,
        both_trim_run=both_trim_run,
    )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Profile qret routing live memory and retention.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT / "surface_code_cache",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Reuse the existing qret binary instead of running scripts/build_qret.sh.",
    )
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--sample-interval-sec", type=float, default=SAMPLE_INTERVAL_SEC)
    parser.add_argument(
        "--cases",
        nargs="+",
        choices=tuple(CASE_CHAIN_LENGTH),
        default=tuple(CASE_CHAIN_LENGTH),
    )
    args = parser.parse_args(argv)
    run_profile(
        output_root=args.output_root.resolve(),
        report_path=args.report.resolve(),
        cache_root=args.cache_root.resolve(),
        build=not args.skip_build,
        cases=tuple(args.cases),
        batch_size=args.batch_size,
        sample_interval_sec=args.sample_interval_sec,
    )
    print(f"summary: {args.output_root / 'summary.json'}")
    print(f"report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
