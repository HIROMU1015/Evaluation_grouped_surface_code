import pytest

from scripts import run_distance_sensitive_latency_sweep as sweep


def _row(condition: str, factor: int, runtime: int, distance: int = 15) -> dict:
    return {
        "molecule": "H4",
        "rotation_precision": 1e-5,
        "diagnostic_family": "placement",
        "diagnostic_condition": condition,
        "path_latency_factor": factor,
        "runtime": runtime,
        "diagnostic_path_latency_dependency_depth": runtime,
        "code_distance": distance,
        "qubit_volume": runtime * 10,
    }


def test_enrich_reports_stress_amplification() -> None:
    config = {"families": {"placement": {"reference": "compact"}}}
    rows = [
        _row("compact", 0, 100),
        _row("perimeter", 0, 101),
        _row("compact", 1, 120),
        _row("perimeter", 1, 132),
    ]

    enriched = sweep._enrich(rows, config)
    target = next(
        row
        for row in enriched
        if row["diagnostic_condition"] == "perimeter" and row["path_latency_factor"] == 1
    )

    assert target["dependency_depth_change_pct_vs_family_reference"] == pytest.approx(10)
    assert target["reference_penalty_amplification_percentage_points"] == pytest.approx(9)


def test_case_name_identifies_latency_model() -> None:
    assert sweep._case_name("H7", 1e-2, "routing", "choke", 1) == "h7_p1e-02_routing_choke_latency1"
