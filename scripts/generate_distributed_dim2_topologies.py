#!/usr/bin/env python3
"""Generate balanced two-plane DistributedDim2 topologies for H4 and H7."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import generate_logical_placement_topologies as placement  # noqa: E402


DEFAULT_GRID_MANIFEST = (
    REPO_ROOT
    / "configs"
    / "topologies"
    / "logical_grid_capacity_h4_h7"
    / "grid_capacity_manifest.json"
)
DEFAULT_OUTPUT_ROOT = (
    REPO_ROOT / "configs" / "topologies" / "distributed_dim2_h4_h7_4th"
)
MOLECULES = ("H4", "H7")
GRID_SIZE = (10, 10)
PLANE_ZS = (0, 2)
MAGIC_FACTORIES = {
    0: ((0, (0, 4)), (1, (0, 6))),
    2: ((2, (0, 4)), (3, (0, 6))),
}
ENTANGLEMENT_FACTORIES = {
    0: ((0, 1, (0, 0)),),
    2: ((1, 0, (0, 0)),),
}
QUBIT_COORD_POOL = (
    (4, 4),
    (4, 6),
    (6, 4),
    (6, 6),
    (3, 2),
    (3, 8),
    (7, 2),
    (7, 8),
    (8, 4),
    (8, 6),
)
ENTANGLEMENT_COORD = (0, 0)


EdgeWeights = Counter[tuple[int, int]]
Coord = tuple[int, int]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def _cut_weight(plane_zero: set[int], edges: EdgeWeights) -> int:
    return sum(
        int(weight)
        for (lhs, rhs), weight in edges.items()
        if (lhs in plane_zero) != (rhs in plane_zero)
    )


def _balanced_partition(
    num_qubits: int, edges: EdgeWeights, *, maximize: bool
) -> tuple[set[int], set[int], int]:
    plane_zero_size = num_qubits // 2
    candidates: list[tuple[int, tuple[int, ...]]] = []
    # Plane labels are symmetric. Pin q0 to z=0 for deterministic complements.
    for remainder in itertools.combinations(range(1, num_qubits), plane_zero_size - 1):
        plane_zero_tuple = (0, *remainder)
        plane_zero = set(plane_zero_tuple)
        candidates.append((_cut_weight(plane_zero, edges), plane_zero_tuple))
    if not candidates:
        raise ValueError("balanced partition requires at least two logical qubits")
    selected = max(candidates) if maximize else min(candidates)
    cut, plane_zero_tuple = selected
    plane_zero = set(plane_zero_tuple)
    plane_two = set(range(num_qubits)) - plane_zero
    return plane_zero, plane_two, int(cut)


def _placement_objective(
    mapping: Mapping[int, Coord],
    local_qubits: set[int],
    edges: EdgeWeights,
) -> int:
    total = 0
    for (lhs, rhs), weight in edges.items():
        lhs_local = lhs in local_qubits
        rhs_local = rhs in local_qubits
        if lhs_local and rhs_local:
            total += int(weight) * placement._manhattan(mapping[lhs], mapping[rhs])
        elif lhs_local:
            total += int(weight) * placement._manhattan(
                mapping[lhs], ENTANGLEMENT_COORD
            )
        elif rhs_local:
            total += int(weight) * placement._manhattan(
                mapping[rhs], ENTANGLEMENT_COORD
            )
    return total


def _place_qubits(local_qubits: set[int], edges: EdgeWeights) -> dict[int, Coord]:
    if len(local_qubits) > len(QUBIT_COORD_POOL):
        raise ValueError("not enough explicit coordinates for one plane")
    coordinates = list(QUBIT_COORD_POOL[: len(local_qubits)])
    degree = Counter[int]()
    cross_degree = Counter[int]()
    for (lhs, rhs), weight in edges.items():
        degree[lhs] += int(weight)
        degree[rhs] += int(weight)
        if (lhs in local_qubits) != (rhs in local_qubits):
            cross_degree[lhs] += int(weight)
            cross_degree[rhs] += int(weight)
    ranked_qubits = sorted(
        local_qubits,
        key=lambda qubit: (-cross_degree[qubit], -degree[qubit], qubit),
    )
    ranked_coordinates = sorted(
        coordinates,
        key=lambda coord: (
            placement._manhattan(coord, ENTANGLEMENT_COORD),
            sum(placement._manhattan(coord, other) for other in coordinates),
            coord,
        ),
    )
    mapping = dict(zip(ranked_qubits, ranked_coordinates, strict=True))
    ordered_qubits = sorted(local_qubits)
    while True:
        current = _placement_objective(mapping, local_qubits, edges)
        best = current
        best_pair: tuple[int, int] | None = None
        for index, lhs in enumerate(ordered_qubits):
            for rhs in ordered_qubits[index + 1 :]:
                mapping[lhs], mapping[rhs] = mapping[rhs], mapping[lhs]
                candidate = _placement_objective(mapping, local_qubits, edges)
                mapping[lhs], mapping[rhs] = mapping[rhs], mapping[lhs]
                if candidate < best:
                    best = candidate
                    best_pair = (lhs, rhs)
        if best_pair is None:
            break
        lhs, rhs = best_pair
        mapping[lhs], mapping[rhs] = mapping[rhs], mapping[lhs]
    return mapping


def _plane_payload(z: int, mapping: Mapping[int, Coord]) -> dict[str, Any]:
    return {
        "type": "plane",
        "coord": [GRID_SIZE[0], GRID_SIZE[1], z],
        "magic_factory": [
            {"symbol": symbol, "coord": list(coord)}
            for symbol, coord in MAGIC_FACTORIES[z]
        ],
        "entanglement_factory": [
            {"symbol": symbol, "pair": pair, "coord": list(coord)}
            for symbol, pair, coord in ENTANGLEMENT_FACTORIES[z]
        ],
        "qubit": [
            {"symbol": qubit, "coord": list(mapping[qubit])}
            for qubit in sorted(mapping)
        ],
    }


def _validate_payload(payload: Mapping[str, Any], num_qubits: int) -> None:
    grids = payload.get("grids", [])
    if len(grids) != 2:
        raise ValueError("DistributedDim2 topology must contain two planes")
    qubits: set[int] = set()
    magic_symbols: set[int] = set()
    entanglement_pairs: dict[int, int] = {}
    for plane in grids:
        width, height, z = (int(value) for value in plane["coord"])
        if (width, height) != GRID_SIZE or z not in PLANE_ZS:
            raise ValueError("unexpected plane dimensions or z coordinate")
        occupied: set[Coord] = set()
        for key in ("magic_factory", "entanglement_factory", "qubit"):
            for item in plane.get(key, []):
                coord = tuple(int(value) for value in item["coord"])
                if not (0 <= coord[0] < width and 0 <= coord[1] < height):
                    raise ValueError("topology coordinate is outside its plane")
                if coord in occupied:
                    raise ValueError("topology contains overlapping coordinates")
                occupied.add(coord)
        qubits.update(int(item["symbol"]) for item in plane.get("qubit", []))
        magic_symbols.update(
            int(item["symbol"]) for item in plane.get("magic_factory", [])
        )
        for item in plane.get("entanglement_factory", []):
            entanglement_pairs[int(item["symbol"])] = int(item["pair"])
    if qubits != set(range(num_qubits)):
        raise ValueError("logical-qubit symbols are incomplete")
    if magic_symbols != set(range(4)):
        raise ValueError("magic-factory symbols are incomplete")
    if entanglement_pairs != {0: 1, 1: 0}:
        raise ValueError("expected one bidirectional entanglement-factory pair")


def _mapping_records(
    mappings: Mapping[int, Mapping[int, Coord]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for z in PLANE_ZS:
        for qubit in sorted(mappings[z]):
            records.append(
                {
                    "logical_qubit": qubit,
                    "plane_z": z,
                    "coord": list(mappings[z][qubit]),
                }
            )
    return records


def generate(grid_manifest_path: Path, output_root: Path) -> dict[str, Any]:
    grid_manifest = json.loads(grid_manifest_path.read_text(encoding="utf-8"))
    source_records = grid_manifest["grids"]["10x10"]["molecules"]
    output_root.mkdir(parents=True, exist_ok=True)
    variants: dict[str, Any] = {}
    molecules: dict[str, Any] = {}

    for molecule in MOLECULES:
        source = source_records[molecule]
        qasm_path = (REPO_ROOT / source["qasm_path"]).resolve()
        num_qubits, edges = placement._parse_qasm_interactions(qasm_path)
        partitions: dict[str, Any] = {}
        for partition_name, maximize in (("low_cut", False), ("high_cut", True)):
            plane_zero, plane_two, cut = _balanced_partition(
                num_qubits, edges, maximize=maximize
            )
            mappings = {
                0: _place_qubits(plane_zero, edges),
                2: _place_qubits(plane_two, edges),
            }
            payload = {
                "grids": [
                    _plane_payload(0, mappings[0]),
                    _plane_payload(2, mappings[2]),
                ]
            }
            _validate_payload(payload, num_qubits)
            name = f"{molecule.lower()}_{partition_name}"
            topology_path = output_root / f"{name}.yaml"
            topology_path.write_text(
                yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
            )
            local_objective = sum(
                _placement_objective(mappings[z], set(mappings[z]), edges)
                for z in PLANE_ZS
            )
            record = {
                "molecule": molecule,
                "partition": partition_name,
                "topology_path": _relative(topology_path),
                "topology_sha256": _sha256(topology_path),
                "logical_mapping": _mapping_records(mappings),
                "logical_qubits_by_plane": {
                    str(z): sorted(mappings[z]) for z in PLANE_ZS
                },
                "logical_qubit_count_by_plane": {
                    str(z): len(mappings[z]) for z in PLANE_ZS
                },
                "weighted_interplane_cnot_count": cut,
                "weighted_interplane_cnot_fraction": cut / sum(edges.values()),
                "weighted_local_and_endpoint_distance": local_objective,
                "magic_factory_count": 4,
                "entanglement_factory_endpoint_count": 2,
                "entanglement_link_count": 1,
                "total_logical_cells": 2 * GRID_SIZE[0] * GRID_SIZE[1],
                "usable_non_factory_cells": (2 * GRID_SIZE[0] * GRID_SIZE[1] - 4 - 2),
            }
            variants[name] = record
            partitions[partition_name] = record
        if (
            partitions["low_cut"]["weighted_interplane_cnot_count"]
            >= partitions["high_cut"]["weighted_interplane_cnot_count"]
        ):
            raise ValueError(f"partitions do not create a cut contrast for {molecule}")
        molecules[molecule] = {
            "num_logical_qubits": num_qubits,
            "qasm_path": _relative(qasm_path),
            "qasm_sha256": _sha256(qasm_path),
            "weighted_cnot_count": sum(edges.values()),
            "weighted_cnot_edge_count": len(edges),
            "partitions": {
                name: f"{molecule.lower()}_{name}" for name in ("low_cut", "high_cut")
            },
        }

    manifest = {
        "schema_version": "distributed_dim2_topology_v1",
        "pf_label": "4th(new_2)",
        "machine_type": "DistributedDim2",
        "plane_count": 2,
        "plane_size": list(GRID_SIZE),
        "plane_z_coordinates": list(PLANE_ZS),
        "total_logical_cells": 2 * GRID_SIZE[0] * GRID_SIZE[1],
        "magic_factory_count": 4,
        "entanglement_factory_endpoint_count": 2,
        "entanglement_link_count": 1,
        "usable_non_factory_cells": 2 * GRID_SIZE[0] * GRID_SIZE[1] - 4 - 2,
        "partition_conditions": ["low_cut", "high_cut"],
        "molecules": molecules,
        "variants": variants,
    }
    manifest_path = output_root / "distributed_dim2_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grid-manifest", type=Path, default=DEFAULT_GRID_MANIFEST)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    manifest = generate(
        args.grid_manifest.expanduser().resolve(),
        args.output_root.expanduser().resolve(),
    )
    for name, record in manifest["variants"].items():
        print(
            name,
            "cut=",
            record["weighted_interplane_cnot_count"],
            "fraction=",
            f"{record['weighted_interplane_cnot_fraction']:.4f}",
            "qubits=",
            record["logical_qubit_count_by_plane"],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
