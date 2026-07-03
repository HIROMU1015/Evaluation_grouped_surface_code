#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trotterlib import surface_code as sc  # noqa: E402


DEFAULT_OUTPUT = ROOT / "artifacts" / "surface_code_basis_decompose_ab"
PF_LABEL = "4th(new_2)"
COMPILE_MODE = "ftqc_compile_topology_qec"
MAX_CASE_CHAIN_LENGTH = 5


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{time.time_ns()}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def git_output(args: list[str]) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unknown"


def meminfo() -> dict[str, int]:
    ret: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, rest = line.split(":", 1)
            value = rest.strip().split()[0]
            ret[key] = int(value)
    except Exception:
        pass
    return ret


def preflight(path: Path) -> dict[str, Any]:
    usage = shutil.disk_usage(path if path.exists() else path.parent)
    info = meminfo()
    return {
        "mem_total_kb": info.get("MemTotal"),
        "mem_available_kb": info.get("MemAvailable"),
        "swap_total_kb": info.get("SwapTotal"),
        "swap_free_kb": info.get("SwapFree"),
        "disk_total_bytes": usage.total,
        "disk_free_bytes": usage.free,
    }


def qret_version() -> str:
    try:
        return subprocess.check_output(
            [str(Path(sc.SURFACE_CODE_QCSF_PATH)), "--version"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()
    except Exception as exc:
        return f"unavailable: {exc!r}"


def environment_payload() -> dict[str, Any]:
    try:
        import qiskit

        qiskit_version = getattr(qiskit, "__version__", "unknown")
    except Exception as exc:
        qiskit_version = f"import-error: {exc!r}"
    return {
        "repo": str(ROOT),
        "commit": git_output(["rev-parse", "HEAD"]),
        "branch": git_output(["branch", "--show-current"]),
        "dirty_status": git_output(["status", "--short"]),
        "python": sys.version,
        "python_executable": sys.executable,
        "qiskit": qiskit_version,
        "qret_path": str(Path(sc.SURFACE_CODE_QCSF_PATH).expanduser().resolve()),
        "qret_version": qret_version(),
        "qret_hash": sc.file_sha256(sc.SURFACE_CODE_QCSF_PATH)
        if Path(sc.SURFACE_CODE_QCSF_PATH).exists()
        else None,
        "topology_path": str(Path(sc.SURFACE_CODE_TOPOLOGY_PATH).expanduser().resolve()),
        "topology_hash": sc.file_sha256(sc.SURFACE_CODE_TOPOLOGY_PATH)
        if Path(sc.SURFACE_CODE_TOPOLOGY_PATH).exists()
        else None,
        "compile_mode": COMPILE_MODE,
        "compile_info_output_mode": sc.SURFACE_CODE_COMPILE_INFO_OUTPUT_MODE,
        "rz_helper_opt_mode": sc.SURFACE_CODE_RZ_HELPER_OPT_MODE,
        "rz_helper_batch_size": int(sc.SURFACE_CODE_RZ_HELPER_BATCH_SIZE),
        "qasm_basis_gates": list(sc.SURFACE_CODE_QASM_BASIS_GATES),
        "default_qasm_decompose_reps": int(sc.SURFACE_CODE_QASM_DECOMPOSE_REPS),
        "profile_note": "application-cold per run; OS page cache is not dropped",
    }


def read_proc_rows() -> dict[int, dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        pid = int(proc.name)
        try:
            stat = (proc / "stat").read_text()
            rparen = stat.rfind(")")
            fields = stat[rparen + 2 :].split()
            ppid = int(fields[1])
            rss_kb = 0
            for line in (proc / "status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    rss_kb = int(line.split()[1])
                    break
            raw_cmd = (proc / "cmdline").read_bytes().replace(b"\0", b" ").strip()
            command = raw_cmd.decode("utf-8", errors="replace")
            rows[pid] = {"pid": pid, "ppid": ppid, "rss_kb": rss_kb, "command": command}
        except Exception:
            continue
    return rows


def descendants(root_pid: int, rows: Mapping[int, Mapping[str, Any]]) -> list[int]:
    children: dict[int, list[int]] = {}
    for pid, row in rows.items():
        children.setdefault(int(row.get("ppid") or 0), []).append(int(pid))
    out: list[int] = []
    stack = [root_pid]
    while stack:
        current = stack.pop()
        for child in children.get(current, []):
            out.append(child)
            stack.append(child)
    return out


def sample_tree(root_pid: int) -> dict[str, Any]:
    rows = read_proc_rows()
    pids = [root_pid, *descendants(root_pid, rows)]
    selected = [rows[pid] for pid in pids if pid in rows]
    tree_rss = sum(int(row.get("rss_kb") or 0) for row in selected)
    qret_rows = [row for row in selected if "qret" in str(row.get("command") or "")]
    qret_rss = sum(int(row.get("rss_kb") or 0) for row in qret_rows)
    root_rss = int(rows.get(root_pid, {}).get("rss_kb") or 0)
    return {
        "timestamp": time.time(),
        "tree_rss_kb": tree_rss,
        "root_rss_kb": root_rss,
        "qret_rss_kb": qret_rss,
        "pid_count": len(selected),
        "qret_pid_count": len(qret_rows),
        "commands": [
            {
                "pid": int(row["pid"]),
                "rss_kb": int(row.get("rss_kb") or 0),
                "kind": "qret" if row in qret_rows else "worker",
                "command": str(row.get("command") or "")[:240],
            }
            for row in selected
            if int(row.get("rss_kb") or 0) > 0
        ],
    }


def stage_metrics_path(root: Path, primary: str, cache_hit: str) -> Path | None:
    primary_path = root / primary
    cache_path = root / cache_hit
    if primary_path.exists():
        return primary_path
    if cache_path.exists():
        return cache_path
    return None


def stage_by_name(metrics: Mapping[str, Any], name: str) -> dict[str, Any]:
    for item in metrics.get("stages") or []:
        if isinstance(item, Mapping) and item.get("name") == name:
            return dict(item)
    return {}


def selected_resource_metrics(metrics: Mapping[str, Any]) -> dict[str, Any]:
    resource_keys = (
        "magic_state_consumption_count",
        "magic_state_consumption_depth",
        "runtime_without_topology",
        "runtime",
        "chip_cell_count",
        "qubit_volume",
        "num_physical_qubits",
        "code_distance",
        "gate_count",
        "gate_depth",
        "magic_factory_count",
        "measurement_feedback_count",
        "measurement_feedback_depth",
        "chip_cell_active_qubit_area_ave",
        "chip_cell_active_qubit_area_peak",
        "chip_cell_active_qubit_area_ratio_ave",
        "chip_cell_active_qubit_area_ratio_peak",
        "chip_cell_algorithmic_qubit_ave",
        "chip_cell_algorithmic_qubit_peak",
        "chip_cell_algorithmic_qubit_ratio_ave",
        "chip_cell_algorithmic_qubit_ratio_peak",
        "entanglement_consumption_rate_ave",
        "entanglement_consumption_rate_peak",
        "gate_throughput_ave",
        "gate_throughput_peak",
        "magic_state_consumption_rate_ave",
        "magic_state_consumption_rate_peak",
        "measurement_feedback_rate_ave",
        "measurement_feedback_rate_peak",
    )
    return {key: metrics.get(key) for key in resource_keys if key in metrics}


def artifact_summary(artifact: sc.SurfaceCodeStepArtifact, metrics: Mapping[str, Any]) -> dict[str, Any]:
    qasm_path = Path(artifact.qasm_path)
    ir_path = Path(artifact.ir_path)
    opt_path = Path(artifact.optimized_ir_path)
    stream_path = artifact.runtime_root / "step_instruction_stream_summary.json"
    stream = read_json(stream_path) if stream_path.exists() else {}
    compile_root = sc._compile_runtime_root(artifact, sc.SurfaceCodeArchitecture(compile_mode=COMPILE_MODE))
    compile_info_path = compile_root / "compile_info.json"
    prepare_metrics_path = stage_metrics_path(
        artifact.runtime_root,
        sc._PREPARE_STAGE_METRICS_FILENAME,
        sc._PREPARE_STAGE_CACHE_HIT_METRICS_FILENAME,
    )
    compile_metrics_path = stage_metrics_path(
        compile_root,
        sc._COMPILE_STAGE_METRICS_FILENAME,
        sc._COMPILE_STAGE_CACHE_HIT_METRICS_FILENAME,
    )
    prepare_metrics = read_json(prepare_metrics_path) if prepare_metrics_path else {}
    compile_metrics = read_json(compile_metrics_path) if compile_metrics_path else {}
    qasm_stage = stage_by_name(prepare_metrics, "qasm_text")
    basis_stage = stage_by_name(prepare_metrics, "basis_circuit")
    qret_parse_stage = stage_by_name(prepare_metrics, "qret_parse")
    qret_compile_stage = stage_by_name(compile_metrics, "qret_compile")
    return {
        "artifact_runtime_root": str(artifact.runtime_root),
        "compile_runtime_root": str(compile_root),
        "qasm_path": str(qasm_path),
        "ir_path": str(ir_path),
        "optimized_ir_path": str(opt_path),
        "compile_info_path": str(compile_info_path),
        "prepare_stage_metrics_path": str(prepare_metrics_path) if prepare_metrics_path else None,
        "compile_stage_metrics_path": str(compile_metrics_path) if compile_metrics_path else None,
        "qasm_hash": sc.file_sha256(qasm_path),
        "qasm_size_bytes": qasm_path.stat().st_size,
        "ir_hash": sc.file_sha256(ir_path),
        "ir_size_bytes": ir_path.stat().st_size,
        "optimized_ir_hash": sc.file_sha256(opt_path),
        "optimized_ir_size_bytes": opt_path.stat().st_size,
        "compile_info_hash": sc.file_sha256(compile_info_path) if compile_info_path.exists() else None,
        "compile_info_size_bytes": compile_info_path.stat().st_size if compile_info_path.exists() else None,
        "num_logical_qubits": int(artifact.num_logical_qubits),
        "step_rz_count": int(artifact.step_rz_count),
        "step_rz_depth": int(metrics.get("step_rz_depth") or 0),
        "step_magic_state_count": int(artifact.step_magic_state_count),
        "step_magic_state_depth": int(artifact.step_magic_state_depth),
        "peak_magic_layer": int(artifact.peak_magic_layer),
        "instruction_count": int(artifact.instruction_count),
        "gate_depth": int(artifact.gate_depth),
        "normalized_instruction_stream_hash": stream.get("normalized_instruction_stream_hash"),
        "opcode_count": stream.get("opcode_count"),
        "resource_metrics": selected_resource_metrics(metrics),
        "stage_extract": {
            "basis_circuit": basis_stage,
            "qasm_text": qasm_stage,
            "qret_parse": qret_parse_stage,
            "qret_compile": qret_compile_stage,
        },
    }


def worker(args: argparse.Namespace) -> int:
    if int(args.chain_length) > MAX_CASE_CHAIN_LENGTH:
        raise ValueError(
            "profile_basis_decomposition_reps.py is limited to H5 or smaller "
            f"for this A/B task; got H{int(args.chain_length)}"
        )
    run_dir = args.run_dir.resolve()
    cache_root = args.cache_root.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    cache_root.mkdir(parents=True, exist_ok=True)
    sc.SURFACE_CODE_CACHE_DIR = cache_root
    sc.SURFACE_CODE_QASM_DECOMPOSE_REPS = int(args.reps)
    os.environ["SURFACE_CODE_PROFILE_RSS_SAMPLING"] = "1"
    os.environ["SURFACE_CODE_PROFILE_RSS_SAMPLING_INTERVAL_SEC"] = str(args.stage_sample_interval)
    os.environ["SURFACE_CODE_COMPILE_INFO_OUTPUT_MODE"] = "summary"

    architecture = sc.SurfaceCodeArchitecture(compile_mode=COMPILE_MODE)
    ham_name = sc.grouped_hchain_ham_name(int(args.chain_length))
    started = time.perf_counter()
    prepare_started = time.perf_counter()
    artifact = sc.prepare_grouped_surface_code_step_artifact(
        ham_name,
        PF_LABEL,
        architecture=architecture,
    )
    prepare_elapsed = time.perf_counter() - prepare_started
    compile_started = time.perf_counter()
    metrics = sc.compile_prepared_surface_code_step_artifact(
        artifact,
        architecture,
        reuse_cache=False,
    )
    compile_elapsed = time.perf_counter() - compile_started
    total_elapsed = time.perf_counter() - started
    result = {
        "status": "ok",
        "case": f"H{int(args.chain_length)}",
        "pf_label": PF_LABEL,
        "scope": "uncontrolled_pf_one_step",
        "qasm_decompose_reps": int(args.reps),
        "cache_root": str(cache_root),
        "prepare_elapsed_sec": prepare_elapsed,
        "compile_elapsed_sec": compile_elapsed,
        "total_elapsed_sec": total_elapsed,
        "artifact": artifact_summary(artifact, metrics),
        "metrics": dict(metrics),
    }
    write_json(run_dir / "worker_result.json", result)
    return 0


def run_one(
    *,
    output_root: Path,
    chain_length: int,
    reps: int,
    run_index: int,
    sample_interval: float,
) -> dict[str, Any]:
    label = f"h{chain_length}_reps{reps}_run{run_index}"
    run_dir = output_root / label
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    cache_root = run_dir / "surface_code_cache"
    write_json(run_dir / "preflight.json", preflight(output_root))
    env = dict(os.environ)
    env.update(
        {
            "PYTHONPATH": str(SRC),
            "PYTHONHASHSEED": "0",
            "LC_ALL": "C",
            "LANG": "C",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
            "SURFACE_CODE_COMPILE_INFO_OUTPUT_MODE": "summary",
        }
    )
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "worker",
        "--chain-length",
        str(chain_length),
        "--reps",
        str(reps),
        "--run-dir",
        str(run_dir),
        "--cache-root",
        str(cache_root),
        "--stage-sample-interval",
        str(sample_interval),
    ]
    started = time.perf_counter()
    proc = subprocess.Popen(
        cmd,
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    samples_path = run_dir / "samples.jsonl"
    peak = {
        "tree_rss_kb": 0,
        "root_rss_kb": 0,
        "qret_rss_kb": 0,
        "tree_peak_sample": None,
    }
    with samples_path.open("w", encoding="utf-8") as samples:
        while proc.poll() is None:
            sample = sample_tree(proc.pid)
            samples.write(json.dumps(sample, ensure_ascii=True) + "\n")
            samples.flush()
            if int(sample["tree_rss_kb"]) > int(peak["tree_rss_kb"]):
                peak["tree_rss_kb"] = int(sample["tree_rss_kb"])
                peak["tree_peak_sample"] = sample
            peak["root_rss_kb"] = max(int(peak["root_rss_kb"]), int(sample["root_rss_kb"]))
            peak["qret_rss_kb"] = max(int(peak["qret_rss_kb"]), int(sample["qret_rss_kb"]))
            time.sleep(sample_interval)
        final_sample = sample_tree(proc.pid)
        samples.write(json.dumps(final_sample, ensure_ascii=True) + "\n")
    stdout, stderr = proc.communicate()
    elapsed = time.perf_counter() - started
    (run_dir / "worker_stdout.log").write_text(stdout or "", encoding="utf-8")
    (run_dir / "worker_stderr.log").write_text(stderr or "", encoding="utf-8")
    worker_result_path = run_dir / "worker_result.json"
    worker_result = read_json(worker_result_path) if worker_result_path.exists() else {}
    result = {
        "label": label,
        "status": "ok" if proc.returncode == 0 else "failed",
        "returncode": proc.returncode,
        "monitor_elapsed_sec": elapsed,
        "command": cmd,
        "run_dir": str(run_dir),
        "samples_path": str(samples_path),
        "peak_tree_rss_kb": peak["tree_rss_kb"],
        "peak_parent_rss_kb": peak["root_rss_kb"],
        "peak_qret_rss_kb": peak["qret_rss_kb"],
        "tree_peak_sample": peak["tree_peak_sample"],
        "worker_result": worker_result,
    }
    write_json(run_dir / "result.json", result)
    if proc.returncode != 0:
        raise RuntimeError(f"{label} failed; see {run_dir}")
    return result


def median(values: list[float]) -> float | None:
    if not values:
        return None
    return float(statistics.median(values))


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in results:
        wr = item.get("worker_result") or {}
        key = f"{wr.get('case')}:reps{wr.get('qasm_decompose_reps')}"
        groups.setdefault(key, []).append(item)
    group_summaries: dict[str, Any] = {}
    for key, rows in groups.items():
        totals = [float((r["worker_result"] or {}).get("total_elapsed_sec") or 0) for r in rows]
        prepares = [float((r["worker_result"] or {}).get("prepare_elapsed_sec") or 0) for r in rows]
        compiles = [float((r["worker_result"] or {}).get("compile_elapsed_sec") or 0) for r in rows]
        group_summaries[key] = {
            "runs": len(rows),
            "total_elapsed_sec": {"median": median(totals), "min": min(totals), "max": max(totals)},
            "prepare_elapsed_sec": {"median": median(prepares), "min": min(prepares), "max": max(prepares)},
            "compile_elapsed_sec": {"median": median(compiles), "min": min(compiles), "max": max(compiles)},
            "peak_tree_rss_kb": {
                "median": median([float(r["peak_tree_rss_kb"]) for r in rows]),
                "min": min(int(r["peak_tree_rss_kb"]) for r in rows),
                "max": max(int(r["peak_tree_rss_kb"]) for r in rows),
            },
            "peak_parent_rss_kb": {
                "median": median([float(r["peak_parent_rss_kb"]) for r in rows]),
                "min": min(int(r["peak_parent_rss_kb"]) for r in rows),
                "max": max(int(r["peak_parent_rss_kb"]) for r in rows),
            },
            "peak_qret_rss_kb": {
                "median": median([float(r["peak_qret_rss_kb"]) for r in rows]),
                "min": min(int(r["peak_qret_rss_kb"]) for r in rows),
                "max": max(int(r["peak_qret_rss_kb"]) for r in rows),
            },
            "hashes": [
                {
                    "label": r["label"],
                    "qasm": (((r.get("worker_result") or {}).get("artifact") or {}).get("qasm_hash")),
                    "ir": (((r.get("worker_result") or {}).get("artifact") or {}).get("ir_hash")),
                    "optimized_ir": (((r.get("worker_result") or {}).get("artifact") or {}).get("optimized_ir_hash")),
                    "stream": (((r.get("worker_result") or {}).get("artifact") or {}).get("normalized_instruction_stream_hash")),
                    "compile_info": (((r.get("worker_result") or {}).get("artifact") or {}).get("compile_info_hash")),
                }
                for r in rows
            ],
        }
    comparisons: dict[str, Any] = {}
    cases = sorted({(r.get("worker_result") or {}).get("case") for r in results})
    for case in cases:
        if not case:
            continue
        base_rows = groups.get(f"{case}:reps8") or []
        cand_rows = groups.get(f"{case}:reps4") or []
        if not base_rows or not cand_rows:
            continue
        base = (base_rows[0].get("worker_result") or {}).get("artifact") or {}
        cand = (cand_rows[0].get("worker_result") or {}).get("artifact") or {}
        comparisons[str(case)] = {
            "qasm_byte_identical": base.get("qasm_hash") == cand.get("qasm_hash")
            and base.get("qasm_size_bytes") == cand.get("qasm_size_bytes"),
            "ir_hash_match": base.get("ir_hash") == cand.get("ir_hash"),
            "optimized_ir_hash_match": base.get("optimized_ir_hash") == cand.get("optimized_ir_hash"),
            "instruction_stream_hash_match": base.get("normalized_instruction_stream_hash")
            == cand.get("normalized_instruction_stream_hash"),
            "resource_metrics_match": base.get("resource_metrics") == cand.get("resource_metrics"),
            "baseline_artifact": base,
            "candidate_artifact": cand,
        }
    return {"groups": group_summaries, "comparisons": comparisons}


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    worker_parser = sub.add_parser("worker")
    worker_parser.add_argument("--chain-length", type=int, required=True)
    worker_parser.add_argument("--reps", type=int, required=True)
    worker_parser.add_argument("--run-dir", type=Path, required=True)
    worker_parser.add_argument("--cache-root", type=Path, required=True)
    worker_parser.add_argument("--stage-sample-interval", type=float, default=0.05)

    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cases", nargs="+", default=["H4", "H5"])
    parser.add_argument("--reps", nargs="+", type=int, default=[8, 4])
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--sample-interval", type=float, default=0.05)
    parser.add_argument("--reset-output", action="store_true")
    args = parser.parse_args()
    if args.cmd == "worker":
        return worker(args)

    output_root = args.output_root.resolve()
    if args.reset_output:
        shutil.rmtree(output_root, ignore_errors=True)
    output_root.mkdir(parents=True, exist_ok=True)
    write_json(output_root / "environment.json", environment_payload())
    write_json(output_root / "preflight.json", preflight(output_root))

    results: list[dict[str, Any]] = []
    for case in args.cases:
        if not str(case).startswith("H"):
            raise ValueError(f"case must be Hn, got {case!r}")
        chain_length = int(str(case)[1:])
        if chain_length > MAX_CASE_CHAIN_LENGTH:
            raise ValueError(
                "profile_basis_decomposition_reps.py is limited to H5 or smaller "
                f"for this A/B task; got H{chain_length}"
            )
        for run_index in range(1, int(args.runs) + 1):
            for reps in args.reps:
                result = run_one(
                    output_root=output_root,
                    chain_length=chain_length,
                    reps=int(reps),
                    run_index=run_index,
                    sample_interval=float(args.sample_interval),
                )
                results.append(result)
                write_json(
                    output_root / "partial_summary.json",
                    {"results": results, **summarize(results)},
                )
    summary = {"results": results, **summarize(results)}
    write_json(output_root / "summary.json", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
