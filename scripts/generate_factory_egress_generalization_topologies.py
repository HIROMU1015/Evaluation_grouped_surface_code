#!/usr/bin/env python3
"""Generate H5/H6 topologies for the factory-egress generalization sweep."""

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
    REPO_ROOT / "configs" / "topologies" / "factory_egress_generalization_h5_h6_4th"
)
TRAPPED_FACTORY_COORD = (3, 3)


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


def _set_bans(plane: dict[str, Any], bans: list[tuple[int, int]]) -> None:
    if bans:
        plane["ban"] = [list(coord) for coord in sorted(bans)]
    else:
        plane.pop("ban", None)


def _validate(payload: Mapping[str, Any], expected_qubits: int) -> None:
    plane = egress._plane(payload)
    width, height = (int(value) for value in plane["coord"][:2])
    mapping = egress._mapping(plane)
    factories = egress._factories(plane)
    bans = egress._bans(plane)
    if set(mapping) != set(range(expected_qubits)):
        raise ValueError(f"expected logical qubits 0 through {expected_qubits - 1}")
    if set(factories) != set(range(4)):
        raise ValueError("expected magic factories 0 through 3")
    coordinates = list(mapping.values()) + list(factories.values()) + list(bans)
    if len(coordinates) != len(set(coordinates)):
        raise ValueError("topology contains overlapping qubits, factories, or bans")
    if any(not (0 <= x < width and 0 <= y < height) for x, y in coordinates):
        raise ValueError("topology contains an out-of-grid coordinate")


def _variants(
    molecule: str, baseline: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    variants: dict[str, dict[str, Any]] = {}

    def add(
        name: str,
        *,
        bans: list[tuple[int, int]] | None = None,
        moves: Mapping[int, tuple[int, int]] | None = None,
    ) -> None:
        payload = deepcopy(dict(baseline))
        plane = egress._plane(payload)
        mapping = egress._mapping(plane)
        mapping.update(moves or {})
        egress._set_mapping(plane, mapping)
        _set_bans(plane, bans or [])
        _validate(payload, len(mapping))
        variants[name] = payload

    if molecule == "H5":
        add("h5_egress_2_baseline")
        add("h5_egress_1_ban_left", bans=[(2, 3)])
        add("h5_egress_0_ban_both", bans=[(2, 3), (3, 2)])
        add("h5_control_remote_ban_1", bans=[(7, 7)])
        add("h5_control_remote_ban_2", bans=[(7, 7), (7, 5)])
    elif molecule == "H6":
        add("h6_egress_1_baseline")
        add("h6_egress_0_ban_down", bans=[(3, 2)])
        add("h6_control_remote_ban_1", bans=[(7, 7)])
        add("h6_egress_2_move_q0", moves={0: (2, 2)})
    else:
        raise ValueError(f"unsupported molecule: {molecule}")
    return variants


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
    source = grid_manifest["grids"]["8x8"]["molecules"]
    output_root.mkdir(parents=True, exist_ok=True)

    records: dict[str, Any] = {}
    molecules: dict[str, Any] = {}
    baseline_names = {
        "H5": "h5_egress_2_baseline",
        "H6": "h6_egress_1_baseline",
    }
    for molecule in ("H5", "H6"):
        source_record = source[molecule]
        baseline_path = (REPO_ROOT / source_record["topology_path"]).resolve()
        qasm_path = (REPO_ROOT / source_record["qasm_path"]).resolve()
        baseline = yaml.safe_load(baseline_path.read_text(encoding="utf-8"))
        if not isinstance(baseline, dict):
            raise ValueError(f"expected YAML mapping: {baseline_path}")
        expected_qubits = int(source_record["num_logical_qubits"])
        _validate(baseline, expected_qubits)
        parsed_qubits, edges = placement._parse_qasm_interactions(qasm_path)
        if parsed_qubits != expected_qubits:
            raise ValueError(
                f"{molecule} QASM has {parsed_qubits} qubits, expected {expected_qubits}"
            )

        molecule_records: dict[str, Any] = {}
        for name, payload in _variants(molecule, baseline).items():
            output_path = output_root / f"{name}.yaml"
            output_path.write_text(
                yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
            )
            plane = egress._plane(payload)
            mapping = egress._mapping(plane)
            factories = egress._factories(plane)
            bans = egress._bans(plane)
            free_by_symbol, free_by_coord = egress._free_neighbors(plane)
            cnot_distance = placement._mapping_objective(mapping, edges)
            nearest_distance, nearest_mean = _nearest_factory_distance(
                mapping, factories
            )
            record = {
                "molecule": molecule,
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
                "usable_non_factory_cell_count": 64 - len(factories) - len(bans),
                "initial_free_neighbors_by_factory_symbol": {
                    str(symbol): count
                    for symbol, count in sorted(free_by_symbol.items())
                },
                "initial_free_neighbors_by_factory_coordinate": free_by_coord,
                "trapped_coordinate_free_neighbors": free_by_coord["3,3"],
                "weighted_cnot_distance": cnot_distance,
                # Uniform logical-qubit weighting; retained names match the runner schema.
                "weighted_nearest_factory_distance": nearest_distance,
                "weighted_nearest_factory_distance_mean": nearest_mean,
            }
            molecule_records[name] = record
            records[name] = record

        baseline_record = molecule_records[baseline_names[molecule]]
        for record in molecule_records.values():
            record["weighted_cnot_distance_delta_vs_baseline"] = int(
                record["weighted_cnot_distance"]
            ) - int(baseline_record["weighted_cnot_distance"])
            record["weighted_nearest_factory_distance_delta_vs_baseline"] = int(
                record["weighted_nearest_factory_distance"]
            ) - int(baseline_record["weighted_nearest_factory_distance"])
        molecules[molecule] = {
            "baseline_case": baseline_names[molecule],
            "baseline_topology_path": _relative(baseline_path),
            "baseline_topology_sha256": _sha256(baseline_path),
            "qasm_path": _relative(qasm_path),
            "qasm_sha256": _sha256(qasm_path),
            "num_logical_qubits": expected_qubits,
            "variants": list(molecule_records),
        }

    manifest = {
        "schema_version": "factory_egress_generalization_topology_v1",
        "pf_label": "4th(new_2)",
        "grid_size": [8, 8],
        "trapped_factory_coordinate": list(TRAPPED_FACTORY_COORD),
        "interaction_source": "pre-synthesis efficient-controlled PF-step QASM CNOT counts",
        "nearest_factory_distance_weighting": "one uniform weight per logical qubit",
        "molecules": molecules,
        "variants": records,
    }
    manifest_path = output_root / "factory_egress_generalization_manifest.json"
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
            record["trapped_coordinate_free_neighbors"],
            "bans=",
            record["banned_cell_count"],
            "cnot_delta=",
            record["weighted_cnot_distance_delta_vs_baseline"],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
