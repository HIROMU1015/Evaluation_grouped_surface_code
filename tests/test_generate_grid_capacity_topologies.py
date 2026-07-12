import importlib.util
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "generate_grid_capacity_topologies.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("generate_grid_capacity", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_center_factories_form_a_centered_two_by_two_block() -> None:
    module = _load_module()
    for size in (8, 10, 12):
        factories = module._center_factories((size, size))
        coords = {coord for _, coord in factories}
        lower = size // 2 - 1
        assert coords == {
            (lower, lower),
            (lower, lower + 1),
            (lower + 1, lower),
            (lower + 1, lower + 1),
        }


def test_capacity_coordinates_fit_h7_on_every_grid() -> None:
    module = _load_module()
    for size in (8, 10, 12):
        grid_size = (size, size)
        factories = module._center_factories(grid_size)
        coordinates, supplemental = module._capacity_coordinates(
            15,
            grid_size,
            factories,
        )
        factory_coords = {coord for _, coord in factories}
        assert len(coordinates) == 15
        assert len(set(coordinates)) == 15
        assert not set(coordinates) & factory_coords
        assert all(0 <= x < size and 0 <= y < size for x, y in coordinates)
        assert supplemental == (3 if size == 8 else 0)


def test_auto_payload_omits_explicit_qubits() -> None:
    module = _load_module()
    grid_size = (8, 8)
    payload = module._topology_payload(
        grid_size,
        module._center_factories(grid_size),
    )
    plane = payload["grids"][0]
    assert plane["coord"] == [8, 8, 0]
    assert "qubit" not in plane
