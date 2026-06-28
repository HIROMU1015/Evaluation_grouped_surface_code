#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import json
import platform
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import profile_qret_magic_path_interning as magic_profile  # noqa: E402


DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "qret_inverse_map_design"
DEFAULT_REPORT_PATH = REPO_ROOT / "docs" / "benchmarks" / "qret_inverse_map_compact_design.md"
CASE_CHAIN_LENGTH = {
    "h4_4th_new2": 4,
    "h5_4th_new2": 5,
}
CASE_DISPLAY = {
    "h4_4th_new2": "H4 `4th(new_2)`",
    "h5_4th_new2": "H5 `4th(new_2)`",
}
PROHIBITED_CASE_PREFIXES = ("h6", "h7", "h8", "h9")
VARIANTS = {
    "profile_off": {
        "profile": "0",
        "storage": "interned",
        "description": "current production, inverse-map usage profile off",
    },
    "profile_on": {
        "profile": "1",
        "storage": "interned",
        "description": "current production, inverse-map usage profile on",
    },
}
DEFAULT_RUNS = {
    "h4_4th_new2": {"profile_off": 1, "profile_on": 1},
    "h5_4th_new2": {"profile_on": 1},
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


def _git_output(args: Sequence[str], *, cwd: Path = REPO_ROOT) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def _validate_profile_value(value: str) -> str:
    if value not in {"0", "1"}:
        raise ValueError("QRET_PROFILE_INVERSE_MAP_USAGE must be 0 or 1")
    return value


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
    return tuple(cases)


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
    env["QRET_MAGIC_PATH_STORAGE"] = "interned"
    env["QRET_SUMMARY_TIME_SERIES_IMPL"] = "legacy_timeseries"
    env["QRET_DEP_GRAPH_IMPL"] = "compact"
    env["QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING"] = "1"
    env["QRET_RSS_DIAGNOSTIC_TRIM_STAGE"] = "none"
    env["QRET_PROFILE_MAGIC_PATHS"] = "0"
    env["QRET_PROFILE_INVERSE_MAP_USAGE"] = _validate_profile_value(VARIANTS[variant]["profile"])
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


def _stage_row(rows: Sequence[Mapping[str, Any]], stage: str, *, last: bool = False) -> Mapping[str, Any]:
    iterable = reversed(rows) if last else rows
    for row in iterable:
        if row.get("stage") == stage:
            return row
    return {}


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


def _max_stage_row(rows: Sequence[Mapping[str, Any]], prefix: str | None = None) -> Mapping[str, Any]:
    candidates = [
        row
        for row in rows
        if row.get("vmrss_kb") is not None
        and (prefix is None or str(row.get("stage", "")).startswith(prefix))
    ]
    if not candidates:
        return {}
    return max(candidates, key=lambda row: int(row.get("vmrss_kb") or 0))


def _has_inverse_usage_fields(result: Mapping[str, Any]) -> bool:
    for row in result.get("profile_rows", []):
        extra = row.get("extra")
        if not isinstance(extra, Mapping):
            continue
        for key in extra:
            if str(key).startswith("inverse_map_usage_") or str(key).startswith(
                "machine_instruction_projected_stable_id"
            ) or "stable_id_object_delta" in str(key):
                return True
    return False


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


def _component_estimates(
    result: Mapping[str, Any],
    *,
    inverse_map_bytes: int | None = None,
    stable_id_delta_bytes: int = 0,
) -> dict[str, dict[str, Any]]:
    machine = _peak_machine_extra(result)
    routing = _routing_live_extra(result)
    path_bytes = int(machine.get("machine_ancilla_path_coordinate_list_node_bytes_estimated") or 0)
    operand_bytes = int(machine.get("machine_operand_list_node_bytes_estimated") or 0)
    inverse_bytes = (
        int(machine.get("machine_inverse_map_bytes_estimated") or 0)
        if inverse_map_bytes is None
        else int(inverse_map_bytes)
    )
    return {
        "instruction_object": {
            "classification": "estimated",
            "bytes": int(machine.get("machine_instruction_object_bytes_estimated") or 0)
            + stable_id_delta_bytes,
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
        "inverse_map": {"classification": "estimated", "bytes": inverse_bytes},
        "metadata": {
            "classification": "estimated",
            "bytes": int(machine.get("machine_metadata_bytes_estimated") or 0),
            "note": "metadata is stored inside instruction objects",
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


def _machine_type_counts(result: Mapping[str, Any]) -> dict[str, int]:
    counts = _peak_machine_extra(result).get("machine_instruction_type_count", {})
    if not isinstance(counts, Mapping):
        return {}
    return {str(key): int(value or 0) for key, value in counts.items()}


def _bytes_per_instruction(result: Mapping[str, Any], components: Mapping[str, Mapping[str, Any]]) -> float:
    instructions = int(_peak_machine_extra(result).get("machine_instructions") or 0)
    if instructions <= 0:
        return 0.0
    total = sum(int(item.get("bytes") or 0) for item in components.values())
    return float(total) / float(instructions)


def _candidate_models(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    machine = _peak_machine_extra(result)
    usage = _usage_extra(result)
    entries = int(machine.get("machine_inverse_map_entries") or usage.get("inverse_map_usage_max_live_entries") or 0)
    current_bytes = int(machine.get("machine_inverse_map_bytes_estimated") or 0)
    iterator_size = int(
        usage.get(
            "inverse_map_usage_vector_const_iterator_size_bytes",
            machine.get("machine_inverse_map_mapped_iterator_size_bytes", 8),
        )
        or 8
    )
    pointer_size = int(usage.get("inverse_map_usage_pointer_size_bytes") or 8)
    stable_delta = int(machine.get("machine_instruction_projected_stable_id_object_delta_bytes_estimated") or 0)
    insert_count = int(usage.get("inverse_map_usage_insert_before_count") or 0) + int(
        usage.get("inverse_map_usage_insert_after_count") or 0
    )
    erase_count = int(usage.get("inverse_map_usage_erase_count") or 0)
    contain_count = int(usage.get("inverse_map_usage_contain_count") or 0)
    touched_upper = min(entries, contain_count + insert_count + erase_count)
    models = [
        {
            "candidate": "current_std_map",
            "classification": "observed",
            "bytes": current_bytes,
            "saving_bytes": 0,
            "notes": "current std::map<const MachineInstruction*, ConstIterator>",
        },
        {
            "candidate": "stable_instruction_id_vector",
            "classification": "theoretical",
            "bytes": entries * iterator_size + stable_delta,
            "saving_bytes": max(0, current_bytes - (entries * iterator_size + stable_delta)),
            "notes": "requires a stable 32-bit instruction ID or equivalent side metadata",
        },
        {
            "candidate": "block_local_slot_vector_tombstone",
            "classification": "theoretical",
            "bytes": entries * (iterator_size + 1) + erase_count * 4 + stable_delta,
            "saving_bytes": max(
                0,
                current_bytes - (entries * (iterator_size + 1) + erase_count * 4 + stable_delta),
            ),
            "notes": "requires block-local slot ownership and tombstone/free-list policy",
        },
        {
            "candidate": "unordered_map_pointer_iterator",
            "classification": "theoretical",
            "bytes": entries * (pointer_size + iterator_size + pointer_size + 16)
            + int(entries / 0.8 + 1) * pointer_size,
            "saving_bytes": max(
                0,
                current_bytes
                - (
                    entries * (pointer_size + iterator_size + pointer_size + 16)
                    + int(entries / 0.8 + 1) * pointer_size
                ),
            ),
            "notes": "lower code risk, but allocator and bucket overhead keep savings modest",
        },
        {
            "candidate": "sorted_flat_pointer_iterator",
            "classification": "theoretical",
            "bytes": entries * (pointer_size + iterator_size),
            "saving_bytes": max(0, current_bytes - entries * (pointer_size + iterator_size)),
            "notes": "compact, but Insert/Erase are O(N) unless updates are batched",
        },
        {
            "candidate": "partial_lazy_inverse_map_lower_bound",
            "classification": "theoretical",
            "bytes": touched_upper * int(machine.get("machine_inverse_map_node_bytes_estimated") or 40),
            "saving_bytes": max(
                0,
                current_bytes
                - touched_upper * int(machine.get("machine_inverse_map_node_bytes_estimated") or 40),
            ),
            "notes": "lower-bound estimate; exact unique touched pointers are not observed",
        },
    ]
    return models


def _best_theoretical_candidate(result: Mapping[str, Any]) -> Mapping[str, Any]:
    models = _candidate_models(result)
    partial = next(
        (row for row in models if row["candidate"] == "partial_lazy_inverse_map_lower_bound"),
        {},
    )
    usage = _usage_extra(result)
    operations = sum(
        int(usage.get(key) or 0)
        for key in (
            "inverse_map_usage_contain_count",
            "inverse_map_usage_insert_before_count",
            "inverse_map_usage_insert_after_count",
            "inverse_map_usage_erase_count",
        )
    )
    if partial and operations == 0:
        return partial
    candidates = [
        row
        for row in models
        if row["candidate"] not in {"current_std_map", "partial_lazy_inverse_map_lower_bound"}
    ]
    return max(candidates, key=lambda row: int(row.get("saving_bytes") or 0), default={})


def _candidate_component_split(result: Mapping[str, Any], candidate: Mapping[str, Any]) -> tuple[int, int]:
    stable_delta = int(
        _peak_machine_extra(result).get(
            "machine_instruction_projected_stable_id_object_delta_bytes_estimated",
            0,
        )
        or 0
    )
    total_bytes = int(candidate.get("bytes") or 0)
    if candidate.get("candidate") in {
        "stable_instruction_id_vector",
        "block_local_slot_vector_tombstone",
    }:
        return max(0, total_bytes - stable_delta), stable_delta
    return total_bytes, 0


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


def _component_growth_factor(
    h4_components: Mapping[str, Mapping[str, Any]],
    h5_components: Mapping[str, Mapping[str, Any]],
    component: str,
) -> float:
    return _growth_ratio(
        int(h4_components.get(component, {}).get("bytes") or 0),
        int(h5_components.get(component, {}).get("bytes") or 0),
    )


def _estimate_h9_component(
    *,
    h4: Mapping[str, Any],
    h5: Mapping[str, Any],
    h4_components: Mapping[str, Mapping[str, Any]],
    h5_components: Mapping[str, Mapping[str, Any]],
    component: str,
    scenario: str,
) -> int:
    h4_inst = int(_peak_machine_extra(h4).get("machine_instructions") or 0)
    h5_inst = int(_peak_machine_extra(h5).get("machine_instructions") or 0)
    h5_component = int(h5_components.get(component, {}).get("bytes") or 0)
    inst_ratio = _growth_ratio(h4_inst, h5_inst)
    type_ratio = _type_count_growth_factor(h4, h5)
    h4_bpi = _bytes_per_instruction(h4, h4_components)
    h5_bpi = _bytes_per_instruction(h5, h5_components)
    bpi_ratio = _growth_ratio(int(h4_bpi * max(h4_inst, 1)), int(h5_bpi * max(h5_inst, 1)))
    component_ratio = _component_growth_factor(h4_components, h5_components, component)
    values = [
        h5_component * (inst_ratio**4),
        h5_component * (type_ratio**4),
        h5_component * (bpi_ratio**4),
        h5_component * (component_ratio**4),
    ]
    values.sort()
    if scenario == "conservative":
        selected = values[1] if len(values) > 1 else values[0]
        return int(selected * 0.85)
    if scenario == "central":
        return int(statistics.median(values))
    return int(values[-1] * 1.25)


def _h9_estimates(summary: Mapping[str, Any]) -> dict[str, Any]:
    results = summary.get("results", [])
    if not isinstance(results, Sequence):
        return {}
    h4 = _first_result(results, "h4_4th_new2", "profile_on")
    h5 = _first_result(results, "h5_4th_new2", "profile_on")
    if not h4 or not h5:
        return {}
    h4_current = _component_estimates(h4)
    h5_current = _component_estimates(h5)
    h4_best = _best_theoretical_candidate(h4)
    h5_best = _best_theoretical_candidate(h5)
    h4_inverse_bytes, h4_stable_delta = _candidate_component_split(h4, h4_best)
    h5_inverse_bytes, h5_stable_delta = _candidate_component_split(h5, h5_best)
    h4_candidate = _component_estimates(
        h4,
        inverse_map_bytes=h4_inverse_bytes
        if h4_best
        else int(h4_current["inverse_map"]["bytes"]),
        stable_id_delta_bytes=h4_stable_delta,
    )
    h5_candidate = _component_estimates(
        h5,
        inverse_map_bytes=h5_inverse_bytes
        if h5_best
        else int(h5_current["inverse_map"]["bytes"]),
        stable_id_delta_bytes=h5_stable_delta,
    )
    observed = {
        "classification": "observed",
        "largest_measured_case": "H5",
        "h4_qret_peak_rss_kb": h4.get("qret_peak_rss_kb"),
        "h5_qret_peak_rss_kb": h5.get("qret_peak_rss_kb"),
        "h4_components": h4_current,
        "h5_components": h5_current,
    }
    estimated: dict[str, Any] = {"classification": "estimated", "scenarios": {}}
    changed_components = {"inverse_map"}
    if h5_best.get("candidate") in {
        "stable_instruction_id_vector",
        "block_local_slot_vector_tombstone",
    }:
        changed_components.add("instruction_object")
    for scenario in ("conservative", "central", "upper"):
        scenario_payload: dict[str, Any] = {}
        for label, h4_components, h5_components in (
            ("current_production", h4_current, h5_current),
            ("with_compact_inverse_map_candidate", h4_candidate, h5_candidate),
        ):
            components = {
                component: _estimate_h9_component(
                    h4=h4,
                    h5=h5,
                    h4_components=h4_components,
                    h5_components=h5_components,
                    component=component,
                    scenario=scenario,
                )
                for component in COMPONENT_KEYS
            }
            scenario_payload[label] = {
                "classification": "estimated",
                "components": components,
                "total_bytes": sum(components.values()),
            }
        current_components = scenario_payload["current_production"]["components"]
        candidate_components = scenario_payload["with_compact_inverse_map_candidate"]["components"]
        for component in COMPONENT_KEYS:
            if component not in changed_components:
                candidate_components[component] = current_components[component]
        scenario_payload["with_compact_inverse_map_candidate"]["total_bytes"] = sum(
            candidate_components.values()
        )
        estimated["scenarios"][scenario] = scenario_payload
    theoretical = {
        "classification": "theoretical",
        "selected_compact_candidate": h5_best.get("candidate"),
        "h5_candidate_saving_bytes": h5_best.get("saving_bytes"),
        "scenario_savings": {},
    }
    for scenario, payload in estimated["scenarios"].items():
        current_total = int(payload["current_production"]["total_bytes"])
        candidate_total = int(payload["with_compact_inverse_map_candidate"]["total_bytes"])
        theoretical["scenario_savings"][scenario] = {
            "classification": "theoretical",
            "bytes": max(0, current_total - candidate_total),
            "percent": 0.0
            if current_total <= 0
            else 100.0 * (current_total - candidate_total) / current_total,
        }
    return {"observed": observed, "estimated": estimated, "theoretical": theoretical}


def _first_result(
    results: Sequence[Mapping[str, Any]],
    case: str,
    variant: str,
) -> Mapping[str, Any]:
    return next((row for row in results if row.get("case") == case and row.get("variant") == variant), {})


def _metric_comparisons(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    h4_off = _first_result(results, "h4_4th_new2", "profile_off")
    h4_on = _first_result(results, "h4_4th_new2", "profile_on")
    if not h4_off or not h4_on:
        return {}
    return {"h4_profile_off_vs_on": magic_profile._compare_metrics(h4_off, h4_on)}


def _semantic_parity(comparisons: Mapping[str, Any]) -> bool:
    return bool(comparisons) and all(
        row.get("raw", {}).get("all_equal") and row.get("normalized", {}).get("all_equal")
        for row in comparisons.values()
    )


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


def _usage_counter_value(extra: Mapping[str, Any], key: str) -> Any:
    if key == "inverse_map_usage_initial_inserted_entries":
        blocks = extra.get("inverse_map_usage_construct_block_entries")
        if isinstance(blocks, Sequence) and not isinstance(blocks, (str, bytes)):
            try:
                return sum(int(item or 0) for item in blocks)
            except (TypeError, ValueError):
                pass
    return extra.get(key)


def _type_stable_id_rows(result: Mapping[str, Any], limit: int = 12) -> list[dict[str, Any]]:
    extra = _peak_machine_extra(result)
    counts = extra.get("machine_instruction_type_count", {})
    object_bytes = extra.get("machine_instruction_type_object_bytes_estimated", {})
    projected = extra.get("machine_instruction_type_projected_stable_id_object_bytes_estimated", {})
    delta = extra.get("machine_instruction_type_stable_id_object_delta_bytes_estimated", {})
    if not all(isinstance(item, Mapping) for item in (counts, object_bytes, projected, delta)):
        return []
    rows = [
        {
            "type": str(inst_type),
            "count": int(count or 0),
            "object_bytes": int(object_bytes.get(inst_type, 0) or 0),
            "projected_bytes": int(projected.get(inst_type, 0) or 0),
            "delta_bytes": int(delta.get(inst_type, 0) or 0),
        }
        for inst_type, count in counts.items()
    ]
    return sorted(rows, key=lambda row: row["delta_bytes"], reverse=True)[:limit]


def _write_report(path: Path, summary: Mapping[str, Any]) -> None:
    results = summary.get("results", [])
    comparisons = summary.get("comparisons", {})
    h4_off = _first_result(results, "h4_4th_new2", "profile_off")
    h4_on = _first_result(results, "h4_4th_new2", "profile_on")
    h5_on = _first_result(results, "h5_4th_new2", "profile_on")
    h5_rows = h5_on.get("profile_rows", []) if isinstance(h5_on, Mapping) else []
    h5_before_release = _stage_row(h5_rows, "routing_before_inverse_map_release", last=True)
    h5_after_release = _stage_row(h5_rows, "routing_after_inverse_map_release", last=True)
    h5_peak = _max_stage_row(h5_rows, prefix="routing_")
    h5_machine = _peak_machine_extra(h5_on)
    h5_usage = _usage_extra(h5_on)
    h5_safety = h5_on.get("safety_snapshot_before_h5", {})
    if not isinstance(h5_safety, Mapping):
        h5_safety = {}
    h9 = summary.get("h9_estimates", {})
    lines = [
        "# qret Compact Inverse Map Design Audit",
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
        "- non-path operands: legacy list containers",
        "- compile-info output: `summary`",
        "- summary TimeSeries: `legacy_timeseries`",
        "- DepGraph: `compact`",
        "- inverse-map release after routing: enabled",
        "- pipeline-state output skip: enabled through the Evaluation architecture",
        "",
        "## H4 Correctness And Schema",
        "",
        f"- profile-off return code: `{h4_off.get('returncode')}`",
        f"- profile-on return code: `{h4_on.get('returncode')}`",
        f"- raw/normalized metric parity: `{_semantic_parity(comparisons)}`",
        f"- profile-off has inverse-map usage fields: `{_has_inverse_usage_fields(h4_off)}`",
        f"- profile-on has inverse-map usage fields: `{_has_inverse_usage_fields(h4_on)}`",
        "",
        "| comparison | raw equal | normalized equal | raw mismatches | normalized mismatches |",
        "| ---------- | --------: | ---------------: | -------------- | --------------------- |",
    ]
    for key, row in comparisons.items():
        lines.append(
            f"| {key} | {row.get('raw', {}).get('all_equal')} | "
            f"{row.get('normalized', {}).get('all_equal')} | "
            f"{row.get('raw', {}).get('mismatches')} | "
            f"{row.get('normalized', {}).get('mismatches')} |"
        )
    lines.extend(
        [
            "",
            "## H5 Observed Profile",
            "",
            f"- qret peak RSS KB: `{_fmt_int(h5_on.get('qret_peak_rss_kb'))}`",
            f"- process tree peak KB: `{_fmt_int(h5_on.get('tree_peak_rss_kb'))}`",
            f"- elapsed seconds: `{_fmt_float(h5_on.get('elapsed_seconds'))}`",
            f"- routing peak stage: `{h5_peak.get('stage')}`",
            f"- routing peak RSS KB: `{_fmt_int(h5_peak.get('vmrss_kb'))}`",
            f"- routing before inverse-map release RSS KB: `{_fmt_int(h5_before_release.get('vmrss_kb'))}`",
            f"- routing after inverse-map release RSS KB: `{_fmt_int(h5_after_release.get('vmrss_kb'))}`",
            f"- qret inverse map entries: `{_fmt_int(h5_machine.get('machine_inverse_map_entries'))}`",
            f"- qret inverse map estimated MB: `{_fmt_mb_from_bytes(h5_machine.get('machine_inverse_map_bytes_estimated'))}`",
            f"- allocator uordblks at before-release KB: `{_fmt_int(h5_before_release.get('mallinfo2_uordblks_kb'))}`",
            f"- allocator fordblks at before-release KB: `{_fmt_int(h5_before_release.get('mallinfo2_fordblks_kb'))}`",
            "",
            "## H5 Safety Snapshot",
            "",
            f"- MemTotal KB: `{_fmt_int(h5_safety.get('MemTotal'))}`",
            f"- MemAvailable KB: `{_fmt_int(h5_safety.get('MemAvailable'))}`",
            f"- SwapTotal KB: `{_fmt_int(h5_safety.get('SwapTotal'))}`",
            f"- SwapFree KB: `{_fmt_int(h5_safety.get('SwapFree'))}`",
            f"- disk free bytes: `{_fmt_int(h5_safety.get('disk_free_bytes'))}`",
            "- script guard rejects H6/H7/H8/H9 case names before qret execution.",
            "",
            "## Usage Counters",
            "",
            "| counter | value |",
            "| ------- | ----: |",
        ]
    )
    for key in (
        "inverse_map_usage_construct_inverse_map_count",
        "inverse_map_usage_initial_inserted_entries",
        "inverse_map_usage_full_rebuild_count",
        "inverse_map_usage_lazy_rebuild_count",
        "inverse_map_usage_contain_count",
        "inverse_map_usage_contain_hit_count",
        "inverse_map_usage_contain_miss_count",
        "inverse_map_usage_insert_before_count",
        "inverse_map_usage_insert_after_count",
        "inverse_map_usage_erase_count",
        "inverse_map_usage_release_count",
        "inverse_map_usage_max_live_entries",
        "inverse_map_usage_final_entries_before_release_total",
    ):
        lines.append(f"| `{key}` | {_fmt_int(_usage_counter_value(h5_usage, key))} |")
    lines.extend(
        [
            "",
            "## Compact Candidate Model",
            "",
            "| candidate | classification | estimated MB | theoretical saving MB | note |",
            "| --------- | -------------- | -----------: | --------------------: | ---- |",
        ]
    )
    for row in _candidate_models(h5_on):
        lines.append(
            f"| `{row['candidate']}` | {row['classification']} | "
            f"{_fmt_mb_from_bytes(row.get('bytes'))} | "
            f"{_fmt_mb_from_bytes(row.get('saving_bytes'))} | {row.get('notes')} |"
        )
    lines.extend(
        [
            "",
            "## Stable ID Layout Projection",
            "",
            "The stable-ID option is not implemented here. The table is a layout projection: observed object bytes plus a 32-bit ID rounded to each instruction type's alignment.",
            "",
            "| instruction type | count | current object MB | projected object MB | delta MB |",
            "| ---------------- | ----: | ----------------: | ------------------: | -------: |",
        ]
    )
    for row in _type_stable_id_rows(h5_on):
        lines.append(
            f"| `{row['type']}` | {_fmt_int(row['count'])} | "
            f"{_fmt_mb_from_bytes(row['object_bytes'])} | "
            f"{_fmt_mb_from_bytes(row['projected_bytes'])} | "
            f"{_fmt_mb_from_bytes(row['delta_bytes'])} |"
        )
    lines.extend(
        [
            "",
            "## Lifetime And Stability Audit",
            "",
            "- owner: each `MachineBasicBlock` owns one inverse map for its instruction list.",
            "- construction: routing constructs maps for all blocks immediately after validation.",
            "- last normal use: routing main loop mutations and block lookup helpers; compile-info and serialization use linear iteration and do not require the inverse map.",
            "- release: `MachineFunction::ReleaseInverseMaps()` clears all maps after routing temporaries are destroyed.",
            "- lazy rebuild: `Contain`, `InsertBefore`, `InsertAfter`, and `Erase` call `EnsureInverseMap()`, so custom passes after release can rebuild on demand.",
            "- iterator stability: `std::list` insert preserves existing iterators; erase invalidates only the erased iterator and the map erases that pointer.",
            "- pointer stability: instructions are separately allocated behind `unique_ptr`; list node movement does not move instruction objects.",
            "- multi-compile safety: profile counters are process-local and reset by qret process lifetime; production data remains per `MachineBasicBlock`.",
            "",
            "## H9 Estimates",
            "",
            "H9 was not run. These estimates combine instruction-count ratio, instruction-type ratio, bytes-per-instruction, and component-growth models from observed H4/H5 values.",
            "",
            f"- observed classification present: `{h9.get('observed', {}).get('classification')}`",
            f"- estimated classification present: `{h9.get('estimated', {}).get('classification')}`",
            f"- theoretical classification present: `{h9.get('theoretical', {}).get('classification')}`",
            f"- selected compact candidate: `{h9.get('theoretical', {}).get('selected_compact_candidate')}`",
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
    lines.extend(
        [
            "",
            "## Decision",
            "",
            "- production inverse-map implementation changed in this task: `False`",
            "- H5 adoption decision for compact inverse map: `defer`; this phase produced read-only measurements and design estimates only.",
            f"- next production candidate: `{h9.get('theoretical', {}).get('selected_compact_candidate')}`.",
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
                    results.append(result)
                    magic_profile._write_json(
                        output_root / "summary.json",
                        {"environment": environment, "results": results},
                    )
    comparisons = _metric_comparisons(results)
    summary = {
        "environment": environment,
        "build_provenance": build_provenance,
        "run_plan": run_plan,
        "results": results,
        "comparisons": comparisons,
        "semantic_parity": _semantic_parity(comparisons),
        "largest_measured_case": "H5",
        "h6_executed": False,
        "h7_executed": False,
        "h8_executed": False,
        "h9_executed": False,
    }
    summary["h9_estimates"] = _h9_estimates(summary)
    magic_profile._write_json(output_root / "summary.json", summary)
    _write_report(report_path, summary)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit qret inverse-map usage and model compact inverse-map options."
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
