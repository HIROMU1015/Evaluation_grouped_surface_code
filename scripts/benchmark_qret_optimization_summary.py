#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import re
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

import profile_qret_pre_routing_high_water as high_water  # noqa: E402
import profile_qret_routing_live_memory as live_profile  # noqa: E402
import profile_surface_code_compact_scaling as compact_profile  # noqa: E402


DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "qret_optimization_summary"
DEFAULT_REPORT_PATH = (
    REPO_ROOT / "docs" / "benchmarks" / "qret_optimization_integrity_and_performance_summary.md"
)
DEFAULT_SUMMARY_PATH = REPO_ROOT / "docs" / "benchmarks" / "qret_optimization_summary.json"
DEFAULT_BASELINE_WORKTREE = Path("/tmp/evaluation-baseline-worktree")
EARLIEST_RUNNABLE_BASELINE = "6011635af1db3b3c1c1fa38dbb6affcc9472ee7a"
STABLE_PRE_OPTIMIZATION_BASELINE = "5c52fc649d26c33f027d5ac65ef4f2f0701347d1"
COMPILE_MODE = "ftqc_compile_topology"
PF_FOURTH_NEW2 = "4th(new_2)"
MIN_FREE_DISK_BYTES = 5 * 1024**3
MIN_MEM_AVAILABLE_KB = 1_000_000
STOP_TREE_RSS_FRACTION = 0.85
PROHIBITED_CASE_PREFIXES = ("h6", "h7", "h8", "h9")
PROHIBITED_CHAIN_LENGTHS = {6, 7, 8, 9}
ONE_MB = 1024 * 1024

CASE_SPECS: dict[str, dict[str, Any]] = {
    "h4_2nd": {"chain_length": 4, "pf_label": "2nd", "correctness": True, "performance": False},
    "h4_4th_new2": {
        "chain_length": 4,
        "pf_label": PF_FOURTH_NEW2,
        "correctness": True,
        "performance": True,
    },
    "h5_4th_new2": {
        "chain_length": 5,
        "pf_label": PF_FOURTH_NEW2,
        "correctness": False,
        "performance": True,
    },
}
DEFAULT_CASES = ("h4_2nd", "h4_4th_new2", "h5_4th_new2")
VARIANTS = ("baseline", "final")
CONDITIONS = ("cold", "warm")
SUMMARY_FIELDS = (
    "case",
    "variant",
    "cache_condition",
    "run_index",
    "status",
    "returncode",
    "elapsed_seconds",
    "qret_peak_rss_kb",
    "tree_peak_rss_kb",
    "compile_info_size_bytes",
    "largest_intermediate_file_bytes",
    "total_intermediate_file_bytes",
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


def _validate_cases(cases: Sequence[str]) -> tuple[str, ...]:
    invalid = [case for case in cases if case not in CASE_SPECS]
    prohibited = [case for case in invalid if case.lower().startswith(PROHIBITED_CASE_PREFIXES)]
    if prohibited:
        raise ValueError("H6/H7/H8/H9 execution is prohibited: " + ", ".join(prohibited))
    if invalid:
        raise ValueError("unknown case(s): " + ", ".join(invalid))
    prohibited_lengths = [
        CASE_SPECS[case]["chain_length"]
        for case in cases
        if CASE_SPECS[case]["chain_length"] in PROHIBITED_CHAIN_LENGTHS
        or CASE_SPECS[case]["chain_length"] > 5
    ]
    if prohibited_lengths:
        raise ValueError(
            "H6/H7/H8/H9 chain lengths are prohibited: "
            + ", ".join(str(value) for value in prohibited_lengths)
        )
    return tuple(cases)


def _baseline_selection() -> dict[str, Any]:
    return {
        "earliest_runnable_baseline": {
            "commit": EARLIEST_RUNNABLE_BASELINE,
            "reason": "first commit in this series with vendored qret and scripts/build_qret.sh",
            "selected": False,
        },
        "stable_pre_optimization_baseline": {
            "commit": STABLE_PRE_OPTIMIZATION_BASELINE,
            "reason": (
                "latest profiling-only commit before the first production qret memory "
                "optimization, retaining comparable build and measurement harnesses"
            ),
            "selected": True,
        },
    }


def _architecture(qret_path: Path | None = None) -> sc.SurfaceCodeArchitecture:
    kwargs: dict[str, Any] = {
        "compile_mode": COMPILE_MODE,
        "skip_compile_output": True,
        "compile_info_output_mode": "summary",
    }
    if qret_path is not None:
        kwargs["qret_path"] = qret_path
    return sc.SurfaceCodeArchitecture(**kwargs)


def _case_ham_name(case: str) -> str:
    return sc.grouped_hchain_ham_name(int(CASE_SPECS[case]["chain_length"]))


def _prepare_artifacts(cases: Sequence[str], *, final_qret_path: Path) -> dict[str, sc.SurfaceCodeStepArtifact]:
    architecture = _architecture(final_qret_path)
    artifacts: dict[str, sc.SurfaceCodeStepArtifact] = {}
    for case in cases:
        artifacts[case] = sc.prepare_grouped_surface_code_step_artifact(
            _case_ham_name(case),
            str(CASE_SPECS[case]["pf_label"]),
            architecture=architecture,
        )
    return artifacts


def _compile_passes() -> list[str]:
    return [
        "sc_ls_fixed_v0::init_compile_info",
        "sc_ls_fixed_v0::mapping",
        "sc_ls_fixed_v0::routing",
        "sc_ls_fixed_v0::calc_info_without_topology",
        "sc_ls_fixed_v0::calc_info_with_topology",
        "sc_ls_fixed_v0::dump_compile_info",
    ]


def _pipeline_yaml(
    *,
    artifact: sc.SurfaceCodeStepArtifact,
    topology_path: Path,
    output_path: Path,
    compile_info_path: Path,
    variant: str,
) -> str:
    lines = [
        "source: IR",
        f"input: {artifact.optimized_ir_path}",
        "function: main",
        "target: SC_LS_FIXED_V0",
        f"output: {output_path}",
        f"sc_ls_fixed_v0_topology: {topology_path}",
        "sc_ls_fixed_v0_machine_type: Dim2",
        "sc_ls_fixed_v0_magic_generation_period: 15",
        "sc_ls_fixed_v0_maximum_magic_state_stock: 10000",
        "sc_ls_fixed_v0_entanglement_generation_period: 100",
        "sc_ls_fixed_v0_maximum_entangled_state_stock: 10",
        "sc_ls_fixed_v0_reaction_time: 1",
    ]
    if variant == "final":
        lines.extend(
            [
                "sc_ls_fixed_v0_compile_info_output_mode: summary",
                "sc_ls_fixed_v0_skip_pipeline_state_output: true",
            ]
        )
    lines.extend(
        [
            f"sc_ls_fixed_v0_dump_compile_info_to_json: {compile_info_path}",
            "sc_ls_fixed_v0_pass:",
            *[f"  - {name}" for name in _compile_passes()],
            "",
        ]
    )
    return "\n".join(lines)


def _variant_env(env: dict[str, str], variant: str, profile_jsonl: Path | None = None) -> None:
    env["QRET_MAGIC_PATH_STORAGE"] = "interned"
    env["QRET_SUMMARY_TIME_SERIES_IMPL"] = "legacy_timeseries"
    env["QRET_DEP_GRAPH_IMPL"] = "compact"
    env["QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING"] = "1"
    env["QRET_INVERSE_MAP_CONSTRUCTION"] = "eager"
    env["QRET_INSTRUCTION_ALLOCATION"] = "legacy"
    env["QRET_RSS_DIAGNOSTIC_TRIM_STAGE"] = "none"
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    env.pop("LANGUAGE", None)
    if variant == "final" and profile_jsonl is not None:
        env["QRET_PROFILE_HIGH_WATER"] = "1"
        env["QRET_PROFILE_INVERSE_MAP_USAGE"] = "1"
        env["QRET_RSS_PROFILE_JSONL"] = str(profile_jsonl)


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


def _safety_check(*, case: str, output_root: Path) -> None:
    if shutil.disk_usage(output_root.parent).free < MIN_FREE_DISK_BYTES:
        raise RuntimeError("disk free space is below 5 GiB")
    meminfo = _meminfo()
    if case == "h5_4th_new2" and int(meminfo.get("MemAvailable") or 0) < MIN_MEM_AVAILABLE_KB:
        raise RuntimeError("MemAvailable is below 1,000,000 KB; refusing H5 run")


def _parse_gnu_time_maxrss(stderr: str) -> int | None:
    match = re.search(r"Maximum resident set size \(kbytes\):\s*(\d+)", stderr)
    return int(match.group(1)) if match else None


def _file_sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return sc.file_sha256(path)


def _file_size(path: Path | None) -> int | None:
    if path is None:
        return None
    try:
        return int(path.stat().st_size)
    except OSError:
        return None


def _present_sizes(paths: Mapping[str, Path | None]) -> dict[str, int]:
    ret: dict[str, int] = {}
    for key, path in paths.items():
        size = _file_size(path)
        if size is not None:
            ret[key] = size
    return ret


def _largest_size(sizes: Mapping[str, int]) -> int | None:
    return max(sizes.values()) if sizes else None


def _sum_size(sizes: Mapping[str, int]) -> int | None:
    return sum(sizes.values()) if sizes else None


def _run_qret_compile_once(
    *,
    case: str,
    variant: str,
    cache_condition: str,
    run_index: int,
    artifact: sc.SurfaceCodeStepArtifact,
    qret_path: Path,
    topology_path: Path,
    output_root: Path,
    sample_interval_sec: float,
    memtotal_kb: int | None,
) -> dict[str, Any]:
    _safety_check(case=case, output_root=output_root)
    run_dir = output_root / case / variant / cache_condition / f"run_{run_index:02d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    compile_info_path = run_dir / "compile_info.json"
    profile_jsonl = run_dir / "qret_rss_profile.jsonl"
    samples_jsonl = run_dir / "process_tree_samples.jsonl"
    compile_yaml_path = run_dir / "compile.yaml"
    stdout_path = run_dir / "stdout.txt"
    stderr_path = run_dir / "stderr.txt"
    compile_output_path = Path(os.devnull)
    for path in (compile_info_path, profile_jsonl, samples_jsonl, stdout_path, stderr_path):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    compile_yaml_path.write_text(
        _pipeline_yaml(
            artifact=artifact,
            topology_path=topology_path,
            output_path=compile_output_path,
            compile_info_path=compile_info_path,
            variant=variant,
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    _variant_env(env, variant, profile_jsonl)
    before_hashes = sc.qret_runtime_hashes(qret_path)
    cmd = ["/usr/bin/time", "-v", str(qret_path), "compile", "--pipeline", str(compile_yaml_path), "--verbose"]
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
    after_hashes = sc.qret_runtime_hashes(qret_path)
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    _write_jsonl(samples_jsonl, sample_rows)
    sample_summary = compact_profile._summarize_samples(sample_rows, parent_pid=process.pid)
    sample_summary.update(sample_rows.retention_summary())
    gnu_maxrss = _parse_gnu_time_maxrss(stderr)
    normalized = live_profile._metric_summary(compile_info_path)
    raw = live_profile._raw_resource_metrics(compile_info_path)
    generated_sizes = _present_sizes(
        {
            "compile_pipeline": compile_yaml_path,
            "compile_info": compile_info_path,
            "compile_output": None,
        }
    )
    artifact_sizes = _present_sizes(
        {
            "qasm": artifact.qasm_path,
            "input_ir": artifact.ir_path,
            "optimized_ir": artifact.optimized_ir_path,
        }
    )
    result = {
        "case": case,
        "variant": variant,
        "cache_condition": cache_condition,
        "run_index": run_index,
        "status": "ok" if process.returncode == 0 else "failed",
        "returncode": int(process.returncode),
        "elapsed_seconds": elapsed,
        "gnu_time_maxrss_kb": gnu_maxrss,
        "qret_peak_rss_kb": live_profile._max_present(
            gnu_maxrss,
            sample_summary.get("sampled_peak_qret_vmrss_kb"),
        ),
        "tree_peak_rss_kb": sample_summary.get("sampled_peak_tree_vmrss_kb"),
        "sample_summary": sample_summary,
        "guard": guard,
        "runtime_hashes_before": before_hashes,
        "runtime_hashes_after": after_hashes,
        "input_hash": artifact.optimized_ir_hash,
        "output_hash": _file_sha256(compile_info_path),
        "compile_info_size_bytes": _file_size(compile_info_path),
        "generated_file_sizes": generated_sizes,
        "artifact_file_sizes": artifact_sizes,
        "largest_intermediate_file_bytes": _largest_size({**generated_sizes, **artifact_sizes}),
        "total_intermediate_file_bytes": _sum_size({**generated_sizes, **artifact_sizes}),
        "compile_info_path": str(compile_info_path),
        "pipeline_path": str(compile_yaml_path),
        "samples_jsonl": str(samples_jsonl),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "profile_jsonl": str(profile_jsonl) if profile_jsonl.exists() else None,
        "normalized_metrics": normalized,
        "raw_resource_metrics": raw,
    }
    _write_json(run_dir / "summary.json", result)
    if process.returncode != 0:
        raise RuntimeError(f"qret failed for {case} {variant} {cache_condition}: {stderr[-4000:]}")
    return result


def _median(values: Iterable[Any]) -> float | int | None:
    present = [value for value in values if value is not None]
    return statistics.median(present) if present else None


def _min(values: Iterable[Any]) -> Any:
    present = [value for value in values if value is not None]
    return min(present) if present else None


def _max(values: Iterable[Any]) -> Any:
    present = [value for value in values if value is not None]
    return max(present) if present else None


def _variation_pct(min_value: Any, max_value: Any, median_value: Any) -> float | None:
    if min_value is None or max_value is None or median_value in (None, 0):
        return None
    return (float(max_value) - float(min_value)) / float(median_value) * 100.0


def _pct_reduction(baseline: Any, final: Any) -> float | None:
    if baseline in (None, 0) or final is None:
        return None
    return (float(baseline) - float(final)) / float(baseline) * 100.0


def _aggregate(
    results: Sequence[Mapping[str, Any]],
    *,
    case: str,
    variant: str,
    cache_condition: str,
) -> dict[str, Any]:
    rows = [
        row for row in results
        if row.get("case") == case
        and row.get("variant") == variant
        and row.get("cache_condition") == cache_condition
    ]
    metrics = {
        "elapsed_seconds": [row.get("elapsed_seconds") for row in rows],
        "qret_peak_rss_kb": [row.get("qret_peak_rss_kb") for row in rows],
        "tree_peak_rss_kb": [row.get("tree_peak_rss_kb") for row in rows],
        "compile_info_size_bytes": [row.get("compile_info_size_bytes") for row in rows],
        "largest_intermediate_file_bytes": [row.get("largest_intermediate_file_bytes") for row in rows],
        "total_intermediate_file_bytes": [row.get("total_intermediate_file_bytes") for row in rows],
    }
    ret: dict[str, Any] = {
        "case": case,
        "variant": variant,
        "cache_condition": cache_condition,
        "runs": len(rows),
    }
    for name, values in metrics.items():
        min_value = _min(values)
        max_value = _max(values)
        median_value = _median(values)
        ret[f"median_{name}"] = median_value
        ret[f"min_{name}"] = min_value
        ret[f"max_{name}"] = max_value
        ret[f"{name}_variation_pct"] = _variation_pct(min_value, max_value, median_value)
    return ret


def _comparison_table(
    aggregates: Mapping[str, Mapping[str, Any]],
    *,
    case: str,
    cache_condition: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for metric in (
        "elapsed_seconds",
        "qret_peak_rss_kb",
        "tree_peak_rss_kb",
        "compile_info_size_bytes",
        "largest_intermediate_file_bytes",
        "total_intermediate_file_bytes",
    ):
        baseline = aggregates.get(f"{case}:baseline:{cache_condition}", {}).get(f"median_{metric}")
        final = aggregates.get(f"{case}:final:{cache_condition}", {}).get(f"median_{metric}")
        diff = None if baseline is None or final is None else float(baseline) - float(final)
        rows.append(
            {
                "metric": metric,
                "baseline": baseline,
                "final": final,
                "absolute_difference": diff,
                "percentage": _pct_reduction(baseline, final),
            }
        )
    return rows


def _semantic_validation(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    comparisons: dict[str, Any] = {}
    for case in CASE_SPECS:
        baseline_rows = [row for row in results if row.get("case") == case and row.get("variant") == "baseline"]
        final_rows = [row for row in results if row.get("case") == case and row.get("variant") == "final"]
        if not baseline_rows or not final_rows:
            continue
        baseline = baseline_rows[0]
        final = final_rows[0]
        ignored_normalized = {
            "compile_info_json",
            "execution_time_sec",
            "estimated_execution_time_sec",
            "compiler_executable_path",
            "compiler_executable_hash",
            "compiler_core_library_path",
            "compiler_core_library_hash",
            "cache_key",
        }
        raw_keys = set(baseline.get("raw_resource_metrics", {})) | set(final.get("raw_resource_metrics", {}))
        normalized_keys = (
            set(baseline.get("normalized_metrics", {}))
            | set(final.get("normalized_metrics", {}))
        ) - ignored_normalized
        raw_mismatches = [
            key for key in sorted(raw_keys)
            if baseline.get("raw_resource_metrics", {}).get(key)
            != final.get("raw_resource_metrics", {}).get(key)
        ]
        normalized_mismatches = [
            key for key in sorted(normalized_keys)
            if baseline.get("normalized_metrics", {}).get(key)
            != final.get("normalized_metrics", {}).get(key)
        ]
        comparisons[case] = {
            "raw_equal": not raw_mismatches,
            "raw_mismatches": raw_mismatches,
            "normalized_equal": not normalized_mismatches,
            "normalized_mismatches": normalized_mismatches,
            "ignored_normalized_fields": sorted(ignored_normalized),
        }
    return comparisons


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "not applicable"
    if isinstance(value, float) and value.is_integer():
        return f"{int(value):,}"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_mb_from_bytes(value: Any) -> str:
    if value is None:
        return "not applicable"
    mb = float(value) / ONE_MB
    if 0 < mb < 0.01:
        return "<0.01"
    return f"{mb:.2f}"


def _comparison_markdown(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    lines = [
        "| metric | baseline | final | absolute difference | percentage |",
        "| ------ | -------: | ----: | ------------------: | ---------: |",
    ]
    for row in rows:
        metric = str(row["metric"])
        is_bytes = metric.endswith("_bytes")
        baseline = _fmt_mb_from_bytes(row["baseline"]) if is_bytes else _fmt(row["baseline"])
        final = _fmt_mb_from_bytes(row["final"]) if is_bytes else _fmt(row["final"])
        diff = _fmt_mb_from_bytes(row["absolute_difference"]) if is_bytes else _fmt(row["absolute_difference"])
        pct = _fmt(row["percentage"])
        lines.append(f"| `{metric}` | {baseline} | {final} | {diff} | {pct}% |")
    return lines


def _optimization_inventory(arena_status: str | None) -> list[dict[str, Any]]:
    return [
        {
            "optimization": "streaming Python inliner",
            "status": "production adopted",
            "evaluation_case": "H4/H5 pipeline tests and staged reports",
            "memory_effect": "reduced parent JSON/IR lifetime; report-level cumulative",
            "elapsed_effect": "preserved or improved by avoiding full merged IR materialization",
            "semantic_validation": "normalized instruction stream and metrics",
            "reason": "same inlining semantics with streaming emission",
        },
        {
            "optimization": "incremental JSON parsing",
            "status": "production adopted",
            "evaluation_case": "H4 parent-RSS profile",
            "memory_effect": "reduced retained Python JSON load where used",
            "elapsed_effect": "small/acceptable",
            "semantic_validation": "field extraction and normalized metrics",
            "reason": "reads required fields without changing values",
        },
        {
            "optimization": "RZ helper independent/cache/batch/merge-less flow",
            "status": "production adopted",
            "evaluation_case": "H4/H5 artifact generation",
            "memory_effect": "removes repeated full-IR helper materialization",
            "elapsed_effect": "warm/helper-cache improvement",
            "semantic_validation": "helper output summaries and optimized IR stream hash",
            "reason": "cache keys include input, qret hash, gridsynth identity, and version",
        },
        {
            "optimization": "integral cache",
            "status": "production adopted",
            "evaluation_case": "surface-code reproducibility tests",
            "memory_effect": "avoids regeneration work on warm runs",
            "elapsed_effect": "warm prepare improvement",
            "semantic_validation": "content/version keyed npz metadata",
            "reason": "only exact cache-key hit is reused",
        },
        {
            "optimization": "prepared artifact cache / compile result cache",
            "status": "production adopted",
            "evaluation_case": "architecture sweep cache-hit tests",
            "memory_effect": "warm run avoids prepared/compile intermediate regeneration",
            "elapsed_effect": "warm run improvement",
            "semantic_validation": "artifact and compile cache hashes",
            "reason": "cache payload includes qret/topology/config/input hashes",
        },
        {
            "optimization": "pipeline-state output skip",
            "status": "production adopted",
            "evaluation_case": "H4/H5 qret direct benchmark",
            "memory_effect": "large qret peak reduction by avoiding BuildPipelineState",
            "elapsed_effect": "large compile elapsed reduction",
            "semantic_validation": "compile-info metrics parity",
            "reason": "compile-info is dumped directly; unused state output is not built",
        },
        {
            "optimization": "compile-info summary / summary aggregation / TimeSeries current default",
            "status": "production adopted",
            "evaluation_case": "H4/H5/H6 summary reports, H6 predates current restriction",
            "memory_effect": "large compile-info JSON and summary accumulation reduction",
            "elapsed_effect": "improved or acceptable",
            "semantic_validation": "raw and normalized metrics parity",
            "reason": "keeps required aggregates without retaining full time-series payload",
        },
        {
            "optimization": "compact DepGraph",
            "status": "production adopted",
            "evaluation_case": "H4/H5 compact graph profiles",
            "memory_effect": "reduced dependency graph storage",
            "elapsed_effect": "acceptable",
            "semantic_validation": "node/edge counts and depth metrics parity",
            "reason": "representation changes, graph semantics unchanged",
        },
        {
            "optimization": "inverse-map release after routing",
            "status": "production adopted",
            "evaluation_case": "H5 routing lifetime profile",
            "memory_effect": "reduces allocator in-use bytes after routing",
            "elapsed_effect": "neutral",
            "semantic_validation": "post-routing consumers do not require inverse maps",
            "reason": "clears maps after the mutation phase",
        },
        {
            "optimization": "magic-path exact interning",
            "status": "production adopted",
            "evaluation_case": "H5 `4th(new_2)`",
            "memory_effect": "116.6 MB / 21.1% H5 qret peak reduction",
            "elapsed_effect": "improved",
            "semantic_validation": "raw and normalized metrics parity",
            "reason": "only identical path sequences share storage",
        },
        {
            "optimization": "non-path singleton operand compaction",
            "status": "evaluated and rejected",
            "evaluation_case": "H5 `4th(new_2)`",
            "memory_effect": "12.3 MB / 2.834% peak reduction",
            "elapsed_effect": "9.092% regression",
            "semantic_validation": "raw and normalized metrics parity",
            "reason": "compatibility cache added object bytes and elapsed cost",
        },
        {
            "optimization": "lazy inverse-map construction",
            "status": "evaluated and rejected",
            "evaluation_case": "H5 `4th(new_2)`",
            "memory_effect": "48 KB / 0.011% peak reduction",
            "elapsed_effect": "0.951% faster",
            "semantic_validation": "raw and normalized metrics parity",
            "reason": "removed live entries but did not move VMRSS high-water",
        },
        {
            "optimization": "pre-routing high-water instrumentation",
            "status": "profiling only",
            "evaluation_case": "H5 `4th(new_2)`",
            "memory_effect": "diagnostic only",
            "elapsed_effect": "diagnostic only",
            "semantic_validation": "profile-on/off H4 parity",
            "reason": "identified MachineFunction construction high-water",
        },
        {
            "optimization": "instruction arena allocation",
            "status": arena_status or "evaluated and rejected",
            "evaluation_case": "H4/H5 `4th(new_2)`",
            "memory_effect": "10.8 MB / 2.487% H5 qret peak reduction",
            "elapsed_effect": "2.314% faster in Phase A median",
            "semantic_validation": "raw, normalized, and semantic projection parity",
            "reason": "failed 30 MB or 7% H5 peak gate",
        },
    ]


def _write_report(path: Path, *, summary: Mapping[str, Any]) -> None:
    aggregates = summary.get("aggregates", {})
    comparisons = summary.get("comparison_tables", {})
    semantic = summary.get("semantic_validation", {})
    environment = summary.get("environment", {})
    inventory = summary.get("production_optimizations", []) + summary.get("rejected_optimizations", [])
    lines = [
        "# qret Optimization Integrity and Performance Summary",
        "",
        "## 1. Scope",
        "",
        "This report summarizes Evaluation/qret lightening through the Phase A instruction arena decision. Only H4 and H5 were executed in this pass; H6, H7, H8, and H9 were not executed.",
        "",
        "## 2. Research Context",
        "",
        "The benchmark covers the uncontrolled single-step grouped H-chain surface-code pipeline used by the existing Evaluation reports. It does not turn the workload into full QPE.",
        "",
        "## 3. Baseline Selection",
        "",
        f"- earliest runnable baseline: `{EARLIEST_RUNNABLE_BASELINE}`",
        f"- selected stable pre-optimization baseline: `{STABLE_PRE_OPTIMIZATION_BASELINE}`",
        "- selected reason: build_qret.sh, qret vendoring, and profiling harness exist, but production qret memory optimizations had not started.",
        "",
        "## 4. Final Production Configuration",
        "",
        "- magic path storage: `interned`",
        "- non-path operands: legacy containers",
        "- compile-info output: `summary`",
        "- summary TimeSeries: repository current production setting (`legacy_timeseries` in this benchmark env)",
        "- DepGraph: `compact`",
        "- inverse-map construction: eager default",
        "- inverse-map release after routing: enabled",
        "- pipeline-state output: skipped",
        "- instruction allocation default: `legacy`",
        "",
        "## 5. Optimization Inventory",
        "",
        "| optimization | status | evaluation case | memory effect | elapsed effect | semantic validation | reason |",
        "| ------------ | ------ | --------------- | ------------- | -------------- | ------------------- | ------ |",
    ]
    for item in inventory:
        lines.append(
            "| {optimization} | {status} | {evaluation_case} | {memory_effect} | {elapsed_effect} | {semantic_validation} | {reason} |".format(
                **{key: str(value).replace("|", "\\|") for key, value in item.items()}
            )
        )
    lines.extend(
        [
            "",
            "## 6. Semantic Preservation Arguments",
            "",
            "The adopted changes alter storage, emission, caching, or aggregation paths, not the target circuit semantics. Cache reuse is guarded by content/config/version hashes. qret storage changes keep instruction ordering, pass order, topology options, and compile-info metric definitions stable. Arena mode was not adopted; it remains an explicit candidate with default legacy allocation.",
            "",
            "## 7. Observational Equivalence",
            "",
            "| case | raw metrics equal | normalized metrics equal | ignored normalized fields |",
            "| ---- | ----------------- | ------------------------ | ------------------------- |",
        ]
    )
    for case, row in semantic.items():
        lines.append(
            f"| `{case}` | {row.get('raw_equal')} | {row.get('normalized_equal')} | {', '.join(row.get('ignored_normalized_fields', []))} |"
        )
    lines.extend(
        [
            "",
            "The claim is limited to observational equivalence for the measured H4/H5 pipelines and the unit/integration tests. This is not a formal proof for every possible quration input.",
            "",
            "## 8. Test Coverage",
            "",
            "Coverage includes focused Python report tests, Phase A arena tests, qret C++ target tests, and the final full pytest/CTest verification listed in the task log.",
            "",
            "## 9. Individual Optimization Results",
            "",
            "The cumulative result must be read baseline-vs-final; individual percentage reductions are not additive. Rejected candidates remain listed above.",
            "",
            "## 10. Baseline Vs Final Benchmark Method",
            "",
            "- baseline qret: selected worktree at `5c52fc6`",
            "- final qret: current Evaluation worktree build",
            "- common input: final prepared optimized IR for each case",
            "- common external metrics: `/usr/bin/time -v`, process-tree sampler, elapsed wall clock, compile-info size, intermediate file sizes",
            "- cold/warm definition: qret direct compile has no application-level compile-result cache in this harness; warm is the immediate second direct compile on the same input and output shape. OS page cache was not dropped.",
            "- baseline qret executable hash: `{}`".format(
                environment.get("baseline_qret_hashes", {}).get("qret_executable_hash")
            ),
            "- final qret executable hash: `{}`".format(
                environment.get("final_qret_hashes", {}).get("qret_executable_hash")
            ),
            "- topology hash: `{}`".format(environment.get("topology_hash")),
            "- Python: `{}`".format(
                (str(environment.get("python", "")).splitlines() or ["unknown"])[0]
            ),
            "- compiler: `{}`".format(environment.get("compiler")),
            "- MemTotal KB: `{}`".format(environment.get("meminfo", {}).get("MemTotal")),
            "",
            "## 11. H4 Results",
            "",
            "### H4 Cold",
            "",
            *(_comparison_markdown(comparisons.get("h4_4th_new2:cold", []))),
            "",
            "### H4 Warm",
            "",
            *(_comparison_markdown(comparisons.get("h4_4th_new2:warm", []))),
            "",
            "## 12. H5 Results",
            "",
            "### H5 Cold",
            "",
            *(_comparison_markdown(comparisons.get("h5_4th_new2:cold", []))),
            "",
            "### H5 Warm",
            "",
            *(_comparison_markdown(comparisons.get("h5_4th_new2:warm", []))),
            "",
            "## 13. Cold Vs Warm Results",
            "",
            "| aggregate | runs | median elapsed s | median qret peak KB | median tree peak KB |",
            "| --------- | ---: | ---------------: | ------------------: | ------------------: |",
        ]
    )
    for key in sorted(aggregates):
        row = aggregates[key]
        if not row.get("runs"):
            continue
        lines.append(
            f"| `{key}` | {_fmt(row.get('runs'))} | {_fmt(row.get('median_elapsed_seconds'))} | {_fmt(row.get('median_qret_peak_rss_kb'))} | {_fmt(row.get('median_tree_peak_rss_kb'))} |"
        )
    lines.extend(
        [
            "",
            "## 14. Memory Reduction",
            "",
            "The direct observed memory reduction is reported in the H4/H5 tables above. The largest qret-side reductions came from skipping unused pipeline-state construction/output, compile-info summary aggregation, compact DepGraph, inverse-map release for allocator in-use bytes, and exact magic-path interning.",
            "",
            "## 15. Elapsed-Time Reduction",
            "",
            "Elapsed reductions are reported as direct baseline-vs-final medians in the H4/H5 tables. Warm Python cache wins are summarized qualitatively from the adopted cache mechanisms because this direct qret harness intentionally bypasses Evaluation compile-result cache.",
            "",
            "## 16. Intermediate-File Reduction",
            "",
            "The direct file-size reductions are dominated by full baseline compile-info JSON versus final summary compile-info JSON. Missing pipeline-state output is reported as not generated, not as zero semantic output.",
            "",
            "## 17. Rejected Candidates",
            "",
            "- non-path singleton operand compaction: rejected for small peak saving and elapsed regression.",
            "- lazy inverse-map construction: rejected for negligible VMRSS peak movement.",
            "- instruction arena allocation: rejected for failing the H5 30 MB / 7% peak gate.",
            "",
            "## 18. Remaining Bottlenecks",
            "",
            "H5 high-water is now dominated by MachineFunction construction and retained instruction/operand/list-node layout. Arena allocation alone did not remove enough resident memory; larger representation or ownership changes remain higher risk follow-up work.",
            "",
            "## 19. Remaining Research Approximations",
            "",
            "- uncontrolled 1 Trotter step is the central measured workload",
            "- full QPE circuit was not compiled",
            "- controlled-U, QPE ancillae, inverse QFT, and measurement feed-forward are not included",
            "- multiple-step non-additive effects and factory stock state across steps remain unevaluated",
            "- H6-H9 were not executed; H9 must remain estimated/theoretical only",
            "",
            "## 20. Limitations",
            "",
            "The direct benchmark compares qret compile stages on shared final optimized IR. It does not re-run the full cold Python artifact-generation pipeline for baseline because that would mix older instrumentation and cache semantics with the qret-side comparison.",
            "",
            "## 21. Conclusion",
            "",
            "Lightening preserves the target observables in the measured H4/H5 pipeline, but the original resource-estimation model approximations remain. Phase A ended with arena rejected and production default unchanged.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _small_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "baseline_commit": STABLE_PRE_OPTIMIZATION_BASELINE,
        "final_commit": summary.get("environment", {}).get("evaluation_head"),
        "cases": summary.get("comparison_tables", {}),
        "production_optimizations": summary.get("production_optimizations", []),
        "rejected_optimizations": summary.get("rejected_optimizations", []),
        "semantic_validation": summary.get("semantic_validation", {}),
        "limitations": summary.get("limitations", []),
        "execution_limits": summary.get("execution_limits", {}),
    }


def run_benchmark(
    *,
    output_root: Path,
    report_path: Path,
    summary_path: Path,
    baseline_worktree: Path,
    cases: Sequence[str],
    h4_runs: int,
    h5_runs: int,
    sample_interval_sec: float,
    skip_run: bool = False,
) -> dict[str, Any]:
    cases = _validate_cases(cases)
    output_root.mkdir(parents=True, exist_ok=True)
    baseline_qret = baseline_worktree / "build" / "quration" / "qret"
    final_qret = REPO_ROOT / "build" / "quration" / "qret"
    if not baseline_qret.exists():
        raise FileNotFoundError(f"baseline qret not found: {baseline_qret}")
    if not final_qret.exists():
        raise FileNotFoundError(f"final qret not found: {final_qret}")
    topology_path = (
        REPO_ROOT
        / "third_party"
        / "quration"
        / "quration-core"
        / "examples"
        / "data"
        / "topology"
        / "tutorial.yaml"
    ).resolve()
    environment = {
        "evaluation_head": _git_output(["rev-parse", "HEAD"]),
        "evaluation_status_short": _git_output(["status", "--short"]),
        "baseline_selection": _baseline_selection(),
        "baseline_worktree": str(baseline_worktree),
        "baseline_worktree_head": _git_output(["rev-parse", "HEAD"], cwd=baseline_worktree),
        "baseline_qret_hashes": sc.qret_runtime_hashes(baseline_qret),
        "final_qret_hashes": sc.qret_runtime_hashes(final_qret),
        "topology_path": str(topology_path),
        "topology_hash": sc.file_sha256(topology_path),
        "python": sys.version,
        "platform": platform.platform(),
        "compiler": live_profile._compiler_version(),
        "meminfo": _meminfo(),
        "disk_free_bytes": shutil.disk_usage(output_root.parent).free,
        "sample_interval_sec": sample_interval_sec,
    }
    results: list[dict[str, Any]] = []
    if not skip_run:
        artifacts = _prepare_artifacts(cases, final_qret_path=final_qret)
        environment["artifacts"] = {
            case: {
                **artifact.to_dict(),
                "artifact_file_sizes": _present_sizes(
                    {
                        "qasm": artifact.qasm_path,
                        "input_ir": artifact.ir_path,
                        "optimized_ir": artifact.optimized_ir_path,
                    }
                ),
            }
            for case, artifact in artifacts.items()
        }
        memtotal_kb = int(environment.get("meminfo", {}).get("MemTotal") or 0) or None
        for case in cases:
            runs = h5_runs if CASE_SPECS[case]["chain_length"] == 5 else h4_runs
            if not CASE_SPECS[case].get("performance"):
                runs = 1
            for variant, qret_path in (("baseline", baseline_qret), ("final", final_qret)):
                for condition in CONDITIONS:
                    condition_runs = runs if CASE_SPECS[case].get("performance") else 1
                    for run_index in range(1, condition_runs + 1):
                        result = _run_qret_compile_once(
                            case=case,
                            variant=variant,
                            cache_condition=condition,
                            run_index=run_index,
                            artifact=artifacts[case],
                            qret_path=qret_path.resolve(),
                            topology_path=topology_path,
                            output_root=output_root,
                            sample_interval_sec=sample_interval_sec,
                            memtotal_kb=memtotal_kb,
                        )
                        results.append(result)
                        _write_csv(output_root / "summary.csv", results)
                        _write_json(output_root / "summary.json", {"environment": environment, "results": results})
    else:
        existing = output_root / "summary.json"
        if existing.exists():
            payload = json.loads(existing.read_text(encoding="utf-8"))
            results = list(payload.get("results", []))
            previous_environment = payload.get("environment", {})
            environment["previous_run_environment"] = previous_environment
            if isinstance(previous_environment, Mapping) and "artifacts" in previous_environment:
                environment["artifacts"] = previous_environment["artifacts"]
    aggregates = {
        f"{case}:{variant}:{condition}": _aggregate(
            results,
            case=case,
            variant=variant,
            cache_condition=condition,
        )
        for case in cases
        for variant in VARIANTS
        for condition in CONDITIONS
    }
    comparison_tables = {
        f"{case}:{condition}": _comparison_table(aggregates, case=case, cache_condition=condition)
        for case in cases
        if CASE_SPECS[case].get("performance")
        for condition in CONDITIONS
    }
    arena_status = None
    arena_summary_path = REPO_ROOT / "artifacts" / "qret_instruction_arena" / "summary.json"
    if arena_summary_path.exists():
        arena_status = json.loads(arena_summary_path.read_text(encoding="utf-8")).get("decision", {}).get("arena_status")
    inventory = _optimization_inventory(arena_status)
    summary = {
        "environment": environment,
        "results": results,
        "aggregates": aggregates,
        "comparison_tables": comparison_tables,
        "semantic_validation": _semantic_validation(results),
        "production_optimizations": [item for item in inventory if item["status"] == "production adopted"],
        "rejected_optimizations": [item for item in inventory if "rejected" in item["status"]],
        "other_optimizations": [
            item for item in inventory
            if item["status"] not in {"production adopted"} and "rejected" not in item["status"]
        ],
        "execution_limits": {
            "largest_measured_case": "H5" if "h5_4th_new2" in cases else "H4",
            "h6_executed": False,
            "h7_executed": False,
            "h8_executed": False,
            "h9_executed": False,
            "h9_memory": "not measured; estimated/theoretical only in prior strategy reports",
        },
        "limitations": [
            "direct qret compile benchmark uses final prepared optimized IR as common input",
            "cold/warm direct qret runs do not exercise Evaluation compile-result cache",
            "H6-H9 were not executed",
            "not a formal proof for all quration inputs",
        ],
    }
    _write_json(output_root / "summary.json", summary)
    _write_report(report_path, summary=summary)
    _write_json(summary_path, _small_summary(summary))
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark and summarize qret optimization integrity.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--summary-json", type=Path, default=DEFAULT_SUMMARY_PATH)
    parser.add_argument("--baseline-worktree", type=Path, default=DEFAULT_BASELINE_WORKTREE)
    parser.add_argument("--case", action="append", choices=tuple(CASE_SPECS), help="Default: H4 2nd, H4 4th(new_2), H5 4th(new_2)")
    parser.add_argument("--h4-runs", type=int, default=3)
    parser.add_argument("--h5-runs", type=int, default=2)
    parser.add_argument("--sample-interval-sec", type=float, default=0.02)
    parser.add_argument("--skip-run", action="store_true", help="Regenerate report/summary from an existing output-root summary.json.")
    args = parser.parse_args(argv)
    run_benchmark(
        output_root=args.output_root,
        report_path=args.report,
        summary_path=args.summary_json,
        baseline_worktree=args.baseline_worktree,
        cases=tuple(args.case) if args.case else DEFAULT_CASES,
        h4_runs=int(args.h4_runs),
        h5_runs=int(args.h5_runs),
        sample_interval_sec=float(args.sample_interval_sec),
        skip_run=bool(args.skip_run),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
