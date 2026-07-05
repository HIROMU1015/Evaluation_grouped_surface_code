from typing import Sequence, Tuple

import numpy as np

from openfermion.ops import QubitOperator

from qiskit import QuantumCircuit
from qiskit.circuit.library import PauliEvolutionGate
from qiskit.quantum_info import SparsePauliOp, Statevector

from .config import PFLabel
from .qiskit_time_evolution_utils import (
    apply_time_evolution,
    _get_w_list,
    term_to_sparse_pauli,
)
from .pf_decomposition import iter_pf_steps


def add_clique_to_circuit_grouper(
    commuting_clique: Sequence[QubitOperator],
    time: float,
    num_qubits: int,
    weight: float,
    circuit: QuantumCircuit,
) -> int:
    """
    可換クリーク中の項を和に束ねて一括で進化ゲートを追加。
    戻り値は、元の「指数項の数」（ゲート数ではなく、物理評価用のカウント）を返す。
    """
    # 係数付きの SparsePauliOp を加算して合成ハミルトニアン H_clique を構築
    clique_hamiltonian: SparsePauliOp | None = None
    exp_term_count = 0
    for hamiltonian in commuting_clique:
        for term, coeff in hamiltonian.terms.items():
            if not term:
                # 恒等項（定数項）は回路には入れない
                continue
            # PauliOp へ変換して加算
            pauli_op = term_to_sparse_pauli(tuple(term), num_qubits)
            pauli_op = coeff.real * pauli_op
            clique_hamiltonian = (
                pauli_op if clique_hamiltonian is None else (clique_hamiltonian + pauli_op)
            )
            exp_term_count += 1
    if clique_hamiltonian is None:
        return 0
    # 以前は各項 angle=coeff*w*t だったが、ここでは H=Σ coeff*P として time=w*t を与える
    evolution_gate = PauliEvolutionGate(
        clique_hamiltonian, time=(weight * time), synthesis=None
    )
    circuit.append(evolution_gate, range(num_qubits))
    return exp_term_count


def _qiskit_circuit_qubit(term_index: int, num_qubits: int) -> int:
    # Match term_to_sparse_pauli: the leftmost SparsePauliOp label maps to the
    # highest-index Qiskit circuit qubit.
    return int(num_qubits) - 1 - int(term_index)


def _apply_pauli_basis_change(
    circuit: QuantumCircuit,
    mapped_term: Sequence[tuple[int, str]],
) -> None:
    for qubit, pauli in mapped_term:
        if pauli == "X":
            circuit.h(qubit)
        elif pauli == "Y":
            circuit.sdg(qubit)
            circuit.h(qubit)
        elif pauli == "Z":
            continue
        else:
            raise ValueError(f"Unsupported Pauli operator: {pauli!r}")


def _undo_pauli_basis_change(
    circuit: QuantumCircuit,
    mapped_term: Sequence[tuple[int, str]],
) -> None:
    for qubit, pauli in reversed(mapped_term):
        if pauli == "X":
            circuit.h(qubit)
        elif pauli == "Y":
            circuit.h(qubit)
            circuit.s(qubit)
        elif pauli == "Z":
            continue
        else:
            raise ValueError(f"Unsupported Pauli operator: {pauli!r}")


def add_clique_to_circuit_efficient_controlled(
    commuting_clique: Sequence[QubitOperator],
    time: float,
    num_qubits: int,
    weight: float,
    circuit: QuantumCircuit,
    control_qubit: int,
) -> int:
    """Append controlled Pauli rotations while keeping Clifford work system-only."""
    exp_term_count = 0
    for hamiltonian in commuting_clique:
        for term, coeff in hamiltonian.terms.items():
            if not term:
                continue
            angle = float(coeff.real) * float(weight) * float(time)
            mapped_term = [
                (_qiskit_circuit_qubit(index, num_qubits), pauli)
                for index, pauli in term
            ]
            active_qubits = [qubit for qubit, _pauli in mapped_term]
            if not active_qubits:
                continue
            target = active_qubits[-1]
            _apply_pauli_basis_change(circuit, mapped_term)
            for qubit in active_qubits[:-1]:
                circuit.cx(qubit, target)
            circuit.crz(2.0 * angle, control_qubit, target)
            for qubit in reversed(active_qubits[:-1]):
                circuit.cx(qubit, target)
            _undo_pauli_basis_change(circuit, mapped_term)
            exp_term_count += 1
    return exp_term_count


def w_trotter_grouper(
    circuit: QuantumCircuit,
    commuting_cliques: Sequence[Sequence[QubitOperator]],
    time: float,
    num_qubits: int,
    pf_label: PFLabel,
) -> int:
    """与えられた w シリーズで PF 分解を回路に追加し、累計項数を返す。"""
    # PF 係数列に従ってクリークを順次追加
    weights = _get_w_list(pf_label)
    exp_term_count = 0
    for term_idx, weight in iter_pf_steps(len(commuting_cliques), weights):
        exp_term_count += add_clique_to_circuit_grouper(
            commuting_cliques[term_idx], time, num_qubits, weight, circuit
        )
    return exp_term_count


def w_trotter_grouper_efficient_controlled(
    circuit: QuantumCircuit,
    commuting_cliques: Sequence[Sequence[QubitOperator]],
    time: float,
    num_qubits: int,
    pf_label: PFLabel,
    control_qubit: int,
) -> int:
    """Append an efficient k=0 controlled PF step.

    Only each Pauli rotation's central RZ is controlled. Basis changes, parity
    compute, and parity uncompute are applied on system qubits only.
    """
    weights = _get_w_list(pf_label)
    exp_term_count = 0
    for term_idx, weight in iter_pf_steps(len(commuting_cliques), weights):
        exp_term_count += add_clique_to_circuit_efficient_controlled(
            commuting_cliques[term_idx],
            time,
            num_qubits,
            weight,
            circuit,
            control_qubit,
        )
    return exp_term_count


def tEvolution_vector_grouper(
    commuting_cliques: Sequence[Sequence[QubitOperator]],
    time: float,
    num_qubits: int,
    state_vec: np.ndarray,
    pf_label: PFLabel,
) -> Tuple[float, Statevector, int]:
    """グルーピング済みハミルトニアンで時間発展回路を合成し、最終状態を返す。"""
    # 回路を構築して時間発展
    evolution_circuit = QuantumCircuit(num_qubits)
    exp_term_count = w_trotter_grouper(
        evolution_circuit, commuting_cliques, time, num_qubits, pf_label
    )
    final_statevector = apply_time_evolution(state_vec, evolution_circuit)
    return time, final_statevector, exp_term_count
