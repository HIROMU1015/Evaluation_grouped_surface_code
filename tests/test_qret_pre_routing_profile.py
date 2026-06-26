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
