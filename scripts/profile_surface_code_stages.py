#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from trotterlib import surface_code as sc  # noqa: E402
from trotterlib.profiling import (  # noqa: E402
    flatten_stage_metrics,
    largest_python_current_rss_delta_stage,
    peak_python_rss_stage,
    peak_subprocess_rss_stage,
    slowest_stage,
    write_csv,
    write_jsonl,
)


def _git_output(args: list[str]) -> str:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _commit_sha() -> str:
    return _git_output(["rev-parse", "HEAD"])


def _dirty_status() -> str:
    return _git_output(["status", "--short"])


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root is not an object: {path}")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{time.time_ns()}.tmp")
    try:
        tmp_path.write_text(
            json.dumps(dict(payload), ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        tmp_path.replace(path)
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass


def _parse_case(raw: str) -> tuple[int, str]:
    if ":" not in raw:
        raise ValueError(f"case must be Hn:pf_label, got {raw!r}")
    molecule, pf_label = raw.split(":", 1)
    molecule = molecule.strip()
    if not molecule.startswith("H"):
        raise ValueError(f"case molecule must be Hn, got {molecule!r}")
    return int(molecule[1:]), pf_label.strip()


def _copy_if_exists(source: Path, destination: Path) -> bool:
    if not source.exists():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return True


def _selected_stage_metrics_path(root: Path, primary: str, cache_hit: str) -> Path:
    cache_hit_path = root / cache_hit
    if cache_hit_path.exists():
        return cache_hit_path
    return root / primary


def _environment_payload() -> dict[str, Any]:
    return {
        "commit_sha": _commit_sha(),
        "dirty_status": _dirty_status(),
        "python": sys.version,
        "platform": platform.platform(),
        "executable": sys.executable,
        "qret_path": str(Path(sc.SURFACE_CODE_QCSF_PATH).expanduser().resolve()),
        "qret_hash": sc.file_sha256(sc.SURFACE_CODE_QCSF_PATH)
        if Path(sc.SURFACE_CODE_QCSF_PATH).exists()
        else None,
        "topology_path": str(Path(sc.SURFACE_CODE_TOPOLOGY_PATH).expanduser().resolve()),
        "rz_helper_batch_size": sc._rz_helper_batch_size(),
        "surface_code_cache_dir": str(sc.SURFACE_CODE_CACHE_DIR),
        "integral_cache_enabled": bool(sc.SURFACE_CODE_INTEGRAL_CACHE_ENABLED),
        "rss_sampling_enabled": os.environ.get(
            "SURFACE_CODE_PROFILE_RSS_SAMPLING"
        ),
        "rss_sampling_interval_sec": os.environ.get(
            "SURFACE_CODE_PROFILE_RSS_SAMPLING_INTERVAL_SEC"
        ),
        "circuit_release_experiment": os.environ.get(
            "SURFACE_CODE_PROFILE_CIRCUIT_RELEASE_EXPERIMENT"
        ),
        "compile_info_extraction_mode": os.environ.get(
            "SURFACE_CODE_COMPILE_INFO_EXTRACTION_MODE"
        ),
    }


def _artifact_semantics(artifact: sc.SurfaceCodeStepArtifact) -> dict[str, Any]:
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


def _format_stage(row: Mapping[str, Any] | None) -> str:
    if not row:
        return "N/A"
    name = row.get("stage_name")
    elapsed = row.get("elapsed_seconds")
    py_rss = row.get("python_self_maxrss_kb")
    current_after = row.get("python_current_rss_after_kb")
    sampled_peak = row.get("python_sampled_peak_rss_kb")
    sub_rss = row.get("subprocess_maxrss_kb")
    pieces = [str(name)]
    if elapsed is not None:
        pieces.append(f"elapsed={float(elapsed):.3f}s")
    if py_rss is not None:
        pieces.append(f"python_rss={int(py_rss)}KB")
    if current_after is not None:
        pieces.append(f"current_rss={int(current_after)}KB")
    if sampled_peak is not None:
        pieces.append(f"sampled_peak={int(sampled_peak)}KB")
    if sub_rss is not None:
        pieces.append(f"subprocess_rss={int(sub_rss)}KB")
    return ", ".join(pieces)


def _write_report(
    path: Path,
    *,
    environment: Mapping[str, Any],
    rows: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
) -> None:
    slowest = slowest_stage(rows)
    peak_py = peak_python_rss_stage(rows)
    largest_current_delta = largest_python_current_rss_delta_stage(rows)
    peak_sub = peak_subprocess_rss_stage(rows)
    lines = [
        "# Surface-Code Stage Profiling Report",
        "",
        "## Purpose",
        "",
        "Identify which prepare and compile stages dominate wall time and peak RSS "
        "without adding a new optimization based on guesswork.",
        "",
        "## Target Commit",
        "",
        f"- Commit: `{environment.get('commit_sha')}`",
        f"- Dirty status: `{environment.get('dirty_status') or 'clean'}`",
        "",
        "## Environment",
        "",
        f"- Python: `{str(environment.get('python', '')).splitlines()[0]}`",
        f"- Platform: `{environment.get('platform')}`",
        f"- qret: `{environment.get('qret_path')}`",
        f"- qret hash: `{environment.get('qret_hash')}`",
        f"- Topology: `{environment.get('topology_path')}`",
        f"- RZ helper batch size: `{environment.get('rz_helper_batch_size')}`",
        "",
        "## Method",
        "",
        "- Prepare metrics are read from `prepare_stage_metrics.json` or "
        "`prepare_stage_cache_hit_metrics.json`.",
        "- Compile metrics are read from `compile_stage_metrics.json` or "
        "`compile_stage_cache_hit_metrics.json`.",
        "- Python RSS uses `resource.getrusage(...).ru_maxrss` and is stored in KB.",
        "- qret subprocess RSS uses `/usr/bin/time -v` when available and is stored in KB.",
        "- Parent Python current RSS is read from `/proc/self/status` `VmRSS` when available.",
        "- Parent Python sampled peak RSS is enabled by this benchmark script and "
        "uses a low-frequency sampling thread.",
        "- `SURFACE_CODE_PROFILE_CIRCUIT_RELEASE_EXPERIMENT=del` or "
        "`del_plus_gc` adds profiling-only object release stages after OpenQASM "
        "text generation and after writing QASM.",
        "- `SURFACE_CODE_COMPILE_INFO_EXTRACTION_MODE=top_level_metric_fields` "
        "uses the experimental minimal `compile_info.json` metric-field extractor; "
        "the default is full `json.load()`.",
        "- Mapping, routing, and QEC elapsed are not split unless qret exposes them; "
        "otherwise they are included in `qret_compile`.",
        "",
        "## Result Summary",
        "",
        "| case | cache | compile mode | prepare elapsed | compile elapsed | stream hash |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for summary in summaries:
        semantics = summary.get("semantics", {})
        lines.append(
            "| {case} | {cache} | {mode} | {prepare:.3f}s | {compile:.3f}s | `{stream}` |".format(
                case=summary.get("case_name"),
                cache=summary.get("cache_condition"),
                mode=summary.get("compile_mode"),
                prepare=float(summary.get("prepare_elapsed_seconds") or 0.0),
                compile=float(summary.get("compile_elapsed_seconds") or 0.0),
                stream=semantics.get("normalized_instruction_stream_hash"),
            )
        )
    lines.extend(
        [
            "",
            "## Baseline Reference",
            "",
            "These values are prior H4 observations and are not directly comparable "
            "to the measurements above unless rerun under the same commit, cache "
            "state, and environment.",
            "",
            "| item | value |",
            "| --- | --- |",
            "| legacy RZ helper full-IR prepare | H4 about 98.4s |",
            "| current cold prepare | H4 about 24.9s |",
            "| current hot prepare | H4 about 12.2s |",
            "| legacy RZ helper opt | about 88.8s, 186 qret launches |",
            "| batched RZ helper opt | about 12.7s, 6 qret launches |",
            "| legacy full-IR peak RSS | about 335 MiB |",
            "| current cold peak RSS | about 333 MiB |",
            "| current hot peak RSS | about 327 MiB |",
            "",
            "## Observed Facts",
            "",
            f"- Slowest recorded stage: {_format_stage(slowest)}.",
            f"- Highest Python parent RSS stage: {_format_stage(peak_py)}.",
            f"- Largest Python current RSS delta stage: {_format_stage(largest_current_delta)}.",
            f"- Highest qret subprocess RSS stage: {_format_stage(peak_sub)}.",
            "",
            "## Interpretation",
            "",
            "- Treat the rows above as observations for the listed commit and cache state only.",
            "- If `subprocess_maxrss_kb` is missing, `/usr/bin/time -v` was unavailable "
            "or the stage did not launch qret.",
            "- If `qret_compile` dominates elapsed or subprocess RSS, the next boundary is "
            "inside qret rather than the Evaluation Python wrapper.",
            "- For small H2 profiles, do not extrapolate RSS or routing behavior to H4 "
            "without rerunning H4 under the same conditions.",
            "- A flat Python parent high-water mark does not by itself prove that "
            "`step_ir.json` full-load is or is not the dominant H4 RSS source.",
            "- Current RSS deltas are better evidence for retained memory than "
            "`ru_maxrss`, which is a process lifetime high-water mark.",
            "",
            "## Judgment Items",
            "",
            "| question | current answer |",
            "| --- | --- |",
            "| prepare stage creating peak RSS | Unconfirmed for H4 unless an H4 run is present in this report. |",
            "| qret subprocess vs Python parent | Compare `Highest Python parent RSS stage` and `Highest qret subprocess RSS stage`; note that they use separate semantics. |",
            "| value of optimizing `step_ir.json` full-load | Only justified if Python parent RSS rises in IR load/inline stages for H4. |",
            "| main cleanup or qret parse dominance | Use the stage rows; do not infer dominance when elapsed is unavailable. |",
            "| streaming inliner impact | Requires comparison against legacy inliner metrics; semantic hashes here only verify stability. |",
            "| mapping/routing major constraint size | Unconfirmed unless qret exposes finer elapsed or larger cases are run. |",
            "| Evaluation vs Quration boundary | Evaluation records wrapper stages; finer mapping/routing/QEC attribution requires qret-side instrumentation. |",
            "",
            "## Open Items",
            "",
            "- Full H4/H5/H6 cold and hot matrices should be run only when runtime budget allows.",
            "- qret does not currently expose mapping/routing/QEC elapsed at separate stage granularity.",
            "",
            "## Next Optimization Candidates",
            "",
            "- Optimize the stage that dominates in this report, after confirming it also dominates H4.",
            "- Consider `step_ir.json` input-side parsing only if Python parent RSS rises during "
            "IR load/inline stages rather than qret subprocess stages.",
            "",
            "## Optimizations Not Yet Justified",
            "",
            "- Do not rewrite routing or qret internals based only on Python-side RSS.",
            "- Do not add compact binary IR until JSON file size or parse RSS is confirmed dominant.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def run_case(
    *,
    chain_length: int,
    pf_label: str,
    compile_mode: str,
    output_root: Path,
    cache_condition: str,
    reuse_compile_cache: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    molecule = f"H{chain_length}"
    case_name = f"{molecule}_{pf_label}_{compile_mode}_{cache_condition}".replace("/", "_")
    run_dir = output_root / f"{time.strftime('%Y%m%d_%H%M%S')}_{case_name}"
    run_dir.mkdir(parents=True, exist_ok=True)

    architecture = sc.SurfaceCodeArchitecture(compile_mode=compile_mode)
    artifact = sc.prepare_grouped_surface_code_step_artifact(
        sc.grouped_hchain_ham_name(chain_length),
        pf_label,
        architecture=architecture,
    )
    metrics = sc.compile_prepared_surface_code_step_artifact(
        artifact,
        architecture,
        reuse_cache=reuse_compile_cache,
    )

    prepare_metrics_source = _selected_stage_metrics_path(
        artifact.runtime_root,
        sc._PREPARE_STAGE_METRICS_FILENAME,
        sc._PREPARE_STAGE_CACHE_HIT_METRICS_FILENAME,
    )
    compile_root = sc._compile_runtime_root(artifact, architecture)
    compile_metrics_source = _selected_stage_metrics_path(
        compile_root,
        sc._COMPILE_STAGE_METRICS_FILENAME,
        sc._COMPILE_STAGE_CACHE_HIT_METRICS_FILENAME,
    )
    prepare_metrics_path = run_dir / "prepare_stage_metrics.json"
    compile_metrics_path = run_dir / "compile_stage_metrics.json"
    _copy_if_exists(prepare_metrics_source, prepare_metrics_path)
    _copy_if_exists(compile_metrics_source, compile_metrics_path)

    environment = _environment_payload()
    _write_json(run_dir / "environment.json", environment)

    prepare_metrics = _load_json(prepare_metrics_path)
    compile_metrics = _load_json(compile_metrics_path)
    rows = flatten_stage_metrics(
        prepare_metrics,
        commit_sha=str(environment["commit_sha"]),
        case_name=case_name,
        phase="prepare",
        cache_condition=cache_condition,
        hchain_size=chain_length,
    )
    rows.extend(
        flatten_stage_metrics(
            compile_metrics,
            commit_sha=str(environment["commit_sha"]),
            case_name=case_name,
            phase="compile",
            cache_condition=cache_condition,
            hchain_size=chain_length,
        )
    )
    summary = {
        "case_name": case_name,
        "molecule": molecule,
        "pf_label": pf_label,
        "cache_condition": cache_condition,
        "compile_mode": compile_mode,
        "prepare_elapsed_seconds": prepare_metrics.get("elapsed_seconds"),
        "compile_elapsed_seconds": compile_metrics.get("elapsed_seconds"),
        "compile_cache_hit": metrics.get("compile_cache_hit"),
        "prepare_metrics": str(prepare_metrics_path),
        "compile_metrics": str(compile_metrics_path),
        "semantics": _artifact_semantics(artifact),
    }
    _write_json(run_dir / "result_summary.json", summary)
    write_jsonl(run_dir / "stage_metrics.jsonl", rows)
    write_csv(run_dir / "stage_metrics.csv", rows)
    return rows, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="Benchmark case as Hn:pf_label. Can be repeated. Default: H2:2nd.",
    )
    parser.add_argument(
        "--compile-mode",
        action="append",
        default=[],
        help="Compile mode. Can be repeated. Default: ftqc_compile_topology.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "benchmark_results" / "profiling",
    )
    parser.add_argument("--cache-condition", default="current-cache-state")
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=None,
        help="Override SURFACE_CODE_CACHE_DIR for isolated profiling caches.",
    )
    parser.add_argument(
        "--reset-cache-root",
        action="store_true",
        help="Delete --cache-root before running. Only allowed under benchmark_results/.",
    )
    parser.add_argument(
        "--no-reuse-compile-cache",
        action="store_true",
        help="Force qret compile even when compile_info.json already exists.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Override SURFACE_CODE_RZ_HELPER_BATCH_SIZE for this process.",
    )
    parser.add_argument(
        "--rss-sampling-interval",
        type=float,
        default=0.02,
        help="Current RSS sampling interval in seconds. Default: 0.02.",
    )
    parser.add_argument(
        "--no-rss-sampling",
        action="store_true",
        help="Disable stage-level current RSS sampling.",
    )
    parser.add_argument(
        "--circuit-release-experiment",
        nargs="?",
        const="del_plus_gc",
        choices=("del", "del_plus_gc"),
        help=(
            "Add profiling-only stages that delete qc/qc_basis and qasm_text. "
            "Use 'del' or 'del_plus_gc'. With no value, uses del_plus_gc."
        ),
    )
    parser.add_argument(
        "--compile-info-extraction-mode",
        choices=("full_json_load", "top_level_metric_fields"),
        default="full_json_load",
        help=(
            "compile_info.json read mode. Default keeps the production baseline "
            "full json.load() behavior."
        ),
    )
    parser.add_argument(
        "--write-report",
        type=Path,
        default=REPO_ROOT / "docs" / "benchmarks" / "profiling_report.md",
    )
    args = parser.parse_args()

    if args.batch_size is not None:
        sc.SURFACE_CODE_RZ_HELPER_BATCH_SIZE = int(args.batch_size)
    if args.cache_root is not None:
        cache_root = args.cache_root.expanduser().resolve()
        benchmark_root = (REPO_ROOT / "benchmark_results").resolve()
        if args.reset_cache_root:
            try:
                cache_root.relative_to(benchmark_root)
            except ValueError as exc:
                raise SystemExit(
                    "--reset-cache-root is only allowed under benchmark_results/"
                ) from exc
            shutil.rmtree(cache_root, ignore_errors=True)
        cache_root.mkdir(parents=True, exist_ok=True)
        sc.SURFACE_CODE_CACHE_DIR = cache_root
    if args.no_rss_sampling:
        os.environ.pop("SURFACE_CODE_PROFILE_RSS_SAMPLING", None)
    else:
        os.environ["SURFACE_CODE_PROFILE_RSS_SAMPLING"] = "1"
        os.environ["SURFACE_CODE_PROFILE_RSS_SAMPLING_INTERVAL_SEC"] = str(
            float(args.rss_sampling_interval)
        )
    if args.circuit_release_experiment:
        os.environ["SURFACE_CODE_PROFILE_CIRCUIT_RELEASE_EXPERIMENT"] = str(
            args.circuit_release_experiment
        )
    os.environ["SURFACE_CODE_COMPILE_INFO_EXTRACTION_MODE"] = str(
        args.compile_info_extraction_mode
    )

    cases = [_parse_case(item) for item in (args.case or ["H2:2nd"])]
    compile_modes = args.compile_mode or ["ftqc_compile_topology"]
    rows: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for chain_length, pf_label in cases:
        for compile_mode in compile_modes:
            case_rows, summary = run_case(
                chain_length=chain_length,
                pf_label=pf_label,
                compile_mode=compile_mode,
                output_root=args.output_root,
                cache_condition=str(args.cache_condition),
                reuse_compile_cache=not args.no_reuse_compile_cache,
            )
            rows.extend(case_rows)
            summaries.append(summary)

    aggregate_root = args.output_root
    aggregate_root.mkdir(parents=True, exist_ok=True)
    write_jsonl(aggregate_root / "stage_metrics.jsonl", rows)
    write_csv(aggregate_root / "stage_metrics.csv", rows)
    _write_json(
        aggregate_root / "result_summary.json",
        {
            "environment": _environment_payload(),
            "cases": summaries,
            "slowest_stage": dict(slowest_stage(rows) or {}),
            "peak_python_rss_stage": dict(peak_python_rss_stage(rows) or {}),
            "largest_python_current_rss_delta_stage": dict(
                largest_python_current_rss_delta_stage(rows) or {}
            ),
            "peak_subprocess_rss_stage": dict(peak_subprocess_rss_stage(rows) or {}),
        },
    )
    _write_report(args.write_report, environment=_environment_payload(), rows=rows, summaries=summaries)
    print(f"rows: {len(rows)}")
    print(f"jsonl: {aggregate_root / 'stage_metrics.jsonl'}")
    print(f"csv: {aggregate_root / 'stage_metrics.csv'}")
    print(f"report: {args.write_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
