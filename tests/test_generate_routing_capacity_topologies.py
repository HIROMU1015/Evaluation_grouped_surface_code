import yaml

from scripts import generate_factory_egress_micro_topologies as egress
from scripts import generate_logical_placement_topologies as placement
from scripts import generate_routing_capacity_topologies as routing_capacity


def _source(molecule: str):
    topology = (
        routing_capacity.REPO_ROOT
        / "configs"
        / "topologies"
        / "logical_grid_capacity_h4_h7"
        / f"{molecule.lower()}_10x10_compact_interaction_aware.yaml"
    )
    manifest = __import__("json").loads(
        routing_capacity.DEFAULT_GRID_MANIFEST.read_text(encoding="utf-8")
    )
    qasm = routing_capacity.REPO_ROOT / manifest["grids"]["10x10"]["molecules"][molecule]["qasm_path"]
    return yaml.safe_load(topology.read_text(encoding="utf-8")), qasm


def test_routing_variants_preserve_budget_connectivity_and_factory_egress():
    for molecule in ("H4", "H5", "H6", "H7"):
        baseline, qasm = _source(molecule)
        mapping = egress._mapping(egress._plane(baseline))
        _num_qubits, edges = placement._parse_qasm_interactions(qasm)
        objectives = {}
        for name, bans in routing_capacity.BAN_VARIANTS.items():
            payload = yaml.safe_load(yaml.safe_dump(baseline, sort_keys=False))
            plane = egress._plane(payload)
            plane["ban"] = [list(coord) for coord in sorted(bans)]
            objective, _max_distance = routing_capacity._validate(
                payload, len(mapping), edges
            )
            objectives[name] = objective
            assert egress._mapping(plane) == mapping
            assert len(egress._bans(plane)) == 8
            assert min(egress._free_neighbors(plane)[0].values()) == 2

        assert objectives["central_choke"] > objectives["remote_ban_control"]
