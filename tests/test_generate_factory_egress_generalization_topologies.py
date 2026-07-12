import yaml

from scripts import generate_factory_egress_generalization_topologies as generalization
from scripts import generate_factory_egress_micro_topologies as egress


def _load(molecule: str):
    path = (
        generalization.REPO_ROOT
        / "configs"
        / "topologies"
        / "logical_grid_capacity_h4_h7"
        / f"{molecule.lower()}_8x8_compact_interaction_aware.yaml"
    )
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_h5_bans_change_egress_without_changing_logical_mapping():
    variants = generalization._variants("H5", _load("H5"))
    expected_egress = {
        "h5_egress_2_baseline": 2,
        "h5_egress_1_ban_left": 1,
        "h5_egress_0_ban_both": 0,
        "h5_control_remote_ban_1": 2,
        "h5_control_remote_ban_2": 2,
    }
    baseline_mapping = egress._mapping(
        egress._plane(variants["h5_egress_2_baseline"])
    )
    for name, payload in variants.items():
        plane = egress._plane(payload)
        assert egress._mapping(plane) == baseline_mapping
        assert egress._free_neighbors(plane)[1]["3,3"] == expected_egress[name]

    assert len(egress._bans(egress._plane(variants["h5_egress_1_ban_left"]))) == len(
        egress._bans(egress._plane(variants["h5_control_remote_ban_1"]))
    )
    assert len(egress._bans(egress._plane(variants["h5_egress_0_ban_both"]))) == len(
        egress._bans(egress._plane(variants["h5_control_remote_ban_2"]))
    )


def test_h6_variants_isolate_ban_and_single_qubit_move():
    variants = generalization._variants("H6", _load("H6"))
    expected_egress = {
        "h6_egress_1_baseline": 1,
        "h6_egress_0_ban_down": 0,
        "h6_control_remote_ban_1": 1,
        "h6_egress_2_move_q0": 2,
    }
    baseline_mapping = egress._mapping(
        egress._plane(variants["h6_egress_1_baseline"])
    )
    for name, payload in variants.items():
        assert egress._free_neighbors(egress._plane(payload))[1]["3,3"] == expected_egress[name]

    for name in ("h6_egress_0_ban_down", "h6_control_remote_ban_1"):
        assert egress._mapping(egress._plane(variants[name])) == baseline_mapping
    moved_mapping = egress._mapping(egress._plane(variants["h6_egress_2_move_q0"]))
    assert moved_mapping[0] == (2, 2)
    assert {q for q in moved_mapping if moved_mapping[q] != baseline_mapping[q]} == {0}
