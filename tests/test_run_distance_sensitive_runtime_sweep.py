import pytest

from scripts import run_distance_sensitive_runtime_sweep as sweep


def _row(condition: str, factor: int, runtime: int, distance: int = 15) -> dict:
    return {
        "molecule": "H4",
        "rotation_precision": 1e-5,
        "diagnostic_family": "placement",
        "diagnostic_condition": condition,
        "path_latency_factor": factor,
        "runtime": runtime,
        "code_distance": distance,
        "qubit_volume": runtime * 10,
    }


def _proxy_row(condition: str, factor: int, runtime: int, depth: int) -> dict:
    return {
        **_row(condition, factor, runtime),
        "diagnostic_path_latency_dependency_depth": depth,
    }


def test_enrich_compares_full_runtime_with_proxy_penalty() -> None:
    config = {"families": {"placement": {"reference": "compact"}}}
    rows = [
        _row("compact", 0, 100),
        _row("perimeter", 0, 100),
        _row("compact", 1, 120),
        _row("perimeter", 1, 144),
    ]
    proxy_rows = [
        _proxy_row("compact", 0, 100, 100),
        _proxy_row("perimeter", 0, 100, 100),
        _proxy_row("compact", 1, 100, 120),
        _proxy_row("perimeter", 1, 100, 132),
    ]

    enriched = sweep._enrich(rows, config, proxy_rows)
    target = next(
        row
        for row in enriched
        if row["diagnostic_condition"] == "perimeter"
        and row["path_latency_factor"] == 1
    )

    assert target["runtime_change_pct_vs_family_reference"] == pytest.approx(20)
    assert target["proxy_depth_change_pct_vs_family_reference"] == pytest.approx(10)
    assert target["runtime_penalty_minus_proxy_percentage_points"] == pytest.approx(10)
    assert target["runtime_change_pct_vs_fixed_latency_same_topology"] == pytest.approx(44)


def test_factor_zero_parity_is_recorded() -> None:
    config = {"families": {"placement": {"reference": "compact"}}}
    rows = [_row("compact", 0, 100), _row("perimeter", 0, 101)]
    proxy_rows = [
        _proxy_row("compact", 0, 100, 100),
        _proxy_row("perimeter", 0, 101, 101),
    ]

    enriched = sweep._enrich(rows, config, proxy_rows)

    assert all(row["factor_zero_runtime_matches_previous_run"] for row in enriched)
    assert all(row["factor_zero_qubit_volume_matches_previous_run"] for row in enriched)
    assert all(row["factor_zero_runtime_within_tolerance"] for row in enriched)
    assert all(row["factor_zero_qubit_volume_within_tolerance"] for row in enriched)


def test_factor_zero_small_drift_is_compatibility_tolerated() -> None:
    config = {"families": {"placement": {"reference": "compact"}}}
    rows = [
        _row("compact", 0, 1_000_010),
        _row("perimeter", 0, 1_000_010),
    ]
    proxy_rows = [
        _proxy_row("compact", 0, 1_000_000, 100),
        _proxy_row("perimeter", 0, 1_000_000, 100),
    ]

    enriched = sweep._enrich(rows, config, proxy_rows)

    assert not any(row["factor_zero_runtime_matches_previous_run"] for row in enriched)
    assert all(row["factor_zero_runtime_delta_beats"] == 10 for row in enriched)
    assert all(row["factor_zero_runtime_within_tolerance"] for row in enriched)
    assert all(row["factor_zero_qubit_volume_within_tolerance"] for row in enriched)
