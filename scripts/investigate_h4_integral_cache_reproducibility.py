#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from trotterlib import surface_code as sc


HAM_NAME = sc.grouped_hchain_ham_name(4)
PF_LABEL = "4th(new_2)"
GATE_DEF_RE = re.compile(
    r"^gate\s+(?P<name>\w+)\s+\w+\s+\{\s*rz\((?P<theta>.+)\)\s+\w+;\s*\}$"
)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sc._atomic_write_json(path, payload)


def extract_rewritten_qasm_rz_occurrences(qasm_path: Path) -> list[str]:
    lines = qasm_path.read_text(encoding="utf-8").splitlines()
    gate_to_theta: dict[str, str] = {}
    for line in lines:
        match = GATE_DEF_RE.match(line.strip())
        if match is not None:
            gate_to_theta[match.group("name")] = match.group("theta").strip()

    occurrences: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("gate "):
            continue
        parts = stripped.split(None, 1)
        if parts and parts[0] in gate_to_theta and stripped.endswith(";"):
            occurrences.append(gate_to_theta[parts[0]])
    return occurrences


def helper_input_hashes(
    ir_path: Path,
    helpers: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    ir_data = load_json(ir_path)
    out: list[dict[str, Any]] = []
    for index, helper in enumerate(helpers):
        function_name = str(helper["function_name"])
        helper_ir = sc._single_circuit_ir(ir_data, function_name)
        normalized_value = sc._helper_input_ir_cache_value(helper_ir)
        out.append(
            {
                "index": int(index),
                "theta": helper.get("theta"),
                "key": helper.get("key"),
                "function_name": function_name,
                "normalized_single_ir_hash": sc._canonical_json_hash(normalized_value),
            }
        )
    return out


def summarize_stage_metrics(stage_path: Path) -> dict[str, Any]:
    stage = load_json(stage_path)
    stages = list(stage.get("stages", []))
    prefix_elapsed: defaultdict[str, float] = defaultdict(float)
    prefix_count: defaultdict[str, int] = defaultdict(int)
    integral_events: list[dict[str, Any]] = []
    helper_lookup_hit = 0
    helper_lookup_miss = 0

    for item in stages:
        name = str(item.get("name", ""))
        result = item.get("result", {})
        elapsed = float(item.get("elapsed_seconds", 0.0))
        prefix = name
        if name.startswith("rz_helper_independent_cache_lookup_"):
            prefix = "rz_helper_independent_cache_lookup"
            status = result.get("cache_status")
            if status == "hit":
                helper_lookup_hit += 1
            elif status == "miss":
                helper_lookup_miss += 1
        elif name.startswith("rz_helper_independent_cache_lock_"):
            prefix = "rz_helper_independent_cache_lock"
        elif name.startswith("qret_opt_rz_helper_independent_"):
            prefix = "qret_opt_rz_helper_independent"
        elif name.startswith("qret_opt_rz_helper_"):
            prefix = "qret_opt_rz_helper"

        prefix_elapsed[prefix] += elapsed
        prefix_count[prefix] += 1
        if name.startswith("integral_"):
            integral_events.append(
                {
                    "name": name,
                    "elapsed_seconds": elapsed,
                    "result": dict(result),
                }
            )

    elapsed_by_prefix = [
        {
            "stage": key,
            "count": int(prefix_count[key]),
            "elapsed_seconds": round(value, 6),
        }
        for key, value in sorted(prefix_elapsed.items(), key=lambda kv: kv[1], reverse=True)
    ]
    integral_lookup = next(
        (
            item
            for item in integral_events
            if item.get("name") == "integral_cache_lookup"
        ),
        None,
    )
    return {
        "path": str(stage_path),
        "status": stage.get("status"),
        "elapsed_seconds": float(stage.get("elapsed_seconds", 0.0)),
        "rss": dict(stage.get("rss", {})),
        "stage_count": int(stage.get("stage_count", len(stages))),
        "elapsed_by_prefix": elapsed_by_prefix,
        "dominant_stage": elapsed_by_prefix[0] if elapsed_by_prefix else None,
        "integral_events": integral_events,
        "integral_cache_lookup": integral_lookup,
        "helper_cache_lookup_hit_count": int(helper_lookup_hit),
        "helper_cache_lookup_miss_count": int(helper_lookup_miss),
    }


def helper_cache_summary(artifact: sc.SurfaceCodeStepArtifact) -> dict[str, Any]:
    cached_opt = artifact.rz_call_cache.get("cached_opt", {})
    helper_cache = cached_opt.get("helper_cache", {}) if isinstance(cached_opt, Mapping) else {}
    hit = int(helper_cache.get("hit_count") or 0)
    miss = int(helper_cache.get("miss_count") or 0)
    total = hit + miss
    return {
        "hit_count": hit,
        "miss_count": miss,
        "legacy_full_ir_count": helper_cache.get("legacy_full_ir_count"),
        "hit_rate": (float(hit) / float(total)) if total else None,
    }


def patched_prepared_runtime_root(label: str):
    original = sc._step_artifact_runtime_root

    def runtime_root(
        ham_name: str,
        pf_label: sc.PFLabel,
        *,
        target_error: float,
        step_time: float,
        rotation_precision: float,
        qret_hash: str,
    ) -> Path:
        base = original(
            ham_name,
            pf_label,
            target_error=target_error,
            step_time=step_time,
            rotation_precision=rotation_precision,
            qret_hash=qret_hash,
        )
        prepared_root = sc.SURFACE_CODE_CACHE_DIR / "gr" / "prepared_step"
        try:
            rel = base.relative_to(prepared_root)
        except ValueError:
            rel = Path(base.name)
        return sc.SURFACE_CODE_CACHE_DIR / "gr" / "prepared_step_runs" / label / rel

    return original, runtime_root


def collect_run(
    *,
    label: str,
    cache_root: Path,
    integral_cache_enabled: bool,
    clean_cache_root: bool,
) -> dict[str, Any]:
    if clean_cache_root and cache_root.exists():
        shutil.rmtree(cache_root)
    cache_root.mkdir(parents=True, exist_ok=True)

    sc.SURFACE_CODE_CACHE_DIR = cache_root
    sc.SURFACE_CODE_INTEGRAL_CACHE_ENABLED = bool(integral_cache_enabled)
    sc.SURFACE_CODE_RZ_CALL_CACHE = True
    sc.SURFACE_CODE_RZ_HELPER_OPT_MODE = "independent_helper"

    original_runtime_root, runtime_root = patched_prepared_runtime_root(label)
    sc._step_artifact_runtime_root = runtime_root
    try:
        started = time.perf_counter()
        artifact = sc.prepare_grouped_surface_code_step_artifact(HAM_NAME, PF_LABEL)
        wall_elapsed = float(time.perf_counter() - started)
    finally:
        sc._step_artifact_runtime_root = original_runtime_root

    rz_metadata = load_json(artifact.runtime_root / "rz_call_cache_metadata.json")
    helpers = list(rz_metadata.get("helpers", []))
    helper_hashes = helper_input_hashes(artifact.ir_path, helpers)
    theta_occurrences = extract_rewritten_qasm_rz_occurrences(artifact.qasm_path)
    stream_summary = load_json(artifact.runtime_root / "step_instruction_stream_summary.json")
    stage_path = artifact.runtime_root / sc._PREPARE_STAGE_METRICS_FILENAME
    stage_metrics = summarize_stage_metrics(stage_path)
    integral_lookup = stage_metrics.get("integral_cache_lookup") or {}
    integral_lookup_result = integral_lookup.get("result", {})

    return {
        "label": label,
        "cache_root": str(cache_root),
        "runtime_root": str(artifact.runtime_root),
        "integral_cache_enabled": bool(integral_cache_enabled),
        "wall_elapsed_seconds": wall_elapsed,
        "metrics_elapsed_seconds": stage_metrics["elapsed_seconds"],
        "qasm_path": str(artifact.qasm_path),
        "ir_path": str(artifact.ir_path),
        "optimized_ir_path": str(artifact.optimized_ir_path),
        "step_qasm_sha256": sc.file_sha256(artifact.qasm_path),
        "step_ir_sha256": sc.file_sha256(artifact.ir_path),
        "optimized_ir_sha256": sc.file_sha256(artifact.optimized_ir_path),
        "rz_occurrence_thetas": theta_occurrences,
        "unique_theta_set": sorted(set(theta_occurrences)),
        "helpers": [
            {
                "index": int(index),
                "theta": helper.get("theta"),
                "key": helper.get("key"),
                "function_name": helper.get("function_name"),
                "count": helper.get("count"),
            }
            for index, helper in enumerate(helpers)
        ],
        "unique_helper_count": int(len(helpers)),
        "helper_input_hashes": helper_hashes,
        "helper_input_hash_set": sorted(
            {item["normalized_single_ir_hash"] for item in helper_hashes}
        ),
        "instruction_stream": {
            "normalized_instruction_stream_hash": stream_summary.get(
                "normalized_instruction_stream_hash"
            ),
            "opcode_count": stream_summary.get("opcode_count"),
            "emitted_instruction_count": stream_summary.get(
                "emitted_instruction_count"
            ),
            "scheduled_instruction_count": stream_summary.get(
                "scheduled_instruction_count"
            ),
            "instruction_count": artifact.instruction_count,
            "gate_depth": artifact.gate_depth,
            "magic_count": artifact.step_magic_state_count,
            "magic_depth": artifact.step_magic_state_depth,
            "peak_magic_layer": artifact.peak_magic_layer,
        },
        "integral_cache": {
            "lookup_status": integral_lookup_result.get("cache_status"),
            "invalid_reason": integral_lookup_result.get("invalid_reason"),
            "lookup_event": integral_lookup,
        },
        "helper_cache": helper_cache_summary(artifact),
        "stage_metrics": stage_metrics,
    }


def all_equal(values: list[Any]) -> bool:
    return all(value == values[0] for value in values[1:]) if values else True


def compare_integral_cache_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    stream_keys = [
        "normalized_instruction_stream_hash",
        "instruction_count",
        "gate_depth",
        "magic_count",
        "magic_depth",
        "peak_magic_layer",
    ]
    return {
        "step_qasm_hash_all_equal": all_equal(
            [run["step_qasm_sha256"] for run in runs]
        ),
        "step_ir_hash_all_equal": all_equal([run["step_ir_sha256"] for run in runs]),
        "rz_occurrence_theta_all_equal": all_equal(
            [run["rz_occurrence_thetas"] for run in runs]
        ),
        "unique_helper_set_all_equal": all_equal(
            [
                sorted((helper["theta"], helper["key"], helper["function_name"]) for helper in run["helpers"])
                for run in runs
            ]
        ),
        "helper_input_hash_set_all_equal": all_equal(
            [run["helper_input_hash_set"] for run in runs]
        ),
        "instruction_stream_all_equal": {
            key: all_equal([run["instruction_stream"][key] for run in runs])
            for key in stream_keys
        },
        "qasm_hashes": [run["step_qasm_sha256"] for run in runs],
        "step_ir_hashes": [run["step_ir_sha256"] for run in runs],
        "unique_helper_counts": [run["unique_helper_count"] for run in runs],
        "helper_input_hash_set_hashes": [
            sc._canonical_json_hash(run["helper_input_hash_set"]) for run in runs
        ],
        "rz_occurrence_hashes": [
            sc._canonical_json_hash(run["rz_occurrence_thetas"]) for run in runs
        ],
        "stream_hashes": [
            run["instruction_stream"]["normalized_instruction_stream_hash"]
            for run in runs
        ],
    }


def timing_table(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for run in runs:
        out.append(
            {
                "label": run["label"],
                "integral_cache_enabled": run["integral_cache_enabled"],
                "integral_cache_lookup_status": run["integral_cache"][
                    "lookup_status"
                ],
                "helper_cache_hit_rate": run["helper_cache"]["hit_rate"],
                "helper_cache_hit_count": run["helper_cache"]["hit_count"],
                "helper_cache_miss_count": run["helper_cache"]["miss_count"],
                "wall_elapsed_seconds": round(float(run["wall_elapsed_seconds"]), 6),
                "metrics_elapsed_seconds": round(
                    float(run["metrics_elapsed_seconds"]),
                    6,
                ),
                "dominant_stage": run["stage_metrics"]["dominant_stage"],
                "stage_elapsed_by_prefix": run["stage_metrics"]["elapsed_by_prefix"],
            }
        )
    return out


def run_investigation(output_path: Path, cache_base: Path) -> dict[str, Any]:
    if cache_base.exists():
        shutil.rmtree(cache_base)
    cache_base.mkdir(parents=True, exist_ok=True)

    no_integral = collect_run(
        label="no_integral_cache_no_helper_cache",
        cache_root=cache_base / "no_integral_cache_no_helper_cache",
        integral_cache_enabled=False,
        clean_cache_root=True,
    )
    write_json(output_path, {"status": "running", "runs": [no_integral]})

    shared_integral_root = cache_base / "integral_cache_enabled"
    integral_runs: list[dict[str, Any]] = []
    for index, label in enumerate(
        [
            "integral_cache_first",
            "integral_cache_second",
            "integral_cache_third",
        ],
        start=1,
    ):
        run = collect_run(
            label=label,
            cache_root=shared_integral_root,
            integral_cache_enabled=True,
            clean_cache_root=index == 1,
        )
        integral_runs.append(run)
        write_json(
            output_path,
            {
                "status": "running",
                "runs": [no_integral, *integral_runs],
            },
        )

    all_runs = [no_integral, *integral_runs]
    summary = {
        "status": "ok",
        "ham_name": HAM_NAME,
        "pf_label": PF_LABEL,
        "cache_base": str(cache_base),
        "integral_cache_schema_version": sc._SURFACE_CODE_INTEGRAL_CACHE_VERSION,
        "reproducibility_scope": (
            "The guarantee is strict reproducibility after reusing the same integral "
            "cache entry. The first generated integral values may differ when the "
            "cache is newly created on another run or environment."
        ),
        "runs": all_runs,
        "integral_cache_reproducibility": compare_integral_cache_runs(integral_runs),
        "timing": timing_table(all_runs),
        "theta_count_multisets": {
            run["label"]: dict(Counter(run["rz_occurrence_thetas"]))
            for run in integral_runs
        },
    }
    write_json(output_path, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "artifacts/surface_code_experiment_summaries/"
            "h4_integral_cache_reproducibility_summary.json"
        ),
    )
    parser.add_argument(
        "--cache-base",
        type=Path,
        default=Path("artifacts/surface_code_cache/h4_integral_cache_reproducibility"),
    )
    args = parser.parse_args()
    summary = run_investigation(args.output.resolve(), args.cache_base.resolve())
    print(json.dumps(summary["integral_cache_reproducibility"], indent=2, sort_keys=True))
    print(json.dumps(summary["timing"], indent=2, sort_keys=True))
    print(f"summary: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
