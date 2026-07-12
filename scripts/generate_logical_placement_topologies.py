#!/usr/bin/env python3
"""Generate reproducible explicit logical-placement topology files."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = (
    REPO_ROOT
    / "artifacts"
    / "surface_code_rotation_precision_topology_sweep_h4_h7_4th"
    / "results.csv"
)
DEFAULT_CACHE_ROOT = REPO_ROOT / "artifacts" / "surface_code_cache" / "gr" / "prepared_step"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "configs" / "topologies" / "logical_placement_h4_h7"
MOLECULES = ("H4", "H5", "H6", "H7")
GRID_SIZE = (10, 10)
MAGIC_FACTORIES = (
    (0, (4, 4)),
    (1, (4, 5)),
    (2, (5, 4)),
    (3, (5, 5)),
)
PERIMETER_POOL = (
    (0, 0),
    (0, 2),
    (0, 4),
    (0, 6),
    (0, 8),
    (2, 0),
    (4, 0),
    (6, 0),
    (8, 0),
    (9, 2),
    (9, 4),
    (9, 6),
    (9, 8),
    (2, 9),
    (4, 9),
)
_QREG_RE = re.compile(r"^qreg\s+q\[(?P<count>\d+)\];$")
_CX_RE = re.compile(r"^cx\s+q\[(?P<lhs>\d+)\],q\[(?P<rhs>\d+)\];$")


Coord = tuple[int, int]
MappingByQubit = dict[int, Coord]
EdgeWeights = Counter[tuple[int, int]]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _manhattan(lhs: Coord, rhs: Coord) -> int:
    return abs(lhs[0] - rhs[0]) + abs(lhs[1] - rhs[1])


def _mapping_objective(mapping: MappingByQubit, edges: EdgeWeights) -> int:
    return sum(
        int(weight) * _manhattan(mapping[lhs], mapping[rhs])
        for (lhs, rhs), weight in edges.items()
    )


def _auto_soft_candidates() -> list[Coord]:
    width, height = GRID_SIZE
    factory_coords = {coord for _, coord in MAGIC_FACTORIES}
    places: set[Coord] = set()

    for x in range(width):
        for y in range(height):
            available = True
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    candidate = (x + dx, y + dy)
                    outside = not (
                        0 <= candidate[0] < width and 0 <= candidate[1] < height
                    )
                    if outside:
                        continue
                    if candidate in factory_coords or candidate in places:
                        available = False
            if available:
                places.add((x, y))
    return sorted(places)


def _compact_coordinates(num_qubits: int) -> list[Coord]:
    center_x = 0.5 * (GRID_SIZE[0] - 1)
    center_y = 0.5 * (GRID_SIZE[1] - 1)
    ranked = sorted(
        _auto_soft_candidates(),
        key=lambda coord: (
            (coord[0] - center_x) ** 2 + (coord[1] - center_y) ** 2,
            abs(coord[0] - center_x) + abs(coord[1] - center_y),
            coord,
        ),
    )
    if len(ranked) < num_qubits:
        raise ValueError(f"Not enough compact coordinates for {num_qubits} qubits")
    return sorted(ranked[:num_qubits])


def _perimeter_coordinates(num_qubits: int) -> list[Coord]:
    if num_qubits > len(PERIMETER_POOL):
        raise ValueError(f"Not enough perimeter coordinates for {num_qubits} qubits")
    indexes = [math.floor(index * len(PERIMETER_POOL) / num_qubits) for index in range(num_qubits)]
    coordinates = sorted(PERIMETER_POOL[index] for index in indexes)
    if len(set(coordinates)) != num_qubits:
        raise AssertionError("Perimeter coordinate selection produced duplicates")
    return coordinates


def _numeric_mapping(coordinates: Iterable[Coord]) -> MappingByQubit:
    return {qubit: coord for qubit, coord in enumerate(sorted(coordinates))}


def _interaction_aware_mapping(
    coordinates: Iterable[Coord],
    edges: EdgeWeights,
) -> MappingByQubit:
    coords = sorted(coordinates)
    qubits = sorted({qubit for edge in edges for qubit in edge})
    if len(qubits) != len(coords):
        raise ValueError(
            f"Interaction graph has {len(qubits)} qubits for {len(coords)} coordinates"
        )

    degree = Counter[int]()
    for (lhs, rhs), weight in edges.items():
        degree[lhs] += int(weight)
        degree[rhs] += int(weight)
    ranked_qubits = sorted(qubits, key=lambda qubit: (-degree[qubit], qubit))
    ranked_coords = sorted(
        coords,
        key=lambda coord: (sum(_manhattan(coord, other) for other in coords), coord),
    )
    mapping = dict(zip(ranked_qubits, ranked_coords, strict=True))

    while True:
        current = _mapping_objective(mapping, edges)
        best_objective = current
        best_pair: tuple[int, int] | None = None
        for lhs_index, lhs in enumerate(qubits):
            for rhs in qubits[lhs_index + 1 :]:
                mapping[lhs], mapping[rhs] = mapping[rhs], mapping[lhs]
                candidate = _mapping_objective(mapping, edges)
                mapping[lhs], mapping[rhs] = mapping[rhs], mapping[lhs]
                if candidate < best_objective:
                    best_objective = candidate
                    best_pair = (lhs, rhs)
        if best_pair is None:
            break
        lhs, rhs = best_pair
        mapping[lhs], mapping[rhs] = mapping[rhs], mapping[lhs]

    return mapping


def _parse_qasm_interactions(path: Path) -> tuple[int, EdgeWeights]:
    num_qubits: int | None = None
    edges: EdgeWeights = Counter()
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            qreg_match = _QREG_RE.fullmatch(line)
            if qreg_match is not None:
                num_qubits = int(qreg_match.group("count"))
                continue
            cx_match = _CX_RE.fullmatch(line)
            if cx_match is None:
                continue
            lhs = int(cx_match.group("lhs"))
            rhs = int(cx_match.group("rhs"))
            edges[tuple(sorted((lhs, rhs)))] += 1
    if num_qubits is None:
        raise ValueError(f"Missing qreg in {path}")
    if set(qubit for edge in edges for qubit in edge) != set(range(num_qubits)):
        raise ValueError(f"CNOT interaction graph does not cover every qubit in {path}")
    return num_qubits, edges


def _target_hashes(results_path: Path) -> dict[str, str]:
    with results_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    hashes: dict[str, str] = {}
    for molecule in MOLECULES:
        matches = [
            row
            for row in rows
            if row["molecule"] == molecule
            and float(row["rotation_precision"]) == 1.0e-5
            and row["topology_name"] == "factory_center_block"
        ]
        if len(matches) != 1:
            raise ValueError(f"Expected one baseline center row for {molecule}")
        hashes[molecule] = matches[0]["optimized_ir_hash"]
    return hashes


def _discover_qasm_paths(results_path: Path, cache_root: Path) -> dict[str, Path]:
    target_hashes = _target_hashes(results_path)
    found: dict[str, Path] = {}
    for molecule, target_hash in target_hashes.items():
        roots = list(cache_root.glob(f"{molecule}_*__4th_new_2_"))
        for root in roots:
            for artifact_path in root.glob("*/step_artifact.json"):
                try:
                    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if payload.get("optimized_ir_hash") != target_hash:
                    continue
                qasm_path = Path(str(payload["qasm_path"]))
                if not qasm_path.exists():
                    qasm_path = artifact_path.parent / "step.qasm"
                found[molecule] = qasm_path.resolve()
                break
            if molecule in found:
                break
        if molecule not in found:
            raise FileNotFoundError(f"Prepared QASM not found for {molecule}: {target_hash}")
    return found


def _topology_payload(mapping: MappingByQubit) -> dict[str, Any]:
    return {
        "grids": [
            {
                "type": "plane",
                "coord": [GRID_SIZE[0], GRID_SIZE[1], 0],
                "magic_factory": [
                    {"symbol": symbol, "coord": list(coord)}
                    for symbol, coord in MAGIC_FACTORIES
                ],
                "qubit": [
                    {"symbol": qubit, "coord": list(mapping[qubit])}
                    for qubit in sorted(mapping)
                ],
            }
        ]
    }


def _mapping_records(mapping: MappingByQubit) -> list[dict[str, Any]]:
    return [
        {"logical_qubit": qubit, "coord": list(mapping[qubit])}
        for qubit in sorted(mapping)
    ]


def _bbox(mapping: MappingByQubit) -> dict[str, int]:
    xs = [coord[0] for coord in mapping.values()]
    ys = [coord[1] for coord in mapping.values()]
    return {
        "x_min": min(xs),
        "x_max": max(xs),
        "y_min": min(ys),
        "y_max": max(ys),
    }


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def generate(results_path: Path, cache_root: Path, output_root: Path) -> dict[str, Any]:
    qasm_paths = _discover_qasm_paths(results_path, cache_root)
    output_root.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "schema_version": "logical_placement_topology_v1",
        "grid_size": list(GRID_SIZE),
        "magic_factories": [
            {"symbol": symbol, "coord": list(coord)} for symbol, coord in MAGIC_FACTORIES
        ],
        "interaction_source": "pre-synthesis efficient-controlled PF-step QASM CNOT counts",
        "molecules": {},
    }

    for molecule in MOLECULES:
        qasm_path = qasm_paths[molecule]
        num_qubits, edges = _parse_qasm_interactions(qasm_path)
        compact_coords = _compact_coordinates(num_qubits)
        mappings = {
            "compact_numeric": _numeric_mapping(compact_coords),
            "compact_interaction_aware": _interaction_aware_mapping(compact_coords, edges),
            "perimeter_numeric": _numeric_mapping(_perimeter_coordinates(num_qubits)),
        }
        molecule_record: dict[str, Any] = {
            "num_logical_qubits": num_qubits,
            "num_system_qubits": num_qubits - 1,
            "control_qubit": num_qubits - 1,
            "qasm_path": _relative(qasm_path),
            "qasm_sha256": _sha256(qasm_path),
            "cnot_count": sum(edges.values()),
            "interaction_edges": [
                {"q0": lhs, "q1": rhs, "weight": weight}
                for (lhs, rhs), weight in sorted(edges.items())
            ],
            "placements": {},
        }
        for placement_name, mapping in mappings.items():
            output_path = output_root / f"{molecule.lower()}_{placement_name}.yaml"
            output_path.write_text(
                yaml.safe_dump(_topology_payload(mapping), sort_keys=False),
                encoding="utf-8",
            )
            molecule_record["placements"][placement_name] = {
                "topology_path": _relative(output_path),
                "mapping": _mapping_records(mapping),
                "bbox": _bbox(mapping),
                "weighted_cnot_distance": _mapping_objective(mapping, edges),
            }
        manifest["molecules"][molecule] = molecule_record

    manifest_path = output_root / "placement_manifest.json"
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
    for molecule, record in manifest["molecules"].items():
        numeric = record["placements"]["compact_numeric"]["weighted_cnot_distance"]
        aware = record["placements"]["compact_interaction_aware"][
            "weighted_cnot_distance"
        ]
        print(f"{molecule}: compact weighted CNOT distance {numeric} -> {aware}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
