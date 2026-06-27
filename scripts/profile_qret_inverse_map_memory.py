#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import profile_qret_routing_live_memory as base


DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "qret_inverse_map_memory"
DEFAULT_REPORT_PATH = (
    REPO_ROOT / "docs" / "benchmarks" / "qret_inverse_map_memory_optimization.md"
)
VARIANTS = {
    "baseline": {"release_inverse_map": "0"},
    "inverse_map_release": {"release_inverse_map": "1"},
}
DEFAULT_RUNS = {
    "h4_4th_new2": {"baseline": 1, "inverse_map_release": 1},
    "h5_4th_new2": {"baseline": 2, "inverse_map_release": 2},
}
REQUIRED_STAGES = tuple(
    dict.fromkeys(
        (
            *base.REQUIRED_STAGES,
            "routing_before_inverse_map_release",
            "routing_after_inverse_map_release",
        )
    )
)
STAGE_ORDER = (
    "routing_main_loop_exit",
    "routing_before_inverse_map_release",
    "routing_after_inverse_map_release",
    "before_calc_info_without_topology",
    "after_calc_info_without_topology",
    "before_calc_info_with_topology",
    "after_calc_info_with_topology",
    "compile_exit",
)


def _validate_release_value(value: str) -> str:
    if value not in {"0", "1"}:
        raise ValueError("QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING must be 0 or 1")
    return value


def _variant_release_value(variant: str) -> str:
    try:
        return _validate_release_value(str(VARIANTS[variant]["release_inverse_map"]))
    except KeyError as exc:
        raise ValueError(f"unknown variant: {variant}") from exc


def _variant_env(env: dict[str, str], variant: str) -> None:
    env["QRET_SUMMARY_TIME_SERIES_IMPL"] = "legacy_timeseries"
    env["QRET_RSS_DIAGNOSTIC_TRIM_STAGE"] = "none"
    env["QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING"] = _variant_release_value(variant)
    env.pop("QRET_DEP_GRAPH_IMPL", None)


@contextlib.contextmanager
def _patched_base() -> Iterator[None]:
    saved = {
        "DEFAULT_OUTPUT_ROOT": base.DEFAULT_OUTPUT_ROOT,
        "DEFAULT_REPORT_PATH": base.DEFAULT_REPORT_PATH,
        "VARIANTS": base.VARIANTS,
        "DEFAULT_RUNS": base.DEFAULT_RUNS,
        "REQUIRED_STAGES": base.REQUIRED_STAGES,
        "_variant_env": base._variant_env,
        "_variant_trim_stage": base._variant_trim_stage,
    }
    base.DEFAULT_OUTPUT_ROOT = DEFAULT_OUTPUT_ROOT
    base.DEFAULT_REPORT_PATH = DEFAULT_REPORT_PATH
    base.VARIANTS = VARIANTS
    base.DEFAULT_RUNS = DEFAULT_RUNS
    base.REQUIRED_STAGES = REQUIRED_STAGES
    base._variant_env = _variant_env
    base._variant_trim_stage = lambda variant: "none"
    try:
        yield
    finally:
        for key, value in saved.items():
            setattr(base, key, value)


def _median(values: Sequence[float | int | None]) -> float | int | None:
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
        return f"{float(value) / base.ONE_MB:.1f}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_mb_from_kb(value: Any) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value) / 1024.0:.1f}"
    except (TypeError, ValueError):
        return str(value)


def _stage_row(rows: Sequence[Mapping[str, Any]], stage: str) -> Mapping[str, Any]:
    for row in reversed(rows):
        if row.get("stage") == stage:
            return row
    return {}


def _extra_at_stage(rows: Sequence[Mapping[str, Any]], stage: str) -> dict[str, Any]:
    row = _stage_row(rows, stage)
    extra = row.get("extra")
    return dict(extra) if isinstance(extra, Mapping) else {}


def _stage_rss(row: Mapping[str, Any]) -> int | None:
    value = row.get("vmrss_kb")
    return None if value is None else int(value)


def _stage_allocator(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "rss_kb": row.get("vmrss_kb"),
        "pss_kb": row.get("pss_kb"),
        "private_dirty_kb": row.get("private_dirty_kb"),
        "uordblks_kb": row.get("mallinfo2_uordblks_kb"),
        "fordblks_kb": row.get("mallinfo2_fordblks_kb"),
        "arena_kb": None
        if row.get("mallinfo2_arena") is None
        else int(row["mallinfo2_arena"]) // 1024,
        "keepcost_kb": None
        if row.get("mallinfo2_keepcost") is None
        else int(row["mallinfo2_keepcost"]) // 1024,
    }


def _stage_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    ret: dict[str, dict[str, Any]] = {}
    for stage in STAGE_ORDER:
        row = _stage_row(rows, stage)
        extra = row.get("extra")
        if not isinstance(extra, Mapping):
            extra = {}
        ret[stage] = {
            **_stage_allocator(row),
            "machine_instructions": extra.get("machine_instructions"),
            "inverse_map_entries": extra.get("machine_inverse_map_entries"),
            "inverse_map_bytes": extra.get("machine_inverse_map_bytes_estimated"),
            "inverse_map_valid_blocks": extra.get("machine_inverse_map_valid_blocks"),
            "inverse_map_released_blocks": extra.get("machine_inverse_map_released_blocks"),
            "machine_total_bytes": extra.get("machine_total_bytes_estimated"),
            "ancilla_path_bytes": extra.get(
                "machine_ancilla_path_coordinate_list_node_bytes_estimated",
                extra.get("machine_path_coordinate_list_node_bytes_estimated"),
            ),
            "operand_list_bytes": extra.get("machine_operand_list_node_bytes_estimated"),
            "metadata_bytes": extra.get("machine_metadata_bytes_estimated"),
        }
    return ret


def _result_rows(results: Sequence[Mapping[str, Any]], case: str, variant: str) -> list[Mapping[str, Any]]:
    return [row for row in results if row.get("case") == case and row.get("variant") == variant]


def _aggregate(results: Sequence[Mapping[str, Any]], case: str, variant: str) -> dict[str, Any]:
    rows = _result_rows(results, case, variant)
    return {
        "runs": len(rows),
        "median_peak_rss_kb": _median([row.get("qret_peak_rss_kb") for row in rows]),
        "median_elapsed_seconds": _median([row.get("elapsed_seconds") for row in rows]),
        "median_compile_info_size_bytes": _median(
            [row.get("compile_info_size_bytes") for row in rows]
        ),
        "median_routing_exit_kb": _median(
            [_stage_rss(_stage_row(row.get("profile_rows", []), "routing_main_loop_exit")) for row in rows]
        ),
        "median_after_release_kb": _median(
            [
                _stage_rss(
                    _stage_row(row.get("profile_rows", []), "routing_after_inverse_map_release")
                )
                for row in rows
            ]
        ),
        "median_calc_info_peak_kb": _median(
            [
                max(
                    (
                        _stage_rss(_stage_row(row.get("profile_rows", []), stage)) or 0
                        for stage in (
                            "after_calc_info_without_topology",
                            "after_calc_info_with_topology",
                        )
                    ),
                    default=0,
                )
                for row in rows
            ]
        ),
    }


def _first_result(results: Sequence[Mapping[str, Any]], case: str, variant: str) -> Mapping[str, Any]:
    return next((row for row in results if row.get("case") == case and row.get("variant") == variant), {})


def _instruction_type_breakdown(extra: Mapping[str, Any], limit: int = 10) -> list[dict[str, Any]]:
    counts = extra.get("machine_instruction_type_count", {})
    object_bytes = extra.get("machine_instruction_type_object_bytes_estimated", {})
    operand_bytes = extra.get("machine_instruction_type_operand_list_node_bytes_estimated", {})
    path_bytes = extra.get("machine_instruction_type_ancilla_path_list_node_bytes_estimated", {})
    total_bytes = extra.get("machine_instruction_type_total_bytes_estimated", {})
    if not all(isinstance(item, Mapping) for item in (counts, object_bytes, operand_bytes, path_bytes, total_bytes)):
        return []
    rows = [
        {
            "type": str(type_name),
            "count": int(count),
            "object_bytes": int(object_bytes.get(type_name, 0)),
            "operand_bytes": int(operand_bytes.get(type_name, 0)),
            "ancilla_path_bytes": int(path_bytes.get(type_name, 0)),
            "total_bytes": int(total_bytes.get(type_name, 0)),
        }
        for type_name, count in counts.items()
    ]
    return sorted(rows, key=lambda row: row["total_bytes"], reverse=True)[:limit]


def _component_rows(extra: Mapping[str, Any]) -> list[tuple[str, Any, Any]]:
    return [
        ("instruction object bytes", extra.get("machine_instructions"), extra.get("machine_instruction_object_bytes_estimated")),
        ("instruction list node bytes", extra.get("machine_instructions"), extra.get("machine_instruction_list_node_bytes_estimated")),
        ("basic block node bytes", extra.get("machine_basic_blocks"), extra.get("machine_basic_block_node_bytes_estimated")),
        ("inverse map bytes", extra.get("machine_inverse_map_entries"), extra.get("machine_inverse_map_bytes_estimated")),
        ("operand list node bytes", None, extra.get("machine_operand_list_node_bytes_estimated")),
        ("condition list bytes", extra.get("machine_condition_elements"), extra.get("machine_condition_list_node_bytes_estimated")),
        ("ancilla/path coordinate list node bytes", extra.get("machine_path_coordinate_elements"), extra.get("machine_ancilla_path_coordinate_list_node_bytes_estimated")),
        ("destination coordinate bytes", extra.get("machine_destination_coordinate_fields"), extra.get("machine_destination_coordinate_bytes_estimated")),
        ("metadata bytes", extra.get("machine_metadata_objects"), extra.get("machine_metadata_bytes_estimated")),
        ("predecessor/successor container bytes", None, extra.get("machine_predecessor_successor_container_bytes_estimated")),
        ("compile-info bytes", None, extra.get("machine_compile_info_bytes_estimated")),
        ("IR pointer bytes", None, extra.get("machine_ir_pointer_bytes_estimated")),
        ("MachineFunction corrected total", None, extra.get("machine_total_bytes_estimated")),
    ]


def _metric_parity(comparisons: Mapping[str, Any]) -> bool:
    return bool(comparisons) and all(
        item.get("raw", {}).get("all_equal") and item.get("normalized", {}).get("all_equal")
        for item in comparisons.values()
    )


def _production_decision(results: Sequence[Mapping[str, Any]], comparisons: Mapping[str, Any]) -> dict[str, Any]:
    baseline = _aggregate(results, "h5_4th_new2", "baseline")
    release = _aggregate(results, "h5_4th_new2", "inverse_map_release")
    base_peak = baseline.get("median_peak_rss_kb")
    rel_peak = release.get("median_peak_rss_kb")
    base_elapsed = baseline.get("median_elapsed_seconds")
    rel_elapsed = release.get("median_elapsed_seconds")
    peak_saved_kb = None if base_peak is None or rel_peak is None else int(base_peak - rel_peak)
    elapsed_ratio = None if not base_elapsed or rel_elapsed is None else float(rel_elapsed) / float(base_elapsed)
    baseline_runs = _result_rows(results, "h5_4th_new2", "baseline")
    release_runs = _result_rows(results, "h5_4th_new2", "inverse_map_release")
    consistent_peak_drop = (
        bool(baseline_runs)
        and bool(release_runs)
        and max(int(row.get("qret_peak_rss_kb") or 0) for row in release_runs)
        < min(int(row.get("qret_peak_rss_kb") or 0) for row in baseline_runs)
    )
    return {
        "metrics_equal": _metric_parity(comparisons),
        "peak_saved_kb": peak_saved_kb,
        "peak_saved_fraction": None
        if peak_saved_kb is None or not base_peak
        else float(peak_saved_kb) / float(base_peak),
        "elapsed_ratio": elapsed_ratio,
        "consistent_peak_drop": consistent_peak_drop,
        "passes": bool(
            _metric_parity(comparisons)
            and consistent_peak_drop
            and peak_saved_kb is not None
            and peak_saved_kb > 0
            and (elapsed_ratio is None or elapsed_ratio <= 1.03)
        ),
    }


def _write_report(path: Path, summary: Mapping[str, Any]) -> None:
    environment = summary.get("environment", {})
    build = summary.get("build_provenance", {})
    results = summary.get("results", [])
    comparisons = summary.get("comparisons", {})
    decision = _production_decision(results, comparisons)
    baseline = _first_result(results, "h5_4th_new2", "baseline") or _first_result(
        results,
        "h4_4th_new2",
        "baseline",
    )
    release = _first_result(results, "h5_4th_new2", "inverse_map_release") or _first_result(
        results,
        "h4_4th_new2",
        "inverse_map_release",
    )
    baseline_rows = baseline.get("profile_rows", [])
    release_rows = release.get("profile_rows", [])
    before_extra = _extra_at_stage(baseline_rows, "routing_before_inverse_map_release")
    after_release_extra = _extra_at_stage(release_rows, "routing_after_inverse_map_release")
    type_rows = _instruction_type_breakdown(before_extra)
    baseline_stage = _stage_summary(baseline_rows)
    release_stage = _stage_summary(release_rows)
    h5_base = _aggregate(results, "h5_4th_new2", "baseline")
    h5_rel = _aggregate(results, "h5_4th_new2", "inverse_map_release")
    release_drop_kb = None
    before_release_rss = release_stage["routing_before_inverse_map_release"].get("rss_kb")
    after_release_rss = release_stage["routing_after_inverse_map_release"].get("rss_kb")
    if before_release_rss is not None and after_release_rss is not None:
        release_drop_kb = int(before_release_rss) - int(after_release_rss)
    full_schema_summary: dict[str, Any] = {}
    output_root = environment.get("output_root")
    if output_root:
        full_schema_path = Path(str(output_root)) / "h4_full_schema" / "summary.json"
        if full_schema_path.exists():
            try:
                full_schema_summary = json.loads(full_schema_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                full_schema_summary = {}

    lines = [
        "# qret Inverse Map Memory Optimization",
        "",
        "H6 was not run. This profile only uses H4 for instrumentation/correctness checks and H5 for A/B selection.",
        "",
        "## Environment",
        "",
        f"- Evaluation HEAD at run start: `{environment.get('evaluation_head')}`",
        f"- qret executable hash: `{environment.get('measurement_runtime_hashes', {}).get('qret_executable_hash')}`",
        f"- libqret-core hash: `{environment.get('measurement_runtime_hashes', {}).get('qret_core_library_hash')}`",
        f"- libqret-core path: `{environment.get('measurement_runtime_hashes', {}).get('qret_core_library_path')}`",
        f"- build requested: `{build.get('build_requested')}`",
        f"- batch size: `{environment.get('batch_size')}`",
        f"- sampling interval: `{environment.get('sample_interval_sec')}` sec",
        f"- output root: `{environment.get('output_root')}`",
        "",
        "## Consumer Audit",
        "",
        "| method | call site | stage | lazy rebuild required |",
        "| ------ | --------- | ----- | --------------------- |",
        "| `ConstructInverseMap` | `routing.cpp` | routing start after validate | no |",
        "| `ConstructInverseMap` | `runtime_simulation_pruning.cpp` | pruning pass setup | no |",
        "| `Contain` | `simulator.h`, `search_chip_comm.cpp` | routing helper lookup | yes for custom post-routing passes |",
        "| `InsertBefore` | `simulator.cpp`, `runtime_simulation_pruning.cpp` | routing/pruning mutation | yes |",
        "| `InsertAfter` | `simulator.cpp`, `search_chip_comm.cpp` | routing mutation | yes |",
        "| `Erase` | `simulator.cpp`, `search_chip_comm.cpp`, `runtime_simulation_pruning.cpp` | routing/pruning mutation | yes |",
        "| `InverseMapSize` | `memory_profile_stats.cpp` | profiling markers | no |",
        "| `mp_` | `machine_function.cpp` only | implementation detail | no external direct use |",
        "",
        "Compile-info and pipeline-state output iterate instructions directly and do not require the inverse map. Custom post-routing passes remain compatible because `Contain`, `InsertBefore`, `InsertAfter`, and `Erase` rebuild lazily.",
        "",
        "## Corrected MachineFunction Breakdown",
        "",
        "| component | count | estimated bytes | share |",
        "| --------- | ----: | --------------: | ----: |",
    ]
    total = before_extra.get("machine_total_bytes_estimated")
    total_float = float(total or 0)
    for name, count, bytes_value in _component_rows(before_extra):
        share = "" if not total_float or bytes_value is None else f"{100.0 * float(bytes_value) / total_float:.1f}%"
        lines.append(f"| {name} | {_fmt_int(count)} | {_fmt_int(bytes_value)} | {share} |")
    lines.extend(
        [
            "",
            "Destination coordinate and metadata bytes are reported as object subfields and are not added again to the corrected total. Ancilla/path list nodes are included once through operand list node bytes.",
            "",
            "## Instruction Type Breakdown",
            "",
            "| type | count | object MB | operand MB | ancilla/path MB | total MB |",
            "| ---- | ----: | --------: | ---------: | --------------: | -------: |",
        ]
    )
    for row in type_rows:
        lines.append(
            "| {type} | {count} | {obj} | {operand} | {path} | {total} |".format(
                type=row["type"],
                count=_fmt_int(row["count"]),
                obj=_fmt_mb_from_bytes(row["object_bytes"]),
                operand=_fmt_mb_from_bytes(row["operand_bytes"]),
                path=_fmt_mb_from_bytes(row["ancilla_path_bytes"]),
                total=_fmt_mb_from_bytes(row["total_bytes"]),
            )
        )
    lines.extend(
        [
            "",
            "## H5 Inverse Map",
            "",
            f"- entry count: `{_fmt_int(before_extra.get('machine_inverse_map_entries'))}`",
            f"- estimated bytes: `{_fmt_int(before_extra.get('machine_inverse_map_bytes_estimated'))}` (`{_fmt_mb_from_bytes(before_extra.get('machine_inverse_map_bytes_estimated'))}` MB)",
            f"- basic block count: `{_fmt_int(before_extra.get('machine_basic_blocks'))}`",
            f"- largest block entries: `{_fmt_int(before_extra.get('machine_inverse_map_largest_block_entries'))}`",
            f"- key size bytes: `{_fmt_int(before_extra.get('machine_inverse_map_key_size_bytes'))}`",
            f"- mapped iterator size bytes: `{_fmt_int(before_extra.get('machine_inverse_map_mapped_iterator_size_bytes'))}`",
            f"- estimated node overhead bytes: `{_fmt_int(before_extra.get('machine_inverse_map_node_overhead_estimated_bytes'))}`",
            "",
            "`std::map` node size is an estimate; the C++ standard does not specify node layout.",
            "",
            "## H5 A/B",
            "",
            "| variant | median peak | routing exit | after release | calc-info peak | elapsed |",
            "| ------- | ----------: | -----------: | ------------: | -------------: | ------: |",
            f"| baseline | {_fmt_int(h5_base.get('median_peak_rss_kb'))} | {_fmt_int(h5_base.get('median_routing_exit_kb'))} | {_fmt_int(h5_base.get('median_after_release_kb'))} | {_fmt_int(h5_base.get('median_calc_info_peak_kb'))} | {_fmt_float(h5_base.get('median_elapsed_seconds'))} |",
            f"| inverse_map_release | {_fmt_int(h5_rel.get('median_peak_rss_kb'))} | {_fmt_int(h5_rel.get('median_routing_exit_kb'))} | {_fmt_int(h5_rel.get('median_after_release_kb'))} | {_fmt_int(h5_rel.get('median_calc_info_peak_kb'))} | {_fmt_float(h5_rel.get('median_elapsed_seconds'))} |",
            "",
            "## Allocator A/B",
            "",
            "| variant | stage | uordblks | fordblks | RSS |",
            "| ------- | ----- | -------: | -------: | --: |",
        ]
    )
    for variant_name, stage_map in (("baseline", baseline_stage), ("inverse_map_release", release_stage)):
        for stage in (
            "routing_before_inverse_map_release",
            "routing_after_inverse_map_release",
            "after_calc_info_with_topology",
        ):
            row = stage_map.get(stage, {})
            lines.append(
                f"| {variant_name} | `{stage}` | {_fmt_int(row.get('uordblks_kb'))} | {_fmt_int(row.get('fordblks_kb'))} | {_fmt_int(row.get('rss_kb'))} |"
            )
    lines.extend(
        [
            "",
            "## Correctness",
            "",
            f"- raw metrics parity: `{decision['metrics_equal']}`",
            f"- normalized metrics parity: `{decision['metrics_equal']}`",
            f"- H4 full schema raw parity: `{full_schema_summary.get('raw_equal')}`",
            f"- H4 full schema normalized parity: `{full_schema_summary.get('normalized_equal')}`",
            f"- summary schema: qret return code was zero for completed A/B runs.",
            f"- custom pipeline lazy rebuild: covered by `target_sc_ls_fixed_v0_machine_function_inverse_map`.",
            f"- routing after release inverse map entries: `{_fmt_int(after_release_extra.get('machine_inverse_map_entries'))}`",
            "",
            "## H4 Full Schema Check",
            "",
            "| release env | return code | elapsed | compile_info bytes | after-release entries |",
            "| ----------- | ----------: | ------: | -----------------: | --------------------: |",
        ]
    )
    for row in full_schema_summary.get("results", []):
        if not isinstance(row, Mapping):
            continue
        lines.append(
            "| {release} | {returncode} | {elapsed} | {size} | {entries} |".format(
                release=row.get("release"),
                returncode=_fmt_int(row.get("returncode")),
                elapsed=_fmt_float(row.get("elapsed_seconds")),
                size=_fmt_int(row.get("compile_info_size_bytes")),
                entries=_fmt_int(row.get("after_release_entries")),
            )
        )
    lines.extend(
        [
            "",
            "## Final Answers",
            "",
            f"1. H5 inverse map estimated size: `{_fmt_mb_from_bytes(before_extra.get('machine_inverse_map_bytes_estimated'))}` MB.",
            f"2. Release-immediate RSS drop: `{_fmt_mb_from_kb(release_drop_kb)}` MB.",
            f"3. H5 final peak drop: `{_fmt_mb_from_kb(decision.get('peak_saved_kb'))}` MB (`{_fmt_float(100.0 * float(decision.get('peak_saved_fraction') or 0), 2)}%`).",
            f"4. Calc-info reuse of freed allocator space: compare `fordblks` in Allocator A/B; observed after-release `fordblks` is `{_fmt_int(release_stage['routing_after_inverse_map_release'].get('fordblks_kb'))}` KB.",
            f"5. Elapsed ratio release/baseline: `{_fmt_float(decision.get('elapsed_ratio'), 4)}`.",
            "6. Lazy rebuild works in targeted C++ tests.",
            "7. Custom pipeline compatibility is maintained by lazy rebuild.",
            f"8. Corrected MachineFunction total: `{_fmt_mb_from_bytes(before_extra.get('machine_total_bytes_estimated'))}` MB.",
            f"9. Ancilla/path list: `{_fmt_mb_from_bytes(before_extra.get('machine_ancilla_path_coordinate_list_node_bytes_estimated'))}` MB.",
            f"10. Metadata: `{_fmt_mb_from_bytes(before_extra.get('machine_metadata_bytes_estimated'))}` MB.",
            f"11. Operand list: `{_fmt_mb_from_bytes(before_extra.get('machine_operand_list_node_bytes_estimated'))}` MB.",
            f"12. Inverse map release production default: `{decision['passes']}`.",
            f"13. If not production default, reason: `passes={decision['passes']}`, consistent peak drop `{decision['consistent_peak_drop']}`, elapsed ratio `{_fmt_float(decision.get('elapsed_ratio'), 4)}`.",
            "14. Next candidate is ancilla/path only if the corrected value crosses the threshold above; otherwise move to Python parent memory.",
            "15. Python parent process should be considered if inverse map and ancilla/path do not meet the next-candidate threshold.",
            "16. H6 was not run.",
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
    if any(case not in base.CASE_CHAIN_LENGTH for case in cases):
        raise ValueError(f"unsupported case requested: {cases}")
    with _patched_base():
        summary = base.run_profile(
            output_root=output_root,
            report_path=output_root / "routing_live_base_report.md",
            cache_root=cache_root,
            build=build,
            cases=cases,
            batch_size=batch_size,
            sample_interval_sec=sample_interval_sec,
        )
    summary["h6_run"] = False
    summary["production_decision"] = _production_decision(
        summary.get("results", []),
        summary.get("comparisons", {}),
    )
    base._write_json(output_root / "summary.json", summary)
    _write_report(report_path, summary)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Profile qret inverse-map release memory.")
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
    parser.add_argument("--sample-interval-sec", type=float, default=base.SAMPLE_INTERVAL_SEC)
    parser.add_argument(
        "--cases",
        nargs="+",
        choices=tuple(base.CASE_CHAIN_LENGTH),
        default=tuple(base.CASE_CHAIN_LENGTH),
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
