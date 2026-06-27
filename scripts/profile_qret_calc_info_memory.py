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

DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "qret_calc_info_memory"

PREFIX_PASSES: dict[str, list[str]] = {
    "prefix_a_routing": [
        "sc_ls_fixed_v0::init_compile_info",
        "sc_ls_fixed_v0::mapping",
        "sc_ls_fixed_v0::routing",
    ],
    "prefix_b_calc_without_topology": [
        "sc_ls_fixed_v0::init_compile_info",
        "sc_ls_fixed_v0::mapping",
        "sc_ls_fixed_v0::routing",
        "sc_ls_fixed_v0::calc_info_without_topology",
    ],
    "prefix_c_calc_with_topology": [
        "sc_ls_fixed_v0::init_compile_info",
        "sc_ls_fixed_v0::mapping",
        "sc_ls_fixed_v0::routing",
        "sc_ls_fixed_v0::calc_info_without_topology",
        "sc_ls_fixed_v0::calc_info_with_topology",
    ],
    "prefix_d_dump_compile_info": [
        "sc_ls_fixed_v0::init_compile_info",
        "sc_ls_fixed_v0::mapping",
        "sc_ls_fixed_v0::routing",
        "sc_ls_fixed_v0::calc_info_without_topology",
        "sc_ls_fixed_v0::calc_info_with_topology",
        "sc_ls_fixed_v0::dump_compile_info",
    ],
}
FULL_PREFIX = "prefix_d_dump_compile_info"

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
IGNORED_METRIC_FIELDS = (
    "compile_info_json",
    "execution_time_sec",
)

KEY_STAGES = (
    "routing_after_main_loop",
    "calc_info_without_topology_entry",
    "calc_info_without_topology_after_dep_graph",
    "calc_info_without_topology_after_runtime_without_topology",
    "calc_info_without_topology_exit",
    "calc_info_with_topology_entry",
    "calc_info_with_topology_after_time_series",
    "calc_info_with_topology_after_rate_vector_resize",
    "calc_info_with_topology_after_cell_vector_resize",
    "calc_info_with_topology_exit",
    "dump_compile_info_entry",
    "dump_compile_info_before_json_dom_create",
    "compile_info_json_after_assign_gate_throughput",
    "compile_info_json_after_assign_measurement_feedback_rate",
    "compile_info_json_after_assign_magic_state_consumption_rate",
    "compile_info_json_after_assign_entanglement_consumption_rate",
    "compile_info_json_after_assign_chip_cell_algorithmic_qubit",
    "compile_info_json_after_assign_chip_cell_algorithmic_qubit_ratio",
    "compile_info_json_after_assign_chip_cell_active_qubit_area",
    "compile_info_json_after_assign_chip_cell_active_qubit_area_ratio",
    "dump_compile_info_after_json_dom_create",
    "dump_compile_info_after_json_stream_write",
    "dump_compile_info_after_json_dom_destroy",
    "dump_compile_info_exit",
    "after_pass_manager_run",
    "pipeline_state_output_skipped",
    "run_compilation_end",
)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    pre._write_json(path, payload)


def _write_jsonl(path: Path, rows: list[Mapping[str, Any]]) -> None:
    pre._write_jsonl(path, rows)


def _profile_rows(path: Path) -> list[dict[str, Any]]:
    return pre._load_jsonl(path)


def _stage_rows(rows: list[dict[str, Any]], stage: str) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("stage") == stage]


def _last_stage_row(rows: list[dict[str, Any]], stage: str) -> dict[str, Any] | None:
    matches = _stage_rows(rows, stage)
    return matches[-1] if matches else None


def _stage_rss(rows: list[dict[str, Any]], stage: str) -> int | None:
    row = _last_stage_row(rows, stage)
    value = row.get("vmrss_kb") if row else None
    return None if value is None else int(value)


def _pass_after_row(rows: list[dict[str, Any]], pass_argument: str) -> dict[str, Any] | None:
    for row in rows:
        if row.get("stage") != "mf_pass_after":
            continue
        extra = row.get("extra")
        if isinstance(extra, Mapping) and extra.get("pass_argument") == pass_argument:
            return row
    return None


def _pass_after_rss(rows: list[dict[str, Any]], pass_argument: str) -> int | None:
    row = _pass_after_row(rows, pass_argument)
    value = row.get("vmrss_kb") if row else None
    return None if value is None else int(value)


def _profile_peak_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return max(rows, key=lambda row: int(row.get("vmrss_kb", -1)), default={})


def _stage_label(row: Mapping[str, Any]) -> str | None:
    stage = row.get("stage")
    if not stage:
        return None
    extra = row.get("extra")
    key = extra.get("key") if isinstance(extra, Mapping) else None
    return f"{stage}:{key}" if key else str(stage)


def _compile_info_vector_total(row: Mapping[str, Any]) -> dict[str, Any]:
    extra = row.get("extra")
    if not isinstance(extra, Mapping):
        return {}
    compile_info = extra.get("compile_info")
    if not isinstance(compile_info, Mapping):
        return {}
    return {
        "vector_total_size": compile_info.get("vector_total_size"),
        "vector_total_capacity": compile_info.get("vector_total_capacity"),
        "vector_total_payload_bytes": compile_info.get("vector_total_payload_bytes"),
        "vector_total_capacity_bytes": compile_info.get("vector_total_capacity_bytes"),
        "runtime": compile_info.get("runtime"),
        "runtime_without_topology": compile_info.get("runtime_without_topology"),
        "qubit_volume": compile_info.get("qubit_volume"),
    }


def _extract_container_snapshots(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for row in rows:
        stage = str(row.get("stage", ""))
        if stage not in KEY_STAGES and not stage.startswith("compile_info_json_after_assign_"):
            continue
        extra = row.get("extra")
        if not isinstance(extra, Mapping):
            continue
        snapshot: dict[str, Any] = {
            "stage": stage,
            "stage_label": _stage_label(row),
            "vmrss_kb": row.get("vmrss_kb"),
            "elapsed_sec": row.get("elapsed_sec"),
        }
        for key in (
            "dep_graph_nodes",
            "dep_graph_edges",
            "time_series_runtime",
            "beat2inst_bucket_count",
            "beat2inst_pointer_count",
            "beat2inst_pointer_capacity",
            "beat2chip_count",
            "feedback_info_size",
            "json_top_level_size",
            "json_node_count",
            "json_array_element_count",
            "json_numeric_count",
            "json_string_bytes",
            "vector_size",
            "vector_capacity",
            "vector_payload_bytes",
            "vector_capacity_bytes",
        ):
            if key in extra:
                snapshot[key] = extra[key]
        json_dom = extra.get("json_dom")
        if isinstance(json_dom, Mapping):
            for key in (
                "json_node_count",
                "json_object_count",
                "json_array_count",
                "json_array_element_count",
                "json_numeric_count",
                "json_string_bytes",
            ):
                snapshot[key] = json_dom.get(key)
        snapshot.update(_compile_info_vector_total(row))
        snapshots.append(snapshot)
    return snapshots


def _summarize_profile(rows: list[dict[str, Any]]) -> dict[str, Any]:
    peak = _profile_peak_row(rows)
    stage_rss = {
        stage: _stage_rss(rows, stage)
        for stage in KEY_STAGES
        if _stage_rss(rows, stage) is not None
    }
    return {
        "profile_mark_count": len(rows),
        "max_profile_stage": peak.get("stage"),
        "max_profile_stage_label": _stage_label(peak),
        "max_profile_vmrss_kb": peak.get("vmrss_kb"),
        "stage_vmrss_kb": stage_rss,
        "post_calc_info_without_topology_rss_kb": _pass_after_rss(
            rows,
            "sc_ls_fixed_v0::calc_info_without_topology",
        ),
        "post_calc_info_with_topology_rss_kb": _pass_after_rss(
            rows,
            "sc_ls_fixed_v0::calc_info_with_topology",
        ),
        "post_dump_compile_info_rss_kb": _pass_after_rss(
            rows,
            "sc_ls_fixed_v0::dump_compile_info",
        ),
        "container_snapshots": _extract_container_snapshots(rows),
    }


def _run_qret(
    *,
    case: pre.CaseArtifact,
    run_name: str,
    passes: list[str],
    qret_path: Path,
    topology_path: Path,
    output_root: Path,
    sample_interval_sec: float,
    enable_internal_profile: bool,
) -> dict[str, Any]:
    run_root = output_root / case.name / run_name
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
            passes=passes,
            skip_pipeline_state_output=True,
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    if enable_internal_profile:
        env["QRET_RSS_PROFILE_JSONL"] = str(profile_jsonl)
    else:
        env.pop("QRET_RSS_PROFILE_JSONL", None)
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
    profile_summary = _summarize_profile(profile_rows)
    sample_summary = pre._summarize_samples(samples)
    compile_info_exists = compile_info_path.exists()
    metrics = (
        sc.surface_code_step_metrics_from_compile_info_json(compile_info_path)
        if compile_info_exists
        else {}
    )
    output_exists = output_path.exists()
    result = {
        "case": case.name,
        "run_name": run_name,
        "passes": list(passes),
        "skip_pipeline_state_output": True,
        "internal_profile_enabled": enable_internal_profile,
        "returncode": process.returncode,
        "elapsed_seconds": elapsed,
        "gnu_time_maxrss_kb": pre._parse_gnu_time_maxrss(stderr),
        "sample_interval_sec": sample_interval_sec,
        "pipeline_path": str(pipeline_path),
        "profile_jsonl": str(profile_jsonl) if enable_internal_profile else None,
        "samples_jsonl": str(samples_jsonl),
        "compile_info_path": str(compile_info_path) if compile_info_exists else None,
        "compile_info_exists": compile_info_exists,
        "compile_info_size_bytes": compile_info_path.stat().st_size
        if compile_info_exists
        else None,
        "output_path": str(output_path),
        "output_exists": output_exists,
        "output_size_bytes": output_path.stat().st_size if output_exists else None,
        "input_path": str(case.optimized_ir_path),
        "input_size_bytes": case.optimized_ir_path.stat().st_size,
        "optimized_ir_hash": case.optimized_ir_hash,
        "normalized_metrics": metrics,
        **profile_summary,
        **sample_summary,
    }
    _write_json(run_root / "summary.json", result)
    if process.returncode != 0:
        raise RuntimeError(
            f"qret failed for {case.name}/{run_name} with code {process.returncode}; "
            f"see {stderr_path}"
        )
    return result


def _normalized_metrics_for_compare(row: Mapping[str, Any]) -> dict[str, Any]:
    metrics = dict(row.get("normalized_metrics") or {})
    for key in IGNORED_METRIC_FIELDS:
        metrics.pop(key, None)
    return metrics


def _compare_metrics(profiled: Mapping[str, Any], unprofiled: Mapping[str, Any]) -> dict[str, Any]:
    profiled_metrics = _normalized_metrics_for_compare(profiled)
    unprofiled_metrics = _normalized_metrics_for_compare(unprofiled)
    semantic: dict[str, dict[str, Any]] = {}
    for field in SEMANTIC_FIELDS:
        profiled_has = field in profiled_metrics
        unprofiled_has = field in unprofiled_metrics
        semantic[field] = {
            "profiled_present": profiled_has,
            "unprofiled_present": unprofiled_has,
            "equal": profiled_has == unprofiled_has
            and (not profiled_has or profiled_metrics[field] == unprofiled_metrics[field]),
            "profiled": profiled_metrics.get(field),
            "unprofiled": unprofiled_metrics.get(field),
        }

    all_keys = sorted(set(profiled_metrics) | set(unprofiled_metrics))
    mismatches = [
        key
        for key in all_keys
        if profiled_metrics.get(key, object()) != unprofiled_metrics.get(key, object())
    ]
    return {
        "ignored_metric_fields": list(IGNORED_METRIC_FIELDS),
        "semantic_fields": semantic,
        "semantic_fields_equal": all(item["equal"] for item in semantic.values()),
        "normalized_metrics_equal": not mismatches,
        "normalized_metric_mismatches": mismatches,
    }


def _delta(a: Any, b: Any) -> int | None:
    if a is None or b is None:
        return None
    return int(b) - int(a)


def _case_prefix_rows(results: list[dict[str, Any]], case: str) -> list[dict[str, Any]]:
    return [
        row
        for row in results
        if row["case"] == case and row["run_name"] in PREFIX_PASSES
    ]


def _write_markdown_report(
    path: Path,
    *,
    results: list[dict[str, Any]],
    comparisons: Mapping[str, Any],
    qret_path: Path,
    topology_path: Path,
    sample_interval_sec: float,
) -> None:
    lines = [
        "# qret Calc-Info RSS Profile",
        "",
        f"- qret: `{qret_path}`",
        f"- topology: `{topology_path}`",
        f"- external sampler interval: `{sample_interval_sec:.3f}` sec",
        "- qret option: `sc_ls_fixed_v0_skip_pipeline_state_output: true`",
        "",
        "## Prefix Runs",
        "",
        "| case | prefix | elapsed s | GNU time max RSS KB | sampled tree peak KB | qret marker peak KB | compile-info size B | rc |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in results:
        if row["run_name"] not in PREFIX_PASSES:
            continue
        lines.append(
            "| {case} | {prefix} | {elapsed:.3f} | {maxrss} | {sample_peak} | "
            "{mark_peak} | {ci_size} | {rc} |".format(
                case=row["case"],
                prefix=row["run_name"],
                elapsed=float(row["elapsed_seconds"]),
                maxrss=row.get("gnu_time_maxrss_kb") or "",
                sample_peak=row.get("sampled_peak_tree_vmrss_kb") or "",
                mark_peak=row.get("max_profile_vmrss_kb") or "",
                ci_size=row.get("compile_info_size_bytes") or "",
                rc=row.get("returncode"),
            )
        )

    lines.extend(["", "## Key Stage RSS", ""])
    lines.append("| case | prefix | stage | VmRSS KB | delta from previous key stage KB |")
    lines.append("| --- | --- | --- | ---: | ---: |")
    for row in results:
        if row["run_name"] not in PREFIX_PASSES:
            continue
        previous = None
        stage_rss = row.get("stage_vmrss_kb") or {}
        for stage in KEY_STAGES:
            current = stage_rss.get(stage)
            if current is None:
                continue
            lines.append(
                "| {case} | {prefix} | `{stage}` | {rss} | {delta} |".format(
                    case=row["case"],
                    prefix=row["run_name"],
                    stage=stage,
                    rss=current,
                    delta="" if previous is None else int(current) - int(previous),
                )
            )
            previous = current

    lines.extend(["", "## Profiling On/Off Semantic Compare", ""])
    lines.append("| case | semantic fields equal | normalized metrics equal | mismatches |")
    lines.append("| --- | --- | --- | --- |")
    for case, comparison in comparisons.items():
        lines.append(
            "| {case} | {semantic} | {normalized} | {mismatches} |".format(
                case=case,
                semantic=comparison.get("semantic_fields_equal"),
                normalized=comparison.get("normalized_metrics_equal"),
                mismatches=", ".join(comparison.get("normalized_metric_mismatches") or []),
            )
        )

    lines.extend(["", "## Prefix Deltas", ""])
    lines.append("| case | A peak KB | B peak KB | C peak KB | D peak KB | B-A KB | C-B KB | D-C KB |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for case in sorted({row["case"] for row in results}):
        prefix_rows = {row["run_name"]: row for row in _case_prefix_rows(results, case)}
        a = prefix_rows.get("prefix_a_routing", {}).get("gnu_time_maxrss_kb")
        b = prefix_rows.get("prefix_b_calc_without_topology", {}).get("gnu_time_maxrss_kb")
        c = prefix_rows.get("prefix_c_calc_with_topology", {}).get("gnu_time_maxrss_kb")
        d = prefix_rows.get("prefix_d_dump_compile_info", {}).get("gnu_time_maxrss_kb")
        lines.append(
            "| {case} | {a} | {b} | {c} | {d} | {ba} | {cb} | {dc} |".format(
                case=case,
                a=a or "",
                b=b or "",
                c=c or "",
                d=d or "",
                ba=_delta(a, b) if _delta(a, b) is not None else "",
                cb=_delta(b, c) if _delta(b, c) is not None else "",
                dc=_delta(c, d) if _delta(c, d) is not None else "",
            )
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Profile qret calc-info and dump_compile_info RSS with pass prefixes."
    )
    parser.add_argument(
        "--case",
        action="append",
        choices=sorted(pre.DEFAULT_CASE_ARTIFACTS),
        help="Case to run. May be repeated. Default: H4 2nd and H4 4th(new_2).",
    )
    parser.add_argument(
        "--prefix",
        action="append",
        choices=sorted(PREFIX_PASSES),
        help="Prefix run to execute. May be repeated. Default: all A-D prefixes.",
    )
    parser.add_argument("--qret-path", type=Path, default=pre.DEFAULT_QRET_PATH)
    parser.add_argument("--topology-path", type=Path, default=pre.DEFAULT_TOPOLOGY_PATH)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--sample-interval-sec", type=float, default=0.02)
    parser.add_argument(
        "--skip-semantic-no-profile",
        action="store_true",
        help="Skip the extra full-D run with QRET_RSS_PROFILE_JSONL disabled.",
    )
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

    prefixes = args.prefix or list(PREFIX_PASSES)
    cases = args.case or sorted(pre.DEFAULT_CASE_ARTIFACTS)
    results: list[dict[str, Any]] = []
    comparisons: dict[str, Any] = {}
    for case_name in cases:
        case = pre._load_case_artifact(case_name)
        case_results: dict[str, dict[str, Any]] = {}
        for prefix in prefixes:
            result = _run_qret(
                case=case,
                run_name=prefix,
                passes=PREFIX_PASSES[prefix],
                qret_path=qret_path,
                topology_path=topology_path,
                output_root=output_root,
                sample_interval_sec=float(args.sample_interval_sec),
                enable_internal_profile=True,
            )
            case_results[prefix] = result
            results.append(result)
            print(
                "{case}/{prefix}: maxrss={maxrss}KB marker_peak={marker}KB "
                "compile_info_size={ci}".format(
                    case=case_name,
                    prefix=prefix,
                    maxrss=result.get("gnu_time_maxrss_kb"),
                    marker=result.get("max_profile_vmrss_kb"),
                    ci=result.get("compile_info_size_bytes"),
                ),
                flush=True,
            )

        if not args.skip_semantic_no_profile and FULL_PREFIX in case_results:
            no_profile = _run_qret(
                case=case,
                run_name="prefix_d_dump_compile_info_no_profile",
                passes=PREFIX_PASSES[FULL_PREFIX],
                qret_path=qret_path,
                topology_path=topology_path,
                output_root=output_root,
                sample_interval_sec=float(args.sample_interval_sec),
                enable_internal_profile=False,
            )
            results.append(no_profile)
            comparisons[case_name] = _compare_metrics(case_results[FULL_PREFIX], no_profile)
            print(
                "{case}/no_profile: maxrss={maxrss}KB metrics_equal={metrics}".format(
                    case=case_name,
                    maxrss=no_profile.get("gnu_time_maxrss_kb"),
                    metrics=comparisons[case_name].get("normalized_metrics_equal"),
                ),
                flush=True,
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
            "cases": cases,
            "prefixes": prefixes,
            "skip_pipeline_state_output": True,
            "semantic_fields": list(SEMANTIC_FIELDS),
            "ignored_metric_fields": list(IGNORED_METRIC_FIELDS),
        },
    )
    _write_markdown_report(
        output_root / "qret_calc_info_memory_profile.md",
        results=results,
        comparisons=comparisons,
        qret_path=qret_path,
        topology_path=topology_path,
        sample_interval_sec=float(args.sample_interval_sec),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
