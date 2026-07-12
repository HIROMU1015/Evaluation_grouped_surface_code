#!/usr/bin/env python3
"""Run the fixed-circuit H5/H6 factory-egress generalization sweep."""

from __future__ import annotations

import argparse
import csv
import json
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
    REPO_ROOT / "configs" / "surface_code_factory_egress_generalization_h5_h6_4th.yaml"
)
DEFAULT_QRET = REPO_ROOT / "build" / "quration" / "qret"
DEFAULT_DIAGNOSTIC_PATCH = Path("/tmp/qret-magic-failure-reason-diagnostic.patch")


def _resolve(path: str | Path) -> Path:
    value = Path(path).expanduser()
    return value.resolve() if value.is_absolute() else (REPO_ROOT / value).resolve()


def _load_config(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected YAML mapping: {path}")
    return payload


def _source_rows(config: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    source = config["source"]
    with _resolve(source["results_csv"]).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    selected: dict[str, dict[str, str]] = {}
    for molecule in ("H5", "H6"):
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


def _enrich(
    rows: Sequence[Mapping[str, Any]], baseline_cases: Mapping[str, str]
) -> list[dict[str, Any]]:
    baselines = {
        molecule: next(
            row for row in rows if row["case_name"] == baseline_cases[molecule]
        )
        for molecule in baseline_cases
    }
    enriched: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        baseline = baselines[str(row["molecule"])]
        row["runtime_delta_vs_molecule_baseline"] = int(row["runtime"]) - int(
            baseline["runtime"]
        )
        row["runtime_change_pct_vs_molecule_baseline"] = (
            int(row["runtime"]) / int(baseline["runtime"]) - 1.0
        ) * 100.0
        row["factory_egress_blocked_delta_vs_molecule_baseline"] = int(
            row["factory_egress_blocked"]
        ) - int(baseline["factory_egress_blocked"])
        row["qubit_volume_change_pct_vs_molecule_baseline"] = (
            int(row["qubit_volume"]) / int(baseline["qubit_volume"]) - 1.0
        ) * 100.0
        enriched.append(row)
    return enriched


def _write_outputs(
    output_root: Path,
    rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> None:
    enriched = _enrich(rows, config["baseline_cases"])
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

    by_name = {str(row["case_name"]): row for row in enriched}
    lines = [
        "# H5/H6 8x8 Factory-Egress Generalization Sweep",
        "",
        "This fixed-circuit experiment tests whether the H7 zero-egress runtime penalty generalizes to lower-load H5/H6 circuits. Adjacent bans close factory `(3,3)` egress without moving logical qubits; equal-count remote bans control for lost usable cells.",
    ]
    for molecule in ("H5", "H6"):
        lines.extend(
            [
                "",
                f"## {molecule}",
                "",
                "| case | egress | bans | runtime | vs baseline | topology overhead | egress blocked | fail share | CNOT delta | nearest-factory delta | code distance | physical qubits | semantic match |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
            ]
        )
        for row in enriched:
            if row["molecule"] != molecule:
                continue
            lines.append(
                "| {case} | {egress} | {bans} | {runtime:,} | {runtime_pct:+.4f}% | {overhead:,} | {blocked:,} | {share:.3f}% | {cnot:+,} | {nearest:+,} | {distance} | {physical:,} | {match} |".format(
                    case=row["case_name"],
                    egress=int(row["trapped_coordinate_free_neighbors"]),
                    bans=int(row["banned_cell_count"]),
                    runtime=int(row["runtime"]),
                    runtime_pct=float(row["runtime_change_pct_vs_molecule_baseline"]),
                    overhead=int(row["runtime_topology_overhead"]),
                    blocked=int(row["factory_egress_blocked"]),
                    share=100.0 * float(row["factory_egress_blocked_fraction"]),
                    cnot=int(row["weighted_cnot_distance_delta_vs_baseline"]),
                    nearest=int(
                        row["weighted_nearest_factory_distance_delta_vs_baseline"]
                    ),
                    distance=int(row["code_distance"]),
                    physical=int(row["physical_qubits"]),
                    match="yes" if row["semantic_match"] else "no",
                )
            )

    h5_adjacent_1 = by_name["h5_egress_1_ban_left"]
    h5_remote_1 = by_name["h5_control_remote_ban_1"]
    h5_adjacent_2 = by_name["h5_egress_0_ban_both"]
    h5_remote_2 = by_name["h5_control_remote_ban_2"]
    h6_adjacent = by_name["h6_egress_0_ban_down"]
    h6_remote = by_name["h6_control_remote_ban_1"]
    h6_open = by_name["h6_egress_2_move_q0"]
    peak_rss = max(int(row["gnu_time_max_rss_kb"]) for row in enriched)
    lines.extend(
        [
            "",
            "## Controlled contrasts",
            "",
            "- H5 one-ban adjacent minus remote runtime: {:+,} beats ({:+.4f} percentage points vs baseline).".format(
                int(h5_adjacent_1["runtime"]) - int(h5_remote_1["runtime"]),
                float(h5_adjacent_1["runtime_change_pct_vs_molecule_baseline"])
                - float(h5_remote_1["runtime_change_pct_vs_molecule_baseline"]),
            ),
            "- H5 two-ban adjacent minus remote runtime: {:+,} beats ({:+.4f} percentage points vs baseline).".format(
                int(h5_adjacent_2["runtime"]) - int(h5_remote_2["runtime"]),
                float(h5_adjacent_2["runtime_change_pct_vs_molecule_baseline"])
                - float(h5_remote_2["runtime_change_pct_vs_molecule_baseline"]),
            ),
            "- H6 one-ban adjacent minus remote runtime: {:+,} beats ({:+.4f} percentage points vs baseline).".format(
                int(h6_adjacent["runtime"]) - int(h6_remote["runtime"]),
                float(h6_adjacent["runtime_change_pct_vs_molecule_baseline"])
                - float(h6_remote["runtime_change_pct_vs_molecule_baseline"]),
            ),
            "- H6 opening a second egress changes runtime by {:+,} beats ({:+.4f}%). This case moves only q0 and is therefore a directional check, not as clean as the ban contrasts.".format(
                int(h6_open["runtime_delta_vs_molecule_baseline"]),
                float(h6_open["runtime_change_pct_vs_molecule_baseline"]),
            ),
            "- H7 reference: zero to one egress reduced runtime by about 10.007%, while one to two egress produced no further improvement.",
            "- Circuit-semantic fields must match within each molecule; code-distance changes, if any, remain part of final resource output but not the fixed-circuit runtime intervention.",
            "",
            "## Execution resources",
            "",
            f"- peak qret RSS: {peak_rss:,} KiB ({peak_rss / 1024**2:.2f} GiB)",
            f"- maximum GNU-time swaps: {max(int(row['gnu_time_swaps']) for row in enriched)}",
            "- execution: sequential tmux session with `MemoryHigh=44G`, `MemoryMax=48G`",
            f"- diagnostic `libqret-core.so` SHA-256: `{enriched[0]['qret_core_library_hash']}`",
            f"- local diagnostic patch SHA-256: `{enriched[0]['diagnostic_patch_sha256']}`",
            "",
        ]
    )
    (output_root / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--qret", type=Path, default=DEFAULT_QRET)
    parser.add_argument("--diagnostic-patch", type=Path, default=DEFAULT_DIAGNOSTIC_PATCH)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    config = _load_config(args.config.expanduser().resolve())
    manifest_path = _resolve(config["topology_manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    variants = manifest["variants"]
    case_names = [str(name) for name in config["cases"]]
    if any(name not in variants for name in case_names):
        raise ValueError("config references an unknown topology variant")
    if args.dry_run:
        for name in case_names:
            record = variants[name]
            print(
                name,
                record["molecule"],
                record["trapped_coordinate_free_neighbors"],
                record["banned_cell_count"],
                record["weighted_cnot_distance_delta_vs_baseline"],
            )
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
    output_root = _resolve(config["output_directory"])
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
        row["banned_cells"] = json.dumps(record["banned_cells"])
        row["banned_cell_count"] = int(record["banned_cell_count"])
        row["usable_non_factory_cell_count"] = int(
            record["usable_non_factory_cell_count"]
        )
        rows.append(row)
        print(
            name,
            "runtime=",
            row["runtime"],
            "egress_blocked=",
            row["factory_egress_blocked"],
            flush=True,
        )

    _write_outputs(output_root, rows, config)
    shutil.rmtree(output_root / ".work", ignore_errors=True)
    if not all(bool(row["semantic_match"]) for row in rows):
        raise RuntimeError("one or more cases changed fixed circuit semantics")
    print(output_root / "summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
