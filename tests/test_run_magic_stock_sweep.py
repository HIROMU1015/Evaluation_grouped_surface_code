import pytest

from scripts import run_magic_stock_sweep as stock


def _row(molecule: str, precision: float, value: int, runtime: int) -> dict:
    return {
        "molecule": molecule,
        "rotation_precision": precision,
        "maximum_magic_state_stock": value,
        "runtime": runtime,
        "qubit_volume": runtime * 10,
    }


def test_case_selection_preserves_config_order() -> None:
    cases = [("H4", 1e-5, 1), ("H4", 1e-5, 4), ("H5", 1e-2, 1)]
    selected = stock._select_cases(cases, ["h5_p1e-02_s1", "h4_p1e-05_s4"])

    assert selected == [("H4", 1e-5, 4), ("H5", 1e-2, 1)]


def test_enrich_compares_within_precision() -> None:
    config = {
        "maximum_magic_state_stocks": [1, 4, 10000],
        "comparison_policy": {"baseline_stock": 10000},
    }
    rows = [
        _row("H4", 1e-5, 1, 120),
        _row("H4", 1e-5, 4, 110),
        _row("H4", 1e-5, 10000, 100),
        _row("H4", 1e-2, 1, 60),
        _row("H4", 1e-2, 4, 55),
        _row("H4", 1e-2, 10000, 50),
    ]

    enriched = stock._enrich(rows, config)
    by_key = {
        (row["rotation_precision"], row["maximum_magic_state_stock"]): row
        for row in enriched
    }

    assert by_key[(1e-5, 1)]["runtime_change_pct_vs_stock_10000"] == pytest.approx(20.0)
    assert by_key[(1e-2, 1)]["runtime_change_pct_vs_stock_10000"] == pytest.approx(20.0)
    assert by_key[(1e-5, 4)][
        "runtime_reduction_pct_vs_previous_stock"
    ] == pytest.approx((1.0 - 110 / 120) * 100.0)
