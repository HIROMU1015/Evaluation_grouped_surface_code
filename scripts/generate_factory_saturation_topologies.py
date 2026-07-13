#!/usr/bin/env python3
"""Generate fixed-budget H4-H6 topologies for factory-saturation sweeps."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
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
    REPO_ROOT / "configs" / "topologies" / "factory_saturation_h4_h6_4th"
)
FACTORY_BUDGET_COORDS = (
    (4, 3),
    (5, 3),
    (4, 4),
    (5, 4),
    (4, 5),
    (5, 5),
    (4, 6),
    (5, 6),
)
ACTIVE_COORDS = {
    4: ((4, 4), (5, 4), (4, 5), (5, 5)),
    6: ((4, 4), (5, 4), (4, 5), (5, 5), (4, 3), (5, 3)),
    8: (
        (4, 4),
        (5, 4),
        (4, 5),
        (5, 5),
        (4, 3),
        (5, 3),
        (4, 6),
        (5, 6),
    ),
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


def _set_factory_budget(plane: dict[str, Any], factory_count: int) -> None:
    active = ACTIVE_COORDS[factory_count]
    inactive = sorted(set(FACTORY_BUDGET_COORDS) - set(active))
    plane["magic_factory"] = [
        {"symbol": symbol, "coord": list(coord)} for symbol, coord in enumerate(active)
    ]
    if inactive:
        plane["ban"] = [list(coord) for coord in inactive]
    else:
        plane.pop("ban", None)


def _validate(
    payload: Mapping[str, Any], expected_qubits: int, factory_count: int
) -> None:
    plane = egress._plane(payload)
    width, height = (int(value) for value in plane["coord"][:2])
    mapping = egress._mapping(plane)
    factories = egress._factories(plane)
    bans = egress._bans(plane)
    if (width, height) != (10, 10):
        raise ValueError("factory-saturation sweep requires a 10x10 plane")
    if set(mapping) != set(range(expected_qubits)):
        raise ValueError("logical-qubit symbols are not contiguous")
    if set(factories) != set(range(factory_count)):
        raise ValueError("factory symbols are not contiguous")
    if set(factories.values()) | bans != set(FACTORY_BUDGET_COORDS):
        raise ValueError("active factory plus ban coordinates must preserve the budget")
    if set(factories.values()) & bans:
        raise ValueError("factory and ban coordinates overlap")
    coordinates = list(mapping.values()) + list(factories.values()) + list(bans)
    if len(coordinates) != len(set(coordinates)):
        raise ValueError("topology contains overlapping qubits, factories, or bans")
    if any(not (0 <= x < width and 0 <= y < height) for x, y in coordinates):
        raise ValueError("topology contains an out-of-grid coordinate")
    free_by_symbol, _free_by_coord = egress._free_neighbors(plane)
    if min(free_by_symbol.values()) < 1:
        raise ValueError("every active factory must have at least one free egress")


def _nearest_factory_distance(
    mapping: Mapping[int, tuple[int, int]],
    factories: Mapping[int, tuple[int, int]],
) -> tuple[int, float]:
    distances = [
        min(
            placement._manhattan(coord, factory_coord)
            for factory_coord in factories.values()
        )
        for coord in mapping.values()
    ]
    return sum(distances), sum(distances) / len(distances)


def generate(grid_manifest_path: Path, output_root: Path) -> dict[str, Any]:
    grid_manifest = json.loads(grid_manifest_path.read_text(encoding="utf-8"))
    grid_records = grid_manifest["grids"]["10x10"]["molecules"]
    output_root.mkdir(parents=True, exist_ok=True)

    variants: dict[str, Any] = {}
    molecules: dict[str, Any] = {}
    for molecule in ("H4", "H5", "H6"):
        source = grid_records[molecule]
        baseline_path = (REPO_ROOT / source["topology_path"]).resolve()
        qasm_path = (REPO_ROOT / source["qasm_path"]).resolve()
        baseline = yaml.safe_load(baseline_path.read_text(encoding="utf-8"))
        if not isinstance(baseline, dict):
            raise ValueError(f"expected YAML mapping: {baseline_path}")
        expected_qubits = int(source["num_logical_qubits"])
        parsed_qubits, edges = placement._parse_qasm_interactions(qasm_path)
        if parsed_qubits != expected_qubits:
            raise ValueError(
                f"{molecule} QASM has {parsed_qubits} qubits, expected {expected_qubits}"
            )

        records: list[dict[str, Any]] = []
        names: list[str] = []
        baseline_cnot: int | None = None
        baseline_nearest: int | None = None
        for factory_count in (4, 6, 8):
            payload = deepcopy(baseline)
            plane = egress._plane(payload)
            _set_factory_budget(plane, factory_count)
            _validate(payload, expected_qubits, factory_count)
            mapping = egress._mapping(plane)
            factories = egress._factories(plane)
            bans = egress._bans(plane)
            free_by_symbol, free_by_coord = egress._free_neighbors(plane)
            cnot_distance = placement._mapping_objective(mapping, edges)
            nearest_distance, nearest_mean = _nearest_factory_distance(
                mapping, factories
            )
            name = f"{molecule.lower()}_factory_count_{factory_count}"
            output_path = output_root / f"{name}.yaml"
            output_path.write_text(
                yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
            )
            record = {
                "molecule": molecule,
                "factory_count": factory_count,
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
                "factory_plus_ban_cell_count": len(factories) + len(bans),
                "usable_non_factory_cell_count": 100 - len(factories) - len(bans),
                "initial_free_neighbors_by_factory_symbol": {
                    str(symbol): count
                    for symbol, count in sorted(free_by_symbol.items())
                },
                "initial_free_neighbors_by_factory_coordinate": free_by_coord,
                "minimum_initial_free_neighbors": min(free_by_symbol.values()),
                "weighted_cnot_distance": cnot_distance,
                "weighted_nearest_factory_distance": nearest_distance,
                "weighted_nearest_factory_distance_mean": nearest_mean,
            }
            if factory_count == 4:
                baseline_cnot = cnot_distance
                baseline_nearest = nearest_distance
            records.append(record)
            variants[name] = record
            names.append(name)

        assert baseline_cnot is not None and baseline_nearest is not None
        for record in records:
            record["weighted_cnot_distance_delta_vs_four"] = (
                int(record["weighted_cnot_distance"]) - baseline_cnot
            )
            record["weighted_nearest_factory_distance_delta_vs_four"] = (
                int(record["weighted_nearest_factory_distance"]) - baseline_nearest
            )
        molecules[molecule] = {
            "baseline_case": f"{molecule.lower()}_factory_count_4",
            "baseline_topology_path": _relative(baseline_path),
            "baseline_topology_sha256": _sha256(baseline_path),
            "qasm_path": _relative(qasm_path),
            "qasm_sha256": _sha256(qasm_path),
            "num_logical_qubits": expected_qubits,
            "variants": names,
        }

    manifest = {
        "schema_version": "factory_saturation_topology_v1",
        "pf_label": "4th(new_2)",
        "grid_size": [10, 10],
        "factory_counts": [4, 6, 8],
        "factory_budget_coordinates": [list(coord) for coord in FACTORY_BUDGET_COORDS],
        "factory_budget_policy": "inactive factory coordinates become banned cells",
        "factory_activation_policy": "nested central block; symbols 0-3 remain fixed",
        "nearest_factory_distance_weighting": "one uniform weight per logical qubit",
        "molecules": molecules,
        "variants": variants,
    }
    manifest_path = output_root / "factory_saturation_manifest.json"
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
            "factories=",
            record["factory_count"],
            "min_egress=",
            record["minimum_initial_free_neighbors"],
            "usable=",
            record["usable_non_factory_cell_count"],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
