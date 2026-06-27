from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "profile_surface_code_compact_scaling.py"
)


def _load_module():
    scripts_root = Path(__file__).resolve().parents[1] / "scripts"
    if str(scripts_root) not in sys.path:
        sys.path.insert(0, str(scripts_root))
    spec = importlib.util.spec_from_file_location(
        "profile_surface_code_compact_scaling",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_scaling_sampler_summary_separates_parent_qret_and_tree_peak() -> None:
    module = _load_module()
    summary = module._summarize_samples(
        [
            {
                "pid": 10,
                "command": "python profile_surface_code_compact_scaling.py",
                "vmrss_kb": 100,
                "tree_vmrss_kb": 150,
                "mem_available_kb": 9000,
                "swap_total_kb": 1000,
                "swap_free_kb": 1000,
                "sample_index": 0,
            },
            {
                "pid": 11,
                "command": "/repo/build/quration/qret compile",
                "vmrss_kb": 300,
                "tree_vmrss_kb": 450,
                "mem_available_kb": 8000,
                "swap_total_kb": 1000,
                "swap_free_kb": 990,
                "sample_index": 1,
            },
        ],
        parent_pid=10,
    )
    assert summary["sampled_peak_tree_vmrss_kb"] == 450
    assert summary["sampled_peak_qret_vmrss_kb"] == 300
    assert summary["sampled_peak_parent_vmrss_kb"] == 100
    assert summary["minimum_mem_available_kb"] == 8000
    assert summary["maximum_swap_used_kb"] == 10
    assert summary["maximum_swap_free_drop_kb"] == 10


def test_scaling_metric_compare_ignores_paths_and_execution_time() -> None:
    module = _load_module()
    comparison = module._compare_metrics(
        [
            {
                "compile_info_json": "/tmp/a.json",
                "execution_time_sec": 1.0,
                "runtime": 10,
                "gate_count": 20,
            },
            {
                "compile_info_json": "/tmp/b.json",
                "execution_time_sec": 2.0,
                "runtime": 10,
                "gate_count": 20,
            },
        ]
    )
    assert comparison["all_equal"] is True
    assert comparison["semantic_fields"]["runtime"]["equal"] is True


def test_h6_safety_rejects_low_mem_available(tmp_path: Path) -> None:
    module = _load_module()
    decision = module._safety_for_h6(
        h4_results=[
            {
                "phase": "isolated_qret",
                "qret_peak_rss_kb": 100,
                "depgraph_nodes": 10,
            }
        ],
        h5_results=[
            {
                "phase": "isolated_qret",
                "status": "ok",
                "returncode": 0,
                "normalized_metrics": {"runtime": 1},
                "qret_peak_rss_kb": 200,
                "tree_peak_rss_kb": 300,
                "min_mem_available_kb": 100,
                "max_swap_used_kb": 0,
                "guard": {"triggered": False},
            }
        ],
        memtotal_kb=10_000,
        output_root=tmp_path,
    )
    assert decision["proceed_to_h6"] is False
    assert "mem_available_over_2gib" in decision["failed_conditions"]
