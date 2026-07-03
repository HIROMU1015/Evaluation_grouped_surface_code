from __future__ import annotations

import os
import subprocess
import sys

from trotterlib import surface_code as sc


def test_h2_basis_decompose_reps4_matches_reps8_qasm(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "SURFACE_CODE_CACHE_DIR", tmp_path / "cache")
    ham_name = sc.grouped_hchain_ham_name(2)
    pf_label = "4th(new_2)"
    step_time = sc.surface_code_step_time(ham_name, pf_label)
    qc = sc.build_grouped_surface_code_step_circuit(
        ham_name,
        pf_label,
        step_time=step_time,
    )

    outputs: dict[int, str] = {}
    for reps in (4, 8):
        monkeypatch.setattr(sc, "SURFACE_CODE_QASM_DECOMPOSE_REPS", reps)
        basis = sc._basis_circuit(qc, runtime_root=tmp_path / f"basis_reps_{reps}")
        outputs[reps] = sc._qasm2_text(basis)

    assert outputs[4] == outputs[8]


def test_qasm_decompose_reps_env_override():
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    env["SURFACE_CODE_QASM_DECOMPOSE_REPS"] = "8"
    output = subprocess.check_output(
        [
            sys.executable,
            "-c",
            "from trotterlib import surface_code as sc; "
            "print(sc.SURFACE_CODE_QASM_DECOMPOSE_REPS)",
        ],
        env=env,
        text=True,
    ).strip()

    assert output == "8"


def test_basis_decomposition_profile_rejects_h6(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/profile_basis_decomposition_reps.py",
            "--output-root",
            str(tmp_path / "profile"),
            "--cases",
            "H6",
            "--reps",
            "4",
            "--runs",
            "1",
        ],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode != 0
    assert "limited to H5 or smaller" in proc.stderr
