from __future__ import annotations

from pathlib import Path

import pytest

import scripts.profile_qret_routing_live_memory as profile


def _result(
    *,
    case: str = "h5_4th_new2",
    variant: str = "baseline",
    peak: int = 600_000,
    elapsed: float = 10.0,
    profile_rows: list[dict[str, object]] | None = None,
    object_estimates: dict[str, object] | None = None,
    trim_diagnostics: dict[str, object] | None = None,
) -> dict[str, object]:
    metrics = {
        "runtime": 1,
        "runtime_without_topology": 1,
        "gate_count": 2,
        "gate_depth": 3,
        "estimated_execution_time_sec": 4.0,
        "compile_info_json": "/tmp/a.json",
    }
    return {
        "case": case,
        "variant": variant,
        "run_index": 1,
        "qret_peak_rss_kb": peak,
        "elapsed_seconds": elapsed,
        "max_rss_stage": "routing_before_temporary_destroy",
        "max_rss_stage_vmrss_kb": peak - 10,
        "profile_rows": profile_rows or [],
        "stage_memory_table": profile._stage_memory_table(profile_rows or []),
        "object_estimates": object_estimates or {},
        "trim_diagnostics": trim_diagnostics or {},
        "raw_resource_metrics": {k: v for k, v in metrics.items() if k != "compile_info_json"},
        "normalized_metrics": metrics,
        "missing_required_stages": [],
    }


def test_variants_cases_and_defaults_do_not_include_h6() -> None:
    assert set(profile.CASE_CHAIN_LENGTH) == {"h4_4th_new2", "h5_4th_new2"}
    assert "h6_4th_new2" not in profile.CASE_CHAIN_LENGTH
    assert profile.DEFAULT_RUNS["h4_4th_new2"]["baseline"] == 1
    assert profile.DEFAULT_RUNS["h5_4th_new2"]["baseline"] == 2
    assert profile.VARIANTS["baseline"]["trim_stage"] == "none"
    assert (
        profile.VARIANTS["trim_after_json_destroy"]["trim_stage"]
        == "after_json_dom_destroy"
    )


def test_invalid_trim_stage_is_rejected() -> None:
    with pytest.raises(ValueError):
        profile._validate_trim_stage("bad_stage")


def test_stage_memory_table_handles_missing_mallinfo_fields() -> None:
    rows = [
        {"stage": "before_ir_json_parse", "vmrss_kb": 100, "pss_kb": 90},
        {
            "stage": "after_ir_json_parse",
            "vmrss_kb": 180,
            "pss_kb": 170,
            "private_dirty_kb": 120,
            "mallinfo2_uordblks_kb": 30,
        },
        {"stage": "after_ir_json_parse", "vmrss_kb": 160, "pss_kb": 150},
    ]

    table = profile._stage_memory_table(rows)
    by_stage = {row["stage"]: row for row in table}

    assert by_stage["before_ir_json_parse"]["mallinfo2_uordblks_kb"] is None
    assert by_stage["after_ir_json_parse"]["vmrss_kb"] == 180
    assert by_stage["after_ir_json_parse"]["mallinfo2_fordblks_kb"] is None


def test_object_estimates_collect_json_machine_and_routing_stats() -> None:
    rows = [
        {
            "stage": "after_ir_json_parse",
            "extra": {
                "json_object_count": 10,
                "json_estimated_dynamic_payload_bytes": 1_000,
                "json_string_total_size": 200,
                "ir_file_size_bytes": 2_000,
                "json_estimate_is_exact": False,
            },
        },
        {
            "stage": "after_lowering",
            "extra": {
                "machine_instructions": 5,
                "machine_total_bytes_estimated": 3_000,
                "machine_metadata_bytes_estimated": 40,
                "machine_raw_string_live_capacity_bytes": 0,
            },
        },
        {
            "stage": "routing_before_temporary_destroy",
            "extra": {
                "routing_queue_nodes": 7,
                "routing_queue_total_bytes_estimated": 4_000,
                "routing_sim_total_bytes_estimated": 5_000,
                "routing_live_total_bytes_estimated": 12_000,
            },
        },
    ]

    estimates = profile._object_estimates(rows)

    assert estimates["json_dom"]["estimated_payload_bytes"] == 1_000
    assert estimates["machine_function"]["estimated_payload_bytes"] == 3_000
    assert estimates["routing_temporary"]["estimated_payload_bytes"] == 9_000
    assert estimates["routing_temporary"]["routing_live_bytes"] == 12_000


def test_trim_diagnostics_compute_rss_and_allocator_drops() -> None:
    rows = [
        {
            "stage": "diagnostic_trim_before_after_json_dom_destroy",
            "vmrss_kb": 500,
            "mallinfo2_uordblks_kb": 300,
            "mallinfo2_fordblks_kb": 100,
        },
        {
            "stage": "diagnostic_trim_after_after_json_dom_destroy",
            "vmrss_kb": 420,
            "mallinfo2_uordblks_kb": 280,
            "mallinfo2_fordblks_kb": 10,
            "extra": {"malloc_trim_elapsed_sec": 0.01},
        },
    ]

    diagnostics = profile._trim_diagnostics(rows, "after_json_dom_destroy")

    assert diagnostics["after_json_dom_destroy"]["rss_drop_kb"] == 80
    assert diagnostics["after_json_dom_destroy"]["uordblks_drop_kb"] == 20
    assert diagnostics["after_json_dom_destroy"]["fordblks_drop_kb"] == 90
    assert diagnostics["after_json_dom_destroy"]["elapsed_sec"] == 0.01


def test_runtime_hash_comparison_and_change_detection() -> None:
    baseline = {
        "qret_executable_hash": "exe",
        "qret_core_library_path": "/tmp/libqret-core.so",
        "qret_core_library_hash": "lib",
    }
    same = dict(baseline)
    changed = dict(baseline, qret_core_library_hash="other")

    assert profile._hashes_equal(baseline, same)
    assert not profile._hashes_equal(baseline, changed)
    profile._ensure_runtime_hash_stable(baseline, same)
    with pytest.raises(RuntimeError):
        profile._ensure_runtime_hash_stable(baseline, changed)


def test_metric_comparisons_ignore_compile_info_path_for_normalized_metrics() -> None:
    baseline = _result(variant="baseline")
    trim = _result(variant="trim_after_json_destroy")
    trim["normalized_metrics"] = {
        **trim["normalized_metrics"],  # type: ignore[index]
        "compile_info_json": "/tmp/b.json",
    }

    comparisons = profile._metric_comparisons([baseline, trim])
    comparison = comparisons["h5_4th_new2:trim_after_json_destroy:run_1"]

    assert comparison["raw"]["all_equal"]
    assert comparison["normalized"]["all_equal"]


def test_both_trim_variant_runs_only_when_both_single_trim_drops_are_material() -> None:
    assert not profile._should_run_both_trim(
        [
            _result(
                variant="trim_after_json_destroy",
                trim_diagnostics={
                    "after_json_dom_destroy": {"rss_drop_kb": profile.BOTH_TRIM_GATE_KB}
                },
            ),
            _result(
                variant="trim_after_routing_temporary_destroy",
                trim_diagnostics={
                    "after_routing_temporary_destroy": {
                        "rss_drop_kb": profile.BOTH_TRIM_GATE_KB - 1
                    }
                },
            ),
        ]
    )
    assert profile._should_run_both_trim(
        [
            _result(
                variant="trim_after_json_destroy",
                trim_diagnostics={
                    "after_json_dom_destroy": {"rss_drop_kb": profile.BOTH_TRIM_GATE_KB}
                },
            ),
            _result(
                variant="trim_after_routing_temporary_destroy",
                trim_diagnostics={
                    "after_routing_temporary_destroy": {
                        "rss_drop_kb": profile.BOTH_TRIM_GATE_KB
                    }
                },
            ),
        ]
    )


def test_candidate_gate_supports_100mb_10_percent_and_150mb_live_rules() -> None:
    estimates = {
        "json_dom": {"estimated_payload_bytes": 1_000},
        "machine_function": {"estimated_payload_bytes": 160 * profile.ONE_MB},
        "routing_temporary": {"estimated_payload_bytes": 1_000},
    }
    rows = [
        _result(variant="baseline", peak=500_000, object_estimates=estimates),
        _result(
            variant="trim_after_json_destroy",
            peak=430_000,
            trim_diagnostics={"after_json_dom_destroy": {"rss_drop_kb": 60_000}},
        ),
        _result(
            variant="trim_after_routing_temporary_destroy",
            peak=380_000,
            trim_diagnostics={
                "after_routing_temporary_destroy": {"rss_drop_kb": 120_000}
            },
        ),
    ]

    ranking = profile._candidate_ranking(rows)
    by_name = {row["candidate"]: row for row in ranking}

    assert by_name["JSON DOM allocator retention"]["passes_gate"] is True
    assert by_name["MachineFunction live object"]["passes_gate"] is True
    assert by_name["routing temporary allocator retention"]["passes_gate"] is True
    assert by_name["MachineFunction live object"]["priority"] == "proposal_only"


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


def test_report_generation_mentions_h6_absence_and_candidates(tmp_path: Path) -> None:
    report = tmp_path / "report.md"
    rows = [
        _result(
            variant="baseline",
            profile_rows=[
                {
                    "stage": "after_ir_json_parse",
                    "vmrss_kb": 100,
                    "pss_kb": 90,
                    "private_dirty_kb": 80,
                    "mallinfo2_uordblks_kb": 40,
                    "mallinfo2_fordblks_kb": 5,
                }
            ],
            object_estimates={
                "json_dom": {
                    "count": 2,
                    "estimated_payload_bytes": 1_000,
                    "file_size_bytes": 2_000,
                },
                "machine_function": {
                    "count": 3,
                    "estimated_payload_bytes": 3_000,
                    "metadata_bytes": 100,
                    "raw_string_bytes": 0,
                },
                "routing_temporary": {
                    "count": 4,
                    "estimated_payload_bytes": 4_000,
                },
            },
        )
    ]
    candidates = profile._candidate_ranking(rows)

    profile._write_report(
        report,
        environment={
            "evaluation_head": "head",
            "measurement_runtime_hashes": {
                "qret_executable_hash": "exe",
                "qret_core_library_hash": "lib",
            },
            "compiler": "c++",
            "allocator": "glibc",
            "meminfo": {"MemTotal": 1, "SwapTotal": 0},
            "disk_free_bytes": 10,
            "output_root": str(tmp_path),
        },
        build_provenance={"build_requested": False},
        results=rows,
        comparisons={},
        candidate_ranking=candidates,
        both_trim_run=False,
    )

    text = report.read_text(encoding="utf-8")
    assert "# qret Routing Live Memory Profile" in text
    assert "H6 was not run" in text
    assert "Candidate Ranking" in text
    assert "production optimization implemented: `False`" in text
