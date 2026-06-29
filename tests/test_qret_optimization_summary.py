from __future__ import annotations

from pathlib import Path

import pytest

import scripts.benchmark_qret_optimization_summary as summary


def _result(
    case: str,
    variant: str,
    condition: str,
    run: int,
    *,
    elapsed: float,
    peak: int,
    tree: int,
    compile_info: int | None = 100,
) -> dict[str, object]:
    metrics = {
        "runtime": 1,
        "gate_count": 2,
        "gate_depth": 3,
        "magic_state_consumption_count": 4,
        "magic_state_consumption_depth": 5,
        "qubit_volume": 6,
        "num_physical_qubits": 7,
        "code_distance": 8,
    }
    return {
        "case": case,
        "variant": variant,
        "cache_condition": condition,
        "run_index": run,
        "elapsed_seconds": elapsed,
        "qret_peak_rss_kb": peak,
        "tree_peak_rss_kb": tree,
        "compile_info_size_bytes": compile_info,
        "largest_intermediate_file_bytes": None if compile_info is None else compile_info + 10,
        "total_intermediate_file_bytes": None if compile_info is None else compile_info + 20,
        "raw_resource_metrics": metrics,
        "normalized_metrics": metrics | {"compile_info_json": f"/tmp/{case}-{variant}.json"},
    }


def test_baseline_selection_marks_stable_pre_optimization() -> None:
    selected = summary._baseline_selection()["stable_pre_optimization_baseline"]

    assert selected["commit"] == summary.STABLE_PRE_OPTIMIZATION_BASELINE
    assert selected["selected"] is True


def test_validate_cases_rejects_h6_to_h9() -> None:
    assert summary._validate_cases(["h4_2nd", "h4_4th_new2", "h5_4th_new2"]) == (
        "h4_2nd",
        "h4_4th_new2",
        "h5_4th_new2",
    )
    for case in ("h6_4th_new2", "h7_4th_new2", "h8_4th_new2", "h9_4th_new2"):
        with pytest.raises(ValueError, match="H6/H7/H8/H9"):
            summary._validate_cases([case])


def test_variant_env_records_production_defaults(tmp_path: Path) -> None:
    env: dict[str, str] = {}
    summary._variant_env(env, "final", tmp_path / "rss.jsonl")

    assert env["QRET_MAGIC_PATH_STORAGE"] == "interned"
    assert env["QRET_DEP_GRAPH_IMPL"] == "compact"
    assert env["QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING"] == "1"
    assert env["QRET_INVERSE_MAP_CONSTRUCTION"] == "eager"
    assert env["QRET_INSTRUCTION_ALLOCATION"] == "legacy"
    assert env["QRET_PROFILE_HIGH_WATER"] == "1"


def test_percentage_variation_and_missing_metrics() -> None:
    assert summary._pct_reduction(200, 150) == 25.0
    assert summary._pct_reduction(0, 150) is None
    assert summary._variation_pct(90, 110, 100) == 20.0
    assert summary._variation_pct(None, 110, 100) is None


def test_aggregate_separates_cold_and_warm_and_handles_not_applicable() -> None:
    rows = [
        _result("h4_4th_new2", "baseline", "cold", 1, elapsed=10, peak=200, tree=300),
        _result("h4_4th_new2", "baseline", "cold", 2, elapsed=12, peak=220, tree=320),
        _result("h4_4th_new2", "baseline", "warm", 1, elapsed=9, peak=190, tree=290, compile_info=None),
    ]

    cold = summary._aggregate(rows, case="h4_4th_new2", variant="baseline", cache_condition="cold")
    warm = summary._aggregate(rows, case="h4_4th_new2", variant="baseline", cache_condition="warm")

    assert cold["runs"] == 2
    assert cold["median_elapsed_seconds"] == 11.0
    assert cold["elapsed_seconds_variation_pct"] == pytest.approx(18.1818, rel=1e-4)
    assert warm["median_compile_info_size_bytes"] is None


def test_comparison_table_uses_baseline_minus_final() -> None:
    rows = [
        _result("h5_4th_new2", "baseline", "cold", 1, elapsed=20, peak=500, tree=600, compile_info=1000),
        _result("h5_4th_new2", "final", "cold", 1, elapsed=10, peak=300, tree=400, compile_info=100),
    ]
    aggregates = {
        f"h5_4th_new2:{variant}:cold": summary._aggregate(
            rows,
            case="h5_4th_new2",
            variant=variant,
            cache_condition="cold",
        )
        for variant in ("baseline", "final")
    }

    table = summary._comparison_table(aggregates, case="h5_4th_new2", cache_condition="cold")
    peak = next(row for row in table if row["metric"] == "qret_peak_rss_kb")

    assert peak["absolute_difference"] == 200.0
    assert peak["percentage"] == 40.0


def test_semantic_validation_ignores_paths_and_times() -> None:
    rows = [
        _result("h4_2nd", "baseline", "cold", 1, elapsed=1, peak=10, tree=20),
        _result("h4_2nd", "final", "cold", 1, elapsed=2, peak=9, tree=19),
    ]
    rows[1]["normalized_metrics"] = dict(rows[1]["normalized_metrics"]) | {
        "compile_info_json": "/different/path.json",
        "execution_time_sec": 99.0,
    }

    semantic = summary._semantic_validation(rows)

    assert semantic["h4_2nd"]["raw_equal"] is True
    assert semantic["h4_2nd"]["normalized_equal"] is True


def test_report_and_small_json_generation(tmp_path: Path) -> None:
    rows = [
        _result("h4_2nd", "baseline", "cold", 1, elapsed=1, peak=10, tree=20),
        _result("h4_2nd", "final", "cold", 1, elapsed=1, peak=10, tree=20),
        _result("h4_4th_new2", "baseline", "cold", 1, elapsed=10, peak=200, tree=300),
        _result("h4_4th_new2", "final", "cold", 1, elapsed=8, peak=100, tree=200),
    ]
    aggregates = {
        f"h4_4th_new2:{variant}:cold": summary._aggregate(
            rows,
            case="h4_4th_new2",
            variant=variant,
            cache_condition="cold",
        )
        for variant in ("baseline", "final")
    }
    payload = {
        "environment": {"evaluation_head": "abc"},
        "aggregates": aggregates,
        "comparison_tables": {
            "h4_4th_new2:cold": summary._comparison_table(
                aggregates,
                case="h4_4th_new2",
                cache_condition="cold",
            )
        },
        "semantic_validation": summary._semantic_validation(rows),
        "production_optimizations": summary._optimization_inventory("rejected")[:1],
        "rejected_optimizations": summary._optimization_inventory("rejected")[-3:],
        "execution_limits": {"h6_executed": False},
        "limitations": ["H6-H9 were not executed"],
    }
    report = tmp_path / "report.md"

    summary._write_report(report, summary=payload)
    small = summary._small_summary(payload)

    text = report.read_text(encoding="utf-8")
    assert "## 21. Conclusion" in text
    assert "H6, H7, H8, and H9 were not executed" in text
    assert small["baseline_commit"] == summary.STABLE_PRE_OPTIMIZATION_BASELINE
    assert small["final_commit"] == "abc"
