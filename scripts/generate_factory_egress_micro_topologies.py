#!/usr/bin/env python3
"""Generate H7 8x8 topologies for the factory-egress causal micro-sweep."""

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

from scripts import generate_logical_placement_topologies as placement  # noqa: E402


DEFAULT_BASELINE = (
    REPO_ROOT
    / "configs"
    / "topologies"
    / "runtime_grid_threshold_h5_h7"
    / "h7_8x8_compact_interaction_aware.yaml"
)
DEFAULT_GRID_MANIFEST = (
    REPO_ROOT
    / "configs"
    / "topologies"
    / "runtime_grid_threshold_h5_h7"
    / "runtime_grid_threshold_manifest.json"
)
DEFAULT_MAGIC_DIAGNOSTIC = (
    REPO_ROOT
    / "artifacts"
    / "surface_code_magic_failure_reason_diagnostic_h7_4th"
    / "diagnostics"
    / "h7_aware_8x8.json"
)
DEFAULT_OUTPUT_ROOT = (
    REPO_ROOT / "configs" / "topologies" / "factory_egress_micro_h7_4th"
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


def _plane(payload: Mapping[str, Any]) -> dict[str, Any]:
    grids = payload.get("grids", [])
    if len(grids) != 1 or not isinstance(grids[0], dict):
        raise ValueError("expected exactly one plane grid")
    return grids[0]


def _mapping(plane: Mapping[str, Any]) -> dict[int, tuple[int, int]]:
    return {
        int(item["symbol"]): tuple(int(value) for value in item["coord"][:2])
        for item in plane.get("qubit", [])
    }


def _factories(plane: Mapping[str, Any]) -> dict[int, tuple[int, int]]:
    return {
        int(item["symbol"]): tuple(int(value) for value in item["coord"][:2])
        for item in plane.get("magic_factory", [])
    }


def _bans(plane: Mapping[str, Any]) -> set[tuple[int, int]]:
    return {
        tuple(int(value) for value in coord[:2]) for coord in plane.get("ban", [])
    }


def _set_mapping(plane: dict[str, Any], mapping: Mapping[int, tuple[int, int]]) -> None:
    plane["qubit"] = [
        {"symbol": symbol, "coord": list(mapping[symbol])} for symbol in sorted(mapping)
    ]


def _set_factories(
    plane: dict[str, Any], factories: Mapping[int, tuple[int, int]]
) -> None:
    plane["magic_factory"] = [
        {"symbol": symbol, "coord": list(factories[symbol])}
        for symbol in sorted(factories)
    ]


def _validate_topology(payload: Mapping[str, Any]) -> None:
    plane = _plane(payload)
    width, height = (int(value) for value in plane["coord"][:2])
    mapping = _mapping(plane)
    factories = _factories(plane)
    if len(mapping) != 15 or set(mapping) != set(range(15)):
        raise ValueError("expected logical qubits 0 through 14")
    if len(factories) != 4 or set(factories) != set(range(4)):
        raise ValueError("expected magic factories 0 through 3")
    bans = _bans(plane)
    all_coords = list(mapping.values()) + list(factories.values()) + list(bans)
    if len(all_coords) != len(set(all_coords)):
        raise ValueError("topology contains overlapping qubits or factories")
    if any(not (0 <= x < width and 0 <= y < height) for x, y in all_coords):
        raise ValueError("topology contains an out-of-grid coordinate")


def _free_neighbors(
    plane: Mapping[str, Any],
) -> tuple[dict[int, int], dict[str, int]]:
    width, height = (int(value) for value in plane["coord"][:2])
    mapping = _mapping(plane)
    factories = _factories(plane)
    occupied = set(mapping.values()) | set(factories.values()) | _bans(plane)
    by_symbol: dict[int, int] = {}
    by_coord: dict[str, int] = {}
    for symbol, (x, y) in factories.items():
        neighbors = ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
        count = sum(
            1
            for nx, ny in neighbors
            if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in occupied
        )
        by_symbol[symbol] = count
        by_coord[f"{x},{y}"] = count
    return by_symbol, by_coord


def _weighted_nearest_factory_distance(
    mapping: Mapping[int, tuple[int, int]],
    factories: Mapping[int, tuple[int, int]],
    magic_target_counts: Mapping[int, int],
) -> tuple[int, float]:
    weighted = 0
    count = 0
    for qubit, weight in magic_target_counts.items():
        nearest = min(
            placement._manhattan(mapping[qubit], factory_coord)
            for factory_coord in factories.values()
        )
        weighted += int(weight) * nearest
        count += int(weight)
    return weighted, weighted / count if count else 0.0


def _variants(baseline: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    variants: dict[str, dict[str, Any]] = {}

    def add(
        name: str,
        *,
        moves: Mapping[int, tuple[int, int]] | None = None,
        factory_rotation: bool = False,
    ) -> None:
        payload = deepcopy(dict(baseline))
        plane = _plane(payload)
        mapping = _mapping(plane)
        mapping.update(moves or {})
        _set_mapping(plane, mapping)
        if factory_rotation:
            original = _factories(plane)
            _set_factories(
                plane,
                {
                    0: original[1],
                    1: original[2],
                    2: original[3],
                    3: original[0],
                },
            )
        _validate_topology(payload)
        variants[name] = payload

    add("egress_0_baseline")
    add("egress_1_left", moves={1: (1, 3)})
    add("egress_1_down", moves={2: (3, 1)})
    add("egress_2_both", moves={1: (1, 3), 2: (3, 1)})
    add("egress_0_symbol_rotate", factory_rotation=True)
    return variants


def generate(
    baseline_path: Path,
    grid_manifest_path: Path,
    magic_diagnostic_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    baseline = yaml.safe_load(baseline_path.read_text(encoding="utf-8"))
    if not isinstance(baseline, dict):
        raise ValueError(f"expected YAML mapping: {baseline_path}")
    _validate_topology(baseline)
    grid_manifest = json.loads(grid_manifest_path.read_text(encoding="utf-8"))
    h7_grid = grid_manifest["grids"]["8x8"]["molecules"]["H7"]
    qasm_path = (REPO_ROOT / h7_grid["qasm_path"]).resolve()
    num_qubits, edges = placement._parse_qasm_interactions(qasm_path)
    if num_qubits != 15:
        raise ValueError(f"expected 15 H7 logical qubits, found {num_qubits}")
    magic_diagnostic = json.loads(magic_diagnostic_path.read_text(encoding="utf-8"))
    target_stats = magic_diagnostic["magic_routing_distribution"]["target_stats"]
    magic_target_counts = {
        int(qubit): int(stats["instruction_count"])
        for qubit, stats in target_stats.items()
    }

    output_root.mkdir(parents=True, exist_ok=True)
    records: dict[str, Any] = {}
    baseline_cnot: int | None = None
    baseline_magic_distance: int | None = None
    for name, payload in _variants(baseline).items():
        output_path = output_root / f"h7_8x8_{name}.yaml"
        output_path.write_text(
            yaml.safe_dump(payload, sort_keys=False),
            encoding="utf-8",
        )
        plane = _plane(payload)
        mapping = _mapping(plane)
        factories = _factories(plane)
        free_by_symbol, free_by_coord = _free_neighbors(plane)
        weighted_cnot = placement._mapping_objective(mapping, edges)
        weighted_magic, mean_magic = _weighted_nearest_factory_distance(
            mapping,
            factories,
            magic_target_counts,
        )
        if name == "egress_0_baseline":
            baseline_cnot = weighted_cnot
            baseline_magic_distance = weighted_magic
        records[name] = {
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
            "factory_coordinate_set": [list(coord) for coord in sorted(factories.values())],
            "initial_free_neighbors_by_factory_symbol": {
                str(symbol): count for symbol, count in sorted(free_by_symbol.items())
            },
            "initial_free_neighbors_by_factory_coordinate": free_by_coord,
            "trapped_coordinate_free_neighbors": free_by_coord[
                f"{TRAPPED_FACTORY_COORD[0]},{TRAPPED_FACTORY_COORD[1]}"
            ],
            "weighted_cnot_distance": weighted_cnot,
            "weighted_nearest_factory_distance": weighted_magic,
            "weighted_nearest_factory_distance_mean": mean_magic,
        }
    assert baseline_cnot is not None and baseline_magic_distance is not None
    for record in records.values():
        record["weighted_cnot_distance_delta_vs_baseline"] = (
            int(record["weighted_cnot_distance"]) - baseline_cnot
        )
        record["weighted_nearest_factory_distance_delta_vs_baseline"] = (
            int(record["weighted_nearest_factory_distance"]) - baseline_magic_distance
        )

    manifest = {
        "schema_version": "factory_egress_micro_topology_v1",
        "molecule": "H7",
        "pf_label": "4th(new_2)",
        "grid_size": [8, 8],
        "baseline_topology_path": _relative(baseline_path),
        "baseline_topology_sha256": _sha256(baseline_path),
        "qasm_path": _relative(qasm_path),
        "qasm_sha256": _sha256(qasm_path),
        "interaction_source": "pre-synthesis efficient-controlled PF-step QASM CNOT counts",
        "magic_target_source": _relative(magic_diagnostic_path),
        "magic_target_count": sum(magic_target_counts.values()),
        "trapped_factory_coordinate": list(TRAPPED_FACTORY_COORD),
        "variants": records,
    }
    manifest_path = output_root / "factory_egress_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--grid-manifest", type=Path, default=DEFAULT_GRID_MANIFEST)
    parser.add_argument("--magic-diagnostic", type=Path, default=DEFAULT_MAGIC_DIAGNOSTIC)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    manifest = generate(
        args.baseline.expanduser().resolve(),
        args.grid_manifest.expanduser().resolve(),
        args.magic_diagnostic.expanduser().resolve(),
        args.output_root.expanduser().resolve(),
    )
    for name, record in manifest["variants"].items():
        print(
            name,
            "egress=",
            record["trapped_coordinate_free_neighbors"],
            "cnot=",
            record["weighted_cnot_distance"],
            "magic_distance=",
            record["weighted_nearest_factory_distance"],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
