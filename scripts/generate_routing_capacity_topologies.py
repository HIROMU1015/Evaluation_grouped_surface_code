#!/usr/bin/env python3
"""Generate fixed-budget H4-H7 topologies for routing-capacity diagnostics."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import deque
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import generate_factory_egress_micro_topologies as egress  # noqa: E402
from scripts import generate_logical_placement_topologies as placement  # noqa: E402


DEFAULT_GRID_MANIFEST = (
    REPO_ROOT
    / "configs"
    / "topologies"
    / "logical_grid_capacity_h4_h7"
    / "grid_capacity_manifest.json"
)
DEFAULT_OUTPUT_ROOT = (
    REPO_ROOT / "configs" / "topologies" / "routing_capacity_h4_h7_4th"
)
BAN_VARIANTS = {
    "remote_ban_control": {
        (0, 0),
        (1, 0),
        (8, 0),
        (9, 0),
        (0, 9),
        (1, 9),
        (8, 9),
        (9, 9),
    },
    "distributed_obstacles": {
        (1, 3),
        (3, 1),
        (6, 1),
        (8, 3),
        (1, 6),
        (3, 8),
        (6, 8),
        (8, 7),
    },
    # The openings at (3,4)/(3,5) preserve factory egress. The only
    # left-to-right routing corridor is (3,1), because the factory block
    # occupies the cells immediately to the right of the other openings.
    "central_choke": {
        (3, 0),
        (3, 2),
        (3, 3),
        (3, 6),
        (3, 7),
        (3, 8),
        (3, 9),
        (9, 9),
    },
}


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


def _bfs_distance(
    source: tuple[int, int],
    target: tuple[int, int],
    blocked: set[tuple[int, int]],
) -> int | None:
    queue = deque([(source, 0)])
    seen = {source}
    while queue:
        current, distance = queue.popleft()
        if current == target:
            return distance
        x, y = current
        for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            nx, ny = neighbor
            if (
                0 <= nx < 10
                and 0 <= ny < 10
                and neighbor not in blocked
                and neighbor not in seen
            ):
                seen.add(neighbor)
                queue.append((neighbor, distance + 1))
    return None


def _obstacle_aware_cnot_objective(
    mapping: Mapping[int, tuple[int, int]],
    factories: Mapping[int, tuple[int, int]],
    bans: set[tuple[int, int]],
    edges: Mapping[tuple[int, int], int],
) -> tuple[int, int]:
    qubit_coords = set(mapping.values())
    factory_coords = set(factories.values())
    weighted_total = 0
    max_distance = 0
    for (source_qubit, target_qubit), weight in edges.items():
        source = mapping[source_qubit]
        target = mapping[target_qubit]
        blocked = factory_coords | bans | (qubit_coords - {source, target})
        distance = _bfs_distance(source, target, blocked)
        if distance is None:
            raise ValueError(
                f"no static route between q{source_qubit} and q{target_qubit}"
            )
        weighted_total += int(weight) * distance
        max_distance = max(max_distance, distance)
    return weighted_total, max_distance


def _validate(
    payload: Mapping[str, Any],
    expected_qubits: int,
    edges: Mapping[tuple[int, int], int],
) -> tuple[int, int]:
    plane = egress._plane(payload)
    mapping = egress._mapping(plane)
    factories = egress._factories(plane)
    bans = egress._bans(plane)
    if tuple(int(value) for value in plane["coord"][:2]) != (10, 10):
        raise ValueError("routing-capacity sweep requires a 10x10 plane")
    if set(mapping) != set(range(expected_qubits)):
        raise ValueError("logical-qubit symbols are not contiguous")
    if set(factories) != set(range(4)):
        raise ValueError("expected four factory symbols")
    if len(bans) != 8:
        raise ValueError("each routing-capacity variant must ban eight cells")
    coordinates = list(mapping.values()) + list(factories.values()) + list(bans)
    if len(coordinates) != len(set(coordinates)):
        raise ValueError("topology contains overlapping qubits, factories, or bans")
    free_by_symbol, _free_by_coord = egress._free_neighbors(plane)
    if min(free_by_symbol.values()) < 2:
        raise ValueError("every factory must retain both external egress cells")
    return _obstacle_aware_cnot_objective(mapping, factories, bans, edges)


def generate(grid_manifest_path: Path, output_root: Path) -> dict[str, Any]:
    grid_manifest = json.loads(grid_manifest_path.read_text(encoding="utf-8"))
    grid_records = grid_manifest["grids"]["10x10"]["molecules"]
    output_root.mkdir(parents=True, exist_ok=True)
    records: dict[str, Any] = {}
    molecules: dict[str, Any] = {}

    for molecule in ("H4", "H5", "H6", "H7"):
        source = grid_records[molecule]
        baseline_path = (REPO_ROOT / source["topology_path"]).resolve()
        qasm_path = (REPO_ROOT / source["qasm_path"]).resolve()
        baseline = yaml.safe_load(baseline_path.read_text(encoding="utf-8"))
        expected_qubits = int(source["num_logical_qubits"])
        parsed_qubits, edges = placement._parse_qasm_interactions(qasm_path)
        if parsed_qubits != expected_qubits:
            raise ValueError(f"unexpected QASM qubit count for {molecule}")

        molecule_records: list[str] = []
        pending: list[dict[str, Any]] = []
        for variant, bans in BAN_VARIANTS.items():
            payload = deepcopy(baseline)
            plane = egress._plane(payload)
            plane["ban"] = [list(coord) for coord in sorted(bans)]
            objective, max_distance = _validate(payload, expected_qubits, edges)
            mapping = egress._mapping(plane)
            factories = egress._factories(plane)
            free_by_symbol, free_by_coord = egress._free_neighbors(plane)
            name = f"{molecule.lower()}_{variant}"
            output_path = output_root / f"{name}.yaml"
            output_path.write_text(
                yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
            )
            nearest_distances = [
                min(
                    placement._manhattan(coord, factory_coord)
                    for factory_coord in factories.values()
                )
                for coord in mapping.values()
            ]
            record = {
                "molecule": molecule,
                "routing_condition": variant,
                "topology_path": _relative(output_path),
                "topology_sha256": _sha256(output_path),
                "logical_mapping": [
                    {"logical_qubit": qubit, "coord": list(mapping[qubit])}
                    for qubit in sorted(mapping)
                ],
                "magic_factories": [
                    {"symbol": symbol, "coord": list(factories[symbol])}
                    for symbol in sorted(factories)
                ],
                "factory_coordinate_set": [
                    list(coord) for coord in sorted(factories.values())
                ],
                "banned_cells": [list(coord) for coord in sorted(bans)],
                "banned_cell_count": len(bans),
                "usable_non_factory_cell_count": 100 - len(factories) - len(bans),
                "initial_free_neighbors_by_factory_symbol": {
                    str(symbol): count
                    for symbol, count in sorted(free_by_symbol.items())
                },
                "initial_free_neighbors_by_factory_coordinate": free_by_coord,
                "minimum_initial_free_neighbors": min(free_by_symbol.values()),
                "trapped_coordinate_free_neighbors": min(free_by_symbol.values()),
                "weighted_cnot_distance": objective,
                "obstacle_aware_cnot_max_distance": max_distance,
                "weighted_nearest_factory_distance": sum(nearest_distances),
                "weighted_nearest_factory_distance_mean": sum(nearest_distances)
                / len(nearest_distances),
            }
            records[name] = record
            pending.append(record)
            molecule_records.append(name)

        control = next(
            record
            for record in pending
            if record["routing_condition"] == "remote_ban_control"
        )
        for record in pending:
            record["weighted_cnot_distance_delta_vs_baseline"] = int(
                record["weighted_cnot_distance"]
            ) - int(control["weighted_cnot_distance"])
            record["weighted_nearest_factory_distance_delta_vs_baseline"] = int(
                record["weighted_nearest_factory_distance"]
            ) - int(control["weighted_nearest_factory_distance"])
        molecules[molecule] = {
            "baseline_topology_path": _relative(baseline_path),
            "baseline_topology_sha256": _sha256(baseline_path),
            "qasm_path": _relative(qasm_path),
            "qasm_sha256": _sha256(qasm_path),
            "num_logical_qubits": expected_qubits,
            "variants": molecule_records,
        }

    manifest = {
        "schema_version": "routing_capacity_topology_v1",
        "pf_label": "4th(new_2)",
        "grid_size": [10, 10],
        "ban_count": 8,
        "usable_non_factory_cell_count": 88,
        "factory_count": 4,
        "minimum_factory_egress": 2,
        "routing_conditions": list(BAN_VARIANTS),
        "molecules": molecules,
        "variants": records,
    }
    manifest_path = output_root / "routing_capacity_manifest.json"
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
            "egress=",
            record["minimum_initial_free_neighbors"],
            "cnot_objective=",
            record["weighted_cnot_distance"],
            "delta=",
            record["weighted_cnot_distance_delta_vs_baseline"],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
