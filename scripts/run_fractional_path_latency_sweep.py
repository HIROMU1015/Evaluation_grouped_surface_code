#!/usr/bin/env python3
"""Run fractional path-latency sensitivity and intermediate-topology checks."""

from __future__ import annotations

import argparse
import csv
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
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
    / "surface_code_fractional_path_latency_sweep_h4_h6_4th_paired.yaml"
)
DEFAULT_QRET = Path("/tmp/evaluation-qret-fractional-latency/qret")
NUMERATOR_ENV = "QRET_SC_LS_PATH_LATENCY_NUMERATOR"
DENOMINATOR_ENV = "QRET_SC_LS_PATH_LATENCY_DENOMINATOR"
STATS_FIELDS = (
    "distance_sensitive_path_latency_numerator",
    "distance_sensitive_path_latency_denominator",
    "distance_sensitive_path_latency_added",
    "distance_sensitive_path_latency_max",
    "distance_sensitive_path_instruction_count",
)


@dataclass(frozen=True)
class Case:
    stage: str
    molecule: str
    precision: float
    family: str
    condition: str
    model: str
    numerator: int
    denominator: int


def _pct(value: int | float, reference: int | float) -> float:
    return (float(value) / float(reference) - 1.0) * 100.0


def _load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _case_name(case: Case) -> str:
    return (
        f"{case.molecule.lower()}_p{factory._precision_label(case.precision)}_"
        f"{case.family}_{case.condition}_latency_{case.model}"
    )


def _cases(config: Mapping[str, Any]) -> list[Case]:
    models = config["latency_models"]
    cases: list[Case] = []
    for stage_name, stage in config["stages"].items():
        for molecule in stage["molecules"]:
            for precision in config["rotation_precisions"]:
                for family, family_config in config["families"].items():
                    for condition in family_config["conditions"]:
                        for model_name in stage["latency_models"]:
                            model = models[model_name]
                            numerator = int(model["numerator"])
                            denominator = int(model["denominator"])
                            if numerator < 0 or denominator <= 0:
                                raise ValueError(f"invalid latency model: {model_name}")
                            cases.append(
                                Case(
                                    str(stage_name),
                                    str(molecule),
                                    float(precision),
                                    str(family),
                                    str(condition),
                                    str(model_name),
                                    numerator,
                                    denominator,
                                )
                            )
    names = [_case_name(case) for case in cases]
    if len(names) != len(set(names)):
        raise ValueError("duplicate case names")
    return cases


def _select_cases(cases: Sequence[Case], requested: Sequence[str]) -> list[Case]:
    if not requested:
        return list(cases)
    if len(requested) != len(set(requested)):
        raise ValueError("duplicate --case value")
    by_name = {_case_name(case): case for case in cases}
    unknown = sorted(set(requested) - set(by_name))
    if unknown:
        raise ValueError(f"unknown --case value(s): {', '.join(unknown)}")
    return [case for case in cases if _case_name(case) in set(requested)]


def _placement_record(
    manifest: Mapping[str, Any], molecule: str, condition: str
) -> dict[str, Any]:
    placement_name = {
        "compact": "compact_interaction_aware",
        "intermediate": "compact_numeric",
        "perimeter": "perimeter_numeric",
    }[condition]
    record = manifest["molecules"][molecule]["placements"][placement_name]
    mapping = record["mapping"]
    factories = [item["coord"] for item in manifest["magic_factories"]]
    distances = [
        min(
            abs(coord[0] - factory_coord[0])
            + abs(coord[1] - factory_coord[1])
            for factory_coord in factories
        )
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


def _routing_record(
    manifest: Mapping[str, Any], molecule: str, condition: str
) -> dict[str, Any]:
    routing_name = {
        "remote": "remote_ban_control",
        "moderate": "moderate_choke",
        "choke": "central_choke",
    }[condition]
    source = manifest["variants"][f"{molecule.lower()}_{routing_name}"]
    return {
        **source,
        "factory_plus_ban_cell_count": int(source["banned_cell_count"]) + 4,
    }


def _topology_record(
    placement_manifest: Mapping[str, Any],
    routing_manifest: Mapping[str, Any],
    case: Case,
) -> dict[str, Any]:
    if case.family == "placement":
        return _placement_record(placement_manifest, case.molecule, case.condition)
    if case.family == "routing":
        return _routing_record(routing_manifest, case.molecule, case.condition)
    raise ValueError(f"unknown family: {case.family}")


def _key(row: Mapping[str, Any]) -> tuple[str, float, str, str, str]:
    return (
        str(row["molecule"]),
        float(row["rotation_precision"]),
        str(row["diagnostic_family"]),
        str(row["diagnostic_condition"]),
        str(row["path_latency_model"]),
    )


def _enrich(
    rows: Sequence[Mapping[str, Any]], config: Mapping[str, Any]
) -> list[dict[str, Any]]:
    by_key = {_key(row): row for row in rows}
    fixed_model = str(config["fixed_latency_model"])
    enriched: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        molecule, precision, family, condition, model = _key(row)
        family_config = config["families"][family]
        conditions = [str(value) for value in family_config["conditions"]]
        reference_condition = str(family_config["reference"])
        reference = by_key[(molecule, precision, family, reference_condition, model)]
        fixed = by_key[(molecule, precision, family, condition, fixed_model)]
        row["condition_order"] = conditions.index(condition)
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
        row["runtime_change_pct_vs_fixed_same_topology"] = _pct(
            int(row["runtime"]), int(fixed["runtime"])
        )
        row["qubit_volume_change_pct_vs_fixed_same_topology"] = _pct(
            int(row["qubit_volume"]), int(fixed["qubit_volume"])
        )
        enriched.append(row)

    enriched_by_key = {_key(row): row for row in enriched}
    for row in enriched:
        molecule, precision, family, _condition, model = _key(row)
        conditions = [str(value) for value in config["families"][family]["conditions"]]
        group = [
            enriched_by_key[(molecule, precision, family, condition, model)]
            for condition in conditions
        ]
        runtimes = [int(item["runtime"]) for item in group]
        physical_runtimes = [
            int(item["runtime"]) * int(item["code_distance"]) for item in group
        ]
        distances = [int(item["weighted_cnot_distance"]) for item in group]
        row["runtime_monotonic_non_decreasing"] = all(
            lhs <= rhs for lhs, rhs in zip(runtimes, runtimes[1:])
        )
        row["architecture_metric_monotonic_non_decreasing"] = all(
            lhs < rhs for lhs, rhs in zip(distances, distances[1:])
        )
        row["physical_runtime_monotonic_non_decreasing"] = all(
            lhs <= rhs
            for lhs, rhs in zip(physical_runtimes, physical_runtimes[1:])
        )
    return enriched


def _attach_unconstrained_comparison(
    rows: Sequence[Mapping[str, Any]],
    unconstrained_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    unconstrained_by_key = {_key(row): row for row in unconstrained_rows}
    compared = []
    for raw in rows:
        row = dict(raw)
        unconstrained = unconstrained_by_key[_key(row)]
        row["runtime_change_pct_vs_unconstrained"] = _pct(
            int(row["runtime"]), int(unconstrained["runtime"])
        )
        row["qubit_volume_change_pct_vs_unconstrained"] = _pct(
            int(row["qubit_volume"]), int(unconstrained["qubit_volume"])
        )
        compared.append(row)
    return compared


def _completed_rows(output_root: Path, cases: Sequence[Case]) -> list[dict[str, Any]]:
    rows = []
    for case in cases:
        path = output_root / "checkpoints" / f"{_case_name(case)}.json"
        if path.exists():
            rows.append(routing._load_json(path))
    return rows


def _write_outputs(
    output_root: Path,
    rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    enriched = _enrich(rows, config)
    unconstrained_rows = None
    if config.get("comparison_results"):
        unconstrained_rows = _load_csv(
            factory._resolve(config["comparison_results"])
        )
        enriched = _attach_unconstrained_comparison(enriched, unconstrained_rows)
    factory._write_rows(output_root / "results.jsonl", enriched)
    excluded = {
        "gate_count_detail",
        "workload_differences",
        "execution_environment",
        "case_metadata",
    }
    fields = [field for field in enriched[0] if field not in excluded]
    with (output_root / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(enriched)

    by_key = {_key(row): row for row in enriched}
    lines = [
        "# Dim2 Fractional Path-Latency Sensitivity",
        "",
        "Latency is `base + ceil(numerator * max(path_coordinates - 1, 0) / denominator)`. The coefficients are diagnostic sensitivity parameters, not calibrated hardware values. Every comparison keeps the logical circuit fixed within molecule and precision.",
        "",
        "| stage | molecule | precision | family | model | intermediate runtime | stress runtime | stress physical runtime | code distances | intermediate QV | stress QV | runtime monotonic |",
        "|---|---|---:|---|---|---:|---:|---:|---|---:|---:|---|",
    ]
    fixed_model = str(config["fixed_latency_model"])
    for stage_name, stage in config["stages"].items():
        for molecule_value in stage["molecules"]:
            molecule = str(molecule_value)
            for precision_value in config["rotation_precisions"]:
                precision = float(precision_value)
                for family, family_config in config["families"].items():
                    conditions = [str(value) for value in family_config["conditions"]]
                    intermediate, stress = conditions[1], conditions[2]
                    for model_value in stage["latency_models"]:
                        model = str(model_value)
                        if model == fixed_model:
                            continue
                        middle = by_key[(molecule, precision, family, intermediate, model)]
                        stressed = by_key[(molecule, precision, family, stress, model)]
                        lines.append(
                            "| {stage} | {molecule} | {precision} | {family} | {model} | {middle_runtime:+.4f}% | {stress_runtime:+.4f}% | {physical:+.4f}% | {distances} | {middle_qv:+.4f}% | {stress_qv:+.4f}% | {monotonic} |".format(
                                stage=stage_name,
                                molecule=molecule,
                                precision=factory._precision_label(precision),
                                family=family,
                                model=model,
                                middle_runtime=float(
                                    middle["runtime_change_pct_vs_family_reference"]
                                ),
                                stress_runtime=float(
                                    stressed["runtime_change_pct_vs_family_reference"]
                                ),
                                physical=float(
                                    stressed[
                                        "physical_runtime_change_pct_vs_family_reference"
                                    ]
                                ),
                                distances="/".join(
                                    str(
                                        by_key[
                                            (
                                                molecule,
                                                precision,
                                                family,
                                                condition,
                                                model,
                                            )
                                        ]["code_distance"]
                                    )
                                    for condition in conditions
                                ),
                                middle_qv=float(
                                    middle["qubit_volume_change_pct_vs_family_reference"]
                                ),
                                stress_qv=float(
                                    stressed["qubit_volume_change_pct_vs_family_reference"]
                                ),
                                monotonic=bool(
                                    stressed["runtime_monotonic_non_decreasing"]
                                ),
                            )
                        )
    if unconstrained_rows is not None:
        unconstrained_by_key = {_key(row): row for row in unconstrained_rows}
        lines.extend(
            [
                "",
                "## Factory endpoint busy comparison",
                "",
                "| precision | model | reference overhead | stress overhead | unconstrained stress penalty | constrained stress penalty | penalty delta |",
                "|---:|---|---:|---:|---:|---:|---:|",
            ]
        )
        for precision_value in config["rotation_precisions"]:
            precision = float(precision_value)
            for family, family_config in config["families"].items():
                reference = str(family_config["reference"])
                stress = str(family_config["conditions"][-1])
                for model in config["stages"][next(iter(config["stages"]))][
                    "latency_models"
                ]:
                    model = str(model)
                    constrained_reference = by_key[
                        ("H4", precision, family, reference, model)
                    ]
                    constrained_stress = by_key[("H4", precision, family, stress, model)]
                    unconstrained_reference = unconstrained_by_key[
                        ("H4", precision, family, reference, model)
                    ]
                    unconstrained_stress = unconstrained_by_key[
                        ("H4", precision, family, stress, model)
                    ]
                    unconstrained_penalty = _pct(
                        int(unconstrained_stress["runtime"]),
                        int(unconstrained_reference["runtime"]),
                    )
                    constrained_penalty = float(
                        constrained_stress["runtime_change_pct_vs_family_reference"]
                    )
                    lines.append(
                        "| {precision} | {model} | {reference_overhead:+.4f}% | {stress_overhead:+.4f}% | {unconstrained:+.4f}% | {constrained:+.4f}% | {delta:+.4f} pp |".format(
                            precision=factory._precision_label(precision),
                            model=model,
                            reference_overhead=_pct(
                                int(constrained_reference["runtime"]),
                                int(unconstrained_reference["runtime"]),
                            ),
                            stress_overhead=_pct(
                                int(constrained_stress["runtime"]),
                                int(unconstrained_stress["runtime"]),
                            ),
                            unconstrained=unconstrained_penalty,
                            constrained=constrained_penalty,
                            delta=constrained_penalty - unconstrained_penalty,
                        )
                    )
    nonfixed = [
        row for row in enriched if row["path_latency_model"] != fixed_model
    ]
    lines.extend(
        [
            "",
            f"- completed cases: `{len(enriched)}`",
            f"- fixed-workload checks passed: `{all(bool(row['fixed_logical_workload_match']) for row in enriched)}`",
            f"- nonfixed runtime-monotonic groups: `{sum(bool(row['runtime_monotonic_non_decreasing']) for row in nonfixed) // 3}/{len(nonfixed) // 3}`",
            f"- nonfixed physical-runtime-monotonic groups: `{sum(bool(row['physical_runtime_monotonic_non_decreasing']) for row in nonfixed) // 3}/{len(nonfixed) // 3}`",
            f"- architecture-metric-monotonic groups: `{sum(bool(row['architecture_metric_monotonic_non_decreasing']) for row in enriched) // 3}/{len(enriched) // 3}`",
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
    parser.add_argument("--stage", dest="stage_names", action="append", default=[])
    parser.add_argument("--case-parallelism", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--summarize-existing", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    config = factory._load_config(args.config.expanduser().resolve())
    placement_manifest = routing._load_json(
        factory._resolve(config["placement_manifest"])
    )
    routing_manifest = routing._load_json(factory._resolve(config["routing_manifest"]))
    sources = factory._source_rows(config)
    all_cases = _cases(config)
    cases = _select_cases(all_cases, args.case_names)
    if args.stage_names:
        known_stages = {case.stage for case in all_cases}
        unknown_stages = sorted(set(args.stage_names) - known_stages)
        if unknown_stages:
            raise ValueError(f"unknown --stage value(s): {', '.join(unknown_stages)}")
        requested_stages = set(args.stage_names)
        cases = [case for case in cases if case.stage in requested_stages]
    if args.dry_run:
        for case in cases:
            record = _topology_record(placement_manifest, routing_manifest, case)
            print(_case_name(case), record["topology_path"])
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
    base_patch_hash = None
    if config.get("base_diagnostic_patch"):
        base_patch_hash = routing._sha256(
            factory._resolve(config["base_diagnostic_patch"])
        )
    source_inputs = {}
    for key, source_row in sources.items():
        source_yaml = routing._find_source_compile_yaml(source_row["cache_key"])
        source_inputs[key] = (
            source_yaml,
            routing._load_json(source_yaml.with_name("compile_info.json")),
        )

    def run(case: Case) -> dict[str, Any]:
        source_row = sources[(case.molecule, case.precision)]
        source_yaml, source_info = source_inputs[(case.molecule, case.precision)]
        record = _topology_record(placement_manifest, routing_manifest, case)
        case_metadata = {
            "validation_stage": case.stage,
            "diagnostic_family": case.family,
            "diagnostic_condition": case.condition,
            "path_latency_model": case.model,
            "path_latency_numerator": case.numerator,
            "path_latency_denominator": case.denominator,
            "state_buffer_width": int(config["execution"]["state_buffer_width"]),
            "diagnostic_patch_sha256": patch_hash,
        }
        if base_patch_hash is not None:
            case_metadata["base_diagnostic_patch_sha256"] = base_patch_hash
        row = factory._run_case(
            case.molecule,
            case.precision,
            4,
            case_name=_case_name(case),
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
            execution_environment={
                NUMERATOR_ENV: str(case.numerator),
                DENOMINATOR_ENV: str(case.denominator),
            },
            case_metadata=case_metadata,
        )
        observed = routing._load_json(factory._resolve(row["compile_info_path"]))
        for field in STATS_FIELDS:
            row[field] = int(observed[field])
        if (
            int(row["distance_sensitive_path_latency_numerator"]) != case.numerator
            or int(row["distance_sensitive_path_latency_denominator"])
            != case.denominator
        ):
            raise RuntimeError(f"latency ratio mismatch for {row['case_name']}")
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
                print(
                    row["case_name"],
                    f"runtime={row['runtime']}",
                    f"rss_kib={row['gnu_time_max_rss_kb']}",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001
                failures.append((_case_name(case), exc))
                print(f"FAILED {_case_name(case)}: {exc}", file=sys.stderr, flush=True)
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
