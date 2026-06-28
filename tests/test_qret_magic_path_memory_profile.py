from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.profile_qret_magic_path_memory as profile


def test_validate_cases_rejects_h6() -> None:
    assert profile._validate_cases(["h4_4th_new2", "h5_4th_new2"]) == (
        "h4_4th_new2",
        "h5_4th_new2",
    )
    with pytest.raises(ValueError, match="H6"):
        profile._validate_cases(["h6_4th_new2"])


def test_profile_env_is_opt_in(tmp_path: Path) -> None:
    env: dict[str, str] = {"QRET_MAGIC_PATH_PROFILE_JSON": "old"}
    profile._profile_env(env, enabled=False, magic_profile_path=tmp_path / "magic.json")
    assert env["QRET_PROFILE_MAGIC_PATHS"] == "0"
    assert "QRET_MAGIC_PATH_PROFILE_JSON" not in env
    assert env["QRET_SUMMARY_TIME_SERIES_IMPL"] == "legacy_timeseries"
    assert env["QRET_DEP_GRAPH_IMPL"] == "compact"
    assert env["QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING"] == "1"

    profile._profile_env(env, enabled=True, magic_profile_path=tmp_path / "magic.json")
    assert env["QRET_PROFILE_MAGIC_PATHS"] == "1"
    assert env["QRET_MAGIC_PATH_PROFILE_JSON"] == str(tmp_path / "magic.json")


def test_load_magic_profile_prefers_json_file(tmp_path: Path) -> None:
    path = tmp_path / "magic.json"
    path.write_text(json.dumps({"path_count": 3}), encoding="utf-8")
    rows = [{"stage": "magic_path_profile", "extra": {"path_count": 1}}]

    assert profile._load_magic_profile(path, rows)["path_count"] == 3


def test_load_magic_profile_falls_back_to_rss_marker(tmp_path: Path) -> None:
    rows = [{"stage": "magic_path_profile", "extra": {"path_count": 5}}]

    assert profile._load_magic_profile(tmp_path / "missing.json", rows)["path_count"] == 5


def test_compare_metrics_ignores_compile_info_json_path() -> None:
    left = {
        "raw_resource_metrics": {"a": 1},
        "normalized_metrics": {"x": 2, "compile_info_json": "left"},
    }
    right = {
        "raw_resource_metrics": {"a": 1},
        "normalized_metrics": {"x": 2, "compile_info_json": "right"},
    }

    comparison = profile._compare_metrics(left, right)

    assert comparison["raw"]["all_equal"] is True
    assert comparison["normalized"]["all_equal"] is True


def test_candidate_ranking_limits_to_two_and_prefers_low_risk() -> None:
    mock_profile = {
        "representation_estimates": {
            "current_list_aligned_bytes": 100 * profile.ONE_MB,
            "rows": [
                {
                    "representation": "std::list<Coord3D> current aligned estimate",
                    "estimated_bytes": 100 * profile.ONE_MB,
                    "saving_bytes": 0,
                    "semantic_risk": "none",
                    "implementation_risk": "none",
                },
                {
                    "representation": "relative shape pool + origin",
                    "estimated_bytes": 20 * profile.ONE_MB,
                    "saving_bytes": 80 * profile.ONE_MB,
                    "semantic_risk": "medium",
                    "implementation_risk": "high",
                },
                {
                    "representation": "std::vector<Coord3D> capacity==size",
                    "estimated_bytes": 55 * profile.ONE_MB,
                    "saving_bytes": 45 * profile.ONE_MB,
                    "semantic_risk": "low",
                    "implementation_risk": "low",
                },
                {
                    "representation": "flat pool + offset no sharing",
                    "estimated_bytes": 40 * profile.ONE_MB,
                    "saving_bytes": 60 * profile.ONE_MB,
                    "semantic_risk": "low",
                    "implementation_risk": "medium",
                },
                {
                    "representation": "flat pool + exact path interning",
                    "estimated_bytes": 15 * profile.ONE_MB,
                    "saving_bytes": 85 * profile.ONE_MB,
                    "semantic_risk": "low",
                    "implementation_risk": "medium",
                },
            ],
        }
    }

    ranking = profile._candidate_ranking(mock_profile, qret_peak_rss_kb=600_000)

    assert [row["candidate"] for row in ranking] == [
        "std::vector<Coord3D>",
        "flat pool + exact path interning",
    ]
    assert ranking[0]["scenario"] == "std::vector<Coord3D> capacity==size"
    assert all(row["passes_gate"] for row in ranking)


def test_report_mentions_observed_estimated_theoretical_and_h6(tmp_path: Path) -> None:
    report = tmp_path / "report.md"
    summary = {
        "environment": {
            "evaluation_head": "abc",
            "runtime_hashes": {
                "qret_executable_hash": "qret",
                "qret_core_library_hash": "lib",
            },
            "output_root": str(tmp_path),
            "sample_interval_sec": 0.02,
        },
        "results": [
            {
                "case": "h4_4th_new2",
                "variant": "profile_off",
                "qret_peak_rss_kb": 10,
                "elapsed_seconds": 1.0,
                "magic_path_profile_present": False,
            },
            {
                "case": "h4_4th_new2",
                "variant": "profile_on",
                "qret_peak_rss_kb": 11,
                "elapsed_seconds": 1.1,
                "magic_path_profile_present": True,
                "magic_path_profile": {"path_count": 1},
            },
            {
                "case": "h5_4th_new2",
                "variant": "profile_on",
                "qret_peak_rss_kb": 12,
                "tree_peak_rss_kb": 13,
                "elapsed_seconds": 1.2,
                "max_rss_stage": "magic_path_profile",
                "compile_info_size_bytes": 123,
                "magic_path_profile": {
                    "path_count": 1,
                    "total_coordinate_count": 2,
                    "length_buckets": {"length_2": 1},
                    "coordinates": {
                        "x": {},
                        "y": {},
                        "z": {},
                        "dx": {},
                        "dy": {},
                        "dz": {},
                    },
                    "segments": {},
                    "representation_estimates": {"rows": []},
                    "magic_operand_memory": {},
                    "all_machine_ancilla_path_memory": {},
                },
            },
        ],
        "comparisons": {
            "h4_profile_on_vs_off": {
                "raw": {"all_equal": True},
                "normalized": {"all_equal": True},
            }
        },
        "candidate_ranking": [],
    }

    profile._write_report(report, summary)
    text = report.read_text(encoding="utf-8")

    assert "observed count" in text
    assert "estimated bytes" in text
    assert "Theoretical Representation Sizes" in text
    assert "H6 was not run" in text
