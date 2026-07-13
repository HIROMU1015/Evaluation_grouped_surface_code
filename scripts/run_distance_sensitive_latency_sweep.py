#!/usr/bin/env python3
"""Run a fixed-circuit Dim2 path-length-sensitive latency diagnostic."""

from __future__ import annotations

import argparse
import csv
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import run_factory_saturation_sweep as factory  # noqa: E402
from scripts import run_qret_runtime_routing_diagnostic as routing  # noqa: E402


DEFAULT_CONFIG = (
    REPO_ROOT
    / "configs"
    / "surface_code_distance_sensitive_latency_sweep_h4_h7_4th_paired.yaml"
)
DEFAULT_QRET = Path("/tmp/evaluation-qret-distance-latency/qret")
LATENCY_ENV = "QRET_SC_LS_PATH_LATENCY_PER_ADDITIONAL_COORDINATE"


def _case_name(
    molecule: str,
    precision: float,
    family: str,
    condition: str,
    factor: int,
) -> str:
    return (
        f"{molecule.lower()}_p{factory._precision_label(precision)}_"
        f"{family}_{condition}_latency{factor}"
    )


def _cases(config: Mapping[str, Any]) -> list[tuple[str, float, str, str, int]]:
    return [
        (str(molecule), float(precision), str(family), str(condition), int(factor))
        for molecule in config["molecules"]
        for precision in config["rotation_precisions"]
        for family, family_config in config["families"].items()
        for condition in family_config["conditions"]
        for factor in config["path_latency_factors"]
    ]


def _select_cases(
    cases: Sequence[tuple[str, float, str, str, int]], requested: Sequence[str]
) -> list[tuple[str, float, str, str, int]]:
    if not requested:
        return list(cases)
    by_name = {_case_name(*case): case for case in cases}
    unknown = sorted(set(requested) - set(by_name))
    if unknown:
        raise ValueError(f"unknown --case value(s): {', '.join(unknown)}")
    wanted = set(requested)
    return [case for case in cases if _case_name(*case) in wanted]


def _placement_record(manifest: Mapping[str, Any], molecule: str, condition: str) -> dict[str, Any]:
    placement_name = {
        "compact": "compact_interaction_aware",
        "perimeter": "perimeter_numeric",
    }[condition]
    record = manifest["molecules"][molecule]["placements"][placement_name]
    mapping = record["mapping"]
    factories = [item["coord"] for item in manifest["magic_factories"]]
    distances = [
        min(abs(coord[0] - factory_coord[0]) + abs(coord[1] - factory_coord[1]) for factory_coord in factories)
        for item in mapping
        for coord in [item["coord"]]
    ]
    return {
        "topology_path": record["topology_path"],
        "factory_plus_ban_cell_count": 4,
        "usable_non_factory_cell_count": 96,
        "minimum_initial_free_neighbors": 2,
        "weighted_cnot_distance": int(record["weighted_cnot_distance"]),
        "weighted_nearest_factory_distance": sum(distances),
        "weighted_nearest_factory_distance_mean": sum(distances) / len(distances),
    }


def _routing_record(manifest: Mapping[str, Any], molecule: str, condition: str) -> dict[str, Any]:
    routing_name = {"remote": "remote_ban_control", "choke": "central_choke"}[condition]
    source = manifest["variants"][f"{molecule.lower()}_{routing_name}"]
    return {
        **source,
        "factory_plus_ban_cell_count": int(source["banned_cell_count"]) + 4,
    }


def _topology_record(
    placement_manifest: Mapping[str, Any],
    routing_manifest: Mapping[str, Any],
    molecule: str,
    family: str,
    condition: str,
) -> dict[str, Any]:
    if family == "placement":
        return _placement_record(placement_manifest, molecule, condition)
    if family == "routing":
        return _routing_record(routing_manifest, molecule, condition)
    raise ValueError(f"unknown family: {family}")


def _enrich(
    rows: Sequence[Mapping[str, Any]], config: Mapping[str, Any]
) -> list[dict[str, Any]]:
    by_key = {
        (
            str(row["molecule"]),
            float(row["rotation_precision"]),
            str(row["diagnostic_family"]),
            str(row["diagnostic_condition"]),
            int(row["path_latency_factor"]),
        ): row
        for row in rows
    }
    enriched = []
    for raw in rows:
        row = dict(raw)
        molecule = str(row["molecule"])
        precision = float(row["rotation_precision"])
        family = str(row["diagnostic_family"])
        condition = str(row["diagnostic_condition"])
        factor = int(row["path_latency_factor"])
        reference_condition = str(config["families"][family]["reference"])
        reference = by_key[(molecule, precision, family, reference_condition, factor)]
        fixed_latency = by_key[(molecule, precision, family, condition, 0)]
        row["dependency_depth_change_pct_vs_family_reference"] = (
            int(row["diagnostic_path_latency_dependency_depth"])
            / int(reference["diagnostic_path_latency_dependency_depth"])
            - 1.0
        ) * 100.0
        row["physical_dependency_depth_change_pct_vs_family_reference"] = (
            int(row["diagnostic_path_latency_dependency_depth"])
            * int(row["code_distance"])
            / (
                int(reference["diagnostic_path_latency_dependency_depth"])
                * int(reference["code_distance"])
            )
            - 1.0
        ) * 100.0
        row["qubit_volume_change_pct_vs_family_reference"] = (
            int(row["qubit_volume"]) / int(reference["qubit_volume"]) - 1.0
        ) * 100.0
        row["dependency_depth_change_pct_vs_fixed_latency_same_topology"] = (
            int(row["diagnostic_path_latency_dependency_depth"])
            / int(fixed_latency["diagnostic_path_latency_dependency_depth"])
            - 1.0
        ) * 100.0
        stress_fixed = by_key[(molecule, precision, family, condition, 0)]
        reference_fixed = by_key[(molecule, precision, family, reference_condition, 0)]
        baseline_penalty = (
            int(stress_fixed["diagnostic_path_latency_dependency_depth"])
            / int(reference_fixed["diagnostic_path_latency_dependency_depth"])
            - 1.0
        ) * 100.0
        row["reference_penalty_amplification_percentage_points"] = (
            float(row["dependency_depth_change_pct_vs_family_reference"])
            - baseline_penalty
        )
        enriched.append(row)
    return enriched


def _completed_rows(output_root: Path, cases: Sequence[tuple[str, float, str, str, int]]) -> list[dict[str, Any]]:
    rows = []
    for case in cases:
        path = output_root / "checkpoints" / f"{_case_name(*case)}.json"
        if path.exists():
            rows.append(routing._load_json(path))
    return rows


def _write_outputs(output_root: Path, rows: Sequence[Mapping[str, Any]], config: Mapping[str, Any]) -> list[dict[str, Any]]:
    enriched = _enrich(rows, config)
    factory._write_rows(output_root / "results.jsonl", enriched)
    excluded = {"gate_count_detail", "workload_differences", "execution_environment", "case_metadata"}
    fields = [field for field in enriched[0] if field not in excluded]
    with (output_root / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(enriched)

    by_key = {
        (
            str(row["molecule"]),
            float(row["rotation_precision"]),
            str(row["diagnostic_family"]),
            str(row["diagnostic_condition"]),
            int(row["path_latency_factor"]),
        ): row
        for row in enriched
    }
    lines = [
        "# Dim2 Distance-Sensitive Latency Diagnostic",
        "",
        "This is a diagnostic critical-path proxy, not a rerouted runtime, STAR, or hardware implementation. Factor 0 uses fixed instruction latency; factor 1 adds one node-weight beat per path coordinate after the first and recomputes the routed instruction DAG's longest dependency depth.",
        "",
        "| precision | molecule | family | stress condition | fixed-latency depth penalty | distance-sensitive depth penalty | amplification | stress depth increase from latency model | physical-depth penalty | existing QV penalty |",
        "|---:|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for precision_value in config["rotation_precisions"]:
        precision = float(precision_value)
        for molecule_value in config["molecules"]:
            molecule = str(molecule_value)
            for family, family_config in config["families"].items():
                reference = str(family_config["reference"])
                stress = next(value for value in family_config["conditions"] if value != reference)
                fixed = by_key[(molecule, precision, family, stress, 0)]
                distance = by_key[(molecule, precision, family, stress, 1)]
                lines.append(
                    "| {precision} | {molecule} | {family} | {stress} | {fixed:+.4f}% | {distance:+.4f}% | {amplification:+.4f} pp | {model:+.4f}% | {physical:+.4f}% | {qv:+.4f}% |".format(
                        precision=factory._precision_label(precision),
                        molecule=molecule,
                        family=family,
                        stress=stress,
                        fixed=float(fixed["dependency_depth_change_pct_vs_family_reference"]),
                        distance=float(distance["dependency_depth_change_pct_vs_family_reference"]),
                        amplification=float(distance["reference_penalty_amplification_percentage_points"]),
                        model=float(distance["dependency_depth_change_pct_vs_fixed_latency_same_topology"]),
                        physical=float(distance["physical_dependency_depth_change_pct_vs_family_reference"]),
                        qv=float(distance["qubit_volume_change_pct_vs_family_reference"]),
                    )
                )
    lines.extend(
        [
            "",
            f"- fixed-workload checks passed: `{all(bool(row['fixed_logical_workload_match']) for row in enriched)}`",
            f"- peak per-case RSS: `{max(int(row['gnu_time_max_rss_kb']) for row in enriched) / 1024**2:.2f} GiB`",
            f"- maximum swaps: `{max(int(row['gnu_time_swaps']) for row in enriched)}`",
            f"- diagnostic patch SHA-256: `{enriched[0]['diagnostic_patch_sha256']}`",
            "",
        ]
    )
    (output_root / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    return enriched


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--qret", type=Path, default=DEFAULT_QRET)
    parser.add_argument("--case", dest="case_names", action="append", default=[])
    parser.add_argument("--case-parallelism", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--summarize-existing", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    config = factory._load_config(args.config.expanduser().resolve())
    placement_manifest = routing._load_json(factory._resolve(config["placement_manifest"]))
    routing_manifest = routing._load_json(factory._resolve(config["routing_manifest"]))
    sources = factory._source_rows(config)
    all_cases = _cases(config)
    cases = _select_cases(all_cases, args.case_names)
    if args.dry_run:
        for case in cases:
            record = _topology_record(placement_manifest, routing_manifest, case[0], case[2], case[3])
            print(_case_name(*case), record["topology_path"])
        return 0

    output_root = factory._resolve(config["output_directory"])
    output_root.mkdir(parents=True, exist_ok=True)
    if args.summarize_existing:
        completed = _completed_rows(output_root, all_cases)
        if len(completed) != len(all_cases):
            raise RuntimeError(f"partial sweep: {len(completed)}/{len(all_cases)}")
        _write_outputs(output_root, completed, config)
        return 0

    qret = args.qret.expanduser().resolve()
    if not qret.exists():
        raise FileNotFoundError(f"diagnostic qret not found: {qret}")
    qret_core = routing._linked_qret_core(qret)
    qret_hash = routing._sha256(qret)
    qret_core_hash = routing._sha256(qret_core)
    patch_hash = routing._sha256(factory._resolve(config["diagnostic_patch"]))
    source_inputs = {}
    for key, source_row in sources.items():
        source_yaml = routing._find_source_compile_yaml(source_row["cache_key"])
        source_inputs[key] = (source_yaml, routing._load_json(source_yaml.with_name("compile_info.json")))

    def run(case: tuple[str, float, str, str, int]) -> dict[str, Any]:
        molecule, precision, family, condition, factor = case
        source_row = sources[(molecule, precision)]
        source_yaml, source_info = source_inputs[(molecule, precision)]
        record = _topology_record(placement_manifest, routing_manifest, molecule, family, condition)
        row = factory._run_case(
            molecule,
            precision,
            4,
            case_name=_case_name(*case),
            source_row=source_row,
            source_yaml=source_yaml,
            source_compile_info=source_info,
            topology_record=record,
            fixed=config["fixed_conditions"],
            output_root=output_root,
            qret=qret,
            qret_hash=qret_hash,
            qret_core=qret_core,
            qret_core_hash=qret_core_hash,
            force=args.force,
            execution_environment={LATENCY_ENV: str(factor)},
            case_metadata={
                "diagnostic_family": family,
                "diagnostic_condition": condition,
                "path_latency_factor": factor,
                "diagnostic_patch_sha256": patch_hash,
            },
        )
        observed = routing._load_json(factory._resolve(row["compile_info_path"]))
        for field in (
            "diagnostic_path_latency_factor",
            "diagnostic_path_latency_dependency_depth",
            "diagnostic_path_latency_added_weight",
        ):
            row[field] = int(observed[field])
        factory._write_json(
            output_root / "checkpoints" / f"{row['case_name']}.json", row
        )
        return row

    parallelism = args.case_parallelism or int(config["execution"]["case_parallelism"])
    failures = []
    with ThreadPoolExecutor(max_workers=min(parallelism, len(cases))) as pool:
        futures = {pool.submit(run, case): case for case in cases}
        for future in as_completed(futures):
            case = futures[future]
            try:
                row = future.result()
                print(row["case_name"], f"runtime={row['runtime']}", f"rss_kib={row['gnu_time_max_rss_kb']}", flush=True)
            except Exception as exc:  # noqa: BLE001
                failures.append((_case_name(*case), exc))
                print(f"FAILED {_case_name(*case)}: {exc}", file=sys.stderr, flush=True)
    if failures:
        raise RuntimeError(f"{len(failures)} case(s) failed")
    completed = _completed_rows(output_root, all_cases)
    if len(completed) == len(all_cases):
        _write_outputs(output_root, completed, config)
        print(output_root / "summary.md")
    else:
        factory._write_rows(output_root / "results.partial.jsonl", completed)
        print(f"partial sweep: {len(completed)}/{len(all_cases)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
