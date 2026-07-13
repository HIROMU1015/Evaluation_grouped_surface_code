import pytest

from scripts import analyze_dim2_physical_runtime as analysis


def test_relative_physical_runtime_includes_distance_change() -> None:
    baseline = {"runtime": "100", "code_distance": "15", "qubit_volume": "1000"}
    row = {"runtime": "90", "code_distance": "17", "qubit_volume": "950"}

    changes = analysis.relative_changes(row, baseline)

    assert changes["runtime_change_pct"] == pytest.approx(-10)
    assert changes["physical_runtime_change_pct"] == pytest.approx(2)
    assert changes["physical_minus_beat_percentage_points"] == pytest.approx(12)


def test_beat_and_factory_calibration() -> None:
    assert analysis.beat_duration_sec(15) == pytest.approx(15e-6)
    assert analysis.factory_throughput_hz(15, 15) == pytest.approx(1 / 225e-6)
