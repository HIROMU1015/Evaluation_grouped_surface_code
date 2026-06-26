# qret Skip Pipeline-State Output

## Purpose

Reduce the H4 `4th(new_2)` qret topology compile peak RSS by skipping the
unused SC_LS_FIXED_V0 pipeline-state output when Evaluation only needs
`compile_info.json`.

Previous profiling showed the peak was not pre-routing. It came from retaining:

- `MachineFunction`
- `ScLsFixedV0PipelineState::program`
- the full `Json(state)` DOM created in `SavePipelineState`

## Implementation

- qret option: `sc_ls_fixed_v0_skip_pipeline_state_output`
- Default: disabled. Existing CLI and pipeline YAML behavior is unchanged when
  the option is absent.
- Evaluation setting: `SurfaceCodeArchitecture.skip_compile_output=True` adds
  `sc_ls_fixed_v0_skip_pipeline_state_output: true` to the qret pipeline YAML.
- Preserved behavior: qret still runs all compile passes, including
  `dump_compile_info`, so `compile_info.json` and physical resource metrics are
  still generated.
- Skipped behavior: when the flag is present, qret does not call
  `BuildPipelineState` or `SavePipelineState` and does not build the output
  JSON DOM.
- The `output` YAML field is still emitted for request compatibility, but the
  skip path does not open or serialize that output.
- Cache key: no new cache-key field was added because
  `surface_code_compile_cache_payload` already includes `skip_compile_output`.

## A/B Results

Command:

```bash
/home/abe/myproject/.venv/bin/python3.11 scripts/profile_qret_skip_pipeline_output.py --sample-interval-sec 0.02
```

Both cases used the same rebuilt qret binary, same topology, and the existing
prepared H4 artifacts used in the previous profile.

| case | mode | elapsed s | peak RSS KB | post-routing RSS KB | post-calc-info RSS KB | output size B | metrics equal |
| ---- | ---- | ------: | -------: | ---------------: | -----------------: | ----------: | ------------- |
| H4 `2nd` | baseline | 1.521 | 449,496 | 51,912 | 129,752 | 32,911,675 | baseline |
| H4 `2nd` | skip output | 0.744 | 188,980 | 52,020 | 129,800 | absent | yes |
| H4 `4th(new_2)` | baseline | 7.207 | 2,087,348 | 216,048 | 587,444 | 155,263,136 | baseline |
| H4 `4th(new_2)` | skip output | 3.965 | 860,160 | 215,808 | 579,500 | absent | yes |

## RSS Reduction

| case | absolute reduction | relative reduction |
| --- | ---: | ---: |
| H4 `2nd` | 260,516 KB, 254.4 MiB | 58.0% |
| H4 `4th(new_2)` | 1,227,188 KB, 1,198.4 MiB | 58.8% |

H4 `4th(new_2)` peak RSS fell from 2,087,348 KB to 860,160 KB.

## Semantic Check

The normalized compile metrics matched exactly after excluding only
`compile_info_json`, which is path metadata and differs between A/B run
directories.

Fields explicitly checked:

`magic_state_consumption_count`, `magic_state_consumption_depth`, `runtime`,
`runtime_without_topology`, `qubit_volume`, `gate_count`, `gate_depth`,
`measurement_feedback_count`, `measurement_feedback_depth`,
`magic_factory_count`, `chip_cell_count`, `code_distance`,
`num_physical_qubits`, `t_count`, `t_depth`.

`t_count` and `t_depth` were absent in both baseline and skip outputs. All other
listed fields were present and equal. The full normalized metric dictionaries
were equal after excluding `compile_info_json`.

## Marker Check

| case | mode | `BuildProgramJson` marker | `SavePipelineState` marker | `Json(state)` marker | skip marker |
| --- | --- | --- | --- | --- | --- |
| H4 `2nd` | baseline | yes | yes | yes | no |
| H4 `2nd` | skip output | no | no | no | yes |
| H4 `4th(new_2)` | baseline | yes | yes | yes | no |
| H4 `4th(new_2)` | skip output | no | no | no | yes |

Skip-mode terminal markers were:

`after_pass_manager_run`, `pipeline_state_output_skipped`,
`run_compilation_end`.

## Decision

1. `BuildPipelineState` and `SavePipelineState` are no longer executed on the
   skip path.
2. H4 `4th(new_2)` peak RSS dropped to 860,160 KB, about 840.0 MiB.
3. The reduction was 1,227,188 KB, about 1,198.4 MiB or 58.8%.
4. Elapsed time improved from 7.207 s to 3.965 s for H4 `4th(new_2)`.
5. `compile_info.json` and physical resource metrics matched exactly.
6. The skip path is suitable as the Evaluation production default when
   `skip_compile_output=True`.
7. Compatibility is preserved for users that need pipeline-state output because
   the new qret flag is opt-in and absent by default.
8. The next RSS bottleneck is now around `calc_info_without_topology` and
   retained compile-info/resource data, not output serialization.
9. If further qret RSS reduction is needed, profile inside
   `calc_info_without_topology`; do not revisit pre-routing IR/mapping first.
