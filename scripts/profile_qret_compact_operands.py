#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import csv
import json
import platform
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
for path in (SRC_ROOT, SCRIPTS_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from trotterlib import surface_code as sc  # noqa: E402

import profile_qret_magic_path_interning as magic_profile  # noqa: E402


DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "qret_compact_operands" / "phase1"
DEFAULT_BASELINE_SUMMARY = (
    REPO_ROOT / "artifacts" / "qret_compact_operands" / "phase0_magic_path" / "summary.json"
)
DEFAULT_REPORT = REPO_ROOT / "docs" / "benchmarks" / "qret_compact_operand_optimization.md"
DEFAULT_STRATEGY_REPORT = REPO_ROOT / "docs" / "benchmarks" / "qret_memory_reduction_strategy.md"
ALLOWED_CHAIN_LENGTHS = {4: "h4_4th_new2", 5: "h5_4th_new2"}
PROHIBITED_CHAIN_LENGTHS = {6, 7, 8, 9}
VARIANTS = ("baseline", "candidate")
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


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = (
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
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})


def _load_summary(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _validate_cases(cases: Sequence[str], chain_lengths: Sequence[int]) -> tuple[str, ...]:
    requested = list(cases)
    for length in chain_lengths:
        if length in PROHIBITED_CHAIN_LENGTHS or length > 5:
            raise ValueError("H6/H7/H8/H9 cases are prohibited for real qret/Evaluation execution")
        if length not in ALLOWED_CHAIN_LENGTHS:
            raise ValueError(f"unsupported chain length: {length}")
        requested.append(ALLOWED_CHAIN_LENGTHS[length])
    if not requested:
        requested = list(magic_profile.CASE_CHAIN_LENGTH)
    return magic_profile._validate_cases(requested)


def _median(values: Sequence[Any]) -> float | int | None:
    present = [value for value in values if value is not None]
    return statistics.median(present) if present else None


def _rows(results: Sequence[Mapping[str, Any]], *, case: str, variant: str) -> list[Mapping[str, Any]]:
    return [
        row
        for row in results
        if row.get("case") == case and row.get("variant") == variant
    ]


def _aggregate(results: Sequence[Mapping[str, Any]], *, case: str, variant: str) -> dict[str, Any]:
    rows = _rows(results, case=case, variant=variant)
    return {
        "case": case,
        "variant": variant,
        "runs": len(rows),
        "median_qret_peak_rss_kb": _median([row.get("qret_peak_rss_kb") for row in rows]),
        "median_tree_peak_rss_kb": _median([row.get("tree_peak_rss_kb") for row in rows]),
        "median_routing_peak_rss_kb": _median([row.get("routing_peak_rss_kb") for row in rows]),
        "median_routing_exit_rss_kb": _median([row.get("routing_exit_rss_kb") for row in rows]),
        "median_elapsed_seconds": _median([row.get("elapsed_seconds") for row in rows]),
    }


def _first(results: Sequence[Mapping[str, Any]], *, case: str, variant: str) -> Mapping[str, Any]:
    rows = _rows(results, case=case, variant=variant)
    return rows[0] if rows else {}


def _metric_comparisons(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ret: dict[str, Any] = {}
    for case in magic_profile.CASE_CHAIN_LENGTH:
        baseline = _first(results, case=case, variant="baseline")
        if not baseline:
            continue
        for row in _rows(results, case=case, variant="candidate"):
            ret[f"{case}:candidate:run_{row.get('run_index')}"] = magic_profile._compare_metrics(
                baseline,
                row,
            )
    return ret


def _all_candidate_below_baseline(results: Sequence[Mapping[str, Any]]) -> bool:
    baseline = [
        int(row["qret_peak_rss_kb"])
        for row in _rows(results, case="h5_4th_new2", variant="baseline")
        if row.get("qret_peak_rss_kb") is not None
    ]
    candidate = [
        int(row["qret_peak_rss_kb"])
        for row in _rows(results, case="h5_4th_new2", variant="candidate")
        if row.get("qret_peak_rss_kb") is not None
    ]
    return bool(baseline and candidate) and max(candidate) < min(baseline)


def _adoption_decision(
    results: Sequence[Mapping[str, Any]],
    comparisons: Mapping[str, Any],
) -> dict[str, Any]:
    h4_cmp = comparisons.get("h4_4th_new2:candidate:run_1", {})
    semantic = bool(
        h4_cmp.get("raw", {}).get("all_equal")
        and h4_cmp.get("normalized", {}).get("all_equal")
    )
    baseline = _aggregate(results, case="h5_4th_new2", variant="baseline")
    candidate = _aggregate(results, case="h5_4th_new2", variant="candidate")
    base_peak = baseline.get("median_qret_peak_rss_kb")
    cand_peak = candidate.get("median_qret_peak_rss_kb")
    reduction_kb = None
    reduction_pct = None
    if base_peak is not None and cand_peak is not None:
        reduction_kb = int(base_peak) - int(cand_peak)
        reduction_pct = 100.0 * float(reduction_kb) / float(base_peak)
    base_elapsed = baseline.get("median_elapsed_seconds")
    cand_elapsed = candidate.get("median_elapsed_seconds")
    elapsed_regression_pct = None
    if base_elapsed not in (None, 0) and cand_elapsed is not None:
        elapsed_regression_pct = (
            100.0 * (float(cand_elapsed) - float(base_elapsed)) / float(base_elapsed)
        )
    peak_gate = reduction_kb is not None and (
        reduction_kb >= 25 * 1024 or float(reduction_pct or 0.0) >= 5.0
    )
    elapsed_gate = elapsed_regression_pct is not None and elapsed_regression_pct <= 3.0
    path_stats_unchanged = _path_interning_unchanged(results)
    return {
        "raw_metrics_parity": all(
            cmp_row.get("raw", {}).get("all_equal") for cmp_row in comparisons.values()
        ),
        "normalized_metrics_parity": all(
            cmp_row.get("normalized", {}).get("all_equal") for cmp_row in comparisons.values()
        ),
        "h4_semantic_parity": semantic,
        "h5_median_qret_peak_reduction_kb": reduction_kb,
        "h5_median_qret_peak_reduction_percent": reduction_pct,
        "all_candidate_runs_below_baseline": _all_candidate_below_baseline(results),
        "elapsed_regression_percent": elapsed_regression_pct,
        "elapsed_gate_3_percent": elapsed_gate,
        "path_interning_stats_unchanged": path_stats_unchanged,
        "production_candidate_adopted_by_h5_measurement": bool(
            semantic
            and peak_gate
            and _all_candidate_below_baseline(results)
            and elapsed_gate
            and path_stats_unchanged
        ),
    }


def _path_interning_unchanged(results: Sequence[Mapping[str, Any]]) -> bool:
    baseline = _first(results, case="h5_4th_new2", variant="baseline").get("machine_extra", {})
    candidates = _rows(results, case="h5_4th_new2", variant="candidate")
    if not baseline or not candidates:
        return False
    keys = ("magic_path_unique_interned_path_count", "magic_path_intern_hit_rate_percent")
    for row in candidates:
        extra = row.get("machine_extra", {})
        for key in keys:
            if extra.get(key) != baseline.get(key):
                return False
    return True


def _baseline_rows(summary: Mapping[str, Any], cases: Sequence[str]) -> list[dict[str, Any]]:
    rows = []
    for row in summary.get("results", []):
        if row.get("case") in cases and row.get("variant") == "candidate":
            copied = copy.deepcopy(row)
            copied["variant"] = "baseline"
            copied["operand_storage_mode"] = "legacy_list_operands"
            rows.append(copied)
    return rows


def _h9_estimates(summary: Mapping[str, Any]) -> dict[str, Any]:
    relabeled = copy.deepcopy(summary)
    for row in relabeled.get("results", []):
        if row.get("variant") == "baseline":
            row["variant"] = "legacy"
    return magic_profile._h9_estimates(relabeled)


def _fmt_int(value: Any) -> str:
    return "" if value is None else f"{int(value):,}"


def _fmt_float(value: Any) -> str:
    return "" if value is None else f"{float(value):.3f}"


def _fmt_mb_from_bytes(value: Any) -> str:
    return "" if value is None else f"{float(value) / ONE_MB:.1f}"


def _component_bytes(row: Mapping[str, Any], key: str) -> int:
    item = row.get("component_estimates", {}).get(key, {})
    return int(item.get("bytes") or 0) if isinstance(item, Mapping) else 0


def _extra_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    extra = row.get("extra", {})
    return dict(extra) if isinstance(extra, Mapping) else {}


def _routing_peak_row_with_machine_extra(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    live_stages = {
        "routing_after_inst_queue_construct",
        "routing_after_queue_construct",
        "routing_after_route_searcher_construct",
        "routing_after_simulator_construct",
        "routing_after_state_construct",
        "routing_after_initial_queue_peek",
        "routing_after_initial_peek",
        "routing_before_main_loop",
        "routing_main_loop_peak",
        "routing_main_loop_exit",
        "routing_before_temporary_destroy",
    }
    best: Mapping[str, Any] = {}
    best_rss = -1
    for row in rows:
        stage = str(row.get("stage", ""))
        if stage not in live_stages:
            continue
        extra = row.get("extra", {})
        if not isinstance(extra, Mapping) or "machine_total_bytes_estimated" not in extra:
            continue
        rss = int(row.get("vmrss_kb") or 0)
        if rss >= best_rss:
            best = row
            best_rss = rss
    return dict(best)


def _enrich_stage_live_components(row: Mapping[str, Any]) -> dict[str, Any]:
    copied = copy.deepcopy(row)
    profile_rows = copied.get("profile_rows", [])
    if not isinstance(profile_rows, list):
        return copied

    routing_peak_row = _routing_peak_row_with_machine_extra(profile_rows)
    routing_peak_extra = _extra_from_row(routing_peak_row)
    before_release_extra = magic_profile._extra_at_stage(
        profile_rows,
        "routing_before_inverse_map_release",
        last=True,
        required_key="machine_total_bytes_estimated",
    )
    after_release_extra = magic_profile._extra_at_stage(
        profile_rows,
        "routing_after_inverse_map_release",
        last=True,
        required_key="machine_total_bytes_estimated",
    )
    routing_exit_extra = magic_profile._extra_at_stage(
        profile_rows,
        "routing_pass_exit",
        last=True,
        required_key="machine_total_bytes_estimated",
    )
    parent_peak_kb = copied.get("parent_peak_rss_kb")
    if parent_peak_kb is None:
        sample_summary = copied.get("sample_summary", {})
        if isinstance(sample_summary, Mapping):
            parent_peak_kb = sample_summary.get("sampled_peak_parent_vmrss_kb")

    if routing_peak_extra:
        copied["routing_peak_extra"] = routing_peak_extra
        copied["routing_peak_stage_for_components"] = routing_peak_row.get("stage")
        copied["routing_peak_component_estimates"] = magic_profile._component_estimates(
            machine_extra=routing_peak_extra,
            routing_extra=routing_peak_extra,
            parent_peak_kb=parent_peak_kb,
        )
        copied["component_estimates"] = copied["routing_peak_component_estimates"]
        copied["bytes_per_instruction_estimated"] = None
        if routing_peak_extra.get("machine_instructions"):
            copied["bytes_per_instruction_estimated"] = float(
                routing_peak_extra.get("machine_total_bytes_estimated") or 0
            ) / float(routing_peak_extra.get("machine_instructions"))
    if before_release_extra:
        copied["routing_before_inverse_map_release_extra"] = before_release_extra
    if after_release_extra:
        copied["routing_after_inverse_map_release_extra"] = after_release_extra
        copied["machine_extra"] = after_release_extra
        copied["machine_instructions"] = after_release_extra.get("machine_instructions")
        copied["machine_type_counts"] = magic_profile._type_counts(after_release_extra)
        copied["machine_type_total_bytes"] = magic_profile._type_total_bytes(after_release_extra)
    if routing_exit_extra:
        copied["routing_exit_extra"] = routing_exit_extra
    return copied


def _write_report(path: Path, summary: Mapping[str, Any]) -> None:
    aggregates = {
        f"{row.get('case')}:{row.get('variant')}": row
        for row in summary.get("aggregates", [])
        if isinstance(row, Mapping)
    }
    adoption = summary.get("adoption_decision", {})
    lines = [
        "# qret Compact Singleton Operand A/B",
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
        "## Phase 0 Magic Path Baseline",
        "",
        "- final holder: `std::list<Coord3D>` plus optional shared handle",
        "- production default: `interned`",
        "- rollback: `QRET_MAGIC_PATH_STORAGE=legacy_list`",
        "- Phase 1 baseline source: Phase 0 interned runs from current final-holder validation.",
        "",
        "## Compact Operand Scope",
        "",
        "- `TWIST.qtarget`",
        "- `HADAMARD.qtarget`",
        "- `LATTICE_SURGERY_MAGIC.qtarget`",
        "- `LATTICE_SURGERY_MAGIC.ccreate`",
        "- `LATTICE_SURGERY_MAGIC.mtarget`",
        "- `PROBABILITY_HINT.cdepend`",
        "",
        "## Run Matrix",
        "",
        "| case | variant | runs | median qret peak KB | median routing peak KB | median routing exit KB | median elapsed s |",
        "| ---- | ------- | ---: | ------------------: | ---------------------: | ---------------------: | ---------------: |",
    ]
    for case in magic_profile.CASE_CHAIN_LENGTH:
        for variant in VARIANTS:
            row = aggregates.get(f"{case}:{variant}", {})
            lines.append(
                f"| {magic_profile.CASE_DISPLAY[case]} | {variant} | {_fmt_int(row.get('runs'))} | "
                f"{_fmt_int(row.get('median_qret_peak_rss_kb'))} | "
                f"{_fmt_int(row.get('median_routing_peak_rss_kb'))} | "
                f"{_fmt_int(row.get('median_routing_exit_rss_kb'))} | "
                f"{_fmt_float(row.get('median_elapsed_seconds'))} |"
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
    for key, row in summary.get("comparisons", {}).items():
        lines.append(
            f"| {key} | {row.get('raw', {}).get('all_equal')} | "
            f"{row.get('normalized', {}).get('all_equal')} | "
            f"{row.get('raw', {}).get('mismatches')} | "
            f"{row.get('normalized', {}).get('mismatches')} |"
        )
    lines.extend(
        [
            "",
            "## H5 Gate",
            "",
            f"- raw metrics parity: `{adoption.get('raw_metrics_parity')}`",
            f"- normalized metrics parity: `{adoption.get('normalized_metrics_parity')}`",
            f"- path interning stats unchanged: `{adoption.get('path_interning_stats_unchanged')}`",
            "- H5 median qret peak reduction KB: "
            f"`{_fmt_int(adoption.get('h5_median_qret_peak_reduction_kb'))}`",
            "- H5 median qret peak reduction percent: "
            f"`{_fmt_float(adoption.get('h5_median_qret_peak_reduction_percent'))}`",
            f"- all candidate runs below baseline: `{adoption.get('all_candidate_runs_below_baseline')}`",
            "- elapsed regression percent: "
            f"`{_fmt_float(adoption.get('elapsed_regression_percent'))}`",
            f"- elapsed gate <=3%: `{adoption.get('elapsed_gate_3_percent')}`",
            "- production candidate adopted by H5 measurement: "
            f"`{adoption.get('production_candidate_adopted_by_h5_measurement')}`",
            "",
            "## Routing Peak Operand Component Snapshot",
            "",
            "| case | variant | run | MachineFunction inst | non-path operand MB | path storage MB | qtarget node MB | cdepend node MB | ccreate node MB | mtarget node MB |",
            "| ---- | ------- | --: | -------------------: | ------------------: | --------------: | --------------: | ---------------: | ---------------: | --------------: |",
        ]
    )
    for row in summary.get("results", []):
        extra = row.get("routing_peak_extra", row.get("machine_extra", {}))
        path_bytes = _component_bytes(row, "path_storage")
        operand_bytes = _component_bytes(row, "operand_containers")
        lines.append(
            f"| {magic_profile.CASE_DISPLAY[str(row.get('case'))]} | {row.get('variant')} | "
            f"{row.get('run_index')} | {_fmt_int(row.get('machine_instructions'))} | "
            f"{_fmt_mb_from_bytes(operand_bytes)} | {_fmt_mb_from_bytes(path_bytes)} | "
            f"{_fmt_mb_from_bytes(extra.get('machine_qtarget_list_node_bytes_estimated'))} | "
            f"{_fmt_mb_from_bytes(extra.get('machine_cdepend_list_node_bytes_estimated'))} | "
            f"{_fmt_mb_from_bytes(extra.get('machine_ccreate_list_node_bytes_estimated'))} | "
            f"{_fmt_mb_from_bytes(extra.get('machine_mtarget_list_node_bytes_estimated'))} |"
        )
    lines.extend(
        [
            "",
            "## Safety And Provenance",
            "",
            "H5 runs recorded `MemTotal`, `MemAvailable`, `SwapTotal`, `SwapFree`, and disk free before execution. H6-H9 are rejected by script guard and test guard.",
            "",
            f"- baseline summary: `{summary.get('environment', {}).get('baseline_summary')}`",
            f"- candidate qret hash: `{summary.get('environment', {}).get('measurement_runtime_hashes', {}).get('qret_executable_hash')}`",
            f"- candidate lib hash: `{summary.get('environment', {}).get('measurement_runtime_hashes', {}).get('qret_core_library_hash')}`",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_profile(
    *,
    output_root: Path,
    baseline_summary_path: Path,
    report_path: Path,
    cache_root: Path,
    build: bool,
    cases: Sequence[str],
    chain_lengths: Sequence[int],
    batch_size: int,
    sample_interval_sec: float,
) -> dict[str, Any]:
    cases = _validate_cases(cases, chain_lengths)
    output_root.mkdir(parents=True, exist_ok=True)
    baseline_summary = _load_summary(baseline_summary_path)
    baseline_rows = [
        _enrich_stage_live_components(row)
        for row in _baseline_rows(baseline_summary, cases)
    ]
    if not baseline_rows:
        raise RuntimeError("baseline summary does not contain Phase 0 interned rows")
    qret_path = Path(magic_profile._architecture().qret_path).expanduser().resolve()
    build_provenance = magic_profile.base._build_qret_and_record(qret_path, build=build)
    runtime_hashes = magic_profile.base._runtime_hashes(qret_path)
    meminfo_start = magic_profile._meminfo()
    environment = {
        "evaluation_head": magic_profile._git_output(["rev-parse", "HEAD"]),
        "baseline_summary": str(baseline_summary_path.resolve()),
        "measurement_runtime_hashes": runtime_hashes,
        "platform": platform.platform(),
        "python": sys.version,
        "meminfo": meminfo_start,
        "safety_snapshot_start": magic_profile._safety_snapshot(),
        "disk_free_bytes": magic_profile._disk_free_bytes(REPO_ROOT),
        "batch_size": batch_size,
        "sample_interval_sec": sample_interval_sec,
        "output_root": str(output_root.resolve()),
        "largest_measured_case": "H5",
        "h6_executed": False,
        "h7_executed": False,
        "h8_executed": False,
        "h9_executed": False,
    }
    artifacts = magic_profile._prepare_artifacts(cases, cache_root=cache_root, batch_size=batch_size)
    environment["artifacts"] = {
        case: magic_profile.base.compact_profile._artifact_summary(artifact)
        for case, artifact in artifacts.items()
    }
    results = list(baseline_rows)
    run_plan = {case: {"candidate": 1 if case == "h4_4th_new2" else 2} for case in cases}
    for case, variants in run_plan.items():
        for _variant, count in variants.items():
            for run_index in range(1, count + 1):
                row = magic_profile._run_qret_once(
                    case_key=case,
                    variant="candidate",
                    artifact=artifacts[case],
                    run_index=run_index,
                    output_root=output_root,
                    sample_interval_sec=sample_interval_sec,
                    memtotal_kb=meminfo_start.get("MemTotal"),
                    expected_runtime_hashes=runtime_hashes,
                )
                row["variant"] = "candidate"
                row["operand_storage_mode"] = "compact_singleton_v1"
                row = _enrich_stage_live_components(row)
                results.append(row)
                _write_csv(output_root / "summary.csv", results)
                _write_json(output_root / "summary.json", {"environment": environment, "results": results})
    aggregates = [
        _aggregate(results, case=case, variant=variant)
        for case in magic_profile.CASE_CHAIN_LENGTH
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
    _write_report(report_path, summary)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run H4/H5-only A/B for qret compact singleton operand storage."
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--baseline-summary", type=Path, default=DEFAULT_BASELINE_SUMMARY)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--cache-root", type=Path, default=DEFAULT_OUTPUT_ROOT / "surface_code_cache")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--sample-interval-sec", type=float, default=0.02)
    parser.add_argument("--cases", nargs="*", default=())
    parser.add_argument("--chain-lengths", nargs="*", type=int, default=())
    args = parser.parse_args(argv)
    run_profile(
        output_root=args.output_root.resolve(),
        baseline_summary_path=args.baseline_summary.resolve(),
        report_path=args.report.resolve(),
        cache_root=args.cache_root.resolve(),
        build=not args.skip_build,
        cases=args.cases,
        chain_lengths=args.chain_lengths,
        batch_size=args.batch_size,
        sample_interval_sec=args.sample_interval_sec,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
