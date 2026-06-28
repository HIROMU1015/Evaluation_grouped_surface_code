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
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import profile_qret_routing_live_memory as base

from trotterlib import surface_code as sc


DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "qret_magic_path_memory"
DEFAULT_REPORT_PATH = REPO_ROOT / "docs" / "benchmarks" / "qret_magic_path_memory_audit.md"
DEFAULT_SAMPLE_INTERVAL_SEC = 0.020
ONE_MB = 1024 * 1024
CASE_LABEL = "4th(new_2)"
CASE_CHAIN_LENGTH = {
    "h4_4th_new2": 4,
    "h5_4th_new2": 5,
}
RUN_MATRIX = (
    ("h4_4th_new2", "profile_off", False),
    ("h4_4th_new2", "profile_on", True),
    ("h5_4th_new2", "profile_on", True),
)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "case",
        "variant",
        "run_index",
        "returncode",
        "elapsed_seconds",
        "qret_peak_rss_kb",
        "tree_peak_rss_kb",
        "max_rss_stage",
        "compile_info_size_bytes",
        "magic_path_profile_present",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _git_output(args: Sequence[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def _meminfo() -> dict[str, int]:
    ret: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, value = line.split(":", 1)
            parts = value.strip().split()
            if parts:
                ret[key] = int(parts[0])
    except OSError:
        return {}
    return ret


def _validate_cases(cases: Sequence[str]) -> tuple[str, ...]:
    invalid = [case for case in cases if case not in CASE_CHAIN_LENGTH]
    if invalid:
        if any(case.lower().startswith("h6") for case in invalid):
            raise ValueError("H6 is intentionally rejected for this audit")
        raise ValueError(f"unknown case(s): {', '.join(invalid)}")
    return tuple(cases)


def _architecture() -> sc.SurfaceCodeArchitecture:
    return sc.SurfaceCodeArchitecture(
        compile_mode=base.COMPILE_MODE,
        skip_compile_output=True,
        compile_info_output_mode="summary",
    )


def _profile_env(env: dict[str, str], *, enabled: bool, magic_profile_path: Path) -> None:
    env["QRET_SUMMARY_TIME_SERIES_IMPL"] = "legacy_timeseries"
    env["QRET_DEP_GRAPH_IMPL"] = "compact"
    env["QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING"] = "1"
    env["QRET_RSS_DIAGNOSTIC_TRIM_STAGE"] = "none"
    env["QRET_PROFILE_MAGIC_PATHS"] = "1" if enabled else "0"
    if enabled:
        env["QRET_MAGIC_PATH_PROFILE_JSON"] = str(magic_profile_path)
    else:
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


def _load_magic_profile(path: Path, profile_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    for row in reversed(profile_rows):
        if row.get("stage") == "magic_path_profile" and isinstance(row.get("extra"), Mapping):
            return dict(row["extra"])
    return {}


def _profile_max_stage(profile_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return base._profile_max_stage(profile_rows)


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


def _representation_rows(profile: Mapping[str, Any]) -> list[dict[str, Any]]:
    estimates = profile.get("representation_estimates", {})
    if not isinstance(estimates, Mapping):
        return []
    rows = estimates.get("rows", [])
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _risk_weight(value: Any) -> int:
    return {"low": 0, "medium": 1, "high": 2, "none": 0}.get(str(value), 3)


def _candidate_family(name: str) -> str:
    if name.startswith("std::vector<Coord3D>"):
        return "std::vector<Coord3D>"
    if name.startswith("inline"):
        return "inline small buffer"
    return name


def _candidate_ranking(
    profile: Mapping[str, Any],
    *,
    qret_peak_rss_kb: int | None = None,
) -> list[dict[str, Any]]:
    estimates = profile.get("representation_estimates", {})
    current = 0
    if isinstance(estimates, Mapping):
        current = int(estimates.get("current_list_aligned_bytes") or 0)
    peak_gate_bytes = 30 * ONE_MB
    best_by_family: dict[str, dict[str, Any]] = {}
    for row in _representation_rows(profile):
        name = str(row.get("representation", ""))
        if name.startswith("std::list<Coord3D> current"):
            continue
        saving = int(row.get("saving_bytes") or 0)
        saving_pct = 0.0 if not current else 100.0 * float(saving) / float(current)
        peak_saving_kb = saving // 1024 if qret_peak_rss_kb is not None else None
        gate = saving >= peak_gate_bytes or saving_pct >= 40.0
        candidate = {
            "candidate": _candidate_family(name),
            "scenario": name,
            "theoretical_saving_bytes": saving,
            "ancilla_path_saving_percent": saving_pct,
            "qret_peak_theoretical_saving_kb": peak_saving_kb,
            "passes_gate": gate,
            "semantic_risk": row.get("semantic_risk"),
            "implementation_risk": row.get("implementation_risk"),
        }
        family = str(candidate["candidate"])
        old = best_by_family.get(family)
        if old is None or int(old["theoretical_saving_bytes"]) < saving:
            best_by_family[family] = candidate
    rows = list(best_by_family.values())
    rows.sort(
        key=lambda row: (
            not row["passes_gate"],
            _risk_weight(row["semantic_risk"]),
            _risk_weight(row["implementation_risk"]),
            -int(row["theoretical_saving_bytes"]),
        )
    )
    return rows[:2]


def _aggregate(results: Sequence[Mapping[str, Any]], case: str, variant: str) -> dict[str, Any]:
    rows = [row for row in results if row.get("case") == case and row.get("variant") == variant]
    return {
        "case": case,
        "variant": variant,
        "runs": len(rows),
        "median_elapsed_seconds": statistics.median(
            [float(row["elapsed_seconds"]) for row in rows if row.get("elapsed_seconds") is not None]
        )
        if rows
        else None,
        "median_qret_peak_rss_kb": statistics.median(
            [int(row["qret_peak_rss_kb"]) for row in rows if row.get("qret_peak_rss_kb") is not None]
        )
        if rows
        else None,
        "median_tree_peak_rss_kb": statistics.median(
            [int(row["tree_peak_rss_kb"]) for row in rows if row.get("tree_peak_rss_kb") is not None]
        )
        if rows
        else None,
    }


def _prepare_artifacts(cases: Sequence[str], *, cache_root: Path, batch_size: int) -> dict[str, sc.SurfaceCodeStepArtifact]:
    previous_cache_dir = sc.SURFACE_CODE_CACHE_DIR
    previous_batch_size = sc.SURFACE_CODE_RZ_HELPER_BATCH_SIZE
    sc.SURFACE_CODE_CACHE_DIR = cache_root
    sc.SURFACE_CODE_RZ_HELPER_BATCH_SIZE = int(batch_size)
    try:
        architecture = _architecture()
        artifacts: dict[str, sc.SurfaceCodeStepArtifact] = {}
        for case in cases:
            artifacts[case] = sc.prepare_grouped_surface_code_step_artifact(
                sc.grouped_hchain_ham_name(CASE_CHAIN_LENGTH[case]),
                CASE_LABEL,
                architecture=architecture,
            )
        return artifacts
    finally:
        sc.SURFACE_CODE_CACHE_DIR = previous_cache_dir
        sc.SURFACE_CODE_RZ_HELPER_BATCH_SIZE = previous_batch_size


def _run_qret_once(
    *,
    case_key: str,
    variant: str,
    profile_enabled: bool,
    artifact: sc.SurfaceCodeStepArtifact,
    run_index: int,
    output_root: Path,
    sample_interval_sec: float,
    memtotal_kb: int | None,
    expected_runtime_hashes: Mapping[str, Any],
) -> dict[str, Any]:
    architecture = _architecture()
    run_dir = output_root / "runs" / case_key / variant / f"run_{run_index:02d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    profile_jsonl = run_dir / "qret_rss_profile.jsonl"
    samples_jsonl = run_dir / "process_tree_samples.jsonl"
    magic_profile_path = run_dir / "magic_path_profile.json"
    compile_yaml_path = run_dir / "compile.yaml"
    compile_info_path = run_dir / "compile_info.json"
    stdout_path = run_dir / "stdout.txt"
    stderr_path = run_dir / "stderr.txt"
    output_path = Path(os.devnull)
    for path in (
        profile_jsonl,
        samples_jsonl,
        magic_profile_path,
        compile_info_path,
        stdout_path,
        stderr_path,
    ):
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
    _profile_env(env, enabled=profile_enabled, magic_profile_path=magic_profile_path)
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

    profile_rows = base.qret_profile._load_jsonl(profile_jsonl)
    sample_summary = base.compact_profile._summarize_samples(sample_rows, parent_pid=process.pid)
    gnu_maxrss = base.qret_profile._parse_gnu_time_maxrss(stderr)
    magic_profile = _load_magic_profile(magic_profile_path, profile_rows)
    max_stage = _profile_max_stage(profile_rows)
    qret_peak = max(
        [value for value in (gnu_maxrss, sample_summary.get("sampled_peak_qret_vmrss_kb")) if value is not None],
        default=None,
    )
    result = {
        "case": case_key,
        "variant": variant,
        "profile_enabled": profile_enabled,
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
        "profile_summary": base.calc_profile._summarize_profile(profile_rows),
        "profile_rows": profile_rows,
        "max_rss_stage": max_stage.get("stage"),
        "max_rss_stage_vmrss_kb": max_stage.get("vmrss_kb"),
        "compile_info_path": str(compile_info_path),
        "compile_info_size_bytes": compile_info_path.stat().st_size
        if compile_info_path.exists()
        else None,
        "profile_jsonl": str(profile_jsonl),
        "samples_jsonl": str(samples_jsonl),
        "magic_path_profile_path": str(magic_profile_path),
        "magic_path_profile_present": bool(magic_profile),
        "magic_path_profile": magic_profile,
        "pipeline_path": str(compile_yaml_path),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "normalized_metrics": _metric_summary(compile_info_path),
        "raw_resource_metrics": _raw_resource_metrics(compile_info_path),
        "artifact": base.compact_profile._artifact_summary(artifact),
    }
    _write_json(run_dir / "summary.json", result)
    if process.returncode != 0:
        raise RuntimeError(f"qret failed for {case_key} {variant}: {stderr[-4000:]}")
    return result


def _first_result(results: Sequence[Mapping[str, Any]], case: str, variant: str) -> Mapping[str, Any]:
    return next((row for row in results if row.get("case") == case and row.get("variant") == variant), {})


def _ownership_audit_rows() -> list[tuple[str, str, str, str, str, str]]:
    return [
        (
            "condition list",
            "ScLsInstructionBase::condition_list_",
            "constructor/FromJson",
            "SetCondition in pruning or direct construction",
            "validation, simulator, queue dependencies, compile-info",
            "DefaultJson condition",
        ),
        (
            "qtarget",
            "LatticeSurgeryMagic::q_",
            "New/FromJson/lowering",
            "SetQubitList API; no routing path-local mutation found",
            "runnability, route search, compile-info",
            "DefaultJson qtarget",
        ),
        (
            "mtarget",
            "LatticeSurgeryMagic::m_",
            "New/FromJson",
            "SetMagicFactory in 2D magic routing",
            "MagicFactory availability and RunLatticeSurgeryMagic",
            "DefaultJson mtarget",
        ),
        (
            "basis_list",
            "LatticeSurgeryMagic::basis_list_",
            "New/FromJson/lowering",
            "no setter; copied when 3D magic is replaced by LatticeSurgery",
            "runnability and boundary checks",
            "ToJson basis_list",
        ),
        (
            "ancilla/path",
            "LatticeSurgeryMagic::ancilla_",
            "New/FromJson; route result assigned during routing",
            "SetPath only; temporary route may pop endpoints before assignment",
            "runnability, RunLatticeSurgeryMagic, compile-info, pipeline-state",
            "DefaultJson ancilla",
        ),
        (
            "metadata",
            "ScLsInstructionBase::metadata_",
            "default construction/FromJson",
            "MetadataMut during scheduling",
            "compile-info, pipeline-state, debug output",
            "DefaultJson metadata",
        ),
    ]


def _mutation_audit_rows() -> list[tuple[str, str, str, str, str]]:
    return [
        (
            "SearchLatticeSurgeryMagicPath2DBFSAndRun",
            "routing",
            "copy route.logical_path, pop_front, pop_back, SetMagicFactory, SetPath",
            "no",
            "no stored-path iterator stability",
        ),
        (
            "SearchLatticeSurgeryMagicPath2DSteinerAndRun",
            "routing",
            "SetMagicFactory and SetPath from SearchRoute::Ancilla2D",
            "no",
            "no",
        ),
        (
            "SearchLatticeSurgeryMagicPath3DAndRun",
            "routing",
            "copy route.logical_path, pop endpoints, create LatticeSurgery, erase magic",
            "no for retained magic path",
            "queue handles instruction replacement, not path nodes",
        ),
        (
            "LatticeSurgeryMagic::FromJson",
            "pipeline load",
            "JsonToT builds list sequentially",
            "no",
            "no",
        ),
        (
            "IsLatticeSurgeryMagicRunnable / RunLatticeSurgeryMagic",
            "routing simulation",
            "read-only iteration over Path()",
            "no",
            "no",
        ),
        (
            "DefaultJson / ToString",
            "serialization/debug",
            "read-only iteration over Path()",
            "no",
            "no",
        ),
    ]


def _write_report(path: Path, summary: Mapping[str, Any]) -> None:
    environment = summary.get("environment", {})
    results = summary.get("results", [])
    comparisons = summary.get("comparisons", {})
    h4_off = _first_result(results, "h4_4th_new2", "profile_off")
    h4_on = _first_result(results, "h4_4th_new2", "profile_on")
    h5_on = _first_result(results, "h5_4th_new2", "profile_on")
    profile = h5_on.get("magic_path_profile") or h4_on.get("magic_path_profile") or {}
    memory = profile.get("magic_operand_memory", {}) if isinstance(profile, Mapping) else {}
    all_path = profile.get("all_machine_ancilla_path_memory", {}) if isinstance(profile, Mapping) else {}
    candidates = summary.get("candidate_ranking", [])

    lines = [
        "# qret LATTICE_SURGERY_MAGIC Path Memory Audit",
        "",
        "This is a read-only profiling audit. It does not change the production instruction schema, routing algorithm, operand API, serialization schema, or path representation. H6 was not run.",
        "",
        "## Environment",
        "",
        f"- Evaluation HEAD at run start: `{environment.get('evaluation_head')}`",
        f"- qret executable hash: `{environment.get('runtime_hashes', {}).get('qret_executable_hash')}`",
        f"- libqret-core hash: `{environment.get('runtime_hashes', {}).get('qret_core_library_hash')}`",
        f"- output root: `{environment.get('output_root')}`",
        f"- sample interval: `{environment.get('sample_interval_sec')}` sec",
        f"- compile-info mode: `summary`",
        f"- summary TimeSeries: `summary_legacy_timeseries`",
        f"- DepGraph: `compact`",
        f"- inverse map release: `QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING=1`",
        f"- pipeline-state output: `skip`",
        "",
        "## Ownership Audit",
        "",
        "| field/container | owner | construction | mutation | last use | serialization use |",
        "| --------------- | ----- | ------------ | -------- | -------- | ----------------- |",
    ]
    for row in _ownership_audit_rows():
        lines.append("| " + " | ".join(row) + " |")
    lines.extend(
        [
            "",
            "## Routing Mutation Audit",
            "",
            "| call site | stage | operation | random insertion needed | iterator stability needed |",
            "| --------- | ----- | --------- | ----------------------- | ------------------------- |",
        ]
    )
    for row in _mutation_audit_rows():
        lines.append("| " + " | ".join(row) + " |")
    lines.extend(
        [
            "",
            "- `std::list` required for retained `LATTICE_SURGERY_MAGIC::ancilla_`: `no` based on audited call sites.",
            "- Generated path read-only after assignment: `yes` for surviving `LATTICE_SURGERY_MAGIC` instructions.",
            "- Contiguous storage feasibility: `yes`, conditional on preserving order, serialization, and route-search temporary APIs.",
            "",
            "## H4 Instrumentation Check",
            "",
            "| variant | profile enabled | qret peak KB | elapsed s | magic profile | raw equal | normalized equal |",
            "| ------- | --------------: | -----------: | --------: | ------------: | --------: | ---------------: |",
            "| profile_off | 0 | "
            + f"{_fmt_int(h4_off.get('qret_peak_rss_kb'))} | {_fmt_float(h4_off.get('elapsed_seconds'))} | "
            + f"{h4_off.get('magic_path_profile_present')} |  |  |",
            "| profile_on | 1 | "
            + f"{_fmt_int(h4_on.get('qret_peak_rss_kb'))} | {_fmt_float(h4_on.get('elapsed_seconds'))} | "
            + f"{h4_on.get('magic_path_profile_present')} | "
            + f"{comparisons.get('h4_profile_on_vs_off', {}).get('raw', {}).get('all_equal')} | "
            + f"{comparisons.get('h4_profile_on_vs_off', {}).get('normalized', {}).get('all_equal')} |",
            "",
            "## H5 Profile Run",
            "",
            f"- qret peak RSS: `{_fmt_int(h5_on.get('qret_peak_rss_kb'))}` KB",
            f"- process tree peak RSS: `{_fmt_int(h5_on.get('tree_peak_rss_kb'))}` KB",
            f"- elapsed: `{_fmt_float(h5_on.get('elapsed_seconds'))}` s",
            f"- max RSS stage: `{h5_on.get('max_rss_stage')}`",
            f"- compile_info bytes: `{_fmt_int(h5_on.get('compile_info_size_bytes'))}`",
            "- Note: H5 peak was captured with profiling enabled, so it includes profiling overhead.",
            "",
            "## Magic Path Distribution",
            "",
            f"- path count: `{_fmt_int(profile.get('path_count'))}`",
            f"- total coordinate count: `{_fmt_int(profile.get('total_coordinate_count'))}`",
            f"- length min/median/mean/max: `{profile.get('length_min')}` / `{_fmt_float(profile.get('length_median'))}` / `{_fmt_float(profile.get('length_mean'))}` / `{profile.get('length_max')}`",
            f"- p75/p90/p95/p99: `{profile.get('length_p75')}` / `{profile.get('length_p90')}` / `{profile.get('length_p95')}` / `{profile.get('length_p99')}`",
            "",
            "| bucket | count |",
            "| ------ | ----: |",
        ]
    )
    for bucket, count in (profile.get("length_buckets", {}) or {}).items():
        lines.append(f"| {bucket} | {_fmt_int(count)} |")
    coords = profile.get("coordinates", {}) if isinstance(profile, Mapping) else {}
    lines.extend(
        [
            "",
            "## Coordinate Distribution",
            "",
            "| axis | min | max | unique | negative | int8 | int16 |",
            "| ---- | --: | --: | -----: | -------: | ---: | ----: |",
        ]
    )
    for axis in ("x", "y", "z", "dx", "dy", "dz"):
        item = coords.get(axis, {}) if isinstance(coords, Mapping) else {}
        lines.append(
            f"| {axis} | {_fmt_int(item.get('min'))} | {_fmt_int(item.get('max'))} | "
            f"{_fmt_int(item.get('unique_count'))} | {item.get('has_negative')} | "
            f"{item.get('fits_int8')} | {item.get('fits_int16')} |"
        )
    lines.extend(
        [
            f"- unit delta ratio: `{_fmt_float(coords.get('unit_delta_percent'))}%`",
            f"- Manhattan distance 1 ratio: `{_fmt_float(coords.get('manhattan_one_percent'))}%`",
            f"- consecutive duplicate coordinates: `{_fmt_int(coords.get('same_coordinate_consecutive_count'))}`",
            "",
            "## Duplication",
            "",
            "| mode | unique paths/shapes | duplicate count | duplicate % | most frequent |",
            "| ---- | ------------------: | --------------: | ----------: | ------------: |",
        ]
    )
    for key, label in (
        ("duplicates_exact", "exact"),
        ("duplicates_reverse_canonical", "reverse-canonical"),
        ("duplicates_relative_shape", "relative-shape"),
    ):
        item = profile.get(key, {}) if isinstance(profile, Mapping) else {}
        lines.append(
            f"| {label} | {_fmt_int(item.get('unique_count'))} | {_fmt_int(item.get('duplicate_count'))} | "
            f"{_fmt_float(item.get('duplicate_percent'))} | {_fmt_int(item.get('most_frequent_count'))} |"
        )
    exact_dup = profile.get("duplicates_exact", {}) if isinstance(profile, Mapping) else {}
    lines.extend(
        [
            "",
            f"- exact hash distinct collision count: `{_fmt_int(exact_dup.get('hash_collision_distinct_key_count'))}`",
            f"- exact hash collision fallback used: `{exact_dup.get('hash_collision_fallback_used')}`",
            "",
            "## Top Exact Path Frequencies",
            "",
            "| rank | frequency | length | first coord | last coord |",
            "| ---: | --------: | -----: | ----------- | ---------- |",
        ]
    )
    for index, row in enumerate(exact_dup.get("top_frequencies", []) or [], start=1):
        lines.append(
            f"| {index} | {_fmt_int(row.get('frequency'))} | {_fmt_int(row.get('length'))} | "
            f"`{row.get('first')}` | `{row.get('last')}` |"
        )
    prefix_suffix = profile.get("prefix_suffix", {}) if isinstance(profile, Mapping) else {}
    lines.extend(
        [
            "",
            "## Prefix/Suffix Sharing",
            "",
            "| side | length | total | shared paths | shared keys |",
            "| ---- | -----: | ----: | -----------: | ----------: |",
        ]
    )
    for side in ("prefix", "suffix"):
        side_data = prefix_suffix.get(side, {}) if isinstance(prefix_suffix, Mapping) else {}
        for key, item in side_data.items():
            lines.append(
                f"| {side} | {key} | {_fmt_int(item.get('total_count'))} | "
                f"{_fmt_int(item.get('shared_path_count'))} | {_fmt_int(item.get('shared_key_count'))} |"
            )
    seg = profile.get("segments", {}) if isinstance(profile, Mapping) else {}
    lines.extend(
        [
            "",
            "## Segment Compressibility",
            "",
            f"- total segments: `{_fmt_int(seg.get('total_segment_count'))}`",
            f"- coordinates per segment mean: `{_fmt_float(seg.get('coordinates_per_segment_mean'))}`",
            f"- one segment or less: `{_fmt_float(seg.get('path_percent_1_segment_or_less'))}%`",
            f"- two segments or less: `{_fmt_float(seg.get('path_percent_2_segments_or_less'))}%`",
            f"- four segments or less: `{_fmt_float(seg.get('path_percent_4_segments_or_less'))}%`",
            f"- max segment count: `{_fmt_int(seg.get('max_segment_count'))}`",
            "",
            "## Memory Breakdown",
            "",
            "| component | observed count | estimated bytes | MB | note |",
            "| --------- | -------------: | --------------: | --: | ---- |",
            f"| instruction object | {_fmt_int(memory.get('instruction_count'))} | {_fmt_int(memory.get('magic_instruction_object_bytes_estimated'))} | {_fmt_mb_from_bytes(memory.get('magic_instruction_object_bytes_estimated'))} | includes list object bodies |",
            f"| qtarget list nodes | {_fmt_int(memory.get('qtarget_elements'))} | {_fmt_int(memory.get('qtarget_list_node_bytes_estimated'))} | {_fmt_mb_from_bytes(memory.get('qtarget_list_node_bytes_estimated'))} | sizeof estimate |",
            f"| basis list nodes | {_fmt_int(memory.get('basis_elements'))} | {_fmt_int(memory.get('basis_list_node_bytes_estimated'))} | {_fmt_mb_from_bytes(memory.get('basis_list_node_bytes_estimated'))} | LSM-specific operand |",
            f"| condition list nodes | {_fmt_int(memory.get('condition_elements'))} | {_fmt_int(memory.get('condition_list_node_bytes_estimated'))} | {_fmt_mb_from_bytes(memory.get('condition_list_node_bytes_estimated'))} | base operand |",
            f"| ccreate list nodes | {_fmt_int(memory.get('ccreate_elements'))} | {_fmt_int(memory.get('ccreate_list_node_bytes_estimated'))} | {_fmt_mb_from_bytes(memory.get('ccreate_list_node_bytes_estimated'))} | measurement output |",
            f"| mtarget list nodes | {_fmt_int(memory.get('mtarget_elements'))} | {_fmt_int(memory.get('mtarget_list_node_bytes_estimated'))} | {_fmt_mb_from_bytes(memory.get('mtarget_list_node_bytes_estimated'))} | magic factory |",
            f"| path Coord3D payload | {_fmt_int(memory.get('path_coordinate_elements'))} | {_fmt_int(memory.get('path_coord_payload_bytes'))} | {_fmt_mb_from_bytes(memory.get('path_coord_payload_bytes'))} | raw data only |",
            f"| path list pointer overhead | {_fmt_int(memory.get('path_coordinate_elements'))} | {_fmt_int(memory.get('path_list_node_pointer_overhead_bytes'))} | {_fmt_mb_from_bytes(memory.get('path_list_node_pointer_overhead_bytes'))} | two pointers per node estimate |",
            f"| path allocator alignment overhead | {_fmt_int(memory.get('path_coordinate_elements'))} | {_fmt_int(memory.get('path_list_node_allocator_alignment_overhead_estimated'))} | {_fmt_mb_from_bytes(memory.get('path_list_node_allocator_alignment_overhead_estimated'))} | aligned-node estimate |",
            f"| path list object bodies | {_fmt_int(memory.get('instruction_count'))} | {_fmt_int(memory.get('path_list_object_bytes_in_instruction_object'))} | {_fmt_mb_from_bytes(memory.get('path_list_object_bytes_in_instruction_object'))} | inside instruction object |",
            "",
            "All byte totals except counts are estimates from `sizeof` and a simple list-node model. The C++ standard does not define `std::list` node layout.",
            "",
            "## All MachineFunction Ancilla/Path",
            "",
            f"- LATTICE_SURGERY_MAGIC ancilla/path bytes: `{_fmt_mb_from_bytes(all_path.get('lattice_surgery_magic_ancilla_path_bytes'))}` MB",
            f"- CNOT ancilla/path bytes: `{_fmt_mb_from_bytes(all_path.get('cnot_ancilla_path_bytes'))}` MB",
            f"- other instruction ancilla/path bytes: `{_fmt_mb_from_bytes(all_path.get('other_instruction_ancilla_path_bytes'))}` MB",
            f"- all ancilla/path bytes: `{_fmt_mb_from_bytes(all_path.get('all_ancilla_path_bytes'))}` MB",
            "",
            "## Theoretical Representation Sizes",
            "",
            "| representation | estimated MB | saving MB | saving % | semantic risk | implementation risk |",
            "| -------------- | -----------: | --------: | -------: | ------------- | ------------------- |",
        ]
    )
    for row in _representation_rows(profile):
        lines.append(
            f"| {row.get('representation')} | {_fmt_mb_from_bytes(row.get('estimated_bytes'))} | "
            f"{_fmt_mb_from_bytes(row.get('saving_bytes'))} | {_fmt_float(row.get('saving_percent'))} | "
            f"{row.get('semantic_risk')} | {row.get('implementation_risk')} |"
        )
    lines.extend(
        [
            "",
            "These are ancilla/path-field estimates. RSS can fall by less because malloc arenas may retain freed pages and because replacing containers changes allocation timing.",
            "",
            "## Candidate Ranking",
            "",
            "| rank | candidate | theoretical saving MB | ancilla/path saving % | required code scope | semantic risk |",
            "| ---: | --------- | --------------------: | --------------------: | ------------------- | ------------- |",
        ]
    )
    for index, row in enumerate(candidates, start=1):
        lines.append(
            f"| {index} | {row.get('candidate')} | {_fmt_mb_from_bytes(row.get('theoretical_saving_bytes'))} | "
            f"{_fmt_float(row.get('ancilla_path_saving_percent'))} | path container/API-compatible storage | "
            f"{row.get('semantic_risk')} |"
        )
    lines.extend(
        [
            "",
            "## Conclusions",
            "",
            f"1. H4 raw metrics equal: `{comparisons.get('h4_profile_on_vs_off', {}).get('raw', {}).get('all_equal')}`.",
            f"2. H4 normalized metrics equal: `{comparisons.get('h4_profile_on_vs_off', {}).get('normalized', {}).get('all_equal')}`.",
            "3. The next implementation candidate should be selected from the ranking above, capped at two candidates.",
            "4. H6 was not run.",
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
    batch_size: int,
    sample_interval_sec: float,
    cases: Sequence[str],
) -> dict[str, Any]:
    cases = _validate_cases(cases)
    output_root.mkdir(parents=True, exist_ok=True)
    architecture = _architecture()
    qret_path = Path(architecture.qret_path).expanduser().resolve()
    build_provenance = base._build_qret_and_record(qret_path, build=build)
    runtime_hashes = base._runtime_hashes(qret_path)
    meminfo_start = _meminfo()
    environment = {
        "evaluation_head": _git_output(["rev-parse", "HEAD"]),
        "runtime_hashes": runtime_hashes,
        "platform": platform.platform(),
        "python": sys.version,
        "meminfo": meminfo_start,
        "output_root": str(output_root.resolve()),
        "batch_size": batch_size,
        "sample_interval_sec": sample_interval_sec,
        "h6_run": False,
    }
    artifacts = _prepare_artifacts(cases, cache_root=cache_root, batch_size=batch_size)
    environment["artifacts"] = {
        case: base.compact_profile._artifact_summary(artifact) for case, artifact in artifacts.items()
    }
    results: list[dict[str, Any]] = []
    memtotal_kb = meminfo_start.get("MemTotal")
    for case_key, variant, enabled in RUN_MATRIX:
        if case_key not in cases:
            continue
        result = _run_qret_once(
            case_key=case_key,
            variant=variant,
            profile_enabled=enabled,
            artifact=artifacts[case_key],
            run_index=1,
            output_root=output_root,
            sample_interval_sec=sample_interval_sec,
            memtotal_kb=memtotal_kb,
            expected_runtime_hashes=runtime_hashes,
        )
        results.append(result)
        _write_csv(output_root / "summary.csv", results)
        _write_json(output_root / "summary.json", {"environment": environment, "results": results})

    comparisons: dict[str, Any] = {}
    h4_off = _first_result(results, "h4_4th_new2", "profile_off")
    h4_on = _first_result(results, "h4_4th_new2", "profile_on")
    if h4_off and h4_on:
        comparisons["h4_profile_on_vs_off"] = _compare_metrics(h4_off, h4_on)
    h5_on = _first_result(results, "h5_4th_new2", "profile_on")
    profile = h5_on.get("magic_path_profile") or h4_on.get("magic_path_profile") or {}
    candidate_ranking = _candidate_ranking(
        profile,
        qret_peak_rss_kb=h5_on.get("qret_peak_rss_kb") if h5_on else None,
    )
    summary = {
        "environment": environment,
        "build_provenance": build_provenance,
        "results": results,
        "aggregates": [
            _aggregate(results, "h4_4th_new2", "profile_off"),
            _aggregate(results, "h4_4th_new2", "profile_on"),
            _aggregate(results, "h5_4th_new2", "profile_on"),
        ],
        "comparisons": comparisons,
        "candidate_ranking": candidate_ranking,
        "h6_run": False,
    }
    _write_json(output_root / "summary.json", summary)
    _write_csv(output_root / "summary.csv", results)
    _write_report(report_path, summary)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit LATTICE_SURGERY_MAGIC path memory without changing production storage."
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--cache-root", type=Path, default=DEFAULT_OUTPUT_ROOT / "surface_code_cache")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--sample-interval-sec", type=float, default=DEFAULT_SAMPLE_INTERVAL_SEC)
    parser.add_argument(
        "--cases",
        nargs="+",
        default=tuple(CASE_CHAIN_LENGTH),
        help="Allowed: h4_4th_new2 h5_4th_new2. H6 is rejected.",
    )
    args = parser.parse_args(argv)
    run_profile(
        output_root=args.output_root.resolve(),
        report_path=args.report.resolve(),
        cache_root=args.cache_root.resolve(),
        build=not args.skip_build,
        batch_size=args.batch_size,
        sample_interval_sec=args.sample_interval_sec,
        cases=args.cases,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
