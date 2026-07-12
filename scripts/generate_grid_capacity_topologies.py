#!/usr/bin/env python3
"""Generate center-factory topologies for the logical-grid capacity sweep."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import generate_logical_placement_topologies as placement


DEFAULT_RESULTS = placement.DEFAULT_RESULTS
DEFAULT_CACHE_ROOT = placement.DEFAULT_CACHE_ROOT
DEFAULT_OUTPUT_ROOT = (
    REPO_ROOT / "configs" / "topologies" / "logical_grid_capacity_h4_h7"
)
GRID_SIZES = ((8, 8), (10, 10), (12, 12))


Coord = tuple[int, int]


def _center_factories(grid_size: tuple[int, int]) -> tuple[tuple[int, Coord], ...]:
    width, height = grid_size
    if width < 2 or height < 2:
        raise ValueError(f"Grid is too small for a 2x2 factory block: {grid_size}")
    x0 = width // 2 - 1
    y0 = height // 2 - 1
    return (
        (0, (x0, y0)),
        (1, (x0, y0 + 1)),
        (2, (x0 + 1, y0)),
        (3, (x0 + 1, y0 + 1)),
    )


def _soft_candidates(
    grid_size: tuple[int, int],
    factories: Iterable[tuple[int, Coord]],
) -> list[Coord]:
    width, height = grid_size
    factory_coords = {coord for _, coord in factories}
    places: set[Coord] = set()
    for x in range(width):
        for y in range(height):
            available = True
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    candidate = (x + dx, y + dy)
                    if not (0 <= candidate[0] < width and 0 <= candidate[1] < height):
                        continue
                    if candidate in factory_coords or candidate in places:
                        available = False
            if available:
                places.add((x, y))
    return sorted(places)


def _center_rank(coord: Coord, grid_size: tuple[int, int]) -> tuple[float, float, Coord]:
    center_x = 0.5 * (grid_size[0] - 1)
    center_y = 0.5 * (grid_size[1] - 1)
    return (
        (coord[0] - center_x) ** 2 + (coord[1] - center_y) ** 2,
        abs(coord[0] - center_x) + abs(coord[1] - center_y),
        coord,
    )


def _capacity_coordinates(
    num_qubits: int,
    grid_size: tuple[int, int],
    factories: Iterable[tuple[int, Coord]],
) -> tuple[list[Coord], int]:
    factory_coords = {coord for _, coord in factories}
    soft = sorted(
        _soft_candidates(grid_size, factories),
        key=lambda coord: _center_rank(coord, grid_size),
    )
    selected = soft[:num_qubits]
    supplemental_count = max(0, num_qubits - len(selected))

    while len(selected) < num_qubits:
        candidates = [
            (x, y)
            for x in range(grid_size[0])
            for y in range(grid_size[1])
            if (x, y) not in factory_coords and (x, y) not in selected
        ]
        if not candidates:
            raise ValueError(
                f"Not enough non-factory cells for {num_qubits} qubits on {grid_size}"
            )
        next_coord = min(
            candidates,
            key=lambda coord: (
                -min(placement._manhattan(coord, other) for other in selected),
                _center_rank(coord, grid_size),
            ),
        )
        selected.append(next_coord)

    return sorted(selected), supplemental_count


def _topology_payload(
    grid_size: tuple[int, int],
    factories: Iterable[tuple[int, Coord]],
    mapping: placement.MappingByQubit | None = None,
) -> dict[str, Any]:
    plane: dict[str, Any] = {
        "type": "plane",
        "coord": [grid_size[0], grid_size[1], 0],
        "magic_factory": [
            {"symbol": symbol, "coord": list(coord)} for symbol, coord in factories
        ],
    }
    if mapping is not None:
        plane["qubit"] = [
            {"symbol": qubit, "coord": list(mapping[qubit])}
            for qubit in sorted(mapping)
        ]
    return {"grids": [plane]}


def generate(
    results_path: Path,
    cache_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    qasm_paths = placement._discover_qasm_paths(results_path, cache_root)
    output_root.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "schema_version": "logical_grid_capacity_topology_v1",
        "interaction_source": "pre-synthesis efficient-controlled PF-step QASM CNOT counts",
        "grids": {},
    }

    parsed: dict[str, tuple[int, placement.EdgeWeights]] = {}
    for molecule in placement.MOLECULES:
        parsed[molecule] = placement._parse_qasm_interactions(qasm_paths[molecule])

    for grid_size in GRID_SIZES:
        grid_name = f"{grid_size[0]}x{grid_size[1]}"
        factories = _center_factories(grid_size)
        auto_path = output_root / f"auto_center_{grid_name}.yaml"
        auto_path.write_text(
            yaml.safe_dump(_topology_payload(grid_size, factories), sort_keys=False),
            encoding="utf-8",
        )
        grid_record: dict[str, Any] = {
            "grid_size": list(grid_size),
            "magic_factories": [
                {"symbol": symbol, "coord": list(coord)}
                for symbol, coord in factories
            ],
            "auto_topology_path": placement._relative(auto_path),
            "soft_candidate_count": len(_soft_candidates(grid_size, factories)),
            "molecules": {},
        }

        for molecule in placement.MOLECULES:
            num_qubits, edges = parsed[molecule]
            coordinates, supplemental_count = _capacity_coordinates(
                num_qubits,
                grid_size,
                factories,
            )
            mapping = placement._interaction_aware_mapping(coordinates, edges)
            output_path = output_root / (
                f"{molecule.lower()}_{grid_name}_compact_interaction_aware.yaml"
            )
            output_path.write_text(
                yaml.safe_dump(
                    _topology_payload(grid_size, factories, mapping),
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            qasm_path = qasm_paths[molecule]
            grid_record["molecules"][molecule] = {
                "num_logical_qubits": num_qubits,
                "qasm_path": placement._relative(qasm_path),
                "qasm_sha256": placement._sha256(qasm_path),
                "topology_path": placement._relative(output_path),
                "mapping": placement._mapping_records(mapping),
                "bbox": placement._bbox(mapping),
                "weighted_cnot_distance": placement._mapping_objective(mapping, edges),
                "supplemental_non_soft_cells": supplemental_count,
            }
        manifest["grids"][grid_name] = grid_record

    manifest_path = output_root / "grid_capacity_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    manifest = generate(
        args.results.expanduser().resolve(),
        args.cache_root.expanduser().resolve(),
        args.output_root.expanduser().resolve(),
    )
    for grid_name, grid in manifest["grids"].items():
        supplements = {
            molecule: record["supplemental_non_soft_cells"]
            for molecule, record in grid["molecules"].items()
        }
        print(
            f"{grid_name}: soft candidates={grid['soft_candidate_count']} "
            f"supplemental={supplements}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
