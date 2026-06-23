#!/usr/bin/env python3
from __future__ import annotations

import argparse
import itertools
import json
import re
import shutil
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pyscf
from qiskit import QuantumCircuit
from pyscf import gto, scf

from trotterlib import surface_code as sc
from trotterlib.chemistry_hamiltonian import geo
from trotterlib.config import DEFAULT_BASIS
from trotterlib.qiskit_time_evolution_grouping import w_trotter_grouper
from trotterlib.qiskit_time_evolution_pyscf import _build_grouped_jw_list


HAM_NAME = sc.grouped_hchain_ham_name(4)
PF_LABEL = "4th(new_2)"
DISTANCE = 1.0
GATE_DEF_RE = re.compile(
    r"^gate\s+(?P<name>\w+)\s+\w+\s+\{\s*rz\((?P<theta>.+)\)\s+\w+;\s*\}$"
)


def array_sha256(array: np.ndarray) -> str:
    import hashlib

    return hashlib.sha256(np.asarray(array, dtype=np.float64).tobytes()).hexdigest()


def compact_array_payload(array: np.ndarray, *, include_values: bool = True) -> dict[str, Any]:
    arr = np.asarray(array, dtype=np.float64)
    payload: dict[str, Any] = {
        "shape": list(arr.shape),
        "sha256": array_sha256(arr),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "fro_norm": float(np.linalg.norm(arr.ravel())),
    }
    if include_values:
        payload["values"] = arr.tolist()
    return payload


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=True, indent=2, sort_keys=True)
        f.write("\n")


def run_scf_once() -> dict[str, Any]:
    geometry, multiplicity, charge = geo(4, DISTANCE)
    mol = gto.Mole()
    mol.atom = geometry
    mol.basis = DEFAULT_BASIS
    mol.spin = multiplicity - 1
    mol.charge = charge
    mol.symmetry = False
    mol.build()

    mf = scf.RHF(mol)
    mf.verbose = 0
    mf.kernel()
    s_ao = mf.get_ovlp()
    h_core = mf.get_hcore()
    eri_ao = mf.mol.intor("int2e")
    mo_coeff = np.asarray(mf.mo_coeff, dtype=np.float64)
    one_body, two_body = integrals_from_mo(mf.mol, h_core, mo_coeff)
    return {
        "mol": mol,
        "mf": mf,
        "s_ao": np.asarray(s_ao, dtype=np.float64),
        "h_core": np.asarray(h_core, dtype=np.float64),
        "eri_ao": np.asarray(eri_ao, dtype=np.float64),
        "mo_coeff": mo_coeff,
        "one_body": one_body,
        "two_body": two_body,
    }


def integrals_from_mo(
    mol: Any,
    h_core: np.ndarray,
    mo_coeff: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    one_body = np.asarray(mo_coeff.T @ h_core @ mo_coeff, dtype=np.float64)
    eri_mo = pyscf.ao2mo.kernel(mol, mo_coeff)
    eri_mo = pyscf.ao2mo.restore(1, eri_mo, mo_coeff.shape[0])
    two_body = np.asarray(eri_mo.transpose(0, 2, 3, 1), dtype=np.float64, order="C")
    return one_body, two_body


def phase_normalized_mo(mo_coeff: np.ndarray) -> np.ndarray:
    out = np.array(mo_coeff, dtype=np.float64, copy=True)
    for index in range(out.shape[1]):
        pivot = int(np.argmax(np.abs(out[:, index])))
        if out[pivot, index] < 0:
            out[:, index] *= -1
    return out


def best_signed_permutation_alignment(
    ref_mo: np.ndarray,
    run_mo: np.ndarray,
    s_ao: np.ndarray,
) -> tuple[np.ndarray, dict[str, Any]]:
    overlap = ref_mo.T @ s_ao @ run_mo
    n_cols = overlap.shape[0]
    best_score = -1.0
    best_perm: tuple[int, ...] | None = None
    for perm in itertools.permutations(range(n_cols)):
        score = float(sum(abs(overlap[i, perm[i]]) for i in range(n_cols)))
        if score > best_score:
            best_score = score
            best_perm = tuple(int(item) for item in perm)
    assert best_perm is not None

    aligned = np.zeros_like(run_mo)
    signs: list[int] = []
    for ref_index, run_index in enumerate(best_perm):
        sign = -1 if overlap[ref_index, run_index] < 0 else 1
        signs.append(sign)
        aligned[:, ref_index] = sign * run_mo[:, run_index]
    aligned_overlap = ref_mo.T @ s_ao @ aligned
    return aligned, {
        "permutation_ref_to_run": list(best_perm),
        "signs": signs,
        "score": best_score,
        "aligned_overlap": aligned_overlap.tolist(),
        "max_abs_offdiag_after_alignment": max_abs_offdiag(aligned_overlap),
    }


def full_procrustes_alignment(
    ref_mo: np.ndarray,
    run_mo: np.ndarray,
    s_ao: np.ndarray,
) -> tuple[np.ndarray, dict[str, Any]]:
    overlap = ref_mo.T @ s_ao @ run_mo
    u, singular_values, vt = np.linalg.svd(overlap.T)
    rotation = u @ vt
    aligned = run_mo @ rotation
    aligned_overlap = ref_mo.T @ s_ao @ aligned
    return aligned, {
        "singular_values": singular_values.tolist(),
        "rotation": rotation.tolist(),
        "aligned_overlap": aligned_overlap.tolist(),
        "max_abs_offdiag_after_alignment": max_abs_offdiag(aligned_overlap),
    }


def degenerate_groups(mo_energy: np.ndarray, *, tol: float = 1.0e-10) -> list[list[int]]:
    groups: list[list[int]] = []
    current: list[int] = []
    for index, energy in enumerate(np.asarray(mo_energy, dtype=np.float64)):
        if not current:
            current = [int(index)]
            continue
        previous = float(mo_energy[current[-1]])
        if abs(float(energy) - previous) <= tol:
            current.append(int(index))
        else:
            groups.append(current)
            current = [int(index)]
    if current:
        groups.append(current)
    return groups


def subspace_procrustes_alignment(
    ref_mo: np.ndarray,
    run_mo: np.ndarray,
    s_ao: np.ndarray,
    groups: list[list[int]],
) -> tuple[np.ndarray, dict[str, Any]]:
    aligned = np.array(run_mo, dtype=np.float64, copy=True)
    blocks: list[dict[str, Any]] = []
    for group in groups:
        if len(group) == 1:
            index = group[0]
            sign = -1 if (ref_mo[:, index].T @ s_ao @ aligned[:, index]) < 0 else 1
            aligned[:, index] *= sign
            blocks.append({"indices": group, "type": "phase", "sign": sign})
            continue
        ref_block = ref_mo[:, group]
        run_block = aligned[:, group]
        overlap = ref_block.T @ s_ao @ run_block
        u, singular_values, vt = np.linalg.svd(overlap.T)
        rotation = u @ vt
        aligned[:, group] = run_block @ rotation
        blocks.append(
            {
                "indices": group,
                "type": "procrustes",
                "singular_values": singular_values.tolist(),
                "rotation": rotation.tolist(),
            }
        )
    aligned_overlap = ref_mo.T @ s_ao @ aligned
    return aligned, {
        "groups": groups,
        "blocks": blocks,
        "aligned_overlap": aligned_overlap.tolist(),
        "max_abs_offdiag_after_alignment": max_abs_offdiag(aligned_overlap),
    }


def max_abs_offdiag(matrix: np.ndarray) -> float:
    arr = np.asarray(matrix, dtype=np.float64)
    return float(np.max(np.abs(arr - np.diag(np.diag(arr)))))


def classify_mo_difference(
    ref: Mapping[str, Any],
    run: Mapping[str, Any],
    *,
    energy_tol: float = 1.0e-10,
    overlap_tol: float = 1.0e-8,
) -> dict[str, Any]:
    ref_mo = np.asarray(ref["mo_coeff"], dtype=np.float64)
    run_mo = np.asarray(run["mo_coeff"], dtype=np.float64)
    s_ao = np.asarray(ref["s_ao"], dtype=np.float64)
    overlap = ref_mo.T @ s_ao @ run_mo
    abs_overlap = np.abs(overlap)
    row_best = np.argmax(abs_overlap, axis=1)
    col_best = np.argmax(abs_overlap, axis=0)
    diag = np.diag(overlap)

    sign_flip_indices = [
        int(index)
        for index, value in enumerate(diag)
        if value < -1.0 + overlap_tol
    ]
    identity_like = bool(np.allclose(overlap, np.eye(overlap.shape[0]), atol=overlap_tol))
    signed_identity_like = bool(
        np.allclose(np.abs(overlap), np.eye(overlap.shape[0]), atol=overlap_tol)
    )
    order_swaps = [
        {
            "ref_index": int(index),
            "best_run_index": int(best),
            "overlap": float(overlap[index, best]),
            "abs_overlap": float(abs_overlap[index, best]),
        }
        for index, best in enumerate(row_best)
        if int(best) != int(index) and abs_overlap[index, best] > 1.0 - overlap_tol
    ]
    deg_groups = degenerate_groups(np.asarray(ref["mf_mo_energy"]), tol=energy_tol)
    rotated_groups: list[dict[str, Any]] = []
    for group in deg_groups:
        if len(group) <= 1:
            continue
        block = overlap[np.ix_(group, group)]
        if max_abs_offdiag(block) > overlap_tol:
            rotated_groups.append(
                {
                    "indices": group,
                    "max_abs_offdiag": max_abs_offdiag(block),
                    "block": block.tolist(),
                }
            )

    if sign_flip_indices and not order_swaps and signed_identity_like:
        category = "MO列の符号反転"
    elif order_swaps:
        category = "軌道順序の入れ替わり"
    elif rotated_groups:
        category = "近縮退部分空間内の直交回転"
    elif identity_like:
        category = "それ以外のSCF非決定性"
    else:
        category = "それ以外のSCF非決定性"

    return {
        "category": category,
        "overlap": overlap.tolist(),
        "abs_overlap": abs_overlap.tolist(),
        "diag": diag.tolist(),
        "row_best_run_index": [int(item) for item in row_best],
        "col_best_ref_index": [int(item) for item in col_best],
        "identity_like": identity_like,
        "signed_identity_like": signed_identity_like,
        "sign_flip_count": int(len(sign_flip_indices)),
        "sign_flip_indices": sign_flip_indices,
        "order_swap_count": int(len(order_swaps)),
        "order_swaps": order_swaps,
        "degenerate_groups": deg_groups,
        "rotated_degenerate_group_count": int(len(rotated_groups)),
        "rotated_degenerate_groups": rotated_groups,
        "max_abs_offdiag": max_abs_offdiag(overlap),
        "max_abs_diag_deviation_from_one": float(np.max(np.abs(np.abs(diag) - 1.0))),
        "max_abs_mo_coeff_delta": float(np.max(np.abs(ref_mo - run_mo))),
        "max_abs_one_body_delta": float(
            np.max(np.abs(np.asarray(ref["one_body"]) - np.asarray(run["one_body"])))
        ),
        "max_abs_two_body_delta": float(
            np.max(np.abs(np.asarray(ref["two_body"]) - np.asarray(run["two_body"])))
        ),
    }


def build_circuit_from_integrals(one_body: np.ndarray, two_body: np.ndarray) -> QuantumCircuit:
    commuting_cliques = _build_grouped_jw_list(
        float(0.0),
        np.asarray(one_body, dtype=np.float64),
        np.asarray(two_body, dtype=np.float64),
    )
    num_qubits = int(2 * np.asarray(one_body).shape[0])
    qc = QuantumCircuit(num_qubits)
    step_time = sc.surface_code_step_time(HAM_NAME, PF_LABEL)
    w_trotter_grouper(qc, commuting_cliques, step_time, num_qubits, PF_LABEL)
    qc.global_phase = 0.0
    return qc


def qasm_and_helpers_from_integrals(
    *,
    label: str,
    run_index: int,
    one_body: np.ndarray,
    two_body: np.ndarray,
    output_root: Path,
) -> dict[str, Any]:
    runtime_root = output_root / label / f"run_{run_index}"
    runtime_root.mkdir(parents=True, exist_ok=True)
    qc = build_circuit_from_integrals(one_body, two_body)
    qc_basis = sc._basis_circuit(qc, runtime_root=runtime_root)
    qasm_text = sc._qasm2_text(qc_basis)
    rewritten_qasm, rz_metadata = sc._rewrite_qasm_rz_as_calls(qasm_text)
    qasm_path = runtime_root / "step.qasm"
    qasm_path.write_text(rewritten_qasm, encoding="utf-8")
    ir_path = runtime_root / "step_ir.json"
    qret_path = Path(sc.SurfaceCodeArchitecture().qret_path).expanduser().resolve()
    sc._run_qret(
        [
            str(qret_path),
            "parse",
            "--input",
            str(qasm_path),
            "--output",
            str(ir_path),
            "--format",
            "OpenQASM2",
            "--verbose",
        ],
        runtime_root=runtime_root,
        rotation_precision=sc.SURFACE_CODE_ROTATION_PRECISION_FLOOR,
        stage_recorder=None,
    )
    sc._rewrite_ir_rotation_precision(
        ir_path,
        rotation_precision=sc.SURFACE_CODE_ROTATION_PRECISION_FLOOR,
    )
    helpers = [dict(item) for item in rz_metadata.get("helpers", [])]
    helper_hashes = helper_input_hashes(ir_path, helpers)
    theta_occurrences = extract_rewritten_qasm_rz_occurrences_from_text(rewritten_qasm)
    return {
        "label": label,
        "run_index": int(run_index),
        "runtime_root": str(runtime_root),
        "qasm_path": str(qasm_path),
        "ir_path": str(ir_path),
        "qasm_sha256": sc.file_sha256(qasm_path),
        "ir_sha256": sc.file_sha256(ir_path),
        "rz_occurrence_thetas": theta_occurrences,
        "rz_occurrence_count": int(len(theta_occurrences)),
        "rz_occurrence_sha256": string_list_sha256(theta_occurrences),
        "unique_theta_count": int(len({str(item) for item in theta_occurrences})),
        "unique_theta_set_sha256": string_list_sha256(sorted({str(item) for item in theta_occurrences})),
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
        "helper_normalized_hashes": [
            item["normalized_single_ir_hash"] for item in helper_hashes
        ],
        "helper_normalized_hash_set_sha256": string_list_sha256(
            sorted(item["normalized_single_ir_hash"] for item in helper_hashes)
        ),
    }


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
                "normalized_single_ir_hash": sc._canonical_json_hash(normalized_value),
            }
        )
    return out


def extract_rewritten_qasm_rz_occurrences_from_text(qasm_text: str) -> list[str]:
    lines = str(qasm_text).splitlines()
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


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def string_list_sha256(values: Iterable[str]) -> str:
    import hashlib

    digest = hashlib.sha256()
    for value in values:
        digest.update(str(value).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def compare_condition_outputs(outputs: list[dict[str, Any]]) -> dict[str, Any]:
    qasm_hashes = [item["qasm_sha256"] for item in outputs]
    rz_hashes = [item["rz_occurrence_sha256"] for item in outputs]
    unique_hashes = [item["unique_theta_set_sha256"] for item in outputs]
    helper_hashes = [item["helper_normalized_hash_set_sha256"] for item in outputs]
    base_thetas = outputs[0]["rz_occurrence_thetas"]
    pairwise: list[dict[str, Any]] = []
    for item in outputs[1:]:
        other_thetas = item["rz_occurrence_thetas"]
        diff_examples: list[dict[str, Any]] = []
        numeric_diff_count = 0
        max_abs_diff = 0.0
        for index, (a, b) in enumerate(zip(base_thetas, other_thetas)):
            va = sc._eval_qasm_angle(a)
            vb = sc._eval_qasm_angle(b)
            abs_diff = abs(float(va) - float(vb))
            if str(a) != str(b):
                numeric_diff_count += int(va != vb)
                if len(diff_examples) < 8:
                    diff_examples.append(
                        {
                            "index": int(index),
                            "theta_ref": a,
                            "theta_run": b,
                            "value_ref": float(va),
                            "value_run": float(vb),
                            "abs_diff": abs_diff,
                        }
                    )
            max_abs_diff = max(max_abs_diff, abs_diff)
        pairwise.append(
            {
                "run_index": int(item["run_index"]),
                "qasm_equal": outputs[0]["qasm_sha256"] == item["qasm_sha256"],
                "rz_occurrence_equal": base_thetas == other_thetas,
                "unique_theta_set_equal": set(base_thetas) == set(other_thetas),
                "helper_hash_set_equal": Counter(outputs[0]["helper_normalized_hashes"])
                == Counter(item["helper_normalized_hashes"]),
                "numeric_diff_count": int(numeric_diff_count),
                "max_abs_diff": max_abs_diff,
                "first_differences": diff_examples,
            }
        )
    return {
        "qasm_hashes": qasm_hashes,
        "rz_occurrence_hashes": rz_hashes,
        "unique_theta_set_hashes": unique_hashes,
        "helper_hash_set_hashes": helper_hashes,
        "qasm_all_equal": len(set(qasm_hashes)) == 1,
        "rz_occurrence_all_equal": len(set(rz_hashes)) == 1,
        "unique_theta_set_all_equal": len(set(unique_hashes)) == 1,
        "helper_input_hash_set_all_equal": len(set(helper_hashes)) == 1,
        "helper_counts": [item["helper_count"] for item in outputs],
        "unique_theta_counts": [item["unique_theta_count"] for item in outputs],
        "pairwise_against_run_1": pairwise,
    }


def summarize_scf_run(run: Mapping[str, Any], *, include_values: bool) -> dict[str, Any]:
    mf = run["mf"]
    return {
        "mf_e_tot": float(mf.e_tot),
        "mf_mo_energy": compact_array_payload(mf.mo_energy, include_values=True),
        "mf_mo_occ": compact_array_payload(mf.mo_occ, include_values=True),
        "S": compact_array_payload(run["s_ao"], include_values=include_values),
        "mo_coeff": compact_array_payload(run["mo_coeff"], include_values=include_values),
        "one_body": compact_array_payload(run["one_body"], include_values=include_values),
        "two_body": compact_array_payload(run["two_body"], include_values=include_values),
    }


def run_investigation(output_path: Path, cache_base: Path) -> dict[str, Any]:
    if cache_base.exists():
        shutil.rmtree(cache_base)
    cache_base.mkdir(parents=True, exist_ok=True)

    scf_runs: list[dict[str, Any]] = []
    for _index in range(3):
        scf_runs.append(run_scf_once())

    ref = scf_runs[0]
    groups = degenerate_groups(ref["mf"].mo_energy)
    classifications = [
        classify_mo_difference(
            {
                "mo_coeff": ref["mo_coeff"],
                "s_ao": ref["s_ao"],
                "mf_mo_energy": ref["mf"].mo_energy,
                "one_body": ref["one_body"],
                "two_body": ref["two_body"],
            },
            {
                "mo_coeff": run["mo_coeff"],
                "one_body": run["one_body"],
                "two_body": run["two_body"],
            },
        )
        for run in scf_runs
    ]

    condition_mos: dict[str, list[np.ndarray]] = {
        "raw": [run["mo_coeff"] for run in scf_runs],
        "phase_normalized": [phase_normalized_mo(run["mo_coeff"]) for run in scf_runs],
    }
    signed_permutation_metadata: list[dict[str, Any]] = []
    signed_permutation_mos: list[np.ndarray] = []
    full_procrustes_metadata: list[dict[str, Any]] = []
    full_procrustes_mos: list[np.ndarray] = []
    subspace_procrustes_metadata: list[dict[str, Any]] = []
    subspace_procrustes_mos: list[np.ndarray] = []

    for run in scf_runs:
        aligned, metadata = best_signed_permutation_alignment(
            ref["mo_coeff"], run["mo_coeff"], ref["s_ao"]
        )
        signed_permutation_mos.append(aligned)
        signed_permutation_metadata.append(metadata)
        aligned, metadata = full_procrustes_alignment(
            ref["mo_coeff"], run["mo_coeff"], ref["s_ao"]
        )
        full_procrustes_mos.append(aligned)
        full_procrustes_metadata.append(metadata)
        aligned, metadata = subspace_procrustes_alignment(
            ref["mo_coeff"], run["mo_coeff"], ref["s_ao"], groups
        )
        subspace_procrustes_mos.append(aligned)
        subspace_procrustes_metadata.append(metadata)

    condition_mos["signed_permutation_alignment"] = signed_permutation_mos
    condition_mos["degenerate_subspace_procrustes"] = subspace_procrustes_mos
    condition_mos["full_procrustes_alignment"] = full_procrustes_mos
    condition_mos["reference_mo_cache_control"] = [
        np.array(ref["mo_coeff"], copy=True) for _run in scf_runs
    ]

    conditions: dict[str, list[dict[str, Any]]] = {}
    for condition, mos in condition_mos.items():
        outputs: list[dict[str, Any]] = []
        for run_index, (run, mo_coeff) in enumerate(zip(scf_runs, mos), start=1):
            one_body, two_body = integrals_from_mo(run["mol"], run["h_core"], mo_coeff)
            outputs.append(
                qasm_and_helpers_from_integrals(
                    label=condition,
                    run_index=run_index,
                    one_body=one_body,
                    two_body=two_body,
                    output_root=cache_base,
                )
            )
        conditions[condition] = outputs
        write_json(
            output_path,
            {
                "status": "running",
                "completed_condition": condition,
                "condition_comparisons": {
                    key: compare_condition_outputs(value)
                    for key, value in conditions.items()
                },
            },
        )

    condition_comparisons = {
        condition: compare_condition_outputs(outputs)
        for condition, outputs in conditions.items()
    }
    category_counts = Counter(item["category"] for item in classifications[1:])
    recommended_policy = (
        "deterministic_mo_canonicalization"
        if condition_comparisons["phase_normalized"]["qasm_all_equal"]
        or condition_comparisons["signed_permutation_alignment"]["qasm_all_equal"]
        or condition_comparisons["degenerate_subspace_procrustes"]["qasm_all_equal"]
        else "integral_cache"
    )
    summary = {
        "status": "ok",
        "ham_name": HAM_NAME,
        "pf_label": PF_LABEL,
        "cache_base": str(cache_base),
        "scf_runs": [
            summarize_scf_run(run, include_values=True)
            for run in scf_runs
        ],
        "mo_overlap_classification_against_run_1": classifications,
        "classification_counts_excluding_run_1": dict(category_counts),
        "sign_flip_count_excluding_run_1": int(
            sum(item["sign_flip_count"] for item in classifications[1:])
        ),
        "order_swap_count_excluding_run_1": int(
            sum(item["order_swap_count"] for item in classifications[1:])
        ),
        "rotated_degenerate_group_count_excluding_run_1": int(
            sum(item["rotated_degenerate_group_count"] for item in classifications[1:])
        ),
        "degenerate_groups": groups,
        "alignment_metadata": {
            "signed_permutation_alignment": signed_permutation_metadata,
            "degenerate_subspace_procrustes": subspace_procrustes_metadata,
            "full_procrustes_alignment": full_procrustes_metadata,
        },
        "condition_outputs": conditions,
        "condition_comparisons": condition_comparisons,
        "recommended_next_policy": recommended_policy,
        "notes": {
            "reference_mo_cache_control": (
                "Uses run 1 mo_coeff for all three runs; this simulates an integral/MO cache "
                "and is a control, not a production change."
            ),
            "full_procrustes_alignment": (
                "Allowed to mix all MOs for diagnosis. It is not a physically conservative "
                "canonicalization when applied across non-degenerate orbitals."
            ),
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
            "h4_mo_stability_summary.json"
        ),
    )
    parser.add_argument(
        "--cache-base",
        type=Path,
        default=Path("artifacts/surface_code_cache/h4_mo_stability"),
    )
    args = parser.parse_args()
    started = time.perf_counter()
    summary = run_investigation(args.output.resolve(), args.cache_base.resolve())
    elapsed = time.perf_counter() - started
    print(json.dumps(summary["classification_counts_excluding_run_1"], indent=2, sort_keys=True))
    print(json.dumps(summary["condition_comparisons"], indent=2, sort_keys=True))
    print(f"recommended_next_policy: {summary['recommended_next_policy']}")
    print(f"elapsed_seconds: {elapsed:.3f}")
    print(f"summary: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
