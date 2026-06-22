from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

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


def test_independent_rz_helper_cache_generate_hit_and_corrupt_invalidate(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    cache_root = tmp_path / "cache"
    qret_path = tmp_path / "qret"
    qret_path.write_text("#!/bin/sh\n", encoding="utf-8")
    full_ir = {
        "metadata": {"format": "test", "created_at": "first"},
        "name": "fixture",
        "circuit_list": [
            {
                "name": "__helper()",
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
    helper = {
        "function_name": "__helper()",
        "theta": "0.125",
        "key": "0.125",
    }
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
