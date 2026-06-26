#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import json
import os
import resource
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from trotterlib import surface_code as sc  # noqa: E402


def _current_rss_kb() -> int | None:
    status_path = Path("/proc/self/status")
    try:
        with status_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(parts[1])
                    return None
    except (OSError, ValueError):
        return None
    return None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{time.time_ns()}.tmp")
    try:
        tmp.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        tmp.replace(path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root is not an object: {path}")
    return payload


def _set_runtime_options(args: argparse.Namespace) -> None:
    sc.SURFACE_CODE_CACHE_DIR = args.cache_root.expanduser().resolve()
    sc.SURFACE_CODE_RZ_HELPER_BATCH_SIZE = int(args.batch_size)
    os.environ["SURFACE_CODE_PROFILE_RSS_SAMPLING"] = "1"
    os.environ["SURFACE_CODE_PROFILE_RSS_SAMPLING_INTERVAL_SEC"] = str(
        float(args.rss_sampling_interval)
    )
    os.environ["SURFACE_CODE_COMPILE_INFO_EXTRACTION_MODE"] = str(
        args.compile_info_extraction_mode
    )


def _semantics(artifact: sc.SurfaceCodeStepArtifact) -> dict[str, Any]:
    stream_path = artifact.runtime_root / "step_instruction_stream_summary.json"
    stream = _load_json(stream_path) if stream_path.exists() else {}
    return {
        "qasm_hash": artifact.qasm_hash,
        "optimized_ir_hash": artifact.optimized_ir_hash,
        "normalized_instruction_stream_hash": stream.get(
            "normalized_instruction_stream_hash"
        ),
        "opcode_count": stream.get("opcode_count"),
        "instruction_count": artifact.instruction_count,
        "gate_depth": artifact.gate_depth,
        "magic_state_count": artifact.step_magic_state_count,
        "magic_state_depth": artifact.step_magic_state_depth,
        "peak_magic_layer": artifact.peak_magic_layer,
    }


def _semantic_core(semantics: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "normalized_instruction_stream_hash",
        "opcode_count",
        "instruction_count",
        "gate_depth",
        "magic_state_count",
        "magic_state_depth",
        "peak_magic_layer",
    )
    return {key: semantics.get(key) for key in keys}


def _metrics_summary(metrics: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "magic_state_consumption_count",
        "magic_state_consumption_depth",
        "runtime",
        "runtime_without_topology",
        "qubit_volume",
        "chip_cell_count",
        "code_distance",
        "num_physical_qubits",
        "gate_count",
        "gate_depth",
        "compile_cache_hit",
    )
    return {key: metrics.get(key) for key in keys}


def _compile_start_rss(compile_metrics_path: Path) -> int | None:
    if not compile_metrics_path.exists():
        return None
    payload = _load_json(compile_metrics_path)
    for stage in payload.get("stages", []):
        if isinstance(stage, dict) and stage.get("name") == "compile_cache_lookup":
            value = stage.get("python_current_rss_before_kb")
            return None if value is None else int(value)
    return None


def _qret_subprocess_peak(compile_metrics_path: Path) -> int | None:
    if not compile_metrics_path.exists():
        return None
    payload = _load_json(compile_metrics_path)
    peaks = []
    for stage in payload.get("stages", []):
        if not isinstance(stage, dict):
            continue
        result = stage.get("result")
        if isinstance(result, dict) and result.get("subprocess_maxrss_kb") is not None:
            peaks.append(int(result["subprocess_maxrss_kb"]))
        if stage.get("subprocess_maxrss_kb") is not None:
            peaks.append(int(stage["subprocess_maxrss_kb"]))
    return max(peaks) if peaks else None


def _prepare(args: argparse.Namespace) -> dict[str, Any]:
    _set_runtime_options(args)
    started = time.perf_counter()
    architecture = sc.SurfaceCodeArchitecture(compile_mode=args.compile_mode)
    artifact = sc.prepare_grouped_surface_code_step_artifact(
        sc.grouped_hchain_ham_name(args.chain_length),
        args.pf_label,
        architecture=architecture,
    )
    elapsed = float(time.perf_counter() - started)
    artifact_path = artifact.runtime_root / "step_artifact.json"
    prepare_metrics_path = artifact.runtime_root / sc._PREPARE_STAGE_METRICS_FILENAME
    return {
        "phase": "prepare",
        "elapsed_seconds": elapsed,
        "ru_maxrss_kb": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        "current_rss_after_kb": _current_rss_kb(),
        "artifact_path": str(artifact_path),
        "prepare_metrics_path": str(prepare_metrics_path),
        "semantics": _semantics(artifact),
    }


def _compile(args: argparse.Namespace) -> dict[str, Any]:
    _set_runtime_options(args)
    artifact = sc.surface_code_step_artifact_from_dict(_load_json(args.artifact_path))
    architecture = sc.SurfaceCodeArchitecture(compile_mode=args.compile_mode)
    compile_root = sc._compile_runtime_root(artifact, architecture)
    started = time.perf_counter()
    metrics = sc.compile_prepared_surface_code_step_artifact(
        artifact,
        architecture,
        reuse_cache=not args.no_reuse_compile_cache,
    )
    elapsed = float(time.perf_counter() - started)
    compile_metrics_path = compile_root / (
        sc._COMPILE_STAGE_CACHE_HIT_METRICS_FILENAME
        if metrics.get("compile_cache_hit")
        else sc._COMPILE_STAGE_METRICS_FILENAME
    )
    return {
        "phase": "compile",
        "elapsed_seconds": elapsed,
        "ru_maxrss_kb": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        "current_rss_after_kb": _current_rss_kb(),
        "compile_start_current_rss_kb": _compile_start_rss(compile_metrics_path),
        "qret_subprocess_peak_rss_kb": _qret_subprocess_peak(compile_metrics_path),
        "compile_metrics_path": str(compile_metrics_path),
        "compile_cache_hit": bool(metrics.get("compile_cache_hit")),
        "metrics_summary": _metrics_summary(metrics),
    }


def _same_process(args: argparse.Namespace) -> dict[str, Any]:
    _set_runtime_options(args)
    architecture = sc.SurfaceCodeArchitecture(compile_mode=args.compile_mode)
    started = time.perf_counter()
    artifact = sc.prepare_grouped_surface_code_step_artifact(
        sc.grouped_hchain_ham_name(args.chain_length),
        args.pf_label,
        architecture=architecture,
    )
    compile_root = sc._compile_runtime_root(artifact, architecture)
    metrics = sc.compile_prepared_surface_code_step_artifact(
        artifact,
        architecture,
        reuse_cache=not args.no_reuse_compile_cache,
    )
    elapsed = float(time.perf_counter() - started)
    compile_metrics_path = compile_root / (
        sc._COMPILE_STAGE_CACHE_HIT_METRICS_FILENAME
        if metrics.get("compile_cache_hit")
        else sc._COMPILE_STAGE_METRICS_FILENAME
    )
    return {
        "phase": "same_process",
        "elapsed_seconds": elapsed,
        "ru_maxrss_kb": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        "current_rss_after_kb": _current_rss_kb(),
        "artifact_path": str(artifact.runtime_root / "step_artifact.json"),
        "prepare_metrics_path": str(
            artifact.runtime_root / sc._PREPARE_STAGE_METRICS_FILENAME
        ),
        "compile_metrics_path": str(compile_metrics_path),
        "compile_start_current_rss_kb": _compile_start_rss(compile_metrics_path),
        "qret_subprocess_peak_rss_kb": _qret_subprocess_peak(compile_metrics_path),
        "compile_cache_hit": bool(metrics.get("compile_cache_hit")),
        "semantics": _semantics(artifact),
        "metrics_summary": _metrics_summary(metrics),
    }


def _run_child(
    args: argparse.Namespace,
    phase: str,
    artifact_path: Path | None,
    cache_root: Path,
) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--child",
        phase,
        "--cache-root",
        str(cache_root),
        "--chain-length",
        str(args.chain_length),
        "--pf-label",
        args.pf_label,
        "--compile-mode",
        args.compile_mode,
        "--batch-size",
        str(args.batch_size),
        "--rss-sampling-interval",
        str(args.rss_sampling_interval),
        "--compile-info-extraction-mode",
        args.compile_info_extraction_mode,
    ]
    if args.no_reuse_compile_cache:
        cmd.append("--no-reuse-compile-cache")
    if artifact_path is not None:
        cmd.extend(["--artifact-path", str(artifact_path)])
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    started = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    elapsed = float(time.perf_counter() - started)
    if proc.returncode != 0:
        raise RuntimeError(
            f"{phase} child failed with code={proc.returncode}\n{proc.stderr}"
        )
    payload = json.loads(proc.stdout)
    payload["process_elapsed_seconds"] = elapsed
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--chain-length", type=int, default=4)
    parser.add_argument("--pf-label", default="4th(new_2)")
    parser.add_argument("--compile-mode", default="ftqc_compile_topology")
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--rss-sampling-interval", type=float, default=0.02)
    parser.add_argument(
        "--compile-info-extraction-mode",
        choices=("full_json_load", "top_level_metric_fields"),
        default="full_json_load",
    )
    parser.add_argument("--no-reuse-compile-cache", action="store_true")
    parser.add_argument("--artifact-path", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--reset-cache-root", action="store_true")
    parser.add_argument(
        "--child",
        choices=("prepare", "compile", "same_process"),
        default=None,
    )
    args = parser.parse_args()

    if args.child == "prepare":
        with contextlib.redirect_stdout(sys.stderr):
            payload = _prepare(args)
        print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
        return 0
    if args.child == "compile":
        if args.artifact_path is None:
            raise SystemExit("--child compile requires --artifact-path")
        with contextlib.redirect_stdout(sys.stderr):
            payload = _compile(args)
        print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
        return 0
    if args.child == "same_process":
        with contextlib.redirect_stdout(sys.stderr):
            payload = _same_process(args)
        print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
        return 0

    base_cache_root = args.cache_root.expanduser().resolve()
    if args.reset_cache_root:
        benchmark_root = (REPO_ROOT / "benchmark_results").resolve()
        try:
            base_cache_root.relative_to(benchmark_root)
        except ValueError as exc:
            raise SystemExit(
                "--reset-cache-root is only allowed under benchmark_results/"
            ) from exc
        shutil.rmtree(base_cache_root, ignore_errors=True)
    same_cache_root = base_cache_root / "same_process"
    split_cache_root = base_cache_root / "split_process"

    same = _run_child(args, "same_process", None, same_cache_root)
    prepare = _run_child(args, "prepare", None, split_cache_root)
    artifact_path = Path(str(prepare["artifact_path"]))
    compile_only = _run_child(args, "compile", artifact_path, split_cache_root)
    payload = {
        "same_process": same,
        "split_process": {
            "prepare": prepare,
            "compile": compile_only,
        },
        "comparison": {
            "same_compile_start_current_rss_kb": same.get(
                "compile_start_current_rss_kb"
            ),
            "split_compile_start_current_rss_kb": compile_only.get(
                "compile_start_current_rss_kb"
            ),
            "compile_start_current_rss_drop_kb": (
                None
                if same.get("compile_start_current_rss_kb") is None
                or compile_only.get("compile_start_current_rss_kb") is None
                else int(same["compile_start_current_rss_kb"])
                - int(compile_only["compile_start_current_rss_kb"])
            ),
            "same_qret_subprocess_peak_rss_kb": same.get(
                "qret_subprocess_peak_rss_kb"
            ),
            "split_qret_subprocess_peak_rss_kb": compile_only.get(
                "qret_subprocess_peak_rss_kb"
            ),
            "same_semantics_equal_split_prepare": same.get("semantics")
            == prepare.get("semantics"),
            "same_semantic_core_equal_split_prepare": _semantic_core(
                dict(same.get("semantics") or {})
            )
            == _semantic_core(dict(prepare.get("semantics") or {})),
        },
    }
    if args.output is not None:
        _write_json(args.output, payload)
    print(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
