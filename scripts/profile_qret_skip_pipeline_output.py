#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Mapping

import profile_qret_pre_routing_memory as pre

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from trotterlib import surface_code as sc  # noqa: E402

DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "qret_skip_pipeline_state_output"
MODES = {
    "baseline": False,
    "skip_output": True,
}
SEMANTIC_FIELDS = (
    "magic_state_consumption_count",
    "magic_state_consumption_depth",
    "runtime",
    "runtime_without_topology",
    "qubit_volume",
    "gate_count",
    "gate_depth",
    "measurement_feedback_count",
    "measurement_feedback_depth",
    "magic_factory_count",
    "chip_cell_count",
    "code_distance",
    "num_physical_qubits",
    "t_count",
    "t_depth",
)
IGNORED_METRIC_FIELDS = ("compile_info_json",)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    pre._write_json(path, payload)


def _write_jsonl(path: Path, rows: list[Mapping[str, Any]]) -> None:
    pre._write_jsonl(path, rows)


def _profile_rows(path: Path) -> list[dict[str, Any]]:
    return pre._load_jsonl(path)


def _stage_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("stage")): row for row in rows if row.get("stage")}


def _pass_after_rss(rows: list[dict[str, Any]], pass_argument: str) -> int | None:
    for row in rows:
        if row.get("stage") != "mf_pass_after":
            continue
        extra = row.get("extra")
        if not isinstance(extra, Mapping):
            continue
        if extra.get("pass_argument") == pass_argument:
            value = row.get("vmrss_kb")
            return None if value is None else int(value)
    return None


def _run_mode(
    *,
    case: pre.CaseArtifact,
    mode: str,
    skip_pipeline_state_output: bool,
    qret_path: Path,
    topology_path: Path,
    output_root: Path,
    sample_interval_sec: float,
) -> dict[str, Any]:
    run_root = output_root / case.name / mode
    run_root.mkdir(parents=True, exist_ok=True)
    profile_jsonl = run_root / "qret_rss_profile.jsonl"
    samples_jsonl = run_root / "process_samples.jsonl"
    pipeline_path = run_root / "compile.yaml"
    compile_info_path = run_root / "compile_info.json"
    output_path = run_root / "step_sc_ls_fixed_v0.json"
    stdout_path = run_root / "stdout.txt"
    stderr_path = run_root / "stderr.txt"
    for path in (
        profile_jsonl,
        samples_jsonl,
        compile_info_path,
        output_path,
        stdout_path,
        stderr_path,
    ):
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    pipeline_path.write_text(
        pre._build_pipeline_yaml(
            opt_path=case.optimized_ir_path,
            output_path=output_path,
            compile_info_path=compile_info_path,
            topology_path=topology_path,
            passes=pre.TOPOLOGY_PASSES["full_topology"],
            skip_pipeline_state_output=skip_pipeline_state_output,
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["QRET_RSS_PROFILE_JSONL"] = str(profile_jsonl)
    cmd = [
        "/usr/bin/time",
        "-v",
        str(qret_path),
        "compile",
        "--pipeline",
        str(pipeline_path),
        "--verbose",
    ]
    start = time.perf_counter()
    process = subprocess.Popen(
        cmd,
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    samples: list[dict[str, Any]] = []
    stop_event = threading.Event()
    sampler = threading.Thread(
        target=pre._sample_process_tree,
        kwargs={
            "root_pid": process.pid,
            "interval_sec": sample_interval_sec,
            "stop_event": stop_event,
            "rows": samples,
        },
        daemon=True,
    )
    sampler.start()
    stdout, stderr = process.communicate()
    stop_event.set()
    sampler.join(timeout=2.0)
    elapsed = time.perf_counter() - start
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    _write_jsonl(samples_jsonl, samples)

    profile_rows = _profile_rows(profile_jsonl)
    profile_summary = pre._summarize_qret_profile(profile_rows)
    sample_summary = pre._summarize_samples(samples)
    stages = _stage_map(profile_rows)
    metrics = (
        sc.surface_code_step_metrics_from_compile_info_json(compile_info_path)
        if compile_info_path.exists()
        else {}
    )
    output_exists = output_path.exists()
    result = {
        "case": case.name,
        "mode": mode,
        "skip_pipeline_state_output": skip_pipeline_state_output,
        "returncode": process.returncode,
        "elapsed_seconds": elapsed,
        "gnu_time_maxrss_kb": pre._parse_gnu_time_maxrss(stderr),
        "sample_interval_sec": sample_interval_sec,
        "pipeline_path": str(pipeline_path),
        "profile_jsonl": str(profile_jsonl),
        "samples_jsonl": str(samples_jsonl),
        "compile_info_path": str(compile_info_path) if compile_info_path.exists() else None,
        "compile_info_size_bytes": compile_info_path.stat().st_size
        if compile_info_path.exists()
        else None,
        "output_path": str(output_path),
        "output_exists": output_exists,
        "output_size_bytes": output_path.stat().st_size if output_exists else None,
        "build_program_json_ran": any(
            str(row.get("stage", "")).startswith("build_program_json") for row in profile_rows
        ),
        "save_pipeline_state_ran": any(
            str(row.get("stage", "")).startswith("save_pipeline_state")
            for row in profile_rows
        ),
        "json_state_dom_built": "save_pipeline_state_after_to_json" in stages,
        "pipeline_state_output_skipped_marker": "pipeline_state_output_skipped" in stages,
        "routing_before_main_loop_rss_kb": stages.get("routing_before_main_loop", {}).get(
            "vmrss_kb"
        ),
        "routing_after_main_loop_rss_kb": stages.get("routing_after_main_loop", {}).get(
            "vmrss_kb"
        ),
        "post_calc_info_without_topology_rss_kb": _pass_after_rss(
            profile_rows,
            "sc_ls_fixed_v0::calc_info_without_topology",
        ),
        "pass_manager_end_rss_kb": stages.get("after_pass_manager_run", {}).get("vmrss_kb"),
        "pipeline_state_skip_decision_rss_kb": (
            stages.get("pipeline_state_output_skipped", {}).get("vmrss_kb")
            if skip_pipeline_state_output
            else stages.get("before_build_pipeline_state", {}).get("vmrss_kb")
        ),
        "run_compilation_end_rss_kb": stages.get("run_compilation_end", {}).get("vmrss_kb"),
        "normalized_metrics": metrics,
        **profile_summary,
        **sample_summary,
    }
    _write_json(run_root / "summary.json", result)
    if process.returncode != 0:
        raise RuntimeError(
            f"qret failed for {case.name}/{mode} with code {process.returncode}; "
            f"see {stderr_path}"
        )
    if not compile_info_path.exists():
        raise RuntimeError(f"compile_info was not created for {case.name}/{mode}")
    return result


def _compare_metrics(baseline: Mapping[str, Any], skip: Mapping[str, Any]) -> dict[str, Any]:
    baseline_metrics = dict(baseline["normalized_metrics"])
    skip_metrics = dict(skip["normalized_metrics"])
    for key in IGNORED_METRIC_FIELDS:
        baseline_metrics.pop(key, None)
        skip_metrics.pop(key, None)

    semantic = {}
    for field in SEMANTIC_FIELDS:
        baseline_has = field in baseline_metrics
        skip_has = field in skip_metrics
        semantic[field] = {
            "baseline_present": baseline_has,
            "skip_present": skip_has,
            "equal": baseline_has == skip_has
            and (not baseline_has or baseline_metrics[field] == skip_metrics[field]),
            "baseline": baseline_metrics.get(field),
            "skip": skip_metrics.get(field),
        }

    all_keys = sorted(set(baseline_metrics) | set(skip_metrics))
    mismatches = [
        key
        for key in all_keys
        if baseline_metrics.get(key, object()) != skip_metrics.get(key, object())
    ]
    return {
        "ignored_metric_fields": list(IGNORED_METRIC_FIELDS),
        "semantic_fields": semantic,
        "semantic_fields_equal": all(item["equal"] for item in semantic.values()),
        "normalized_metrics_equal": not mismatches,
        "normalized_metric_mismatches": mismatches,
    }


def _write_markdown_report(
    path: Path,
    *,
    results: list[dict[str, Any]],
    comparisons: Mapping[str, Any],
) -> None:
    lines = [
        "# qret Skip Pipeline-State Output Profile",
        "",
        "| case | mode | elapsed s | peak RSS KB | post-routing KB | post-calc-info KB | output size B | metrics equal |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in results:
        comparison = comparisons.get(row["case"], {})
        metrics_equal = (
            comparison.get("normalized_metrics_equal")
            if row["mode"] == "skip_output"
            else ""
        )
        lines.append(
            "| {case} | {mode} | {elapsed:.3f} | {peak} | {post_route} | "
            "{post_calc} | {output_size} | {metrics_equal} |".format(
                case=row["case"],
                mode=row["mode"],
                elapsed=float(row["elapsed_seconds"]),
                peak=row.get("gnu_time_maxrss_kb") or "",
                post_route=row.get("routing_after_main_loop_rss_kb") or "",
                post_calc=row.get("post_calc_info_without_topology_rss_kb") or "",
                output_size=row.get("output_size_bytes")
                if row.get("output_size_bytes") is not None
                else "absent",
                metrics_equal=metrics_equal,
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare qret baseline vs skip-pipeline-state-output RSS."
    )
    parser.add_argument(
        "--case",
        action="append",
        choices=sorted(pre.DEFAULT_CASE_ARTIFACTS),
        help="Case to run. May be repeated. Default: H4 2nd and H4 4th(new_2).",
    )
    parser.add_argument("--qret-path", type=Path, default=pre.DEFAULT_QRET_PATH)
    parser.add_argument("--topology-path", type=Path, default=pre.DEFAULT_TOPOLOGY_PATH)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--sample-interval-sec", type=float, default=0.02)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    qret_path = args.qret_path.expanduser().resolve()
    topology_path = args.topology_path.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    if not qret_path.exists():
        raise FileNotFoundError(f"qret not found: {qret_path}")
    if not topology_path.exists():
        raise FileNotFoundError(f"topology not found: {topology_path}")
    if not (0 < args.sample_interval_sec <= 1):
        raise ValueError("--sample-interval-sec must be in (0, 1]")

    results: list[dict[str, Any]] = []
    comparisons: dict[str, Any] = {}
    for case_name in args.case or sorted(pre.DEFAULT_CASE_ARTIFACTS):
        case = pre._load_case_artifact(case_name)
        mode_results = {}
        for mode, skip in MODES.items():
            result = _run_mode(
                case=case,
                mode=mode,
                skip_pipeline_state_output=skip,
                qret_path=qret_path,
                topology_path=topology_path,
                output_root=output_root,
                sample_interval_sec=float(args.sample_interval_sec),
            )
            mode_results[mode] = result
            results.append(result)
            print(
                "{case}/{mode}: maxrss={maxrss}KB output_exists={output_exists} "
                "metrics={metrics}".format(
                    case=case_name,
                    mode=mode,
                    maxrss=result.get("gnu_time_maxrss_kb"),
                    output_exists=result.get("output_exists"),
                    metrics=bool(result.get("normalized_metrics")),
                ),
                flush=True,
            )
        comparisons[case_name] = _compare_metrics(
            mode_results["baseline"],
            mode_results["skip_output"],
        )
        baseline_peak = mode_results["baseline"].get("gnu_time_maxrss_kb")
        skip_peak = mode_results["skip_output"].get("gnu_time_maxrss_kb")
        if baseline_peak and skip_peak:
            comparisons[case_name]["peak_reduction_kb"] = int(baseline_peak) - int(skip_peak)
            comparisons[case_name]["peak_reduction_percent"] = (
                (int(baseline_peak) - int(skip_peak)) / int(baseline_peak) * 100.0
            )
        comparisons[case_name]["elapsed_delta_seconds"] = (
            float(mode_results["skip_output"]["elapsed_seconds"])
            - float(mode_results["baseline"]["elapsed_seconds"])
        )

    _write_jsonl(output_root / "results.jsonl", results)
    _write_json(output_root / "comparisons.json", comparisons)
    _write_json(
        output_root / "environment.json",
        {
            "qret_path": str(qret_path),
            "qret_hash": pre._file_sha256(qret_path),
            "topology_path": str(topology_path),
            "sample_interval_sec": float(args.sample_interval_sec),
            "modes": MODES,
            "semantic_fields": list(SEMANTIC_FIELDS),
            "ignored_metric_fields": list(IGNORED_METRIC_FIELDS),
        },
    )
    _write_markdown_report(
        output_root / "qret_skip_pipeline_state_output.md",
        results=results,
        comparisons=comparisons,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
