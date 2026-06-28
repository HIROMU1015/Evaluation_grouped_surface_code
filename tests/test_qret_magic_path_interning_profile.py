from __future__ import annotations

from pathlib import Path

import pytest

import scripts.profile_qret_magic_path_interning as profile


def _mock_result(
    *,
    case: str,
    variant: str,
    peak: int,
    elapsed: float,
    machine_instructions: int,
    path_bytes: int,
) -> dict[str, object]:
    component_bytes = {
        "instruction_object": 1000 * machine_instructions,
        "operand_containers": 400 * machine_instructions,
        "path_storage": path_bytes,
        "instruction_list_nodes": 64 * machine_instructions,
        "inverse_map": 128 * machine_instructions,
        "metadata": 32 * machine_instructions,
        "routing_temporary": 300 * machine_instructions,
        "python_parent": 10_000,
    }
    return {
        "case": case,
        "variant": variant,
        "run_index": 1,
        "qret_peak_rss_kb": peak,
        "elapsed_seconds": elapsed,
        "machine_instructions": machine_instructions,
        "prepared_ir_instruction_count": machine_instructions // 2,
        "bytes_per_instruction_estimated": 2000.0,
        "raw_resource_metrics": {"runtime": 1, "gate_count": 2},
        "normalized_metrics": {
            "runtime": 1,
            "gate_count": 2,
            "compile_info_json": f"/tmp/{case}-{variant}.json",
        },
        "machine_type_counts": {
            "LATTICE_SURGERY_MAGIC": machine_instructions // 4,
            "CNOT": machine_instructions // 2,
        },
        "component_estimates": {
            key: {"classification": "estimated", "bytes": value}
            for key, value in component_bytes.items()
        },
        "machine_extra": {
            "magic_path_unique_interned_path_count": 10,
            "magic_path_intern_hit_rate_percent": 99.0,
        },
    }


def _mock_summary() -> dict[str, object]:
    results = [
        _mock_result(
            case="h4_4th_new2",
            variant="legacy",
            peak=500_000,
            elapsed=10.0,
            machine_instructions=1_000,
            path_bytes=2_000_000,
        ),
        _mock_result(
            case="h4_4th_new2",
            variant="candidate",
            peak=450_000,
            elapsed=10.1,
            machine_instructions=1_000,
            path_bytes=200_000,
        ),
        _mock_result(
            case="h5_4th_new2",
            variant="legacy",
            peak=900_000,
            elapsed=20.0,
            machine_instructions=2_000,
            path_bytes=5_000_000,
        ),
        _mock_result(
            case="h5_4th_new2",
            variant="legacy",
            peak=910_000,
            elapsed=20.2,
            machine_instructions=2_000,
            path_bytes=5_000_000,
        ),
        _mock_result(
            case="h5_4th_new2",
            variant="candidate",
            peak=820_000,
            elapsed=20.4,
            machine_instructions=2_000,
            path_bytes=500_000,
        ),
        _mock_result(
            case="h5_4th_new2",
            variant="candidate",
            peak=830_000,
            elapsed=20.5,
            machine_instructions=2_000,
            path_bytes=500_000,
        ),
    ]
    comparisons = profile._metric_comparisons(results)
    return {
        "results": results,
        "aggregates": [
            profile._aggregate(results, case=case, variant=variant)
            for case in profile.CASE_CHAIN_LENGTH
            for variant in profile.VARIANTS
        ],
        "comparisons": comparisons,
        "adoption_decision": profile._adoption_decision(results, comparisons),
    }


def test_validate_cases_rejects_h6_h7_h8_h9() -> None:
    assert profile._validate_cases(["h4_4th_new2", "h5_4th_new2"]) == (
        "h4_4th_new2",
        "h5_4th_new2",
    )
    for case in ("h6_4th_new2", "h7_4th_new2", "h8_4th_new2", "h9_4th_new2"):
        with pytest.raises(ValueError, match="H6/H7/H8/H9"):
            profile._validate_cases([case])


def test_variant_env_sets_exact_path_storage_only() -> None:
    env: dict[str, str] = {"QRET_MAGIC_PATH_PROFILE_JSON": "old"}
    profile._variant_env(env, "candidate")

    assert env["QRET_MAGIC_PATH_STORAGE"] == "interned"
    assert env["QRET_SUMMARY_TIME_SERIES_IMPL"] == "legacy_timeseries"
    assert env["QRET_DEP_GRAPH_IMPL"] == "compact"
    assert env["QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING"] == "1"
    assert env["QRET_RSS_DIAGNOSTIC_TRIM_STAGE"] == "none"
    assert env["QRET_PROFILE_MAGIC_PATHS"] == "0"
    assert "QRET_MAGIC_PATH_PROFILE_JSON" not in env


def test_adoption_decision_uses_h5_only_for_peak_and_elapsed() -> None:
    summary = _mock_summary()
    decision = summary["adoption_decision"]

    assert decision["h4_semantic_parity"] is True
    assert decision["h5_median_qret_peak_reduction_kb"] == 80_000
    assert decision["all_candidate_runs_below_baseline"] is True
    assert decision["elapsed_gate_3_percent"] is True
    assert decision["production_candidate_adopted_by_h5_measurement"] is True


def test_h9_estimates_are_labeled_and_model_only() -> None:
    summary = _mock_summary()
    summary["h9_estimates"] = profile._h9_estimates(summary)
    h9 = summary["h9_estimates"]

    assert h9["observed"]["classification"] == "observed"
    assert h9["estimated"]["classification"] == "estimated"
    assert h9["theoretical"]["classification"] == "theoretical"
    assert set(h9["estimated"]["scenarios"]) == {"conservative", "central", "upper"}
    assert "path_storage" in h9["estimated"]["scenarios"]["central"]["candidate"]["components"]


def test_reports_mention_h5_largest_and_no_h6_to_h9(tmp_path: Path) -> None:
    summary = _mock_summary()
    summary["h9_estimates"] = profile._h9_estimates(summary)
    phase_a = tmp_path / "phase_a.md"
    strategy = tmp_path / "strategy.md"

    profile._write_phase_a_report(phase_a, summary)
    profile._write_strategy_report(strategy, summary)

    phase_text = phase_a.read_text(encoding="utf-8")
    strategy_text = strategy.read_text(encoding="utf-8")
    for text in (phase_text, strategy_text):
        assert "largest measured case: `H5`" in text
        assert "H6 executed: `False`" in text
        assert "H7 executed: `False`" in text
        assert "H8 executed: `False`" in text
        assert "H9 executed: `False`" in text
        assert "estimated from observed H4/H5 values, not measured" in text
    assert "observed" in strategy_text
    assert "estimated" in strategy_text
    assert "theoretical" in strategy_text
