from __future__ import annotations

import json
from pathlib import Path

import pytest

from trotterlib import architecture_sweep as sweep
from trotterlib import surface_code as sc

import scripts.profile_qret_summary_aggregation_memory as profile


def _compile_info_payload(*, include_arrays: bool) -> dict[str, object]:
    payload: dict[str, object] = {
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


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=True, separators=(",", ":")), encoding="utf-8")


def test_summary_parser_preserves_estimated_execution_time(tmp_path: Path) -> None:
    path = tmp_path / "compile_info.json"
    _write_json(path, _compile_info_payload(include_arrays=False))

    metrics = sc.surface_code_step_metrics_from_compile_info_json(path)

    assert metrics["execution_time_sec"] == 1.25
    assert metrics["estimated_execution_time_sec"] == 1.25


def test_generated_metric_names_separate_compile_wall_time() -> None:
    normalized = sc.normalize_surface_code_step_metrics(
        {
            **_compile_info_payload(include_arrays=False),
            "estimated_execution_time_sec": 1.25,
            "compile_wall_time_sec": 9.5,
            "execution_time_sec": 9.5,
        }
    )

    assert normalized["estimated_execution_time_sec"] == 1.25
    assert normalized["compile_wall_time_sec"] == 9.5
    assert normalized["execution_time_sec"] == 9.5


def test_architecture_sweep_prefers_compile_wall_time() -> None:
    row = sweep._compile_info_row(
        raw=_compile_info_payload(include_arrays=False),
        metrics={
            "compile_wall_time_sec": 9.5,
            "execution_time_sec": 1.25,
        },
        compile_mode="ftqc_compile_topology",
    )

    assert row["compile_elapsed_time"] == 9.5
    assert row["compile_elapsed_time_unavailable_reason"] is None


def test_qret_runtime_hashes_include_adjacent_core_library(tmp_path: Path) -> None:
    qret = tmp_path / "qret"
    core = tmp_path / "libqret-core.so.1"
    qret.write_bytes(b"fake qret executable")
    core.write_bytes(b"fake core library")

    hashes = sc.qret_runtime_hashes(qret)

    assert hashes["qret_executable_hash"] == sc.file_sha256(qret)
    assert hashes["qret_core_library_path"] == str(core.resolve())
    assert hashes["qret_core_library_hash"] == sc.file_sha256(core)


def test_compile_cache_key_includes_qret_core_library_hash(tmp_path: Path) -> None:
    qret = tmp_path / "qret"
    core = tmp_path / "libqret-core.so.1"
    qret.write_bytes(b"fake qret executable")
    core.write_bytes(b"core v1")
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
        qret_path=qret,
        qret_hash=sc.file_sha256(qret),
        step_rz_count=0,
        step_rz_layer=None,
        step_magic_state_count=0,
        step_magic_state_depth=0,
        peak_magic_layer=0,
        instruction_count=0,
        gate_depth=0,
        rz_call_cache={},
    )
    arch = sc.SurfaceCodeArchitecture(
        compile_mode="decompose_only",
        qret_path=qret,
        compile_info_output_mode="summary",
    )

    key_v1 = sc.surface_code_compile_cache_key(artifact, arch)
    payload_v1 = sc.surface_code_compile_cache_payload(artifact, arch)
    core.write_bytes(b"core v2")
    key_v2 = sc.surface_code_compile_cache_key(artifact, arch)
    payload_v2 = sc.surface_code_compile_cache_payload(artifact, arch)

    assert payload_v1["qret_hash"] == payload_v2["qret_hash"]
    assert payload_v1["qret_core_library_hash"] != payload_v2["qret_core_library_hash"]
    assert key_v1 != key_v2


def test_profile_hash_stability_detection() -> None:
    before = {
        "qret_executable_hash": "exe",
        "qret_core_library_path": "/tmp/libqret-core.so.1",
        "qret_core_library_hash": "core-v1",
    }
    same = dict(before)
    changed = {**before, "qret_core_library_hash": "core-v2"}

    profile._ensure_runtime_hash_stable(before, same)
    with pytest.raises(RuntimeError, match="qret runtime hash changed"):
        profile._ensure_runtime_hash_stable(before, changed)


def test_profile_raw_resource_metrics_include_qret_execution_time(tmp_path: Path) -> None:
    path = tmp_path / "compile_info.json"
    _write_json(path, _compile_info_payload(include_arrays=False))

    raw = profile._raw_resource_metrics(path)

    assert raw["execution_time_sec"] == 1.25
    assert raw["gate_throughput_ave"] == 2.5


def test_full_and_summary_artifact_compatibility(tmp_path: Path) -> None:
    summary_path = tmp_path / "summary.json"
    full_path = tmp_path / "full.json"
    _write_json(summary_path, _compile_info_payload(include_arrays=False))
    _write_json(full_path, _compile_info_payload(include_arrays=True))

    summary = sc.surface_code_step_metrics_from_compile_info_json(summary_path)
    full = sc.surface_code_step_metrics_from_compile_info_json(full_path)
    summary.pop("compile_info_json")
    full.pop("compile_info_json")

    assert summary == full
