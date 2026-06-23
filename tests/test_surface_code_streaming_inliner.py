from __future__ import annotations

import json
import multiprocessing as mp
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from trotterlib import surface_code as sc


def _fixture_ir() -> dict[str, Any]:
    return {
        "format": "quration-ir-test",
        "circuit_list": [
            {
                "name": "main",
                "argument": {"num_qubits": 3},
                "bb_list": [
                    {
                        "name": "entry",
                        "inst_list": [
                            {"opcode": "H", "q": 0},
                            {"opcode": "Call", "callee": "helper", "operate": [2, 0]},
                            {"opcode": "CX", "q0": 0, "q1": 2},
                            {"opcode": "Return"},
                        ],
                    }
                ],
            },
            {
                "name": "helper",
                "argument": {"num_qubits": 2},
                "bb_list": [
                    {
                        "name": "entry",
                        "inst_list": [
                            {"opcode": "T", "q": 0},
                            {"opcode": "Call", "callee": "nested", "operate": [1]},
                            {"opcode": "TDag", "q": 1},
                            {"opcode": "Return"},
                        ],
                    }
                ],
            },
            {
                "name": "nested",
                "argument": {"num_qubits": 1},
                "bb_list": [
                    {
                        "name": "entry",
                        "inst_list": [
                            {"opcode": "S", "q": 0},
                            {"opcode": "X", "q": 0},
                            {"opcode": "Return"},
                        ],
                    }
                ],
            },
        ],
    }


def _rz_helper_cache_fixture_ir(function_name: str = "__helper()") -> dict[str, Any]:
    return {
        "metadata": {"format": "test", "created_at": "first"},
        "name": "fixture",
        "circuit_list": [
            {
                "name": function_name,
                "entry_point": "entry",
                "argument": {
                    "num_qubits": 1,
                    "qubits": {"arg": 1},
                    "num_registers": 0,
                },
                "num_tmp_registers": 0,
                "bb_list": [
                    {
                        "name": "entry",
                        "inst_list": [
                            {
                                "opcode": "RZ",
                                "q": 0,
                                "theta": {"value": 0.125, "precision": 1.0e-5},
                            },
                            {"opcode": "Return"},
                        ],
                    }
                ],
            }
        ],
    }


def _rz_helper_fixture_metadata(function_name: str = "__helper()") -> dict[str, str]:
    return {
        "function_name": function_name,
        "theta": "0.125",
        "key": "0.125",
    }


def _rz_helper_e2e_fixture_ir() -> dict[str, Any]:
    return {
        "metadata": {"format": "test", "created_at": "first"},
        "name": "fixture",
        "circuit_list": [
            {
                "name": "main",
                "entry_point": "entry",
                "argument": {"num_qubits": 2, "qubits": {"arg": 2}},
                "num_tmp_registers": 0,
                "bb_list": [
                    {
                        "name": "entry",
                        "inst_list": [
                            {"opcode": "H", "q": 0},
                            {
                                "opcode": "Call",
                                "callee": "__helper()",
                                "operate": [1],
                            },
                            {"opcode": "CX", "q0": 0, "q1": 1},
                            {"opcode": "Return"},
                        ],
                    }
                ],
            },
            _rz_helper_cache_fixture_ir()["circuit_list"][0],
        ],
    }


def _run_parallel_rz_helper_cache_worker(
    cache_root: str,
    qret_path: str,
    result_queue: Any,
) -> None:
    try:
        sc.SURFACE_CODE_CACHE_DIR = Path(cache_root)
        circuit, metadata = sc._optimize_rz_helper_independent_cached(
            qret_path=Path(qret_path),
            runtime_root=Path(cache_root),
            full_ir_data=_rz_helper_cache_fixture_ir(),
            helper=_rz_helper_fixture_metadata(),
            helper_index=0,
            rotation_precision=1.0e-5,
            qret_hash=sc.file_sha256(qret_path),
            helper_passes=sc._rz_helper_passes(),
            stage_recorder=None,
        )
        result_queue.put(
            {
                "ok": True,
                "cache_status": metadata["cache_status"],
                "filled_by_other_process": metadata.get(
                    "filled_by_other_process",
                    False,
                ),
                "circuit_name": circuit["name"],
            }
        )
    except BaseException as exc:
        result_queue.put({"ok": False, "error": repr(exc)})
        raise


def _run_parallel_integral_cache_worker(
    cache_root: str,
    result_queue: Any,
) -> None:
    try:
        sc.SURFACE_CODE_CACHE_DIR = Path(cache_root)
        sc.SURFACE_CODE_INTEGRAL_CACHE_ENABLED = True
        resolved = sc._resolve_surface_code_integrals(4, distance=1.0)
        result_queue.put(
            {
                "ok": True,
                "constant": float(resolved.constant),
                "one_body_shape": list(np.asarray(resolved.one_body).shape),
                "two_body_shape": list(np.asarray(resolved.two_body).shape),
                "cache_status": resolved.cache_status,
                "filled_by_other_process": resolved.filled_by_other_process,
                "integral_value_hash": resolved.integral_value_hash,
            }
        )
    except BaseException as exc:
        result_queue.put({"ok": False, "error": repr(exc)})
        raise


def _legacy_python_inline_ir(
    input_ir_path: Path,
    output_ir_path: Path,
    *,
    function_name: str = "main",
) -> None:
    with input_ir_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    functions: dict[str, dict[str, Any]] = {}
    target_item: dict[str, Any] | None = None
    for circuit in data.get("circuit_list", []):
        if not isinstance(circuit, Mapping):
            continue
        name = circuit.get("name")
        if not isinstance(name, str):
            continue
        bb_list = circuit.get("bb_list")
        argument = circuit.get("argument")
        if not isinstance(bb_list, list) or len(bb_list) != 1:
            raise ValueError(f"Python inliner only supports one basic block: {name}")
        if not isinstance(argument, Mapping):
            raise ValueError(f"Missing argument for {name}")
        functions[name] = {
            "inst_list": bb_list[0].get("inst_list", []),
            "num_qubits": int(argument.get("num_qubits", 0)),
        }
        if name == function_name:
            target_item = dict(circuit)

    if function_name not in functions or target_item is None:
        raise ValueError(f"Circuit '{function_name}' not found in {input_ir_path}")

    inlined: list[dict[str, Any]] = []

    def map_qubit(qubit_map: Sequence[int], value: Any) -> int:
        return int(qubit_map[int(value)])

    def unroll(name: str, qubit_map: Sequence[int], stack: tuple[str, ...]) -> None:
        if name in stack:
            raise ValueError(
                "Recursive Call cycle detected: " + " -> ".join((*stack, name))
            )
        function = functions.get(name)
        if function is None:
            raise ValueError(f"Unknown callee '{name}'")
        for inst in function["inst_list"]:
            if not isinstance(inst, Mapping):
                continue
            opcode = str(inst.get("opcode"))
            if opcode == "Call":
                callee = inst.get("callee")
                operate = inst.get("operate")
                if not isinstance(callee, str) or not isinstance(operate, list):
                    raise ValueError(f"Invalid Call in {name}")
                child_map = [map_qubit(qubit_map, q) for q in operate]
                unroll(callee, child_map, (*stack, name))
                continue
            if opcode in sc._INLINE_IGNORED_OPS:
                continue
            new_inst = dict(inst)
            if opcode in sc._INLINE_ONE_QUBIT_OPS:
                new_inst["q"] = map_qubit(qubit_map, new_inst["q"])
            elif opcode in sc._INLINE_TWO_QUBIT_OPS:
                new_inst["q0"] = map_qubit(qubit_map, new_inst["q0"])
                new_inst["q1"] = map_qubit(qubit_map, new_inst["q1"])
            elif opcode in sc._INLINE_THREE_QUBIT_OPS:
                new_inst["q0"] = map_qubit(qubit_map, new_inst["q0"])
                new_inst["q1"] = map_qubit(qubit_map, new_inst["q1"])
                new_inst["q2"] = map_qubit(qubit_map, new_inst["q2"])
            else:
                raise ValueError(f"Unsupported opcode '{opcode}'")
            inlined.append(new_inst)

    num_qubits = int(functions[function_name]["num_qubits"])
    unroll(function_name, list(range(num_qubits)), ())
    inlined.append({"opcode": "Return"})
    target_item["bb_list"][0]["inst_list"] = inlined
    data["circuit_list"] = [target_item]
    with output_ir_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=True, separators=(",", ":"))


def _flat_inst_list(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data["circuit_list"][0]["bb_list"][0]["inst_list"]


def test_streaming_inliner_matches_legacy_flat_ir_and_metrics(tmp_path: Path) -> None:
    input_path = tmp_path / "input.json"
    legacy_path = tmp_path / "legacy.json"
    streaming_path = tmp_path / "streaming.json"
    input_path.write_text(
        json.dumps(_fixture_ir(), ensure_ascii=True, separators=(",", ":")),
        encoding="utf-8",
    )

    _legacy_python_inline_ir(input_path, legacy_path)
    streaming_inline_summary = sc._python_inline_ir(input_path, streaming_path)

    assert _flat_inst_list(streaming_path) == _flat_inst_list(legacy_path)
    assert _flat_inst_list(streaming_path) == [
        {"opcode": "H", "q": 0},
        {"opcode": "T", "q": 2},
        {"opcode": "S", "q": 0},
        {"opcode": "X", "q": 0},
        {"opcode": "TDag", "q": 0},
        {"opcode": "CX", "q0": 0, "q1": 2},
        {"opcode": "Return"},
    ]

    legacy_summary = sc.summarize_optimized_ir(legacy_path)
    streaming_summary = sc.summarize_optimized_ir(streaming_path)
    assert streaming_inline_summary["instruction_stream"] == streaming_summary[
        "instruction_stream"
    ]

    summary_keys = [
        "instruction_count",
        "scheduled_instruction_count",
        "emitted_instruction_count",
        "gate_depth",
        "step_magic_state_count",
        "step_magic_state_depth",
        "peak_magic_layer",
    ]
    for key in summary_keys:
        assert streaming_summary[key] == legacy_summary[key]

    stream_keys = [
        "normalized_instruction_stream_hash",
        "opcode_count",
        "scheduled_instruction_count",
        "emitted_instruction_count",
        "gate_depth",
        "step_magic_state_count",
        "step_magic_state_depth",
        "peak_magic_layer",
    ]
    for key in stream_keys:
        assert streaming_summary["instruction_stream"][key] == legacy_summary[
            "instruction_stream"
        ][key]

    assert streaming_inline_summary["emitted_instruction_count"] == 7
    assert streaming_inline_summary["scheduled_instruction_count"] == 6
    assert not list(tmp_path.glob("*.tmp"))
    assert not list(tmp_path.glob(".*.tmp"))


def test_inline_summary_is_used_without_reloading_flat_ir(tmp_path: Path) -> None:
    input_path = tmp_path / "input.json"
    streaming_path = tmp_path / "streaming.json"
    input_path.write_text(
        json.dumps(_fixture_ir(), ensure_ascii=True, separators=(",", ":")),
        encoding="utf-8",
    )
    streaming_inline_summary = sc._python_inline_ir(input_path, streaming_path)

    summary = sc._optimized_ir_summary_from_inline_or_file(
        tmp_path / "missing_step_opt.json",
        {"inline_summary": streaming_inline_summary},
    )

    assert summary["instruction_stream"] == streaming_inline_summary[
        "instruction_stream"
    ]
    assert summary["instruction_count"] == 6
    assert summary["emitted_instruction_count"] == 7


def test_mapping_result_collection_is_opt_in(tmp_path: Path, monkeypatch: Any) -> None:
    qret_path = tmp_path / "qret"
    qret_path.write_text("#!/bin/sh\n", encoding="utf-8")
    opt_path = tmp_path / "step_opt.json"
    opt_path.write_text("{}", encoding="utf-8")
    compile_root = tmp_path / "compile"
    compile_root.mkdir()
    (compile_root / "compile_info.json").write_text(
        json.dumps(
            {
                "magic_state_consumption_count": 0,
                "magic_state_consumption_depth": 0,
                "runtime": 0,
                "runtime_without_topology": 0,
                "qubit_volume": 0,
            },
            ensure_ascii=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )

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
        optimized_ir_path=opt_path,
        qasm_hash="qasm",
        optimized_ir_hash="opt",
        qret_path=qret_path,
        qret_hash="qret",
        step_rz_count=0,
        step_rz_layer=None,
        step_magic_state_count=0,
        step_magic_state_depth=0,
        peak_magic_layer=0,
        instruction_count=0,
        gate_depth=0,
        rz_call_cache={},
    )
    architecture = sc.SurfaceCodeArchitecture(
        compile_mode="decompose_only",
        qret_path=qret_path,
        save_mapping_result=False,
    )

    def fail_save_mapping_result(**_: Any) -> dict[str, Any]:
        raise AssertionError("mapping result collection should be opt-in")

    monkeypatch.setattr(sc, "_compile_runtime_root", lambda *_: compile_root)
    monkeypatch.setattr(sc, "save_surface_code_mapping_result", fail_save_mapping_result)

    metrics = sc.compile_prepared_surface_code_step_artifact(
        artifact,
        architecture,
        reuse_cache=True,
    )

    assert metrics["mapping_result_json"] is None
    assert metrics["mapping_result_hash"] is None
    assert metrics["mapping_result_unavailable_reason"] == "disabled"


def test_stage_metrics_recorder_writes_valid_json(tmp_path: Path) -> None:
    output_path = tmp_path / "payload.json"
    metrics_path = tmp_path / "prepare_stage_metrics.json"
    recorder = sc._StageMetricsRecorder(
        scope="unit_test",
        metadata={"case": "stage_recorder"},
    )

    with recorder.stage("write_payload", output_path=str(output_path)) as span:
        output_path.write_text("{}", encoding="utf-8")
        span.add_result(output_size_bytes=output_path.stat().st_size)

    recorder.write(
        metrics_path,
        status="ok",
        files={"payload": output_path},
        extra={"example": True},
    )

    with metrics_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    assert payload["version"] == sc._PREPARE_STAGE_METRICS_VERSION
    assert payload["status"] == "ok"
    assert payload["scope"] == "unit_test"
    assert payload["stage_count"] == 1
    assert payload["stages"][0]["name"] == "write_payload"
    assert payload["stages"][0]["result"]["output_size_bytes"] == 2
    assert payload["file_sizes_bytes"]["payload"] == 2


def test_ir_rotation_rewrite_normalizes_parse_timestamp(tmp_path: Path) -> None:
    ir_path = tmp_path / "step_ir.json"
    sc._atomic_write_json(
        ir_path,
        {
            "metadata": {
                "format": "IR",
                "schema_version": "0.1",
                "created_at": "2026-06-23T12:34:56",
            },
            "name": "OpenQASM2",
            "circuit_list": [
                {
                    "name": "main",
                    "argument": {"num_qubits": 1},
                    "bb_list": [
                        {
                            "name": "entry",
                            "inst_list": [
                                {
                                    "opcode": "RZ",
                                    "q": 0,
                                    "theta": {"value": 0.25, "precision": 1.0e-3},
                                },
                                {"opcode": "Return"},
                            ],
                        }
                    ],
                }
            ],
        },
        indent=None,
    )

    result = sc._rewrite_ir_rotation_precision(ir_path, rotation_precision=1.0e-5)
    payload = json.loads(ir_path.read_text(encoding="utf-8"))

    assert result["metadata_created_at_normalized"] is True
    assert payload["metadata"]["created_at"] == "1970-01-01T00:00:00"
    assert payload["circuit_list"][0]["bb_list"][0]["inst_list"][0]["theta"][
        "precision"
    ] == 1.0e-5


def test_run_qret_records_stage_metrics_for_subprocess(tmp_path: Path) -> None:
    script_path = tmp_path / "fake_qret.sh"
    output_path = tmp_path / "out.json"
    script_path.write_text(
        "#!/bin/sh\n"
        "printf '{\"lc_all\":\"%s\",\"lang\":\"%s\"}' \"$LC_ALL\" \"$LANG\" > \"$1\"\n",
        encoding="utf-8",
    )
    script_path.chmod(0o755)
    recorder = sc._StageMetricsRecorder(
        scope="unit_test_qret",
        metadata={"case": "fake_qret"},
    )

    result = sc._run_qret(
        [str(script_path), str(output_path)],
        runtime_root=tmp_path,
        stage_recorder=recorder,
        stage_name="fake_qret",
        stage_details={"output_path": str(output_path)},
    )

    summary = recorder.summary(status="ok", files={"output": output_path})
    stage = summary["stages"][0]
    assert result["returncode"] == 0
    assert stage["name"] == "fake_qret"
    assert stage["result"]["returncode"] == 0
    assert stage["result"]["output_size_bytes"] == output_path.stat().st_size
    assert summary["file_sizes_bytes"]["output"] == output_path.stat().st_size
    if stage["result"]["gnu_time_used"]:
        assert stage["result"]["subprocess_maxrss_kb"] > 0
        with output_path.open("r", encoding="utf-8") as f:
            output_payload = json.load(f)
        assert output_payload["lc_all"] == "C"
        assert output_payload["lang"] == "C"


def test_prepare_cache_hit_preserves_cold_stage_metrics(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    runtime_root = tmp_path / "prepared"
    runtime_root.mkdir()
    qret_path = tmp_path / "qret"
    qret_path.write_text("#!/bin/sh\n", encoding="utf-8")
    qasm_path = runtime_root / "step.qasm"
    ir_path = runtime_root / "step_ir.json"
    opt_path = runtime_root / "step_opt.json"
    qasm_path.write_text("OPENQASM 2.0;\n", encoding="utf-8")
    ir_path.write_text("{}", encoding="utf-8")
    opt_path.write_text("{}", encoding="utf-8")
    cold_metrics_path = runtime_root / sc._PREPARE_STAGE_METRICS_FILENAME
    cold_metrics = {
        "version": sc._PREPARE_STAGE_METRICS_VERSION,
        "status": "ok",
        "sentinel": "cold-run",
    }
    cold_metrics_path.write_text(json.dumps(cold_metrics), encoding="utf-8")

    artifact = sc.SurfaceCodeStepArtifact(
        ham_name="H2_sto-3g_singlet_distance_100_charge_0_grouping",
        molecule="H2",
        num_logical_qubits=4,
        pf_label="2nd",
        target_error=1.0e-4,
        step_time=1.0,
        rotation_precision=1.0e-5,
        runtime_root=runtime_root,
        qasm_path=qasm_path,
        ir_path=ir_path,
        optimized_ir_path=opt_path,
        qasm_hash=sc.file_sha256(qasm_path),
        optimized_ir_hash=sc.file_sha256(opt_path),
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
    sc._atomic_write_json(runtime_root / "step_artifact.json", artifact.to_dict())
    monkeypatch.setattr(sc, "_step_artifact_runtime_root", lambda *_, **__: runtime_root)
    monkeypatch.setattr(
        sc,
        "_resolve_surface_code_integrals",
        lambda *_, **__: _fake_resolved_integrals(1.0),
    )

    cached = sc.prepare_grouped_surface_code_step_artifact(
        artifact.ham_name,
        artifact.pf_label,
        architecture=sc.SurfaceCodeArchitecture(qret_path=qret_path),
        step_time=artifact.step_time,
        rotation_precision=artifact.rotation_precision,
    )

    assert cached.optimized_ir_hash == artifact.optimized_ir_hash
    with cold_metrics_path.open("r", encoding="utf-8") as f:
        assert json.load(f) == cold_metrics

    cache_hit_path = runtime_root / sc._PREPARE_STAGE_CACHE_HIT_METRICS_FILENAME
    with cache_hit_path.open("r", encoding="utf-8") as f:
        cache_hit_metrics = json.load(f)
    assert cache_hit_metrics["status"] == "cache_hit"
    assert cache_hit_metrics["cold_run_stage_metrics_exists"] is True
    assert cache_hit_metrics["cold_run_stage_metrics_path"] == str(cold_metrics_path)


def _integral_lookup_results(recorder: sc._StageMetricsRecorder) -> list[dict[str, Any]]:
    return [
        dict(stage.get("result", {}))
        for stage in recorder.summary(status="ok").get("stages", [])
        if stage.get("name") == "integral_cache_lookup"
    ]


def _integral_cache_entry_dirs(cache_root: Path) -> list[Path]:
    root = cache_root / "gr" / "integral_cache"
    if not root.exists():
        return []
    return sorted(path for path in root.glob("*/*") if path.is_dir())


def _fixture_integral_payload(
    *,
    distance: float = 1.0,
    basis: str = "sto-3g",
    pyscf_version: str = "pyscf-test-1",
) -> dict[str, Any]:
    geometry = [
        ("H", (0.0, 0.0, -1.5 * distance)),
        ("H", (0.0, 0.0, -0.5 * distance)),
        ("H", (0.0, 0.0, 0.5 * distance)),
        ("H", (0.0, 0.0, 1.5 * distance)),
    ]
    return sc._surface_code_integral_cache_payload(
        chain_length=4,
        geometry=geometry,
        distance=distance,
        basis=basis,
        charge=0,
        multiplicity=1,
        pyscf_version=pyscf_version,
    )


def _write_integral_cache_entry(
    cache_root: Path,
    *,
    constant: Any | None = None,
    one_body: np.ndarray | None = None,
    two_body: np.ndarray | None = None,
    payload: Mapping[str, Any] | None = None,
) -> tuple[Path, str, dict[str, Any]]:
    constant = np.float64(1.25) if constant is None else constant
    one_body = (
        np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float64)
        if one_body is None
        else one_body
    )
    two_body = (
        np.arange(16, dtype=np.float64).reshape(2, 2, 2, 2)
        if two_body is None
        else two_body
    )
    payload = dict(payload or _fixture_integral_payload())
    cache_key = sc._surface_code_integral_cache_key(payload)
    cache_dir = cache_root / "gr" / "integral_cache" / cache_key[:2] / cache_key
    cache_dir.mkdir(parents=True, exist_ok=True)
    npz_path = cache_dir / "integrals.npz"
    sc._write_surface_code_integral_npz_atomic(
        npz_path,
        constant=constant,
        one_body=one_body,
        two_body=two_body,
    )
    _, _, integral_value_hash = sc._checked_surface_code_integral_arrays(
        constant=constant,
        one_body=one_body,
        two_body=two_body,
    )
    metadata = sc._surface_code_integral_cache_metadata(
        cache_key=cache_key,
        payload=payload,
        npz_path=npz_path,
        constant=constant,
        one_body=one_body,
        two_body=two_body,
        integral_value_hash=integral_value_hash,
        cache_status="created",
    )
    sc._atomic_write_json(cache_dir / "metadata.json", metadata)
    return cache_dir, cache_key, metadata


def _rewrite_integral_npz_and_metadata(
    cache_dir: Path,
    metadata: dict[str, Any],
    *,
    constant: Any,
    one_body: np.ndarray,
    two_body: np.ndarray,
    update_integral_hash: bool = True,
) -> dict[str, Any]:
    npz_path = cache_dir / "integrals.npz"
    sc._write_surface_code_integral_npz_atomic(
        npz_path,
        constant=constant,
        one_body=one_body,
        two_body=two_body,
    )
    metadata = dict(metadata)
    metadata["npz_sha256"] = sc.file_sha256(npz_path)
    metadata["arrays"] = sc._surface_code_integral_cache_array_metadata(
        constant=constant,
        one_body=one_body,
        two_body=two_body,
    )
    if update_integral_hash:
        metadata["integral_value_hash"] = sc._surface_code_integral_value_hash(
            constant=constant,
            one_body=one_body,
            two_body=two_body,
        )
    sc._atomic_write_json(cache_dir / "metadata.json", metadata)
    return metadata


def _load_integral_cache_invalid_reason(cache_dir: Path, cache_key: str) -> str | None:
    _, _, _, _, invalid_reason = sc._load_valid_surface_code_integral_cache(
        cache_dir=cache_dir,
        cache_key=cache_key,
    )
    return invalid_reason


def _fake_resolved_integrals(value: float = 1.0) -> sc._ResolvedSurfaceCodeIntegrals:
    one_body = np.array([[value]], dtype=np.float64)
    two_body = np.array([[[[value]]]], dtype=np.float64)
    integral_value_hash = sc._surface_code_integral_value_hash(
        constant=np.float64(value),
        one_body=one_body,
        two_body=two_body,
    )
    return sc._ResolvedSurfaceCodeIntegrals(
        constant=np.float64(value),
        one_body=one_body,
        two_body=two_body,
        cache_enabled=True,
        schema_version=sc._SURFACE_CODE_INTEGRAL_CACHE_VERSION,
        cache_key=f"cache-key-{value}",
        integral_value_hash=integral_value_hash,
        cache_status="hit",
        filled_by_other_process=False,
        initial_invalid_reason=None,
        locked_invalid_reason=None,
        cache_dir=Path(f"/tmp/cache-key-{value}"),
        npz_path=Path(f"/tmp/cache-key-{value}/integrals.npz"),
        npz_sha256=f"npz-{value}",
    )


def test_surface_code_integral_value_hash_is_bit_exact() -> None:
    constant = np.float64(1.25)
    one_body = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float64)
    two_body = np.arange(16, dtype=np.float64).reshape(2, 2, 2, 2)
    base_hash = sc._surface_code_integral_value_hash(
        constant=constant,
        one_body=one_body,
        two_body=two_body,
    )

    assert base_hash == sc._surface_code_integral_value_hash(
        constant=np.array(1.25, dtype=np.float64),
        one_body=one_body.copy(),
        two_body=two_body.copy(),
    )
    changed_value = two_body.copy()
    changed_value.reshape(-1)[0] = np.nextafter(changed_value.reshape(-1)[0], 1.0)
    assert base_hash != sc._surface_code_integral_value_hash(
        constant=constant,
        one_body=one_body,
        two_body=changed_value,
    )
    assert base_hash != sc._surface_code_integral_value_hash(
        constant=constant,
        one_body=one_body.astype(np.float32),
        two_body=two_body,
    )
    assert base_hash != sc._surface_code_integral_value_hash(
        constant=constant,
        one_body=one_body.reshape(1, 4),
        two_body=two_body,
    )
    assert base_hash == sc._surface_code_integral_value_hash(
        constant=constant,
        one_body=np.array(one_body, order="F"),
        two_body=np.array(two_body, order="F"),
    )


def test_surface_code_integral_cache_validation_reasons(tmp_path: Path) -> None:
    cache_root = tmp_path / "cache"

    cache_dir, cache_key, metadata = _write_integral_cache_entry(cache_root)
    broken = dict(metadata)
    broken["cache_payload"] = dict(broken["cache_payload"])
    broken["cache_payload"]["distance"] = 2.0
    sc._atomic_write_json(cache_dir / "metadata.json", broken)
    assert _load_integral_cache_invalid_reason(cache_dir, cache_key) == (
        "cache_payload_mismatch"
    )

    cache_dir, cache_key, metadata = _write_integral_cache_entry(cache_root)
    extra_npz_path = cache_dir / "integrals.npz"
    with extra_npz_path.open("wb") as f:
        np.savez(
            f,
            constant=np.array(1.0),
            one_body=np.eye(2),
            two_body=np.ones((2, 2, 2, 2)),
            extra=np.array([1.0]),
        )
    metadata["npz_sha256"] = sc.file_sha256(extra_npz_path)
    sc._atomic_write_json(cache_dir / "metadata.json", metadata)
    assert _load_integral_cache_invalid_reason(cache_dir, cache_key) == (
        "npz_keys_mismatch"
    )

    cache_dir, cache_key, metadata = _write_integral_cache_entry(cache_root)
    metadata["arrays"]["one_body"]["shape"] = [1, 4]
    sc._atomic_write_json(cache_dir / "metadata.json", metadata)
    assert _load_integral_cache_invalid_reason(cache_dir, cache_key) == (
        "one_body_shape_mismatch"
    )

    cache_dir, cache_key, metadata = _write_integral_cache_entry(cache_root)
    metadata["arrays"]["one_body"]["dtype"] = "<f4"
    sc._atomic_write_json(cache_dir / "metadata.json", metadata)
    assert _load_integral_cache_invalid_reason(cache_dir, cache_key) == (
        "one_body_dtype_mismatch"
    )

    cache_dir, cache_key, metadata = _write_integral_cache_entry(cache_root)
    metadata["arrays"]["one_body"]["nbytes"] += 1
    sc._atomic_write_json(cache_dir / "metadata.json", metadata)
    assert _load_integral_cache_invalid_reason(cache_dir, cache_key) == (
        "one_body_nbytes_mismatch"
    )

    cache_dir, cache_key, metadata = _write_integral_cache_entry(cache_root)
    metadata["integral_value_hash"] = "bad"
    sc._atomic_write_json(cache_dir / "metadata.json", metadata)
    assert _load_integral_cache_invalid_reason(cache_dir, cache_key) == (
        "integral_value_hash_mismatch"
    )

    cache_dir, cache_key, metadata = _write_integral_cache_entry(cache_root)
    nonfinite_one = np.eye(2, dtype=np.float64)
    nonfinite_one[0, 0] = np.inf
    _rewrite_integral_npz_and_metadata(
        cache_dir,
        metadata,
        constant=np.float64(1.0),
        one_body=nonfinite_one,
        two_body=np.ones((2, 2, 2, 2), dtype=np.float64),
    )
    assert _load_integral_cache_invalid_reason(cache_dir, cache_key) == (
        "nonfinite_one_body"
    )

    cache_dir, cache_key, metadata = _write_integral_cache_entry(cache_root)
    _rewrite_integral_npz_and_metadata(
        cache_dir,
        metadata,
        constant=np.float64(1.0),
        one_body=np.ones((2, 3), dtype=np.float64),
        two_body=np.ones((2, 2, 2, 2), dtype=np.float64),
    )
    assert _load_integral_cache_invalid_reason(cache_dir, cache_key) == (
        "one_body_not_square"
    )

    cache_dir, cache_key, metadata = _write_integral_cache_entry(cache_root)
    _rewrite_integral_npz_and_metadata(
        cache_dir,
        metadata,
        constant=np.float64(1.0),
        one_body=np.eye(2, dtype=np.float64),
        two_body=np.ones((2, 2, 2, 1), dtype=np.float64),
    )
    assert _load_integral_cache_invalid_reason(cache_dir, cache_key) == (
        "two_body_dimension_mismatch"
    )


def test_surface_code_integral_cache_miss_hit_and_exact_values(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    cache_root = tmp_path / "cache"
    calls: list[tuple[int, float]] = []
    constant = np.float64(1.25)
    one_body = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float64)
    two_body = np.arange(16, dtype=np.float64).reshape(2, 2, 2, 2)

    def fake_compute(chain_length: int, *, distance: float) -> tuple[Any, Any, Any]:
        calls.append((int(chain_length), float(distance)))
        return constant, one_body.copy(), two_body.copy()

    monkeypatch.setattr(sc, "SURFACE_CODE_CACHE_DIR", cache_root)
    monkeypatch.setattr(sc, "SURFACE_CODE_INTEGRAL_CACHE_ENABLED", True)
    monkeypatch.setattr(sc, "_pyscf_version", lambda: "pyscf-test-1")
    monkeypatch.setattr(sc, "_compute_surface_code_integrals_uncached", fake_compute)

    first_recorder = sc._StageMetricsRecorder(
        scope="integral_cache_test",
        metadata={"run": 1},
    )
    first_constant, first_one_body, first_two_body = sc._surface_code_integrals(
        4,
        distance=1.0,
        stage_recorder=first_recorder,
    )
    assert _integral_lookup_results(first_recorder)[0]["cache_status"] == "miss"
    assert calls == [(4, 1.0)]

    second_recorder = sc._StageMetricsRecorder(
        scope="integral_cache_test",
        metadata={"run": 2},
    )
    second_constant, second_one_body, second_two_body = sc._surface_code_integrals(
        4,
        distance=1.0,
        stage_recorder=second_recorder,
    )
    assert _integral_lookup_results(second_recorder)[0]["cache_status"] == "hit"
    assert calls == [(4, 1.0)]

    assert np.array_equal(np.asarray(second_constant), np.asarray(first_constant))
    assert np.array_equal(second_one_body, first_one_body)
    assert np.array_equal(second_two_body, first_two_body)
    assert np.asarray(second_constant).dtype == np.asarray(first_constant).dtype
    assert second_one_body.dtype == first_one_body.dtype
    assert second_two_body.dtype == first_two_body.dtype
    assert np.asarray(second_constant).shape == np.asarray(first_constant).shape
    assert second_one_body.shape == first_one_body.shape
    assert second_two_body.shape == first_two_body.shape

    entry_dirs = _integral_cache_entry_dirs(cache_root)
    assert len(entry_dirs) == 1
    metadata = json.loads((entry_dirs[0] / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["schema_version"] == sc._SURFACE_CODE_INTEGRAL_CACHE_VERSION
    assert metadata["pyscf_version"] == "pyscf-test-1"
    assert metadata["arrays"]["constant"] == {
        "shape": [],
        "dtype": "<f8",
        "nbytes": 8,
    }
    assert metadata["arrays"]["one_body"] == {
        "shape": [2, 2],
        "dtype": "<f8",
        "nbytes": 32,
    }
    assert metadata["arrays"]["two_body"] == {
        "shape": [2, 2, 2, 2],
        "dtype": "<f8",
        "nbytes": 128,
    }
    assert isinstance(metadata["npz_sha256"], str)
    assert isinstance(metadata["integral_value_hash"], str)
    assert "exact cache entry" in metadata["reproducibility_note"]


def test_surface_code_integral_cache_corrupt_entries_regenerate(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    cache_root = tmp_path / "cache"
    calls: list[int] = []

    def fake_compute(chain_length: int, *, distance: float) -> tuple[Any, Any, Any]:
        calls.append(len(calls) + 1)
        value = float(len(calls))
        return (
            np.float64(value),
            np.full((2, 2), value, dtype=np.float64),
            np.full((2, 2, 2, 2), value, dtype=np.float64),
        )

    monkeypatch.setattr(sc, "SURFACE_CODE_CACHE_DIR", cache_root)
    monkeypatch.setattr(sc, "SURFACE_CODE_INTEGRAL_CACHE_ENABLED", True)
    monkeypatch.setattr(sc, "_pyscf_version", lambda: "pyscf-test-1")
    monkeypatch.setattr(sc, "_compute_surface_code_integrals_uncached", fake_compute)

    sc._surface_code_integrals(4, distance=1.0)
    entry_dir = _integral_cache_entry_dirs(cache_root)[0]

    (entry_dir / "integrals.npz").write_bytes(b"broken")
    npz_recorder = sc._StageMetricsRecorder(
        scope="integral_cache_test",
        metadata={"case": "npz_corrupt"},
    )
    sc._surface_code_integrals(4, distance=1.0, stage_recorder=npz_recorder)
    npz_lookup = _integral_lookup_results(npz_recorder)[0]
    assert npz_lookup["cache_status"] == "miss"
    assert npz_lookup["invalid_reason"] == "npz_hash_mismatch"
    assert len(calls) == 2

    (entry_dir / "metadata.json").write_text("{broken", encoding="utf-8")
    metadata_recorder = sc._StageMetricsRecorder(
        scope="integral_cache_test",
        metadata={"case": "metadata_corrupt"},
    )
    sc._surface_code_integrals(4, distance=1.0, stage_recorder=metadata_recorder)
    metadata_lookup = _integral_lookup_results(metadata_recorder)[0]
    assert metadata_lookup["cache_status"] == "miss"
    assert str(metadata_lookup["invalid_reason"]).startswith("invalid:")
    assert len(calls) == 3


def test_surface_code_integral_cache_key_conditions_miss(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    cache_root = tmp_path / "cache"
    calls: list[tuple[int, float, str, str]] = []

    def fake_compute(chain_length: int, *, distance: float) -> tuple[Any, Any, Any]:
        calls.append(
            (
                int(chain_length),
                float(distance),
                str(sc.DEFAULT_BASIS),
                str(sc._pyscf_version()),
            )
        )
        value = float(len(calls))
        return (
            np.float64(value),
            np.eye(2, dtype=np.float64) * value,
            np.ones((2, 2, 2, 2), dtype=np.float64) * value,
        )

    version = {"value": "pyscf-test-1"}
    monkeypatch.setattr(sc, "SURFACE_CODE_CACHE_DIR", cache_root)
    monkeypatch.setattr(sc, "SURFACE_CODE_INTEGRAL_CACHE_ENABLED", True)
    monkeypatch.setattr(sc, "_pyscf_version", lambda: version["value"])
    monkeypatch.setattr(sc, "_compute_surface_code_integrals_uncached", fake_compute)

    sc._surface_code_integrals(4, distance=1.0)
    sc._surface_code_integrals(4, distance=1.0)
    assert len(calls) == 1

    sc._surface_code_integrals(4, distance=1.1)
    assert len(calls) == 2

    monkeypatch.setattr(sc, "DEFAULT_BASIS", "6-31g")
    sc._surface_code_integrals(4, distance=1.0)
    assert len(calls) == 3

    version["value"] = "pyscf-test-2"
    sc._surface_code_integrals(4, distance=1.0)
    assert len(calls) == 4


def test_surface_code_integral_cache_disabled_recomputes(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    calls: list[int] = []

    def fake_compute(chain_length: int, *, distance: float) -> tuple[Any, Any, Any]:
        del chain_length, distance
        calls.append(len(calls) + 1)
        value = float(len(calls))
        return (
            np.float64(value),
            np.array([[value]], dtype=np.float64),
            np.array([[[[value]]]], dtype=np.float64),
        )

    monkeypatch.setattr(sc, "SURFACE_CODE_CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(sc, "SURFACE_CODE_INTEGRAL_CACHE_ENABLED", False)
    monkeypatch.setattr(sc, "_pyscf_version", lambda: "pyscf-test-1")
    monkeypatch.setattr(sc, "_compute_surface_code_integrals_uncached", fake_compute)

    first = sc._resolve_surface_code_integrals(4, distance=1.0)
    second = sc._resolve_surface_code_integrals(4, distance=1.0)
    assert len(calls) == 2
    assert first.cache_status == "disabled"
    assert second.cache_status == "disabled"
    assert first.integral_value_hash != second.integral_value_hash
    assert first.cache_key == second.cache_key
    assert _integral_cache_entry_dirs(tmp_path / "cache") == []


def test_surface_code_integral_cache_compute_failure_does_not_commit(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    cache_root = tmp_path / "cache"

    def fail_compute(chain_length: int, *, distance: float) -> tuple[Any, Any, Any]:
        del chain_length, distance
        raise RuntimeError("PySCF RHF did not converge: fixture")

    monkeypatch.setattr(sc, "SURFACE_CODE_CACHE_DIR", cache_root)
    monkeypatch.setattr(sc, "SURFACE_CODE_INTEGRAL_CACHE_ENABLED", True)
    monkeypatch.setattr(sc, "_pyscf_version", lambda: "pyscf-test-1")
    monkeypatch.setattr(sc, "_compute_surface_code_integrals_uncached", fail_compute)

    try:
        sc._resolve_surface_code_integrals(4, distance=1.0)
    except RuntimeError as exc:
        assert "did not converge" in str(exc)
    else:
        raise AssertionError("SCF failure must propagate")

    for entry_dir in _integral_cache_entry_dirs(cache_root):
        assert not (entry_dir / "integrals.npz").exists()
        assert not (entry_dir / "metadata.json").exists()
        assert not list(entry_dir.glob("*.tmp"))
        assert not list(entry_dir.glob(".*.tmp"))


def test_step_artifact_cache_key_depends_on_integral_identity() -> None:
    base = {
        "ham_name": "H4_sto-3g_singlet_distance_100_charge_0_grouping",
        "pf_label": "4th(new_2)",
        "target_error": 1.0e-4,
        "step_time": 1.0,
        "rotation_precision": 1.0e-5,
        "qret_hash": "qret",
        "integral_cache_enabled": True,
        "integral_cache_schema_version": sc._SURFACE_CODE_INTEGRAL_CACHE_VERSION,
        "integral_cache_key": "integral-key-a",
        "integral_value_hash": "value-hash-a",
    }
    base_key = sc._step_artifact_cache_key(**base)
    for changed in (
        {"integral_cache_enabled": False},
        {"integral_cache_schema_version": "surface_code_integral_cache_v_next"},
        {"integral_cache_key": "integral-key-b"},
        {"integral_value_hash": "value-hash-b"},
    ):
        payload = dict(base)
        payload.update(changed)
        assert sc._step_artifact_cache_key(**payload) != base_key

    same_identity = dict(base)
    assert sc._step_artifact_cache_key(**same_identity) == base_key


def test_stale_prepared_artifact_is_not_reused_for_new_integral_value(
    tmp_path: Path,
) -> None:
    common = {
        "ham_name": "H4_sto-3g_singlet_distance_100_charge_0_grouping",
        "pf_label": "4th(new_2)",
        "target_error": 1.0e-4,
        "step_time": 1.0,
        "rotation_precision": 1.0e-5,
        "qret_hash": "qret",
        "integral_cache_enabled": True,
        "integral_cache_schema_version": sc._SURFACE_CODE_INTEGRAL_CACHE_VERSION,
        "integral_cache_key": "same-integral-cache-key",
    }
    original_cache_root = sc.SURFACE_CODE_CACHE_DIR
    sc.SURFACE_CODE_CACHE_DIR = tmp_path / "cache"
    try:
        root_a = sc._step_artifact_runtime_root(
            **common,
            integral_value_hash="value-a",
        )
        root_b = sc._step_artifact_runtime_root(
            **common,
            integral_value_hash="value-b",
        )
    finally:
        sc.SURFACE_CODE_CACHE_DIR = original_cache_root
    assert root_a != root_b

    root_a.mkdir(parents=True)
    qret_path = tmp_path / "qret"
    qret_path.write_text("#!/bin/sh\n", encoding="utf-8")
    qasm_path = root_a / "step.qasm"
    ir_path = root_a / "step_ir.json"
    opt_path = root_a / "step_opt.json"
    qasm_path.write_text("OPENQASM 2.0;\n", encoding="utf-8")
    ir_path.write_text("{}", encoding="utf-8")
    opt_path.write_text("{}", encoding="utf-8")
    artifact = sc.SurfaceCodeStepArtifact(
        ham_name=common["ham_name"],
        molecule="H4",
        num_logical_qubits=8,
        pf_label=common["pf_label"],
        target_error=common["target_error"],
        step_time=common["step_time"],
        rotation_precision=common["rotation_precision"],
        runtime_root=root_a,
        qasm_path=qasm_path,
        ir_path=ir_path,
        optimized_ir_path=opt_path,
        qasm_hash=sc.file_sha256(qasm_path),
        optimized_ir_hash=sc.file_sha256(opt_path),
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
        integral_cache={"integral_value_hash": "value-a"},
    )
    sc._atomic_write_json(root_a / "step_artifact.json", artifact.to_dict())

    assert sc.load_prepared_surface_code_step_artifact(root_a) is not None
    assert sc.load_prepared_surface_code_step_artifact(root_b) is None


def test_surface_code_integral_stage_metrics_miss_and_hit(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    calls: list[int] = []

    def fake_compute(chain_length: int, *, distance: float) -> tuple[Any, Any, Any]:
        del chain_length, distance
        calls.append(len(calls) + 1)
        return (
            np.float64(1.0),
            np.eye(2, dtype=np.float64),
            np.ones((2, 2, 2, 2), dtype=np.float64),
        )

    monkeypatch.setattr(sc, "SURFACE_CODE_CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(sc, "SURFACE_CODE_INTEGRAL_CACHE_ENABLED", True)
    monkeypatch.setattr(sc, "_pyscf_version", lambda: "pyscf-test-1")
    monkeypatch.setattr(sc, "_compute_surface_code_integrals_uncached", fake_compute)

    miss_recorder = sc._StageMetricsRecorder(
        scope="integral_stage_test",
        metadata={"run": "miss"},
    )
    sc._resolve_surface_code_integrals(
        4,
        distance=1.0,
        stage_recorder=miss_recorder,
    )
    miss_stages = miss_recorder.summary(status="ok")["stages"]
    miss_names = [stage["name"] for stage in miss_stages]
    assert "integral_cache_lookup" in miss_names
    assert "integral_cache_lock_wait_and_relookup" in miss_names
    assert "integral_scf_and_transform" in miss_names
    assert "integral_cache_write" in miss_names
    assert "build_step_circuit" not in miss_names

    hit_recorder = sc._StageMetricsRecorder(
        scope="integral_stage_test",
        metadata={"run": "hit"},
    )
    sc._resolve_surface_code_integrals(
        4,
        distance=1.0,
        stage_recorder=hit_recorder,
    )
    hit_stages = hit_recorder.summary(status="ok")["stages"]
    hit_names = [stage["name"] for stage in hit_stages]
    assert hit_names == ["integral_cache_lookup"]
    assert hit_stages[0]["result"]["cache_status"] == "hit"
    assert "integral_scf_and_transform" not in hit_names
    assert "integral_cache_write" not in hit_names
    assert calls == [1]


def test_surface_code_integral_cache_lock_prevents_parallel_generation(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    started_path = tmp_path / "integral_started"
    runs_path = tmp_path / "integral_runs.txt"

    def fake_compute(chain_length: int, *, distance: float) -> tuple[Any, Any, Any]:
        del chain_length, distance
        started_path.write_text("started", encoding="utf-8")
        time.sleep(0.6)
        with runs_path.open("a", encoding="utf-8") as f:
            f.write("run\n")
        return (
            np.float64(1.0),
            np.eye(2, dtype=np.float64),
            np.ones((2, 2, 2, 2), dtype=np.float64),
        )

    monkeypatch.setattr(sc, "_pyscf_version", lambda: "pyscf-test-1")
    monkeypatch.setattr(sc, "_compute_surface_code_integrals_uncached", fake_compute)

    ctx = mp.get_context("fork")
    result_queue = ctx.Queue()
    cache_root = tmp_path / "cache"
    first = ctx.Process(
        target=_run_parallel_integral_cache_worker,
        args=(str(cache_root), result_queue),
    )
    first.start()
    deadline = time.monotonic() + 5.0
    while not started_path.exists() and time.monotonic() < deadline:
        if first.exitcode is not None:
            break
        time.sleep(0.01)
    assert started_path.exists()

    second = ctx.Process(
        target=_run_parallel_integral_cache_worker,
        args=(str(cache_root), result_queue),
    )
    second.start()
    first.join(10)
    second.join(10)
    assert first.exitcode == 0
    assert second.exitcode == 0

    results = [result_queue.get(timeout=2), result_queue.get(timeout=2)]
    assert all(item["ok"] for item in results)
    assert runs_path.read_text(encoding="utf-8").splitlines() == ["run"]
    assert [item["one_body_shape"] for item in results] == [[2, 2], [2, 2]]
    assert sorted(item["cache_status"] for item in results) == ["hit", "miss"]
    assert sum(1 for item in results if item["filled_by_other_process"]) == 1
    assert len({item["integral_value_hash"] for item in results}) == 1


def test_independent_rz_helper_cache_generate_hit_and_corrupt_invalidate(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    cache_root = tmp_path / "cache"
    qret_path = tmp_path / "qret"
    qret_path.write_text("#!/bin/sh\n", encoding="utf-8")
    full_ir = _rz_helper_cache_fixture_ir()
    helper = _rz_helper_fixture_metadata()
    calls: list[dict[str, Any]] = []

    def fake_run_qret(
        cmd: Any,
        *,
        runtime_root: Path,
        rotation_precision: float | None = None,
        stage_recorder: Any = None,
        stage_name: str | None = None,
        stage_details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        del cmd, runtime_root, rotation_precision, stage_recorder, stage_name
        assert stage_details is not None
        input_path = Path(str(stage_details["input_path"]))
        output_path = Path(str(stage_details["output_path"]))
        with input_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        payload["circuit_list"][0]["bb_list"][0]["inst_list"] = [
            {"opcode": "H", "q": 0},
            {"opcode": "T", "q": 0},
            {"opcode": "Return"},
        ]
        sc._atomic_write_json(output_path, payload, indent=None)
        calls.append({"output_path": str(output_path)})
        return {
            "returncode": 0,
            "gnu_time_used": False,
            "stdout_bytes": 0,
            "stderr_bytes": 0,
        }

    monkeypatch.setattr(sc, "SURFACE_CODE_CACHE_DIR", cache_root)
    monkeypatch.setattr(sc, "_run_qret", fake_run_qret)

    first_circuit, first_meta = sc._optimize_rz_helper_independent_cached(
        qret_path=qret_path,
        runtime_root=tmp_path,
        full_ir_data=full_ir,
        helper=helper,
        helper_index=0,
        rotation_precision=1.0e-5,
        qret_hash=sc.file_sha256(qret_path),
        helper_passes=sc._rz_helper_passes(),
        stage_recorder=None,
    )
    assert first_meta["cache_status"] == "miss"
    assert sc._helper_circuit_summary(first_circuit)["t_count"] == 1
    assert len(calls) == 1

    full_ir["metadata"]["created_at"] = "second"
    full_ir["circuit_list"][0]["name"] = "__helper_renamed()"
    renamed_helper = dict(helper)
    renamed_helper["function_name"] = "__helper_renamed()"
    second_circuit, second_meta = sc._optimize_rz_helper_independent_cached(
        qret_path=qret_path,
        runtime_root=tmp_path,
        full_ir_data=full_ir,
        helper=renamed_helper,
        helper_index=0,
        rotation_precision=1.0e-5,
        qret_hash=sc.file_sha256(qret_path),
        helper_passes=sc._rz_helper_passes(),
        stage_recorder=None,
    )
    assert second_meta["cache_status"] == "hit"
    assert second_circuit["name"] == "__helper_renamed()"
    assert len(calls) == 1

    output_path = Path(str(first_meta["cache_dir"])) / "helper_opt.json"
    output_path.write_text("{broken", encoding="utf-8")
    _, third_meta = sc._optimize_rz_helper_independent_cached(
        qret_path=qret_path,
        runtime_root=tmp_path,
        full_ir_data=full_ir,
        helper=renamed_helper,
        helper_index=0,
        rotation_precision=1.0e-5,
        qret_hash=sc.file_sha256(qret_path),
        helper_passes=sc._rz_helper_passes(),
        stage_recorder=None,
    )
    assert third_meta["cache_status"] == "miss"
    assert str(third_meta["invalid_reason"]).startswith("invalid:")
    assert len(calls) == 2


def test_independent_rz_helper_cache_lock_prevents_parallel_generation(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    qret_path = tmp_path / "fake_qret.py"
    started_path = tmp_path / "qret_started"
    runs_path = tmp_path / "qret_runs.txt"
    qret_path.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "import time\n"
        "from pathlib import Path\n"
        "pipeline = Path(sys.argv[sys.argv.index('--pipeline') + 1])\n"
        "values = {}\n"
        "for line in pipeline.read_text(encoding='utf-8').splitlines():\n"
        "    if ': ' in line:\n"
        "        key, value = line.split(': ', 1)\n"
        "        values[key] = value\n"
        "Path(os.environ['FAKE_QRET_STARTED']).write_text('started', encoding='utf-8')\n"
        "time.sleep(0.6)\n"
        "with Path(values['input']).open('r', encoding='utf-8') as f:\n"
        "    payload = json.load(f)\n"
        "payload['circuit_list'][0]['bb_list'][0]['inst_list'] = [\n"
        "    {'opcode': 'H', 'q': 0},\n"
        "    {'opcode': 'T', 'q': 0},\n"
        "    {'opcode': 'Return'},\n"
        "]\n"
        "Path(values['output']).write_text(\n"
        "    json.dumps(payload, ensure_ascii=True, separators=(',', ':')),\n"
        "    encoding='utf-8',\n"
        ")\n"
        "with Path(os.environ['FAKE_QRET_RUNS']).open('a', encoding='utf-8') as f:\n"
        "    f.write('run\\n')\n",
        encoding="utf-8",
    )
    qret_path.chmod(0o755)
    monkeypatch.setenv("FAKE_QRET_STARTED", str(started_path))
    monkeypatch.setenv("FAKE_QRET_RUNS", str(runs_path))

    ctx = mp.get_context("fork")
    result_queue = ctx.Queue()
    cache_root = tmp_path / "cache"
    first = ctx.Process(
        target=_run_parallel_rz_helper_cache_worker,
        args=(str(cache_root), str(qret_path), result_queue),
    )
    first.start()
    deadline = time.monotonic() + 5.0
    while not started_path.exists() and time.monotonic() < deadline:
        if first.exitcode is not None:
            break
        time.sleep(0.01)
    assert started_path.exists()

    second = ctx.Process(
        target=_run_parallel_rz_helper_cache_worker,
        args=(str(cache_root), str(qret_path), result_queue),
    )
    second.start()
    first.join(10)
    second.join(10)
    assert first.exitcode == 0
    assert second.exitcode == 0

    results = [result_queue.get(timeout=2), result_queue.get(timeout=2)]
    assert all(item["ok"] for item in results)
    assert sorted(item["cache_status"] for item in results) == ["hit", "miss"]
    assert sum(1 for item in results if item["filled_by_other_process"]) == 1
    assert runs_path.read_text(encoding="utf-8").splitlines() == ["run"]


def test_rz_helper_opt_modes_produce_equivalent_flat_ir(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    qret_path = tmp_path / "qret"
    qret_path.write_text("#!/bin/sh\n", encoding="utf-8")
    rz_metadata = {
        "enabled": True,
        "helpers": [_rz_helper_fixture_metadata()],
    }
    stream_keys = [
        "normalized_instruction_stream_hash",
        "opcode_count",
        "emitted_instruction_count",
        "scheduled_instruction_count",
        "gate_depth",
        "step_magic_state_count",
        "step_magic_state_depth",
        "peak_magic_layer",
    ]

    def fake_run_qret(
        cmd: Any,
        *,
        runtime_root: Path,
        rotation_precision: float | None = None,
        stage_recorder: Any = None,
        stage_name: str | None = None,
        stage_details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        del cmd, runtime_root, rotation_precision, stage_recorder
        assert stage_details is not None
        input_path = Path(str(stage_details["input_path"]))
        output_path = Path(str(stage_details["output_path"]))
        with input_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        helper_function_name = stage_details.get("helper_function_name")
        if helper_function_name is not None:
            for circuit in payload["circuit_list"]:
                if circuit["name"] == helper_function_name:
                    circuit["bb_list"][0]["inst_list"] = [
                        {"opcode": "T", "q": 0},
                        {"opcode": "H", "q": 0},
                        {"opcode": "Return"},
                    ]
                    break
            else:
                raise AssertionError(f"missing helper {helper_function_name}")
        elif stage_name != "qret_opt_main_cleanup":
            raise AssertionError(f"unexpected qret stage {stage_name}")
        sc._atomic_write_json(output_path, payload, indent=None)
        return {
            "returncode": 0,
            "gnu_time_used": False,
            "stdout_bytes": 0,
            "stderr_bytes": 0,
        }

    monkeypatch.setattr(sc, "_run_qret", fake_run_qret)

    def run_mode(mode: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        runtime_root = tmp_path / mode
        runtime_root.mkdir()
        ir_path = runtime_root / "step_ir.json"
        opt_path = runtime_root / "step_opt.json"
        sc._atomic_write_json(ir_path, _rz_helper_e2e_fixture_ir(), indent=None)
        monkeypatch.setattr(sc, "SURFACE_CODE_RZ_HELPER_OPT_MODE", mode)
        monkeypatch.setattr(sc, "SURFACE_CODE_CACHE_DIR", tmp_path / f"cache_{mode}")
        result = sc._run_rz_call_cached_opt(
            qret_path=qret_path,
            runtime_root=runtime_root,
            ir_path=ir_path,
            opt_path=opt_path,
            rz_metadata=rz_metadata,
            rotation_precision=1.0e-5,
            stage_recorder=None,
        )
        return _flat_inst_list(opt_path), result["inline_summary"]["instruction_stream"]

    legacy_flat, legacy_stream = run_mode("legacy_full_ir")
    independent_flat, independent_stream = run_mode("independent_helper")

    assert independent_flat == legacy_flat
    for key in stream_keys:
        assert independent_stream[key] == legacy_stream[key]
