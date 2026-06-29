from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.profile_qret_lazy_inverse_map as profile


def _extra(
    *,
    instructions: int,
    inverse_entries: int,
    inverse_bytes: int,
    constructed_blocks: int,
    never_constructed_blocks: int,
    max_live_entries: int,
    eager_count: int,
    lazy_count: int,
    initial_entries: int,
    lazy_entries: int,
) -> dict[str, object]:
    return {
        "machine_instructions": instructions,
        "machine_instruction_object_bytes_estimated": instructions * 96,
        "machine_instruction_list_node_bytes_estimated": instructions * 24,
        "machine_operand_list_node_bytes_estimated": instructions * 44,
        "machine_ancilla_path_coordinate_list_node_bytes_estimated": instructions * 4,
        "machine_inverse_map_entries": inverse_entries,
        "machine_inverse_map_bytes_estimated": inverse_bytes,
        "machine_inverse_map_mapped_iterator_size_bytes": 8,
        "machine_inverse_map_node_bytes_estimated": 40,
        "machine_inverse_map_valid_blocks": constructed_blocks,
        "machine_inverse_map_never_constructed_blocks": never_constructed_blocks,
        "machine_metadata_bytes_estimated": instructions * 8,
        "machine_instruction_type_count": {
            "LATTICE_SURGERY_MAGIC": instructions // 4,
            "CNOT": instructions // 2,
        },
        "inverse_map_usage_schema": "qret_inverse_map_usage_profile_v1",
        "inverse_map_usage_eager_construction_count": eager_count,
        "inverse_map_usage_lazy_construction_count": lazy_count,
        "inverse_map_usage_ensure_inverse_map_count": lazy_count,
        "inverse_map_usage_ensure_noop_count": 0,
        "inverse_map_usage_constructed_block_count": constructed_blocks,
        "inverse_map_usage_never_constructed_block_count": never_constructed_blocks,
        "inverse_map_usage_initial_inserted_entries": initial_entries,
        "inverse_map_usage_lazy_inserted_entries": lazy_entries,
        "inverse_map_usage_max_live_entries": max_live_entries,
        "inverse_map_usage_final_entries_before_release_total": inverse_entries,
        "inverse_map_usage_contain_count": lazy_count,
        "inverse_map_usage_insert_before_count": 0,
        "inverse_map_usage_insert_after_count": 0,
        "inverse_map_usage_erase_count": 0,
        "inverse_map_usage_release_count": 3,
    }


def _result(
    *,
    case: str,
    variant: str,
    run_index: int,
    peak: int,
    elapsed: float,
    instructions: int,
    inverse_entries: int,
    inverse_bytes: int,
    constructed_blocks: int,
    never_constructed_blocks: int,
    max_live_entries: int,
) -> dict[str, object]:
    is_lazy = variant == "lazy"
    extra = _extra(
        instructions=instructions,
        inverse_entries=inverse_entries,
        inverse_bytes=inverse_bytes,
        constructed_blocks=constructed_blocks,
        never_constructed_blocks=never_constructed_blocks,
        max_live_entries=max_live_entries,
        eager_count=0 if is_lazy else 3,
        lazy_count=1 if is_lazy and constructed_blocks else 0,
        initial_entries=0 if is_lazy else inverse_entries,
        lazy_entries=inverse_entries if is_lazy else 0,
    )
    routing_extra = dict(extra)
    routing_extra.update(
        {
            "routing_queue_total_bytes_estimated": instructions * 12,
            "routing_sim_total_bytes_estimated": instructions * 18,
            "routing_live_total_bytes_estimated": instructions * 400,
        }
    )
    after_extra = dict(extra)
    after_extra.update(
        {
            "machine_inverse_map_entries": 0,
            "machine_inverse_map_bytes_estimated": 0,
        }
    )
    return {
        "case": case,
        "variant": variant,
        "run_index": run_index,
        "returncode": 0,
        "elapsed_seconds": elapsed,
        "qret_peak_rss_kb": peak,
        "tree_peak_rss_kb": peak + 1200,
        "parent_peak_rss_kb": 10_000,
        "routing_peak_rss_kb": peak - 20,
        "raw_resource_metrics": {"runtime": 1, "gate_count": 2, "code_distance": 7},
        "normalized_metrics": {
            "runtime": 1,
            "gate_count": 2,
            "code_distance": 7,
            "compile_info_json": f"/tmp/{case}-{variant}.json",
        },
        "profile_rows": [
            {"stage": "routing_entry", "vmrss_kb": peak - 9000, "extra": after_extra},
            {
                "stage": "routing_after_construct_inverse_map",
                "vmrss_kb": peak - 1000,
                "extra": dict(extra, inverse_map_construction_mode=variant),
            },
            {"stage": "routing_main_loop_peak", "vmrss_kb": peak - 100, "extra": routing_extra},
            {
                "stage": "routing_before_temporary_destroy",
                "vmrss_kb": peak - 80,
                "extra": routing_extra,
            },
            {
                "stage": "routing_before_inverse_map_release",
                "vmrss_kb": peak - 50,
                "mallinfo2_uordblks_kb": peak - 1000,
                "mallinfo2_fordblks_kb": 5000,
                "extra": extra,
            },
            {
                "stage": "routing_after_inverse_map_release",
                "vmrss_kb": peak - 5000,
                "extra": after_extra,
            },
            {"stage": "after_calc_info_without_topology", "vmrss_kb": peak - 20, "extra": after_extra},
        ],
        "provenance": {
            "evaluation_head": "head",
            "qret_executable_hash": "qret",
            "libqret_core_hash": "lib",
            "prepared_optimized_ir_hash": "ir",
            "topology_hash": "topology",
            "pipeline_config_hash": "pipeline",
            "inverse_map_construction_mode": variant,
        },
    }


def _summary() -> dict[str, object]:
    results = [
        _result(
            case="h4_4th_new2",
            variant="eager",
            run_index=1,
            peak=300_000,
            elapsed=7.0,
            instructions=1000,
            inverse_entries=1000,
            inverse_bytes=40_000,
            constructed_blocks=3,
            never_constructed_blocks=0,
            max_live_entries=1000,
        ),
        _result(
            case="h4_4th_new2",
            variant="lazy",
            run_index=1,
            peak=270_000,
            elapsed=7.05,
            instructions=1000,
            inverse_entries=0,
            inverse_bytes=0,
            constructed_blocks=0,
            never_constructed_blocks=3,
            max_live_entries=0,
        ),
        _result(
            case="h5_4th_new2",
            variant="eager",
            run_index=1,
            peak=520_000,
            elapsed=10.0,
            instructions=2000,
            inverse_entries=2000,
            inverse_bytes=80_000,
            constructed_blocks=3,
            never_constructed_blocks=0,
            max_live_entries=2000,
        ),
        _result(
            case="h5_4th_new2",
            variant="eager",
            run_index=2,
            peak=518_000,
            elapsed=10.1,
            instructions=2000,
            inverse_entries=2000,
            inverse_bytes=80_000,
            constructed_blocks=3,
            never_constructed_blocks=0,
            max_live_entries=2000,
        ),
        _result(
            case="h5_4th_new2",
            variant="lazy",
            run_index=1,
            peak=450_000,
            elapsed=10.1,
            instructions=2000,
            inverse_entries=0,
            inverse_bytes=0,
            constructed_blocks=0,
            never_constructed_blocks=3,
            max_live_entries=0,
        ),
        _result(
            case="h5_4th_new2",
            variant="lazy",
            run_index=2,
            peak=452_000,
            elapsed=10.2,
            instructions=2000,
            inverse_entries=0,
            inverse_bytes=0,
            constructed_blocks=0,
            never_constructed_blocks=3,
            max_live_entries=0,
        ),
    ]
    comparisons = profile._metric_comparisons(results)  # type: ignore[arg-type]
    aggregates = [
        profile._aggregate(results, case=case, variant=variant)  # type: ignore[arg-type]
        for case, variants in profile.DEFAULT_RUNS.items()
        for variant in variants
    ]
    summary = {
        "results": results,
        "comparisons": comparisons,
        "aggregates": aggregates,
    }
    summary["adoption_decision"] = profile._adoption_decision(results, comparisons)  # type: ignore[arg-type]
    summary["h9_estimates"] = profile._h9_estimates(summary)
    return summary


def test_validate_cases_and_chain_lengths_reject_h6_h7_h8_h9() -> None:
    assert profile._validate_cases(["h4_4th_new2", "h5_4th_new2"]) == (
        "h4_4th_new2",
        "h5_4th_new2",
    )
    for case in ("h6_4th_new2", "h7_4th_new2", "h8_4th_new2", "h9_4th_new2"):
        with pytest.raises(ValueError, match="H6/H7/H8/H9"):
            profile._validate_cases([case])
    for chain_length in (6, 7, 8, 9):
        with pytest.raises(ValueError, match="H6/H7/H8/H9"):
            profile._validate_chain_lengths([chain_length])


def test_default_run_plan_is_h4_h5_eager_lazy_only() -> None:
    profile._validate_run_plan(profile.DEFAULT_RUNS)

    assert profile.DEFAULT_RUNS["h4_4th_new2"] == {"eager": 1, "lazy": 1}
    assert profile.DEFAULT_RUNS["h5_4th_new2"] == {"eager": 2, "lazy": 2}


def test_variant_env_sets_current_production_and_construction_mode() -> None:
    env = {"QRET_MAGIC_PATH_PROFILE_JSON": "old"}
    profile._variant_env(env, "lazy")

    assert env["QRET_MAGIC_PATH_STORAGE"] == "interned"
    assert env["QRET_SUMMARY_TIME_SERIES_IMPL"] == "legacy_timeseries"
    assert env["QRET_DEP_GRAPH_IMPL"] == "compact"
    assert env["QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING"] == "1"
    assert env["QRET_PROFILE_MAGIC_PATHS"] == "0"
    assert env["QRET_PROFILE_INVERSE_MAP_USAGE"] == "1"
    assert env["QRET_INVERSE_MAP_CONSTRUCTION"] == "lazy"
    assert "QRET_MAGIC_PATH_PROFILE_JSON" not in env


def test_metric_parity_and_adoption_gate_accept_good_lazy_candidate() -> None:
    summary = _summary()

    assert profile._semantic_parity(summary["comparisons"]) is True  # type: ignore[arg-type]
    decision = summary["adoption_decision"]
    assert decision["production_candidate_adopted_by_h5_measurement"] is True  # type: ignore[index]
    assert decision["h5_median_qret_peak_reduction_kb"] >= 30 * 1024  # type: ignore[index,operator]
    assert decision["all_lazy_runs_below_eager"] is True  # type: ignore[index]
    assert decision["elapsed_gate_3_percent"] is True  # type: ignore[index]
    assert decision["h5_max_live_gate"] is True  # type: ignore[index]


def test_usage_counters_track_constructed_and_never_constructed_blocks() -> None:
    summary = _summary()
    lazy_h5 = profile._first_result(  # type: ignore[arg-type]
        summary["results"], case="h5_4th_new2", variant="lazy"
    )

    assert profile._usage_counter(lazy_h5, "constructed_block_count") == 0
    assert profile._usage_counter(lazy_h5, "never_constructed_block_count") == 3
    assert profile._usage_counter(lazy_h5, "initial_inserted_entries") == 0
    assert profile._usage_counter(lazy_h5, "max_live_entries") == 0


def test_h9_estimates_are_labeled_and_component_split() -> None:
    h9 = _summary()["h9_estimates"]

    assert h9["observed"]["classification"] == "observed"  # type: ignore[index]
    assert h9["estimated"]["classification"] == "estimated"  # type: ignore[index]
    assert h9["theoretical"]["classification"] == "theoretical"  # type: ignore[index]
    assert set(h9["estimated"]["scenarios"]) == {"conservative", "central", "upper"}  # type: ignore[index]
    central = h9["estimated"]["scenarios"]["central"]  # type: ignore[index]
    assert "inverse_map" in central["current_production_eager"]["components"]
    assert "inverse_map" in central["with_lazy_inverse_map_candidate"]["components"]


def test_run_provenance_records_hashes(tmp_path: Path) -> None:
    pipeline = tmp_path / "compile.yaml"
    ir = tmp_path / "input.ir.json"
    pipeline.write_text("pipeline\n", encoding="utf-8")
    ir.write_text("ir\n", encoding="utf-8")
    artifact = SimpleNamespace(optimized_ir_path=ir, optimized_ir_hash=profile._sha256_file(ir))
    result = {
        "pipeline_path": str(pipeline),
        "runtime_hashes_before": {
            "qret_executable_hash": "qret-hash",
            "qret_core_library_path": "/tmp/libqret-core.so",
            "qret_core_library_hash": "lib-hash",
        },
    }

    provenance = profile._run_provenance(result, artifact, "eager")

    assert provenance["qret_executable_hash"] == "qret-hash"
    assert provenance["libqret_core_hash"] == "lib-hash"
    assert provenance["prepared_optimized_ir_hash"] == profile._sha256_file(ir)
    assert provenance["pipeline_config_hash"] == profile._sha256_file(pipeline)
    assert provenance["inverse_map_construction_mode"] == "eager"


def test_report_mentions_limits_classifications_and_provenance(tmp_path: Path) -> None:
    summary = _summary()
    report = tmp_path / "report.md"
    profile._write_report(report, summary)
    text = report.read_text(encoding="utf-8")

    assert "largest measured case: `H5`" in text
    assert "H6 executed: `False`" in text
    assert "H7 executed: `False`" in text
    assert "H8 executed: `False`" in text
    assert "H9 executed: `False`" in text
    assert "estimated from observed H4/H5 values, not measured" in text
    assert "observed" in text
    assert "estimated" in text
    assert "theoretical" in text
    assert "pipeline hash" in text
