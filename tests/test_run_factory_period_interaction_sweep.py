import pytest

from scripts import run_factory_period_interaction_sweep as sweep


def _row(count: int, period: int, runtime: int, distance: int = 15) -> dict:
    return {
        "molecule": "H4",
        "rotation_precision": 1e-5,
        "factory_count": count,
        "magic_generation_period": period,
        "runtime": runtime,
        "code_distance": distance,
        "qubit_volume": runtime * 10,
    }


def test_enrich_separates_main_effects_and_interaction() -> None:
    config = {
        "fixed_conditions": {
            "baseline_factory_count": 4,
            "baseline_magic_generation_period": 15,
        }
    }
    rows = [
        _row(3, 15, 110),
        _row(3, 30, 132),
        _row(4, 15, 100),
        _row(4, 30, 110),
    ]

    enriched = sweep._enrich(rows, config)
    by_key = {(row["factory_count"], row["magic_generation_period"]): row for row in enriched}

    assert by_key[(3, 15)]["factory_three_penalty_pct_at_same_period"] == pytest.approx(10)
    assert by_key[(3, 30)]["factory_three_penalty_pct_at_same_period"] == pytest.approx(20)
    assert by_key[(4, 30)]["period_30_penalty_pct_at_same_factory_count"] == pytest.approx(10)
    assert by_key[(3, 30)]["factory_period_interaction_percentage_points"] == pytest.approx(10)


def test_physical_runtime_ratio_includes_code_distance() -> None:
    assert sweep._physical_runtime_units(_row(4, 15, 100, 17)) == 1700
