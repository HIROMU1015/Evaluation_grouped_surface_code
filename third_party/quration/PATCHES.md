# Local quration changes

## Multi-function qret opt

Purpose:

- Allow one `qret opt` process to sequentially optimize multiple independent
  helper functions with the same pass list.
- Support Evaluation-side cold RZ helper batching without committing or pushing
  changes to the upstream quration repository.

Main implementation:

- `quration-core/src/qret/cmd/opt.cpp`
- `quration-core/src/qret/cmd/opt.h`
- `quration-core/tests/cmd/main.cpp`

Behavior:

- Adds pipeline YAML `functions:` support.
- Preserves the existing scalar `function:` interface.
- Rejects simultaneous `function` and `functions`.
- Rejects empty, duplicate, non-scalar, and unknown function names.
- Validates all requested functions before executing passes.
- Creates fresh pass instances for each function and each pass application.
- Writes output once after all requested functions succeed.
- Uses a temporary output file and atomic publish.

Evaluation integration:

- `scripts/build_qret.sh` builds this vendored source.
- The generated qret binary is expected at `build/quration/qret`.
- Evaluation defaults to that generated binary unless `QRET_PATH` or
  `SURFACE_CODE_QRET_PATH` is set.

## Build compatibility for vendored qret

Purpose:

- Keep the vendored quration source buildable from a clean Evaluation checkout
  with the current Linux/GCC toolchain.

Main implementation:

- `quration-core/src/qret/target/sc_ls_fixed_v0/state.h`
- `quration-core/src/qret/target/sc_ls_fixed_v0/topology.h`

Behavior:

- Includes `<span>` where `std::span` is used.
- Removes `constexpr` from a defaulted comparison involving `std::string`,
  which is not constexpr-comparable with this toolchain.
