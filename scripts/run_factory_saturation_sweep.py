#!/usr/bin/env python3
"""Run the paired-precision H4-H6 Dim2 factory-saturation sweep."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import run_qret_runtime_routing_diagnostic as routing  # noqa: E402


DEFAULT_CONFIG = (
    REPO_ROOT
    / "configs"
    / "surface_code_factory_saturation_sweep_h4_h6_4th_paired.yaml"
)
DEFAULT_QRET = REPO_ROOT / "build" / "quration" / "qret"
WORKLOAD_INVARIANT_FIELDS = (
    "gate_depth",
    "measurement_feedback_count",
    "measurement_feedback_depth",
    "magic_state_consumption_count",
    "magic_state_consumption_depth",
    "runtime_estimation_magic_state_consumption_count",
    "runtime_estimation_magic_state_consumption_depth",
)


def _resolve(path: str | Path) -> Path:
    value = Path(path).expanduser()
    return value.resolve() if value.is_absolute() else (REPO_ROOT / value).resolve()


def _display(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def _load_config(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected YAML mapping: {path}")
    return payload


def _precision_label(precision: float) -> str:
    return f"{precision:.0e}"


def _case_name(molecule: str, precision: float, factory_count: int) -> str:
    return f"{molecule.lower()}_p{_precision_label(precision)}_f{factory_count}"


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
                    f"expected one source row for {molecule}/{precision}, "
                    f"found {len(matches)}"
                )
            selected[(molecule, precision)] = matches[0]
    return selected


def _cases(config: Mapping[str, Any]) -> list[tuple[str, float, int]]:
    return [
        (str(molecule), float(precision), int(factory_count))
        for molecule in config["molecules"]
        for precision in config["rotation_precisions"]
        for factory_count in config["factory_counts"]
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


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _workload_differences(
    source: Mapping[str, Any], observed: Mapping[str, Any], factory_count: int
) -> dict[str, Any]:
    differences = {
        field: {"source": source.get(field), "observed": observed.get(field)}
        for field in WORKLOAD_INVARIANT_FIELDS
        if source.get(field) != observed.get(field)
    }
    source_detail = dict(source.get("gate_count_detail", {}))
    observed_detail = dict(observed.get("gate_count_detail", {}))
    source_allocations = int(source_detail.pop("ALLOCATE_MAGIC_FACTORY", 0))
    observed_allocations = int(observed_detail.pop("ALLOCATE_MAGIC_FACTORY", 0))
    if source_detail != observed_detail:
        differences["gate_count_detail_without_factory_allocation"] = {
            "source": source_detail,
            "observed": observed_detail,
        }
    source_non_factory_gates = int(source["gate_count"]) - source_allocations
    observed_non_factory_gates = int(observed["gate_count"]) - observed_allocations
    if source_non_factory_gates != observed_non_factory_gates:
        differences["gate_count_without_factory_allocation"] = {
            "source": source_non_factory_gates,
            "observed": observed_non_factory_gates,
        }
    if observed_allocations != factory_count:
        differences["allocate_magic_factory_count"] = {
            "expected": factory_count,
            "observed": observed_allocations,
        }
    if int(observed.get("magic_factory_count", -1)) != factory_count:
        differences["magic_factory_count"] = {
            "expected": factory_count,
            "observed": observed.get("magic_factory_count"),
        }
    return differences


def _run_case(
    molecule: str,
    precision: float,
    factory_count: int,
    *,
    source_row: Mapping[str, str],
    source_yaml: Path,
    source_compile_info: Mapping[str, Any],
    topology_record: Mapping[str, Any],
    fixed: Mapping[str, Any],
    output_root: Path,
    qret: Path,
    qret_hash: str,
    qret_core: Path,
    qret_core_hash: str,
    force: bool,
) -> dict[str, Any]:
    name = _case_name(molecule, precision, factory_count)
    checkpoint_path = output_root / "checkpoints" / f"{name}.json"
    topology_path = _resolve(topology_record["topology_path"])
    topology_hash = routing._sha256(topology_path)
    if checkpoint_path.exists() and not force:
        checkpoint = routing._load_json(checkpoint_path)
        if (
            checkpoint.get("qret_executable_hash") == qret_hash
            and checkpoint.get("qret_core_library_hash") == qret_core_hash
            and checkpoint.get("topology_hash") == topology_hash
            and checkpoint.get("source_cache_key") == source_row["cache_key"]
            and int(checkpoint.get("factory_count", -1)) == factory_count
        ):
            return checkpoint

    work_dir = output_root / ".work" / name
    log_dir = output_root / "logs" / "cases"
    compile_info_dir = output_root / "compile_info"
    work_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    compile_info_dir.mkdir(parents=True, exist_ok=True)
    pipeline_path = work_dir / "compile.yaml"
    compile_info_path = compile_info_dir / f"{name}.json"
    stdout_path = log_dir / f"{name}.stdout.txt"
    stderr_path = log_dir / f"{name}.stderr.txt"
    for path in (compile_info_path, stdout_path, stderr_path):
        path.unlink(missing_ok=True)

    pipeline = yaml.safe_load(source_yaml.read_text(encoding="utf-8"))
    if not isinstance(pipeline, dict):
        raise ValueError(f"expected YAML mapping: {source_yaml}")
    pipeline.update(
        {
            "output": "/dev/null",
            "sc_ls_fixed_v0_topology": str(topology_path),
            "sc_ls_fixed_v0_machine_type": "Dim2",
            "sc_ls_fixed_v0_magic_generation_period": int(
                fixed["magic_generation_period"]
            ),
            "sc_ls_fixed_v0_maximum_magic_state_stock": int(
                fixed["maximum_magic_state_stock"]
            ),
            "sc_ls_fixed_v0_entanglement_generation_period": int(
                fixed["entanglement_generation_period"]
            ),
            "sc_ls_fixed_v0_maximum_entangled_state_stock": int(
                fixed["maximum_entangled_state_stock"]
            ),
            "sc_ls_fixed_v0_reaction_time": int(fixed["reaction_time"]),
            "sc_ls_fixed_v0_compile_info_output_mode": "summary",
            "sc_ls_fixed_v0_skip_pipeline_state_output": True,
            "sc_ls_fixed_v0_dump_compile_info_to_json": str(
                compile_info_path.resolve()
            ),
        }
    )
    pipeline_path.write_text(
        yaml.safe_dump(pipeline, sort_keys=False), encoding="utf-8"
    )

    env = os.environ.copy()
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    command = [
        "/usr/bin/time",
        "-v",
        str(qret),
        "compile",
        "--pipeline",
        str(pipeline_path),
    ]
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    elapsed = time.perf_counter() - started
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(
            f"qret failed for {name} with exit {completed.returncode}:\n"
            f"{completed.stderr[-5000:]}"
        )
    if not compile_info_path.exists():
        raise RuntimeError(f"qret did not emit compile info for {name}")

    observed = routing._load_json(compile_info_path)
    workload_differences = _workload_differences(
        source_compile_info, observed, factory_count
    )
    gate_detail = dict(observed.get("gate_count_detail", {}))
    runtime = int(observed["runtime"])
    runtime_without_topology = int(observed["runtime_without_topology"])
    result: dict[str, Any] = {
        "status": "ok",
        "case_name": name,
        "molecule": molecule,
        "pf_label": source_row["pf_label"],
        "rotation_precision": float(source_row["rotation_precision"]),
        "factory_count": factory_count,
        "qasm_hash": source_row["qasm_hash"],
        "optimized_ir_hash": source_row["optimized_ir_hash"],
        "source_cache_key": source_row["cache_key"],
        "source_compile_yaml": _display(source_yaml),
        "topology_path": _display(topology_path),
        "topology_hash": topology_hash,
        "machine_type": "Dim2",
        "factory_plus_ban_cell_count": int(
            topology_record["factory_plus_ban_cell_count"]
        ),
        "usable_non_factory_cell_count": int(
            topology_record["usable_non_factory_cell_count"]
        ),
        "minimum_initial_free_neighbors": int(
            topology_record["minimum_initial_free_neighbors"]
        ),
        "weighted_cnot_distance": int(topology_record["weighted_cnot_distance"]),
        "weighted_nearest_factory_distance": int(
            topology_record["weighted_nearest_factory_distance"]
        ),
        "weighted_nearest_factory_distance_mean": float(
            topology_record["weighted_nearest_factory_distance_mean"]
        ),
        "runtime": runtime,
        "runtime_without_topology": runtime_without_topology,
        "runtime_topology_overhead": runtime - runtime_without_topology,
        "qubit_volume": int(observed["qubit_volume"]),
        "chip_cell_count": int(observed["chip_cell_count"]),
        "code_distance": int(observed["code_distance"]),
        "physical_qubits": int(observed["num_physical_qubits"]),
        "estimated_execution_time_sec": float(observed["execution_time_sec"]),
        "gate_count": int(observed["gate_count"]),
        "gate_count_detail": gate_detail,
        "gate_depth": int(observed["gate_depth"]),
        "allocate_magic_factory_count": int(
            gate_detail.get("ALLOCATE_MAGIC_FACTORY", 0)
        ),
        "magic_factory_count": int(observed["magic_factory_count"]),
        "measurement_feedback_count": int(observed["measurement_feedback_count"]),
        "measurement_feedback_depth": int(observed["measurement_feedback_depth"]),
        "magic_state_consumption_count": int(observed["magic_state_consumption_count"]),
        "magic_state_consumption_depth": int(observed["magic_state_consumption_depth"]),
        "fixed_logical_workload_match": not workload_differences,
        "workload_differences": workload_differences,
        "compile_info_path": _display(compile_info_path),
        "elapsed_seconds": elapsed,
        "gnu_time_max_rss_kb": int(
            routing._gnu_time_value(
                completed.stderr, "Maximum resident set size (kbytes)"
            )
            or 0
        ),
        "gnu_time_swaps": int(routing._gnu_time_value(completed.stderr, "Swaps") or 0),
        "qret_executable_hash": qret_hash,
        "qret_core_library_hash": qret_core_hash,
        "magic_generation_period": int(fixed["magic_generation_period"]),
        "maximum_magic_state_stock": int(fixed["maximum_magic_state_stock"]),
        "reaction_time": int(fixed["reaction_time"]),
    }
    _write_json(checkpoint_path, result)
    return result


def _enrich(
    rows: Sequence[Mapping[str, Any]], config: Mapping[str, Any]
) -> list[dict[str, Any]]:
    fixed = config["fixed_conditions"]
    baseline_count = int(fixed["baseline_factory_count"])
    comparison_count = int(fixed["comparison_factory_count"])
    counts = sorted(int(value) for value in config["factory_counts"])
    by_key = {
        (
            str(row["molecule"]),
            float(row["rotation_precision"]),
            int(row["factory_count"]),
        ): row
        for row in rows
    }
    enriched: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        molecule = str(row["molecule"])
        precision = float(row["rotation_precision"])
        count = int(row["factory_count"])
        baseline = by_key[(molecule, precision, baseline_count)]
        comparison = by_key[(molecule, precision, comparison_count)]
        row["runtime_change_pct_vs_four_factories"] = (
            int(row["runtime"]) / int(baseline["runtime"]) - 1.0
        ) * 100.0
        row["runtime_change_pct_vs_eight_factories"] = (
            int(row["runtime"]) / int(comparison["runtime"]) - 1.0
        ) * 100.0
        row["qubit_volume_change_pct_vs_four_factories"] = (
            int(row["qubit_volume"]) / int(baseline["qubit_volume"]) - 1.0
        ) * 100.0
        index = counts.index(count)
        if index == 0:
            row["runtime_reduction_pct_vs_previous_count"] = None
        else:
            previous = by_key[(molecule, precision, counts[index - 1])]
            row["runtime_reduction_pct_vs_previous_count"] = (
                1.0 - int(row["runtime"]) / int(previous["runtime"])
            ) * 100.0
        ideal_supply = math.ceil(
            int(row["magic_state_consumption_count"])
            * int(row["magic_generation_period"])
            / count
        )
        row["ideal_magic_supply_runtime"] = ideal_supply
        row["runtime_without_topology_minus_ideal_supply"] = (
            int(row["runtime_without_topology"]) - ideal_supply
        )
        enriched.append(row)
    return enriched


def _write_rows(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), sort_keys=True) + "\n")


def _completed_rows(
    output_root: Path, cases: Sequence[tuple[str, float, int]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        checkpoint_path = output_root / "checkpoints" / f"{_case_name(*case)}.json"
        if checkpoint_path.exists():
            rows.append(routing._load_json(checkpoint_path))
    return rows


def _write_outputs(
    output_root: Path,
    rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    enriched = _enrich(rows, config)
    _write_rows(output_root / "results.jsonl", enriched)
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

    lines = [
        "# H4-H6 Paired-Precision Dim2 Factory-Saturation Sweep",
        "",
        "Each molecule/precision uses one fixed optimized IR. Active factory count changes from 4 to 6 to 8 inside one fixed eight-cell central factory/ban budget on a 10x10 Dim2 plane. Absolute runtime is not compared across precision as an architecture effect.",
    ]
    for precision in (1e-5, 1e-2):
        lines.extend(
            [
                "",
                f"## rotation_precision={_precision_label(precision)}",
                "",
                "| molecule | factories | runtime | vs four | vs eight | marginal reduction | runtime no topology | supply-floor residual | topology overhead | nearest-factory mean | min egress | cells | code distance | QV vs four | workload match |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
            ]
        )
        for row in enriched:
            if float(row["rotation_precision"]) != precision:
                continue
            marginal = row["runtime_reduction_pct_vs_previous_count"]
            lines.append(
                "| {molecule} | {count} | {runtime:,} | {vs_four:+.4f}% | {vs_eight:+.4f}% | {marginal} | {no_topology:,} | {residual:+,} | {overhead:+,} | {distance:.3f} | {egress} | {cells} | {code_distance} | {qv:+.4f}% | {match} |".format(
                    molecule=row["molecule"],
                    count=int(row["factory_count"]),
                    runtime=int(row["runtime"]),
                    vs_four=float(row["runtime_change_pct_vs_four_factories"]),
                    vs_eight=float(row["runtime_change_pct_vs_eight_factories"]),
                    marginal=(
                        "reference" if marginal is None else f"{float(marginal):+.4f}%"
                    ),
                    no_topology=int(row["runtime_without_topology"]),
                    residual=int(row["runtime_without_topology_minus_ideal_supply"]),
                    overhead=int(row["runtime_topology_overhead"]),
                    distance=float(row["weighted_nearest_factory_distance_mean"]),
                    egress=int(row["minimum_initial_free_neighbors"]),
                    cells=int(row["chip_cell_count"]),
                    code_distance=int(row["code_distance"]),
                    qv=float(row["qubit_volume_change_pct_vs_four_factories"]),
                    match="yes" if row["fixed_logical_workload_match"] else "no",
                )
            )

    by_key = {
        (
            str(row["molecule"]),
            float(row["rotation_precision"]),
            int(row["factory_count"]),
        ): row
        for row in enriched
    }
    lines.extend(
        [
            "",
            "## Four-to-Eight Factory Runtime Reduction",
            "",
            "| molecule | reduction at 1e-5 | reduction at 1e-2 | six-to-eight residual at 1e-5 | six-to-eight residual at 1e-2 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    h7_trigger = False
    trigger_pct = float(config["comparison_policy"]["h7_trigger_runtime_change_pct"])
    for molecule in ("H4", "H5", "H6"):
        reductions: dict[float, float] = {}
        residuals: dict[float, float] = {}
        for precision in (1e-5, 1e-2):
            four = by_key[(molecule, precision, 4)]
            six = by_key[(molecule, precision, 6)]
            eight = by_key[(molecule, precision, 8)]
            reductions[precision] = (
                1.0 - int(eight["runtime"]) / int(four["runtime"])
            ) * 100.0
            residuals[precision] = (
                int(six["runtime"]) / int(eight["runtime"]) - 1.0
            ) * 100.0
            if (
                reductions[precision] > trigger_pct
                or residuals[precision] > trigger_pct
            ):
                h7_trigger = True
        lines.append(
            "| {molecule} | {conv:+.4f}% | {cheap:+.4f}% | {conv_res:+.4f}% | {cheap_res:+.4f}% |".format(
                molecule=molecule,
                conv=reductions[1e-5],
                cheap=reductions[1e-2],
                conv_res=residuals[1e-5],
                cheap_res=residuals[1e-2],
            )
        )

    peak_rss = max(int(row["gnu_time_max_rss_kb"]) for row in enriched)
    lines.extend(
        [
            "",
            "## Validity and Execution",
            "",
            "- QASM and optimized-IR hashes are fixed within each molecule/precision.",
            "- Non-factory gate counts/depths and magic/feedback demand must remain fixed. Only factory-allocation count and architecture-dependent runtime/resource fields may change.",
            "- Active factories plus banned cells remain eight, leaving 92 non-factory cells in every case.",
            "- Factory sets are nested and symbols 0-3 retain their coordinates. Additional sources change both aggregate supply throughput and nearest-source availability within the fixed budget.",
            "- Code-distance changes, if present, affect physical qubits/QV but not the primary beat-runtime conclusion.",
            f"- peak qret RSS: {peak_rss:,} KiB ({peak_rss / 1024**2:.2f} GiB)",
            f"- maximum GNU-time swaps: {max(int(row['gnu_time_swaps']) for row in enriched)}",
            f"- H7 follow-up trigger (> {trigger_pct:.1f}% unresolved runtime effect): {'yes' if h7_trigger else 'no'}",
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
    config = _load_config(args.config.expanduser().resolve())
    manifest = routing._load_json(_resolve(config["topology_manifest"]))
    variants = manifest["variants"]
    sources = _source_rows(config)
    all_cases = _cases(config)
    if args.case_parallelism < 1:
        raise ValueError("--case-parallelism must be at least 1")
    cases = _select_cases(all_cases, args.case_names)
    if args.dry_run:
        for molecule, precision, factory_count in cases:
            name = f"{molecule.lower()}_factory_count_{factory_count}"
            record = variants[name]
            print(
                _case_name(molecule, precision, factory_count),
                sources[(molecule, precision)]["cache_key"],
                f"factories={factory_count}",
                f"budget={record['factory_plus_ban_cell_count']}",
                f"min_egress={record['minimum_initial_free_neighbors']}",
            )
        return 0

    output_root = _resolve(config["output_directory"])
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
    fixed = config["fixed_conditions"]

    def run_case(case: tuple[str, float, int]) -> dict[str, Any]:
        molecule, precision, factory_count = case
        source_row = sources[(molecule, precision)]
        source_yaml, source_compile_info = source_inputs[(molecule, precision)]
        topology_record = variants[f"{molecule.lower()}_factory_count_{factory_count}"]
        return _run_case(
            molecule,
            precision,
            factory_count,
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
        _write_rows(output_root / "results.partial.jsonl", completed)
        print(
            row["case_name"],
            "runtime=",
            row["runtime"],
            "factory_count=",
            row["factory_count"],
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
    _write_rows(output_root / "results.partial.jsonl", completed)
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
