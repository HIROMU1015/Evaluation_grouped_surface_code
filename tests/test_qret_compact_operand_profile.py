from __future__ import annotations

from pathlib import Path

import pytest

import scripts.profile_qret_compact_operands as profile


def _profile_rows(*, peak_inverse_bytes: int = 1200, after_inverse_bytes: int = 0) -> list[dict[str, object]]:
    peak_extra = {
        "machine_total_bytes_estimated": 10_000,
        "machine_instructions": 100,
        "machine_instruction_object_bytes_estimated": 4000,
        "machine_instruction_list_node_bytes_estimated": 1600,
        "machine_operand_list_node_bytes_estimated": 2500,
        "machine_ancilla_path_coordinate_list_node_bytes_estimated": 400,
        "machine_inverse_map_entries": 100,
        "machine_inverse_map_bytes_estimated": peak_inverse_bytes,
        "machine_metadata_bytes_estimated": 800,
        "routing_queue_total_bytes_estimated": 900,
        "routing_sim_total_bytes_estimated": 700,
        "machine_instruction_type_count": {"TWIST": 80, "LATTICE_SURGERY_MAGIC": 20},
    }
    after_extra = dict(peak_extra)
    after_extra.update(
        {
            "machine_inverse_map_entries": 0 if after_inverse_bytes == 0 else 100,
            "machine_inverse_map_bytes_estimated": after_inverse_bytes,
            "routing_queue_total_bytes_estimated": 0,
            "routing_sim_total_bytes_estimated": 0,
        }
    )
    return [
        {"stage": "routing_main_loop_peak", "vmrss_kb": 2000, "extra": peak_extra},
        {"stage": "routing_before_inverse_map_release", "vmrss_kb": 1900, "extra": peak_extra},
        {"stage": "routing_after_inverse_map_release", "vmrss_kb": 1500, "extra": after_extra},
        {"stage": "routing_pass_exit", "vmrss_kb": 1500, "extra": after_extra},
    ]


def _mock_result(
    *,
    case: str,
    variant: str,
    peak: int,
    elapsed: float,
    machine_instructions: int,
    operand_bytes: int,
    run_index: int = 1,
) -> dict[str, object]:
    return {
        "case": case,
        "variant": variant,
        "run_index": run_index,
        "qret_peak_rss_kb": peak,
        "routing_peak_rss_kb": peak - 1000,
        "routing_exit_rss_kb": peak - 20_000,
        "elapsed_seconds": elapsed,
        "machine_instructions": machine_instructions,
        "prepared_ir_instruction_count": machine_instructions // 2,
        "bytes_per_instruction_estimated": 200.0,
        "raw_resource_metrics": {"runtime": 1, "gate_count": 2},
        "normalized_metrics": {
            "runtime": 1,
            "gate_count": 2,
            "compile_info_json": f"/tmp/{case}-{variant}.json",
        },
        "machine_type_counts": {
            "TWIST": machine_instructions // 2,
            "LATTICE_SURGERY_MAGIC": machine_instructions // 4,
        },
        "machine_extra": {
            "machine_instructions": machine_instructions,
            "machine_qtarget_list_node_bytes_estimated": operand_bytes // 2,
            "machine_cdepend_list_node_bytes_estimated": operand_bytes // 4,
            "machine_ccreate_list_node_bytes_estimated": operand_bytes // 8,
            "machine_mtarget_list_node_bytes_estimated": operand_bytes // 8,
            "magic_path_unique_interned_path_count": 10,
            "magic_path_intern_hit_rate_percent": 99.0,
        },
        "component_estimates": {
            "instruction_object": {"classification": "estimated", "bytes": machine_instructions * 100},
            "operand_containers": {"classification": "estimated", "bytes": operand_bytes},
            "path_storage": {"classification": "estimated", "bytes": machine_instructions * 10},
            "instruction_list_nodes": {"classification": "estimated", "bytes": machine_instructions * 20},
            "inverse_map": {"classification": "estimated", "bytes": machine_instructions * 30},
            "metadata": {"classification": "estimated", "bytes": machine_instructions * 5},
            "routing_temporary": {"classification": "estimated", "bytes": machine_instructions * 40},
            "python_parent": {"classification": "observed", "bytes": 1000},
        },
    }


def _mock_summary() -> dict[str, object]:
    results = [
        _mock_result(
            case="h4_4th_new2",
            variant="baseline",
            peak=200_000,
            elapsed=5.0,
            machine_instructions=1000,
            operand_bytes=60_000,
        ),
        _mock_result(
            case="h4_4th_new2",
            variant="candidate",
            peak=190_000,
            elapsed=5.0,
            machine_instructions=1000,
            operand_bytes=20_000,
        ),
        _mock_result(
            case="h5_4th_new2",
            variant="baseline",
            peak=500_000,
            elapsed=20.0,
            machine_instructions=2000,
            operand_bytes=120_000,
            run_index=1,
        ),
        _mock_result(
            case="h5_4th_new2",
            variant="baseline",
            peak=502_000,
            elapsed=20.2,
            machine_instructions=2000,
            operand_bytes=120_000,
            run_index=2,
        ),
        _mock_result(
            case="h5_4th_new2",
            variant="candidate",
            peak=470_000,
            elapsed=20.1,
            machine_instructions=2000,
            operand_bytes=60_000,
            run_index=1,
        ),
        _mock_result(
            case="h5_4th_new2",
            variant="candidate",
            peak=472_000,
            elapsed=20.3,
            machine_instructions=2000,
            operand_bytes=60_000,
            run_index=2,
        ),
    ]
    comparisons = profile._metric_comparisons(results)
    return {
        "environment": {
            "baseline_summary": "/tmp/phase0-summary.json",
            "measurement_runtime_hashes": {
                "qret_executable_hash": "qret-hash",
                "qret_core_library_hash": "lib-hash",
            },
        },
        "results": results,
        "aggregates": [
            profile._aggregate(results, case=case, variant=variant)
            for case in profile.magic_profile.CASE_CHAIN_LENGTH
            for variant in profile.VARIANTS
        ],
        "comparisons": comparisons,
        "adoption_decision": profile._adoption_decision(results, comparisons),
    }


def test_validate_cases_rejects_h6_to_h9_by_name_and_chain_length() -> None:
    assert profile._validate_cases([], []) == ("h4_4th_new2", "h5_4th_new2")
    for case in ("h6_4th_new2", "h7_4th_new2", "h8_4th_new2", "h9_4th_new2"):
        with pytest.raises(ValueError, match="H6/H7/H8/H9"):
            profile._validate_cases([case], [])
    for length in (6, 7, 8, 9):
        with pytest.raises(ValueError, match="H6/H7/H8/H9"):
            profile._validate_cases([], [length])


def test_baseline_rows_relabels_phase0_interned_candidate_rows() -> None:
    phase0 = {
        "results": [
            _mock_result(
                case="h4_4th_new2",
                variant="legacy",
                peak=250_000,
                elapsed=5.2,
                machine_instructions=1000,
                operand_bytes=90_000,
            ),
            _mock_result(
                case="h4_4th_new2",
                variant="candidate",
                peak=200_000,
                elapsed=5.0,
                machine_instructions=1000,
                operand_bytes=60_000,
            ),
        ]
    }
    rows = profile._baseline_rows(phase0, ["h4_4th_new2"])
    assert len(rows) == 1
    assert rows[0]["variant"] == "baseline"
    assert rows[0]["operand_storage_mode"] == "legacy_list_operands"


def test_stage_live_components_use_routing_peak_inverse_map() -> None:
    row = _mock_result(
        case="h5_4th_new2",
        variant="baseline",
        peak=500_000,
        elapsed=20.0,
        machine_instructions=100,
        operand_bytes=1000,
    )
    row["profile_rows"] = _profile_rows(peak_inverse_bytes=1200, after_inverse_bytes=0)
    enriched = profile._enrich_stage_live_components(row)

    assert enriched["routing_peak_component_estimates"]["inverse_map"]["bytes"] == 1200
    assert enriched["routing_after_inverse_map_release_extra"]["machine_inverse_map_bytes_estimated"] == 0
    assert enriched["component_estimates"]["routing_temporary"]["bytes"] == 1600


def test_adoption_decision_uses_h5_only_for_peak_gate() -> None:
    summary = _mock_summary()
    decision = summary["adoption_decision"]

    assert decision["h4_semantic_parity"] is True
    assert decision["h5_median_qret_peak_reduction_kb"] == 30_000
    assert decision["all_candidate_runs_below_baseline"] is True
    assert decision["elapsed_gate_3_percent"] is True
    assert decision["path_interning_stats_unchanged"] is True
    assert decision["production_candidate_adopted_by_h5_measurement"] is True


def test_h9_estimates_are_model_only_and_labeled() -> None:
    summary = _mock_summary()
    summary["h9_estimates"] = profile._h9_estimates(summary)
    h9 = summary["h9_estimates"]

    assert h9["observed"]["classification"] == "observed"
    assert h9["estimated"]["classification"] == "estimated"
    assert h9["theoretical"]["classification"] == "theoretical"
    assert set(h9["estimated"]["scenarios"]) == {"conservative", "central", "upper"}


def test_report_mentions_h5_largest_no_h6_to_h9_and_hashes(tmp_path: Path) -> None:
    summary = _mock_summary()
    summary["h9_estimates"] = profile._h9_estimates(summary)
    report = tmp_path / "compact.md"
    profile._write_report(report, summary)
    text = report.read_text(encoding="utf-8")

    assert "largest measured case: `H5`" in text
    assert "H6 executed: `False`" in text
    assert "H7 executed: `False`" in text
    assert "H8 executed: `False`" in text
    assert "H9 executed: `False`" in text
    assert "estimated from observed H4/H5 values, not measured" in text
    assert "qret-hash" in text
    assert "lib-hash" in text
