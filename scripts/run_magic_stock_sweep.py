#!/usr/bin/env python3
"""Run the paired-precision H4-H6 Dim2 magic-stock sweep."""

from __future__ import annotations

import argparse
import csv
import json
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
    REPO_ROOT / "configs" / "surface_code_magic_stock_sweep_h4_h6_4th_paired.yaml"
)
DEFAULT_QRET = REPO_ROOT / "build" / "quration" / "qret"


def _case_name(molecule: str, precision: float, stock: int) -> str:
    return f"{molecule.lower()}_p{factory._precision_label(precision)}_s{stock}"


def _cases(config: Mapping[str, Any]) -> list[tuple[str, float, int]]:
    return [
        (str(molecule), float(precision), int(stock))
        for molecule in config["molecules"]
        for precision in config["rotation_precisions"]
        for stock in config["maximum_magic_state_stocks"]
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
    baseline_stock = int(config["comparison_policy"]["baseline_stock"])
    stocks = sorted(int(value) for value in config["maximum_magic_state_stocks"])
    by_key = {
        (
            str(row["molecule"]),
            float(row["rotation_precision"]),
            int(row["maximum_magic_state_stock"]),
        ): row
        for row in rows
    }
    enriched: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        molecule = str(row["molecule"])
        precision = float(row["rotation_precision"])
        stock = int(row["maximum_magic_state_stock"])
        baseline = by_key[(molecule, precision, baseline_stock)]
        row["runtime_change_pct_vs_stock_10000"] = (
            int(row["runtime"]) / int(baseline["runtime"]) - 1.0
        ) * 100.0
        row["qubit_volume_change_pct_vs_stock_10000"] = (
            int(row["qubit_volume"]) / int(baseline["qubit_volume"]) - 1.0
        ) * 100.0
        index = stocks.index(stock)
        if index == 0:
            row["runtime_reduction_pct_vs_previous_stock"] = None
        else:
            previous = by_key[(molecule, precision, stocks[index - 1])]
            row["runtime_reduction_pct_vs_previous_stock"] = (
                1.0 - int(row["runtime"]) / int(previous["runtime"])
            ) * 100.0
        enriched.append(row)
    return enriched


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

    threshold = float(config["comparison_policy"]["saturation_runtime_threshold_pct"])
    stocks = sorted(int(value) for value in config["maximum_magic_state_stocks"])
    lines = [
        "# H4-H6 Paired-Precision Dim2 Magic-Stock Sweep",
        "",
        "Each molecule/precision uses one fixed optimized IR and one fixed 10x10 Dim2 topology with four central factories, 96 usable non-factory cells, and two initial egress cells per factory. Only qret's maximum magic-state stock changes. Absolute runtime is not compared across precision as an architecture effect.",
    ]
    by_key = {
        (
            str(row["molecule"]),
            float(row["rotation_precision"]),
            int(row["maximum_magic_state_stock"]),
        ): row
        for row in enriched
    }
    saturation: dict[tuple[str, float], int] = {}
    for precision in (1e-5, 1e-2):
        lines.extend(
            [
                "",
                f"## rotation_precision={factory._precision_label(precision)}",
                "",
                "| molecule | stock | runtime | vs stock 10000 | marginal reduction | runtime no topology | topology overhead | code distance | physical qubits | QV vs stock 10000 | workload match |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
            ]
        )
        for molecule in ("H4", "H5", "H6"):
            group = [by_key[(molecule, precision, stock)] for stock in stocks]
            saturation[(molecule, precision)] = next(
                int(row["maximum_magic_state_stock"])
                for row in group
                if abs(float(row["runtime_change_pct_vs_stock_10000"])) < threshold
            )
            for row in group:
                marginal = row["runtime_reduction_pct_vs_previous_stock"]
                lines.append(
                    "| {molecule} | {stock} | {runtime:,} | {runtime_pct:+.4f}% | {marginal} | {no_topology:,} | {overhead:+,} | {distance} | {physical:,} | {qv:+.4f}% | {match} |".format(
                        molecule=molecule,
                        stock=int(row["maximum_magic_state_stock"]),
                        runtime=int(row["runtime"]),
                        runtime_pct=float(row["runtime_change_pct_vs_stock_10000"]),
                        marginal=(
                            "reference"
                            if marginal is None
                            else f"{float(marginal):+.4f}%"
                        ),
                        no_topology=int(row["runtime_without_topology"]),
                        overhead=int(row["runtime_topology_overhead"]),
                        distance=int(row["code_distance"]),
                        physical=int(row["physical_qubits"]),
                        qv=float(row["qubit_volume_change_pct_vs_stock_10000"]),
                        match="yes" if row["fixed_logical_workload_match"] else "no",
                    )
                )

    lines.extend(
        [
            "",
            f"## Saturation at < {threshold:.1f}% Runtime Difference",
            "",
            "| molecule | saturation stock at 1e-5 | saturation stock at 1e-2 | stock 64 penalty at 1e-5 | stock 64 penalty at 1e-2 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    intermediate_required = False
    for molecule in ("H4", "H5", "H6"):
        p64_conv = float(
            by_key[(molecule, 1e-5, 64)]["runtime_change_pct_vs_stock_10000"]
        )
        p64_cheap = float(
            by_key[(molecule, 1e-2, 64)]["runtime_change_pct_vs_stock_10000"]
        )
        if p64_conv >= threshold or p64_cheap >= threshold:
            intermediate_required = True
        lines.append(
            "| {molecule} | {conv} | {cheap} | {p64_conv:+.4f}% | {p64_cheap:+.4f}% |".format(
                molecule=molecule,
                conv=saturation[(molecule, 1e-5)],
                cheap=saturation[(molecule, 1e-2)],
                p64_conv=p64_conv,
                p64_cheap=p64_cheap,
            )
        )

    h7_required = any(
        float(by_key[("H6", precision, 64)]["runtime_change_pct_vs_stock_10000"])
        >= threshold
        or saturation[("H6", precision)] > saturation[("H5", precision)]
        for precision in (1e-5, 1e-2)
    )

    peak_rss = max(int(row["gnu_time_max_rss_kb"]) for row in enriched)
    lines.extend(
        [
            "",
            "## Validity and Execution",
            "",
            "- QASM, optimized IR, topology, factory count/coordinates, magic generation period, reaction time, and QEC inputs are fixed within each molecule/precision.",
            "- Non-factory gate counts/depths and magic/feedback demand must match in every stock case.",
            "- The standard compile-info schema does not expose a direct no-magic-stock rejection count; runtime response is the primary saturation evidence.",
            "- Code-distance changes, if present, affect physical qubits/QV but not the primary beat-runtime comparison.",
            f"- additional stock 256/1024 required: {'yes' if intermediate_required else 'no'}",
            f"- H7 follow-up required by the predeclared saturation/size-trend rule: {'yes' if h7_required else 'no'}",
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
    manifest = routing._load_json(factory._resolve(config["topology_manifest"]))
    variants = manifest["variants"]
    sources = factory._source_rows(config)
    all_cases = _cases(config)
    if args.case_parallelism < 1:
        raise ValueError("--case-parallelism must be at least 1")
    cases = _select_cases(all_cases, args.case_names)
    if args.dry_run:
        for molecule, precision, stock in cases:
            record = variants[f"{molecule.lower()}_factory_count_4"]
            print(
                _case_name(molecule, precision, stock),
                sources[(molecule, precision)]["cache_key"],
                f"stock={stock}",
                f"factories={record['factory_count']}",
                f"usable={record['usable_non_factory_cell_count']}",
                f"min_egress={record['minimum_initial_free_neighbors']}",
            )
        return 0

    output_root = factory._resolve(config["output_directory"])
    output_root.mkdir(parents=True, exist_ok=True)
    if args.summarize_existing:
        completed = _completed_rows(output_root, all_cases)
        if len(completed) != len(all_cases):
            raise RuntimeError(
                f"cannot summarize partial sweep: {len(completed)}/{len(all_cases)}"
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
        molecule, precision, stock = case
        source_row = sources[(molecule, precision)]
        source_yaml, source_compile_info = source_inputs[(molecule, precision)]
        topology_record = variants[f"{molecule.lower()}_factory_count_4"]
        fixed = {**base_fixed, "maximum_magic_state_stock": stock}
        return factory._run_case(
            molecule,
            precision,
            4,
            case_name=_case_name(molecule, precision, stock),
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
            "stock=",
            row["maximum_magic_state_stock"],
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

    completed = _completed_rows(output_root, all_cases)
    factory._write_rows(output_root / "results.partial.jsonl", completed)
    if len(completed) != len(all_cases):
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
