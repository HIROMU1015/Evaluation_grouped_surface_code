import importlib.util
from collections import Counter
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "generate_logical_placement_topologies.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("generate_logical_placements", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_interaction_aware_mapping_keeps_cells_and_improves_objective() -> None:
    module = _load_module()
    coordinates = module._compact_coordinates(5)
    edges = Counter({(0, 1): 100, (0, 2): 50, (3, 4): 1})
    numeric = module._numeric_mapping(coordinates)
    aware = module._interaction_aware_mapping(coordinates, edges)

    assert set(numeric.values()) == set(aware.values())
    assert module._mapping_objective(aware, edges) <= module._mapping_objective(
        numeric, edges
    )


def test_perimeter_coordinates_are_distinct_and_avoid_factories() -> None:
    module = _load_module()
    coordinates = module._perimeter_coordinates(15)
    factories = {coord for _, coord in module.MAGIC_FACTORIES}

    assert len(coordinates) == 15
    assert len(set(coordinates)) == 15
    assert not set(coordinates) & factories
