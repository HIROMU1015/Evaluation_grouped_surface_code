#!/usr/bin/env python3
"""Run the paired fixed-circuit Dim2 factory-count/period interaction sweep."""

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
from scripts import run_magic_period_sweep as period  # noqa: E402
from scripts import run_qret_runtime_routing_diagnostic as routing  # noqa: E402


DEFAULT_CONFIG = (
    REPO_ROOT
    / "configs"
    / "surface_code_factory_period_interaction_sweep_h4_h7_4th_paired.yaml"
)
DEFAULT_QRET = REPO_ROOT / "build" / "quration" / "qret"


def _case_name(
    molecule: str, precision: float, factory_count: int, magic_period: int
) -> str:
    return (
        f"{molecule.lower()}_p{factory._precision_label(precision)}_"
        f"f{factory_count}_period{magic_period}"
    )


def _cases(config: Mapping[str, Any]) -> list[tuple[str, float, int, int]]:
    return [
        (str(molecule), float(precision), int(count), int(magic_period))
        for molecule in config["molecules"]
        for precision in config["rotation_precisions"]
        for count in config["factory_counts"]
        for magic_period in config["magic_generation_periods"]
    ]


def _select_cases(
    cases: Sequence[tuple[str, float, int, int]], requested: Sequence[str]
) -> list[tuple[str, float, int, int]]:
    if not requested:
        return list(cases)
    by_name = {_case_name(*case): case for case in cases}
    unknown = sorted(set(requested) - set(by_name))
    if unknown:
        raise ValueError(f"unknown --case value(s): {', '.join(unknown)}")
    selected = set(requested)
    return [case for case in cases if _case_name(*case) in selected]


def _physical_runtime_units(row: Mapping[str, Any]) -> int:
    return int(row["runtime"]) * int(row["code_distance"])


def _enrich(
    rows: Sequence[Mapping[str, Any]], config: Mapping[str, Any]
) -> list[dict[str, Any]]:
    fixed = config["fixed_conditions"]
    baseline_count = int(fixed["baseline_factory_count"])
    baseline_period = int(fixed["baseline_magic_generation_period"])
    by_key = {
        (
            str(row["molecule"]),
            float(row["rotation_precision"]),
            int(row["factory_count"]),
            int(row["magic_generation_period"]),
        ): row
        for row in rows
    }
    enriched: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        molecule = str(row["molecule"])
        precision = float(row["rotation_precision"])
        count = int(row["factory_count"])
        magic_period = int(row["magic_generation_period"])
        baseline = by_key[(molecule, precision, baseline_count, baseline_period)]
        same_period_four = by_key[(molecule, precision, baseline_count, magic_period)]
        same_count_15 = by_key[(molecule, precision, count, baseline_period)]
        row["runtime_change_pct_vs_f4_period15"] = (
            int(row["runtime"]) / int(baseline["runtime"]) - 1.0
        ) * 100.0
        row["physical_runtime_change_pct_vs_f4_period15"] = (
            _physical_runtime_units(row) / _physical_runtime_units(baseline) - 1.0
        ) * 100.0
        row["qubit_volume_change_pct_vs_f4_period15"] = (
            int(row["qubit_volume"]) / int(baseline["qubit_volume"]) - 1.0
        ) * 100.0
        row["factory_three_penalty_pct_at_same_period"] = (
            int(row["runtime"]) / int(same_period_four["runtime"]) - 1.0
        ) * 100.0
        row["period_30_penalty_pct_at_same_factory_count"] = (
            int(row["runtime"]) / int(same_count_15["runtime"]) - 1.0
        ) * 100.0
        enriched.append(row)

    for row in enriched:
        molecule = str(row["molecule"])
        precision = float(row["rotation_precision"])
        p15 = by_key[(molecule, precision, 3, 15)]
        p30 = by_key[(molecule, precision, 3, 30)]
        f4p15 = by_key[(molecule, precision, 4, 15)]
        f4p30 = by_key[(molecule, precision, 4, 30)]
        penalty15 = (int(p15["runtime"]) / int(f4p15["runtime"]) - 1.0) * 100.0
        penalty30 = (int(p30["runtime"]) / int(f4p30["runtime"]) - 1.0) * 100.0
        row["factory_period_interaction_percentage_points"] = penalty30 - penalty15
    return enriched


def _completed_rows(
    output_root: Path, cases: Sequence[tuple[str, float, int, int]]
) -> list[dict[str, Any]]:
    rows = []
    for case in cases:
        path = output_root / "checkpoints" / f"{_case_name(*case)}.json"
        if path.exists():
            rows.append(routing._load_json(path))
    return rows


def _write_outputs(
    output_root: Path,
    rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    enriched = _enrich(rows, config)
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

    by_key = {
        (
            str(row["molecule"]),
            float(row["rotation_precision"]),
            int(row["factory_count"]),
            int(row["magic_generation_period"]),
        ): row
        for row in enriched
    }
    lines = [
        "# Fixed-Circuit Factory Count x Magic Period Interaction",
        "",
        "All comparisons are within one molecule and one rotation precision. The optimized IR is fixed; only factory count and generation period change.",
        "",
        "| precision | molecule | 3-factory penalty at period 15 | 3-factory penalty at period 30 | interaction | period-30 penalty with 4 factories | worst beat runtime vs f4/p15 | worst physical runtime vs f4/p15 | worst QV vs f4/p15 |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for precision_value in config["rotation_precisions"]:
        precision = float(precision_value)
        for molecule_value in config["molecules"]:
            molecule = str(molecule_value)
            f3p15 = by_key[(molecule, precision, 3, 15)]
            f3p30 = by_key[(molecule, precision, 3, 30)]
            f4p15 = by_key[(molecule, precision, 4, 15)]
            f4p30 = by_key[(molecule, precision, 4, 30)]
            penalty15 = (int(f3p15["runtime"]) / int(f4p15["runtime"]) - 1) * 100
            penalty30 = (int(f3p30["runtime"]) / int(f4p30["runtime"]) - 1) * 100
            candidates = (f3p15, f3p30, f4p30)
            worst = max(candidates, key=lambda row: float(row["runtime_change_pct_vs_f4_period15"]))
            lines.append(
                "| {precision} | {molecule} | {p15:+.4f}% | {p30:+.4f}% | {interaction:+.4f} pp | {period:+.4f}% | {runtime:+.4f}% | {physical:+.4f}% | {qv:+.4f}% |".format(
                    precision=factory._precision_label(precision),
                    molecule=molecule,
                    p15=penalty15,
                    p30=penalty30,
                    interaction=penalty30 - penalty15,
                    period=(int(f4p30["runtime"]) / int(f4p15["runtime"]) - 1) * 100,
                    runtime=float(worst["runtime_change_pct_vs_f4_period15"]),
                    physical=float(worst["physical_runtime_change_pct_vs_f4_period15"]),
                    qv=float(worst["qubit_volume_change_pct_vs_f4_period15"]),
                )
            )
    peak = max(int(row["gnu_time_max_rss_kb"]) for row in enriched)
    lines.extend(
        [
            "",
            "- Interaction is the period-30 three-factory penalty minus the period-15 three-factory penalty.",
            "- Physical runtime uses `runtime * code_distance * code_cycle_time`; the fixed cycle time cancels in percentages.",
            f"- fixed-workload checks passed: `{all(bool(row['fixed_logical_workload_match']) for row in enriched)}`",
            f"- peak per-case RSS: `{peak / 1024**2:.2f} GiB`; maximum swaps: `{max(int(row['gnu_time_swaps']) for row in enriched)}`",
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
    manifest = routing._load_json(factory._resolve(config["topology_manifest"]))
    sources = factory._source_rows(config)
    all_cases = _cases(config)
    cases = _select_cases(all_cases, args.case_names)
    if args.dry_run:
        for case in cases:
            print(_case_name(*case))
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
    qret_core = routing._linked_qret_core(qret)
    qret_hash = routing._sha256(qret)
    qret_core_hash = routing._sha256(qret_core)
    source_inputs = {}
    for key, source_row in sources.items():
        source_yaml = routing._find_source_compile_yaml(source_row["cache_key"])
        source_inputs[key] = (
            source_yaml,
            routing._load_json(source_yaml.with_name("compile_info.json")),
        )

    def run(case: tuple[str, float, int, int]) -> dict[str, Any]:
        molecule, precision, count, magic_period = case
        source_row = sources[(molecule, precision)]
        source_yaml, source_info = source_inputs[(molecule, precision)]
        fixed = dict(config["fixed_conditions"])
        fixed["magic_generation_period"] = magic_period
        return factory._run_case(
            molecule,
            precision,
            count,
            case_name=_case_name(*case),
            source_row=source_row,
            source_yaml=source_yaml,
            source_compile_info=source_info,
            topology_record=manifest["variants"][f"{molecule.lower()}_factory_count_{count}"],
            fixed=fixed,
            output_root=output_root,
            qret=qret,
            qret_hash=qret_hash,
            qret_core=qret_core,
            qret_core_hash=qret_core_hash,
            force=args.force,
            workload_ignored_fields=period.PERIOD_SCALED_RUNTIME_ESTIMATION_FIELDS,
        )

    parallelism = args.case_parallelism or int(config["execution"]["case_parallelism"])
    if parallelism < 1:
        raise ValueError("case parallelism must be positive")
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
