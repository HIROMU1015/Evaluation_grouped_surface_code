from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts import generate_distributed_dim2_topologies as distributed
from scripts import run_distributed_dim2_sweep as sweep


REPO_ROOT = Path(__file__).resolve().parents[1]
GRID_MANIFEST = (
    REPO_ROOT
    / "configs"
    / "topologies"
    / "logical_grid_capacity_h4_h7"
    / "grid_capacity_manifest.json"
)


def test_generate_balanced_distributed_dim2_topologies(tmp_path: Path) -> None:
    manifest = distributed.generate(GRID_MANIFEST, tmp_path)

    assert manifest["schema_version"] == "distributed_dim2_topology_v1"
    assert manifest["plane_count"] == 2
    assert manifest["total_logical_cells"] == 200
    assert manifest["usable_non_factory_cells"] == 194
    assert set(manifest["variants"]) == {
        "h4_low_cut",
        "h4_high_cut",
        "h7_low_cut",
        "h7_high_cut",
    }

    for molecule, num_qubits in (("H4", 9), ("H7", 15)):
        low = manifest["variants"][f"{molecule.lower()}_low_cut"]
        high = manifest["variants"][f"{molecule.lower()}_high_cut"]
        assert (
            low["weighted_interplane_cnot_count"]
            < high["weighted_interplane_cnot_count"]
        )
        for record in (low, high):
            counts = sorted(record["logical_qubit_count_by_plane"].values())
            assert counts == [num_qubits // 2, num_qubits - num_qubits // 2]
            topology = yaml.safe_load(
                (REPO_ROOT / record["topology_path"]).read_text(encoding="utf-8")
                if str(record["topology_path"]).startswith("configs/")
                else (tmp_path / Path(record["topology_path"]).name).read_text(
                    encoding="utf-8"
                )
            )
            assert len(topology["grids"]) == 2
            assert {grid["coord"][2] for grid in topology["grids"]} == {0, 2}
            assert sum(len(grid["magic_factory"]) for grid in topology["grids"]) == 4
            assert (
                sum(len(grid["entanglement_factory"]) for grid in topology["grids"])
                == 2
            )

    written = json.loads(
        (tmp_path / "distributed_dim2_manifest.json").read_text(encoding="utf-8")
    )
    assert written == manifest


def test_balanced_partition_is_deterministic() -> None:
    edges = distributed.EdgeWeights(
        {
            (0, 1): 5,
            (0, 2): 1,
            (0, 3): 2,
            (1, 2): 3,
            (1, 3): 1,
            (2, 3): 4,
        }
    )
    low = distributed._balanced_partition(4, edges, maximize=False)
    high = distributed._balanced_partition(4, edges, maximize=True)

    assert 0 in low[0]
    assert 0 in high[0]
    assert low[2] < high[2]


def test_select_distributed_dim2_cases_preserves_config_order() -> None:
    cases = [
        ("H4", 1e-5, "low_cut", 1),
        ("H4", 1e-5, "high_cut", 1),
        ("H7", 1e-2, "low_cut", 15),
    ]

    selected = sweep._select_cases(
        cases,
        ["h7_p1e-02_low_cut_e15", "h4_p1e-05_low_cut_e1"],
    )

    assert selected == [cases[0], cases[2]]


def test_select_distributed_dim2_cases_rejects_unknown_name() -> None:
    cases = [("H4", 1e-5, "low_cut", 1)]

    try:
        sweep._select_cases(cases, ["h7_p1e-02_low_cut_e1"])
    except ValueError as exc:
        assert "unknown --case" in str(exc)
    else:
        raise AssertionError("unknown case name was accepted")


def test_completed_distributed_dim2_rows_follow_case_order(tmp_path: Path) -> None:
    cases = [
        ("H4", 1e-5, "low_cut", 1),
        ("H7", 1e-2, "high_cut", 100),
    ]
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir()
    (checkpoint_dir / "h7_p1e-02_high_cut_e100.json").write_text(
        json.dumps({"case_name": "h7_p1e-02_high_cut_e100"}),
        encoding="utf-8",
    )
    (checkpoint_dir / "h4_p1e-05_low_cut_e1.json").write_text(
        json.dumps({"case_name": "h4_p1e-05_low_cut_e1"}),
        encoding="utf-8",
    )

    rows = sweep._completed_rows(tmp_path, cases)

    assert [row["case_name"] for row in rows] == [
        "h4_p1e-05_low_cut_e1",
        "h7_p1e-02_high_cut_e100",
    ]
