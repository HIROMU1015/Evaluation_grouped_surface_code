#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QRET_PATH = REPO_ROOT / "build" / "quration" / "qret"
DEFAULT_TOPOLOGY_PATH = (
    REPO_ROOT
    / "third_party"
    / "quration"
    / "quration-core"
    / "examples"
    / "data"
    / "topology"
    / "tutorial.yaml"
)
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "qret_pre_routing_memory"
GNU_TIME_MAXRSS_RE = re.compile(r"Maximum resident set size \(kbytes\):\s*(\d+)")
PROC_SAMPLE_FIELDS = (
    "timestamp_seconds",
    "pid",
    "vmrss_kb",
    "vmhwm_kb",
    "vmsize_kb",
    "rss_anon_kb",
    "rss_file_kb",
    "rss_shmem_kb",
    "smaps_rollup_rss_kb",
    "pss_kb",
    "private_dirty_kb",
)

TOPOLOGY_PASSES = {
    "init_only": ["sc_ls_fixed_v0::init_compile_info"],
    "mapping_only": [
        "sc_ls_fixed_v0::init_compile_info",
        "sc_ls_fixed_v0::mapping",
    ],
    "routing_only": [
        "sc_ls_fixed_v0::init_compile_info",
        "sc_ls_fixed_v0::mapping",
        "sc_ls_fixed_v0::routing",
    ],
    "full_topology": [
        "sc_ls_fixed_v0::init_compile_info",
        "sc_ls_fixed_v0::mapping",
        "sc_ls_fixed_v0::routing",
        "sc_ls_fixed_v0::calc_info_without_topology",
        "sc_ls_fixed_v0::calc_info_with_topology",
        "sc_ls_fixed_v0::dump_compile_info",
    ],
}

DEFAULT_CASE_ARTIFACTS = {
    "h4_2nd": (
        REPO_ROOT
        / "artifacts"
        / "surface_code_cache"
        / "gr"
        / "prepared_step"
        / "H4_sto-3g_singlet_distance_100_charge_0_grouping__2nd"
        / "219de8464f2c6658"
        / "step_artifact.json"
    ),
    "h4_4th_new2": (
        REPO_ROOT
        / "artifacts"
        / "surface_code_cache"
        / "gr"
        / "prepared_step"
        / "H4_sto-3g_singlet_distance_100_charge_0_grouping__4th_new_2_"
        / "2eb5acb2b3f04ba2"
        / "step_artifact.json"
    ),
}

PROFILE_STAGES = [
    "compile_backend_after_load_topology",
    "load_ir_after_json_parse_json_alive",
    "load_ir_after_load_json_json_alive",
    "after_load_function_json_destroyed",
    "after_set_ir",
    "after_recursive_inliner",
    "after_static_condition_pruning",
    "after_decompose_inst",
    "after_ignore_global_phase",
    "after_lowering",
    "before_pass_manager_run",
    "mapping_entry",
    "mapping_after_qubit_graph",
    "mapping_after_map_qubits",
    "routing_entry",
    "routing_after_validate",
    "routing_after_inst_queue_construct",
    "routing_after_simulator_construct",
    "routing_after_initial_queue_peek",
    "routing_before_main_loop",
    "routing_after_main_loop",
    "after_pass_manager_run",
    "pipeline_state_output_skipped",
    "before_build_pipeline_state",
    "build_pipeline_state_entry",
    "build_pipeline_state_after_target",
    "build_pipeline_state_after_pass_history",
    "build_pipeline_state_after_compile_info",
    "build_program_json_before",
    "build_program_json_after",
    "build_pipeline_state_after_program",
    "after_build_pipeline_state",
    "save_pipeline_state_entry",
    "save_pipeline_state_after_to_json",
    "save_pipeline_state_after_stream_write",
    "after_save_pipeline_state",
    "run_compilation_end",
]


@dataclass(frozen=True)
class CaseArtifact:
    name: str
    artifact_path: Path
    optimized_ir_path: Path
    optimized_ir_hash: str
    metadata: dict[str, Any]


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


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{time.time_ns()}.tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(dict(row), ensure_ascii=True, sort_keys=True))
                f.write("\n")
        tmp_path.replace(path)
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_case_artifact(case_name: str) -> Path:
    exact = DEFAULT_CASE_ARTIFACTS[case_name]
    if exact.exists():
        return exact

    if case_name == "h4_2nd":
        pattern = (
            "H4_sto-3g_singlet_distance_100_charge_0_grouping__2nd"
            "/*/step_artifact.json"
        )
    elif case_name == "h4_4th_new2":
        pattern = (
            "H4_sto-3g_singlet_distance_100_charge_0_grouping__4th_new_2_"
            "/*/step_artifact.json"
        )
    else:
        raise KeyError(case_name)

    root = REPO_ROOT / "artifacts" / "surface_code_cache" / "gr" / "prepared_step"
    candidates = sorted(root.glob(pattern))
    if not candidates:
        raise FileNotFoundError(f"prepared H4 artifact not found for case {case_name!r}")

    def instruction_count(path: Path) -> int:
        return int(_load_json(path).get("instruction_count", sys.maxsize))

    return min(candidates, key=instruction_count)


def _load_case_artifact(case_name: str) -> CaseArtifact:
    artifact_path = _find_case_artifact(case_name)
    metadata = _load_json(artifact_path)
    opt_path = Path(str(metadata["optimized_ir_path"])).expanduser().resolve()
    if not opt_path.exists():
        raise FileNotFoundError(f"optimized IR not found: {opt_path}")
    opt_hash = str(metadata["optimized_ir_hash"])
    actual_hash = _file_sha256(opt_path)
    if actual_hash != opt_hash:
        raise ValueError(
            f"optimized IR hash mismatch for {opt_path}: {actual_hash} != {opt_hash}"
        )
    return CaseArtifact(
        name=case_name,
        artifact_path=artifact_path,
        optimized_ir_path=opt_path,
        optimized_ir_hash=opt_hash,
        metadata=metadata,
    )


def _build_pipeline_yaml(
    *,
    opt_path: Path,
    output_path: Path,
    compile_info_path: Path,
    topology_path: Path,
    passes: list[str],
    skip_pipeline_state_output: bool = False,
) -> str:
    lines = [
        "source: IR",
        f"input: {opt_path}",
        "function: main",
        "target: SC_LS_FIXED_V0",
        f"output: {output_path}",
        f"sc_ls_fixed_v0_topology: {topology_path}",
        "sc_ls_fixed_v0_machine_type: Dim2",
        "sc_ls_fixed_v0_magic_generation_period: 15",
        "sc_ls_fixed_v0_maximum_magic_state_stock: 10000",
        "sc_ls_fixed_v0_entanglement_generation_period: 100",
        "sc_ls_fixed_v0_maximum_entangled_state_stock: 10",
        "sc_ls_fixed_v0_reaction_time: 1",
    ]
    if skip_pipeline_state_output:
        lines.append("sc_ls_fixed_v0_skip_pipeline_state_output: true")
    lines.extend(
        [
            f"sc_ls_fixed_v0_dump_compile_info_to_json: {compile_info_path}",
            "sc_ls_fixed_v0_pass:",
            *[f"  - {name}" for name in passes],
            "",
        ]
    )
    return "\n".join(lines)


def _parse_status_file(path: Path) -> dict[str, int]:
    ret: dict[str, int] = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ret
    key_map = {
        "VmRSS:": "vmrss_kb",
        "VmHWM:": "vmhwm_kb",
        "VmSize:": "vmsize_kb",
        "RssAnon:": "rss_anon_kb",
        "RssFile:": "rss_file_kb",
        "RssShmem:": "rss_shmem_kb",
    }
    for line in lines:
        for proc_key, out_key in key_map.items():
            if line.startswith(proc_key):
                parts = line.split()
                if len(parts) >= 2:
                    ret[out_key] = int(parts[1])
    return ret


def _parse_smaps_rollup(path: Path) -> dict[str, int]:
    ret: dict[str, int] = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ret
    key_map = {
        "Rss:": "smaps_rollup_rss_kb",
        "Pss:": "pss_kb",
        "Private_Dirty:": "private_dirty_kb",
    }
    for line in lines:
        for proc_key, out_key in key_map.items():
            if line.startswith(proc_key):
                parts = line.split()
                if len(parts) >= 2:
                    ret[out_key] = int(parts[1])
    if "smaps_rollup_rss_kb" in ret:
        ret["smaps_rss_kb"] = ret["smaps_rollup_rss_kb"]
    if "pss_kb" in ret:
        ret["smaps_pss_kb"] = ret["pss_kb"]
    if "private_dirty_kb" in ret:
        ret["smaps_private_dirty_kb"] = ret["private_dirty_kb"]
    return ret


def _children(pid: int) -> list[int]:
    path = Path("/proc") / str(pid) / "task" / str(pid) / "children"
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return []
    if not raw:
        return []
    return [int(value) for value in raw.split()]


def _process_tree(root_pid: int) -> list[int]:
    seen: set[int] = set()
    pending = [root_pid]
    while pending:
        pid = pending.pop()
        if pid in seen:
            continue
        seen.add(pid)
        pending.extend(_children(pid))
    return sorted(seen)


def _sample_process_tree(
    root_pid: int,
    *,
    interval_sec: float,
    stop_event: threading.Event,
    rows: list[dict[str, Any]],
) -> None:
    sample_index = 0
    while not stop_event.is_set():
        timestamp = time.time()
        pids = _process_tree(root_pid)
        tree_vmrss_kb = 0
        per_pid: list[dict[str, Any]] = []
        for pid in pids:
            proc_root = Path("/proc") / str(pid)
            status = _parse_status_file(proc_root / "status")
            if not status:
                continue
            smaps = _parse_smaps_rollup(proc_root / "smaps_rollup")
            row = {field: None for field in PROC_SAMPLE_FIELDS}
            row.update(
                {
                    "sample_index": sample_index,
                    "timestamp": timestamp,
                    "timestamp_seconds": timestamp,
                    "pid": pid,
                    **status,
                    **smaps,
                }
            )
            per_pid.append(row)
            tree_vmrss_kb += int(status.get("vmrss_kb", 0))
        for row in per_pid:
            row["tree_vmrss_kb"] = tree_vmrss_kb
            rows.append(row)
        sample_index += 1
        stop_event.wait(interval_sec)


def _parse_gnu_time_maxrss(stderr_text: str) -> int | None:
    matches = list(GNU_TIME_MAXRSS_RE.finditer(stderr_text))
    if not matches:
        return None
    return int(matches[-1].group(1))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _summarize_qret_profile(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_stage: dict[str, dict[str, Any]] = {}
    for row in rows:
        stage = str(row.get("stage", ""))
        if stage:
            by_stage[stage] = row

    max_row = max(rows, key=lambda row: int(row.get("vmrss_kb", -1)), default={})
    stage_rss = {
        stage: int(by_stage[stage]["vmrss_kb"])
        for stage in PROFILE_STAGES
        if stage in by_stage and by_stage[stage].get("vmrss_kb") is not None
    }
    first_jump = None
    prev = None
    for row in rows:
        current = row.get("vmrss_kb")
        if current is None:
            continue
        current = int(current)
        if prev is not None and current - prev >= 100_000:
            first_jump = {
                "stage": row.get("stage"),
                "delta_kb": current - prev,
                "from_kb": prev,
                "to_kb": current,
            }
            break
        prev = current

    json_alive = stage_rss.get("load_ir_after_load_json_json_alive")
    json_destroyed = stage_rss.get("after_load_function_json_destroyed")
    routing_entry = stage_rss.get("routing_entry")
    routing_before_loop = stage_rss.get("routing_before_main_loop")
    return {
        "profile_mark_count": len(rows),
        "max_profile_stage": max_row.get("stage"),
        "max_profile_vmrss_kb": max_row.get("vmrss_kb"),
        "stage_vmrss_kb": stage_rss,
        "json_destroy_current_delta_kb": None
        if json_alive is None or json_destroyed is None
        else json_destroyed - json_alive,
        "routing_entry_vmrss_kb": routing_entry,
        "routing_before_main_loop_vmrss_kb": routing_before_loop,
        "first_100mb_jump": first_jump,
    }


def _summarize_samples(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    peak_pid = max(rows, key=lambda row: int(row.get("vmrss_kb", -1)))
    peak_tree = max(rows, key=lambda row: int(row.get("tree_vmrss_kb", -1)))
    return {
        "sample_count": len(rows),
        "sampled_peak_pid": peak_pid.get("pid"),
        "sampled_peak_pid_vmrss_kb": peak_pid.get("vmrss_kb"),
        "sampled_peak_tree_vmrss_kb": peak_tree.get("tree_vmrss_kb"),
    }


def _run_variant(
    *,
    case: CaseArtifact,
    variant: str,
    passes: list[str],
    qret_path: Path,
    topology_path: Path,
    output_root: Path,
    sample_interval_sec: float,
) -> dict[str, Any]:
    run_root = output_root / case.name / variant
    run_root.mkdir(parents=True, exist_ok=True)
    profile_jsonl = run_root / "qret_rss_profile.jsonl"
    samples_jsonl = run_root / "process_samples.jsonl"
    pipeline_path = run_root / "compile.yaml"
    compile_info_path = run_root / "compile_info.json"
    stdout_path = run_root / "stdout.txt"
    stderr_path = run_root / "stderr.txt"
    output_path = Path(os.devnull)
    for path in (profile_jsonl, samples_jsonl, compile_info_path, stdout_path, stderr_path):
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    pipeline_path.write_text(
        _build_pipeline_yaml(
            opt_path=case.optimized_ir_path,
            output_path=output_path,
            compile_info_path=compile_info_path,
            topology_path=topology_path,
            passes=passes,
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["QRET_RSS_PROFILE_JSONL"] = str(profile_jsonl)
    cmd = [
        "/usr/bin/time",
        "-v",
        str(qret_path),
        "compile",
        "--pipeline",
        str(pipeline_path),
        "--verbose",
    ]
    start = time.perf_counter()
    process = subprocess.Popen(
        cmd,
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    samples: list[dict[str, Any]] = []
    stop_event = threading.Event()
    sampler = threading.Thread(
        target=_sample_process_tree,
        kwargs={
            "root_pid": process.pid,
            "interval_sec": sample_interval_sec,
            "stop_event": stop_event,
            "rows": samples,
        },
        daemon=True,
    )
    sampler.start()
    stdout, stderr = process.communicate()
    stop_event.set()
    sampler.join(timeout=2.0)
    elapsed = time.perf_counter() - start
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    _write_jsonl(samples_jsonl, samples)

    profile_rows = _load_jsonl(profile_jsonl)
    profile_summary = _summarize_qret_profile(profile_rows)
    sample_summary = _summarize_samples(samples)
    gnu_time_maxrss = _parse_gnu_time_maxrss(stderr)
    result = {
        "case": case.name,
        "variant": variant,
        "returncode": process.returncode,
        "elapsed_seconds": elapsed,
        "gnu_time_maxrss_kb": gnu_time_maxrss,
        "pipeline_path": str(pipeline_path),
        "profile_jsonl": str(profile_jsonl),
        "samples_jsonl": str(samples_jsonl),
        "compile_info_path": str(compile_info_path)
        if compile_info_path.exists()
        else None,
        "input_path": str(case.optimized_ir_path),
        "input_size_bytes": case.optimized_ir_path.stat().st_size,
        "passes": list(passes),
        **profile_summary,
        **sample_summary,
    }
    maxrss = result.get("gnu_time_maxrss_kb")
    routing_entry = result.get("routing_entry_vmrss_kb")
    routing_before_loop = result.get("routing_before_main_loop_vmrss_kb")
    if maxrss and routing_entry:
        result["routing_entry_fraction_of_gnu_time_maxrss"] = routing_entry / maxrss
    if maxrss and routing_before_loop:
        result["routing_before_loop_fraction_of_gnu_time_maxrss"] = routing_before_loop / maxrss
    _write_json(run_root / "summary.json", result)
    if process.returncode != 0:
        raise RuntimeError(
            f"qret failed for {case.name}/{variant} with code {process.returncode}; "
            f"see {stderr_path}"
        )
    return result


def _write_run_report(
    path: Path,
    *,
    results: list[dict[str, Any]],
    qret_path: Path,
    topology_path: Path,
    sample_interval_sec: float,
) -> None:
    lines = [
        "# qret Pre-Routing RSS Profile",
        "",
        f"- qret: `{qret_path}`",
        f"- topology: `{topology_path}`",
        f"- external sampler interval: `{sample_interval_sec:.3f}` sec",
        "",
        "| case | variant | elapsed s | GNU time max RSS KB | sampled tree peak KB | qret mark peak KB | routing entry KB | before loop KB |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in results:
        lines.append(
            "| {case} | {variant} | {elapsed:.3f} | {maxrss} | {sample_peak} | "
            "{mark_peak} | {routing_entry} | {before_loop} |".format(
                case=row["case"],
                variant=row["variant"],
                elapsed=float(row["elapsed_seconds"]),
                maxrss=row.get("gnu_time_maxrss_kb") or "",
                sample_peak=row.get("sampled_peak_tree_vmrss_kb") or "",
                mark_peak=row.get("max_profile_vmrss_kb") or "",
                routing_entry=row.get("routing_entry_vmrss_kb") or "",
                before_loop=row.get("routing_before_main_loop_vmrss_kb") or "",
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Profile qret RSS through IR load, mapping, and pre-routing boundaries."
    )
    parser.add_argument(
        "--case",
        action="append",
        choices=sorted(DEFAULT_CASE_ARTIFACTS),
        help="Case to run. May be repeated. Default: both H4 control and H4 4th(new_2).",
    )
    parser.add_argument(
        "--variant",
        action="append",
        choices=sorted(TOPOLOGY_PASSES),
        help="Pass prefix variant. May be repeated. Default: all variants.",
    )
    parser.add_argument("--qret-path", type=Path, default=DEFAULT_QRET_PATH)
    parser.add_argument("--topology-path", type=Path, default=DEFAULT_TOPOLOGY_PATH)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--sample-interval-sec",
        type=float,
        default=0.02,
        help="External /proc sampler interval; use 0.01-0.02 for the requested profile.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    qret_path = args.qret_path.expanduser().resolve()
    topology_path = args.topology_path.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    if not qret_path.exists():
        raise FileNotFoundError(f"qret not found: {qret_path}")
    if not topology_path.exists():
        raise FileNotFoundError(f"topology not found: {topology_path}")
    if not (0 < args.sample_interval_sec <= 1):
        raise ValueError("--sample-interval-sec must be in (0, 1]")

    cases = args.case or sorted(DEFAULT_CASE_ARTIFACTS)
    variants = args.variant or list(TOPOLOGY_PASSES)
    results: list[dict[str, Any]] = []
    for case_name in cases:
        case = _load_case_artifact(case_name)
        for variant in variants:
            result = _run_variant(
                case=case,
                variant=variant,
                passes=TOPOLOGY_PASSES[variant],
                qret_path=qret_path,
                topology_path=topology_path,
                output_root=output_root,
                sample_interval_sec=float(args.sample_interval_sec),
            )
            results.append(result)
            print(
                "{case}/{variant}: maxrss={maxrss}KB routing_entry={routing_entry}KB "
                "before_loop={before_loop}KB".format(
                    case=case_name,
                    variant=variant,
                    maxrss=result.get("gnu_time_maxrss_kb"),
                    routing_entry=result.get("routing_entry_vmrss_kb"),
                    before_loop=result.get("routing_before_main_loop_vmrss_kb"),
                ),
                flush=True,
            )

    _write_jsonl(output_root / "results.jsonl", results)
    _write_json(
        output_root / "environment.json",
        {
            "qret_path": str(qret_path),
            "qret_hash": _file_sha256(qret_path),
            "topology_path": str(topology_path),
            "sample_interval_sec": float(args.sample_interval_sec),
            "cases": cases,
            "variants": variants,
        },
    )
    _write_run_report(
        output_root / "qret_pre_routing_memory_profile.md",
        results=results,
        qret_path=qret_path,
        topology_path=topology_path,
        sample_interval_sec=float(args.sample_interval_sec),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
