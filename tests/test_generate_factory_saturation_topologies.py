from pathlib import Path

import yaml

from scripts import generate_factory_saturation_topologies as generator


def _plane(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return payload["grids"][0]


def _coordinates(items: list[dict]) -> set[tuple[int, int]]:
    return {tuple(int(value) for value in item["coord"][:2]) for item in items}


def test_generate_fixed_eight_cell_budget(tmp_path: Path) -> None:
    manifest = generator.generate(generator.DEFAULT_GRID_MANIFEST, tmp_path)

    assert manifest["factory_counts"] == [4, 6, 8]
    assert len(manifest["variants"]) == 9
    budget = set(generator.FACTORY_BUDGET_COORDS)

    for molecule in ("H4", "H5", "H6"):
        logical_mappings = []
        active_sets = []
        for factory_count in (4, 6, 8):
            name = f"{molecule.lower()}_factory_count_{factory_count}"
            record = manifest["variants"][name]
            path = tmp_path / f"{name}.yaml"
            plane = _plane(path)
            factories = _coordinates(plane["magic_factory"])
            bans = {tuple(coord) for coord in plane.get("ban", [])}
            qubits = _coordinates(plane["qubit"])

            assert len(factories) == factory_count
            assert factories | bans == budget
            assert not factories & bans
            assert not qubits & budget
            assert record["factory_plus_ban_cell_count"] == 8
            assert record["usable_non_factory_cell_count"] == 92
            assert record["minimum_initial_free_neighbors"] >= 1
            assert record["topology_sha256"] == generator._sha256(path)
            logical_mappings.append(record["logical_mapping"])
            active_sets.append(factories)

        assert logical_mappings[0] == logical_mappings[1] == logical_mappings[2]
        assert active_sets[0] < active_sets[1] < active_sets[2]


def test_four_factory_symbols_and_coordinates_remain_stable(tmp_path: Path) -> None:
    manifest = generator.generate(generator.DEFAULT_GRID_MANIFEST, tmp_path)

    for molecule in ("H4", "H5", "H6"):
        symbol_maps = []
        for factory_count in (4, 6, 8):
            record = manifest["variants"][
                f"{molecule.lower()}_factory_count_{factory_count}"
            ]
            symbol_maps.append(
                {
                    int(item["symbol"]): tuple(item["coord"])
                    for item in record["magic_factories"]
                }
            )
        assert (
            {symbol: symbol_maps[0][symbol] for symbol in range(4)}
            == {symbol: symbol_maps[1][symbol] for symbol in range(4)}
            == {symbol: symbol_maps[2][symbol] for symbol in range(4)}
        )
