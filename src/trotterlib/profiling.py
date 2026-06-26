from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


STAGE_PROFILE_FIELDS = [
    "commit_sha",
    "case_name",
    "phase",
    "molecule",
    "hchain_size",
    "pf_label",
    "cache_condition",
    "batch_size",
    "compile_mode",
    "stage_index",
    "stage_name",
    "elapsed_seconds",
    "python_current_rss_before_kb",
    "python_current_rss_after_kb",
    "python_current_rss_delta_kb",
    "python_sampled_peak_rss_kb",
    "python_self_maxrss_kb",
    "python_self_maxrss_delta_kb",
    "python_self_maxrss_before_kb",
    "python_self_maxrss_after_kb",
    "python_children_maxrss_kb",
    "subprocess_maxrss_kb",
    "input_bytes",
    "output_bytes",
    "instruction_count",
    "helper_count",
    "qret_invocation_count",
    "cache_status",
    "status",
    "failed_stage",
]


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _path_size_from_details(details: Mapping[str, Any], key: str) -> int | None:
    path_value = details.get(key)
    if not path_value:
        return None
    try:
        return int(Path(str(path_value)).expanduser().stat().st_size)
    except OSError:
        return None


def _stage_input_bytes(details: Mapping[str, Any], result: Mapping[str, Any]) -> int | None:
    value = _first_present(
        result.get("input_size_bytes"),
        details.get("input_size_bytes"),
        _path_size_from_details(details, "input_path"),
    )
    return None if value is None else int(value)


def _stage_output_bytes(details: Mapping[str, Any], result: Mapping[str, Any]) -> int | None:
    value = _first_present(
        result.get("output_size_bytes"),
        details.get("output_size_bytes"),
        _path_size_from_details(details, "output_path"),
    )
    return None if value is None else int(value)


def _stage_helper_count(details: Mapping[str, Any], result: Mapping[str, Any]) -> int | None:
    helpers = _first_present(
        result.get("helper_count"),
        result.get("planned_helper_count"),
        details.get("helper_count"),
        details.get("planned_helper_count"),
    )
    if helpers is not None:
        return int(helpers)
    function_names = _first_present(details.get("function_names"), result.get("function_names"))
    if isinstance(function_names, Sequence) and not isinstance(function_names, (str, bytes)):
        return len(function_names)
    return None


def flatten_stage_metrics(
    stage_metrics: Mapping[str, Any],
    *,
    commit_sha: str,
    case_name: str,
    phase: str,
    cache_condition: str,
    hchain_size: int | None = None,
) -> list[dict[str, Any]]:
    metadata = _as_mapping(stage_metrics.get("metadata"))
    rows: list[dict[str, Any]] = []
    for stage in stage_metrics.get("stages", []):
        if not isinstance(stage, Mapping):
            continue
        details = _as_mapping(stage.get("details"))
        result = _as_mapping(stage.get("result"))
        rss_after = _as_mapping(stage.get("rss_after"))
        rows.append(
            {
                "commit_sha": commit_sha,
                "case_name": case_name,
                "phase": phase,
                "molecule": _first_present(metadata.get("molecule"), metadata.get("ham_name")),
                "hchain_size": hchain_size,
                "pf_label": metadata.get("pf_label"),
                "cache_condition": cache_condition,
                "batch_size": _first_present(
                    metadata.get("rz_helper_batch_size"),
                    details.get("configured_batch_size"),
                    result.get("configured_batch_size"),
                ),
                "compile_mode": metadata.get("compile_mode"),
                "stage_index": stage.get("index"),
                "stage_name": stage.get("name"),
                "elapsed_seconds": stage.get("elapsed_seconds"),
                "python_current_rss_before_kb": stage.get(
                    "python_current_rss_before_kb"
                ),
                "python_current_rss_after_kb": stage.get(
                    "python_current_rss_after_kb"
                ),
                "python_current_rss_delta_kb": stage.get(
                    "python_current_rss_delta_kb"
                ),
                "python_sampled_peak_rss_kb": stage.get(
                    "python_sampled_peak_rss_kb"
                ),
                "python_self_maxrss_kb": rss_after.get("self_maxrss_kb"),
                "python_self_maxrss_delta_kb": stage.get("self_maxrss_delta_kb"),
                "python_self_maxrss_before_kb": stage.get(
                    "python_self_maxrss_before_kb"
                ),
                "python_self_maxrss_after_kb": stage.get(
                    "python_self_maxrss_after_kb"
                ),
                "python_children_maxrss_kb": rss_after.get("children_maxrss_kb"),
                "subprocess_maxrss_kb": result.get("subprocess_maxrss_kb"),
                "input_bytes": _stage_input_bytes(details, result),
                "output_bytes": _stage_output_bytes(details, result),
                "instruction_count": _first_present(
                    result.get("instruction_count"),
                    result.get("scheduled_instruction_count"),
                    result.get("emitted_instruction_count"),
                ),
                "helper_count": _stage_helper_count(details, result),
                "qret_invocation_count": 1 if details.get("command") else 0,
                "cache_status": _first_present(
                    result.get("cache_status"),
                    details.get("cache_status"),
                    "hit" if result.get("cache_hit") is True else None,
                    "miss" if result.get("cache_hit") is False else None,
                ),
                "status": stage.get("status"),
                "failed_stage": stage.get("name") if stage.get("status") == "failed" else None,
            }
        )
    return rows


def write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(dict(row), ensure_ascii=True, sort_keys=True) + "\n")


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=STAGE_PROFILE_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in STAGE_PROFILE_FIELDS})


def slowest_stage(rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    candidates = [row for row in rows if row.get("elapsed_seconds") is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda row: float(row.get("elapsed_seconds") or 0.0))


def peak_python_rss_stage(rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    candidates = [
        row
        for row in rows
        if row.get("python_sampled_peak_rss_kb") is not None
        or row.get("python_current_rss_after_kb") is not None
        or row.get("python_self_maxrss_kb") is not None
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda row: int(
            row.get("python_sampled_peak_rss_kb")
            or row.get("python_current_rss_after_kb")
            or row.get("python_self_maxrss_kb")
            or 0
        ),
    )


def largest_python_current_rss_delta_stage(
    rows: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    candidates = [
        row for row in rows if row.get("python_current_rss_delta_kb") is not None
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda row: int(row.get("python_current_rss_delta_kb") or 0),
    )


def peak_subprocess_rss_stage(rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    candidates = [row for row in rows if row.get("subprocess_maxrss_kb") is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda row: int(row.get("subprocess_maxrss_kb") or 0))
