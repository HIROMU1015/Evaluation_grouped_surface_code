#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(
  cd "$(dirname "${BASH_SOURCE[0]}")/.." &&
  pwd
)"

QURATION_ROOT="${PROJECT_ROOT}/third_party/quration"
BUILD_ROOT="${PROJECT_ROOT}/build/quration/cmake-build"
OUTPUT_DIR="${PROJECT_ROOT}/build/quration"

find_cmake() {
  if [[ -n "${CMAKE:-}" ]]; then
    printf '%s\n' "${CMAKE}"
    return 0
  fi
  if command -v cmake >/dev/null 2>&1; then
    command -v cmake
    return 0
  fi
  local candidate
  for candidate in "${HOME}"/.local/vcpkg/downloads/tools/cmake-*-linux/*/bin/cmake; do
    if [[ -x "${candidate}" ]]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done
  return 1
}

if [[ ! -d "${QURATION_ROOT}/quration-core" ]]; then
  echo "vendored quration source not found: ${QURATION_ROOT}" >&2
  exit 1
fi

CMAKE_BIN="$(find_cmake)" || {
  echo "cmake not found. Install cmake or set CMAKE=/path/to/cmake." >&2
  exit 1
}

mkdir -p "${BUILD_ROOT}" "${OUTPUT_DIR}"

CMAKE_ARGS=(
  -S "${QURATION_ROOT}"
  -B "${BUILD_ROOT}"
  -DCMAKE_BUILD_TYPE=Release
  -DQRET_BUILD_APPLICATION=ON
  -DQRET_BUILD_ALGORITHM=OFF
  -DQRET_BUILD_EXAMPLE=OFF
  -DQRET_BUILD_TEST=OFF
  -DQRET_BUILD_PYTHON=OFF
  -DQRET_USE_QULACS=OFF
)

if [[ -n "${CMAKE_TOOLCHAIN_FILE:-}" ]]; then
  CMAKE_ARGS+=("-DCMAKE_TOOLCHAIN_FILE=${CMAKE_TOOLCHAIN_FILE}")
elif [[ -f "${HOME}/.local/vcpkg/scripts/buildsystems/vcpkg.cmake" ]]; then
  CMAKE_ARGS+=("-DCMAKE_TOOLCHAIN_FILE=${HOME}/.local/vcpkg/scripts/buildsystems/vcpkg.cmake")
fi

"${CMAKE_BIN}" "${CMAKE_ARGS[@]}"
"${CMAKE_BIN}" --build "${BUILD_ROOT}" --target qret --parallel "${QRET_BUILD_JOBS:-2}"

install -m 0755 "${BUILD_ROOT}/main/qret" "${OUTPUT_DIR}/qret"
for lib in "${BUILD_ROOT}"/quration-core/src/libqret-core.so*; do
  if [[ -e "${lib}" ]]; then
    cp -a "${lib}" "${OUTPUT_DIR}/"
  fi
done

echo "qret built at ${OUTPUT_DIR}/qret"
