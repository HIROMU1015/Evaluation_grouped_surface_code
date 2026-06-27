from __future__ import annotations

from pathlib import Path

import pytest

import scripts.profile_qret_inverse_map_memory as profile


def _result(
    *,
    case: str = "h5_4th_new2",
    variant: str = "baseline",
    peak: int = 640_000,
    elapsed: float = 10.0,
    entries: int = 3,
    after_entries: int | None = None,
) -> dict[str, object]:
    metrics = {
        "runtime": 1,
        "runtime_without_topology": 1,
        "gate_count": 2,
        "gate_depth": 3,
        "estimated_execution_time_sec": 4.0,
        "compile_info_json": "/tmp/a.json",
    }
    after_entries = entries if after_entries is None else after_entries
    rows = [
        {
            "stage": "routing_before_inverse_map_release",
            "vmrss_kb": 500_000,
            "mallinfo2_uordblks_kb": 450_000,
            "mallinfo2_fordblks_kb": 10_000,
            "extra": {
                "machine_basic_blocks": 1,
                "machine_instructions": 3,
                "machine_total_bytes_estimated": 3_000,
                "machine_instruction_object_bytes_estimated": 600,
                "machine_instruction_list_node_bytes_estimated": 96,
                "machine_basic_block_node_bytes_estimated": 128,
                "machine_inverse_map_entries": entries,
                "machine_inverse_map_bytes_estimated": 120,
                "machine_inverse_map_largest_block_entries": entries,
                "machine_inverse_map_key_size_bytes": 8,
                "machine_inverse_map_mapped_iterator_size_bytes": 8,
                "machine_inverse_map_node_overhead_estimated_bytes": 24,
                "machine_operand_list_node_bytes_estimated": 1_000,
                "machine_condition_elements": 1,
                "machine_condition_list_node_bytes_estimated": 24,
                "machine_path_coordinate_elements": 2,
                "machine_ancilla_path_coordinate_list_node_bytes_estimated": 80,
                "machine_path_coordinate_list_node_bytes_estimated": 80,
                "machine_path_coordinate_list_node_bytes_included_in_total": True,
                "machine_destination_coordinate_fields": 1,
                "machine_destination_coordinate_bytes_estimated": 12,
                "machine_metadata_objects": 3,
                "machine_metadata_bytes_estimated": 24,
                "machine_predecessor_successor_container_bytes_estimated": 0,
                "machine_compile_info_bytes_estimated": 256,
                "machine_ir_pointer_bytes_estimated": 8,
                "machine_instruction_type_count": {"A": 2, "B": 1},
                "machine_instruction_type_object_bytes_estimated": {"A": 200, "B": 100},
                "machine_instruction_type_operand_list_node_bytes_estimated": {
                    "A": 800,
                    "B": 200,
                },
                "machine_instruction_type_ancilla_path_list_node_bytes_estimated": {
                    "A": 80,
                    "B": 0,
                },
                "machine_instruction_type_total_bytes_estimated": {"A": 1_000, "B": 300},
            },
        },
        {
            "stage": "routing_after_inverse_map_release",
            "vmrss_kb": 490_000,
            "mallinfo2_uordblks_kb": 440_000,
            "mallinfo2_fordblks_kb": 20_000,
            "extra": {
                "machine_inverse_map_entries": after_entries,
                "machine_inverse_map_bytes_estimated": 0 if after_entries == 0 else 120,
                "machine_inverse_map_valid_blocks": 0 if after_entries == 0 else 1,
                "machine_inverse_map_released_blocks": 1 if after_entries == 0 else 0,
            },
        },
        {"stage": "after_calc_info_with_topology", "vmrss_kb": peak - 10},
    ]
    return {
        "case": case,
        "variant": variant,
        "run_index": 1,
        "qret_peak_rss_kb": peak,
        "elapsed_seconds": elapsed,
        "compile_info_size_bytes": 100,
        "profile_rows": rows,
        "raw_resource_metrics": {k: v for k, v in metrics.items() if k != "compile_info_json"},
        "normalized_metrics": metrics,
    }


def test_variants_defaults_and_h6_absence() -> None:
    assert profile.VARIANTS["baseline"]["release_inverse_map"] == "0"
    assert profile.VARIANTS["inverse_map_release"]["release_inverse_map"] == "1"
    assert profile.DEFAULT_RUNS["h4_4th_new2"]["baseline"] == 1
    assert profile.DEFAULT_RUNS["h5_4th_new2"]["inverse_map_release"] == 2
    assert "h6_4th_new2" not in profile.DEFAULT_RUNS


def test_invalid_release_env_value_is_rejected() -> None:
    assert profile._validate_release_value("0") == "0"
    assert profile._validate_release_value("1") == "1"
    with pytest.raises(ValueError):
        profile._validate_release_value("true")


def test_variant_env_sets_release_and_never_trim() -> None:
    env = {"QRET_DEP_GRAPH_IMPL": "compact", "QRET_RSS_DIAGNOSTIC_TRIM_STAGE": "both"}
    profile._variant_env(env, "inverse_map_release")

    assert env["QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING"] == "1"
    assert env["QRET_RSS_DIAGNOSTIC_TRIM_STAGE"] == "none"
    assert env["QRET_SUMMARY_TIME_SERIES_IMPL"] == "legacy_timeseries"
    assert "QRET_DEP_GRAPH_IMPL" not in env


def test_stage_summary_reports_inverse_map_and_corrected_total() -> None:
    summary = profile._stage_summary(_result().get("profile_rows", []))
    before = summary["routing_before_inverse_map_release"]

    assert before["inverse_map_entries"] == 3
    assert before["machine_total_bytes"] == 3_000
    assert before["ancilla_path_bytes"] == 80
    assert before["operand_list_bytes"] == 1_000


def test_instruction_type_breakdown_sorts_by_total() -> None:
    extra = profile._extra_at_stage(
        _result().get("profile_rows", []),
        "routing_before_inverse_map_release",
    )
    rows = profile._instruction_type_breakdown(extra)

    assert [row["type"] for row in rows] == ["A", "B"]
    assert rows[0]["ancilla_path_bytes"] == 80


def test_metric_parity_ignores_compile_info_path() -> None:
    baseline = _result(variant="baseline")
    release = _result(variant="inverse_map_release", peak=620_000, after_entries=0)
    release["normalized_metrics"] = {
        **release["normalized_metrics"],  # type: ignore[index]
        "compile_info_json": "/tmp/b.json",
    }

    with profile._patched_base():
        comparisons = profile.base._metric_comparisons([baseline, release])

    assert profile._metric_parity(comparisons)


def test_production_decision_requires_consistent_peak_drop_and_elapsed() -> None:
    rows = [
        _result(variant="baseline", peak=640_000, elapsed=10.0),
        _result(variant="baseline", peak=641_000, elapsed=10.2),
        _result(variant="inverse_map_release", peak=620_000, elapsed=10.1, after_entries=0),
        _result(variant="inverse_map_release", peak=621_000, elapsed=10.0, after_entries=0),
    ]
    with profile._patched_base():
        comparisons = profile.base._metric_comparisons(rows)

    decision = profile._production_decision(rows, comparisons)

    assert decision["metrics_equal"] is True
    assert decision["consistent_peak_drop"] is True
    assert decision["passes"] is True


def test_run_profile_rejects_h6_case_before_execution(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        profile.run_profile(
            output_root=tmp_path / "out",
            report_path=tmp_path / "report.md",
            cache_root=tmp_path / "cache",
            build=False,
            cases=("h6_4th_new2",),
            batch_size=2,
            sample_interval_sec=0.02,
        )


def test_report_generation_mentions_h6_and_release(tmp_path: Path) -> None:
    report = tmp_path / "report.md"
    rows = [
        _result(variant="baseline", peak=640_000),
        _result(variant="inverse_map_release", peak=620_000, after_entries=0),
    ]
    with profile._patched_base():
        comparisons = profile.base._metric_comparisons(rows)
    profile._write_report(
        report,
        {
            "environment": {
                "evaluation_head": "head",
                "measurement_runtime_hashes": {
                    "qret_executable_hash": "exe",
                    "qret_core_library_hash": "lib",
                },
            },
            "build_provenance": {"build_requested": False},
            "results": rows,
            "comparisons": comparisons,
        },
    )

    text = report.read_text(encoding="utf-8")
    assert "# qret Inverse Map Memory Optimization" in text
    assert "H6 was not run" in text
    assert "routing_after_inverse_map_release" in text
