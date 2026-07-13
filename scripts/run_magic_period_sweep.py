#!/usr/bin/env python3
"""Run the fixed-circuit cheap-RZ Dim2 magic-generation-period sweep."""

from __future__ import annotations

import argparse
import csv
import shutil
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
    / "surface_code_magic_period_sweep_h4_h7_4th_cheap_rz.yaml"
)
DEFAULT_QRET = REPO_ROOT / "build" / "quration" / "qret"
PERIOD_SCALED_RUNTIME_ESTIMATION_FIELDS = (
    "runtime_estimation_magic_state_consumption_count",
    "runtime_estimation_magic_state_consumption_depth",
)


def _case_name(molecule: str, precision: float, period: int) -> str:
    return f"{molecule.lower()}_p{factory._precision_label(precision)}_period{period}"


def _cases(
    config: Mapping[str, Any], *, include_conditional: bool = False
) -> list[tuple[str, float, int]]:
    molecules = list(config["primary_molecules"])
    if include_conditional:
        molecules.extend(config.get("conditional_molecules", []))
    return [
        (str(molecule), float(precision), int(period))
        for molecule in molecules
        for precision in config["rotation_precisions"]
        for period in config["magic_generation_periods"]
    ]


def _select_cases(
    cases: Sequence[tuple[str, float, int]], requested_names: Sequence[str]
) -> list[tuple[str, float, int]]:
    if not requested_names:
        return list(cases)
    if len(set(requested_names)) != len(requested_names):
        raise ValueError("duplicate --case value")
    by_name = {_case_name(*case): case for case in cases}
    unknown = sorted(set(requested_names) - set(by_name))
    if unknown:
        raise ValueError(f"unknown --case value(s): {', '.join(unknown)}")
    requested = set(requested_names)
    return [case for case in cases if _case_name(*case) in requested]


def _completed_rows(
    output_root: Path, cases: Sequence[tuple[str, float, int]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        path = output_root / "checkpoints" / f"{_case_name(*case)}.json"
        if path.exists():
            rows.append(routing._load_json(path))
    return rows


def _enrich(
    rows: Sequence[Mapping[str, Any]], config: Mapping[str, Any]
) -> list[dict[str, Any]]:
    policy = config["comparison_policy"]
    ideal_period = int(policy["ideal_reference_period"])
    standard_period = int(policy["standard_baseline_period"])
    periods = sorted(int(value) for value in config["magic_generation_periods"])
    if ideal_period not in periods or standard_period not in periods:
        raise ValueError("reference periods must be present in magic_generation_periods")
    by_key = {
        (
            str(row["molecule"]),
            float(row["rotation_precision"]),
            int(row["magic_generation_period"]),
        ): row
        for row in rows
    }
    enriched: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        molecule = str(row["molecule"])
        precision = float(row["rotation_precision"])
        period = int(row["magic_generation_period"])
        ideal = by_key[(molecule, precision, ideal_period)]
        standard = by_key[(molecule, precision, standard_period)]
        row["runtime_change_pct_vs_period_1"] = (
            int(row["runtime"]) / int(ideal["runtime"]) - 1.0
        ) * 100.0
        row["runtime_change_pct_vs_period_15"] = (
            int(row["runtime"]) / int(standard["runtime"]) - 1.0
        ) * 100.0
        row["qubit_volume_change_pct_vs_period_15"] = (
            int(row["qubit_volume"]) / int(standard["qubit_volume"]) - 1.0
        ) * 100.0
        index = periods.index(period)
        if index == 0:
            row["runtime_change_pct_vs_previous_period"] = None
        else:
            previous = by_key[(molecule, precision, periods[index - 1])]
            row["runtime_change_pct_vs_previous_period"] = (
                int(row["runtime"]) / int(previous["runtime"]) - 1.0
            ) * 100.0
        enriched.append(row)
    return enriched


def _h7_required(
    rows: Sequence[Mapping[str, Any]], config: Mapping[str, Any]
) -> tuple[bool, list[str]]:
    threshold = float(
        config["comparison_policy"]["material_runtime_threshold_pct"]
    )
    trigger_periods = {
        int(value) for value in config["comparison_policy"]["h7_trigger_periods"]
    }
    reasons: list[str] = []
    for row in rows:
        if str(row["molecule"]) != "H6":
            continue
        period = int(row["magic_generation_period"])
        change = float(row["runtime_change_pct_vs_period_15"])
        if period in trigger_periods and abs(change) >= threshold:
            reasons.append(f"H6 period={period}: {change:+.4f}% vs period=15")
    return bool(reasons), reasons


def _write_outputs(
    output_root: Path,
    rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    enriched = _enrich(rows, config)
    factory._write_rows(output_root / "results.jsonl", enriched)
    excluded = {"gate_count_detail", "workload_differences"}
    csv_fields = [key for key in enriched[0] if key not in excluded]
    with (output_root / "results.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=csv_fields,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(enriched)

    periods = sorted(int(value) for value in config["magic_generation_periods"])
    molecules = [str(value) for value in config["primary_molecules"]]
    conditional = [str(value) for value in config.get("conditional_molecules", [])]
    completed_molecules = {str(row["molecule"]) for row in enriched}
    molecules.extend(value for value in conditional if value in completed_molecules)
    precision = float(config["rotation_precisions"][0])
    by_key = {
        (
            str(row["molecule"]),
            float(row["rotation_precision"]),
            int(row["magic_generation_period"]),
        ): row
        for row in enriched
    }
    lines = [
        "# H4-H7 Cheap-RZ Dim2 Magic-Generation-Period Sweep",
        "",
        "Each molecule uses one fixed optimized IR and one fixed 10x10 Dim2 topology with four central factories, stock 10000, reaction time 1, 96 usable non-factory cells, and two initial egress cells per factory. Only qret's magic-generation period changes.",
        "",
        f"- rotation precision: `{factory._precision_label(precision)}`",
        "- period 1: ideal fast-supply reference",
        "- period 15: current standard Dim2 baseline",
    ]
    for molecule in molecules:
        lines.extend(
            [
                "",
                f"## {molecule}",
                "",
                "| period | runtime | vs period 1 | vs period 15 | change vs previous | runtime no topology | topology overhead | code distance | physical qubits | QV vs period 15 | workload match |",
                "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
            ]
        )
        for period in periods:
            row = by_key[(molecule, precision, period)]
            marginal = row["runtime_change_pct_vs_previous_period"]
            lines.append(
                "| {period} | {runtime:,} | {ideal:+.4f}% | {standard:+.4f}% | {marginal} | {no_topology:,} | {overhead:+,} | {distance} | {physical:,} | {qv:+.4f}% | {match} |".format(
                    period=period,
                    runtime=int(row["runtime"]),
                    ideal=float(row["runtime_change_pct_vs_period_1"]),
                    standard=float(row["runtime_change_pct_vs_period_15"]),
                    marginal=(
                        "reference"
                        if marginal is None
                        else f"{float(marginal):+.4f}%"
                    ),
                    no_topology=int(row["runtime_without_topology"]),
                    overhead=int(row["runtime_topology_overhead"]),
                    distance=int(row["code_distance"]),
                    physical=int(row["physical_qubits"]),
                    qv=float(row["qubit_volume_change_pct_vs_period_15"]),
                    match="yes" if row["fixed_logical_workload_match"] else "no",
                )
            )

    primary_rows = [
        row
        for row in enriched
        if str(row["molecule"]) in set(config["primary_molecules"])
    ]
    h7_required, h7_reasons = _h7_required(primary_rows, config)
    threshold = float(
        config["comparison_policy"]["material_runtime_threshold_pct"]
    )
    lines.extend(
        [
            "",
            "## Sensitivity Summary",
            "",
            "| molecule | period 15 vs 1 | period 30 vs 15 | period 100 vs 15 | full runtime spread |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for molecule in molecules:
        group = [by_key[(molecule, precision, period)] for period in periods]
        runtimes = [int(row["runtime"]) for row in group]
        lines.append(
            "| {molecule} | {p15:+.4f}% | {p30:+.4f}% | {p100:+.4f}% | {spread:.4f}% |".format(
                molecule=molecule,
                p15=float(
                    by_key[(molecule, precision, 15)][
                        "runtime_change_pct_vs_period_1"
                    ]
                ),
                p30=float(
                    by_key[(molecule, precision, 30)][
                        "runtime_change_pct_vs_period_15"
                    ]
                ),
                p100=float(
                    by_key[(molecule, precision, 100)][
                        "runtime_change_pct_vs_period_15"
                    ]
                ),
                spread=(max(runtimes) / min(runtimes) - 1.0) * 100.0,
            )
        )

    h7_complete = all(value in completed_molecules for value in conditional)
    peak_rss = max(int(row["gnu_time_max_rss_kb"]) for row in enriched)
    lines.extend(
        [
            "",
            "## Validity and Execution",
            "",
            "- QASM, optimized IR, topology, factory count/coordinates, maximum magic-state stock, reaction time, and QEC inputs are fixed within each molecule.",
            "- Non-factory gate counts/depths and magic/feedback demand must match in every period case.",
            "- `runtime_estimation_magic_state_consumption_count/depth` are period-scaled supply-time estimates, so they are recorded but excluded from the fixed logical-workload invariant.",
            f"- material runtime threshold: {threshold:.1f}% versus period 15 at H6 period 30/100",
            f"- H7 follow-up required: {'yes' if h7_required else 'no'}",
            f"- H7 follow-up complete: {'yes' if h7_complete else 'no'}",
        ]
    )
    if h7_reasons:
        lines.append(f"- H7 trigger: {'; '.join(h7_reasons)}")
    lines.extend(
        [
            f"- peak qret RSS: {peak_rss:,} KiB ({peak_rss / 1024**2:.2f} GiB)",
            f"- maximum GNU-time swaps: {max(int(row['gnu_time_swaps']) for row in enriched)}",
            f"- qret executable SHA-256: `{enriched[0]['qret_executable_hash']}`",
            f"- qret core library SHA-256: `{enriched[0]['qret_core_library_hash']}`",
            "",
        ]
    )
    (output_root / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    return enriched


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--qret", type=Path, default=DEFAULT_QRET)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--summarize-existing", action="store_true")
    parser.add_argument("--include-h7", action="store_true")
    parser.add_argument(
        "--case",
        dest="case_names",
        action="append",
        default=[],
        metavar="NAME",
        help="run only the named case; may be repeated",
    )
    parser.add_argument(
        "--case-parallelism",
        type=int,
        default=1,
        metavar="N",
        help="maximum number of independent qret cases to run concurrently",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    config = factory._load_config(args.config.expanduser().resolve())
    primary_cases = _cases(config)
    all_cases = _cases(config, include_conditional=args.include_h7)
    if args.case_parallelism < 1:
        raise ValueError("--case-parallelism must be at least 1")
    cases = _select_cases(all_cases, args.case_names)
    manifest = routing._load_json(factory._resolve(config["topology_manifest"]))
    variants = manifest["variants"]
    source_config = {
        **config,
        "molecules": list(config["primary_molecules"])
        + (
            list(config.get("conditional_molecules", []))
            if args.include_h7
            else []
        ),
    }
    sources = factory._source_rows(source_config)
    if args.dry_run:
        for molecule, precision, period in cases:
            record = variants[f"{molecule.lower()}_factory_count_4"]
            print(
                _case_name(molecule, precision, period),
                sources[(molecule, precision)]["cache_key"],
                f"period={period}",
                f"factories={record['factory_count']}",
                f"usable={record['usable_non_factory_cell_count']}",
                f"min_egress={record['minimum_initial_free_neighbors']}",
            )
        return 0

    output_root = factory._resolve(config["output_directory"])
    output_root.mkdir(parents=True, exist_ok=True)
    if args.summarize_existing:
        completed = _completed_rows(output_root, all_cases)
        expected = all_cases if args.include_h7 else primary_cases
        if len(completed) != len(expected):
            raise RuntimeError(
                f"cannot summarize partial sweep: {len(completed)}/{len(expected)}"
            )
        _write_outputs(output_root, completed, config)
        print(output_root / "summary.md")
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
    qret_hash = routing._sha256(qret)
    qret_core_hash = routing._sha256(qret_core)
    base_fixed = dict(config["fixed_conditions"])

    def run_case(case: tuple[str, float, int]) -> dict[str, Any]:
        molecule, precision, period = case
        source_row = sources[(molecule, precision)]
        source_yaml, source_compile_info = source_inputs[(molecule, precision)]
        topology_record = variants[f"{molecule.lower()}_factory_count_4"]
        fixed = {**base_fixed, "magic_generation_period": period}
        return factory._run_case(
            molecule,
            precision,
            4,
            case_name=_case_name(molecule, precision, period),
            source_row=source_row,
            source_yaml=source_yaml,
            source_compile_info=source_compile_info,
            topology_record=topology_record,
            fixed=fixed,
            output_root=output_root,
            qret=qret,
            qret_hash=qret_hash,
            qret_core=qret_core,
            qret_core_hash=qret_core_hash,
            force=args.force,
            workload_ignored_fields=PERIOD_SCALED_RUNTIME_ESTIMATION_FIELDS,
        )

    rows: list[dict[str, Any]] = []
    failures: list[tuple[str, Exception]] = []

    def record(row: dict[str, Any]) -> None:
        rows.append(row)
        completed = _completed_rows(output_root, all_cases)
        factory._write_rows(output_root / "results.partial.jsonl", completed)
        print(
            row["case_name"],
            "runtime=",
            row["runtime"],
            "period=",
            row["magic_generation_period"],
            "rss_kib=",
            row["gnu_time_max_rss_kb"],
            flush=True,
        )

    if args.case_parallelism == 1 or len(cases) == 1:
        for case in cases:
            record(run_case(case))
    else:
        worker_count = min(args.case_parallelism, len(cases))
        print(
            f"CASE_PARALLELISM={worker_count} SELECTED_CASES={len(cases)}",
            flush=True,
        )
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_cases = {executor.submit(run_case, case): case for case in cases}
            for future in as_completed(future_cases):
                case = future_cases[future]
                try:
                    record(future.result())
                except Exception as exc:
                    name = _case_name(*case)
                    failures.append((name, exc))
                    print(f"CASE_FAILED {name}: {exc}", file=sys.stderr, flush=True)

    if failures:
        names = ", ".join(name for name, _ in failures)
        raise RuntimeError(f"{len(failures)} case(s) failed: {names}")

    completed_primary = _completed_rows(output_root, primary_cases)
    factory._write_rows(output_root / "results.partial.jsonl", completed_primary)
    if len(completed_primary) != len(primary_cases):
        print(
            f"PARTIAL_PRIMARY_COMPLETE={len(completed_primary)}/{len(primary_cases)}",
            flush=True,
        )
        return 0
    completed = _completed_rows(output_root, all_cases)
    if args.include_h7 and len(completed) != len(all_cases):
        print(f"PARTIAL_COMPLETE={len(completed)}/{len(all_cases)}", flush=True)
        return 0

    enriched = _write_outputs(output_root, completed, config)
    shutil.rmtree(output_root / ".work", ignore_errors=True)
    (output_root / "results.partial.jsonl").unlink(missing_ok=True)
    if not all(bool(row["fixed_logical_workload_match"]) for row in enriched):
        raise RuntimeError("one or more cases changed the fixed logical workload")
    print(output_root / "summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
