from __future__ import annotations

from pathlib import Path

import pytest

import scripts.profile_qret_pre_routing_high_water as profile


def _row(stage: str, *, vmrss: int, uord: int | None = None) -> dict[str, object]:
    row: dict[str, object] = {
        "stage": stage,
        "vmrss_kb": vmrss,
        "vmhwm_kb": vmrss + 10,
        "vmsize_kb": vmrss + 100,
        "vmdata_kb": vmrss - 10,
        "rss_anon_kb": vmrss - 20,
        "rss_file_kb": 20,
        "ru_maxrss_kb": vmrss + 10,
    }
    if uord is not None:
        row["mallinfo2_uordblks_kb"] = uord
        row["mallinfo2_fordblks_kb"] = max(0, vmrss - uord)
    return row


def _result(case: str = "h5_4th_new2", variant: str = "eager") -> dict[str, object]:
    components = {
        "instruction_count": 2000,
        "instruction_object_bytes": 200_000,
        "operand_container_bytes": 100_000,
        "instruction_list_node_bytes": 50_000,
        "inverse_map_entries": 2000,
        "inverse_map_bytes": 80_000,
        "metadata_bytes": 32_000,
        "machine_total_bytes": 500_000,
    }
    return {
        "case": case,
        "variant": variant,
        "run_index": 1,
        "qret_peak_rss_kb": 500_000,
        "raw_resource_metrics": {"runtime": 1, "gate_count": 2},
        "normalized_metrics": {
            "runtime": 1,
            "gate_count": 2,
            "compile_info_json": f"/tmp/{case}-{variant}.json",
        },
        "profile_rows": [],
        "stage_timeline": profile._stage_timeline(
            [
                _row("process_start", vmrss=10, uord=5),
                _row("after_ir_json_parse", vmrss=100, uord=80),
                _row("during_machine_function_construction", vmrss=180, uord=160),
                _row("after_machine_function_construction", vmrss=220, uord=180),
                _row("routing_entry", vmrss=450_000, uord=300_000),
                _row("routing_before_inverse_map_release", vmrss=500_000, uord=390_000),
                _row("routing_after_inverse_map_release", vmrss=500_000, uord=300_000),
                _row("after_compile_info", vmrss=500_000, uord=310_000),
                _row("before_serialization", vmrss=500_000, uord=310_000),
                _row("after_serialization", vmrss=500_000, uord=310_000),
                _row("before_process_exit", vmrss=500_000, uord=1),
            ]
        ),
        "machine_components": components,
        "first_max_vmhwm_stage": "routing_before_inverse_map_release",
        "first_max_vmhwm_kb": 500_010,
        "first_max_vmrss_stage": "routing_before_inverse_map_release",
        "first_max_vmrss_kb": 500_000,
    }


def test_validate_rejects_h6_to_h9_by_name_and_chain_length() -> None:
    assert profile._validate_cases(["h4_4th_new2", "h5_4th_new2"]) == (
        "h4_4th_new2",
        "h5_4th_new2",
    )
    for case in ("h6_4th_new2", "h7_4th_new2", "h8_4th_new2", "h9_4th_new2"):
        with pytest.raises(ValueError, match="H6/H7/H8/H9"):
            profile._validate_cases([case])
    for length in (6, 7, 8, 9):
        with pytest.raises(ValueError, match="H6/H7/H8/H9"):
            profile._validate_chain_lengths([length])


def test_variant_env_sets_production_and_profile_switch(tmp_path: Path) -> None:
    env = {"QRET_MAGIC_PATH_PROFILE_JSON": "old"}
    profile._variant_env(env, "lazy", tmp_path / "profile.jsonl")

    assert env["QRET_MAGIC_PATH_STORAGE"] == "interned"
    assert env["QRET_SUMMARY_TIME_SERIES_IMPL"] == "legacy_timeseries"
    assert env["QRET_DEP_GRAPH_IMPL"] == "compact"
    assert env["QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING"] == "1"
    assert env["QRET_INVERSE_MAP_CONSTRUCTION"] == "lazy"
    assert env["QRET_PROFILE_HIGH_WATER"] == "1"
    assert env["QRET_RSS_DIAGNOSTIC_TRIM_STAGE"] == "none"
    assert "QRET_MAGIC_PATH_PROFILE_JSON" not in env

    profile._variant_env(env, "eager_profile_off", tmp_path / "profile.jsonl")
    assert "QRET_RSS_PROFILE_JSONL" not in env
    assert env["QRET_PROFILE_HIGH_WATER"] == "0"


def test_stage_timeline_maps_aliases_and_computes_rss_minus_uord() -> None:
    timeline = profile._stage_timeline(
        [
            _row("before_ir_file_read", vmrss=100, uord=40),
            _row("after_ir_file_read", vmrss=120, uord=50),
            _row("during_machine_function_construction", vmrss=180, uord=90),
            _row("during_machine_function_construction", vmrss=220, uord=100),
            _row("routing_after_inverse_map_release", vmrss=200, uord=80),
            _row("calc_info_without_topology_entry", vmrss=200, uord=90),
            _row("calc_info_with_topology_after_summary_stats_store", vmrss=200, uord=190),
        ]
    )
    by_stage = {row["logical_stage"]: row for row in timeline}

    assert by_stage["before_input_json_read"]["observed_stage"] == "before_ir_file_read"
    assert by_stage["during_machine_function_construction"]["vmrss_kb"] == 220
    assert by_stage["compile_info_peak"]["observed_stage"] == (
        "calc_info_with_topology_after_summary_stats_store"
    )
    assert by_stage["routing_after_inverse_map_release"]["vmrss_minus_uordblks_kb"] == 120


def test_metric_comparisons_ignore_paths_and_execution_time() -> None:
    baseline = _result("h4_4th_new2", "eager_profile_off")
    profiled = _result("h4_4th_new2", "eager")
    profiled["normalized_metrics"] = {
        "runtime": 1,
        "gate_count": 2,
        "execution_time_sec": 99,
        "compile_info_json": "/tmp/other.json",
    }
    baseline["normalized_metrics"] = {
        "runtime": 1,
        "gate_count": 2,
        "execution_time_sec": 1,
        "compile_info_json": "/tmp/base.json",
    }

    comparisons = profile._metric_comparisons([baseline, profiled])
    assert comparisons["h4_4th_new2:eager:run_1"]["raw"]["all_equal"] is True
    assert comparisons["h4_4th_new2:eager:run_1"]["normalized"]["all_equal"] is True


def test_process_tree_samples_are_bounded() -> None:
    rows = profile._BoundedSampleRows(max_rows=2)
    rows.append({"sample_index": 0})
    rows.append({"sample_index": 1})
    rows.append({"sample_index": 2})

    assert list(rows) == [{"sample_index": 0}, {"sample_index": 1}]
    assert rows.retention_summary() == {
        "process_tree_sample_retained_rows": 2,
        "process_tree_sample_dropped_rows": 1,
        "process_tree_sample_max_retained_rows": 2,
        "process_tree_sample_truncated": True,
    }


def test_hypotheses_and_h9_are_labeled() -> None:
    result = _result()
    hypotheses = {row["hypothesis"]: row for row in profile._hypothesis_evaluation(result)}
    h9 = profile._h9_estimates([_result("h4_4th_new2", "eager"), result])

    assert hypotheses["B"]["status"] == "supported"
    assert h9["observed"]["classification"] == "observed"
    assert h9["estimated"]["classification"] == "estimated"
    assert h9["theoretical"]["classification"] == "theoretical"
    assert set(h9["estimated"]["scenarios"]) == {"conservative", "central", "upper"}


def test_report_mentions_required_sections(tmp_path: Path) -> None:
    h4 = _result("h4_4th_new2", "eager_profile_off")
    h4_profile = _result("h4_4th_new2", "eager")
    h5 = _result("h5_4th_new2", "eager")
    h5_lazy = _result("h5_4th_new2", "lazy")
    h5_lazy["machine_components"] = {**h5_lazy["machine_components"], "inverse_map_entries": 0}
    h5_trim = _result("h5_4th_new2", "eager_trim_after_inverse_release")
    h5_trim["trim_diagnostics"] = {
        "routing_after_inverse_map_release": {
            "rss_drop_kb": 100,
            "uordblks_drop_kb": 0,
            "fordblks_drop_kb": 100,
        }
    }
    results = [h4, h4_profile, h5, h5_lazy, h5_trim]
    summary = {
        "results": results,
        "comparisons": profile._metric_comparisons(results),
        "candidate_ranking": profile._candidate_ranking(results),
        "h9_estimates": profile._h9_estimates(results),
    }
    report = tmp_path / "report.md"

    profile._write_report(report, summary=summary)
    text = report.read_text(encoding="utf-8")

    for heading in (
        "Execution Limits",
        "Instrumentation Design",
        "H5 Observed Memory Timeline",
        "Allocator Retention Analysis",
        "Hypothesis Evaluation",
        "Next Candidate Ranking",
    ):
        assert f"## {heading}" in text
    assert "H9 was not run" in text
