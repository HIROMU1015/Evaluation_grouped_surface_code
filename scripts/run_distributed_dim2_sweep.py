#!/usr/bin/env python3
"""Run the paired-precision H4/H7 DistributedDim2 communication sweep."""

from __future__ import annotations

import argparse
import csv
import json
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
    REPO_ROOT / "configs" / "surface_code_distributed_dim2_sweep_h4_h7_4th_paired.yaml"
)
DEFAULT_QRET = REPO_ROOT / "build" / "quration" / "qret"
PERIOD_INVARIANT_FIELDS = (
    "gate_count",
    "gate_count_detail",
    "gate_depth",
    "measurement_feedback_count",
    "measurement_feedback_depth",
    "magic_state_consumption_count",
    "magic_state_consumption_depth",
    "entanglement_consumption_count",
    "entanglement_consumption_depth",
    "magic_factory_count",
    "entanglement_factory_count",
)
SOURCE_LOGICAL_FIELDS = (
    "measurement_feedback_count",
    "magic_state_consumption_count",
)
SOURCE_ARCHITECTURE_DEPTH_FIELDS = (
    "measurement_feedback_depth",
    "magic_state_consumption_depth",
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


def _case_name(molecule: str, precision: float, partition: str, period: int) -> str:
    return (
        f"{molecule.lower()}_p{_precision_label(precision)}_" f"{partition}_e{period}"
    )


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


def _cases(config: Mapping[str, Any]) -> list[tuple[str, float, str, int]]:
    return [
        (str(molecule), float(precision), str(partition), int(period))
        for molecule in config["molecules"]
        for precision in config["rotation_precisions"]
        for partition in config["partitions"]
        for period in config["entanglement_generation_periods"]
    ]


def _select_cases(
    cases: Sequence[tuple[str, float, str, int]], requested_names: Sequence[str]
) -> list[tuple[str, float, str, int]]:
    if not requested_names:
        return list(cases)
    if len(set(requested_names)) != len(requested_names):
        raise ValueError("duplicate --case value")
    by_name = {
        _case_name(molecule, precision, partition, period): (
            molecule,
            precision,
            partition,
            period,
        )
        for molecule, precision, partition, period in cases
    }
    unknown = sorted(set(requested_names) - set(by_name))
    if unknown:
        raise ValueError(f"unknown --case value(s): {', '.join(unknown)}")
    requested = set(requested_names)
    return [case for case in cases if _case_name(*case) in requested]


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _run_case(
    molecule: str,
    precision: float,
    partition: str,
    period: int,
    *,
    source_row: Mapping[str, str],
    source_yaml: Path,
    source_compile_info: Mapping[str, Any],
    topology_record: Mapping[str, Any],
    output_root: Path,
    qret: Path,
    qret_hash: str,
    qret_core: Path,
    qret_core_hash: str,
    maximum_entangled_state_stock: int,
    force: bool,
) -> dict[str, Any]:
    name = _case_name(molecule, precision, partition, period)
    checkpoint_path = output_root / "checkpoints" / f"{name}.json"
    topology_path = _resolve(topology_record["topology_path"])
    if checkpoint_path.exists() and not force:
        checkpoint = routing._load_json(checkpoint_path)
        if (
            checkpoint.get("qret_executable_hash") == qret_hash
            and checkpoint.get("qret_core_library_hash") == qret_core_hash
            and checkpoint.get("topology_hash") == routing._sha256(topology_path)
            and int(checkpoint.get("entanglement_generation_period", -1)) == period
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
            "sc_ls_fixed_v0_machine_type": "DistributedDim2",
            "sc_ls_fixed_v0_magic_generation_period": 15,
            "sc_ls_fixed_v0_maximum_magic_state_stock": 10000,
            "sc_ls_fixed_v0_entanglement_generation_period": period,
            "sc_ls_fixed_v0_maximum_entangled_state_stock": (
                maximum_entangled_state_stock
            ),
            "sc_ls_fixed_v0_reaction_time": 1,
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
    source_differences = {
        field: {
            "source": source_compile_info.get(field),
            "distributed": observed.get(field),
        }
        for field in SOURCE_LOGICAL_FIELDS
        if source_compile_info.get(field) != observed.get(field)
    }
    source_depth_differences = {
        field: {
            "source": source_compile_info.get(field),
            "distributed": observed.get(field),
        }
        for field in SOURCE_ARCHITECTURE_DEPTH_FIELDS
        if source_compile_info.get(field) != observed.get(field)
    }
    gate_detail = dict(observed.get("gate_count_detail", {}))
    runtime = int(observed["runtime"])
    runtime_without_topology = int(observed["runtime_without_topology"])
    entanglement_count = int(observed["entanglement_consumption_count"])
    result: dict[str, Any] = {
        "status": "ok",
        "case_name": name,
        "molecule": molecule,
        "pf_label": source_row["pf_label"],
        "rotation_precision": source_row["rotation_precision"],
        "partition": partition,
        "entanglement_generation_period": period,
        "maximum_entangled_state_stock": maximum_entangled_state_stock,
        "qasm_hash": source_row["qasm_hash"],
        "optimized_ir_hash": source_row["optimized_ir_hash"],
        "source_cache_key": source_row["cache_key"],
        "source_compile_yaml": _display(source_yaml),
        "topology_path": _display(topology_path),
        "topology_hash": routing._sha256(topology_path),
        "machine_type": "DistributedDim2",
        "plane_count": 2,
        "plane_size": json.dumps([10, 10]),
        "total_logical_cells": int(topology_record["total_logical_cells"]),
        "usable_non_factory_cells": int(topology_record["usable_non_factory_cells"]),
        "magic_factory_count_topology": int(topology_record["magic_factory_count"]),
        "entanglement_factory_endpoint_count_topology": int(
            topology_record["entanglement_factory_endpoint_count"]
        ),
        "entanglement_link_count": int(topology_record["entanglement_link_count"]),
        "logical_qubits_by_plane": json.dumps(
            topology_record["logical_qubits_by_plane"], sort_keys=True
        ),
        "weighted_interplane_cnot_count": int(
            topology_record["weighted_interplane_cnot_count"]
        ),
        "weighted_interplane_cnot_fraction": float(
            topology_record["weighted_interplane_cnot_fraction"]
        ),
        "weighted_local_and_endpoint_distance": int(
            topology_record["weighted_local_and_endpoint_distance"]
        ),
        "runtime": runtime,
        "runtime_without_topology": runtime_without_topology,
        "runtime_topology_overhead": runtime - runtime_without_topology,
        "qubit_volume": int(observed["qubit_volume"]),
        "code_distance": int(observed["code_distance"]),
        "physical_qubits": int(observed["num_physical_qubits"]),
        "gate_count": int(observed["gate_count"]),
        "gate_count_detail": gate_detail,
        "gate_depth": int(observed["gate_depth"]),
        "measurement_feedback_count": int(observed["measurement_feedback_count"]),
        "measurement_feedback_depth": int(observed["measurement_feedback_depth"]),
        "magic_state_consumption_count": int(observed["magic_state_consumption_count"]),
        "magic_state_consumption_depth": int(observed["magic_state_consumption_depth"]),
        "entanglement_consumption_count": entanglement_count,
        "entanglement_consumption_depth": int(
            observed["entanglement_consumption_depth"]
        ),
        "entanglement_consumption_rate_ave": float(
            observed["entanglement_consumption_rate_ave"]
        ),
        "entanglement_consumption_rate_peak": int(
            observed["entanglement_consumption_rate_peak"]
        ),
        "runtime_estimation_entanglement_consumption_count": int(
            observed["runtime_estimation_entanglement_consumption_count"]
        ),
        "runtime_estimation_entanglement_consumption_depth": int(
            observed["runtime_estimation_entanglement_consumption_depth"]
        ),
        "magic_factory_count": int(observed["magic_factory_count"]),
        "entanglement_factory_count": int(observed["entanglement_factory_count"]),
        "allocate_entanglement_factory_count": int(
            gate_detail.get("ALLOCATE_ENTANGLEMENT_FACTORY", 0)
        ),
        "lattice_surgery_multinode_count": int(
            gate_detail.get("LATTICE_SURGERY_MULTINODE", 0)
        ),
        "move_entanglement_count": int(gate_detail.get("MOVE_ENTANGLEMENT", 0)),
        "cnot_count_after_routing": int(gate_detail.get("CNOT", 0)),
        "entanglement_count_minus_static_cut": (
            entanglement_count - int(topology_record["weighted_interplane_cnot_count"])
        ),
        "source_logical_workload_match": not source_differences,
        "source_logical_differences": source_differences,
        "source_architecture_depth_differences": source_depth_differences,
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
    }
    _write_json(checkpoint_path, result)
    return result


def _enrich(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_key = {
        (
            str(row["molecule"]),
            float(row["rotation_precision"]),
            str(row["partition"]),
            int(row["entanglement_generation_period"]),
        ): row
        for row in rows
    }
    enriched: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        molecule = str(row["molecule"])
        precision = float(row["rotation_precision"])
        partition = str(row["partition"])
        period = int(row["entanglement_generation_period"])
        baseline = by_key[(molecule, precision, partition, 1)]
        opposite_partition = "high_cut" if partition == "low_cut" else "low_cut"
        opposite = by_key[(molecule, precision, opposite_partition, period)]
        period_differences = {
            field: {"period_1": baseline.get(field), "observed": row.get(field)}
            for field in PERIOD_INVARIANT_FIELDS
            if baseline.get(field) != row.get(field)
        }
        row["period_invariant_workload_match"] = not period_differences
        row["period_invariant_differences"] = period_differences
        row["runtime_delta_vs_period_1"] = int(row["runtime"]) - int(
            baseline["runtime"]
        )
        row["runtime_change_pct_vs_period_1"] = (
            int(row["runtime"]) / int(baseline["runtime"]) - 1.0
        ) * 100.0
        row["qubit_volume_change_pct_vs_period_1"] = (
            int(row["qubit_volume"]) / int(baseline["qubit_volume"]) - 1.0
        ) * 100.0
        if partition == "high_cut":
            low = opposite
            row["runtime_change_pct_high_vs_low"] = (
                int(row["runtime"]) / int(low["runtime"]) - 1.0
            ) * 100.0
        else:
            high = opposite
            row["runtime_change_pct_high_vs_low"] = (
                int(high["runtime"]) / int(row["runtime"]) - 1.0
            ) * 100.0
        row["runtime_minus_entanglement_count_estimate"] = int(row["runtime"]) - int(
            row["runtime_estimation_entanglement_consumption_count"]
        )
        enriched.append(row)
    return enriched


def _write_rows(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _completed_rows(
    output_root: Path,
    cases: Sequence[tuple[str, float, str, int]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for molecule, precision, partition, period in cases:
        checkpoint_path = (
            output_root
            / "checkpoints"
            / f"{_case_name(molecule, precision, partition, period)}.json"
        )
        if checkpoint_path.exists():
            rows.append(routing._load_json(checkpoint_path))
    return rows


def _write_outputs(
    output_root: Path, rows: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    enriched = _enrich(rows)
    _write_rows(output_root / "results.jsonl", enriched)
    csv_fields = [
        key
        for key in enriched[0]
        if key
        not in {
            "gate_count_detail",
            "source_logical_differences",
            "source_architecture_depth_differences",
            "period_invariant_differences",
        }
    ]
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
        "# H4/H7 Paired-Precision DistributedDim2 Communication Sweep",
        "",
        "Each molecule/precision uses one fixed optimized IR. Two balanced explicit partitions and entanglement-generation periods 1/15/100 are compared on the same two 10x10 planes, four magic factories, one entanglement link, and fixed stock limits. Absolute runtime is not compared across precision as an architecture effect.",
    ]
    for precision in (1e-5, 1e-2):
        lines.extend(
            [
                "",
                f"## rotation_precision={_precision_label(precision)}",
                "",
                "| molecule | partition | period | runtime | vs period=1 | topology overhead | static cut | ent count | ent depth | count estimate | runtime-estimate | code distance | QV vs period=1 | workload match |",
                "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
            ]
        )
        for row in enriched:
            if float(row["rotation_precision"]) != precision:
                continue
            lines.append(
                "| {molecule} | {partition} | {period} | {runtime:,} | {runtime_pct:+.4f}% | {overhead:,} | {cut:,} | {ent_count:,} | {ent_depth:,} | {estimate:,} | {residual:+,} | {distance} | {qv_pct:+.4f}% | {match} |".format(
                    molecule=row["molecule"],
                    partition=row["partition"],
                    period=int(row["entanglement_generation_period"]),
                    runtime=int(row["runtime"]),
                    runtime_pct=float(row["runtime_change_pct_vs_period_1"]),
                    overhead=int(row["runtime_topology_overhead"]),
                    cut=int(row["weighted_interplane_cnot_count"]),
                    ent_count=int(row["entanglement_consumption_count"]),
                    ent_depth=int(row["entanglement_consumption_depth"]),
                    estimate=int(
                        row["runtime_estimation_entanglement_consumption_count"]
                    ),
                    residual=int(row["runtime_minus_entanglement_count_estimate"]),
                    distance=int(row["code_distance"]),
                    qv_pct=float(row["qubit_volume_change_pct_vs_period_1"]),
                    match=(
                        "yes"
                        if row["period_invariant_workload_match"]
                        and row["source_logical_workload_match"]
                        else "no"
                    ),
                )
            )

    lookup = {
        (
            str(row["molecule"]),
            float(row["rotation_precision"]),
            str(row["partition"]),
            int(row["entanglement_generation_period"]),
        ): row
        for row in enriched
    }
    lines.extend(
        [
            "",
            "## High-Cut versus Low-Cut Runtime",
            "",
            "| molecule | precision | period | low-cut runtime | high-cut runtime | high vs low | cut increase |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for molecule in ("H4", "H7"):
        for precision in (1e-5, 1e-2):
            for period in (1, 15, 100):
                low = lookup[(molecule, precision, "low_cut", period)]
                high = lookup[(molecule, precision, "high_cut", period)]
                lines.append(
                    "| {molecule} | {precision} | {period} | {low_runtime:,} | {high_runtime:,} | {pct:+.4f}% | {cut:+,} |".format(
                        molecule=molecule,
                        precision=_precision_label(precision),
                        period=period,
                        low_runtime=int(low["runtime"]),
                        high_runtime=int(high["runtime"]),
                        pct=float(high["runtime_change_pct_high_vs_low"]),
                        cut=(
                            int(high["weighted_interplane_cnot_count"])
                            - int(low["weighted_interplane_cnot_count"])
                        ),
                    )
                )

    peak_rss = max(int(row["gnu_time_max_rss_kb"]) for row in enriched)
    lines.extend(
        [
            "",
            "## Validity and Execution",
            "",
            "- QASM and optimized-IR hashes are fixed within each molecule/precision.",
            "- Magic and measurement-feedback counts must match the source Dim2 compile. Their dependency depths may change under DistributedDim2 lowering and are treated as architecture-lowered metrics.",
            "- Gate, magic, feedback, and entanglement count/depth must remain invariant when only entanglement-generation period changes.",
            "- The compile-info schema exposes entanglement consumption and estimates, but not a direct no-entanglement-stock rejection counter.",
            f"- peak qret RSS: {peak_rss:,} KiB ({peak_rss / 1024**2:.2f} GiB)",
            f"- maximum GNU-time swaps: {max(int(row['gnu_time_swaps']) for row in enriched)}",
            "- execution: the first 18 cases ran sequentially with `MemoryHigh=44G`, `MemoryMax=48G`; the final six H7 `1e-2` cases ran with bounded six-way case parallelism under aggregate `MemoryHigh=32G`, `MemoryMax=40G`",
            f"- qret executable SHA-256: `{enriched[0]['qret_executable_hash']}`",
            f"- qret core library SHA-256: `{enriched[0]['qret_core_library_hash']}`",
            "",
        ]
    )
    (output_root / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    return enriched


def _probe_case(
    config: Mapping[str, Any],
) -> tuple[str, float, str, int]:
    return (
        str(config["molecules"][0]),
        float(config["rotation_precisions"][-1]),
        "high_cut",
        15,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--qret", type=Path, default=DEFAULT_QRET)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--probe", action="store_true")
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
    if args.probe and args.case_names:
        raise ValueError("--probe and --case cannot be used together")
    cases = _select_cases(all_cases, args.case_names)
    if args.probe:
        cases = [_probe_case(config)]
    if args.dry_run:
        for molecule, precision, partition, period in cases:
            record = variants[f"{molecule.lower()}_{partition}"]
            print(
                _case_name(molecule, precision, partition, period),
                sources[(molecule, precision)]["cache_key"],
                f"cut={record['weighted_interplane_cnot_count']}",
                f"period={period}",
            )
        return 0

    output_root = _resolve(config["output_directory"])
    output_root.mkdir(parents=True, exist_ok=True)
    if args.summarize_existing:
        with (output_root / "results.jsonl").open(encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
        _write_outputs(output_root, rows)
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
    maximum_stock = int(config["fixed_conditions"]["maximum_entangled_state_stock"])

    def run_case(case: tuple[str, float, str, int]) -> dict[str, Any]:
        molecule, precision, partition, period = case
        source_row = sources[(molecule, precision)]
        source_yaml, source_compile_info = source_inputs[(molecule, precision)]
        topology_record = variants[f"{molecule.lower()}_{partition}"]
        return _run_case(
            molecule,
            precision,
            partition,
            period,
            source_row=source_row,
            source_yaml=source_yaml,
            source_compile_info=source_compile_info,
            topology_record=topology_record,
            output_root=output_root,
            qret=qret,
            qret_hash=qret_hash,
            qret_core=qret_core,
            qret_core_hash=qret_core_hash,
            maximum_entangled_state_stock=maximum_stock,
            force=args.force,
        )

    rows: list[dict[str, Any]] = []
    failures: list[tuple[str, Exception]] = []

    def record(row: dict[str, Any]) -> None:
        rows.append(row)
        completed_rows = _completed_rows(output_root, all_cases)
        _write_rows(output_root / "results.partial.jsonl", completed_rows)
        print(
            row["case_name"],
            "runtime=",
            row["runtime"],
            "ent_count=",
            row["entanglement_consumption_count"],
            "ent_depth=",
            row["entanglement_consumption_depth"],
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

    if args.probe:
        probe = rows[0]
        if not bool(probe["source_logical_workload_match"]):
            raise RuntimeError("DistributedDim2 probe changed source logical workload")
        if int(probe["entanglement_consumption_count"]) <= 0:
            raise RuntimeError("DistributedDim2 probe consumed no entanglement")
        if int(probe["entanglement_factory_count"]) != int(
            probe["entanglement_link_count"]
        ):
            raise RuntimeError("DistributedDim2 probe did not allocate one E link")
        if int(probe["lattice_surgery_multinode_count"]) <= 0:
            raise RuntimeError("DistributedDim2 probe emitted no multinode operations")
        print("PROBE_OK", json.dumps(probe, sort_keys=True))
        return 0

    completed_rows = _completed_rows(output_root, all_cases)
    _write_rows(output_root / "results.partial.jsonl", completed_rows)
    if len(completed_rows) != len(all_cases):
        print(
            f"PARTIAL_COMPLETE={len(completed_rows)}/{len(all_cases)}",
            flush=True,
        )
        return 0

    enriched = _write_outputs(output_root, completed_rows)
    shutil.rmtree(output_root / ".work", ignore_errors=True)
    (output_root / "results.partial.jsonl").unlink(missing_ok=True)
    if not all(bool(row["source_logical_workload_match"]) for row in enriched):
        raise RuntimeError("one or more cases changed source logical workload")
    if not all(bool(row["period_invariant_workload_match"]) for row in enriched):
        raise RuntimeError("one or more period cases changed the lowered workload")
    print(output_root / "summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
