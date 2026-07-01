from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from qiskit.quantum_info import Operator

from trotterlib import architecture_sweep as sweep
from trotterlib import surface_code as sc


def _h2_integrals() -> tuple[Any, Any, Any]:
    resolved = sc._resolve_surface_code_integrals(2, distance=1.0)
    return resolved.constant, resolved.one_body, resolved.two_body


def _control_block(matrix: np.ndarray, *, num_qubits: int, control: int, row: int, col: int) -> np.ndarray:
    rows = [idx for idx in range(2**num_qubits) if ((idx >> control) & 1) == row]
    cols = [idx for idx in range(2**num_qubits) if ((idx >> control) & 1) == col]
    return matrix[np.ix_(rows, cols)]


def _assert_same_matrix(actual: np.ndarray, expected: np.ndarray, *, atol: float = 1.0e-8) -> None:
    assert actual.shape == expected.shape
    assert np.allclose(actual, expected, atol=atol)


def test_existing_step_circuit_default_is_uncontrolled() -> None:
    ham = sc.grouped_hchain_ham_name(2)
    step_time = sc.surface_code_step_time(ham, "2nd")
    uncontrolled = sc.build_grouped_surface_code_step_circuit(
        ham,
        "2nd",
        step_time=step_time,
    )

    assert uncontrolled.num_qubits == 4
    with pytest.raises(ValueError, match="qpe_power_k is only valid"):
        sc.build_grouped_surface_code_step_circuit(
            ham,
            "2nd",
            step_time=step_time,
            qpe_power_k=0,
        )


def test_controlled_block_qubit_count_and_basis_decomposition(tmp_path: Path) -> None:
    ham = sc.grouped_hchain_ham_name(2)
    step_time = sc.surface_code_step_time(ham, "2nd")
    uncontrolled = sc.build_grouped_surface_code_step_circuit(
        ham,
        "2nd",
        step_time=step_time,
    )
    controlled = sc.build_grouped_surface_code_controlled_block_circuit(
        ham,
        "2nd",
        step_time=step_time,
        qpe_power_k=0,
    )
    basis = sc._basis_circuit(controlled, runtime_root=tmp_path)

    assert controlled.num_qubits == uncontrolled.num_qubits + 1
    assert basis.num_qubits == uncontrolled.num_qubits + 1
    assert {inst.operation.name for inst in basis.data} <= set(sc.SURFACE_CODE_QASM_BASIS_GATES)


@pytest.mark.parametrize("qpe_power_k", [0, 1])
def test_controlled_block_unitary_branches_include_identity_phase(qpe_power_k: int) -> None:
    ham = sc.grouped_hchain_ham_name(2)
    base_step_time = sc.surface_code_step_time(ham, "2nd")
    constant, one_body, two_body = _h2_integrals()
    controlled, metadata = sc._build_grouped_surface_code_controlled_block_circuit_from_integrals(
        ham,
        "2nd",
        base_step_time=base_step_time,
        qpe_power_k=qpe_power_k,
        constant=constant,
        one_body=one_body,
        two_body=two_body,
    )
    system = sc._build_grouped_surface_code_step_circuit_from_integrals(
        ham,
        "2nd",
        step_time=float(metadata["effective_evolution_time"]),
        constant=constant,
        one_body=one_body,
        two_body=two_body,
    )

    matrix = Operator(controlled).data
    num_qubits = int(metadata["num_logical_qubits"])
    control = int(metadata["control_qubit_index"])
    control0 = _control_block(matrix, num_qubits=num_qubits, control=control, row=0, col=0)
    control1 = _control_block(matrix, num_qubits=num_qubits, control=control, row=1, col=1)
    off01 = _control_block(matrix, num_qubits=num_qubits, control=control, row=0, col=1)
    off10 = _control_block(matrix, num_qubits=num_qubits, control=control, row=1, col=0)

    system_matrix = Operator(system).data
    identity_phase = complex(np.exp(1j * float(metadata["identity_phase_angle"])))
    _assert_same_matrix(control0, np.eye(system_matrix.shape[0]))
    _assert_same_matrix(control1, identity_phase * system_matrix)
    _assert_same_matrix(off01, np.zeros_like(off01))
    _assert_same_matrix(off10, np.zeros_like(off10))

    assert not np.allclose(control1, system_matrix, atol=1.0e-8)


def test_qpe_power_k_uses_scaled_time_not_repeated_steps() -> None:
    ham = sc.grouped_hchain_ham_name(2)
    step_time = sc.surface_code_step_time(ham, "2nd")
    constant, one_body, two_body = _h2_integrals()

    controlled, metadata = sc._build_grouped_surface_code_controlled_block_circuit_from_integrals(
        ham,
        "2nd",
        base_step_time=step_time,
        qpe_power_k=1,
        constant=constant,
        one_body=one_body,
        two_body=two_body,
    )

    assert metadata["base_step_time"] == pytest.approx(step_time)
    assert metadata["time_multiplier"] == 2
    assert metadata["effective_evolution_time"] == pytest.approx(2.0 * step_time)
    assert sum(1 for inst in controlled.data if inst.operation.name.startswith("c")) == 1


def test_controlled_scope_validation() -> None:
    with pytest.raises(ValueError, match="integer >= 0"):
        sc._circuit_scope_spec(sc.CONTROLLED_PF_TIME_EVOLUTION_BLOCK_SCOPE, qpe_power_k=-1)
    with pytest.raises(ValueError, match="integer >= 0"):
        sc._circuit_scope_spec(sc.CONTROLLED_PF_TIME_EVOLUTION_BLOCK_SCOPE, qpe_power_k=1.5)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="only valid"):
        sc._circuit_scope_spec(sc.UNCONTROLLED_PF_ONE_STEP_SCOPE, qpe_power_k=0)
    with pytest.raises(ValueError, match="Unknown compiled_circuit_scope"):
        sc._circuit_scope_spec("unknown_scope")


def test_step_artifact_cache_key_separates_scope_and_k() -> None:
    base = {
        "ham_name": sc.grouped_hchain_ham_name(2),
        "pf_label": "2nd",
        "target_error": sc.TARGET_ERROR,
        "step_time": 0.125,
        "rotation_precision": 1.0e-8,
        "qret_hash": "qret",
        "qret_core_library_hash": "core",
        "integral_cache_enabled": True,
        "integral_cache_schema_version": sc._SURFACE_CODE_INTEGRAL_CACHE_VERSION,
        "integral_cache_key": "integrals",
        "integral_value_hash": "values",
    }
    uncontrolled = sc._step_artifact_cache_key(**base)
    controlled_k0 = sc._step_artifact_cache_key(
        **base,
        compiled_circuit_scope=sc.CONTROLLED_PF_TIME_EVOLUTION_BLOCK_SCOPE,
        qpe_power_k=0,
        time_multiplier=1,
        effective_evolution_time=0.125,
        num_control_qubits=1,
    )
    controlled_k1 = sc._step_artifact_cache_key(
        **base,
        compiled_circuit_scope=sc.CONTROLLED_PF_TIME_EVOLUTION_BLOCK_SCOPE,
        qpe_power_k=1,
        time_multiplier=2,
        effective_evolution_time=0.25,
        num_control_qubits=1,
    )

    assert uncontrolled != controlled_k0
    assert controlled_k0 != controlled_k1
    assert controlled_k0 == sc._step_artifact_cache_key(
        **base,
        compiled_circuit_scope=sc.CONTROLLED_PF_TIME_EVOLUTION_BLOCK_SCOPE,
        qpe_power_k=0,
        time_multiplier=1,
        effective_evolution_time=0.125,
        num_control_qubits=1,
    )


def test_architecture_sweep_controlled_rows_do_not_qpe_scale() -> None:
    row = {
        "compiled_circuit_scope": sc.CONTROLLED_PF_TIME_EVOLUTION_BLOCK_SCOPE,
        "step_magic_state_count": 10,
        "step_magic_state_depth": 4,
        "runtime_without_topology": 100,
        "runtime_with_topology": 120,
        "runtime_difference_vs_topology_free": 20,
        "qubit_volume": 500,
    }
    sweep._add_qpe_total_resource_fields(row)

    assert row["qpe_action_count"] is None
    assert row["total_magic_state_count"] is None
    assert row["total_runtime_with_topology"] is None
    assert row["total_runtime_with_topology_unavailable_reason"] == "single_controlled_block_not_qpe_total"


def test_h2_controlled_qret_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    qret_path = Path("build/quration/qret").resolve()
    if not qret_path.exists():
        pytest.skip("qret binary is not built")

    monkeypatch.setattr(sc, "SURFACE_CODE_CACHE_DIR", tmp_path / "cache")
    architecture = sc.SurfaceCodeArchitecture(
        compile_mode="ftqc_compile",
        qret_path=qret_path,
        skip_compile_output=True,
        compile_info_output_mode="summary",
    )

    metrics = sc.compile_grouped_hchain_controlled_block(
        2,
        "2nd",
        0,
        architecture=architecture,
    )

    assert metrics["compiled_circuit_scope"] == sc.CONTROLLED_PF_TIME_EVOLUTION_BLOCK_SCOPE
    assert metrics["qpe_power_k"] == 0
    assert metrics["num_control_qubits"] == 1
    assert Path(metrics["compile_info_json"]).exists()
