# Vendored quration

Original repository:

- `quration/quration`

Base upstream revision:

- `293912c18ee659b4004ac6f980f0cc84ac77d189`

Local qret changes:

- The vendored source in this directory is the authoritative copy used by
  `Evaluation_grouped_surface_code`.
- The previous local quration commit `c7afe2d Support multi-function qret opt
  pipelines` was not pushed upstream and must not be treated as a fetchable
  upstream revision.

Vendoring scope:

- Included: quration top-level CMake files, `cmake/`, `vcpkg.json`,
  `Version.txt`, and `quration-core/`.
- Not included: quration `.git/`, generated build outputs, cache/log files,
  and quration `externals/`.

Runtime external dependency:

- `gridsynth` is not vendored here because this project does not modify it.
- Set `GRIDSYNTH_PATH` or `SURFACE_CODE_GRIDSYNTH_PATH` when running workloads
  that decompose rotations.
