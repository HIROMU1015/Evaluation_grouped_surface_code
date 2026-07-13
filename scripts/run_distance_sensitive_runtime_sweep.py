#!/usr/bin/env python3
"""Run distance-sensitive Dim2 routing and scheduling for fixed circuits."""

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

from scripts import run_distance_sensitive_latency_sweep as proxy  # noqa: E402
from scripts import run_factory_saturation_sweep as factory  # noqa: E402
from scripts import run_qret_runtime_routing_diagnostic as routing  # noqa: E402


DEFAULT_CONFIG = (
    REPO_ROOT
    / "configs"
    / "surface_code_distance_sensitive_runtime_sweep_h4_h7_4th_paired.yaml"
)
DEFAULT_QRET = Path("/tmp/evaluation-qret-distance-runtime/qret")
LATENCY_ENV = "QRET_SC_LS_PATH_LATENCY_PER_ADDITIONAL_COORDINATE"
STATS_FIELDS = (
    "distance_sensitive_path_latency_factor",
    "distance_sensitive_path_latency_added",
    "distance_sensitive_path_latency_max",
    "distance_sensitive_path_instruction_count",
)
FACTOR_ZERO_COMPATIBILITY_TOLERANCE_PCT = 0.002


def _pct(value: int | float, reference: int | float) -> float:
    return (float(value) / float(reference) - 1.0) * 100.0


def _key(row: Mapping[str, Any]) -> tuple[str, float, str, str, int]:
    return (
        str(row["molecule"]),
        float(row["rotation_precision"]),
        str(row["diagnostic_family"]),
        str(row["diagnostic_condition"]),
        int(row["path_latency_factor"]),
    )


def _load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _enrich(
    rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    proxy_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    by_key = {_key(row): row for row in rows}
    proxy_by_key = {_key(row): row for row in proxy_rows}
    enriched: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        molecule, precision, family, condition, factor = _key(row)
        reference_condition = str(config["families"][family]["reference"])
        reference = by_key[(molecule, precision, family, reference_condition, factor)]
        fixed = by_key[(molecule, precision, family, condition, 0)]
        proxy_same = proxy_by_key[(molecule, precision, family, condition, factor)]
        proxy_reference = proxy_by_key[
            (molecule, precision, family, reference_condition, factor)
        ]

        row["runtime_change_pct_vs_family_reference"] = _pct(
            int(row["runtime"]), int(reference["runtime"])
        )
        row["physical_runtime_change_pct_vs_family_reference"] = _pct(
            int(row["runtime"]) * int(row["code_distance"]),
            int(reference["runtime"]) * int(reference["code_distance"]),
        )
        row["qubit_volume_change_pct_vs_family_reference"] = _pct(
            int(row["qubit_volume"]), int(reference["qubit_volume"])
        )
        row["runtime_change_pct_vs_fixed_latency_same_topology"] = _pct(
            int(row["runtime"]), int(fixed["runtime"])
        )
        row["qubit_volume_change_pct_vs_fixed_latency_same_topology"] = _pct(
            int(row["qubit_volume"]), int(fixed["qubit_volume"])
        )
        row["proxy_depth_change_pct_vs_family_reference"] = _pct(
            int(proxy_same["diagnostic_path_latency_dependency_depth"]),
            int(proxy_reference["diagnostic_path_latency_dependency_depth"]),
        )
        row["runtime_penalty_minus_proxy_percentage_points"] = (
            float(row["runtime_change_pct_vs_family_reference"])
            - float(row["proxy_depth_change_pct_vs_family_reference"])
        )
        if factor == 0:
            previous_runtime = int(proxy_same["runtime"])
            previous_qubit_volume = int(proxy_same["qubit_volume"])
            runtime_delta = int(row["runtime"]) - previous_runtime
            qubit_volume_delta = int(row["qubit_volume"]) - previous_qubit_volume
            runtime_delta_pct = _pct(int(row["runtime"]), previous_runtime)
            qubit_volume_delta_pct = _pct(
                int(row["qubit_volume"]), previous_qubit_volume
            )
            row["factor_zero_previous_runtime"] = previous_runtime
            row["factor_zero_runtime_delta_beats"] = runtime_delta
            row["factor_zero_runtime_delta_pct"] = runtime_delta_pct
            row["factor_zero_previous_qubit_volume"] = previous_qubit_volume
            row["factor_zero_qubit_volume_delta"] = qubit_volume_delta
            row["factor_zero_qubit_volume_delta_pct"] = qubit_volume_delta_pct
            row["factor_zero_runtime_matches_previous_run"] = (
                runtime_delta == 0
            )
            row["factor_zero_qubit_volume_matches_previous_run"] = (
                qubit_volume_delta == 0
            )
            row["factor_zero_runtime_within_tolerance"] = (
                abs(runtime_delta_pct) <= FACTOR_ZERO_COMPATIBILITY_TOLERANCE_PCT
            )
            row["factor_zero_qubit_volume_within_tolerance"] = (
                abs(qubit_volume_delta_pct)
                <= FACTOR_ZERO_COMPATIBILITY_TOLERANCE_PCT
            )
        else:
            row["factor_zero_previous_runtime"] = None
            row["factor_zero_runtime_delta_beats"] = None
            row["factor_zero_runtime_delta_pct"] = None
            row["factor_zero_previous_qubit_volume"] = None
            row["factor_zero_qubit_volume_delta"] = None
            row["factor_zero_qubit_volume_delta_pct"] = None
            row["factor_zero_runtime_matches_previous_run"] = None
            row["factor_zero_qubit_volume_matches_previous_run"] = None
            row["factor_zero_runtime_within_tolerance"] = None
            row["factor_zero_qubit_volume_within_tolerance"] = None
        enriched.append(row)
    return enriched


def _completed_rows(
    output_root: Path,
    cases: Sequence[tuple[str, float, str, str, int]],
) -> list[dict[str, Any]]:
    rows = []
    for case in cases:
        path = output_root / "checkpoints" / f"{proxy._case_name(*case)}.json"
        if path.exists():
            rows.append(routing._load_json(path))
    return rows


def _write_outputs(
    output_root: Path,
    rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    proxy_rows = _load_csv(factory._resolve(config["proxy_results"]))
    enriched = _enrich(rows, config, proxy_rows)
    factory._write_rows(output_root / "results.jsonl", enriched)
    excluded = {
        "gate_count_detail",
        "workload_differences",
        "execution_environment",
        "case_metadata",
    }
    fields = [field for field in enriched[0] if field not in excluded]
    with (output_root / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(enriched)

    by_key = {_key(row): row for row in enriched}
    lines = [
        "# Dim2 Distance-Sensitive Routing Runtime",
        "",
        "The routed operations use `base_latency + factor * max(path_coordinates - 1, 0)` during routing, resource occupancy, dependency release, runtime, and qubit-volume calculation. Factor 0 is the compatibility control; factor 1 is a diagnostic model, not a calibrated hardware latency.",
        "",
        "| precision | molecule | family | stress | factor-0 runtime penalty | factor-1 runtime penalty | proxy depth penalty | full minus proxy | stress runtime increase vs factor 0 | physical runtime penalty | factor-1 QV penalty |",
        "|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
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
                    "| {precision} | {molecule} | {family} | {stress} | {fixed:+.4f}% | {runtime:+.4f}% | {proxy:+.4f}% | {delta:+.4f} pp | {model:+.4f}% | {physical:+.4f}% | {qv:+.4f}% |".format(
                        precision=factory._precision_label(precision),
                        molecule=molecule,
                        family=family,
                        stress=stress,
                        fixed=float(fixed["runtime_change_pct_vs_family_reference"]),
                        runtime=float(distance["runtime_change_pct_vs_family_reference"]),
                        proxy=float(distance["proxy_depth_change_pct_vs_family_reference"]),
                        delta=float(distance["runtime_penalty_minus_proxy_percentage_points"]),
                        model=float(distance["runtime_change_pct_vs_fixed_latency_same_topology"]),
                        physical=float(distance["physical_runtime_change_pct_vs_family_reference"]),
                        qv=float(distance["qubit_volume_change_pct_vs_family_reference"]),
                    )
                )
    factor_zero = [row for row in enriched if int(row["path_latency_factor"]) == 0]
    runtime_exact = sum(
        bool(row["factor_zero_runtime_matches_previous_run"]) for row in factor_zero
    )
    qv_exact = sum(
        bool(row["factor_zero_qubit_volume_matches_previous_run"]) for row in factor_zero
    )
    maximum_runtime_delta_beats = max(
        abs(int(row["factor_zero_runtime_delta_beats"])) for row in factor_zero
    )
    maximum_runtime_delta_pct = max(
        abs(float(row["factor_zero_runtime_delta_pct"])) for row in factor_zero
    )
    maximum_qv_delta_pct = max(
        abs(float(row["factor_zero_qubit_volume_delta_pct"])) for row in factor_zero
    )
    compatibility_within_tolerance = all(
        bool(row["factor_zero_runtime_within_tolerance"])
        and bool(row["factor_zero_qubit_volume_within_tolerance"])
        for row in factor_zero
    )
    lines.extend(
        [
            "",
            f"- factor-0 exact runtime matches: `{runtime_exact}/{len(factor_zero)}`",
            f"- factor-0 maximum runtime delta: `{maximum_runtime_delta_beats} beats ({maximum_runtime_delta_pct:.6f}%)`",
            f"- factor-0 exact qubit-volume matches: `{qv_exact}/{len(factor_zero)}`",
            f"- factor-0 maximum qubit-volume delta: `{maximum_qv_delta_pct:.6f}%`",
            f"- factor-0 compatibility within `{FACTOR_ZERO_COMPATIBILITY_TOLERANCE_PCT:.3f}%`: `{compatibility_within_tolerance}`",
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
    all_cases = proxy._cases(config)
    cases = proxy._select_cases(all_cases, args.case_names)
    if args.dry_run:
        for case in cases:
            record = proxy._topology_record(
                placement_manifest, routing_manifest, case[0], case[2], case[3]
            )
            print(proxy._case_name(*case), record["topology_path"])
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
        source_inputs[key] = (
            source_yaml,
            routing._load_json(source_yaml.with_name("compile_info.json")),
        )

    def run(case: tuple[str, float, str, str, int]) -> dict[str, Any]:
        molecule, precision, family, condition, factor = case
        source_row = sources[(molecule, precision)]
        source_yaml, source_info = source_inputs[(molecule, precision)]
        record = proxy._topology_record(
            placement_manifest, routing_manifest, molecule, family, condition
        )
        row = factory._run_case(
            molecule,
            precision,
            4,
            case_name=proxy._case_name(*case),
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
                "state_buffer_width": int(config["execution"]["state_buffer_width"]),
                "diagnostic_patch_sha256": patch_hash,
            },
        )
        observed = routing._load_json(factory._resolve(row["compile_info_path"]))
        for field in STATS_FIELDS:
            row[field] = int(observed[field])
        if int(row["distance_sensitive_path_latency_factor"]) != factor:
            raise RuntimeError(f"latency factor mismatch for {row['case_name']}")
        factory._write_json(output_root / "checkpoints" / f"{row['case_name']}.json", row)
        return row

    parallelism = args.case_parallelism or int(config["execution"]["case_parallelism"])
    failures = []
    with ThreadPoolExecutor(max_workers=min(parallelism, len(cases))) as pool:
        futures = {pool.submit(run, case): case for case in cases}
        for future in as_completed(futures):
            case = futures[future]
            try:
                row = future.result()
                print(
                    row["case_name"],
                    f"runtime={row['runtime']}",
                    f"rss_kib={row['gnu_time_max_rss_kb']}",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001
                failures.append((proxy._case_name(*case), exc))
                print(f"FAILED {proxy._case_name(*case)}: {exc}", file=sys.stderr, flush=True)
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
