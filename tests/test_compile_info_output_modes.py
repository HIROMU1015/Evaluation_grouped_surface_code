from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from trotterlib import surface_code as sc


def _compile_info_payload(*, include_arrays: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "runtime": 11,
        "runtime_without_topology": 7,
        "gate_count": 5,
        "gate_count_detail": {"HADAMARD": 2, "LATTICE_SURGERY": 3},
        "gate_depth": 4,
        "gate_throughput_ave": 2.5,
        "gate_throughput_peak": 5,
        "measurement_feedback_count": 3,
        "measurement_feedback_depth": 2,
        "measurement_feedback_rate_ave": 1.5,
        "measurement_feedback_rate_peak": 3,
        "magic_state_consumption_count": 6,
        "magic_state_consumption_depth": 4,
        "magic_state_consumption_rate_ave": 2.0,
        "magic_state_consumption_rate_peak": 4,
        "entanglement_consumption_count": 0,
        "entanglement_consumption_depth": 0,
        "entanglement_consumption_rate_ave": 0.0,
        "entanglement_consumption_rate_peak": 0,
        "magic_factory_count": 4,
        "entanglement_factory_count": 0,
        "chip_cell_count": 96,
        "chip_cell_algorithmic_qubit_ave": 8.0,
        "chip_cell_algorithmic_qubit_peak": 10,
        "chip_cell_algorithmic_qubit_ratio_ave": 0.25,
        "chip_cell_algorithmic_qubit_ratio_peak": 0.5,
        "chip_cell_active_qubit_area_ave": 12.0,
        "chip_cell_active_qubit_area_peak": 16,
        "chip_cell_active_qubit_area_ratio_ave": 0.375,
        "chip_cell_active_qubit_area_ratio_peak": 0.75,
        "qubit_volume": 123,
        "code_distance": 5,
        "execution_time_sec": 1.25,
        "num_physical_qubits": 200,
    }
    if include_arrays:
        payload.update(
            {
                "gate_throughput": [0, 5],
                "measurement_feedback_rate": [0, 3],
                "magic_state_consumption_rate": [0, 4],
                "entanglement_consumption_rate": [0, 0],
                "chip_cell_algorithmic_qubit": [6, 10],
                "chip_cell_algorithmic_qubit_ratio": [0.0, 0.5],
                "chip_cell_active_qubit_area": [8, 16],
                "chip_cell_active_qubit_area_ratio": [0.0, 0.75],
            }
        )
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":")),
        encoding="utf-8",
    )


def test_compile_info_output_mode_normalization() -> None:
    assert sc.SurfaceCodeArchitecture().compile_info_output_mode == "summary"
    assert sc.SurfaceCodeArchitecture(compile_info_output_mode="full").compile_info_output_mode == "full"
    assert (
        sc.SurfaceCodeArchitecture(compile_info_output_mode="summary").compile_info_output_mode
        == "summary"
    )
    with pytest.raises(ValueError, match="compile_info_output_mode"):
        sc.SurfaceCodeArchitecture(compile_info_output_mode="compact")


def test_compile_pipeline_yaml_sets_compile_info_output_mode(tmp_path: Path) -> None:
    opt_path = tmp_path / "step_opt.json"
    compile_output_path = tmp_path / "step_sc_ls_fixed_v0.json"
    compile_info_path = tmp_path / "compile_info.json"
    topology_path = tmp_path / "topology.yaml"

    summary_yaml = sc.compile_pipeline_yaml(
        opt_path=opt_path,
        compile_output_path=compile_output_path,
        compile_info_path=compile_info_path,
        architecture=sc.SurfaceCodeArchitecture(topology_path=topology_path),
    )
    full_yaml = sc.compile_pipeline_yaml(
        opt_path=opt_path,
        compile_output_path=compile_output_path,
        compile_info_path=compile_info_path,
        architecture=sc.SurfaceCodeArchitecture(
            topology_path=topology_path,
            compile_info_output_mode="full",
        ),
    )

    assert "sc_ls_fixed_v0_compile_info_output_mode: summary" in summary_yaml
    assert "sc_ls_fixed_v0_compile_info_output_mode: full" in full_yaml


def test_compile_cache_key_separates_compile_info_output_mode(tmp_path: Path) -> None:
    qret_path = tmp_path / "fake_qret"
    qret_path.write_text("#!/bin/sh\n", encoding="utf-8")
    artifact = sc.SurfaceCodeStepArtifact(
        ham_name="H2_sto-3g_singlet_distance_100_charge_0_grouping",
        molecule="H2",
        num_logical_qubits=4,
        pf_label="2nd",
        target_error=1.0e-4,
        step_time=1.0,
        rotation_precision=1.0e-5,
        runtime_root=tmp_path,
        qasm_path=tmp_path / "step.qasm",
        ir_path=tmp_path / "step_ir.json",
        optimized_ir_path=tmp_path / "step_opt.json",
        qasm_hash="qasm",
        optimized_ir_hash="opt",
        qret_path=qret_path,
        qret_hash=sc.file_sha256(qret_path),
        step_rz_count=0,
        step_rz_layer=None,
        step_magic_state_count=0,
        step_magic_state_depth=0,
        peak_magic_layer=0,
        instruction_count=0,
        gate_depth=0,
        rz_call_cache={},
    )
    summary_arch = sc.SurfaceCodeArchitecture(
        compile_mode="decompose_only",
        qret_path=qret_path,
        compile_info_output_mode="summary",
    )
    full_arch = sc.SurfaceCodeArchitecture(
        compile_mode="decompose_only",
        qret_path=qret_path,
        compile_info_output_mode="full",
    )

    assert (
        sc.surface_code_compile_cache_payload(artifact, summary_arch)[
            "compile_info_output_mode"
        ]
        == "summary"
    )
    assert sc.surface_code_compile_cache_payload(artifact, full_arch)[
        "compile_info_output_mode"
    ] == "full"
    assert sc.surface_code_compile_cache_key(
        artifact,
        summary_arch,
    ) != sc.surface_code_compile_cache_key(
        artifact,
        full_arch,
    )


def test_summary_compile_info_parser_and_full_parser_match(tmp_path: Path) -> None:
    summary_path = tmp_path / "summary_compile_info.json"
    full_path = tmp_path / "full_compile_info.json"
    _write_json(summary_path, _compile_info_payload(include_arrays=False))
    _write_json(full_path, _compile_info_payload(include_arrays=True))

    summary_metrics = sc.surface_code_step_metrics_from_compile_info_json(summary_path)
    full_metrics = sc.surface_code_step_metrics_from_compile_info_json(full_path)
    summary_metrics.pop("compile_info_json")
    full_metrics.pop("compile_info_json")

    assert summary_metrics == full_metrics
    assert summary_metrics["gate_count_dict"] == {"HADAMARD": 2, "LATTICE_SURGERY": 3}
    assert summary_metrics["gate_throughput_ave"] == 2.5
    assert summary_metrics["chip_cell_active_qubit_area_ratio_peak"] == 0.75


def test_metric_field_extraction_reads_summary_without_arrays(tmp_path: Path) -> None:
    summary_path = tmp_path / "summary_compile_info.json"
    _write_json(summary_path, _compile_info_payload(include_arrays=False))

    metrics, field_count, mode = sc._load_compile_info_metrics_json(
        summary_path,
        extraction_mode="top_level_metric_fields",
    )

    assert mode == "top_level_metric_fields"
    assert field_count == len(_compile_info_payload(include_arrays=False))
    assert "gate_throughput" not in metrics
    assert metrics["gate_throughput_ave"] == 2.5
    assert metrics["gate_count_detail"] == {"HADAMARD": 2, "LATTICE_SURGERY": 3}
    normalized = sc.normalize_surface_code_step_metrics(metrics)
    assert normalized["magic_state_consumption_count"] == 6
    assert normalized["measurement_feedback_rate_peak"] == 3
