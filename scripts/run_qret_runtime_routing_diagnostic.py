#!/usr/bin/env python3
"""Re-run selected fixed-circuit cases with aggregate qret routing diagnostics."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = (
    REPO_ROOT
    / "artifacts"
    / "surface_code_runtime_grid_threshold_h5_h7_4th"
    / "results.csv"
)
DEFAULT_OUTPUT = (
    REPO_ROOT / "artifacts" / "qret_runtime_routing_diagnostic_h5_h7_4th"
)
DEFAULT_QRET = REPO_ROOT / "build" / "quration" / "qret"
CACHE_ROOT = (
    REPO_ROOT / "artifacts" / "surface_code_cache" / "gr" / "ftqc_compile_topology_qec"
)
CASE_SELECTORS = (
    ("H5", "aware_8x8"),
    ("H7", "aware_8x8"),
    ("H7", "aware_8x10"),
    ("H7", "aware_10x10"),
)
SEMANTIC_FIELDS = (
    "runtime",
    "runtime_without_topology",
    "gate_count",
    "gate_depth",
    "magic_state_consumption_count",
    "magic_state_consumption_depth",
    "chip_cell_count",
    "qubit_volume",
    "code_distance",
    "execution_time_sec",
    "num_physical_qubits",
)
INSTRUCTION_TYPES = (
    "TWIST",
    "HADAMARD",
    "LATTICE_SURGERY_MAGIC",
    "CNOT",
    "PROBABILITY_HINT",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT))
    except ValueError:
        return str(resolved)


def _linked_qret_core(qret: Path) -> Path:
    output = subprocess.check_output(["ldd", str(qret)], text=True)
    match = re.search(r"^\s*libqret-core\.so\S*\s+=>\s+(\S+)", output, re.MULTILINE)
    if not match:
        raise RuntimeError(f"failed to resolve libqret-core for {qret}")
    path = Path(match.group(1)).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _find_source_compile_yaml(cache_key: str) -> Path:
    matches = sorted(CACHE_ROOT.glob(f"*/{cache_key}/compile.yaml"))
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one compile.yaml for cache key {cache_key}, found {len(matches)}"
        )
    return matches[0]


def _selected_rows(results_path: Path) -> list[dict[str, str]]:
    with results_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    selected: list[dict[str, str]] = []
    for molecule, topology in CASE_SELECTORS:
        matches = [
            row
            for row in rows
            if row.get("molecule") == molecule and row.get("topology_name") == topology
        ]
        if len(matches) != 1:
            raise RuntimeError(
                f"expected one source result for {molecule}/{topology}, found {len(matches)}"
            )
        selected.append(matches[0])
    return selected


def _prepare_pipeline(source: Path, destination: Path, compile_info: Path) -> None:
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected YAML mapping: {source}")
    payload["output"] = "/dev/null"
    payload["sc_ls_fixed_v0_dump_compile_info_to_json"] = str(compile_info.resolve())
    destination.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


def _gnu_time_value(stderr: str, label: str) -> str | None:
    match = re.search(
        rf"^\s*{re.escape(label)}:\s*(.+)$",
        stderr,
        flags=re.MULTILINE,
    )
    return match.group(1).strip() if match else None


def _type_value(payload: Mapping[str, Any], field: str, inst_type: str) -> int:
    counters = payload.get(field, {})
    if not isinstance(counters, Mapping):
        return 0
    return int(counters.get(inst_type, 0))


def _path_value(payload: Mapping[str, Any], inst_type: str, field: str) -> Any:
    by_type = payload.get("path_stats_by_type", {})
    if not isinstance(by_type, Mapping):
        return None
    values = by_type.get(inst_type, {})
    return values.get(field) if isinstance(values, Mapping) else None


def _run_case(
    source_row: Mapping[str, str],
    *,
    qret: Path,
    qret_hash: str,
    qret_core_path: Path,
    qret_core_hash: str,
    output_root: Path,
    force: bool,
) -> dict[str, Any]:
    molecule = source_row["molecule"]
    topology = source_row["topology_name"]
    case_name = f"{molecule.lower()}_{topology}"
    run_dir = output_root / ".work" / case_name
    summary_path = run_dir / "summary.json"
    if summary_path.exists() and not force:
        existing = _load_json(summary_path)
        if (
            existing.get("qret_executable_hash") == qret_hash
            and existing.get("qret_core_library_hash") == qret_core_hash
        ):
            return existing

    run_dir.mkdir(parents=True, exist_ok=True)
    source_yaml = _find_source_compile_yaml(source_row["cache_key"])
    source_compile_info = source_yaml.with_name("compile_info.json")
    if not source_compile_info.exists():
        raise FileNotFoundError(source_compile_info)

    pipeline_path = run_dir / "compile.yaml"
    compile_info_path = run_dir / "compile_info.json"
    diagnostic_path = run_dir / "routing_diagnostic.json"
    stdout_path = run_dir / "stdout.txt"
    stderr_path = run_dir / "stderr.txt"
    for path in (compile_info_path, diagnostic_path, stdout_path, stderr_path):
        path.unlink(missing_ok=True)
    _prepare_pipeline(source_yaml, pipeline_path, compile_info_path)

    env = os.environ.copy()
    env["QRET_ROUTING_DIAGNOSTIC_JSON"] = str(diagnostic_path.resolve())
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    command = [
        "/usr/bin/time",
        "-v",
        str(qret.resolve()),
        "compile",
        "--pipeline",
        str(pipeline_path.resolve()),
        "--verbose",
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
            f"qret failed for {case_name} with exit {completed.returncode}:\n"
            f"{completed.stderr[-4000:]}"
        )
    if not compile_info_path.exists() or not diagnostic_path.exists():
        raise RuntimeError(f"qret did not emit all diagnostics for {case_name}")

    baseline = _load_json(source_compile_info)
    observed = _load_json(compile_info_path)
    diagnostic = _load_json(diagnostic_path)
    semantic_differences = {
        field: {"baseline": baseline.get(field), "observed": observed.get(field)}
        for field in SEMANTIC_FIELDS
        if baseline.get(field) != observed.get(field)
    }
    beat_advances = int(diagnostic.get("beat_advances", 0))
    result: dict[str, Any] = {
        "status": "ok",
        "case_name": case_name,
        "molecule": molecule,
        "topology_name": topology,
        "grid": topology.removeprefix("aware_"),
        "cache_key": source_row["cache_key"],
        "qasm_hash": source_row["qasm_hash"],
        "optimized_ir_hash": source_row["optimized_ir_hash"],
        "topology_hash": source_row["topology_hash"],
        "source_compile_yaml": str(source_yaml.relative_to(REPO_ROOT)),
        "source_compile_yaml_hash": _sha256(source_yaml),
        "qret_executable": _display_path(qret),
        "qret_executable_hash": qret_hash,
        "qret_core_library": _display_path(qret_core_path),
        "qret_core_library_hash": qret_core_hash,
        "qret_core_library_hash_capture": "at_case_execution",
        "elapsed_seconds": elapsed,
        "gnu_time_max_rss_kb": int(
            _gnu_time_value(completed.stderr, "Maximum resident set size (kbytes)") or 0
        ),
        "gnu_time_swaps": int(_gnu_time_value(completed.stderr, "Swaps") or 0),
        "baseline_runtime": baseline.get("runtime"),
        "runtime": observed.get("runtime"),
        "runtime_without_topology": observed.get("runtime_without_topology"),
        "runtime_topology_overhead": (
            int(observed["runtime"]) - int(observed["runtime_without_topology"])
        ),
        "qubit_volume": observed.get("qubit_volume"),
        "code_distance": observed.get("code_distance"),
        "physical_qubits": observed.get("num_physical_qubits"),
        "semantic_match": not semantic_differences,
        "semantic_differences": semantic_differences,
        "diagnostic_schema": diagnostic.get("schema_version"),
        "initial_beat": diagnostic.get("initial_beat"),
        "final_beat": diagnostic.get("final_beat"),
        "beat_advances": beat_advances,
        "runnable_blocked_beat_advances": diagnostic.get(
            "runnable_blocked_beat_advances"
        ),
        "reserved_only_beat_advances": diagnostic.get("reserved_only_beat_advances"),
        "other_beat_advances": diagnostic.get("other_beat_advances"),
        "max_consecutive_no_run_beats": diagnostic.get(
            "max_consecutive_no_run_beats"
        ),
        "successful_instruction_runs": diagnostic.get("successful_instruction_runs"),
        "loop_iterations": diagnostic.get("loop_iterations"),
        "runnable_blocked_fraction": (
            float(diagnostic.get("runnable_blocked_beat_advances", 0)) / beat_advances
            if beat_advances
            else 0.0
        ),
    }
    for inst_type in INSTRUCTION_TYPES:
        key = inst_type.lower()
        attempts = _type_value(diagnostic, "attempts_by_type", inst_type)
        failures = _type_value(diagnostic, "failed_attempts_by_type", inst_type)
        result[f"{key}_attempts"] = attempts
        result[f"{key}_failed_attempts"] = failures
        result[f"{key}_failure_fraction"] = failures / attempts if attempts else 0.0
    for inst_type in ("LATTICE_SURGERY_MAGIC", "CNOT"):
        key = inst_type.lower()
        result[f"{key}_path_coordinate_count"] = _path_value(
            diagnostic, inst_type, "path_coordinate_count"
        )
        result[f"{key}_mean_path_coordinates"] = _path_value(
            diagnostic, inst_type, "mean_path_coordinates_per_instruction"
        )
        result[f"{key}_max_path_coordinates"] = _path_value(
            diagnostic, inst_type, "max_path_coordinates"
        )
    published_diagnostic = output_root / "diagnostics" / f"{case_name}.json"
    _write_json(published_diagnostic, diagnostic)
    result["routing_diagnostic_path"] = str(published_diagnostic.relative_to(REPO_ROOT))
    _write_json(summary_path, result)
    return result


def _write_outputs(output_root: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    jsonl_path = output_root / "results.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(dict(row), sort_keys=True) + "\n")

    csv_fields = [
        key
        for key in rows[0]
        if key not in {"semantic_differences"}
    ]
    with (output_root / "results.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=csv_fields,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)

    h7_baseline = next(
        row for row in rows if row["molecule"] == "H7" and row["topology_name"] == "aware_10x10"
    )
    baseline_runtime = int(h7_baseline["runtime"])
    lines = [
        "# Fixed-circuit qret routing diagnostic",
        "",
        "The compiled circuit is fixed within each molecule. This experiment changes only the grid topology and records aggregate routing counters.",
        "",
        "| case | runtime (beats) | vs H7 10x10 | blocked beat advances | max no-run streak | magic fail % | CNOT fail % | magic mean path | CNOT mean path | semantic match |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        if row["molecule"] == "H7":
            delta = (int(row["runtime"]) / baseline_runtime - 1.0) * 100.0
            delta_text = f"{delta:+.3f}%"
        else:
            delta_text = "control"
        lines.append(
            "| {case} | {runtime:,} | {delta} | {blocked:,} | {streak:,} | {magic:.3f}% | {cnot:.3f}% | {magic_path:.3f} | {cnot_path:.3f} | {match} |".format(
                case=row["case_name"],
                runtime=int(row["runtime"]),
                delta=delta_text,
                blocked=int(row["runnable_blocked_beat_advances"]),
                streak=int(row["max_consecutive_no_run_beats"]),
                magic=100.0 * float(row["lattice_surgery_magic_failure_fraction"]),
                cnot=100.0 * float(row["cnot_failure_fraction"]),
                magic_path=float(row["lattice_surgery_magic_mean_path_coordinates"]),
                cnot_path=float(row["cnot_mean_path_coordinates"]),
                match="yes" if row["semantic_match"] else "no",
            )
        )
    h7_8x8 = next(
        row
        for row in rows
        if row["molecule"] == "H7" and row["topology_name"] == "aware_8x8"
    )
    h7_8x10 = next(
        row
        for row in rows
        if row["molecule"] == "H7" and row["topology_name"] == "aware_8x10"
    )
    runtime_delta = int(h7_8x8["runtime"]) - int(h7_baseline["runtime"])
    overhead_delta = int(h7_8x8["runtime_topology_overhead"]) - int(
        h7_baseline["runtime_topology_overhead"]
    )
    magic_failed_delta = (
        int(h7_8x8["lattice_surgery_magic_failed_attempts"])
        / int(h7_baseline["lattice_surgery_magic_failed_attempts"])
        - 1.0
    ) * 100.0
    magic_path_delta = (
        float(h7_8x8["lattice_surgery_magic_mean_path_coordinates"])
        / float(h7_baseline["lattice_surgery_magic_mean_path_coordinates"])
        - 1.0
    ) * 100.0
    cnot_path_delta = (
        float(h7_8x8["cnot_mean_path_coordinates"])
        / float(h7_baseline["cnot_mean_path_coordinates"])
        - 1.0
    ) * 100.0
    peak_rss_kb = max(int(row["gnu_time_max_rss_kb"]) for row in rows)
    max_swaps = max(int(row["gnu_time_swaps"]) for row in rows)
    qret_core_hashes = {str(row["qret_core_library_hash"]) for row in rows}
    if len(qret_core_hashes) != 1:
        raise RuntimeError("diagnostic cases used different qret-core libraries")
    qret_core_hash = next(iter(qret_core_hashes))
    qret_core_hash_captures = {
        str(row.get("qret_core_library_hash_capture", "unspecified")) for row in rows
    }
    qret_core_hash_capture = ", ".join(sorted(qret_core_hash_captures))
    diagnostic_patch_hash = h7_baseline.get("routing_diagnostic_patch_sha256")
    lines.extend(
        [
            "",
            "`failed_attempts` means `ScLsSimulator::Run` rejected an otherwise runnable queue candidate at that beat. It is an aggregate contention/scheduling signal, not a simulator-internal failure-reason classification.",
            "",
            "## Findings",
            "",
            f"- H7 topology-free runtime is fixed at {int(h7_baseline['runtime_without_topology']):,} beats. The 8x8 runtime penalty is {runtime_delta:,} beats, exactly equal to the topology-overhead increase of {overhead_delta:,} beats versus 10x10.",
            f"- H7 8x8 increases the mean magic path from {float(h7_baseline['lattice_surgery_magic_mean_path_coordinates']):.3f} to {float(h7_8x8['lattice_surgery_magic_mean_path_coordinates']):.3f} coordinates ({magic_path_delta:+.1f}%). Rejected magic attempts rise by {magic_failed_delta:+.1f}%, and their fraction rises from {100.0 * float(h7_baseline['lattice_surgery_magic_failure_fraction']):.2f}% to {100.0 * float(h7_8x8['lattice_surgery_magic_failure_fraction']):.2f}%.",
            f"- H7 CNOT rejection does not increase: its rejected-attempt fraction is {100.0 * float(h7_8x8['cnot_failure_fraction']):.2f}% on 8x8 and {100.0 * float(h7_baseline['cnot_failure_fraction']):.2f}% on 10x10. Its mean path increases only {cnot_path_delta:+.1f}%.",
            f"- H7 8x10 returns to the baseline runtime while its mean magic path is {float(h7_8x10['lattice_surgery_magic_mean_path_coordinates']):.3f}. This places the observed transition between 8x8 and the first tested grid with one expanded dimension.",
            f"- The maximum consecutive no-run streak remains {int(h7_8x8['max_consecutive_no_run_beats'])} beats in every case. The penalty is therefore associated with repeated aggregate routing/scheduling rejection, not a longer single stall episode.",
            "",
            "These observations upgrade the generic routing-congestion explanation: the H7 8x8 penalty is specifically associated with longer magic-delivery paths and many more rejected `LATTICE_SURGERY_MAGIC` attempts. Exact simulator failure reasons and simultaneous cell occupancy remain unresolved because this diagnostic records aggregate `Run` outcomes only.",
            "",
            "## Execution resources",
            "",
            f"- peak qret RSS: {peak_rss_kb:,} KiB ({peak_rss_kb / 1024**2:.2f} GiB)",
            f"- maximum swaps reported by GNU time: {max_swaps}",
            "- execution: sequential tmux session with `MemoryHigh=44G`, `MemoryMax=48G`",
            f"- diagnostic `libqret-core.so` SHA-256: `{qret_core_hash}`",
            f"- library hash capture: `{qret_core_hash_capture}`",
            *(
                [f"- local diagnostic patch SHA-256: `{diagnostic_patch_hash}`"]
                if diagnostic_patch_hash
                else []
            ),
            "",
        ]
    )
    (output_root / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--qret", type=Path, default=DEFAULT_QRET)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    results_path = args.results.expanduser().resolve()
    output_root = args.output.expanduser().resolve()
    qret = args.qret.expanduser().resolve()
    if not qret.is_file():
        raise FileNotFoundError(qret)
    selected = _selected_rows(results_path)
    if args.dry_run:
        for row in selected:
            print(row["molecule"], row["topology_name"], row["cache_key"])
        return 0

    output_root.mkdir(parents=True, exist_ok=True)
    qret_hash = _sha256(qret)
    qret_core_path = _linked_qret_core(qret)
    qret_core_hash = _sha256(qret_core_path)
    rows = [
        _run_case(
            row,
            qret=qret,
            qret_hash=qret_hash,
            qret_core_path=qret_core_path,
            qret_core_hash=qret_core_hash,
            output_root=output_root,
            force=args.force,
        )
        for row in selected
    ]
    _write_outputs(output_root, rows)
    shutil.rmtree(output_root / ".work", ignore_errors=True)
    if not all(bool(row["semantic_match"]) for row in rows):
        raise RuntimeError("one or more diagnostic runs changed semantic resource metrics")
    print(output_root / "summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
