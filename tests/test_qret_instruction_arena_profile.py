from __future__ import annotations

from pathlib import Path

import pytest

import scripts.profile_qret_instruction_arena as arena


def _row(stage: str, *, vmrss: int = 100, allocs: int = 0, requested: int = 0) -> dict[str, object]:
    return {
        "stage": stage,
        "vmrss_kb": vmrss,
        "vmhwm_kb": vmrss,
        "extra": {
            "machine_instruction_allocation_mode": "arena" if allocs else "legacy",
            "machine_instruction_arena_enabled": bool(allocs),
            "machine_instruction_arena_allocation_count": allocs,
            "machine_instruction_arena_deallocation_count": 0,
            "machine_instruction_arena_live_allocations": allocs,
            "machine_instruction_arena_requested_bytes": requested,
            "machine_instruction_arena_used_bytes": requested + 8,
            "machine_instruction_arena_reserved_bytes": 1024,
            "machine_instruction_arena_internal_fragmentation_bytes": 8,
            "machine_instruction_arena_reserved_unused_bytes": max(0, 1024 - requested - 8),
            "machine_instruction_arena_chunk_count": 1 if allocs else 0,
            "machine_instruction_legacy_allocator_metadata_model_bytes": allocs * 16,
            "machine_instructions": allocs,
            "machine_instruction_type_count": {"DUMMY": allocs},
        },
    }


def _result(case: str, variant: str, run: int, peak: int, elapsed: float) -> dict[str, object]:
    profile_rows = [
        _row("after_machine_function_construction", vmrss=peak, allocs=10, requested=1000),
        _row(
            "mf_pass_after",
            vmrss=peak,
            allocs=10,
            requested=1000,
        )
        | {"extra": {"pass_argument": "sc_ls_fixed_v0::routing", "elapsed_ms": 7}},
    ]
    return {
        "case": case,
        "variant": variant,
        "run_index": run,
        "qret_peak_rss_kb": peak,
        "tree_peak_rss_kb": peak + 10,
        "elapsed_seconds": elapsed,
        "profile_rows": profile_rows,
        "arena_stats": arena._arena_stats(profile_rows),
        "raw_resource_metrics": {
            "runtime": 1,
            "gate_count": 2,
            "gate_depth": 3,
            "magic_state_consumption_count": 4,
            "magic_state_consumption_depth": 5,
            "qubit_volume": 6,
            "num_physical_qubits": 7,
            "code_distance": 8,
        },
        "normalized_metrics": {
            "runtime": 1,
            "gate_count": 2,
            "compile_info_json": f"/tmp/{case}-{variant}-{run}.json",
        },
        "depgraph_nodes": 10,
        "depgraph_edges": 11,
        "pipeline_state_output_skipped": True,
    }


def test_validate_rejects_h6_to_h9_by_name_and_chain_length() -> None:
    assert arena._validate_cases(["h4_4th_new2", "h5_4th_new2"]) == (
        "h4_4th_new2",
        "h5_4th_new2",
    )
    for case in ("h6_4th_new2", "h7_4th_new2", "h8_4th_new2", "h9_4th_new2"):
        with pytest.raises(ValueError, match="H6/H7/H8/H9"):
            arena._validate_cases([case])
    for length in (6, 7, 8, 9):
        with pytest.raises(ValueError, match="H6/H7/H8/H9"):
            arena._validate_chain_lengths([length])


def test_h5_requires_h4_parity_in_same_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(arena.live_profile, "_disk_free_bytes", lambda _path: arena.MIN_FREE_DISK_BYTES)

    with pytest.raises(ValueError, match="H5 measurement requires H4"):
        arena.run_profile(
            output_root=tmp_path / "out",
            report_path=tmp_path / "report.md",
            cache_root=tmp_path / "cache",
            build=False,
            cases=("h5_4th_new2",),
            variants=None,
            batch_size=1,
            sample_interval_sec=0.02,
        )


def test_variant_env_sets_production_and_allocation_mode(tmp_path: Path) -> None:
    env = {"QRET_MAGIC_PATH_PROFILE_JSON": "old"}
    arena._variant_env(env, "arena", tmp_path / "profile.jsonl")

    assert env["QRET_MAGIC_PATH_STORAGE"] == "interned"
    assert env["QRET_SUMMARY_TIME_SERIES_IMPL"] == "legacy_timeseries"
    assert env["QRET_DEP_GRAPH_IMPL"] == "compact"
    assert env["QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING"] == "1"
    assert env["QRET_INVERSE_MAP_CONSTRUCTION"] == "eager"
    assert env["QRET_INSTRUCTION_ALLOCATION"] == "arena"
    assert env["QRET_PROFILE_HIGH_WATER"] == "1"
    assert "QRET_MAGIC_PATH_PROFILE_JSON" not in env


def test_arena_stats_selects_highest_allocation_count() -> None:
    stats = arena._arena_stats(
        [
            _row("a", allocs=1, requested=10),
            _row("b", allocs=5, requested=50),
            _row("c", allocs=2, requested=20),
        ]
    )

    assert stats["allocation_count"] == 5
    assert stats["requested_bytes"] == 50
    assert stats["internal_fragmentation_bytes"] == 8


def test_gate_rejects_small_or_noisy_peak_delta() -> None:
    results = [
        _result("h4_4th_new2", "legacy", 1, 1000, 1.0),
        _result("h4_4th_new2", "arena", 1, 995, 1.0),
        _result("h5_4th_new2", "legacy", 1, 500_000, 10.0),
        _result("h5_4th_new2", "legacy", 2, 501_000, 10.1),
        _result("h5_4th_new2", "arena", 1, 499_000, 10.0),
        _result("h5_4th_new2", "arena", 2, 498_000, 10.1),
    ]
    comparisons = arena._metric_comparisons(results)
    semantic = arena._semantic_comparisons(results)
    decision = arena._gate_decision(results, comparisons, semantic)

    assert decision["arena_status"] == "rejected"
    assert decision["production_default"] == "legacy"
    assert decision["peak_gate"] is False


def test_gate_adopts_only_when_peak_elapsed_and_parity_pass() -> None:
    results = [
        _result("h4_4th_new2", "legacy", 1, 1000, 1.0),
        _result("h4_4th_new2", "arena", 1, 900, 1.0),
        _result("h5_4th_new2", "legacy", 1, 500_000, 10.0),
        _result("h5_4th_new2", "legacy", 2, 501_000, 10.1),
        _result("h5_4th_new2", "arena", 1, 450_000, 10.2),
        _result("h5_4th_new2", "arena", 2, 451_000, 10.2),
    ]
    comparisons = arena._metric_comparisons(results)
    semantic = arena._semantic_comparisons(results)
    decision = arena._gate_decision(results, comparisons, semantic)

    assert decision["arena_status"] == "adopted"
    assert decision["production_default"] == "arena"
    assert decision["peak_gate"] is True
    assert decision["elapsed_gate"] is True


def test_report_generation_mentions_status_and_classification(tmp_path: Path) -> None:
    results = [
        _result("h4_4th_new2", "legacy", 1, 1000, 1.0),
        _result("h4_4th_new2", "arena", 1, 995, 1.0),
        _result("h5_4th_new2", "legacy", 1, 500_000, 10.0),
        _result("h5_4th_new2", "legacy", 2, 501_000, 10.1),
        _result("h5_4th_new2", "arena", 1, 499_000, 10.0),
        _result("h5_4th_new2", "arena", 2, 498_000, 10.1),
    ]
    comparisons = arena._metric_comparisons(results)
    semantic = arena._semantic_comparisons(results)
    summary = {
        "results": results,
        "comparisons": comparisons,
        "semantic_comparisons": semantic,
        "decision": arena._gate_decision(results, comparisons, semantic),
    }
    report = tmp_path / "arena.md"

    arena._write_report(report, summary=summary)
    text = report.read_text(encoding="utf-8")

    assert "arena status: `rejected`" in text
    assert "classification" in text
    assert "H9 memory: not measured" in text
