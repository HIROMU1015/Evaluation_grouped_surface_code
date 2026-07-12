#!/usr/bin/env python3
"""Run paired-precision H4-H7 fixed-budget routing-capacity sweeps."""

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
    REPO_ROOT / "configs" / "surface_code_routing_capacity_sweep_h4_h7_4th_paired.yaml"
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


def _precision_label(precision: float) -> str:
    return f"{precision:.0e}"


def _case_name(molecule: str, precision: float, condition: str) -> str:
    return f"{molecule.lower()}_p{_precision_label(precision)}_{condition}"


def _source_rows(
    config: Mapping[str, Any],
) -> dict[tuple[str, float], dict[str, str]]:
    source = config["source"]
    with _resolve(source["results_csv"]).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    selected: dict[tuple[str, float], dict[str, str]] = {}
    for molecule_value in config["molecules"]:
        for precision_value in config["rotation_precisions"]:
            molecule = str(molecule_value)
            precision = float(precision_value)
            matches = [
                row
                for row in rows
                if row["molecule"] == molecule
                and row["topology_name"] == str(source["topology_name"])
                and row["pf_label"] == str(source["pf_label"])
                and float(row["rotation_precision"]) == precision
            ]
            if len(matches) != 1:
                raise RuntimeError(
                    f"expected one source row for {molecule}/{precision}, found {len(matches)}"
                )
            selected[(molecule, precision)] = matches[0]
    return selected


def _enrich(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    controls = {
        (str(row["molecule"]), float(row["rotation_precision"])): row
        for row in rows
        if row["routing_condition"] == "remote_ban_control"
    }
    enriched: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        key = (str(row["molecule"]), float(row["rotation_precision"]))
        control = controls[key]
        row["runtime_delta_vs_remote_control"] = int(row["runtime"]) - int(
            control["runtime"]
        )
        row["runtime_change_pct_vs_remote_control"] = (
            int(row["runtime"]) / int(control["runtime"]) - 1.0
        ) * 100.0
        row["qubit_volume_change_pct_vs_remote_control"] = (
            int(row["qubit_volume"]) / int(control["qubit_volume"]) - 1.0
        ) * 100.0
        enriched.append(row)
    return enriched


def _write_outputs(
    output_root: Path, rows: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    enriched = _enrich(rows)
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
        "# H4-H7 Paired-Precision Routing-Capacity Sweep",
        "",
        "The logical circuit is fixed within each precision. All routing conditions use the same 10x10 logical mapping, four factories, eight banned cells, 88 usable non-factory cells, and two initial egress cells per factory. Absolute runtime is not compared across precision as an architecture effect.",
    ]
    for precision in (1e-5, 1e-2):
        lines.extend(
            [
                "",
                f"## rotation_precision={_precision_label(precision)}",
                "",
                "| molecule | condition | runtime | vs remote | topology overhead | static CNOT delta | CNOT fail share | CNOT mean path | magic fail share | magic mean path | egress blocked | route disconnected | code distance | QV vs remote | semantic match |",
                "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
            ]
        )
        for row in enriched:
            if float(row["rotation_precision"]) != precision:
                continue
            lines.append(
                "| {molecule} | {condition} | {runtime:,} | {pct:+.4f}% | {overhead:,} | {static:+,} | {cnot_fail:.3f}% | {cnot_path:.3f} | {magic_fail:.3f}% | {magic_path:.3f} | {egress:,} | {disconnected:,} | {distance} | {qv:+.4f}% | {match} |".format(
                    molecule=row["molecule"],
                    condition=row["routing_condition"],
                    runtime=int(row["runtime"]),
                    pct=float(row["runtime_change_pct_vs_remote_control"]),
                    overhead=int(row["runtime_topology_overhead"]),
                    static=int(row["weighted_cnot_distance_delta_vs_baseline"]),
                    cnot_fail=100.0 * float(row["cnot_failed_attempt_fraction"]),
                    cnot_path=float(row["cnot_mean_path_coordinates"]),
                    magic_fail=100.0 * float(row["factory_egress_blocked_fraction"]),
                    magic_path=float(row["magic_mean_path_coordinates"]),
                    egress=int(row["factory_egress_blocked"]),
                    disconnected=int(row["magic_failure_route_disconnected"]),
                    distance=int(row["code_distance"]),
                    qv=float(row["qubit_volume_change_pct_vs_remote_control"]),
                    match="yes" if row["semantic_match"] else "no",
                )
            )

    by_key = {
        (str(row["molecule"]), float(row["rotation_precision"]), str(row["routing_condition"])): row
        for row in enriched
    }
    lines.extend(
        [
            "",
            "## Central-Choke Precision Comparison",
            "",
            "| molecule | runtime penalty at 1e-5 | runtime penalty at 1e-2 | CNOT path increase at 1e-5 | CNOT path increase at 1e-2 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for molecule in ("H4", "H5", "H6", "H7"):
        values = {}
        for precision in (1e-5, 1e-2):
            control = by_key[(molecule, precision, "remote_ban_control")]
            choke = by_key[(molecule, precision, "central_choke")]
            values[precision] = (
                float(choke["runtime_change_pct_vs_remote_control"]),
                float(choke["cnot_mean_path_coordinates"])
                / float(control["cnot_mean_path_coordinates"])
                - 1.0,
            )
        lines.append(
            "| {molecule} | {runtime_conv:+.4f}% | {runtime_cheap:+.4f}% | {path_conv:+.4f}% | {path_cheap:+.4f}% |".format(
                molecule=molecule,
                runtime_conv=values[1e-5][0],
                runtime_cheap=values[1e-2][0],
                path_conv=100.0 * values[1e-5][1],
                path_cheap=100.0 * values[1e-2][1],
            )
        )

    peak_rss = max(int(row["gnu_time_max_rss_kb"]) for row in enriched)
    lines.extend(
        [
            "",
            "## Validity and Execution",
            "",
            "- Static preflight confirms a route for every weighted CNOT pair and keeps all logical qubits in a connected routing graph.",
            "- The central choke preserves two initial egress cells per factory; runtime differences are not caused by the zero-egress pathology.",
            "- The detailed diagnostic reports operation-specific CNOT and magic attempt/path aggregates; it does not retain per-attempt traces.",
            f"- peak qret RSS: {peak_rss:,} KiB ({peak_rss / 1024**2:.2f} GiB)",
            f"- maximum GNU-time swaps: {max(int(row['gnu_time_swaps']) for row in enriched)}",
            "- intended execution: sequential tmux session with `MemoryHigh=44G`, `MemoryMax=48G`",
            f"- diagnostic `libqret-core.so` SHA-256: `{enriched[0]['qret_core_library_hash']}`",
            f"- local diagnostic patch SHA-256: `{enriched[0]['diagnostic_patch_sha256']}`",
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
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    config = _load_config(args.config.expanduser().resolve())
    manifest_path = _resolve(config["topology_manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    variants = manifest["variants"]
    sources = _source_rows(config)
    cases = [
        (str(molecule), float(precision), str(condition))
        for molecule in config["molecules"]
        for precision in config["rotation_precisions"]
        for condition in config["routing_conditions"]
    ]
    if args.dry_run:
        for molecule, precision, condition in cases:
            record = variants[f"{molecule.lower()}_{condition}"]
            print(
                _case_name(molecule, precision, condition),
                sources[(molecule, precision)]["cache_key"],
                record["minimum_initial_free_neighbors"],
                record["weighted_cnot_distance_delta_vs_baseline"],
            )
        return 0

    source_inputs: dict[tuple[str, float], tuple[Path, dict[str, Any]]] = {}
    for key, source_row in sources.items():
        source_yaml = routing._find_source_compile_yaml(source_row["cache_key"])
        source_inputs[key] = (
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
    for molecule, precision, condition in cases:
        source_row = sources[(molecule, precision)]
        source_yaml, source_compile_info = source_inputs[(molecule, precision)]
        record = variants[f"{molecule.lower()}_{condition}"]
        name = _case_name(molecule, precision, condition)
        row = micro._run_case(
            name,
            record,
            source_yaml=source_yaml,
            source_compile_info=source_compile_info,
            source_row=source_row,
            output_root=output_root,
            qret=qret,
            qret_hash=routing._sha256(qret),
            qret_core=qret_core,
            qret_core_hash=routing._sha256(qret_core),
            diagnostic_patch_hash=patch_hash,
        )
        row["routing_condition"] = condition
        row["banned_cells"] = json.dumps(record["banned_cells"])
        row["banned_cell_count"] = int(record["banned_cell_count"])
        row["usable_non_factory_cell_count"] = int(
            record["usable_non_factory_cell_count"]
        )
        row["minimum_initial_free_neighbors"] = int(
            record["minimum_initial_free_neighbors"]
        )
        row["obstacle_aware_cnot_max_distance"] = int(
            record["obstacle_aware_cnot_max_distance"]
        )
        rows.append(row)
        print(
            name,
            "runtime=",
            row["runtime"],
            "cnot_fail=",
            row["cnot_failed_attempts"],
            "cnot_path=",
            f"{row['cnot_mean_path_coordinates']:.3f}",
            flush=True,
        )

    enriched = _write_outputs(output_root, rows)
    shutil.rmtree(output_root / ".work", ignore_errors=True)
    if not all(bool(row["semantic_match"]) for row in enriched):
        raise RuntimeError("one or more cases changed fixed circuit semantics")
    print(output_root / "summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
