from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.profile_surface_code_lightweight_tree_memory as profile


def test_light_mode_disables_tracemalloc() -> None:
    tracemalloc = profile.tracemalloc
    tracemalloc.start()
    assert tracemalloc.is_tracing()

    state = profile._configure_profile_mode("light")

    assert state["mode"] == "light"
    assert tracemalloc.is_tracing() is False


def test_deep_mode_enables_tracemalloc() -> None:
    tracemalloc = profile.tracemalloc
    if tracemalloc.is_tracing():
        tracemalloc.stop()

    state = profile._configure_profile_mode("deep")

    assert state["mode"] == "deep"
    assert tracemalloc.is_tracing() is True
    tracemalloc.stop()


def test_h6_case_is_rejected() -> None:
    with pytest.raises(ValueError, match="H6"):
        profile._validate_case("h6_4th_new2")


def test_process_isolation_gate_uses_three_thresholds() -> None:
    result = {
        "markers": [
            {"label": "evaluation_entry", "process": {"rss_kb": 50_000}},
            {"label": "after_prepare", "process": {"rss_kb": 360_000}},
            {"label": "before_qret_launch", "process": {"rss_kb": 360_000}},
        ],
        "tree_peak_split": {"tree_vmrss_kb": 900_000, "parent_vmrss_kb": 360_000},
    }

    gate = profile._isolation_gate(result)

    assert gate["passes"] is True
    assert "qret_launch_parent_rss_ge_300mb" in gate["reasons"]
    assert "parent_share_at_tree_peak_ge_30pct" in gate["reasons"]
    assert "prepare_delta_ge_200mb" in gate["reasons"]


def test_manifest_round_trip_and_hash_verification(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    qasm = tmp_path / "step.qasm"
    ir = tmp_path / "step_ir.json"
    opt = tmp_path / "step_opt.json"
    for path, text in ((qasm, "qasm"), (ir, "{}"), (opt, "{}")):
        path.write_text(text, encoding="utf-8")
    artifact = profile.sc.SurfaceCodeStepArtifact(
        ham_name="H4",
        molecule="H4",
        num_logical_qubits=4,
        pf_label=profile.PF_LABEL,
        target_error=1e-3,
        step_time=1.0,
        rotation_precision=1e-5,
        runtime_root=tmp_path,
        qasm_path=qasm,
        ir_path=ir,
        optimized_ir_path=opt,
        qasm_hash="qasm_hash",
        optimized_ir_hash="opt_hash",
        qret_path=tmp_path / "qret",
        qret_hash="qret_hash",
        step_rz_count=1,
        step_rz_layer=1,
        step_magic_state_count=2,
        step_magic_state_depth=3,
        peak_magic_layer=4,
        instruction_count=5,
        gate_depth=6,
        rz_call_cache={},
        integral_cache={},
    )
    monkeypatch.setattr(
        profile.sc,
        "file_sha256",
        lambda path: "qasm_hash" if Path(path) == qasm else "opt_hash",
    )

    loaded = profile._verify_artifact_dict(artifact.to_dict())

    assert loaded.qasm_hash == "qasm_hash"
    assert loaded.optimized_ir_hash == "opt_hash"


def test_missing_or_stale_artifact_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    qasm = tmp_path / "step.qasm"
    ir = tmp_path / "step_ir.json"
    opt = tmp_path / "step_opt.json"
    qasm.write_text("qasm", encoding="utf-8")
    ir.write_text("{}", encoding="utf-8")
    opt.write_text("{}", encoding="utf-8")
    payload = {
        "ham_name": "H4",
        "molecule": "H4",
        "num_logical_qubits": 4,
        "pf_label": profile.PF_LABEL,
        "target_error": 1e-3,
        "step_time": 1.0,
        "rotation_precision": 1e-5,
        "runtime_root": str(tmp_path),
        "qasm_path": str(qasm),
        "ir_path": str(ir),
        "optimized_ir_path": str(opt),
        "qasm_hash": "expected",
        "optimized_ir_hash": "expected",
        "qret_path": str(tmp_path / "qret"),
        "qret_hash": "qret",
        "step_rz_count": 0,
        "step_rz_layer": None,
        "step_magic_state_count": 0,
        "step_magic_state_depth": 0,
        "peak_magic_layer": 0,
        "instruction_count": 0,
        "gate_depth": 0,
        "rz_call_cache": {},
    }
    monkeypatch.setattr(profile.sc, "file_sha256", lambda _path: "different")

    with pytest.raises(ValueError, match="hash mismatch"):
        profile._verify_artifact_dict(payload)

    opt.unlink()
    with pytest.raises(FileNotFoundError):
        profile._verify_artifact_dict(payload)


def test_subprocess_output_streaming_and_failure_tail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeProcess:
        def __init__(self, *_args, **_kwargs):
            pass

        def wait(self, timeout=None):  # noqa: ANN001
            return 2

    monkeypatch.setattr(profile.subprocess, "Popen", FakeProcess)

    with pytest.raises(RuntimeError, match="prepare worker failed"):
        profile._run_worker_subprocess(
            "prepare",
            case=profile.H4_CASE,
            cache_root=tmp_path / "cache",
            run_dir=tmp_path,
            batch_size=2,
            sample_interval_sec=0.02,
        )

    assert (tmp_path / "prepare_worker.stdout.log").exists()
    assert (tmp_path / "prepare_worker.stderr.log").exists()


def test_worker_success_loads_result_without_stdout_retention(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result_path = tmp_path / "prepare_worker_result.json"

    class FakeProcess:
        def __init__(self, cmd, cwd=None, stdout=None, stderr=None, close_fds=True):  # noqa: ANN001
            result_path.write_text(json.dumps({"status": "ok"}), encoding="utf-8")
            if stdout is not None:
                stdout.write(b"hello")

        def wait(self, timeout=None):  # noqa: ANN001
            return 0

    monkeypatch.setattr(profile.subprocess, "Popen", FakeProcess)

    result = profile._run_worker_subprocess(
        "prepare",
        case=profile.H4_CASE,
        cache_root=tmp_path / "cache",
        run_dir=tmp_path,
        batch_size=2,
        sample_interval_sec=0.02,
    )

    assert result["status"] == "ok"
    assert "stdout" not in result
    assert result["worker_stdout_size_bytes"] == 5


def test_worker_pid_classification() -> None:
    assert profile._classify_command("python profile_surface_code_lightweight_tree_memory.py --worker prepare") == "prepare_worker"
    assert profile._classify_command("python profile_surface_code_lightweight_tree_memory.py --worker compile") == "compile_worker"
    assert profile._classify_command("/repo/build/quration/qret compile") == "qret"


def test_light_sampler_streams_without_rows_in_summary(tmp_path: Path) -> None:
    result, summary, guard = profile.parent_profile._run_with_streaming_tree_sampler(
        lambda: "ok",
        samples_path=tmp_path / "samples.jsonl",
        interval_sec=0.001,
        memtotal_kb=10_000_000,
    )

    assert result == "ok"
    assert summary["sample_count"] >= 1
    assert "rows" not in summary
    assert guard["triggered"] is False


def test_simultaneous_tree_peak_from_samples() -> None:
    rows = [
        {"sample_index": 0, "root_pid": 10, "pid": 10, "command": "python", "vmrss_kb": 100, "tree_vmrss_kb": 100},
        {"sample_index": 1, "root_pid": 10, "pid": 10, "command": "python", "vmrss_kb": 200, "tree_vmrss_kb": 700},
        {"sample_index": 1, "root_pid": 10, "pid": 20, "command": "/x/qret compile", "vmrss_kb": 500, "tree_vmrss_kb": 700},
    ]

    summary = profile.parent_profile._summarize_sample_rows(rows)

    assert summary["tree_peak_split"]["parent_vmrss_kb"] == 200
    assert summary["tree_peak_split"]["qret_vmrss_kb"] == 500


def test_raw_normalized_and_cache_comparisons() -> None:
    left = {
        "artifact": {"qasm_hash": "q", "ir_hash": "i", "optimized_ir_hash": "o", "instruction_count": 1, "gate_depth": 2},
        "raw_resource_metrics": {"runtime": 1, "compile_info_json": "/a"},
        "metrics": {
            "runtime": 1,
            "compile_info_json": "/a",
            "compile_wall_time_sec": 1,
            "cache_key": "c",
            "qasm_hash": "q",
            "optimized_ir_hash": "o",
            "compiler_executable_hash": "e",
            "compiler_core_library_hash": "l",
            "topology_hash": "t",
        },
    }
    right = {
        **left,
        "raw_resource_metrics": {"runtime": 1, "compile_info_json": "/b"},
        "metrics": {**left["metrics"], "compile_info_json": "/b", "compile_wall_time_sec": 2},
    }

    comparison = profile._semantic_comparison(left, right)

    assert comparison["artifact_hashes"]["all_equal"]
    assert comparison["raw_metrics"]["all_equal"]
    assert comparison["normalized_metrics"]["all_equal"]


def test_h4_h5_case_names_are_supported() -> None:
    assert profile._case_parameters(profile.H4_CASE)["chain_length"] == 4
    assert profile._case_parameters(profile.H5_CASE)["chain_length"] == 5


def test_report_generation_mentions_final_answers(tmp_path: Path) -> None:
    report = tmp_path / "report.md"
    payload = {
        "light_baseline": {
            "tree_peak_rss_kb": 100,
            "elapsed_seconds": 1.0,
            "tree_peak_split": {"parent_vmrss_kb": 20, "qret_vmrss_kb": 80},
            "prepare_stage_peak": {"python_sampled_peak_rss_kb": 90},
        },
        "deep_reference": {"tree_peak_rss_kb": 120, "parent_at_tree_peak_kb": 30, "elapsed_seconds": 1.2},
        "deep_vs_light": {"tree_peak_delta_kb": -20, "parent_at_tree_delta_kb": -10, "elapsed_delta_seconds": -0.2},
        "process_isolation_gate": {"passes": False, "reasons": [], "before_qret_parent_rss_kb": 20, "prepare_retained_delta_kb": 5},
        "process_isolation_implemented": False,
        "h4_correctness": {},
        "h5_ab": {},
        "semantic_comparisons": {},
        "process_isolation_decision": {"production_default": False, "production_default_reason": "test"},
        "validation": {"pytest": "passed"},
    }

    profile._write_report(report, payload)
    text = report.read_text(encoding="utf-8")

    assert "Profiling Overhead Audit" in text
    assert "Final Answers" in text
    assert "H6は実行していません" in text


def test_qret_and_library_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeArchitecture:
        compile_mode = profile.parent_profile.COMPILE_MODE
        qret_path = Path("/tmp/qret")
        topology_path = Path("/tmp/topology")
        skip_compile_output = True
        compile_info_output_mode = "summary"

        def to_dict(self) -> dict[str, object]:
            return {"compile_mode": self.compile_mode}

    monkeypatch.setattr(
        profile.sc,
        "qret_runtime_hashes",
        lambda _path: {
            "qret_executable_hash": "exe",
            "qret_core_library_hash": "lib",
            "qret_executable_path": "/tmp/qret",
            "qret_core_library_path": "/tmp/lib",
        },
    )
    monkeypatch.setattr(profile.sc, "file_sha256", lambda _path: "hash")

    provenance = profile._runtime_provenance(FakeArchitecture())  # type: ignore[arg-type]

    assert provenance["qret_executable_hash"] == "exe"
    assert provenance["qret_core_library_hash"] == "lib"
