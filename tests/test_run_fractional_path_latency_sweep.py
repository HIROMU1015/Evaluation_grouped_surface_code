from scripts import run_fractional_path_latency_sweep as sweep


def _row(condition: str, model: str, runtime: int, distance: int) -> dict:
    return {
        "molecule": "H4",
        "rotation_precision": 1e-5,
        "diagnostic_family": "placement",
        "diagnostic_condition": condition,
        "path_latency_model": model,
        "runtime": runtime,
        "code_distance": 15,
        "qubit_volume": runtime * 10,
        "weighted_cnot_distance": distance,
    }


def test_config_builds_expected_screening_and_replication_cases() -> None:
    config = sweep.factory._load_config(sweep.DEFAULT_CONFIG)
    cases = sweep._cases(config)

    assert len(cases) == 120
    assert sum(case.molecule == "H4" for case in cases) == 48
    assert sum(case.molecule in {"H5", "H6"} for case in cases) == 72
    assert len({_case_name for _case_name in map(sweep._case_name, cases)}) == 120
    assert sum(case.stage == "screening" for case in cases) == 48
    assert sum(case.stage == "replication" for case in cases) == 72


def test_intermediate_topology_metrics_are_strictly_ordered() -> None:
    config = sweep.factory._load_config(sweep.DEFAULT_CONFIG)
    placement = sweep.routing._load_json(
        sweep.factory._resolve(config["placement_manifest"])
    )
    routing = sweep.routing._load_json(
        sweep.factory._resolve(config["routing_manifest"])
    )

    for molecule in ("H4", "H5", "H6"):
        for family, conditions in {
            "placement": ("compact", "intermediate", "perimeter"),
            "routing": ("remote", "moderate", "choke"),
        }.items():
            distances = []
            for condition in conditions:
                case = sweep.Case(
                    "test", molecule, 1e-5, family, condition, "fixed", 0, 1
                )
                distances.append(
                    sweep._topology_record(placement, routing, case)[
                        "weighted_cnot_distance"
                    ]
                )
            assert distances[0] < distances[1] < distances[2]


def test_enrich_records_runtime_monotonicity_and_relative_changes() -> None:
    config = {
        "fixed_latency_model": "fixed",
        "families": {
            "placement": {
                "reference": "compact",
                "conditions": ["compact", "intermediate", "perimeter"],
            }
        },
    }
    rows = [
        _row("compact", "fixed", 100, 10),
        _row("intermediate", "fixed", 100, 20),
        _row("perimeter", "fixed", 100, 30),
        _row("compact", "half", 120, 10),
        _row("intermediate", "half", 132, 20),
        _row("perimeter", "half", 180, 30),
    ]

    enriched = sweep._enrich(rows, config)
    perimeter = next(
        row
        for row in enriched
        if row["diagnostic_condition"] == "perimeter"
        and row["path_latency_model"] == "half"
    )

    assert perimeter["runtime_change_pct_vs_family_reference"] == 50
    assert perimeter["runtime_change_pct_vs_fixed_same_topology"] == 80
    assert perimeter["runtime_monotonic_non_decreasing"] is True
    assert perimeter["physical_runtime_monotonic_non_decreasing"] is True
    assert perimeter["architecture_metric_monotonic_non_decreasing"] is True


def test_attach_unconstrained_comparison_uses_matching_case() -> None:
    constrained = [_row("compact", "quarter", 125, 10)]
    unconstrained = [_row("compact", "quarter", 100, 10)]

    compared = sweep._attach_unconstrained_comparison(constrained, unconstrained)

    assert compared[0]["runtime_change_pct_vs_unconstrained"] == 25
    assert compared[0]["qubit_volume_change_pct_vs_unconstrained"] == 25
