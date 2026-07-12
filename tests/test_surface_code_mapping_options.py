import hashlib
import json
from pathlib import Path

import pytest

from trotterlib import architecture_sweep as sweep
from trotterlib import surface_code as sc


def test_mapping_options_are_written_to_compile_and_mapping_pipelines(
    tmp_path: Path,
) -> None:
    architecture = sc.SurfaceCodeArchitecture(
        topology_path=tmp_path / "topology.yaml",
        mapping_algorithm=0,
        mapping_partition_algorithm=1,
        mapping_partition_seed=2718,
        mapping_find_place_algorithm=1,
    )

    compile_yaml = sc.compile_pipeline_yaml(
        opt_path=tmp_path / "step_opt.json",
        compile_output_path=tmp_path / "step_sc_ls_fixed_v0.json",
        compile_info_path=tmp_path / "compile_info.json",
        architecture=architecture,
    )
    mapping_yaml = sc.mapping_pipeline_yaml(
        opt_path=tmp_path / "step_opt.json",
        mapping_state_path=tmp_path / "mapping_state.json",
        mapping_compile_info_path=tmp_path / "mapping_compile_info.json",
        architecture=architecture,
    )

    for yaml_text in (compile_yaml, mapping_yaml):
        assert "sc_ls_fixed_v0-mapping-algorithm: 0" in yaml_text
        assert "sc_ls_fixed_v0-partition-algorithm: 1" in yaml_text
        assert "sc_ls_fixed_v0-partition-seed: 2718" in yaml_text
        assert "sc_ls_fixed_v0-find-place-algorithm: 1" in yaml_text


def test_mapping_options_are_part_of_architecture_cache_tag() -> None:
    baseline = sc.SurfaceCodeArchitecture()
    explicit = sc.SurfaceCodeArchitecture(mapping_algorithm=0)

    assert baseline.cache_tag() != explicit.cache_tag()


def test_default_mapping_options_preserve_legacy_cache_tag() -> None:
    architecture = sc.SurfaceCodeArchitecture()
    legacy_values = architecture.to_dict()
    for key in (
        "mapping_algorithm",
        "mapping_partition_algorithm",
        "mapping_partition_seed",
        "mapping_find_place_algorithm",
    ):
        legacy_values.pop(key)

    payload = json.dumps(legacy_values, sort_keys=True, separators=(",", ":"))
    assert architecture.cache_tag() == hashlib.sha256(payload.encode()).hexdigest()[:12]


def test_metis_mapping_is_rejected_until_qret_implements_it() -> None:
    with pytest.raises(ValueError, match="does not implement"):
        sc.SurfaceCodeArchitecture(mapping_partition_algorithm=2)


def test_topology_path_can_be_selected_by_molecule(tmp_path: Path) -> None:
    topology = {
        "paths": {
            "H4": str(tmp_path / "h4.yaml"),
            "H7": str(tmp_path / "h7.yaml"),
        }
    }

    assert sweep._topology_path_for_molecule(topology, "H4") == (
        tmp_path / "h4.yaml"
    ).resolve()
    assert sweep._topology_path_for_molecule(topology, "H7") == (
        tmp_path / "h7.yaml"
    ).resolve()
    with pytest.raises(ValueError, match="Missing topology path"):
        sweep._topology_path_for_molecule(topology, "H5")
