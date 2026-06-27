from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "profile_qret_pre_routing_memory.py"
)
SKIP_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "profile_qret_skip_pipeline_output.py"
)
CALC_INFO_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "profile_qret_calc_info_memory.py"
)


def _load_script_module(path: Path = SCRIPT_PATH, name: str = "profile_qret_pre_routing_memory"):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parse_gnu_time_maxrss() -> None:
    module = _load_script_module()
    stderr = "\n".join(
        [
            "User time (seconds): 1.23",
            "Maximum resident set size (kbytes): 123456",
        ]
    )
    assert module._parse_gnu_time_maxrss(stderr) == 123456


def test_build_pipeline_yaml_uses_requested_passes(tmp_path: Path) -> None:
    module = _load_script_module()
    yaml_text = module._build_pipeline_yaml(
        opt_path=tmp_path / "step_opt.json",
        output_path=Path("/dev/null"),
        compile_info_path=tmp_path / "compile_info.json",
        topology_path=tmp_path / "topology.yaml",
        passes=["sc_ls_fixed_v0::init_compile_info", "sc_ls_fixed_v0::mapping"],
    )
    assert "input: " in yaml_text
    assert "sc_ls_fixed_v0_pass:" in yaml_text
    assert "  - sc_ls_fixed_v0::init_compile_info" in yaml_text
    assert "  - sc_ls_fixed_v0::mapping" in yaml_text


def test_build_pipeline_yaml_can_set_skip_pipeline_state_flag(tmp_path: Path) -> None:
    module = _load_script_module()
    yaml_text = module._build_pipeline_yaml(
        opt_path=tmp_path / "step_opt.json",
        output_path=tmp_path / "step_sc_ls_fixed_v0.json",
        compile_info_path=tmp_path / "compile_info.json",
        topology_path=tmp_path / "topology.yaml",
        passes=["sc_ls_fixed_v0::init_compile_info"],
        skip_pipeline_state_output=True,
    )
    assert "sc_ls_fixed_v0_skip_pipeline_state_output: true" in yaml_text


def test_proc_sampler_parses_requested_rss_fields(tmp_path: Path) -> None:
    module = _load_script_module()
    status_path = tmp_path / "status"
    status_path.write_text(
        "\n".join(
            [
                "VmSize:\t  4000 kB",
                "VmHWM:\t  3000 kB",
                "VmRSS:\t  2000 kB",
                "RssAnon:\t  1500 kB",
                "RssFile:\t   400 kB",
                "RssShmem:\t   100 kB",
            ]
        ),
        encoding="utf-8",
    )
    assert module._parse_status_file(status_path) == {
        "vmsize_kb": 4000,
        "vmhwm_kb": 3000,
        "vmrss_kb": 2000,
        "rss_anon_kb": 1500,
        "rss_file_kb": 400,
        "rss_shmem_kb": 100,
    }

    smaps_path = tmp_path / "smaps_rollup"
    smaps_path.write_text(
        "\n".join(["Rss: 2100 kB", "Pss: 1800 kB", "Private_Dirty: 1600 kB"]),
        encoding="utf-8",
    )
    smaps = module._parse_smaps_rollup(smaps_path)
    assert smaps["smaps_rollup_rss_kb"] == 2100
    assert smaps["pss_kb"] == 1800
    assert smaps["private_dirty_kb"] == 1600
    assert smaps["smaps_rss_kb"] == 2100


def test_summarize_qret_profile_reports_json_destroy_delta() -> None:
    module = _load_script_module()
    summary = module._summarize_qret_profile(
        [
            {"stage": "load_ir_after_json_parse_json_alive", "vmrss_kb": 1000},
            {"stage": "load_ir_after_load_json_json_alive", "vmrss_kb": 2500},
            {"stage": "after_load_function_json_destroyed", "vmrss_kb": 2200},
            {"stage": "after_lowering", "vmrss_kb": 125000},
        ]
    )
    assert summary["json_destroy_current_delta_kb"] == -300
    assert summary["max_profile_stage"] == "after_lowering"
    assert summary["first_100mb_jump"] == {
        "stage": "after_lowering",
        "delta_kb": 122800,
        "from_kb": 2200,
        "to_kb": 125000,
    }


def test_skip_pipeline_output_metric_compare_ignores_paths() -> None:
    _load_script_module()
    module = _load_script_module(
        SKIP_SCRIPT_PATH,
        "profile_qret_skip_pipeline_output",
    )
    comparison = module._compare_metrics(
        {
            "normalized_metrics": {
                "compile_info_json": "/tmp/baseline.json",
                "magic_state_consumption_count": 3,
                "runtime": 11,
            }
        },
        {
            "normalized_metrics": {
                "compile_info_json": "/tmp/skip.json",
                "magic_state_consumption_count": 3,
                "runtime": 11,
            }
        },
    )
    assert comparison["semantic_fields_equal"] is True
    assert comparison["normalized_metrics_equal"] is True


def test_calc_info_prefixes_reach_requested_boundaries(tmp_path: Path) -> None:
    pre_module = _load_script_module()
    module = _load_script_module(
        CALC_INFO_SCRIPT_PATH,
        "profile_qret_calc_info_memory",
    )
    assert module.PREFIX_PASSES["prefix_a_routing"][-1] == "sc_ls_fixed_v0::routing"
    assert (
        module.PREFIX_PASSES["prefix_b_calc_without_topology"][-1]
        == "sc_ls_fixed_v0::calc_info_without_topology"
    )
    assert (
        module.PREFIX_PASSES["prefix_c_calc_with_topology"][-1]
        == "sc_ls_fixed_v0::calc_info_with_topology"
    )
    assert (
        module.PREFIX_PASSES["prefix_d_dump_compile_info"][-1]
        == "sc_ls_fixed_v0::dump_compile_info"
    )

    yaml_text = pre_module._build_pipeline_yaml(
        opt_path=tmp_path / "step_opt.json",
        output_path=tmp_path / "step_sc_ls_fixed_v0.json",
        compile_info_path=tmp_path / "compile_info.json",
        topology_path=tmp_path / "topology.yaml",
        passes=module.PREFIX_PASSES["prefix_d_dump_compile_info"],
        skip_pipeline_state_output=True,
    )
    assert "sc_ls_fixed_v0_skip_pipeline_state_output: true" in yaml_text
    assert "  - sc_ls_fixed_v0::dump_compile_info" in yaml_text


def test_calc_info_profile_metric_compare_ignores_paths_and_execution_time() -> None:
    _load_script_module()
    module = _load_script_module(
        CALC_INFO_SCRIPT_PATH,
        "profile_qret_calc_info_memory",
    )
    comparison = module._compare_metrics(
        {
            "normalized_metrics": {
                "compile_info_json": "/tmp/profiled.json",
                "execution_time_sec": 1.0,
                "runtime": 42,
                "magic_state_consumption_count": 7,
            }
        },
        {
            "normalized_metrics": {
                "compile_info_json": "/tmp/unprofiled.json",
                "execution_time_sec": 2.0,
                "runtime": 42,
                "magic_state_consumption_count": 7,
            }
        },
    )
    assert comparison["semantic_fields_equal"] is True
    assert comparison["normalized_metrics_equal"] is True


def test_calc_info_profile_summary_extracts_pass_and_container_stats() -> None:
    _load_script_module()
    module = _load_script_module(
        CALC_INFO_SCRIPT_PATH,
        "profile_qret_calc_info_memory",
    )
    rows = [
        {"stage": "calc_info_without_topology_entry", "vmrss_kb": 100},
        {
            "stage": "calc_info_without_topology_after_dep_graph",
            "vmrss_kb": 250,
            "extra": {"dep_graph_nodes": 11, "dep_graph_edges": 20},
        },
        {
            "stage": "mf_pass_after",
            "vmrss_kb": 220,
            "extra": {"pass_argument": "sc_ls_fixed_v0::calc_info_without_topology"},
        },
        {
            "stage": "compile_info_json_after_assign_gate_throughput",
            "vmrss_kb": 400,
            "extra": {"key": "gate_throughput", "vector_size": 5},
        },
    ]
    summary = module._summarize_profile(rows)
    assert summary["max_profile_stage_label"] == (
        "compile_info_json_after_assign_gate_throughput:gate_throughput"
    )
    assert summary["post_calc_info_without_topology_rss_kb"] == 220
    assert summary["container_snapshots"][0]["dep_graph_nodes"] == 11
