from __future__ import annotations

from pathlib import Path

import pytest

import scripts.profile_qret_inverse_map_usage as profile


def _extra(*, instructions: int, inverse_entries: int, inverse_bytes: int, profiled: bool) -> dict[str, object]:
    extra: dict[str, object] = {
        "machine_instructions": instructions,
        "machine_instruction_object_bytes_estimated": instructions * 96,
        "machine_instruction_list_node_bytes_estimated": instructions * 24,
        "machine_operand_list_node_bytes_estimated": instructions * 40,
        "machine_ancilla_path_coordinate_list_node_bytes_estimated": instructions * 4,
        "machine_inverse_map_entries": inverse_entries,
        "machine_inverse_map_bytes_estimated": inverse_bytes,
        "machine_inverse_map_mapped_iterator_size_bytes": 8,
        "machine_inverse_map_node_bytes_estimated": 40,
        "machine_metadata_bytes_estimated": instructions * 8,
        "machine_instruction_type_count": {
            "LATTICE_SURGERY_MAGIC": instructions // 4,
            "CNOT": instructions // 2,
        },
        "machine_instruction_type_object_bytes_estimated": {
            "LATTICE_SURGERY_MAGIC": instructions * 48,
            "CNOT": instructions * 24,
        },
    }
    if profiled:
        extra.update(
            {
                "machine_instruction_projected_stable_id_object_bytes_estimated": instructions * 104,
                "machine_instruction_projected_stable_id_object_delta_bytes_estimated": instructions * 8,
                "machine_instruction_type_projected_stable_id_object_bytes_estimated": {
                    "LATTICE_SURGERY_MAGIC": instructions * 52,
                    "CNOT": instructions * 26,
                },
                "machine_instruction_type_stable_id_object_delta_bytes_estimated": {
                    "LATTICE_SURGERY_MAGIC": instructions * 4,
                    "CNOT": instructions * 2,
                },
                "inverse_map_usage_schema": "qret_inverse_map_usage_profile_v1",
                "inverse_map_usage_construct_inverse_map_count": 1,
                "inverse_map_usage_initial_inserted_entries": inverse_entries,
                "inverse_map_usage_full_rebuild_count": 1,
                "inverse_map_usage_lazy_rebuild_count": 0,
                "inverse_map_usage_contain_count": 10,
                "inverse_map_usage_contain_hit_count": 9,
                "inverse_map_usage_contain_miss_count": 1,
                "inverse_map_usage_insert_before_count": 5,
                "inverse_map_usage_insert_after_count": 2,
                "inverse_map_usage_erase_count": 3,
                "inverse_map_usage_release_count": 1,
                "inverse_map_usage_max_live_entries": inverse_entries,
                "inverse_map_usage_final_entries_before_release_total": inverse_entries,
                "inverse_map_usage_vector_const_iterator_size_bytes": 8,
                "inverse_map_usage_pointer_size_bytes": 8,
            }
        )
    return extra


def _result(
    *,
    case: str,
    variant: str,
    peak: int,
    instructions: int,
    inverse_entries: int,
    inverse_bytes: int,
    profiled: bool,
) -> dict[str, object]:
    before_extra = _extra(
        instructions=instructions,
        inverse_entries=inverse_entries,
        inverse_bytes=inverse_bytes,
        profiled=profiled,
    )
    after_extra = dict(before_extra)
    after_extra.update(
        {
            "machine_inverse_map_entries": 0,
            "machine_inverse_map_bytes_estimated": 0,
        }
    )
    if profiled:
        after_extra["inverse_map_usage_current_entries"] = 0
    routing_extra = dict(before_extra)
    routing_extra.update(
        {
            "routing_queue_total_bytes_estimated": instructions * 12,
            "routing_sim_total_bytes_estimated": instructions * 18,
            "routing_live_total_bytes_estimated": instructions * 400,
        }
    )
    return {
        "case": case,
        "variant": variant,
        "run_index": 1,
        "returncode": 0,
        "qret_peak_rss_kb": peak,
        "tree_peak_rss_kb": peak + 1000,
        "parent_peak_rss_kb": 10_000,
        "elapsed_seconds": 10.0,
        "raw_resource_metrics": {"runtime": 1, "gate_count": 2},
        "normalized_metrics": {
            "runtime": 1,
            "gate_count": 2,
            "compile_info_json": f"/tmp/{case}-{variant}.json",
        },
        "profile_rows": [
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
                "extra": before_extra,
            },
            {
                "stage": "routing_after_inverse_map_release",
                "vmrss_kb": peak - 5000,
                "extra": after_extra,
            },
        ],
    }


def _summary() -> dict[str, object]:
    results = [
        _result(
            case="h4_4th_new2",
            variant="profile_off",
            peak=300_000,
            instructions=1000,
            inverse_entries=1000,
            inverse_bytes=40_000,
            profiled=False,
        ),
        _result(
            case="h4_4th_new2",
            variant="profile_on",
            peak=300_500,
            instructions=1000,
            inverse_entries=1000,
            inverse_bytes=40_000,
            profiled=True,
        ),
        _result(
            case="h5_4th_new2",
            variant="profile_on",
            peak=550_000,
            instructions=2000,
            inverse_entries=2000,
            inverse_bytes=80_000,
            profiled=True,
        ),
    ]
    comparisons = profile._metric_comparisons(results)
    return {
        "results": results,
        "comparisons": comparisons,
        "h9_estimates": profile._h9_estimates({"results": results}),
    }


def test_validate_cases_rejects_h6_h7_h8_h9() -> None:
    assert profile._validate_cases(["h4_4th_new2", "h5_4th_new2"]) == (
        "h4_4th_new2",
        "h5_4th_new2",
    )
    for case in ("h6_4th_new2", "h7_4th_new2", "h8_4th_new2", "h9_4th_new2"):
        with pytest.raises(ValueError, match="H6/H7/H8/H9"):
            profile._validate_cases([case])


def test_variant_env_sets_current_production_and_profile_flag() -> None:
    env = {"QRET_MAGIC_PATH_PROFILE_JSON": "old"}
    profile._variant_env(env, "profile_on")

    assert env["QRET_MAGIC_PATH_STORAGE"] == "interned"
    assert env["QRET_SUMMARY_TIME_SERIES_IMPL"] == "legacy_timeseries"
    assert env["QRET_DEP_GRAPH_IMPL"] == "compact"
    assert env["QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING"] == "1"
    assert env["QRET_PROFILE_MAGIC_PATHS"] == "0"
    assert env["QRET_PROFILE_INVERSE_MAP_USAGE"] == "1"
    assert "QRET_MAGIC_PATH_PROFILE_JSON" not in env


def test_profile_fields_are_gated_and_h4_metrics_match() -> None:
    summary = _summary()
    off = profile._first_result(summary["results"], "h4_4th_new2", "profile_off")  # type: ignore[arg-type]
    on = profile._first_result(summary["results"], "h4_4th_new2", "profile_on")  # type: ignore[arg-type]

    assert profile._has_inverse_usage_fields(off) is False
    assert profile._has_inverse_usage_fields(on) is True
    assert profile._semantic_parity(summary["comparisons"]) is True  # type: ignore[arg-type]


def test_candidate_models_include_compact_vector_saving() -> None:
    h5 = profile._first_result(_summary()["results"], "h5_4th_new2", "profile_on")  # type: ignore[arg-type]
    models = {row["candidate"]: row for row in profile._candidate_models(h5)}

    assert models["current_std_map"]["classification"] == "observed"
    assert models["stable_instruction_id_vector"]["classification"] == "theoretical"
    assert models["stable_instruction_id_vector"]["bytes"] < models["current_std_map"]["bytes"]
    assert models["stable_instruction_id_vector"]["saving_bytes"] > 0


def test_h9_estimates_are_model_only_and_labeled() -> None:
    h9 = _summary()["h9_estimates"]

    assert h9["observed"]["classification"] == "observed"
    assert h9["estimated"]["classification"] == "estimated"
    assert h9["theoretical"]["classification"] == "theoretical"
    assert set(h9["estimated"]["scenarios"]) == {"conservative", "central", "upper"}
    central = h9["estimated"]["scenarios"]["central"]
    assert "inverse_map" in central["current_production"]["components"]
    assert "inverse_map" in central["with_compact_inverse_map_candidate"]["components"]


def test_report_mentions_limits_and_classifications(tmp_path: Path) -> None:
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
