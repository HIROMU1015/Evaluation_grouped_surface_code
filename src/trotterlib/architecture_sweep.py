from __future__ import annotations

import csv
import json
import math
import os
import re
import traceback
from pathlib import Path
from typing import Any, Mapping

import yaml

from .config import (
    SURFACE_CODE_QCSF_PATH,
    SURFACE_CODE_TOPOLOGY_PATH,
    TARGET_ERROR,
    normalize_pf_label,
)
from .surface_code import (
    SurfaceCodeArchitecture,
    SurfaceCodeStepArtifact,
    _compile_uses_qec,
    _compile_uses_topology,
    compile_prepared_surface_code_step_artifact,
    file_sha256,
    grouped_hchain_ham_name,
    load_grouped_alpha_and_order,
    prepare_grouped_surface_code_step_artifact,
    qpe_iteration_factor,
    surface_code_compile_cache_key,
)


COMPILED_CIRCUIT_SCOPE = "uncontrolled_pf_one_step"
QPE_SCALING_MODEL = "linear_extrapolation_from_uncontrolled_pf_one_step"

RESULT_FIELDS = [
    "status",
    "compiled_circuit_scope",
    "qpe_scaling_model",
    "molecule",
    "num_logical_qubits",
    "pf_label",
    "step_time",
    "qasm_hash",
    "optimized_ir_hash",
    "rotation_precision",
    "step_rz_count",
    "step_rz_layer",
    "step_rz_depth",
    "step_magic_state_count",
    "step_magic_state_depth",
    "pf_error_coefficient",
    "pf_order",
    "qpe_target_error",
    "qpe_effective_block_count",
    "qpe_action_count",
    "case_name",
    "topology_name",
    "topology_path",
    "topology_hash",
    "mapping_result_json",
    "mapping_result_hash",
    "mapping_result_unavailable_reason",
    "machine_type",
    "magic_generation_period",
    "resolved_maximum_magic_state_stock",
    "stock_policy",
    "entanglement_generation_period",
    "maximum_entangled_state_stock",
    "reaction_time",
    "compile_mode",
    "compiler_executable_path",
    "compiler_executable_hash",
    "cache_key",
    "compile_cache_hit",
    "runtime_without_topology",
    "runtime_without_topology_unavailable_reason",
    "runtime_with_topology",
    "runtime_with_topology_unavailable_reason",
    "runtime_difference_vs_topology_free",
    "runtime_difference_vs_topology_free_unavailable_reason",
    "chip_cells",
    "chip_cells_unavailable_reason",
    "qubit_volume",
    "qubit_volume_unavailable_reason",
    "physical_qubits",
    "physical_qubits_unavailable_reason",
    "code_distance",
    "code_distance_unavailable_reason",
    "failure_probability",
    "failure_probability_unavailable_reason",
    "compile_elapsed_time",
    "compile_elapsed_time_unavailable_reason",
    "peak_process_memory",
    "peak_process_memory_unavailable_reason",
    "total_magic_state_count",
    "total_magic_state_depth",
    "total_runtime_without_topology",
    "total_runtime_without_topology_unavailable_reason",
    "total_runtime_with_topology",
    "total_runtime_with_topology_unavailable_reason",
    "total_runtime_difference_vs_topology_free",
    "total_runtime_difference_vs_topology_free_unavailable_reason",
    "total_qubit_volume",
    "total_qubit_volume_unavailable_reason",
    "error_type",
    "error_message",
]


def expand_env_vars(value: Any) -> Any:
    if isinstance(value, str):
        return os.path.expandvars(os.path.expanduser(value))
    if isinstance(value, list):
        return [expand_env_vars(item) for item in value]
    if isinstance(value, dict):
        return {key: expand_env_vars(item) for key, item in value.items()}
    return value


def load_architecture_sweep_config(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path).expanduser().resolve()
    with path.open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Config root must be a mapping: {path}")
    loaded = expand_env_vars(loaded)
    loaded["_config_path"] = str(path)
    return loaded


def _path_or_default(value: Any, default: str | Path) -> Path:
    if value in (None, ""):
        return Path(default).expanduser().resolve()
    return Path(str(value)).expanduser().resolve()


def _hchain_length(molecule: str) -> int:
    match = re.fullmatch(r"H(?P<chain>\d+)", str(molecule).strip())
    if match is None:
        raise ValueError(f"Only H-chain labels such as H2 are supported: {molecule!r}")
    return int(match.group("chain"))


def _stock_spec(case: Mapping[str, Any], defaults: Mapping[str, Any]) -> Any:
    if "maximum_magic_state_stock" in case:
        return case["maximum_magic_state_stock"]
    return defaults.get("maximum_magic_state_stock", 10000)


def resolve_magic_state_stock(
    stock_spec: Any,
    artifact: SurfaceCodeStepArtifact,
) -> tuple[str, int]:
    if isinstance(stock_spec, Mapping):
        policy = str(stock_spec.get("policy", "fixed"))
        value = stock_spec.get("value")
    else:
        policy = "fixed"
        value = stock_spec

    if policy == "fixed":
        if value is None:
            raise ValueError("fixed stock policy requires a value")
        resolved = int(value)
    elif policy == "peak_magic_layer":
        resolved = int(artifact.peak_magic_layer)
    elif policy == "full_step_magic_count":
        resolved = int(artifact.step_magic_state_count)
    else:
        raise ValueError(f"Unknown magic-state stock policy: {policy}")

    if resolved <= 0:
        raise ValueError(f"Resolved magic-state stock must be positive: {resolved}")
    return policy, resolved


def _topology_config(config: Mapping[str, Any], topology_name: str) -> dict[str, Any]:
    topologies = config.get("topologies", {})
    if not isinstance(topologies, Mapping):
        raise ValueError("topologies must be a mapping")
    raw = topologies.get(topology_name)
    if raw is None:
        raise ValueError(f"Unknown topology: {topology_name}")
    if not isinstance(raw, Mapping):
        raise ValueError(f"topology config must be a mapping: {topology_name}")
    return dict(raw)


def _default_case_values(config: Mapping[str, Any]) -> dict[str, Any]:
    defaults = config.get("defaults", {})
    if defaults is None:
        return {}
    if not isinstance(defaults, Mapping):
        raise ValueError("defaults must be a mapping")
    return dict(defaults)


def _qec_values(config: Mapping[str, Any]) -> dict[str, Any]:
    qec = config.get("qec", {})
    if qec is None:
        return {}
    if not isinstance(qec, Mapping):
        raise ValueError("qec must be a mapping")
    return dict(qec)


def build_architecture_for_case(
    config: Mapping[str, Any],
    case: Mapping[str, Any],
    artifact: SurfaceCodeStepArtifact,
) -> tuple[SurfaceCodeArchitecture, str, int, str, Path]:
    defaults = _default_case_values(config)
    qec = _qec_values(config)
    topology_name = str(case.get("topology", defaults.get("topology", "tutorial")))
    topology = _topology_config(config, topology_name)
    topology_path = _path_or_default(topology.get("path"), SURFACE_CODE_TOPOLOGY_PATH)
    qret_path = _path_or_default(config.get("qret_path"), SURFACE_CODE_QCSF_PATH)

    compile_mode = str(case.get("compile_mode", defaults.get("compile_mode", "ftqc_compile_topology")))
    if compile_mode == "decompose_only":
        raise ValueError("decompose_only cannot be used for topology-aware architecture sweep")

    stock_policy, resolved_stock = resolve_magic_state_stock(
        _stock_spec(case, defaults),
        artifact,
    )
    architecture = SurfaceCodeArchitecture(
        name=str(case.get("name", "case")),
        compile_mode=compile_mode,
        qret_path=qret_path,
        topology_path=topology_path,
        machine_type=str(case.get("machine_type", defaults.get("machine_type", "Dim2"))),
        magic_generation_period=int(
            case.get("magic_generation_period", defaults.get("magic_generation_period", 15))
        ),
        maximum_magic_state_stock=resolved_stock,
        entanglement_generation_period=int(
            case.get(
                "entanglement_generation_period",
                defaults.get("entanglement_generation_period", 100),
            )
        ),
        maximum_entangled_state_stock=int(
            case.get(
                "maximum_entangled_state_stock",
                defaults.get("maximum_entangled_state_stock", 10),
            )
        ),
        reaction_time=int(case.get("reaction_time", defaults.get("reaction_time", 1))),
        physical_error_rate=float(qec.get("physical_error_rate", 1.0e-3)),
        drop_rate=float(qec.get("drop_rate", 0.1)),
        code_cycle_time_sec=float(qec.get("code_cycle_time_sec", 1.0e-6)),
        allowed_failure_prob=float(qec.get("allowed_failure_prob", 1.0e-2)),
        skip_compile_output=bool(
            case.get("skip_compile_output", defaults.get("skip_compile_output", True))
        ),
        save_mapping_result=bool(
            case.get("save_mapping_result", defaults.get("save_mapping_result", False))
        ),
    )
    return architecture, stock_policy, resolved_stock, topology_name, topology_path


def _qpe_scale_row(
    ham_name: str,
    pf_label: str,
    *,
    target_error: float,
) -> dict[str, Any]:
    alpha, order = load_grouped_alpha_and_order(ham_name, pf_label)
    effective_block_count = qpe_iteration_factor(alpha, order, target_error)
    action_count = int(math.ceil(effective_block_count))
    return {
        "pf_error_coefficient": float(alpha),
        "pf_order": float(order),
        "qpe_target_error": float(target_error),
        "qpe_effective_block_count": float(effective_block_count),
        "qpe_action_count": action_count,
    }


def _artifact_row(
    artifact: SurfaceCodeStepArtifact | None,
    *,
    molecule: str,
    pf_label: str,
    qpe_scale: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "compiled_circuit_scope": COMPILED_CIRCUIT_SCOPE,
        "qpe_scaling_model": QPE_SCALING_MODEL,
        "molecule": molecule,
        "pf_label": pf_label,
    }
    if qpe_scale is not None:
        row.update(qpe_scale)
    if artifact is None:
        return row
    row.update(
        {
            "num_logical_qubits": artifact.num_logical_qubits,
            "step_time": artifact.step_time,
            "qasm_hash": artifact.qasm_hash,
            "optimized_ir_hash": artifact.optimized_ir_hash,
            "rotation_precision": artifact.rotation_precision,
            "step_rz_count": artifact.step_rz_count,
            "step_rz_layer": artifact.step_rz_layer,
            "step_rz_depth": artifact.step_rz_layer,
            "step_magic_state_count": artifact.step_magic_state_count,
            "step_magic_state_depth": artifact.step_magic_state_depth,
        }
    )
    return row


def _scale_resource(value: Any, action_count: Any) -> Any:
    if value is None or action_count is None:
        return None
    return int(value) * int(action_count)


def _add_qpe_total_resource_fields(row: dict[str, Any]) -> None:
    action_count = row.get("qpe_action_count")
    row["total_magic_state_count"] = _scale_resource(
        row.get("step_magic_state_count"),
        action_count,
    )
    row["total_magic_state_depth"] = _scale_resource(
        row.get("step_magic_state_depth"),
        action_count,
    )

    scaled_specs = [
        (
            "runtime_without_topology",
            "runtime_without_topology_unavailable_reason",
            "total_runtime_without_topology",
            "total_runtime_without_topology_unavailable_reason",
        ),
        (
            "runtime_with_topology",
            "runtime_with_topology_unavailable_reason",
            "total_runtime_with_topology",
            "total_runtime_with_topology_unavailable_reason",
        ),
        (
            "runtime_difference_vs_topology_free",
            "runtime_difference_vs_topology_free_unavailable_reason",
            "total_runtime_difference_vs_topology_free",
            "total_runtime_difference_vs_topology_free_unavailable_reason",
        ),
        (
            "qubit_volume",
            "qubit_volume_unavailable_reason",
            "total_qubit_volume",
            "total_qubit_volume_unavailable_reason",
        ),
    ]
    for source_key, source_reason_key, total_key, total_reason_key in scaled_specs:
        row[total_key] = _scale_resource(row.get(source_key), action_count)
        if row[total_key] is None:
            row[total_reason_key] = row.get(source_reason_key) or "qpe_action_count_unavailable"
        else:
            row[total_reason_key] = None


def _metric_value(
    raw: Mapping[str, Any],
    key: str,
    *,
    compile_mode: str,
    requires_topology: bool = False,
    requires_qec: bool = False,
) -> tuple[Any, str | None]:
    if requires_topology and not _compile_uses_topology(compile_mode):
        return None, "requires_topology_compile_mode"
    if requires_qec and not _compile_uses_qec(compile_mode):
        return None, "requires_ftqc_compile_topology_qec"
    if key not in raw:
        return None, "missing_in_compile_info"
    return raw[key], None


def _first_existing_metric(raw: Mapping[str, Any], keys: tuple[str, ...]) -> tuple[Any, str | None]:
    for key in keys:
        if key in raw:
            return raw[key], None
    return None, "missing_in_compile_info"


def _compile_info_row(
    *,
    raw: Mapping[str, Any],
    metrics: Mapping[str, Any],
    compile_mode: str,
) -> dict[str, Any]:
    row: dict[str, Any] = {}
    if "magic_state_consumption_count" in raw:
        row["step_magic_state_count"] = raw["magic_state_consumption_count"]
    if "magic_state_consumption_depth" in raw:
        row["step_magic_state_depth"] = raw["magic_state_consumption_depth"]
    metric_specs = {
        "runtime_without_topology": ("runtime_without_topology", False, False),
        "runtime_with_topology": ("runtime", True, False),
        "chip_cells": ("chip_cell_count", True, False),
        "qubit_volume": ("qubit_volume", True, False),
        "physical_qubits": ("num_physical_qubits", True, True),
        "code_distance": ("code_distance", True, True),
    }
    for out_key, (raw_key, needs_topology, needs_qec) in metric_specs.items():
        value, reason = _metric_value(
            raw,
            raw_key,
            compile_mode=compile_mode,
            requires_topology=needs_topology,
            requires_qec=needs_qec,
        )
        row[out_key] = value
        row[f"{out_key}_unavailable_reason"] = reason

    if row["runtime_with_topology"] is None or row["runtime_without_topology"] is None:
        row["runtime_difference_vs_topology_free"] = None
        row["runtime_difference_vs_topology_free_unavailable_reason"] = (
            "runtime_metric_unavailable"
        )
    else:
        row["runtime_difference_vs_topology_free"] = int(row["runtime_with_topology"]) - int(
            row["runtime_without_topology"]
        )
        row["runtime_difference_vs_topology_free_unavailable_reason"] = None

    row["mapping_result_json"] = metrics.get("mapping_result_json")
    row["mapping_result_hash"] = metrics.get("mapping_result_hash")
    row["mapping_result_unavailable_reason"] = metrics.get(
        "mapping_result_unavailable_reason"
    )

    failure_value, failure_reason = _first_existing_metric(
        raw,
        (
            "task_failure_probability",
            "failure_probability",
            "logical_failure_probability",
        ),
    )
    if not _compile_uses_qec(compile_mode) and failure_reason is not None:
        failure_reason = "requires_ftqc_compile_topology_qec"
    row["failure_probability"] = failure_value
    row["failure_probability_unavailable_reason"] = failure_reason

    row["compile_elapsed_time"] = metrics.get("execution_time_sec")
    row["compile_elapsed_time_unavailable_reason"] = (
        None if row["compile_elapsed_time"] is not None else "not_collected"
    )
    row["peak_process_memory"] = None
    row["peak_process_memory_unavailable_reason"] = "not_collected"
    return row


def _architecture_row(
    *,
    architecture: SurfaceCodeArchitecture,
    artifact: SurfaceCodeStepArtifact,
    case_name: str,
    topology_name: str,
    topology_path: Path,
    stock_policy: str,
    resolved_stock: int,
) -> dict[str, Any]:
    topology_hash = (
        file_sha256(topology_path)
        if _compile_uses_topology(architecture.compile_mode) and topology_path.exists()
        else None
    )
    compiler_hash = (
        file_sha256(architecture.qret_path) if Path(architecture.qret_path).exists() else None
    )
    return {
        "case_name": case_name,
        "topology_name": topology_name,
        "topology_path": str(topology_path),
        "topology_hash": topology_hash,
        "machine_type": architecture.machine_type,
        "magic_generation_period": architecture.magic_generation_period,
        "resolved_maximum_magic_state_stock": resolved_stock,
        "stock_policy": stock_policy,
        "entanglement_generation_period": architecture.entanglement_generation_period,
        "maximum_entangled_state_stock": architecture.maximum_entangled_state_stock,
        "reaction_time": architecture.reaction_time,
        "compile_mode": architecture.compile_mode,
        "compiler_executable_path": str(Path(architecture.qret_path).expanduser().resolve()),
        "compiler_executable_hash": compiler_hash,
        "cache_key": surface_code_compile_cache_key(artifact, architecture)
        if Path(architecture.qret_path).exists()
        and (not _compile_uses_topology(architecture.compile_mode) or topology_path.exists())
        else None,
    }


def _finalize_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {field: row.get(field) for field in RESULT_FIELDS}


def _short_unavailable_reason(reason: Any) -> str:
    labels = {
        "requires_ftqc_compile_topology_qec": "QEC mode only",
        "requires_topology_compile_mode": "topology mode only",
        "missing_in_compile_info": "not in compile info",
        "not_collected": "not collected",
        "runtime_metric_unavailable": "runtime unavailable",
    }
    return labels.get(str(reason), str(reason))


def _format_report_cell(value: Any, reason: Any = None) -> str:
    if value is None:
        text = (
            "N/A"
            if reason in (None, "")
            else f"N/A ({_short_unavailable_reason(reason)})"
        )
    elif isinstance(value, int):
        text = f"{value:,}"
    elif isinstance(value, float):
        text = f"{value:.6g}"
    else:
        text = str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_format_report_cell(item) for item in row) + " |")
    return lines


def _format_report_delta(value: Any, baseline: Any) -> str:
    if value is None or baseline in (None, 0):
        return "N/A"
    try:
        value_float = float(value)
        baseline_float = float(baseline)
    except (TypeError, ValueError):
        return "N/A"
    delta = value_float - baseline_float
    percent = 100.0 * delta / baseline_float
    sign = "+" if delta > 0 else ""
    if float(delta).is_integer():
        delta_text = f"{sign}{int(delta):,}"
    else:
        delta_text = f"{sign}{delta:.6g}"
    return f"{delta_text} ({sign}{percent:.2f}%)"


def _pf_sort_key(row: Mapping[str, Any]) -> tuple[float, str]:
    order = row.get("pf_order")
    try:
        order_value = float(order)
    except (TypeError, ValueError):
        order_value = float("inf")
    return order_value, str(row.get("pf_label"))


def _baseline_pf_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    for row in rows:
        if row.get("pf_label") == "2nd":
            return row
    return rows[0] if rows else {}


def _append_pf_comparison_report(lines: list[str], rows: list[dict[str, Any]]) -> None:
    molecule_groups: dict[Any, list[dict[str, Any]]] = {}
    for row in rows:
        molecule_groups.setdefault(row.get("molecule"), []).append(row)

    lines.extend(
        [
            "## PF-Step Linear Scaling Comparison",
            "",
            "These totals are linear extrapolations from one uncontrolled PF step. "
            "They are not compiled full QPE circuits with ancilla, controlled-U, "
            "inverse QFT, measurements, or repeated QPE iterations.",
            "",
        ]
    )
    for molecule, molecule_rows in molecule_groups.items():
        case_groups: dict[Any, list[dict[str, Any]]] = {}
        for row in molecule_rows:
            case_groups.setdefault(row.get("case_name"), []).append(row)

        table_rows: list[list[Any]] = []
        for case_name, case_rows in case_groups.items():
            sorted_rows = sorted(case_rows, key=_pf_sort_key)
            baseline = _baseline_pf_row(sorted_rows)
            for row in sorted_rows:
                table_rows.append(
                    [
                        case_name,
                        row.get("pf_label"),
                        row.get("status"),
                        row.get("qpe_action_count"),
                        row.get("total_magic_state_count"),
                        _format_report_delta(
                            row.get("total_magic_state_count"),
                            baseline.get("total_magic_state_count"),
                        ),
                        row.get("total_magic_state_depth"),
                        _format_report_delta(
                            row.get("total_magic_state_depth"),
                            baseline.get("total_magic_state_depth"),
                        ),
                        _format_report_cell(
                            row.get("total_runtime_with_topology"),
                            row.get("total_runtime_with_topology_unavailable_reason"),
                        ),
                        _format_report_delta(
                            row.get("total_runtime_with_topology"),
                            baseline.get("total_runtime_with_topology"),
                        ),
                        _format_report_cell(
                            row.get("total_qubit_volume"),
                            row.get("total_qubit_volume_unavailable_reason"),
                        ),
                        _format_report_delta(
                            row.get("total_qubit_volume"),
                            baseline.get("total_qubit_volume"),
                        ),
                    ]
                )

        lines.extend(
            [
                f"### {molecule}",
                "",
                *_markdown_table(
                    [
                        "case",
                        "PF",
                        "status",
                        "actions",
                        "total magic count",
                        "vs 2nd",
                        "total magic depth",
                        "vs 2nd",
                        "total runtime topo",
                        "vs 2nd",
                        "total qubit volume",
                        "vs 2nd",
                    ],
                    table_rows,
                ),
                "",
            ]
        )


def _write_markdown_report(rows: list[dict[str, Any]], markdown_path: Path) -> None:
    success_count = sum(1 for row in rows if row.get("status") == "success")
    failed_count = sum(1 for row in rows if row.get("status") == "failed")
    skipped_count = sum(1 for row in rows if row.get("status") == "skipped")
    lines = [
        "# Surface-Code Architecture Sweep",
        "",
        "## Summary",
        "",
        *_markdown_table(
            ["rows", "success", "failed", "skipped"],
            [[len(rows), success_count, failed_count, skipped_count]],
        ),
        "",
    ]

    _append_pf_comparison_report(lines, rows)

    groups: dict[tuple[Any, Any], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((row.get("molecule"), row.get("pf_label")), []).append(row)

    for (molecule, pf_label), group_rows in sorted(groups.items()):
        baseline = next(
            (row for row in group_rows if row.get("case_name") == "baseline"),
            {},
        )
        baseline_runtime = baseline.get("runtime_with_topology")
        baseline_qubit_volume = baseline.get("qubit_volume")
        baseline_total_runtime = baseline.get("total_runtime_with_topology")
        baseline_total_qubit_volume = baseline.get("total_qubit_volume")
        qpe_row = group_rows[0] if group_rows else {}
        lines.extend(
            [
                f"## {molecule} / {pf_label}",
                "",
                "### PF-Step Scaling",
                "",
                *_markdown_table(
                    [
                        "PF coeff",
                        "PF order",
                        "target error",
                        "effective blocks",
                        "actions",
                    ],
                    [
                        [
                            qpe_row.get("pf_error_coefficient"),
                            qpe_row.get("pf_order"),
                            qpe_row.get("qpe_target_error"),
                            qpe_row.get("qpe_effective_block_count"),
                            qpe_row.get("qpe_action_count"),
                        ]
                    ],
                ),
                "",
                "### Linearly Scaled Resources",
                "",
                *_markdown_table(
                    [
                        "case",
                        "status",
                        "total runtime topo",
                        "vs baseline",
                        "total runtime no topo",
                        "total qubit volume",
                        "qv vs baseline",
                        "total magic count",
                        "total magic depth",
                        "cells",
                        "physical qubits",
                        "code distance",
                    ],
                    [
                        [
                            row.get("case_name"),
                            row.get("status"),
                            _format_report_cell(
                                row.get("total_runtime_with_topology"),
                                row.get("total_runtime_with_topology_unavailable_reason"),
                            ),
                            _format_report_delta(
                                row.get("total_runtime_with_topology"),
                                baseline_total_runtime,
                            ),
                            _format_report_cell(
                                row.get("total_runtime_without_topology"),
                                row.get("total_runtime_without_topology_unavailable_reason"),
                            ),
                            _format_report_cell(
                                row.get("total_qubit_volume"),
                                row.get("total_qubit_volume_unavailable_reason"),
                            ),
                            _format_report_delta(
                                row.get("total_qubit_volume"),
                                baseline_total_qubit_volume,
                            ),
                            row.get("total_magic_state_count"),
                            row.get("total_magic_state_depth"),
                            _format_report_cell(
                                row.get("chip_cells"),
                                row.get("chip_cells_unavailable_reason"),
                            ),
                            _format_report_cell(
                                row.get("physical_qubits"),
                                row.get("physical_qubits_unavailable_reason"),
                            ),
                            _format_report_cell(
                                row.get("code_distance"),
                                row.get("code_distance_unavailable_reason"),
                            ),
                        ]
                        for row in group_rows
                    ],
                ),
                "",
                "### Single-Step Resources",
                "",
                *_markdown_table(
                    [
                        "case",
                        "status",
                        "magic period",
                        "stock",
                        "runtime topo",
                        "runtime vs baseline",
                        "runtime no topo",
                        "runtime diff vs no topo",
                        "qubit volume",
                        "qv vs baseline",
                        "cells",
                        "physical qubits",
                        "code distance",
                        "magic count",
                        "magic depth",
                    ],
                    [
                        [
                            row.get("case_name"),
                            row.get("status"),
                            row.get("magic_generation_period"),
                            row.get("resolved_maximum_magic_state_stock"),
                            _format_report_cell(
                                row.get("runtime_with_topology"),
                                row.get("runtime_with_topology_unavailable_reason"),
                            ),
                            _format_report_delta(
                                row.get("runtime_with_topology"),
                                baseline_runtime,
                            ),
                            _format_report_cell(
                                row.get("runtime_without_topology"),
                                row.get("runtime_without_topology_unavailable_reason"),
                            ),
                            _format_report_cell(
                                row.get("runtime_difference_vs_topology_free"),
                                row.get(
                                    "runtime_difference_vs_topology_free_unavailable_reason"
                                ),
                            ),
                            _format_report_cell(
                                row.get("qubit_volume"),
                                row.get("qubit_volume_unavailable_reason"),
                            ),
                            _format_report_delta(
                                row.get("qubit_volume"),
                                baseline_qubit_volume,
                            ),
                            _format_report_cell(
                                row.get("chip_cells"),
                                row.get("chip_cells_unavailable_reason"),
                            ),
                            _format_report_cell(
                                row.get("physical_qubits"),
                                row.get("physical_qubits_unavailable_reason"),
                            ),
                            _format_report_cell(
                                row.get("code_distance"),
                                row.get("code_distance_unavailable_reason"),
                            ),
                            row.get("step_magic_state_count"),
                            row.get("step_magic_state_depth"),
                        ]
                        for row in group_rows
                    ],
                ),
                "",
            ]
        )

    problem_rows = [
        row for row in rows if row.get("status") in {"failed", "skipped"}
    ]
    if problem_rows:
        lines.extend(
            [
                "## Failed Or Skipped Cases",
                "",
                *_markdown_table(
                    ["molecule", "pf", "case", "status", "type", "message"],
                    [
                        [
                            row.get("molecule"),
                            row.get("pf_label"),
                            row.get("case_name"),
                            row.get("status"),
                            row.get("error_type"),
                            row.get("error_message"),
                        ]
                        for row in problem_rows
                    ],
                ),
                "",
            ]
        )

    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_outputs(rows: list[dict[str, Any]], output_config: Mapping[str, Any]) -> tuple[Path, Path, Path]:
    out_dir = _path_or_default(output_config.get("directory"), "artifacts/surface_code_architecture_sweep")
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / str(output_config.get("jsonl", "surface_code_architecture_sweep.jsonl"))
    csv_path = out_dir / str(output_config.get("csv", "surface_code_architecture_sweep.csv"))
    markdown_path = out_dir / str(output_config.get("markdown", "surface_code_architecture_sweep.md"))

    with jsonl_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(_finalize_row(row), ensure_ascii=True, sort_keys=True) + "\n")
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(_finalize_row(row))
    _write_markdown_report([_finalize_row(row) for row in rows], markdown_path)
    return jsonl_path, csv_path, markdown_path


def run_surface_code_architecture_sweep(config_path: str | Path) -> dict[str, Any]:
    config = load_architecture_sweep_config(config_path)
    targets = config.get("targets", {})
    if not isinstance(targets, Mapping):
        raise ValueError("targets must be a mapping")
    molecules = list(targets.get("molecules", ["H2"]))
    pf_labels = [normalize_pf_label(label) for label in targets.get("pf_labels", ["2nd"])]
    cases = config.get("architecture_cases", [])
    if not isinstance(cases, list) or not cases:
        raise ValueError("architecture_cases must be a non-empty list")

    cache_config = config.get("cache", {})
    if cache_config is None:
        cache_config = {}
    if not isinstance(cache_config, Mapping):
        raise ValueError("cache must be a mapping")
    reuse_compile_cache = bool(cache_config.get("reuse_compile_results", True))

    target_error = float(config.get("target_error", TARGET_ERROR))
    rotation_precision = config.get("rotation_precision")
    rotation_precision_value = (
        None if rotation_precision in (None, "") else float(rotation_precision)
    )

    rows: list[dict[str, Any]] = []
    for molecule in molecules:
        molecule_text = str(molecule)
        ham_name = grouped_hchain_ham_name(_hchain_length(molecule_text))
        for pf_label in pf_labels:
            qpe_scale: dict[str, Any] | None = None
            try:
                qpe_scale = _qpe_scale_row(
                    ham_name,
                    pf_label,
                    target_error=target_error,
                )
                prepare_architecture = SurfaceCodeArchitecture(
                    qret_path=_path_or_default(config.get("qret_path"), SURFACE_CODE_QCSF_PATH)
                )
                artifact = prepare_grouped_surface_code_step_artifact(
                    ham_name,
                    pf_label,
                    target_error=target_error,
                    architecture=prepare_architecture,
                    rotation_precision=rotation_precision_value,
                )
            except Exception as exc:
                row = _artifact_row(
                    None,
                    molecule=molecule_text,
                    pf_label=pf_label,
                    qpe_scale=qpe_scale,
                )
                row.update(
                    {
                        "status": "failed",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    }
                )
                rows.append(row)
                continue

            for raw_case in cases:
                if not isinstance(raw_case, Mapping):
                    raise ValueError("each architecture case must be a mapping")
                case_name = str(raw_case.get("name", "case"))
                row = _artifact_row(
                    artifact,
                    molecule=molecule_text,
                    pf_label=pf_label,
                    qpe_scale=qpe_scale,
                )
                if raw_case.get("enabled", True) is False:
                    row.update({"status": "skipped", "case_name": case_name})
                    row.update(
                        {
                            "error_type": "SkippedCase",
                            "error_message": "case is disabled in config",
                        }
                    )
                    rows.append(row)
                    continue

                try:
                    architecture, stock_policy, resolved_stock, topology_name, topology_path = (
                        build_architecture_for_case(config, raw_case, artifact)
                    )
                    row.update(
                        _architecture_row(
                            architecture=architecture,
                            artifact=artifact,
                            case_name=case_name,
                            topology_name=topology_name,
                            topology_path=topology_path,
                            stock_policy=stock_policy,
                            resolved_stock=resolved_stock,
                        )
                    )
                    topology = _topology_config(config, topology_name)
                    if topology.get("enabled", True) is False:
                        row.update(
                            {
                                "status": "skipped",
                                "error_type": "DisabledTopology",
                                "error_message": f"topology is disabled: {topology_name}",
                            }
                        )
                        rows.append(row)
                        continue
                    if _compile_uses_topology(architecture.compile_mode) and not topology_path.exists():
                        row.update(
                            {
                                "status": "skipped",
                                "error_type": "MissingTopology",
                                "error_message": f"topology file not found: {topology_path}",
                            }
                        )
                        rows.append(row)
                        continue

                    metrics = compile_prepared_surface_code_step_artifact(
                        artifact,
                        architecture,
                        reuse_cache=reuse_compile_cache,
                    )
                    compile_info_json = metrics.get("compile_info_json")
                    raw_compile_info: Mapping[str, Any] = {}
                    if compile_info_json is not None:
                        with Path(str(compile_info_json)).open("r", encoding="utf-8") as f:
                            raw_compile_info = json.load(f)
                    row.update(
                        _compile_info_row(
                            raw=raw_compile_info,
                            metrics=metrics,
                            compile_mode=architecture.compile_mode,
                        )
                    )
                    row["compile_cache_hit"] = metrics.get("compile_cache_hit")
                    _add_qpe_total_resource_fields(row)
                    row["status"] = "success"
                except Exception as exc:
                    row.update(
                        {
                            "status": "failed",
                            "error_type": type(exc).__name__,
                            "error_message": str(exc),
                        }
                    )
                    if bool(config.get("debug_traceback", False)):
                        row["error_message"] = row["error_message"] + "\n" + traceback.format_exc()
                rows.append(row)

    output = config.get("output", {})
    if output is None:
        output = {}
    if not isinstance(output, Mapping):
        raise ValueError("output must be a mapping")
    jsonl_path, csv_path, markdown_path = _write_outputs(rows, output)
    return {
        "rows": rows,
        "jsonl_path": str(jsonl_path),
        "csv_path": str(csv_path),
        "markdown_path": str(markdown_path),
        "success_count": sum(1 for row in rows if row.get("status") == "success"),
        "failed_count": sum(1 for row in rows if row.get("status") == "failed"),
        "skipped_count": sum(1 for row in rows if row.get("status") == "skipped"),
    }
