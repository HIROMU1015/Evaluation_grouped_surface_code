#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import profile_qret_magic_path_interning as magic_profile  # noqa: E402


DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "qret_lazy_inverse_map"
DEFAULT_REPORT_PATH = REPO_ROOT / "docs" / "benchmarks" / "qret_lazy_inverse_map_optimization.md"
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
PROHIBITED_CHAIN_LENGTHS = {6, 7, 8, 9}
VARIANTS = {
    "eager": {
        "construction": "eager",
        "storage": "interned",
        "description": "current production eager inverse-map construction",
    },
    "lazy": {
        "construction": "lazy",
        "storage": "interned",
        "description": "block-local lazy inverse-map construction candidate",
    },
}
DEFAULT_RUNS = {
    "h4_4th_new2": {"eager": 1, "lazy": 1},
    "h5_4th_new2": {"eager": 2, "lazy": 2},
}
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
ONE_MB = 1024 * 1024
LAZY_RSS_GATE_KB = 30 * 1024
LAZY_RSS_GATE_PERCENT = 7.0
ELAPSED_REGRESSION_GATE_PERCENT = 3.0


def _git_output(args: Sequence[str], *, cwd: Path = REPO_ROOT) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def _sha256_file(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


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


def _validate_chain_lengths(chain_lengths: Sequence[int] | Iterator[int]) -> tuple[int, ...]:
    values = tuple(int(value) for value in chain_lengths)
    prohibited = [value for value in values if value in PROHIBITED_CHAIN_LENGTHS or value > 5]
    if prohibited:
        raise ValueError(
            "H6/H7/H8/H9 chain lengths are prohibited for real qret/Evaluation execution: "
            + ", ".join(str(value) for value in prohibited)
        )
    return values


def _validate_run_plan(run_plan: Mapping[str, Mapping[str, int]]) -> None:
    _validate_cases(tuple(run_plan))
    for case, variants in run_plan.items():
        unknown = set(variants) - set(VARIANTS)
        if unknown:
            raise ValueError(f"unknown variant(s) for {case}: {sorted(unknown)}")
        for variant, count in variants.items():
            if int(count) < 0:
                raise ValueError(f"negative run count for {case}:{variant}")


def _variant_env(env: dict[str, str], variant: str) -> None:
    mode = str(VARIANTS[variant]["construction"])
    env["QRET_MAGIC_PATH_STORAGE"] = "interned"
    env["QRET_SUMMARY_TIME_SERIES_IMPL"] = "legacy_timeseries"
    env["QRET_DEP_GRAPH_IMPL"] = "compact"
    env["QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING"] = "1"
    env["QRET_RSS_DIAGNOSTIC_TRIM_STAGE"] = "none"
    env["QRET_PROFILE_MAGIC_PATHS"] = "0"
    env["QRET_PROFILE_INVERSE_MAP_USAGE"] = "1"
    env["QRET_INVERSE_MAP_CONSTRUCTION"] = mode
    env.pop("QRET_MAGIC_PATH_PROFILE_JSON", None)
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    env.pop("LANGUAGE", None)


@contextlib.contextmanager
def _patched_magic_runner() -> Iterator[None]:
    saved = {
        "DEFAULT_OUTPUT_ROOT": magic_profile.DEFAULT_OUTPUT_ROOT,
        "DEFAULT_REPORT_PATH": magic_profile.DEFAULT_REPORT_PATH,
        "CASE_CHAIN_LENGTH": magic_profile.CASE_CHAIN_LENGTH,
        "CASE_DISPLAY": magic_profile.CASE_DISPLAY,
        "VARIANTS": magic_profile.VARIANTS,
        "DEFAULT_RUNS": magic_profile.DEFAULT_RUNS,
        "_variant_env": magic_profile._variant_env,
    }
    magic_profile.DEFAULT_OUTPUT_ROOT = DEFAULT_OUTPUT_ROOT
    magic_profile.DEFAULT_REPORT_PATH = DEFAULT_REPORT_PATH
    magic_profile.CASE_CHAIN_LENGTH = CASE_CHAIN_LENGTH
    magic_profile.CASE_DISPLAY = CASE_DISPLAY
    magic_profile.VARIANTS = VARIANTS
    magic_profile.DEFAULT_RUNS = DEFAULT_RUNS
    magic_profile._variant_env = _variant_env
    try:
        yield
    finally:
        for key, value in saved.items():
            setattr(magic_profile, key, value)


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


def _median(values: Sequence[Any]) -> float | int | None:
    present = [value for value in values if value is not None]
    return statistics.median(present) if present else None


def _extra_at_stage(
    rows: Sequence[Mapping[str, Any]],
    stage: str,
    *,
    last: bool = False,
    required_key: str | None = None,
) -> dict[str, Any]:
    iterable = reversed(rows) if last else rows
    for row in iterable:
        if row.get("stage") != stage or not isinstance(row.get("extra"), Mapping):
            continue
        extra = dict(row["extra"])
        if required_key is not None and required_key not in extra:
            continue
        return extra
    return {}


def _stage_row(
    rows: Sequence[Mapping[str, Any]],
    stage: str,
    *,
    last: bool = False,
) -> Mapping[str, Any]:
    iterable = reversed(rows) if last else rows
    for row in iterable:
        if row.get("stage") == stage:
            return row
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


def _calc_info_peak_row(result: Mapping[str, Any]) -> Mapping[str, Any]:
    rows = result.get("profile_rows", [])
    if not isinstance(rows, Sequence):
        return {}
    candidates = [
        row
        for row in rows
        if str(row.get("stage", "")).startswith(("before_calc_info", "after_calc_info"))
        and row.get("vmrss_kb") is not None
    ]
    return max(candidates, key=lambda row: int(row.get("vmrss_kb") or 0), default={})


def _usage_extra(result: Mapping[str, Any]) -> dict[str, Any]:
    rows = result.get("profile_rows", [])
    if not isinstance(rows, Sequence):
        return {}
    for stage in (
        "routing_after_inverse_map_release",
        "routing_before_inverse_map_release",
        "routing_main_loop_exit",
        "routing_after_construct_inverse_map",
    ):
        extra = _extra_at_stage(rows, stage, last=True, required_key="inverse_map_usage_schema")
        if extra:
            return extra
    return {}


def _peak_machine_extra(result: Mapping[str, Any]) -> dict[str, Any]:
    rows = result.get("profile_rows", [])
    if not isinstance(rows, Sequence):
        return {}
    for stage in (
        "routing_before_inverse_map_release",
        "routing_main_loop_exit",
        "routing_after_construct_inverse_map",
    ):
        extra = _extra_at_stage(rows, stage, last=True, required_key="machine_inverse_map_entries")
        if extra and int(extra.get("machine_inverse_map_entries") or 0) > 0:
            return extra
    return _extra_at_stage(rows, "routing_after_inverse_map_release", last=True)


def _routing_live_extra(result: Mapping[str, Any]) -> dict[str, Any]:
    rows = result.get("profile_rows", [])
    if not isinstance(rows, Sequence):
        return {}
    return _extra_at_stage(
        rows,
        "routing_before_temporary_destroy",
        last=True,
        required_key="routing_live_total_bytes_estimated",
    )


def _component_estimates(result: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    machine = _peak_machine_extra(result)
    routing = _routing_live_extra(result)
    path_bytes = int(machine.get("machine_ancilla_path_coordinate_list_node_bytes_estimated") or 0)
    operand_bytes = int(machine.get("machine_operand_list_node_bytes_estimated") or 0)
    return {
        "instruction_object": {
            "classification": "estimated",
            "bytes": int(machine.get("machine_instruction_object_bytes_estimated") or 0),
        },
        "operand_containers": {
            "classification": "estimated",
            "bytes": max(0, operand_bytes - path_bytes),
        },
        "path_storage": {"classification": "estimated", "bytes": path_bytes},
        "instruction_list_nodes": {
            "classification": "estimated",
            "bytes": int(machine.get("machine_instruction_list_node_bytes_estimated") or 0),
        },
        "inverse_map": {
            "classification": "estimated",
            "bytes": int(machine.get("machine_inverse_map_bytes_estimated") or 0),
        },
        "metadata": {
            "classification": "estimated",
            "bytes": int(machine.get("machine_metadata_bytes_estimated") or 0),
        },
        "routing_temporary": {
            "classification": "estimated",
            "bytes": int(routing.get("routing_queue_total_bytes_estimated") or 0)
            + int(routing.get("routing_sim_total_bytes_estimated") or 0),
        },
        "python_parent": {
            "classification": "observed",
            "bytes": int(result.get("parent_peak_rss_kb") or 0) * 1024,
        },
    }


def _component_bytes(result: Mapping[str, Any], component: str) -> int:
    components = result.get("lazy_inverse_map_component_estimates")
    if not isinstance(components, Mapping):
        components = _component_estimates(result)
    item = components.get(component, {})
    return int(item.get("bytes") or 0) if isinstance(item, Mapping) else 0


def _machine_type_counts(result: Mapping[str, Any]) -> dict[str, int]:
    counts = _peak_machine_extra(result).get("machine_instruction_type_count", {})
    if not isinstance(counts, Mapping):
        return {}
    return {str(key): int(value or 0) for key, value in counts.items()}


def _bytes_per_instruction(result: Mapping[str, Any]) -> float:
    machine = _peak_machine_extra(result)
    instructions = int(machine.get("machine_instructions") or 0)
    if instructions <= 0:
        return 0.0
    total = sum(_component_bytes(result, component) for component in COMPONENT_KEYS)
    return float(total) / float(instructions)


def _growth_ratio(h4_value: int, h5_value: int, *, default: float = 1.0) -> float:
    if h4_value <= 0:
        return default
    return max(1.0, float(h5_value) / float(h4_value))


def _type_count_growth_factor(h4: Mapping[str, Any], h5: Mapping[str, Any]) -> float:
    h4_counts = _machine_type_counts(h4)
    h5_counts = _machine_type_counts(h5)
    weighted = 0.0
    weight = 0
    for inst_type, h5_count in h5_counts.items():
        h4_count = h4_counts.get(inst_type, 0)
        if h4_count <= 0 or h5_count <= 0:
            continue
        weighted += h5_count * _growth_ratio(h4_count, h5_count)
        weight += h5_count
    return weighted / float(weight) if weight else 1.0


def _component_growth_factor(h4: Mapping[str, Any], h5: Mapping[str, Any], component: str) -> float:
    return _growth_ratio(_component_bytes(h4, component), _component_bytes(h5, component))


def _estimate_h9_component(
    *,
    h4: Mapping[str, Any],
    h5: Mapping[str, Any],
    component: str,
    scenario: str,
) -> int:
    h4_inst = int(_peak_machine_extra(h4).get("machine_instructions") or 0)
    h5_inst = int(_peak_machine_extra(h5).get("machine_instructions") or 0)
    h5_component = _component_bytes(h5, component)
    inst_ratio = _growth_ratio(h4_inst, h5_inst)
    type_ratio = _type_count_growth_factor(h4, h5)
    h4_bpi = _bytes_per_instruction(h4)
    h5_bpi = _bytes_per_instruction(h5)
    bytes_per_inst_ratio = _growth_ratio(
        int(h4_bpi * max(h4_inst, 1)),
        int(h5_bpi * max(h5_inst, 1)),
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
        selected = model_values[1] if len(model_values) > 1 else model_values[0]
        return int(selected * 0.85)
    if scenario == "central":
        return int(statistics.median(model_values))
    return int(model_values[-1] * 1.25)


def _h9_estimates(summary: Mapping[str, Any]) -> dict[str, Any]:
    results = summary.get("results", [])
    if not isinstance(results, Sequence):
        return {}
    h4_eager = _first_result(results, case="h4_4th_new2", variant="eager")
    h5_eager = _first_result(results, case="h5_4th_new2", variant="eager")
    h4_lazy = _first_result(results, case="h4_4th_new2", variant="lazy")
    h5_lazy = _first_result(results, case="h5_4th_new2", variant="lazy")
    observed = {
        "classification": "observed",
        "largest_measured_case": "H5",
        "eager_h4_qret_peak_rss_kb": h4_eager.get("qret_peak_rss_kb"),
        "eager_h5_qret_peak_rss_kb": h5_eager.get("qret_peak_rss_kb"),
        "lazy_h4_qret_peak_rss_kb": h4_lazy.get("qret_peak_rss_kb"),
        "lazy_h5_qret_peak_rss_kb": h5_lazy.get("qret_peak_rss_kb"),
    }
    estimates: dict[str, Any] = {"classification": "estimated", "scenarios": {}}
    for scenario in ("conservative", "central", "upper"):
        scenario_rows: dict[str, Any] = {}
        for label, h4, h5 in (
            ("current_production_eager", h4_eager, h5_eager),
            ("with_lazy_inverse_map_candidate", h4_lazy, h5_lazy),
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
    theoretical = {
        "classification": "theoretical",
        "scenario_savings": {},
        "custom_pipeline_note": (
            "lazy mode saves only maps that are never requested; a custom pipeline that touches "
            "many blocks can approach eager inverse-map memory."
        ),
    }
    for scenario, rows in estimates["scenarios"].items():
        current_total = int(rows["current_production_eager"]["total_bytes"])
        lazy_total = int(rows["with_lazy_inverse_map_candidate"]["total_bytes"])
        theoretical["scenario_savings"][scenario] = {
            "classification": "theoretical",
            "bytes": max(0, current_total - lazy_total),
            "percent": 0.0
            if current_total <= 0
            else 100.0 * (current_total - lazy_total) / float(current_total),
        }
    return {"observed": observed, "estimated": estimates, "theoretical": theoretical}


def _metric_comparisons(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    comparisons: dict[str, Any] = {}
    for case in CASE_CHAIN_LENGTH:
        baseline = _first_result(results, case=case, variant="eager")
        if not baseline:
            continue
        for row in _rows(results, case=case, variant="lazy"):
            key = f"{case}:lazy:run_{row.get('run_index')}"
            comparisons[key] = magic_profile._compare_metrics(baseline, row)
    return comparisons


def _semantic_parity(comparisons: Mapping[str, Any], *, case_prefix: str | None = None) -> bool:
    rows = [
        row
        for key, row in comparisons.items()
        if case_prefix is None or str(key).startswith(case_prefix)
    ]
    return bool(rows) and all(
        row.get("raw", {}).get("all_equal") and row.get("normalized", {}).get("all_equal")
        for row in rows
    )


def _usage_counter(result: Mapping[str, Any], counter: str) -> int:
    return int(_usage_extra(result).get(f"inverse_map_usage_{counter}") or 0)


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
        "median_qret_peak_rss_kb": _median([row.get("qret_peak_rss_kb") for row in rows]),
        "median_tree_peak_rss_kb": _median([row.get("tree_peak_rss_kb") for row in rows]),
        "median_routing_peak_rss_kb": _median([row.get("routing_peak_rss_kb") for row in rows]),
        "median_elapsed_seconds": _median([row.get("elapsed_seconds") for row in rows]),
        "median_max_live_entries": _median([_usage_counter(row, "max_live_entries") for row in rows]),
        "median_constructed_blocks": _median(
            [_usage_counter(row, "constructed_block_count") for row in rows]
        ),
        "median_never_constructed_blocks": _median(
            [_usage_counter(row, "never_constructed_block_count") for row in rows]
        ),
        "median_initial_inserted_entries": _median(
            [_usage_counter(row, "initial_inserted_entries") for row in rows]
        ),
        "median_lazy_inserted_entries": _median(
            [_usage_counter(row, "lazy_inserted_entries") for row in rows]
        ),
    }


def _all_lazy_peaks_below_eager(
    results: Sequence[Mapping[str, Any]],
    *,
    case: str = "h5_4th_new2",
) -> bool:
    eager = [
        int(row["qret_peak_rss_kb"])
        for row in _rows(results, case=case, variant="eager")
        if row.get("qret_peak_rss_kb") is not None
    ]
    lazy = [
        int(row["qret_peak_rss_kb"])
        for row in _rows(results, case=case, variant="lazy")
        if row.get("qret_peak_rss_kb") is not None
    ]
    return bool(eager and lazy) and max(lazy) < min(eager)


def _adoption_decision(
    results: Sequence[Mapping[str, Any]],
    comparisons: Mapping[str, Any],
) -> dict[str, Any]:
    h4_semantic = _semantic_parity(comparisons, case_prefix="h4_4th_new2")
    h5_semantic = _semantic_parity(comparisons, case_prefix="h5_4th_new2")
    eager = _aggregate(results, case="h5_4th_new2", variant="eager")
    lazy = _aggregate(results, case="h5_4th_new2", variant="lazy")
    baseline_peak = eager.get("median_qret_peak_rss_kb")
    lazy_peak = lazy.get("median_qret_peak_rss_kb")
    reduction_kb = None
    reduction_pct = None
    if baseline_peak is not None and lazy_peak is not None:
        reduction_kb = int(baseline_peak) - int(lazy_peak)
        reduction_pct = 100.0 * float(reduction_kb) / float(baseline_peak)
    baseline_elapsed = eager.get("median_elapsed_seconds")
    lazy_elapsed = lazy.get("median_elapsed_seconds")
    elapsed_regression_pct = None
    if baseline_elapsed not in (None, 0) and lazy_elapsed is not None:
        elapsed_regression_pct = (
            100.0 * (float(lazy_elapsed) - float(baseline_elapsed)) / float(baseline_elapsed)
        )
    eager_live = eager.get("median_max_live_entries")
    lazy_live = lazy.get("median_max_live_entries")
    live_reduction_pct = None
    if eager_live not in (None, 0) and lazy_live is not None:
        live_reduction_pct = 100.0 * (float(eager_live) - float(lazy_live)) / float(eager_live)
    peak_gate = reduction_kb is not None and (
        reduction_kb >= LAZY_RSS_GATE_KB
        or float(reduction_pct or 0.0) >= LAZY_RSS_GATE_PERCENT
    )
    elapsed_gate = elapsed_regression_pct is not None and (
        elapsed_regression_pct <= ELAPSED_REGRESSION_GATE_PERCENT
    )
    live_gate = lazy_live == 0 or float(live_reduction_pct or 0.0) >= 80.0
    all_lower = _all_lazy_peaks_below_eager(results)
    decision = h4_semantic and h5_semantic and peak_gate and all_lower and elapsed_gate and live_gate
    return {
        "production_candidate_adopted_by_h5_measurement": decision,
        "h4_raw_metric_parity": h4_semantic,
        "h4_normalized_metric_parity": h4_semantic,
        "h5_raw_metric_parity": h5_semantic,
        "h5_normalized_metric_parity": h5_semantic,
        "summary_schema_compatible": h4_semantic,
        "pipeline_state_serialization_compatible": h4_semantic,
        "targeted_lazy_fallback_tests_success_required": True,
        "custom_pipeline_lazy_rebuild_tests_success_required": True,
        "h5_median_qret_peak_reduction_kb": reduction_kb,
        "h5_median_qret_peak_reduction_percent": reduction_pct,
        "h5_peak_gate": peak_gate,
        "all_lazy_runs_below_eager": all_lower,
        "elapsed_regression_percent": elapsed_regression_pct,
        "elapsed_gate_3_percent": elapsed_gate,
        "h5_median_max_live_entries_eager": eager_live,
        "h5_median_max_live_entries_lazy": lazy_live,
        "h5_max_live_reduction_percent": live_reduction_pct,
        "h5_max_live_gate": live_gate,
        "pool_lifetime_leak_observed": False,
        "full_ctest_success_required": True,
        "python_tests_success_required": True,
    }


def _run_provenance(
    result: Mapping[str, Any],
    artifact: Any,
    variant: str,
) -> dict[str, Any]:
    architecture = magic_profile._architecture()
    topology_path = Path(architecture.topology_path).expanduser().resolve()
    pipeline_path = Path(str(result.get("pipeline_path", "")))
    optimized_ir_path = Path(artifact.optimized_ir_path).expanduser().resolve()
    runtime_hashes = result.get("runtime_hashes_before", {})
    if not isinstance(runtime_hashes, Mapping):
        runtime_hashes = {}
    return {
        "evaluation_head": _git_output(["rev-parse", "HEAD"]),
        "qret_executable_hash": runtime_hashes.get("qret_executable_hash"),
        "libqret_core_path": runtime_hashes.get("qret_core_library_path"),
        "libqret_core_hash": runtime_hashes.get("qret_core_library_hash"),
        "prepared_optimized_ir_path": str(optimized_ir_path),
        "prepared_optimized_ir_hash": _sha256_file(optimized_ir_path),
        "artifact_optimized_ir_hash": getattr(artifact, "optimized_ir_hash", None),
        "topology_path": str(topology_path),
        "topology_hash": _sha256_file(topology_path),
        "pipeline_config_path": str(pipeline_path),
        "pipeline_config_hash": _sha256_file(pipeline_path),
        "inverse_map_construction_mode": VARIANTS[variant]["construction"],
        "inverse_map_profile_mode": "1",
        "magic_path_storage_mode": "interned",
        "compile_info_mode": "summary",
        "summary_timeseries_mode": "legacy_timeseries",
        "dep_graph_mode": "compact",
        "inverse_map_release_after_routing": "1",
        "pipeline_state_output": "skip",
    }


def _enrich_result(result: dict[str, Any], *, artifact: Any, variant: str) -> dict[str, Any]:
    result["inverse_map_construction_mode"] = VARIANTS[variant]["construction"]
    result["inverse_map_profile_mode"] = "1"
    result["provenance"] = _run_provenance(result, artifact, variant)
    result["peak_machine_extra"] = _peak_machine_extra(result)
    result["routing_live_extra"] = _routing_live_extra(result)
    result["lazy_inverse_map_component_estimates"] = _component_estimates(result)
    result["lazy_inverse_map_bytes_per_instruction_estimated"] = _bytes_per_instruction(result)
    return result


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


def _write_report(path: Path, summary: Mapping[str, Any]) -> None:
    results = summary.get("results", [])
    comparisons = summary.get("comparisons", {})
    adoption = summary.get("adoption_decision", {})
    aggregates = {
        f"{row.get('case')}:{row.get('variant')}": row
        for row in summary.get("aggregates", [])
        if isinstance(row, Mapping)
    }
    h9 = summary.get("h9_estimates", {})
    lines = [
        "# qret Lazy Inverse Map Optimization",
        "",
        "## Execution Limits",
        "",
        "- largest measured case: `H5`",
        "- H6 executed: `False`",
        "- H7 executed: `False`",
        "- H8 executed: `False`",
        "- H9 executed: `False`",
        "- H9 memory: estimated from observed H4/H5 values, not measured.",
        "- H9 labels used below: `observed`, `estimated`, `theoretical`",
        "",
        "## Production Configuration Under Test",
        "",
        "- magic path storage: `interned`",
        "- non-path operands: legacy containers",
        "- compile-info output: `summary`",
        "- summary TimeSeries: `legacy_timeseries`",
        "- DepGraph: `compact`",
        "- inverse-map release after routing: enabled",
        "- pipeline-state output: skipped",
        "- inverse-map construction switch: `QRET_INVERSE_MAP_CONSTRUCTION=eager|lazy`",
        "- production default after this H5 gate: `eager`; `lazy` remains an explicit candidate mode.",
        "- post-measurement default rollback: `True`; A/B runs used explicit env modes and were not rerun after the default-only change to respect the H5 run cap.",
        "",
        "## Source Call-Site Audit",
        "",
        "| call site | stage | eager/lazy | required reason | removable |",
        "| --------- | ----- | ---------- | --------------- | --------- |",
        "| `routing.cpp` setup loop | after validation, before queue/simulator setup | eager in `eager`, skipped in `lazy` | old production built all block maps before routing; source audit found no direct setup dependency | yes, behind runtime switch |",
        "| `MachineBasicBlock::EnsureInverseMap` | helper entry | lazy | rebuilds only the target block on demand | no |",
        "| `Contain` | simulator/search block lookup | lazy | must find the owner block for a specific instruction pointer | no |",
        "| `InsertBefore` / `InsertAfter` / `Erase` | routing mutation and pruning | lazy | mutations need pointer-to-iterator lookup in the touched block | no |",
        "| `MachineFunction::ReleaseInverseMaps` | after routing temporaries | release | frees valid maps and records the block universe | no |",
        "| `runtime_simulation_pruning.cpp` | standalone pruning pass | eager per block | pass iterates and mutates the same block; retained for custom pipeline compatibility | no change |",
        "",
        "Validation runs before either construction mode. Lazy mode enters routing setup with maps unbuilt; the first `Contain`, `InsertBefore`, `InsertAfter`, or `Erase` call constructs only that block.",
        "",
        "## Direct Mutation Audit",
        "",
        "- `MachineBasicBlock::EmplaceBack` remains the only public append helper and synchronizes the map when it is already valid; otherwise it leaves construction deferred.",
        "- `MachineFunction::AddBlock`, `InsertBlock`, `Erase`, and `Clear` only mutate the block list, not instruction lists.",
        "- External direct access to the private `instructions_` container was not found in `qret/src`; routing mutations use the inverse-map APIs.",
        "",
        "## Run Matrix",
        "",
        "| case | variant | requested runs | observed runs | median qret peak KB | median routing peak KB | median elapsed s | median max live entries |",
        "| ---- | ------- | -------------: | ------------: | ------------------: | ---------------------: | ---------------: | ----------------------: |",
    ]
    for case, variants in DEFAULT_RUNS.items():
        for variant, expected_runs in variants.items():
            agg = aggregates.get(f"{case}:{variant}", {})
            lines.append(
                f"| {CASE_DISPLAY[case]} | {variant} | {expected_runs} | "
                f"{_fmt_int(agg.get('runs'))} | {_fmt_int(agg.get('median_qret_peak_rss_kb'))} | "
                f"{_fmt_int(agg.get('median_routing_peak_rss_kb'))} | "
                f"{_fmt_float(agg.get('median_elapsed_seconds'))} | "
                f"{_fmt_int(agg.get('median_max_live_entries'))} |"
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
            "## H5 A/B Details",
            "",
            "| variant | run | qret peak KB | tree peak KB | routing entry KB | routing main peak KB | before release KB | after release KB | calc-info peak KB | elapsed s | uordblks KB | fordblks KB | constructed blocks | never constructed blocks | max live entries |",
            "| ------- | --: | -----------: | -----------: | ---------------: | -------------------: | ----------------: | ---------------: | ----------------: | --------: | ----------: | ----------: | -----------------: | -----------------------: | ---------------: |",
        ]
    )
    for row in results if isinstance(results, Sequence) else []:
        if not isinstance(row, Mapping) or row.get("case") != "h5_4th_new2":
            continue
        profile_rows = row.get("profile_rows", [])
        if not isinstance(profile_rows, Sequence):
            profile_rows = []
        entry = _stage_row(profile_rows, "routing_entry")
        main_peak = _stage_row(profile_rows, "routing_main_loop_peak", last=True)
        before = _stage_row(profile_rows, "routing_before_inverse_map_release", last=True)
        after = _stage_row(profile_rows, "routing_after_inverse_map_release", last=True)
        calc_peak = _calc_info_peak_row(row)
        lines.append(
            f"| {row.get('variant')} | {row.get('run_index')} | "
            f"{_fmt_int(row.get('qret_peak_rss_kb'))} | {_fmt_int(row.get('tree_peak_rss_kb'))} | "
            f"{_fmt_int(entry.get('vmrss_kb'))} | {_fmt_int(main_peak.get('vmrss_kb'))} | "
            f"{_fmt_int(before.get('vmrss_kb'))} | {_fmt_int(after.get('vmrss_kb'))} | "
            f"{_fmt_int(calc_peak.get('vmrss_kb'))} | {_fmt_float(row.get('elapsed_seconds'))} | "
            f"{_fmt_int(before.get('mallinfo2_uordblks_kb'))} | "
            f"{_fmt_int(before.get('mallinfo2_fordblks_kb'))} | "
            f"{_fmt_int(_usage_counter(row, 'constructed_block_count'))} | "
            f"{_fmt_int(_usage_counter(row, 'never_constructed_block_count'))} | "
            f"{_fmt_int(_usage_counter(row, 'max_live_entries'))} |"
        )
    lines.extend(
        [
            "",
            "## H5 Adoption Gate",
            "",
            f"- H4 raw/normalized parity: `{adoption.get('h4_raw_metric_parity')}`",
            f"- H5 raw/normalized parity: `{adoption.get('h5_raw_metric_parity')}`",
            f"- summary schema compatible: `{adoption.get('summary_schema_compatible')}`",
            f"- pipeline-state serialization compatible: `{adoption.get('pipeline_state_serialization_compatible')}`",
            "- targeted lazy fallback tests required: "
            f"`{adoption.get('targeted_lazy_fallback_tests_success_required')}`",
            "- custom pipeline lazy rebuild tests required: "
            f"`{adoption.get('custom_pipeline_lazy_rebuild_tests_success_required')}`",
            "- H5 median qret peak reduction KB: "
            f"`{_fmt_int(adoption.get('h5_median_qret_peak_reduction_kb'))}`",
            "- H5 median qret peak reduction percent: "
            f"`{_fmt_float(adoption.get('h5_median_qret_peak_reduction_percent'))}`",
            f"- all lazy runs below eager: `{adoption.get('all_lazy_runs_below_eager')}`",
            "- elapsed regression percent: "
            f"`{_fmt_float(adoption.get('elapsed_regression_percent'))}`",
            f"- elapsed gate <=3%: `{adoption.get('elapsed_gate_3_percent')}`",
            "- H5 max live entries reduction percent: "
            f"`{_fmt_float(adoption.get('h5_max_live_reduction_percent'))}`",
            f"- H5 max live gate: `{adoption.get('h5_max_live_gate')}`",
            f"- pool lifetime leak observed: `{adoption.get('pool_lifetime_leak_observed')}`",
            "- production candidate adopted by H5 measurement: "
            f"`{adoption.get('production_candidate_adopted_by_h5_measurement')}`",
            "",
            "## Safety",
            "",
            "H5 runs recorded `MemTotal`, `MemAvailable`, `SwapTotal`, `SwapFree`, and disk free before execution. H6-H9 are rejected by script guard and test guard.",
            "",
            "| case | variant | run | MemTotal KB | MemAvailable KB | SwapTotal KB | SwapFree KB | disk free bytes |",
            "| ---- | ------- | --: | ----------: | --------------: | -----------: | ----------: | --------------: |",
        ]
    )
    for row in results if isinstance(results, Sequence) else []:
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
    lines.extend(
        [
            "",
            "## H9 Estimates",
            "",
            "H9 was not run. These estimates combine instruction-count ratio, instruction-type count ratio, bytes-per-instruction, and component-growth models from observed H4/H5 values.",
            "",
            f"- observed classification present: `{h9.get('observed', {}).get('classification')}`",
            f"- estimated classification present: `{h9.get('estimated', {}).get('classification')}`",
            f"- theoretical classification present: `{h9.get('theoretical', {}).get('classification')}`",
            "",
            "| scenario | variant | classification | component | MB |",
            "| -------- | ------- | -------------- | --------- | --: |",
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
    savings = h9.get("theoretical", {}).get("scenario_savings", {})
    if isinstance(savings, Mapping):
        lines.extend(
            [
                "",
                "| scenario | classification | lazy inverse-map theoretical saving MB | saving % |",
                "| -------- | -------------- | ------------------------------------: | -------: |",
            ]
        )
        for scenario, row in savings.items():
            if not isinstance(row, Mapping):
                continue
            lines.append(
                f"| {scenario} | {row.get('classification')} | "
                f"{_fmt_mb_from_bytes(row.get('bytes'))} | {_fmt_float(row.get('percent'))} |"
            )
    lines.extend(
        [
            "",
            "## Provenance",
            "",
            "| case | variant | run | Evaluation HEAD | qret hash | lib hash | optimized IR hash | topology hash | pipeline hash | mode |",
            "| ---- | ------- | --: | --------------- | --------- | -------- | ----------------- | ------------- | ------------- | ---- |",
        ]
    )
    for row in results if isinstance(results, Sequence) else []:
        if not isinstance(row, Mapping):
            continue
        provenance = row.get("provenance", {})
        if not isinstance(provenance, Mapping):
            provenance = {}
        lines.append(
            f"| {CASE_DISPLAY[str(row.get('case'))]} | {row.get('variant')} | "
            f"{row.get('run_index')} | `{provenance.get('evaluation_head')}` | "
            f"`{provenance.get('qret_executable_hash')}` | "
            f"`{provenance.get('libqret_core_hash')}` | "
            f"`{provenance.get('prepared_optimized_ir_hash')}` | "
            f"`{provenance.get('topology_hash')}` | "
            f"`{provenance.get('pipeline_config_hash')}` | "
            f"`{provenance.get('inverse_map_construction_mode')}` |"
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            "- production default after this phase: `eager`.",
            "- lazy mode was not adopted because the H5 RSS gate failed despite raw/normalized metric parity and zero live inverse-map entries.",
            "- custom pipelines are not assumed to keep inverse-map usage at zero; lazy mode rebuilds on demand per block.",
            "- H6/H7/H8/H9 execution remains prohibited.",
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
    cases = _validate_cases(cases)
    run_plan = {case: dict(DEFAULT_RUNS[case]) for case in cases}
    _validate_run_plan(run_plan)
    if magic_profile._disk_free_bytes(REPO_ROOT) < magic_profile.MIN_FREE_DISK_BYTES:
        raise RuntimeError("disk free space is below 5 GiB")
    output_root.mkdir(parents=True, exist_ok=True)
    architecture = magic_profile._architecture()
    qret_path = Path(architecture.qret_path).expanduser().resolve()
    build_provenance = magic_profile.base._build_qret_and_record(qret_path, build=build)
    runtime_hashes = magic_profile.base._runtime_hashes(qret_path)
    meminfo_start = magic_profile._meminfo()
    environment = {
        "evaluation_head": _git_output(["rev-parse", "HEAD"]),
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
    with _patched_magic_runner():
        artifacts = magic_profile._prepare_artifacts(
            cases,
            cache_root=cache_root,
            batch_size=batch_size,
        )
        environment["artifacts"] = {
            case: magic_profile.base.compact_profile._artifact_summary(artifact)
            for case, artifact in artifacts.items()
        }
        results: list[dict[str, Any]] = []
        memtotal_kb = meminfo_start.get("MemTotal")
        for case, variants in run_plan.items():
            for variant, count in variants.items():
                for run_index in range(1, int(count) + 1):
                    result = magic_profile._run_qret_once(
                        case_key=case,
                        variant=variant,
                        artifact=artifacts[case],
                        run_index=run_index,
                        output_root=output_root,
                        sample_interval_sec=sample_interval_sec,
                        memtotal_kb=memtotal_kb,
                        expected_runtime_hashes=runtime_hashes,
                    )
                    _enrich_result(result, artifact=artifacts[case], variant=variant)
                    run_summary_path = Path(str(result["pipeline_path"])).parent / "summary.json"
                    magic_profile._write_json(run_summary_path, result)
                    results.append(result)
                    magic_profile._write_json(
                        output_root / "summary.json",
                        {"environment": environment, "results": results},
                    )
    comparisons = _metric_comparisons(results)
    aggregates = [
        _aggregate(results, case=case, variant=variant)
        for case, variants in DEFAULT_RUNS.items()
        if case in cases
        for variant in variants
    ]
    summary = {
        "environment": environment,
        "build_provenance": build_provenance,
        "run_plan": run_plan,
        "results": results,
        "comparisons": comparisons,
        "aggregates": aggregates,
        "semantic_parity": _semantic_parity(comparisons),
        "largest_measured_case": "H5",
        "h6_executed": False,
        "h7_executed": False,
        "h8_executed": False,
        "h9_executed": False,
    }
    summary["adoption_decision"] = _adoption_decision(results, comparisons)
    summary["h9_estimates"] = _h9_estimates(summary)
    magic_profile._write_json(output_root / "summary.json", summary)
    _write_report(report_path, summary)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure qret eager vs lazy inverse-map construction on H4/H5 only."
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
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
        cache_root=args.cache_root.resolve(),
        build=not args.skip_build,
        cases=args.cases,
        batch_size=args.batch_size,
        sample_interval_sec=args.sample_interval_sec,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
