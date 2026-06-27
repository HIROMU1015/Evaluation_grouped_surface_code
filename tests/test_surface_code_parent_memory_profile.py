from __future__ import annotations

from pathlib import Path

import pytest

import scripts.profile_surface_code_parent_memory as profile


def _sample(
    *,
    index: int,
    parent: int,
    qret: int = 0,
    other: int = 0,
    mem_available: int = 8_000_000,
) -> list[dict[str, object]]:
    tree = parent + qret + other
    rows: list[dict[str, object]] = [
        {
            "sample_index": index,
            "timestamp_seconds": float(index),
            "root_pid": 10,
            "pid": 10,
            "ppid": 1,
            "command": "python scripts/profile_surface_code_parent_memory.py",
            "vmrss_kb": parent,
            "tree_vmrss_kb": tree,
            "mem_available_kb": mem_available,
            "swap_total_kb": 1000,
            "swap_free_kb": 1000,
        }
    ]
    if qret:
        rows.append(
            {
                "sample_index": index,
                "timestamp_seconds": float(index),
                "root_pid": 10,
                "pid": 20,
                "ppid": 19,
                "command": "/repo/build/quration/qret compile --pipeline compile.yaml",
                "vmrss_kb": qret,
                "tree_vmrss_kb": tree,
                "mem_available_kb": mem_available,
                "swap_total_kb": 1000,
                "swap_free_kb": 990,
            }
        )
    if other:
        rows.append(
            {
                "sample_index": index,
                "timestamp_seconds": float(index),
                "root_pid": 10,
                "pid": 19,
                "ppid": 10,
                "command": "/usr/bin/time -v qret",
                "vmrss_kb": other,
                "tree_vmrss_kb": tree,
                "mem_available_kb": mem_available,
                "swap_total_kb": 1000,
                "swap_free_kb": 990,
            }
        )
    return rows


def test_online_tree_summary_uses_simultaneous_tree_peak_and_classifies_processes() -> None:
    summary = profile.OnlineTreeSummary(parent_pid=10)
    summary.update(_sample(index=0, parent=100_000))
    summary.update(_sample(index=1, parent=210_000, qret=540_000, other=500))
    summary.update(_sample(index=2, parent=220_000, qret=520_000, other=400))

    data = summary.summary()
    split = data["tree_peak_split"]

    assert data["sampled_peak_tree_vmrss_kb"] == 750_500
    assert split["sample_index"] == 1
    assert split["parent_vmrss_kb"] == 210_000
    assert split["qret_vmrss_kb"] == 540_000
    assert split["other_vmrss_kb"] == 500
    assert data["sampled_peak_parent_vmrss_kb"] == 220_000
    assert data["sampled_peak_qret_vmrss_kb"] == 540_000


def test_qret_window_parent_rss_records_before_after_and_increase() -> None:
    summary = profile.OnlineTreeSummary(parent_pid=10)
    summary.update(_sample(index=0, parent=100_000))
    summary.update(_sample(index=1, parent=180_000, qret=500_000))
    summary.update(_sample(index=2, parent=190_000, qret=510_000))
    summary.update(_sample(index=3, parent=120_000))

    window = summary.summary()["qret_window"]

    assert window["parent_before_qret_launch_kb"] == 100_000
    assert window["parent_after_qret_launch_kb"] == 180_000
    assert window["parent_before_qret_exit_kb"] == 190_000
    assert window["parent_after_qret_exit_kb"] == 120_000
    assert window["parent_rss_increase_during_qret_kb"] == 90_000


def test_qret_window_selects_window_containing_tree_peak() -> None:
    summary = profile.OnlineTreeSummary(parent_pid=10)
    summary.update(_sample(index=0, parent=100_000))
    summary.update(_sample(index=1, parent=110_000, qret=12_000))
    summary.update(_sample(index=2, parent=120_000))
    summary.update(_sample(index=3, parent=650_000))
    summary.update(_sample(index=4, parent=650_000, qret=570_000))
    summary.update(_sample(index=5, parent=660_000, qret=560_000))
    summary.update(_sample(index=6, parent=690_000))

    window = summary.summary()["qret_window"]

    assert window["qret_first_sample_index"] == 4
    assert window["qret_last_sample_index"] == 5
    assert window["selected_window_reason"] == "contains_tree_peak_sample"
    assert window["qret_window_count"] == 2
    assert window["parent_before_qret_launch_kb"] == 650_000


def test_parent_gate_decision_covers_thresholds() -> None:
    summary = {
        "tree_peak_split": {"tree_vmrss_kb": 800_000, "parent_vmrss_kb": 210_000},
        "qret_window": {"parent_rss_increase_during_qret_kb": 10_000},
    }
    decision = profile._parent_gate_decision(summary)

    assert decision["passes"] is True
    assert "parent_at_tree_peak_ge_200mb" in decision["reasons"]
    assert "parent_share_ge_25pct" in decision["reasons"]


def test_parent_gate_decision_can_fail_cleanly() -> None:
    summary = {
        "tree_peak_split": {"tree_vmrss_kb": 800_000, "parent_vmrss_kb": 120_000},
        "qret_window": {"parent_rss_increase_during_qret_kb": 10_000},
    }

    assert profile._parent_gate_decision(summary)["passes"] is False


def test_h6_case_is_not_runnable() -> None:
    assert profile._validate_cases(("h4_4th_new2", "h5_4th_new2")) == (
        "h4_4th_new2",
        "h5_4th_new2",
    )
    with pytest.raises(ValueError, match="H6"):
        profile._validate_cases(("h6_4th_new2",))


def test_recursive_size_handles_cycles() -> None:
    value: list[object] = []
    value.append(value)

    size = profile._recursive_size_bytes(value)

    assert isinstance(size, int)
    assert size > 0


def test_numpy_nbytes_and_optional_missing_object_are_reported() -> None:
    class FakeArray:
        nbytes = 1234

    estimate = profile._estimate_object("array", {"array": FakeArray()})
    missing = profile._estimate_object("missing", None)

    assert estimate["numpy_payload_bytes"] == 1234
    assert missing["present"] is False
    assert missing["recursive_size_bytes"] is None


def test_streaming_sampler_writes_jsonl_without_returning_raw_rows(tmp_path: Path) -> None:
    path = tmp_path / "samples.jsonl"

    result, summary, guard = profile._run_with_streaming_tree_sampler(
        lambda: "ok",
        samples_path=path,
        interval_sec=0.001,
        memtotal_kb=10_000_000,
    )

    assert result == "ok"
    assert path.exists()
    assert summary["sample_count"] >= 1
    assert "rows" not in summary
    assert guard["triggered"] is False


def test_subprocess_output_buffer_assessment_flags_only_large_buffers() -> None:
    small = profile._subprocess_output_buffer_assessment(
        stdout_bytes=100,
        stderr_bytes=200,
        large_threshold_bytes=1000,
    )
    large = profile._subprocess_output_buffer_assessment(
        stdout_bytes=700,
        stderr_bytes=400,
        large_threshold_bytes=1000,
    )

    assert small["large_buffer_risk"] is False
    assert large["large_buffer_risk"] is True


def test_metric_hash_and_cache_comparisons_ignore_expected_fields() -> None:
    left = {
        "runtime": 1,
        "gate_count": 2,
        "compile_info_json": "/tmp/a.json",
        "compile_wall_time_sec": 10.0,
        "cache_key": "cache",
        "qasm_hash": "qasm",
        "optimized_ir_hash": "ir",
        "compiler_executable_hash": "exe",
        "compiler_core_library_hash": "lib",
        "topology_hash": "topo",
    }
    right = {
        **left,
        "compile_info_json": "/tmp/b.json",
        "compile_wall_time_sec": 11.0,
    }

    assert profile._compare_metrics(left, right)["all_equal"] is True
    assert profile._compare_hashes(left, right, keys=("optimized_ir_hash",))[
        "all_equal"
    ]
    assert profile._cache_semantics_equal(left, right)


def test_report_generation_mentions_h6_and_next_qret_candidate(tmp_path: Path) -> None:
    report = tmp_path / "report.md"
    payload = {
        "evaluation_head": "head",
        "production_change_adopted": False,
        "result": {
            "elapsed_seconds": 1.0,
            "compile_info_size_bytes": 100,
            "samples_path": "/tmp/samples.jsonl",
            "markers_path": "/tmp/markers.jsonl",
            "stage_metrics_path": "/tmp/stages.jsonl",
            "tree_peak_split": {
                "tree_vmrss_kb": 800_000,
                "parent_vmrss_kb": 120_000,
                "qret_vmrss_kb": 679_000,
                "other_vmrss_kb": 1_000,
                "sample_index": 4,
            },
            "qret_window": {"parent_rss_increase_during_qret_kb": 10_000},
            "gate": {"passes": False, "reasons": []},
            "object_audit": {"largest_objects": []},
            "qret_stage": {"result": {"subprocess_maxrss_kb": 680_000}},
            "read_compile_info_stage": {"python_sampled_peak_rss_kb": 130_000},
            "subprocess_output_buffer": {"total_bytes": 300},
        },
    }

    profile._write_report(report, payload)
    text = report.read_text(encoding="utf-8")

    assert "H6 was not run" in text
    assert "No Python parent production change" in text
    assert "LATTICE_SURGERY_MAGIC" in text


def test_runtime_provenance_includes_qret_and_library_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeArchitecture:
        compile_mode = profile.COMPILE_MODE
        qret_path = Path("/tmp/qret")
        topology_path = Path("/tmp/topology.yaml")
        skip_compile_output = True
        compile_info_output_mode = "summary"

        def to_dict(self) -> dict[str, object]:
            return {"compile_mode": self.compile_mode}

    monkeypatch.setattr(
        profile.sc,
        "qret_runtime_hashes",
        lambda _path: {
            "qret_executable_path": "/tmp/qret",
            "qret_executable_hash": "exe",
            "qret_core_library_path": "/tmp/lib.so",
            "qret_core_library_hash": "lib",
        },
    )
    monkeypatch.setattr(profile.sc, "file_sha256", lambda _path: "topo")

    provenance = profile._runtime_provenance(architecture=FakeArchitecture())  # type: ignore[arg-type]

    assert provenance["qret_executable_hash"] == "exe"
    assert provenance["qret_core_library_hash"] == "lib"
    assert provenance["topology_hash"] in {None, "topo"}
