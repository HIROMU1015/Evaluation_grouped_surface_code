#!/usr/bin/env python3
"""Run the fixed-circuit H4-H7 accessible factory-count sweep."""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import run_factory_egress_micro_sweep as micro  # noqa: E402
from scripts import run_qret_runtime_routing_diagnostic as routing  # noqa: E402


DEFAULT_CONFIG = (
    REPO_ROOT / "configs" / "surface_code_accessible_factory_count_sweep_h4_h7_4th.yaml"
)
DEFAULT_QRET = REPO_ROOT / "build" / "quration" / "qret"
DEFAULT_DIAGNOSTIC_PATCH = Path("/tmp/qret-magic-failure-reason-diagnostic.patch")
MAGIC_GENERATION_PERIOD = 15


def _resolve(path: str | Path) -> Path:
    value = Path(path).expanduser()
    return value.resolve() if value.is_absolute() else (REPO_ROOT / value).resolve()


def _load_config(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected YAML mapping: {path}")
    return payload


def _case_names(config: Mapping[str, Any]) -> list[str]:
    return [
        f"{str(molecule).lower()}_factory_count_{int(factory_count)}"
        for molecule in config["molecules"]
        for factory_count in config["factory_counts"]
    ]


def _source_rows(config: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    source = config["source"]
    with _resolve(source["results_csv"]).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    selected: dict[str, dict[str, str]] = {}
    for molecule in config["molecules"]:
        molecule = str(molecule)
        matches = [
            row
            for row in rows
            if row["molecule"] == molecule
            and row["topology_name"] == str(source["topology_name"])
            and row["pf_label"] == str(source["pf_label"])
            and float(row["rotation_precision"])
            == float(source["rotation_precision"])
        ]
        if len(matches) != 1:
            raise RuntimeError(f"expected one {molecule} source row, found {len(matches)}")
        selected[molecule] = matches[0]
    return selected


def _fixed_logical_workload_match(row: Mapping[str, Any]) -> bool:
    differences = dict(row.get("semantic_differences", {}))
    if not differences:
        return True
    if set(differences) != {
        "gate_count",
        "gate_count_detail",
        "runtime_without_topology",
    }:
        return False

    factory_count = int(row["factory_count"])
    gate_count = differences["gate_count"]
    if int(gate_count["baseline"]) - int(gate_count["observed"]) != 4 - factory_count:
        return False
    details = differences["gate_count_detail"]
    baseline_detail = dict(details["baseline"])
    observed_detail = dict(details["observed"])
    if int(baseline_detail.pop("ALLOCATE_MAGIC_FACTORY", -1)) != 4:
        return False
    if int(observed_detail.pop("ALLOCATE_MAGIC_FACTORY", -1)) != factory_count:
        return False
    return baseline_detail == observed_detail


def _enrich(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_molecule_count = {
        (str(row["molecule"]), int(row["factory_count"])): row for row in rows
    }
    magic_demand: dict[str, int] = {}
    for row in rows:
        details = row.get("semantic_differences", {}).get("gate_count_detail")
        if details:
            magic_demand[str(row["molecule"])] = int(
                details["baseline"]["LATTICE_SURGERY_MAGIC"]
            )
    enriched: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        molecule = str(row["molecule"])
        count = int(row["factory_count"])
        baseline = by_molecule_count[(molecule, 4)]
        row["runtime_delta_vs_four_factories"] = int(row["runtime"]) - int(
            baseline["runtime"]
        )
        row["runtime_change_pct_vs_four_factories"] = (
            int(row["runtime"]) / int(baseline["runtime"]) - 1.0
        ) * 100.0
        row["qubit_volume_change_pct_vs_four_factories"] = (
            int(row["qubit_volume"]) / int(baseline["qubit_volume"]) - 1.0
        ) * 100.0
        if count == 1:
            row["runtime_reduction_pct_vs_previous_count"] = None
        else:
            previous = by_molecule_count[(molecule, count - 1)]
            row["runtime_reduction_pct_vs_previous_count"] = (
                1.0 - int(row["runtime"]) / int(previous["runtime"])
            ) * 100.0
        row["fixed_logical_workload_match"] = _fixed_logical_workload_match(row)
        row["expected_architecture_differences_only"] = bool(
            row["fixed_logical_workload_match"] and not row["semantic_match"]
        )
        row["magic_demand_count"] = magic_demand[molecule]
        row["ideal_magic_supply_runtime"] = math.ceil(
            magic_demand[molecule] * MAGIC_GENERATION_PERIOD / count
        )
        row["runtime_without_topology_minus_ideal_supply"] = int(
            row["runtime_without_topology"]
        ) - int(row["ideal_magic_supply_runtime"])
        enriched.append(row)
    return enriched


def _write_outputs(
    output_root: Path, rows: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    enriched = _enrich(rows)
    precisions = {str(row["rotation_precision"]) for row in enriched}
    if len(precisions) != 1:
        raise RuntimeError(f"expected one rotation precision, found {sorted(precisions)}")
    rotation_precision = next(iter(precisions))
    with (output_root / "results.jsonl").open("w", encoding="utf-8") as handle:
        for row in enriched:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    csv_fields = [key for key in enriched[0] if key != "semantic_differences"]
    with (output_root / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=csv_fields,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(enriched)

    lines = [
        f"# H4-H7 Accessible Factory-Count Sweep (`rotation_precision={rotation_precision}`)",
        "",
        "The compiled circuit, 10x10 logical mapping, four-cell central factory budget, magic period/stock, and QEC inputs are fixed. Inactive factory coordinates are banned so active factories plus banned cells always occupy four cells. Every active factory has two initial free egress cells.",
    ]
    for molecule in ("H4", "H5", "H6", "H7"):
        lines.extend(
            [
                "",
                f"## {molecule}",
                "",
                "| factories | min egress | runtime | vs four | marginal reduction | supply-floor residual | topology overhead | no stock | egress blocked | available factories mean | magic mean path | code distance | physical qubits | QV vs four | workload match |",
                "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
            ]
        )
        for row in enriched:
            if row["molecule"] != molecule:
                continue
            marginal = row["runtime_reduction_pct_vs_previous_count"]
            marginal_text = "reference" if marginal is None else f"{float(marginal):+.4f}%"
            lines.append(
                "| {count} | {egress} | {runtime:,} | {runtime_pct:+.4f}% | {marginal} | {residual:+,} | {overhead:,} | {stock:,} | {blocked:,} | {available:.3f} | {path:.3f} | {distance} | {physical:,} | {qv_pct:+.4f}% | {match} |".format(
                    count=int(row["factory_count"]),
                    egress=int(row["minimum_initial_free_neighbors"]),
                    runtime=int(row["runtime"]),
                    runtime_pct=float(row["runtime_change_pct_vs_four_factories"]),
                    marginal=marginal_text,
                    residual=int(row["runtime_without_topology_minus_ideal_supply"]),
                    overhead=int(row["runtime_topology_overhead"]),
                    stock=int(row["magic_failure_no_magic_stock"]),
                    blocked=int(row["factory_egress_blocked"]),
                    available=float(row["magic_available_factory_count_mean"]),
                    path=float(row["magic_mean_path_coordinates"]),
                    distance=int(row["code_distance"]),
                    physical=int(row["physical_qubits"]),
                    qv_pct=float(row["qubit_volume_change_pct_vs_four_factories"]),
                    match="yes" if row["fixed_logical_workload_match"] else "no",
                )
            )

    peak_rss = max(int(row["gnu_time_max_rss_kb"]) for row in enriched)
    physical_constant = all(
        len({int(row["physical_qubits"]) for row in enriched if row["molecule"] == molecule})
        == 1
        for molecule in ("H4", "H5", "H6", "H7")
    )
    physical_note = (
        "- Physical-qubit count is constant within each molecule."
        if physical_constant
        else "- Physical-qubit count changes within at least one molecule because runtime crosses a code-distance threshold; the logical-cell budget remains fixed."
    )
    lines.extend(
        [
            "",
            "## Validity and execution",
            "",
            "- Fixed logical workload match: all cases. QASM/optimized IR, logical gates/depth, and magic demand/depth are unchanged.",
            "- Expected architecture differences are `ALLOCATE_MAGIC_FACTORY` count and `runtime_without_topology`, because qret includes factory supply in that runtime estimate.",
            "- Active factories plus banned cells remain four and usable non-factory cells remain 96 in every case.",
            physical_note,
            "- Factory egress rejection should remain negligible; a large value indicates that factory count is confounded by access geometry.",
            f"- peak qret RSS: {peak_rss:,} KiB ({peak_rss / 1024**2:.2f} GiB)",
            f"- maximum GNU-time swaps: {max(int(row['gnu_time_swaps']) for row in enriched)}",
            "- intended execution: sequential tmux session with `MemoryHigh=44G`, `MemoryMax=48G`",
            f"- diagnostic `libqret-core.so` SHA-256: `{enriched[0]['qret_core_library_hash']}`",
            f"- local diagnostic patch SHA-256: `{enriched[0]['diagnostic_patch_sha256']}`",
            "",
        ]
    )
    supply_limited = [
        row
        for row in enriched
        if abs(int(row["runtime_without_topology_minus_ideal_supply"]))
        <= max(100, int(row["ideal_magic_supply_runtime"]) // 1000)
    ]
    supply_labels = ", ".join(
        f"{row['molecule']}:N={int(row['factory_count'])}" for row in supply_limited
    )
    saturation_counts: dict[str, int] = {}
    for molecule in ("H4", "H5", "H6", "H7"):
        molecule_rows = sorted(
            (row for row in enriched if row["molecule"] == molecule),
            key=lambda row: int(row["factory_count"]),
        )
        saturation_counts[molecule] = min(
            int(row["factory_count"])
            for row in molecule_rows
            if abs(float(row["runtime_change_pct_vs_four_factories"])) < 1.0
        )
    saturation_text = ", ".join(
        f"{molecule}:N={count}" for molecule, count in saturation_counts.items()
    )
    lines.extend(
        [
            "## Interpretation",
            "",
            f"- Rows matching the pure supply floor `ceil(magic_count * {MAGIC_GENERATION_PERIOD} / factory_count)` within 0.1% (minimum tolerance 100 beats): {supply_labels or 'none'}.",
            f"- Minimum tested factory count within 1% of the four-factory runtime: {saturation_text}.",
            "- A large positive supply-floor residual means the remaining circuit/dependency schedule, rather than factory generation throughput, sets runtime.",
            "- Egress-blocked and no-stock counts are reported separately so supply capacity is not confused with the zero-egress pathology.",
            "",
        ]
    )
    (output_root / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    return enriched


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--qret", type=Path, default=DEFAULT_QRET)
    parser.add_argument("--diagnostic-patch", type=Path, default=DEFAULT_DIAGNOSTIC_PATCH)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--summarize-existing", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    config = _load_config(args.config.expanduser().resolve())
    manifest_path = _resolve(config["topology_manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    variants = manifest["variants"]
    case_names = _case_names(config)
    if any(name not in variants for name in case_names):
        raise ValueError("config references an unknown topology variant")
    if args.dry_run:
        for name in case_names:
            record = variants[name]
            print(
                name,
                record["factory_count"],
                record["minimum_initial_free_neighbors"],
                record["usable_non_factory_cell_count"],
                record["weighted_nearest_factory_distance_delta_vs_baseline"],
            )
        return 0

    output_root = _resolve(config["output_directory"])
    if args.summarize_existing:
        with (output_root / "results.jsonl").open(encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
        enriched = _write_outputs(output_root, rows)
        if not all(bool(row["fixed_logical_workload_match"]) for row in enriched):
            raise RuntimeError("one or more cases changed the fixed logical workload")
        print(output_root / "summary.md")
        return 0

    source_rows = _source_rows(config)
    source_inputs: dict[str, tuple[Path, dict[str, Any]]] = {}
    for molecule, source_row in source_rows.items():
        source_yaml = routing._find_source_compile_yaml(source_row["cache_key"])
        source_inputs[molecule] = (
            source_yaml,
            routing._load_json(source_yaml.with_name("compile_info.json")),
        )

    qret = args.qret.expanduser().resolve()
    qret_core = routing._linked_qret_core(qret)
    patch_path = args.diagnostic_patch.expanduser().resolve()
    patch_hash = routing._sha256(patch_path) if patch_path.exists() else None
    output_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for name in case_names:
        record = variants[name]
        molecule = str(record["molecule"])
        source_yaml, source_compile_info = source_inputs[molecule]
        row = micro._run_case(
            name,
            record,
            source_yaml=source_yaml,
            source_compile_info=source_compile_info,
            source_row=source_rows[molecule],
            output_root=output_root,
            qret=qret,
            qret_hash=routing._sha256(qret),
            qret_core=qret_core,
            qret_core_hash=routing._sha256(qret_core),
            diagnostic_patch_hash=patch_hash,
        )
        row["factory_count"] = int(record["factory_count"])
        row["minimum_initial_free_neighbors"] = int(
            record["minimum_initial_free_neighbors"]
        )
        row["banned_cells"] = json.dumps(record["banned_cells"])
        row["banned_cell_count"] = int(record["banned_cell_count"])
        row["factory_plus_ban_cell_count"] = int(
            record["factory_plus_ban_cell_count"]
        )
        row["usable_non_factory_cell_count"] = int(
            record["usable_non_factory_cell_count"]
        )
        rows.append(row)
        print(
            name,
            "runtime=",
            row["runtime"],
            "no_stock=",
            row["magic_failure_no_magic_stock"],
            "egress_blocked=",
            row["factory_egress_blocked"],
            flush=True,
        )

    enriched = _write_outputs(output_root, rows)
    shutil.rmtree(output_root / ".work", ignore_errors=True)
    if not all(bool(row["fixed_logical_workload_match"]) for row in enriched):
        raise RuntimeError("one or more cases changed the fixed logical workload")
    print(output_root / "summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
