from pathlib import Path

import yaml

from scripts import generate_factory_egress_micro_topologies as egress


REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE = (
    REPO_ROOT
    / "configs"
    / "topologies"
    / "runtime_grid_threshold_h5_h7"
    / "h7_8x8_compact_interaction_aware.yaml"
)


def test_variants_open_only_the_requested_trapped_factory_exits() -> None:
    baseline = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))
    variants = egress._variants(baseline)

    expected = {
        "egress_0_baseline": 0,
        "egress_1_left": 1,
        "egress_1_down": 1,
        "egress_2_both": 2,
        "egress_0_symbol_rotate": 0,
    }
    for name, expected_count in expected.items():
        _by_symbol, by_coord = egress._free_neighbors(egress._plane(variants[name]))
        assert by_coord["3,3"] == expected_count

    assert egress._mapping(egress._plane(variants["egress_1_left"]))[1] == (1, 3)
    assert egress._mapping(egress._plane(variants["egress_1_down"]))[2] == (3, 1)
    both_mapping = egress._mapping(egress._plane(variants["egress_2_both"]))
    assert {qubit: both_mapping[qubit] for qubit in (1, 2)} == {
        1: (1, 3),
        2: (3, 1),
    }


def test_symbol_rotation_preserves_physical_geometry() -> None:
    baseline = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))
    variants = egress._variants(baseline)
    baseline_plane = egress._plane(variants["egress_0_baseline"])
    rotated_plane = egress._plane(variants["egress_0_symbol_rotate"])

    assert egress._mapping(rotated_plane) == egress._mapping(baseline_plane)
    assert set(egress._factories(rotated_plane).values()) == set(
        egress._factories(baseline_plane).values()
    )
    assert egress._factories(rotated_plane)[3] == (3, 3)
