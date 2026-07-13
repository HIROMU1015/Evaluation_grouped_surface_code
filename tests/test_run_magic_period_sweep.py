import pytest

from scripts import run_magic_period_sweep as period


def _row(molecule: str, value: int, runtime: int) -> dict:
    return {
        "molecule": molecule,
        "rotation_precision": 1e-2,
        "magic_generation_period": value,
        "runtime": runtime,
        "qubit_volume": runtime * 10,
    }


def _config() -> dict:
    return {
        "magic_generation_periods": [1, 4, 15, 30, 100],
        "comparison_policy": {
            "ideal_reference_period": 1,
            "standard_baseline_period": 15,
            "material_runtime_threshold_pct": 1.0,
            "h7_trigger_periods": [30, 100],
        },
    }


def test_case_selection_preserves_config_order() -> None:
    cases = [("H4", 1e-2, 1), ("H4", 1e-2, 15), ("H5", 1e-2, 100)]
    selected = period._select_cases(
        cases, ["h5_p1e-02_period100", "h4_p1e-02_period15"]
    )

    assert selected == [("H4", 1e-2, 15), ("H5", 1e-2, 100)]


def test_enrich_compares_with_ideal_and_standard_periods() -> None:
    rows = [
        _row("H4", 1, 100),
        _row("H4", 4, 102),
        _row("H4", 15, 105),
        _row("H4", 30, 110),
        _row("H4", 100, 150),
    ]

    enriched = period._enrich(rows, _config())
    by_period = {row["magic_generation_period"]: row for row in enriched}

    assert by_period[15]["runtime_change_pct_vs_period_1"] == pytest.approx(5.0)
    assert by_period[30]["runtime_change_pct_vs_period_15"] == pytest.approx(
        (110 / 105 - 1.0) * 100.0
    )
    assert by_period[4]["runtime_change_pct_vs_previous_period"] == pytest.approx(
        2.0
    )


def test_h7_trigger_uses_h6_material_slow_period_change() -> None:
    rows = [
        {
            **_row("H6", 30, 101),
            "runtime_change_pct_vs_period_15": 0.8,
        },
        {
            **_row("H6", 100, 120),
            "runtime_change_pct_vs_period_15": 1.2,
        },
    ]

    required, reasons = period._h7_required(rows, _config())

    assert required is True
    assert reasons == ["H6 period=100: +1.2000% vs period=15"]


def test_period_scaled_runtime_estimates_can_be_ignored_as_workload_fields() -> None:
    source = {
        field: 15 for field in period.factory.WORKLOAD_INVARIANT_FIELDS
    }
    observed = dict(source)
    observed["runtime_estimation_magic_state_consumption_count"] = 100
    observed["runtime_estimation_magic_state_consumption_depth"] = 90
    source["gate_count"] = observed["gate_count"] = 10
    source["gate_count_detail"] = observed["gate_count_detail"] = {
        "ALLOCATE_MAGIC_FACTORY": 4
    }
    observed["magic_factory_count"] = 4

    differences = period.factory._workload_differences(
        source,
        observed,
        4,
        ignored_fields=period.PERIOD_SCALED_RUNTIME_ESTIMATION_FIELDS,
    )

    assert differences == {}
