from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, TypeAlias


PFLabel: TypeAlias = str


def _find_project_root(start: Path) -> Path:
    for path in [start, *start.parents]:
        if (path / "pyproject.toml").exists() or (path / ".git").exists():
            return path
    return start


def _first_existing_path(*candidates: Path) -> Path:
    if not candidates:
        raise ValueError("at least one path candidate is required")
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def _positive_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer >= 1: {raw!r}") from exc
    if value < 1:
        raise ValueError(f"{name} must be an integer >= 1: {raw!r}")
    return value


_env_root = os.environ.get("TROTTER_PROJECT_ROOT")
PROJECT_ROOT = (
    Path(_env_root).expanduser().resolve()
    if _env_root
    else _find_project_root(Path(__file__).resolve())
)
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"

PICKLE_DIR = "trotter_expo_coeff"
PICKLE_DIR_GROUPED = "trotter_expo_coeff_gr"
PICKLE_DIR_GROUPED_ORIGINAL = "trotter_expo_coeff_gr_original"
SURFACE_CODE_STEP_DIR_GROUPED = "surface_code_step_gr"
SURFACE_CODE_STEP_DIR_GROUPED_ORIGINAL = "surface_code_step_gr_original"

PICKLE_DIR_PATH = ARTIFACTS_DIR / PICKLE_DIR
PICKLE_DIR_GROUPED_PATH = ARTIFACTS_DIR / PICKLE_DIR_GROUPED
PICKLE_DIR_GROUPED_ORIGINAL_PATH = ARTIFACTS_DIR / PICKLE_DIR_GROUPED_ORIGINAL
SURFACE_CODE_STEP_GROUPED_PATH = ARTIFACTS_DIR / SURFACE_CODE_STEP_DIR_GROUPED
SURFACE_CODE_STEP_GROUPED_ORIGINAL_PATH = (
    ARTIFACTS_DIR / SURFACE_CODE_STEP_DIR_GROUPED_ORIGINAL
)
SURFACE_CODE_CACHE_DIR = ARTIFACTS_DIR / "surface_code_cache"

DEFAULT_BASIS = "sto-3g"
DEFAULT_DISTANCE = 1.0
CA = 1.59360010199040e-3
TARGET_ERROR = CA / 10
BETA = 1.2

P_DIR: dict[PFLabel, int] = {
    "2nd": 2,
    "4th(new_2)": 4,
}

_PF_LABEL_ALIASES = {
    "2nd": "2nd",
    "second": "2nd",
    "4th(new_2)": "4th(new_2)",
    "4th_new_2": "4th(new_2)",
    "4th-new-2": "4th(new_2)",
}


def normalize_pf_label(num_w: PFLabel | None) -> PFLabel:
    if num_w is None:
        raise KeyError(num_w)
    canonical = _PF_LABEL_ALIASES.get(str(num_w).strip().lower(), str(num_w))
    if canonical not in P_DIR:
        raise KeyError(num_w)
    return canonical


def pickle_dir(gr: bool | None = None, *, use_original: bool = False) -> Path:
    if gr is None:
        return PICKLE_DIR_PATH
    if use_original:
        return PICKLE_DIR_GROUPED_ORIGINAL_PATH
    return PICKLE_DIR_GROUPED_PATH


def surface_code_step_dir(source: str = "gr", *, use_original: bool = False) -> Path:
    if source != "gr":
        raise ValueError(f"Unsupported source: {source}")
    return (
        SURFACE_CODE_STEP_GROUPED_ORIGINAL_PATH
        if use_original
        else SURFACE_CODE_STEP_GROUPED_PATH
    )


def ensure_artifact_dirs() -> None:
    for path in (
        ARTIFACTS_DIR,
        PICKLE_DIR_GROUPED_PATH,
        PICKLE_DIR_GROUPED_ORIGINAL_PATH,
        SURFACE_CODE_STEP_GROUPED_PATH,
        SURFACE_CODE_STEP_GROUPED_ORIGINAL_PATH,
        SURFACE_CODE_CACHE_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)


DECOMPO_NUM: Dict[str, Dict[PFLabel, int]] = {
    "H2": {"2nd": 24, "4th(new_2)": 80},
    "H3": {"2nd": 118, "4th(new_2)": 506},
    "H4": {"2nd": 396, "4th(new_2)": 1836},
    "H5": {"2nd": 998, "4th(new_2)": 4770},
    "H6": {"2nd": 2116, "4th(new_2)": 10268},
    "H7": {"2nd": 4026, "4th(new_2)": 19710},
    "H8": {"2nd": 6964, "4th(new_2)": 34276},
    "H9": {"2nd": 11494, "4th(new_2)": 56786},
    "H10": {"2nd": 17660, "4th(new_2)": 87460},
    "H11": {"2nd": 25946, "4th(new_2)": 128718},
    "H12": {"2nd": 36988, "4th(new_2)": 183740},
    "H13": {"2nd": 51462, "4th(new_2)": 255906},
    "H14": {"2nd": 69556, "4th(new_2)": 346156},
    "H15": {"2nd": 92802, "4th(new_2)": 462150},
}

PF_RZ_LAYER: Dict[str, Dict[PFLabel, int]] = {
    "H2": {"2nd": 9, "4th(new_2)": 29},
    "H3": {"2nd": 39, "4th(new_2)": 163},
    "H4": {"2nd": 99, "4th(new_2)": 459},
    "H5": {"2nd": 341, "4th(new_2)": 1657},
    "H6": {"2nd": 568, "4th(new_2)": 2780},
    "H7": {"2nd": 1064, "4th(new_2)": 5252},
    "H8": {"2nd": 1220, "4th(new_2)": 6016},
    "H9": {"2nd": 2442, "4th(new_2)": 12118},
    "H10": {"2nd": 3172, "4th(new_2)": 15756},
    "H11": {"2nd": 4511, "4th(new_2)": 22447},
    "H12": {"2nd": 4865, "4th(new_2)": 24205},
    "H13": {"2nd": 7476, "4th(new_2)": 37248},
    "H14": {"2nd": 8527, "4th(new_2)": 42495},
    "H15": {"2nd": 11657, "4th(new_2)": 58133},
}

SURFACE_CODE_COMPILE_MODE = "ftqc_compile_topology_qec"
SURFACE_CODE_QASM_BASIS_GATES = ("rz", "cx", "sx", "x")
SURFACE_CODE_QASM_DECOMPOSE_REPS = 8
SURFACE_CODE_ROTATION_PRECISION_MODE = "layer_linear_floor"
SURFACE_CODE_ROTATION_ERROR_BUDGET_FRACTION = 1.0e-2
SURFACE_CODE_ROTATION_PRECISION_FLOOR = 1.0e-5
SURFACE_CODE_FIXED_ROTATION_PRECISION = 1.0e-9
SURFACE_CODE_COMPILE_SKIP_OUTPUT = True
SURFACE_CODE_COMPILE_SKIP_REDUNDANT_IR_PREPROCESS = True
SURFACE_CODE_SAVE_MAPPING_RESULT = False
SURFACE_CODE_RZ_CALL_CACHE = True
SURFACE_CODE_RZ_HELPER_OPT_MODE = "independent_helper"
SURFACE_CODE_RZ_HELPER_BATCH_SIZE = _positive_int_env(
    "SURFACE_CODE_RZ_HELPER_BATCH_SIZE",
    1,
)
SURFACE_CODE_RZ_CALL_CACHE_ROUND_DIGITS = None
SURFACE_CODE_INTEGRAL_CACHE_ENABLED = (
    os.environ.get("SURFACE_CODE_INTEGRAL_CACHE_ENABLED", "1").strip().lower()
    not in {"0", "false", "no", "off"}
)

SURFACE_CODE_MACHINE_TYPE = "Dim2"
SURFACE_CODE_MAGIC_GENERATION_PERIOD = 15
SURFACE_CODE_MAX_MAGIC_STATE_STOCK = 10000
SURFACE_CODE_ENTANGLEMENT_GENERATION_PERIOD = 100
SURFACE_CODE_MAX_ENTANGLED_STATE_STOCK = 10
SURFACE_CODE_REACTION_TIME = 1

SURFACE_CODE_P_PHYS_CASES = (1.0e-3, 5.0e-4, 1.0e-4)
SURFACE_CODE_DELTA_FAIL_CASES = (1.0e-2, 1.0e-3)
SURFACE_CODE_CYCLE_TIME_SECONDS = 1.0e-6
SURFACE_CODE_QEC_PHYSICAL_ERROR_RATE = SURFACE_CODE_P_PHYS_CASES[0]
SURFACE_CODE_QEC_DROP_RATE = 0.1
SURFACE_CODE_QEC_CODE_CYCLE_TIME_SECONDS = SURFACE_CODE_CYCLE_TIME_SECONDS
SURFACE_CODE_QEC_ALLOWED_FAILURE_PROB = SURFACE_CODE_DELTA_FAIL_CASES[0]

VENDORED_QURATION_ROOT = PROJECT_ROOT / "third_party" / "quration"

_qret_path_env = os.environ.get("QRET_PATH") or os.environ.get(
    "SURFACE_CODE_QRET_PATH"
)
SURFACE_CODE_QCSF_PATH = (
    Path(_qret_path_env).expanduser().resolve()
    if _qret_path_env
    else PROJECT_ROOT / "build" / "quration" / "qret"
)

_topology_path_env = os.environ.get("SURFACE_CODE_TOPOLOGY_PATH")
SURFACE_CODE_TOPOLOGY_PATH = (
    Path(_topology_path_env).expanduser().resolve()
    if _topology_path_env
    else VENDORED_QURATION_ROOT
    / "quration-core"
    / "examples"
    / "data"
    / "topology"
    / "tutorial.yaml"
)

_gridsynth_path_env = os.environ.get("GRIDSYNTH_PATH") or os.environ.get(
    "SURFACE_CODE_GRIDSYNTH_PATH"
)
SURFACE_CODE_GRIDSYNTH_PATH = (
    Path(_gridsynth_path_env).expanduser().resolve()
    if _gridsynth_path_env
    else _first_existing_path(
        PROJECT_ROOT / "externals" / "bin" / "gridsynth",
        PROJECT_ROOT.parent / "quration" / "externals" / "bin" / "gridsynth",
    )
)
