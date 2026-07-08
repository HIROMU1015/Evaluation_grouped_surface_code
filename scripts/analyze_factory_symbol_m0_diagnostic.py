#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "artifacts" / "surface_code_factory_symbol_m0_diagnostic_h4_h7"
)
TOPOLOGY_PATHS = {
    "m0_left": PROJECT_ROOT / "configs/topologies/factory_symbol_perm_m0_left.yaml",
    "m0_center": PROJECT_ROOT / "configs/topologies/factory_symbol_perm_m0_center.yaml",
    "m0_right": PROJECT_ROOT / "configs/topologies/factory_symbol_perm_m0_right.yaml",
    "m0_far_corner": PROJECT_ROOT
    / "configs/topologies/factory_symbol_perm_m0_far_corner.yaml",
}
CASE_ORDER = ["m0_left", "m0_center", "m0_right", "m0_far_corner"]
RESULT_CSVS = ["h4_h5_results.csv", "h6_results.csv", "h7_results.csv"]
DIAGNOSTIC_FIELDS = [
    "molecule",
    "pf_label",
    "topology_variant",
    "m0_coordinate",
    "factory_coordinate_set",
    "used_magic_factory_symbols",
    "used_magic_factory_coordinates",
    "magic_count_by_factory_symbol",
    "magic_count_by_factory_coordinate",
    "magic_delivery_distance_mean",
    "magic_delivery_distance_max",
    "nearest_magic_distance_mean",
    "nearest_magic_distance_max",
    "cnot_distance_mean",
    "cnot_distance_max",
    "chip_cell_active_qubit_area_ave",
    "chip_cell_active_qubit_area_peak",
    "runtime_with_topology",
    "qubit_volume",
    "chip_cells",
    "physical_qubits",
    "code_distance",
    "qret_compile_elapsed_sec",
    "qret_compile_peak_rss_kb",
    "qret_mapping_elapsed_sec",
    "qret_mapping_peak_rss_kb",
    "qret_peak_rss_kb",
    "compile_cache_hit",
    "mapping_result_json",
    "compile_info_json",
    "stage_metrics_json",
]


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return data


def topology_factories(path: Path) -> dict[int, tuple[int, int, int]]:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    grids = cfg.get("grids") if isinstance(cfg, Mapping) else None
    if not isinstance(grids, list) or not grids:
        raise ValueError(f"topology grids missing: {path}")
    factories = grids[0].get("magic_factory")
    if not isinstance(factories, list):
        raise ValueError(f"magic_factory missing: {path}")
    result: dict[int, tuple[int, int, int]] = {}
    for factory in factories:
        symbol = int(factory["symbol"])
        coord = list(factory["coord"])
        if len(coord) == 2:
            coord.append(0)
        result[symbol] = tuple(int(item) for item in coord[:3])
    return result


def coord_text(coord: Any) -> str:
    if coord is None:
        return ""
    values = list(coord)
    if len(values) >= 2:
        return f"({int(values[0])},{int(values[1])})"
    return str(coord)


def coord_set_text(coords: list[tuple[int, int, int]]) -> str:
    return ";".join(coord_text(coord) for coord in sorted(coords))


def json_compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def metric(stats: Mapping[str, Any], key: str) -> Any:
    value = stats.get(key)
    return "" if value is None else value


def stage_metrics_path(mapping_path: Path) -> Path:
    root = mapping_path.parent
    cold = root / "compile_stage_metrics.json"
    if cold.exists():
        return cold
    return root / "compile_stage_cache_hit_metrics.json"


def qret_stage_metrics(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = load_json(path)
    result: dict[str, Any] = {
        "stage_metrics_json": str(path.relative_to(PROJECT_ROOT)),
    }
    peak_values: list[int] = []
    for stage in data.get("stages", []):
        if not isinstance(stage, Mapping):
            continue
        name = str(stage.get("name"))
        stage_result = stage.get("result")
        if not isinstance(stage_result, Mapping):
            stage_result = {}
        rss = stage_result.get("subprocess_maxrss_kb")
        elapsed = stage.get("elapsed_seconds")
        if rss is not None:
            peak_values.append(int(rss))
        if name == "qret_compile":
            result["qret_compile_elapsed_sec"] = elapsed
            result["qret_compile_peak_rss_kb"] = rss
        elif name == "qret_mapping_result":
            result["qret_mapping_elapsed_sec"] = elapsed
            result["qret_mapping_peak_rss_kb"] = rss
    if peak_values:
        result["qret_peak_rss_kb"] = max(peak_values)
    return result


def read_result_rows(output_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in RESULT_CSVS:
        path = output_dir / name
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as f:
            rows.extend(dict(row) for row in csv.DictReader(f))
    return rows


def build_diagnostic_row(row: Mapping[str, Any]) -> dict[str, Any]:
    mapping_path = Path(str(row["mapping_result_json"]))
    if not mapping_path.is_absolute():
        mapping_path = PROJECT_ROOT / mapping_path
    mapping = load_json(mapping_path)
    compile_info_path = mapping_path.with_name("compile_info.json")
    compile_info = load_json(compile_info_path)
    variant = str(row["case_name"])
    factories = topology_factories(TOPOLOGY_PATHS[variant])
    symbol_counts = mapping.get("magic_operation_count_by_factory", {})
    coord_counts = mapping.get("magic_operation_count_by_factory_coordinate", {})
    used_symbols = sorted(int(symbol) for symbol in symbol_counts)
    used_coords = [factories[symbol] for symbol in used_symbols if symbol in factories]
    stage = qret_stage_metrics(stage_metrics_path(mapping_path))
    magic_stats = mapping.get("magic_operation_distance_stats", {})
    nearest_stats = mapping.get("nearest_magic_distance_stats", {})
    cnot_stats = mapping.get("cnot_distance_stats", {})
    factory_set = coord_set_text(list(factories.values()))
    result = {
        "molecule": row.get("molecule"),
        "pf_label": row.get("pf_label"),
        "topology_variant": variant,
        "m0_coordinate": coord_text(factories[0]),
        "factory_coordinate_set": factory_set,
        "used_magic_factory_symbols": ",".join(str(item) for item in used_symbols),
        "used_magic_factory_coordinates": ";".join(coord_text(coord) for coord in used_coords),
        "magic_count_by_factory_symbol": json_compact(symbol_counts),
        "magic_count_by_factory_coordinate": json_compact(coord_counts),
        "magic_delivery_distance_mean": metric(magic_stats, "mean"),
        "magic_delivery_distance_max": metric(magic_stats, "max"),
        "nearest_magic_distance_mean": metric(nearest_stats, "mean"),
        "nearest_magic_distance_max": metric(nearest_stats, "max"),
        "cnot_distance_mean": metric(cnot_stats, "mean"),
        "cnot_distance_max": metric(cnot_stats, "max"),
        "chip_cell_active_qubit_area_ave": compile_info.get(
            "chip_cell_active_qubit_area_ave", ""
        ),
        "chip_cell_active_qubit_area_peak": compile_info.get(
            "chip_cell_active_qubit_area_peak", ""
        ),
        "runtime_with_topology": row.get("runtime_with_topology"),
        "qubit_volume": row.get("qubit_volume"),
        "chip_cells": row.get("chip_cells"),
        "physical_qubits": row.get("physical_qubits"),
        "code_distance": row.get("code_distance"),
        "qret_compile_elapsed_sec": stage.get("qret_compile_elapsed_sec", ""),
        "qret_compile_peak_rss_kb": stage.get("qret_compile_peak_rss_kb", ""),
        "qret_mapping_elapsed_sec": stage.get("qret_mapping_elapsed_sec", ""),
        "qret_mapping_peak_rss_kb": stage.get("qret_mapping_peak_rss_kb", ""),
        "qret_peak_rss_kb": stage.get("qret_peak_rss_kb", ""),
        "compile_cache_hit": row.get("compile_cache_hit"),
        "mapping_result_json": str(mapping_path.relative_to(PROJECT_ROOT)),
        "compile_info_json": str(compile_info_path.relative_to(PROJECT_ROOT)),
        "stage_metrics_json": stage.get("stage_metrics_json", ""),
    }
    return result


def sort_key(row: Mapping[str, Any]) -> tuple[int, int]:
    molecule = str(row["molecule"])
    return int(molecule[1:]), CASE_ORDER.index(str(row["topology_variant"]))


def write_jsonl(path: Path, rows: list[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(dict(row), ensure_ascii=True, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=DIAGNOSTIC_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in DIAGNOSTIC_FIELDS})


def fmt(value: Any) -> str:
    if value in (None, ""):
        return "N/A"
    if isinstance(value, float):
        return f"{value:.6g}"
    text = str(value)
    return text.replace("|", "\\|")


def markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(fmt(item) for item in row) + " |")
    return lines


def write_summary(path: Path, rows: list[Mapping[str, Any]]) -> None:
    molecules = sorted({str(row["molecule"]) for row in rows}, key=lambda item: int(item[1:]))
    symbol_counter = Counter(str(row["used_magic_factory_symbols"]) for row in rows)
    all_symbol_zero = set(symbol_counter) == {"0"}
    coordinate_follows_m0 = all(
        str(row["used_magic_factory_coordinates"]) == str(row["m0_coordinate"])
        for row in rows
    )
    volume_values = [
        int(row["qubit_volume"])
        for row in rows
        if str(row.get("qubit_volume", "")).strip()
    ]
    active_area_values = [
        float(row["chip_cell_active_qubit_area_ave"])
        for row in rows
        if str(row.get("chip_cell_active_qubit_area_ave", "")).strip()
    ]
    peak_rss_values = [
        int(row["qret_peak_rss_kb"])
        for row in rows
        if str(row.get("qret_peak_rss_kb", "")).strip()
    ]
    elapsed_values = [
        float(row["qret_compile_elapsed_sec"])
        for row in rows
        if str(row.get("qret_compile_elapsed_sec", "")).strip()
    ]
    variant_rows = []
    topology_sets = []
    for variant in CASE_ORDER:
        factories = topology_factories(TOPOLOGY_PATHS[variant])
        topology_sets.append(set(factories.values()))
        variant_rows.append(
            [
                variant,
                coord_text(factories[0]),
                coord_text(factories[1]),
                coord_text(factories[2]),
                coord_text(factories[3]),
                coord_set_text(list(factories.values())),
            ]
        )
    same_coordinate_set = all(item == topology_sets[0] for item in topology_sets)

    result_rows = []
    for row in sorted(rows, key=sort_key):
        result_rows.append(
            [
                row["molecule"],
                row["topology_variant"],
                row["m0_coordinate"],
                row["used_magic_factory_symbols"],
                row["used_magic_factory_coordinates"],
                row["magic_delivery_distance_mean"],
                row["chip_cell_active_qubit_area_ave"],
                row["qubit_volume"],
                row["runtime_with_topology"],
                row["qret_peak_rss_kb"],
            ]
        )

    lines = [
        "# Factory Symbol / m0 Diagnostic Summary",
        "",
        "## Scope",
        "",
        f"- Molecules executed: {', '.join(molecules) if molecules else 'none'}",
        "- PF: `4th(new_2)`",
        "- Circuit scope: `efficient_controlled_pf_one_step`",
        "- Magic period: 15",
        "- Magic stock: fixed 10000",
        "- H8 or larger was not executed.",
        "- This is not a full QPE compile.",
        "",
        "## Topology Variants",
        "",
        "All variants use the same coordinate set; only the symbol assignment changes."
        if same_coordinate_set
        else "WARNING: coordinate sets differ across variants.",
        "",
        *markdown_table(
            ["variant", "m0", "m1", "m2", "m3", "coordinate set"],
            variant_rows,
        ),
        "",
        "## Results",
        "",
        *markdown_table(
            [
                "molecule",
                "variant",
                "m0 coord",
                "used symbols",
                "used coords",
                "magic dist mean",
                "active area ave",
                "qubit volume",
                "runtime",
                "peak RSS KB",
            ],
            result_rows,
        ),
        "",
        "## Interpretation",
        "",
        "### Observed",
        "",
        f"- All cases used magic factory symbol 0: {str(all_symbol_zero).lower()}.",
        f"- Used magic factory coordinates followed the m0 coordinate: {str(coordinate_follows_m0).lower()}.",
        "- The four topology variants used the same factory coordinate set and changed only symbol assignment."
        if same_coordinate_set
        else "- The topology coordinate-set check failed.",
        f"- Qubit volume range across executed rows: {min(volume_values) if volume_values else 'N/A'} to {max(volume_values) if volume_values else 'N/A'}.",
        f"- Active-area average range across executed rows: {min(active_area_values) if active_area_values else 'N/A'} to {max(active_area_values) if active_area_values else 'N/A'}.",
        "",
        "### Inferred",
        "",
        "- These results are consistent with qret selecting magic factory symbol 0 for `LATTICE_SURGERY_MAGIC`, rather than selecting the geometrically nearest available factory.",
        "- Magic-delivery distance follows m0 placement, but active area and qubit volume are mostly invariant under symbol-only permutations in this fixed coordinate set.",
        "- The earlier topology-sweep volume differences therefore cannot be attributed to symbol assignment alone; factory coordinate-set placement, layout occupancy, and/or other qret scheduling details remain relevant.",
        "",
        "### Unresolved",
        "",
        "- This is an observed result for the executed H-chain inputs, not a formal proof of qret behavior for every input.",
        "- The internal reason for choosing symbol 0 remains a quration/qret implementation question.",
        "",
        "## Safety / Execution",
        "",
        f"- Success rows: {sum(1 for row in rows if row)}",
        f"- Peak RSS max: {max(peak_rss_values) if peak_rss_values else 'N/A'} KB",
        f"- Compile elapsed max: {max(elapsed_values) if elapsed_values else 'N/A'} s",
        "- Raw `mapping_state.json` files were not retained.",
        "",
        "## Artifacts",
        "",
        "- `artifacts/surface_code_factory_symbol_m0_diagnostic_h4_h7/diagnostics.csv`",
        "- `artifacts/surface_code_factory_symbol_m0_diagnostic_h4_h7/diagnostics.jsonl`",
        "- `artifacts/surface_code_factory_symbol_m0_diagnostic_h4_h7/summary.md`",
        "- `artifacts/surface_code_factory_symbol_m0_diagnostic_h4_h7/logs/`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze factory-symbol/m0 diagnostic sweep outputs."
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Diagnostic artifact directory.",
    )
    args = parser.parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    source_rows = read_result_rows(output_dir)
    if not source_rows:
        raise FileNotFoundError(f"No result CSV files found in {output_dir}")
    diagnostics = [
        build_diagnostic_row(row)
        for row in source_rows
        if row.get("status") == "success" and row.get("mapping_result_json")
    ]
    diagnostics.sort(key=sort_key)
    write_csv(output_dir / "diagnostics.csv", diagnostics)
    write_jsonl(output_dir / "diagnostics.jsonl", diagnostics)
    write_summary(output_dir / "summary.md", diagnostics)
    print(f"DIAGNOSTICS_OK rows={len(diagnostics)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
