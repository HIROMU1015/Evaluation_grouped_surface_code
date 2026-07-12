#!/usr/bin/env python3
"""Run paired-precision H4-H7 reaction-time sweeps on fixed circuits."""

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
    REPO_ROOT / "configs" / "surface_code_reaction_time_sweep_h4_h7_4th_paired.yaml"
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


def _case_name(molecule: str, precision: float, reaction_time: int) -> str:
    return f"{molecule.lower()}_p{_precision_label(precision)}_r{reaction_time}"


def _source_rows(
    config: Mapping[str, Any],
) -> dict[tuple[str, float], dict[str, str]]:
    source = config["source"]
    with _resolve(source["results_csv"]).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    selected: dict[tuple[str, float], dict[str, str]] = {}
    for molecule in config["molecules"]:
        for precision_value in config["rotation_precisions"]:
            molecule = str(molecule)
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


def _fixed_logical_workload_match(row: Mapping[str, Any]) -> bool:
    differences = dict(row.get("semantic_differences", {}))
    return not differences or set(differences) == {"runtime_without_topology"}


def _enrich(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_group_reaction = {
        (str(row["molecule"]), float(row["rotation_precision"]), int(row["reaction_time"])): row
        for row in rows
    }
    enriched: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        molecule = str(row["molecule"])
        precision = float(row["rotation_precision"])
        reaction_time = int(row["reaction_time"])
        baseline = by_group_reaction[(molecule, precision, 1)]
        runtime_delta = int(row["runtime"]) - int(baseline["runtime"])
        row["runtime_delta_vs_reaction_1"] = runtime_delta
        row["runtime_change_pct_vs_reaction_1"] = (
            int(row["runtime"]) / int(baseline["runtime"]) - 1.0
        ) * 100.0
        row["qubit_volume_change_pct_vs_reaction_1"] = (
            int(row["qubit_volume"]) / int(baseline["qubit_volume"]) - 1.0
        ) * 100.0
        row["runtime_delta_per_extra_reaction_cycle"] = (
            runtime_delta / (reaction_time - 1) if reaction_time > 1 else None
        )
        denominator = int(row["measurement_feedback_depth"]) * (reaction_time - 1)
        row["effective_serial_feedback_fraction"] = (
            runtime_delta / denominator if denominator > 0 else None
        )
        row["fixed_logical_workload_match"] = _fixed_logical_workload_match(row)
        row["expected_architecture_differences_only"] = bool(
            row["fixed_logical_workload_match"] and not row["semantic_match"]
        )
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
        "# H4-H7 Paired-Precision Reaction-Time Sweep",
        "",
        "The logical circuit is fixed within each precision. The 10x10 mapping, four accessible factories, factory egress, magic supply, and QEC inputs are fixed across reaction-time cases. Absolute runtime is not compared across precision as an architecture effect.",
    ]
    for precision in (1e-5, 1e-2):
        lines.extend(
            [
                "",
                f"## rotation_precision={_precision_label(precision)}",
                "",
                "| molecule | reaction | runtime | vs reaction=1 | delta/extra cycle | serial feedback fraction | topology overhead | classical wait | condition wait | no stock | code distance | QV vs reaction=1 | workload match |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
            ]
        )
        for row in enriched:
            if float(row["rotation_precision"]) != precision:
                continue
            delta_per_cycle = row["runtime_delta_per_extra_reaction_cycle"]
            serial_fraction = row["effective_serial_feedback_fraction"]
            lines.append(
                "| {molecule} | {reaction} | {runtime:,} | {pct:+.4f}% | {delta} | {fraction} | {overhead:,} | {classical:,} | {condition:,} | {stock:,} | {distance} | {qv:+.4f}% | {match} |".format(
                    molecule=row["molecule"],
                    reaction=int(row["reaction_time"]),
                    runtime=int(row["runtime"]),
                    pct=float(row["runtime_change_pct_vs_reaction_1"]),
                    delta=(
                        "reference"
                        if delta_per_cycle is None
                        else f"{float(delta_per_cycle):,.3f}"
                    ),
                    fraction=(
                        "reference"
                        if serial_fraction is None
                        else f"{float(serial_fraction):.6f}"
                    ),
                    overhead=int(row["runtime_topology_overhead"]),
                    classical=int(row["magic_failure_classical_dependency_wait"]),
                    condition=int(row["magic_failure_condition_wait"]),
                    stock=int(row["magic_failure_no_magic_stock"]),
                    distance=int(row["code_distance"]),
                    qv=float(row["qubit_volume_change_pct_vs_reaction_1"]),
                    match="yes" if row["fixed_logical_workload_match"] else "no",
                )
            )

    by_key = {
        (str(row["molecule"]), float(row["rotation_precision"]), int(row["reaction_time"])): row
        for row in enriched
    }
    lines.extend(
        [
            "",
            "## Precision-Regime Sensitivity",
            "",
            "| molecule | reaction=10 penalty at 1e-5 | reaction=10 penalty at 1e-2 | reaction=100 penalty at 1e-5 | reaction=100 penalty at 1e-2 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for molecule in ("H4", "H5", "H6", "H7"):
        lines.append(
            "| {molecule} | {p10_conv:+.4f}% | {p10_cheap:+.4f}% | {p100_conv:+.4f}% | {p100_cheap:+.4f}% |".format(
                molecule=molecule,
                p10_conv=float(
                    by_key[(molecule, 1e-5, 10)]["runtime_change_pct_vs_reaction_1"]
                ),
                p10_cheap=float(
                    by_key[(molecule, 1e-2, 10)]["runtime_change_pct_vs_reaction_1"]
                ),
                p100_conv=float(
                    by_key[(molecule, 1e-5, 100)]["runtime_change_pct_vs_reaction_1"]
                ),
                p100_cheap=float(
                    by_key[(molecule, 1e-2, 100)]["runtime_change_pct_vs_reaction_1"]
                ),
            )
        )

    peak_rss = max(int(row["gnu_time_max_rss_kb"]) for row in enriched)
    lines.extend(
        [
            "",
            "## Validity and Execution",
            "",
            "- Fixed logical workload must match within each molecule/precision; reaction time may change only architecture-dependent runtime fields.",
            "- Feedback count/depth are fixed within each molecule/precision and are coupled to magic-state injection in the current circuit.",
            "- Reaction values 1/10/100 are diagnostic cycle counts, not a claim about a specific controller implementation.",
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
        (str(molecule), float(precision), int(reaction_time))
        for molecule in config["molecules"]
        for precision in config["rotation_precisions"]
        for reaction_time in config["reaction_times"]
    ]
    if args.dry_run:
        for molecule, precision, reaction_time in cases:
            source = sources[(molecule, precision)]
            print(
                _case_name(molecule, precision, reaction_time),
                source["cache_key"],
                f"topology={molecule.lower()}_factory_count_4",
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
    for molecule, precision, reaction_time in cases:
        source_row = sources[(molecule, precision)]
        source_yaml, source_compile_info = source_inputs[(molecule, precision)]
        topology_record = variants[f"{molecule.lower()}_factory_count_4"]
        name = _case_name(molecule, precision, reaction_time)
        row = micro._run_case(
            name,
            topology_record,
            source_yaml=source_yaml,
            source_compile_info=source_compile_info,
            source_row=source_row,
            output_root=output_root,
            qret=qret,
            qret_hash=routing._sha256(qret),
            qret_core=qret_core,
            qret_core_hash=routing._sha256(qret_core),
            diagnostic_patch_hash=patch_hash,
            pipeline_overrides={"sc_ls_fixed_v0_reaction_time": reaction_time},
        )
        rows.append(row)
        print(
            name,
            "runtime=",
            row["runtime"],
            "classical_wait=",
            row["magic_failure_classical_dependency_wait"],
            "condition_wait=",
            row["magic_failure_condition_wait"],
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
