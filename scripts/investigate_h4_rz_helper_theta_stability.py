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
GATE_DEF_RE = re.compile(r"^gate\s+(?P<name>\w+)\s+\w+\s+\{\s*rz\((?P<theta>.+)\)\s+\w+;\s*\}$")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=True, indent=2, sort_keys=True)
        f.write("\n")


def file_sha256(path: Path) -> str:
    return sc.file_sha256(path)


def evaluated_theta(theta: str) -> float:
    return float(sc._eval_qasm_angle(str(theta)))


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


def helper_input_hashes(ir_path: Path, helpers: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
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
                "raw_single_ir_hash": sc._canonical_json_hash(helper_ir),
                "normalized_single_ir_hash": sc._canonical_json_hash(normalized_value),
            }
        )
    return out


def summarize_stage_metrics(stage_path: Path) -> dict[str, Any]:
    stage = load_json(stage_path)
    stages = list(stage.get("stages", []))
    prefix_elapsed: defaultdict[str, float] = defaultdict(float)
    prefix_count: defaultdict[str, int] = defaultdict(int)
    helper_qret_rss: list[int] = []
    lookup_hit = 0
    lookup_miss = 0

    for item in stages:
        name = str(item.get("name", ""))
        elapsed = float(item.get("elapsed_seconds", 0.0))
        prefix = name
        if name.startswith("rz_helper_independent_cache_lookup_"):
            prefix = "rz_helper_independent_cache_lookup"
            status = item.get("result", {}).get("cache_status")
            if status == "hit":
                lookup_hit += 1
            elif status == "miss":
                lookup_miss += 1
        elif name.startswith("rz_helper_independent_cache_lock_"):
            prefix = "rz_helper_independent_cache_lock"
        elif name.startswith("qret_opt_rz_helper_independent_"):
            prefix = "qret_opt_rz_helper_independent"
        elif name.startswith("qret_opt_rz_helper_"):
            prefix = "qret_opt_rz_helper"

        prefix_elapsed[prefix] += elapsed
        prefix_count[prefix] += 1
        maxrss = item.get("result", {}).get("subprocess_maxrss_kb")
        if maxrss is not None and (
            name.startswith("qret_opt_rz_helper_independent_")
            or name.startswith("qret_opt_rz_helper_")
        ):
            helper_qret_rss.append(int(maxrss))

    elapsed_by_prefix = [
        {
            "stage": key,
            "count": int(prefix_count[key]),
            "elapsed_seconds": round(value, 6),
        }
        for key, value in sorted(prefix_elapsed.items(), key=lambda kv: kv[1], reverse=True)
    ]
    return {
        "path": str(stage_path),
        "status": stage.get("status"),
        "elapsed_seconds": float(stage.get("elapsed_seconds", 0.0)),
        "rss": dict(stage.get("rss", {})),
        "stage_count": int(stage.get("stage_count", len(stages))),
        "elapsed_by_prefix": elapsed_by_prefix,
        "dominant_stage": elapsed_by_prefix[0] if elapsed_by_prefix else None,
        "helper_cache_lookup_hit_count": int(lookup_hit),
        "helper_cache_lookup_miss_count": int(lookup_miss),
        "helper_qret_max_subprocess_maxrss_kb": (
            max(helper_qret_rss) if helper_qret_rss else None
        ),
    }


def prepare_h4(cache_root: Path) -> tuple[sc.SurfaceCodeStepArtifact, float]:
    sc.SURFACE_CODE_CACHE_DIR = cache_root
    sc.SURFACE_CODE_RZ_CALL_CACHE = True
    sc.SURFACE_CODE_RZ_HELPER_OPT_MODE = "independent_helper"
    started = time.perf_counter()
    artifact = sc.prepare_grouped_surface_code_step_artifact(HAM_NAME, PF_LABEL)
    return artifact, float(time.perf_counter() - started)


def collect_run(label: str, cache_root: Path, *, clean_root: bool) -> dict[str, Any]:
    if clean_root and cache_root.exists():
        shutil.rmtree(cache_root)
    artifact, wall_elapsed = prepare_h4(cache_root)
    metadata_path = artifact.runtime_root / "rz_call_cache_metadata.json"
    rz_metadata = load_json(metadata_path)
    helpers = list(rz_metadata.get("helpers", []))
    theta_occurrences = extract_rewritten_qasm_rz_occurrences(artifact.qasm_path)
    helper_hashes = helper_input_hashes(artifact.ir_path, helpers)
    cached_opt = artifact.rz_call_cache.get("cached_opt", {})
    helper_cache = cached_opt.get("helper_cache", {}) if isinstance(cached_opt, Mapping) else {}
    stage_path = artifact.runtime_root / sc._PREPARE_STAGE_METRICS_FILENAME
    cache_hit_stage_path = artifact.runtime_root / sc._PREPARE_STAGE_CACHE_HIT_METRICS_FILENAME
    effective_stage_path = cache_hit_stage_path if cache_hit_stage_path.exists() else stage_path

    return {
        "label": label,
        "cache_root": str(cache_root),
        "runtime_root": str(artifact.runtime_root),
        "wall_elapsed_seconds": wall_elapsed,
        "step_time": float(artifact.step_time),
        "rotation_precision": float(artifact.rotation_precision),
        "qasm_path": str(artifact.qasm_path),
        "ir_path": str(artifact.ir_path),
        "optimized_ir_path": str(artifact.optimized_ir_path),
        "step_qasm_sha256": file_sha256(artifact.qasm_path),
        "step_ir_sha256": file_sha256(artifact.ir_path),
        "optimized_ir_sha256": file_sha256(artifact.optimized_ir_path),
        "rz_occurrence_thetas": theta_occurrences,
        "rz_occurrence_theta_count": int(len(theta_occurrences)),
        "rz_occurrence_theta_unique_string_count": int(len(set(theta_occurrences))),
        "rz_occurrence_theta_unique_float_count": int(
            len({repr(evaluated_theta(theta)) for theta in theta_occurrences})
        ),
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
        "helper_count": int(len(helpers)),
        "helper_input_hashes": helper_hashes,
        "helper_cache": {
            "hit_count": helper_cache.get("hit_count"),
            "miss_count": helper_cache.get("miss_count"),
            "legacy_full_ir_count": helper_cache.get("legacy_full_ir_count"),
        },
        "prepare_stage_metrics_path": str(stage_path),
        "effective_stage_metrics_path": str(effective_stage_path),
        "stage_metrics": summarize_stage_metrics(effective_stage_path),
    }


def theta_pairwise_summary(a: list[str], b: list[str]) -> dict[str, Any]:
    paired = min(len(a), len(b))
    examples: list[dict[str, Any]] = []
    string_diff_count = 0
    string_only_diff_count = 0
    numeric_diff_count = 0
    max_abs_diff = 0.0
    for index in range(paired):
        theta_a = a[index]
        theta_b = b[index]
        value_a = evaluated_theta(theta_a)
        value_b = evaluated_theta(theta_b)
        abs_diff = abs(value_a - value_b)
        if theta_a != theta_b:
            string_diff_count += 1
            if value_a == value_b:
                string_only_diff_count += 1
            if len(examples) < 10:
                examples.append(
                    {
                        "index": int(index),
                        "theta_a": theta_a,
                        "theta_b": theta_b,
                        "value_a": value_a,
                        "value_b": value_b,
                        "abs_diff": abs_diff,
                    }
                )
        if value_a != value_b:
            numeric_diff_count += 1
        max_abs_diff = max(max_abs_diff, abs_diff)

    a_values = [repr(evaluated_theta(theta)) for theta in a]
    b_values = [repr(evaluated_theta(theta)) for theta in b]
    return {
        "length_a": int(len(a)),
        "length_b": int(len(b)),
        "paired_count": int(paired),
        "string_sequence_equal": a == b,
        "numeric_sequence_equal": a_values == b_values,
        "string_multiset_equal": Counter(a) == Counter(b),
        "numeric_multiset_equal": Counter(a_values) == Counter(b_values),
        "string_diff_count": int(string_diff_count),
        "string_only_diff_count": int(string_only_diff_count),
        "numeric_diff_count": int(numeric_diff_count),
        "max_abs_numeric_diff": max_abs_diff,
        "first_differences": examples,
    }


def hash_multiset(values: Iterable[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def compare_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    qasm_hashes = [run["step_qasm_sha256"] for run in runs]
    ir_hashes = [run["step_ir_sha256"] for run in runs]
    theta_lists = [run["rz_occurrence_thetas"] for run in runs]
    helper_norm_hashes = [
        [item["normalized_single_ir_hash"] for item in run["helper_input_hashes"]]
        for run in runs
    ]
    helper_raw_hashes = [
        [item["raw_single_ir_hash"] for item in run["helper_input_hashes"]]
        for run in runs
    ]

    if len(set(qasm_hashes)) > 1:
        first_diff_stage = "step.qasm"
    elif len(set(ir_hashes)) > 1:
        first_diff_stage = "step_ir.json"
    elif any(theta != theta_lists[0] for theta in theta_lists[1:]):
        first_diff_stage = "theta_occurrence_list"
    elif any(hashes != helper_norm_hashes[0] for hashes in helper_norm_hashes[1:]):
        first_diff_stage = "helper_input_hash"
    else:
        first_diff_stage = "no_difference_detected"

    pairwise: list[dict[str, Any]] = []
    for index in range(1, len(runs)):
        base = runs[0]
        other = runs[index]
        base_norm = helper_norm_hashes[0]
        other_norm = helper_norm_hashes[index]
        base_raw = helper_raw_hashes[0]
        other_raw = helper_raw_hashes[index]
        pairwise.append(
            {
                "a": base["label"],
                "b": other["label"],
                "step_qasm_sha_equal": base["step_qasm_sha256"]
                == other["step_qasm_sha256"],
                "step_ir_sha_equal": base["step_ir_sha256"] == other["step_ir_sha256"],
                "theta": theta_pairwise_summary(
                    base["rz_occurrence_thetas"],
                    other["rz_occurrence_thetas"],
                ),
                "helpers": {
                    "count_a": int(base["helper_count"]),
                    "count_b": int(other["helper_count"]),
                    "function_name_sequence_equal": [
                        helper["function_name"] for helper in base["helpers"]
                    ]
                    == [helper["function_name"] for helper in other["helpers"]],
                    "key_sequence_equal": [helper["key"] for helper in base["helpers"]]
                    == [helper["key"] for helper in other["helpers"]],
                    "theta_sequence_equal": [
                        helper["theta"] for helper in base["helpers"]
                    ]
                    == [helper["theta"] for helper in other["helpers"]],
                    "raw_single_ir_hash_sequence_equal": base_raw == other_raw,
                    "normalized_single_ir_hash_sequence_equal": base_norm == other_norm,
                    "raw_single_ir_hash_multiset_equal": Counter(base_raw)
                    == Counter(other_raw),
                    "normalized_single_ir_hash_multiset_equal": Counter(base_norm)
                    == Counter(other_norm),
                    "normalized_only_metadata_or_name_difference": (
                        Counter(base_norm) == Counter(other_norm)
                        and Counter(base_raw) != Counter(other_raw)
                    ),
                    "normalized_hash_a_minus_b_count": int(
                        sum((Counter(base_norm) - Counter(other_norm)).values())
                    ),
                    "normalized_hash_b_minus_a_count": int(
                        sum((Counter(other_norm) - Counter(base_norm)).values())
                    ),
                },
            }
        )

    return {
        "first_diff_stage": first_diff_stage,
        "step_qasm_hashes": qasm_hashes,
        "step_ir_hashes": ir_hashes,
        "helper_counts": [run["helper_count"] for run in runs],
        "rz_occurrence_counts": [run["rz_occurrence_theta_count"] for run in runs],
        "unique_theta_string_counts": [
            run["rz_occurrence_theta_unique_string_count"] for run in runs
        ],
        "unique_theta_float_counts": [
            run["rz_occurrence_theta_unique_float_count"] for run in runs
        ],
        "pairwise_against_run_1": pairwise,
        "helper_normalized_hash_multisets": [
            hash_multiset(hashes) for hashes in helper_norm_hashes
        ],
    }


def remove_prepared_artifacts(cache_root: Path) -> None:
    shutil.rmtree(cache_root / "gr" / "prepared_step", ignore_errors=True)


def run_investigation(output_path: Path, cache_base: Path) -> dict[str, Any]:
    if cache_base.exists():
        shutil.rmtree(cache_base)
    cache_base.mkdir(parents=True, exist_ok=True)

    triplicate_runs: list[dict[str, Any]] = []
    for run_index in range(1, 4):
        triplicate_runs.append(
            collect_run(
                f"triplicate_run_{run_index}",
                cache_base / "triplicate" / f"run_{run_index}",
                clean_root=True,
            )
        )
        write_json(output_path, {"status": "running", "triplicate_runs": triplicate_runs})

    timing_root = cache_base / "timing" / "shared_helper_cache"
    cold_no_helper_cache = collect_run(
        "timing_no_prepared_no_helper_cache",
        timing_root,
        clean_root=True,
    )
    remove_prepared_artifacts(timing_root)
    helper_cache_available = collect_run(
        "timing_no_prepared_helper_cache_available",
        timing_root,
        clean_root=False,
    )
    prepared_artifact_available = collect_run(
        "timing_prepared_artifact_available",
        timing_root,
        clean_root=False,
    )

    summary = {
        "status": "ok",
        "ham_name": HAM_NAME,
        "pf_label": PF_LABEL,
        "cache_base": str(cache_base),
        "triplicate_runs": triplicate_runs,
        "triplicate_comparison": compare_runs(triplicate_runs),
        "timing_runs": [
            cold_no_helper_cache,
            helper_cache_available,
            prepared_artifact_available,
        ],
        "timing_comparison": {
            "stage_elapsed_seconds": [
                {
                    "label": run["label"],
                    "wall_elapsed_seconds": round(run["wall_elapsed_seconds"], 6),
                    "metrics_elapsed_seconds": round(
                        float(run["stage_metrics"]["elapsed_seconds"]),
                        6,
                    ),
                    "dominant_stage": run["stage_metrics"]["dominant_stage"],
                    "helper_cache": run["helper_cache"],
                }
                for run in [
                    cold_no_helper_cache,
                    helper_cache_available,
                    prepared_artifact_available,
                ]
            ],
            "helper_cache_hit_dominant_stage": helper_cache_available[
                "stage_metrics"
            ]["dominant_stage"],
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
            "h4_rz_helper_theta_stability_summary.json"
        ),
    )
    parser.add_argument(
        "--cache-base",
        type=Path,
        default=Path("artifacts/surface_code_cache/h4_rz_helper_theta_stability"),
    )
    args = parser.parse_args()
    summary = run_investigation(args.output.resolve(), args.cache_base.resolve())
    print(json.dumps(summary["triplicate_comparison"], indent=2, sort_keys=True))
    print(json.dumps(summary["timing_comparison"], indent=2, sort_keys=True))
    print(f"summary: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
