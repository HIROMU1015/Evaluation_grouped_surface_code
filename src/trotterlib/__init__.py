"""Grouped Hamiltonian surface-code resource estimation utilities."""

from .architecture_sweep import run_surface_code_architecture_sweep
from .surface_code import (
    CONTROLLED_PF_TIME_EVOLUTION_BLOCK_SCOPE,
    SurfaceCodeArchitecture,
    SurfaceCodeArchitectureConfig,
    UNCONTROLLED_PF_ONE_STEP_SCOPE,
    build_grouped_surface_code_controlled_block_circuit,
    compile_grouped_hchain_step,
    compile_grouped_hchain_controlled_block,
    generate_grouped_surface_code_controlled_block_metrics,
    generate_grouped_surface_code_step_metrics,
    grouped_hchain_ham_name,
    grouped_surface_code_hchain_targets,
    prepare_grouped_surface_code_controlled_block_artifact,
)

__all__ = [
    "CONTROLLED_PF_TIME_EVOLUTION_BLOCK_SCOPE",
    "SurfaceCodeArchitecture",
    "SurfaceCodeArchitectureConfig",
    "UNCONTROLLED_PF_ONE_STEP_SCOPE",
    "build_grouped_surface_code_controlled_block_circuit",
    "compile_grouped_hchain_controlled_block",
    "compile_grouped_hchain_step",
    "generate_grouped_surface_code_controlled_block_metrics",
    "generate_grouped_surface_code_step_metrics",
    "grouped_hchain_ham_name",
    "grouped_surface_code_hchain_targets",
    "prepare_grouped_surface_code_controlled_block_artifact",
    "run_surface_code_architecture_sweep",
]
