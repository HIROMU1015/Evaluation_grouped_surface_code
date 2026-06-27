from __future__ import annotations

from pathlib import Path

import scripts.profile_qret_timeseries_memory as profile


def _row(case: str, variant: str, peak: int, elapsed: float) -> dict[str, object]:
    metrics = {
        "gate_count": 1,
        "execution_time_sec": 2.0,
        "estimated_execution_time_sec": 2.0,
    }
    return {
        "case": case,
        "phase": "isolated_qret",
        "variant": variant,
        "qret_peak_rss_kb": peak,
        "elapsed_seconds": elapsed,
        "normalized_metrics": metrics,
        "raw_resource_metrics": metrics,
    }


def test_timeseries_variants_and_defaults() -> None:
    assert profile.VARIANTS["summary_legacy_timeseries"]["summary_impl"] == "legacy_timeseries"
    assert profile.VARIANTS["summary_compact_timeseries"]["summary_impl"] == "compact_timeseries"
    assert profile.VARIANTS["summary_event_sweep"]["summary_impl"] == "event_sweep"
    assert profile.DEFAULT_ISOLATED_RUNS["h4_4th_new2"]["full"] == 1
    assert profile.DEFAULT_ISOLATED_RUNS["h4_4th_new2"]["summary_event_sweep"] == 3
    assert profile.DEFAULT_ISOLATED_RUNS["h6_4th_new2"]["summary_compact_timeseries"] == 1


def test_h5_candidate_selection_prefers_event_sweep_when_compact_is_not_close() -> None:
    rows = [
        _row("h4_4th_new2", "full", 300_000, 3.0),
        _row("h4_4th_new2", "summary_legacy_timeseries", 270_000, 3.0),
        _row("h4_4th_new2", "summary_compact_timeseries", 260_000, 3.0),
        _row("h4_4th_new2", "summary_event_sweep", 230_000, 3.0),
    ]
    comparisons = profile._build_comparisons(rows)

    assert profile._select_h5_candidates(rows, comparisons) == ["summary_event_sweep"]


def test_h6_gate_requires_h5_savings_and_elapsed() -> None:
    rows = [
        _row("h5_4th_new2", "summary_legacy_timeseries", 700_000, 10.0),
        _row("h5_4th_new2", "summary_event_sweep", 640_000, 10.4),
    ]
    comparisons = profile._build_comparisons(rows)

    candidate, decisions = profile._select_h6_candidate(
        rows,
        comparisons,
        ["summary_event_sweep"],
    )

    assert candidate == "summary_event_sweep"
    assert decisions["summary_event_sweep"]["passes_h6_gate"] is True


def test_report_generation_records_execution_plan(tmp_path: Path) -> None:
    report = tmp_path / "report.md"
    rows = [
        _row("h4_4th_new2", "full", 300_000, 3.0),
        _row("h4_4th_new2", "summary_legacy_timeseries", 270_000, 3.0),
        _row("h4_4th_new2", "summary_event_sweep", 230_000, 2.9),
    ]
    comparisons = profile._build_comparisons(rows)

    profile._write_report(
        report,
        environment={
            "evaluation_head": "head",
            "measurement_runtime_hashes": {},
            "meminfo": {},
            "batch_size": 2,
            "sample_interval_sec": 0.02,
            "output_root": str(tmp_path),
        },
        build_provenance={},
        results=rows,
        comparisons=comparisons,
        execution_plan={
            "h5_candidates": ["summary_event_sweep"],
            "h6_candidate": "summary_event_sweep",
            "h6_decisions": {},
            "h6_headroom": {},
        },
    )

    text = report.read_text(encoding="utf-8")
    assert "# qret TimeSeries Memory Optimization" in text
    assert "summary_event_sweep" in text
    assert "H5 candidates" in text
    assert "Current production default remains `summary_legacy_timeseries`" in text
