import yaml

from scripts import generate_accessible_factory_count_topologies as factory_count
from scripts import generate_factory_egress_micro_topologies as egress


def _load(molecule: str):
    path = (
        factory_count.REPO_ROOT
        / "configs"
        / "topologies"
        / "logical_grid_capacity_h4_h7"
        / f"{molecule.lower()}_10x10_compact_interaction_aware.yaml"
    )
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_factory_count_variants_preserve_mapping_and_cell_budget():
    for molecule in ("H4", "H5", "H6", "H7"):
        baseline = _load(molecule)
        baseline_mapping = egress._mapping(egress._plane(baseline))
        for count in (1, 2, 3, 4):
            payload = yaml.safe_load(yaml.safe_dump(baseline, sort_keys=False))
            plane = egress._plane(payload)
            factory_count._set_factory_budget(plane, count)
            factory_count._validate(payload, len(baseline_mapping), count)
            factories = egress._factories(plane)
            bans = egress._bans(plane)
            free_by_symbol, _free_by_coord = egress._free_neighbors(plane)

            assert egress._mapping(plane) == baseline_mapping
            assert len(factories) == count
            assert set(factories) == set(range(count))
            assert set(factories.values()) | bans == set(
                factory_count.FACTORY_BUDGET_COORDS
            )
            assert len(factories) + len(bans) == 4
            assert min(free_by_symbol.values()) == 2
