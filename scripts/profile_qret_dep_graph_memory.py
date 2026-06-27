#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Mapping

import profile_qret_calc_info_memory as calc
import profile_qret_pre_routing_memory as pre

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "qret_dep_graph_memory"
IMPLEMENTATIONS = ("legacy", "legacy_no_id2ptr", "legacy_dense", "compact")
DEFAULT_IMPLEMENTATIONS = ("legacy", "compact")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    pre._write_json(path, payload)


def _write_jsonl(path: Path, rows: list[Mapping[str, Any]]) -> None:
    pre._write_jsonl(path, rows)


def _median(values: list[float | int]) -> float | int | None:
    if not values:
        return None
    return statistics.median(values)


def _stage_row(rows: list[dict[str, Any]], stage: str) -> dict[str, Any] | None:
    matches = [row for row in rows if row.get("stage") == stage]
    return matches[-1] if matches else None


def _stage_rss(rows: list[dict[str, Any]], stage: str) -> int | None:
    row = _stage_row(rows, stage)
    value = row.get("vmrss_kb") if row else None
    return None if value is None else int(value)


def _dep_graph_extra(rows: list[dict[str, Any]]) -> dict[str, Any]:
    for row in reversed(rows):
        extra = row.get("extra")
        if isinstance(extra, Mapping) and "dep_graph_implementation" in extra:
            return dict(extra)
    return {}


def _run_once(
    *,
    case: pre.CaseArtifact,
    implementation: str,
    repeat_index: int,
    qret_path: Path,
    topology_path: Path,
    output_root: Path,
    sample_interval_sec: float,
) -> dict[str, Any]:
    run_root = output_root / case.name / implementation / f"run_{repeat_index:02d}"
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
            passes=calc.PREFIX_PASSES[calc.FULL_PREFIX],
            skip_pipeline_state_output=True,
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["QRET_DEP_GRAPH_IMPL"] = implementation
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

    profile_rows = pre._load_jsonl(profile_jsonl)
    profile_summary = calc._summarize_profile(profile_rows)
    sample_summary = pre._summarize_samples(samples)
    dep_extra = _dep_graph_extra(profile_rows)
    before = _stage_rss(profile_rows, "calc_info_without_topology_before_dep_graph")
    after = _stage_rss(profile_rows, "calc_info_without_topology_after_dep_graph")
    pass_end = profile_summary.get("post_calc_info_without_topology_rss_kb")
    metrics = (
        calc.sc.surface_code_step_metrics_from_compile_info_json(compile_info_path)
        if compile_info_path.exists()
        else {}
    )
    result = {
        "case": case.name,
        "implementation": implementation,
        "repeat_index": repeat_index,
        "returncode": process.returncode,
        "elapsed_seconds": elapsed,
        "gnu_time_maxrss_kb": pre._parse_gnu_time_maxrss(stderr),
        "sampled_peak_tree_vmrss_kb": sample_summary.get("sampled_peak_tree_vmrss_kb"),
        "depgraph_before_rss_kb": before,
        "depgraph_after_rss_kb": after,
        "depgraph_delta_rss_kb": None if before is None or after is None else after - before,
        "depgraph_pass_end_rss_kb": pass_end,
        "depgraph_implementation_marker": dep_extra.get("dep_graph_implementation"),
        "depgraph_nodes": dep_extra.get("dep_graph_nodes"),
        "depgraph_edges": dep_extra.get("dep_graph_edges"),
        "depgraph_duplicate_edge_count": dep_extra.get("compact_duplicate_edge_count"),
        "depgraph_maximum_indegree": dep_extra.get("compact_maximum_indegree"),
        "depgraph_average_indegree": dep_extra.get("compact_average_indegree"),
        "depgraph_topological_order_invariant": dep_extra.get(
            "compact_topological_order_invariant",
            dep_extra.get("topological_order_invariant"),
        ),
        "compact_parent_offsets_capacity": dep_extra.get("compact_parent_offsets_capacity"),
        "compact_parent_ids_capacity": dep_extra.get("compact_parent_ids_capacity"),
        "compact_edge_lengths_capacity": dep_extra.get("compact_edge_lengths_capacity"),
        "compact_node_weights_capacity": dep_extra.get("compact_node_weights_capacity"),
        "compact_working_dp_capacity": dep_extra.get("compact_working_dp_capacity"),
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
        "compile_info_path": str(compile_info_path) if compile_info_path.exists() else None,
        "compile_info_size_bytes": compile_info_path.stat().st_size
        if compile_info_path.exists()
        else None,
        "output_exists": output_path.exists(),
        "pipeline_path": str(pipeline_path),
        "profile_jsonl": str(profile_jsonl),
        "samples_jsonl": str(samples_jsonl),
        "passes": list(calc.PREFIX_PASSES[calc.FULL_PREFIX]),
        "skip_pipeline_state_output": True,
        "normalized_metrics": metrics,
        **profile_summary,
    }
    _write_json(run_root / "summary.json", result)
    if process.returncode != 0:
        raise RuntimeError(
            f"qret failed for {case.name}/{implementation}/run_{repeat_index} "
            f"with code {process.returncode}; see {stderr_path}"
        )
    if not compile_info_path.exists():
        raise RuntimeError(f"compile_info was not created for {case.name}/{implementation}")
    return result


def _summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for case in sorted({row["case"] for row in results}):
        summary[case] = {}
        for impl in sorted({row["implementation"] for row in results if row["case"] == case}):
            rows = [
                row
                for row in results
                if row["case"] == case and row["implementation"] == impl
            ]
            peaks = [int(row["gnu_time_maxrss_kb"]) for row in rows if row.get("gnu_time_maxrss_kb")]
            elapsed = [float(row["elapsed_seconds"]) for row in rows]
            deltas = [
                int(row["depgraph_delta_rss_kb"])
                for row in rows
                if row.get("depgraph_delta_rss_kb") is not None
            ]
            summary[case][impl] = {
                "run_count": len(rows),
                "peak_rss_kb_runs": peaks,
                "median_peak_rss_kb": _median(peaks),
                "min_peak_rss_kb": min(peaks) if peaks else None,
                "max_peak_rss_kb": max(peaks) if peaks else None,
                "elapsed_seconds_runs": elapsed,
                "median_elapsed_seconds": _median(elapsed),
                "depgraph_delta_rss_kb_runs": deltas,
                "median_depgraph_delta_rss_kb": _median(deltas),
                "node_count": rows[0].get("depgraph_nodes") if rows else None,
                "edge_count": rows[0].get("depgraph_edges") if rows else None,
                "duplicate_edge_count": rows[0].get("depgraph_duplicate_edge_count")
                if rows
                else None,
                "maximum_indegree": rows[0].get("depgraph_maximum_indegree")
                if rows
                else None,
                "average_indegree": rows[0].get("depgraph_average_indegree")
                if rows
                else None,
                "compact_payload_capacity_bytes": rows[0].get(
                    "compact_payload_capacity_bytes"
                )
                if rows
                else None,
                "returncodes": [row.get("returncode") for row in rows],
            }
    return summary


def _compare_all_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    comparisons: dict[str, Any] = {}
    for case in sorted({row["case"] for row in results}):
        case_rows = [row for row in results if row["case"] == case]
        baseline = next(
            row for row in case_rows if row["implementation"] == "legacy" and row["repeat_index"] == 0
        )
        comparisons[case] = {"against_legacy_run_0": {}, "deterministic": {}}
        for row in case_rows:
            key = f"{row['implementation']}_run_{row['repeat_index']}"
            comparisons[case]["against_legacy_run_0"][key] = calc._compare_metrics(
                baseline,
                row,
            )
        for impl in sorted({row["implementation"] for row in case_rows}):
            impl_rows = [row for row in case_rows if row["implementation"] == impl]
            first = impl_rows[0]
            comparisons[case]["deterministic"][impl] = {
                f"run_{row['repeat_index']}": calc._compare_metrics(first, row)
                for row in impl_rows
            }
    return comparisons


def _write_markdown_report(
    path: Path,
    *,
    results: list[dict[str, Any]],
    summary: Mapping[str, Any],
    comparisons: Mapping[str, Any],
) -> None:
    lines = [
        "# qret DepGraph Memory Profile",
        "",
        "| case | implementation | runs | median elapsed s | median peak RSS KB | "
        "median DepGraph delta KB | nodes | edges | metrics equal |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for case, impls in summary.items():
        for impl, row in impls.items():
            compare_rows = comparisons.get(case, {}).get("against_legacy_run_0", {})
            metrics_equal = all(
                item.get("normalized_metrics_equal") and item.get("semantic_fields_equal")
                for key, item in compare_rows.items()
                if key.startswith(f"{impl}_run_")
            )
            lines.append(
                "| {case} | {impl} | {runs} | {elapsed:.3f} | {peak} | {delta} | "
                "{nodes} | {edges} | {metrics_equal} |".format(
                    case=case,
                    impl=impl,
                    runs=row.get("run_count"),
                    elapsed=float(row.get("median_elapsed_seconds") or 0.0),
                    peak=row.get("median_peak_rss_kb") or "",
                    delta=row.get("median_depgraph_delta_rss_kb") or "",
                    nodes=row.get("node_count") or "",
                    edges=row.get("edge_count") or "",
                    metrics_equal=metrics_equal,
                )
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare qret legacy vs compact DepGraph memory and metrics."
    )
    parser.add_argument(
        "--case",
        action="append",
        choices=sorted(pre.DEFAULT_CASE_ARTIFACTS),
        help="Case to run. May be repeated. Default: H4 2nd and H4 4th(new_2).",
    )
    parser.add_argument(
        "--implementation",
        action="append",
        choices=IMPLEMENTATIONS,
        help="Implementation to run. Default: legacy and compact.",
    )
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--qret-path", type=Path, default=pre.DEFAULT_QRET_PATH)
    parser.add_argument("--topology-path", type=Path, default=pre.DEFAULT_TOPOLOGY_PATH)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--sample-interval-sec", type=float, default=0.02)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.repeat <= 0:
        raise ValueError("--repeat must be positive")
    if not (0 < args.sample_interval_sec <= 1):
        raise ValueError("--sample-interval-sec must be in (0, 1]")
    qret_path = args.qret_path.expanduser().resolve()
    topology_path = args.topology_path.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    if not qret_path.exists():
        raise FileNotFoundError(f"qret not found: {qret_path}")
    if not topology_path.exists():
        raise FileNotFoundError(f"topology not found: {topology_path}")

    cases = args.case or sorted(pre.DEFAULT_CASE_ARTIFACTS)
    implementations = args.implementation or list(DEFAULT_IMPLEMENTATIONS)
    results: list[dict[str, Any]] = []
    for case_name in cases:
        case = pre._load_case_artifact(case_name)
        for implementation in implementations:
            for repeat_index in range(args.repeat):
                result = _run_once(
                    case=case,
                    implementation=implementation,
                    repeat_index=repeat_index,
                    qret_path=qret_path,
                    topology_path=topology_path,
                    output_root=output_root,
                    sample_interval_sec=float(args.sample_interval_sec),
                )
                results.append(result)
                print(
                    "{case}/{impl}/run_{idx}: peak={peak}KB dep_delta={delta}KB "
                    "elapsed={elapsed:.3f}s metrics={metrics}".format(
                        case=case_name,
                        impl=implementation,
                        idx=repeat_index,
                        peak=result.get("gnu_time_maxrss_kb"),
                        delta=result.get("depgraph_delta_rss_kb"),
                        elapsed=float(result["elapsed_seconds"]),
                        metrics=bool(result.get("normalized_metrics")),
                    ),
                    flush=True,
                )

    summary = _summarize_results(results)
    comparisons = _compare_all_metrics(results)
    _write_jsonl(output_root / "results.jsonl", results)
    _write_json(output_root / "summary.json", summary)
    _write_json(output_root / "comparisons.json", comparisons)
    _write_json(
        output_root / "environment.json",
        {
            "qret_path": str(qret_path),
            "qret_hash": pre._file_sha256(qret_path),
            "topology_path": str(topology_path),
            "sample_interval_sec": float(args.sample_interval_sec),
            "cases": cases,
            "implementations": implementations,
            "repeat": args.repeat,
            "skip_pipeline_state_output": True,
            "passes": calc.PREFIX_PASSES[calc.FULL_PREFIX],
            "ignored_metric_fields": list(calc.IGNORED_METRIC_FIELDS),
        },
    )
    _write_markdown_report(
        output_root / "qret_dep_graph_memory_profile.md",
        results=results,
        summary=summary,
        comparisons=comparisons,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
