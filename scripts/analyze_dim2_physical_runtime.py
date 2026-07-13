#!/usr/bin/env python3
"""Recompute physical-runtime ratios and calibrate Dim2 beat parameters."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "artifacts" / "surface_code_dim2_physical_runtime_reanalysis"
CODE_CYCLE_TIME_SEC = 1e-6


@dataclass(frozen=True)
class Experiment:
    name: str
    path: str
    condition_field: str
    baseline: str
    allowed_conditions: tuple[str, ...] = ()


EXPERIMENTS = (
    Experiment(
        "accessible_factory_count_1e-5",
        "artifacts/surface_code_accessible_factory_count_sweep_h4_h7_4th/results.csv",
        "factory_count",
        "4",
    ),
    Experiment(
        "accessible_factory_count_1e-2",
        "artifacts/surface_code_accessible_factory_count_sweep_h4_h7_4th_cheap_rz/results.csv",
        "factory_count",
        "4",
    ),
    Experiment(
        "factory_saturation",
        "artifacts/surface_code_factory_saturation_sweep_h4_h6_4th_paired/results.csv",
        "factory_count",
        "4",
    ),
    Experiment(
        "magic_period_1e-2",
        "artifacts/surface_code_magic_period_sweep_h4_h7_4th_cheap_rz/results.csv",
        "magic_generation_period",
        "15",
    ),
    Experiment(
        "magic_stock",
        "artifacts/surface_code_magic_stock_sweep_h4_h6_4th_paired/results.csv",
        "maximum_magic_state_stock",
        "10000",
    ),
    Experiment(
        "reaction_time",
        "artifacts/surface_code_reaction_time_sweep_h4_h7_4th_paired/results.csv",
        "reaction_time",
        "1",
    ),
    Experiment(
        "logical_placement",
        "artifacts/surface_code_logical_placement_sweep_h4_h7_4th/results.csv",
        "topology_name",
        "explicit_compact_interaction_aware",
        (
            "explicit_compact_interaction_aware",
            "explicit_compact_numeric",
            "explicit_perimeter_numeric",
        ),
    ),
    Experiment(
        "routing_capacity",
        "artifacts/surface_code_routing_capacity_sweep_h4_h7_4th_paired/results.csv",
        "routing_condition",
        "remote_ban_control",
    ),
    Experiment(
        "grid_capacity_explicit",
        "artifacts/surface_code_grid_capacity_sweep_h4_h7_4th/results.csv",
        "topology_name",
        "aware_10x10",
        ("aware_8x8", "aware_10x10", "aware_12x12"),
    ),
    Experiment(
        "factory_placement",
        "artifacts/surface_code_rotation_precision_topology_sweep_h4_h7_4th/results.csv",
        "topology_name",
        "factory_center_block",
    ),
)


def _number(row: Mapping[str, str], *names: str) -> float:
    for name in names:
        value = row.get(name, "")
        if value not in ("", None):
            return float(value)
    raise KeyError(f"none of {names!r} exists in row")


def relative_changes(
    row: Mapping[str, str], baseline: Mapping[str, str]
) -> dict[str, float]:
    runtime = _number(row, "runtime", "runtime_with_topology")
    baseline_runtime = _number(baseline, "runtime", "runtime_with_topology")
    distance = _number(row, "code_distance")
    baseline_distance = _number(baseline, "code_distance")
    qubit_volume = _number(row, "qubit_volume")
    baseline_qv = _number(baseline, "qubit_volume")
    beat_change = (runtime / baseline_runtime - 1.0) * 100.0
    physical_change = (
        runtime * distance / (baseline_runtime * baseline_distance) - 1.0
    ) * 100.0
    return {
        "runtime_change_pct": beat_change,
        "code_distance_change_pct": (distance / baseline_distance - 1.0) * 100.0,
        "physical_runtime_change_pct": physical_change,
        "qubit_volume_change_pct": (qubit_volume / baseline_qv - 1.0) * 100.0,
        "physical_minus_beat_percentage_points": physical_change - beat_change,
    }


def beat_duration_sec(code_distance: int, code_cycle_time_sec: float = CODE_CYCLE_TIME_SEC) -> float:
    return code_distance * code_cycle_time_sec


def factory_throughput_hz(
    period: int, code_distance: int, code_cycle_time_sec: float = CODE_CYCLE_TIME_SEC
) -> float:
    return 1.0 / (period * beat_duration_sec(code_distance, code_cycle_time_sec))


def _group_key(row: Mapping[str, str]) -> tuple[str, str]:
    return row["molecule"], f"{float(row['rotation_precision']):.0e}"


def collect_rows(experiments: Iterable[Experiment] = EXPERIMENTS) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for experiment in experiments:
        path = REPO_ROOT / experiment.path
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        if experiment.allowed_conditions:
            allowed = set(experiment.allowed_conditions)
            rows = [row for row in rows if row[experiment.condition_field] in allowed]
        groups: dict[tuple[str, str], list[dict[str, str]]] = {}
        for row in rows:
            groups.setdefault(_group_key(row), []).append(row)
        for (molecule, precision), group in groups.items():
            baselines = [
                row
                for row in group
                if row[experiment.condition_field] == experiment.baseline
            ]
            if len(baselines) != 1:
                raise RuntimeError(
                    f"{experiment.name}/{molecule}/{precision}: expected one baseline, found {len(baselines)}"
                )
            baseline = baselines[0]
            for row in group:
                condition = row[experiment.condition_field]
                if condition == experiment.baseline:
                    continue
                results.append(
                    {
                        "experiment": experiment.name,
                        "molecule": molecule,
                        "rotation_precision": precision,
                        "condition": condition,
                        "baseline_condition": experiment.baseline,
                        "code_distance": int(_number(row, "code_distance")),
                        "baseline_code_distance": int(_number(baseline, "code_distance")),
                        **relative_changes(row, baseline),
                    }
                )
    return results


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _range(values: Sequence[float]) -> str:
    return f"{min(values):+.4f}% to {max(values):+.4f}%"


def write_report(output: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    _write_csv(output / "results.csv", rows)
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((str(row["experiment"]), str(row["rotation_precision"])), []).append(row)
    lines = [
        "# Dim2 Physical-Runtime Reanalysis and Beat Calibration",
        "",
        "The logical workload is fixed inside every contrast. Beat runtime and physical runtime are both reported relative to the architecture baseline; cross-precision runtime reduction is excluded.",
        "",
        "Physical runtime is recomputed as `runtime_beats * code_distance * code_cycle_time_sec`. With the fixed cycle time, the relative ratio is `(runtime * d) / (runtime_baseline * d_baseline)`.",
        "",
        "## Existing-sweep ranges",
        "",
        "| experiment | precision | beat-runtime change | physical-runtime change | QV change | max |physical - beat| | distance changed |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for key in sorted(grouped):
        group = grouped[key]
        beat = [float(row["runtime_change_pct"]) for row in group]
        physical = [float(row["physical_runtime_change_pct"]) for row in group]
        qv = [float(row["qubit_volume_change_pct"]) for row in group]
        delta = [abs(float(row["physical_minus_beat_percentage_points"])) for row in group]
        distance_changed = any(int(row["code_distance"]) != int(row["baseline_code_distance"]) for row in group)
        lines.append(
            f"| {key[0]} | {key[1]} | {_range(beat)} | {_range(physical)} | {_range(qv)} | {max(delta):.4f} pp | {'yes' if distance_changed else 'no'} |"
        )

    largest = sorted(
        rows,
        key=lambda row: abs(float(row["physical_minus_beat_percentage_points"])),
        reverse=True,
    )[:12]
    lines.extend(
        [
            "",
            "## Largest code-distance corrections",
            "",
            "| experiment | precision | molecule | condition vs baseline | d | beat change | physical change | correction |",
            "|---|---:|---|---|---:|---:|---:|---:|",
        ]
    )
    for row in largest:
        lines.append(
            "| {experiment} | {precision} | {molecule} | {condition} vs {baseline} | {distance} vs {baseline_distance} | {beat:+.4f}% | {physical:+.4f}% | {correction:+.4f} pp |".format(
                experiment=row["experiment"],
                precision=row["rotation_precision"],
                molecule=row["molecule"],
                condition=row["condition"],
                baseline=row["baseline_condition"],
                distance=row["code_distance"],
                baseline_distance=row["baseline_code_distance"],
                beat=float(row["runtime_change_pct"]),
                physical=float(row["physical_runtime_change_pct"]),
                correction=float(row["physical_minus_beat_percentage_points"]),
            )
        )

    distances = (13, 15, 17, 19)
    lines.extend(
        [
            "",
            "## Model-internal beat calibration",
            "",
            "Current sweeps use `code_cycle_time_sec = 1 us`, so one qret beat is `d` code cycles and maps to `d us`.",
            "",
            "| code distance | one beat | reaction 1 | reaction 10 | reaction 100 |",
            "|---:|---:|---:|---:|---:|",
        ]
    )
    for distance in distances:
        beat_us = beat_duration_sec(distance) * 1e6
        lines.append(
            f"| {distance} | {beat_us:.0f} us | {beat_us:.0f} us | {beat_us * 10:.0f} us | {beat_us * 100 / 1000:.3f} ms |"
        )
    lines.extend(
        [
            "",
            "### Magic generation per factory",
            "",
            "| d | period 1 | period 4 | period 15 | period 30 | period 100 |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for distance in distances:
        cells = []
        for magic_period in (1, 4, 15, 30, 100):
            duration_us = magic_period * beat_duration_sec(distance) * 1e6
            throughput = factory_throughput_hz(magic_period, distance)
            cells.append(f"{duration_us:.0f} us ({throughput:,.1f}/s)")
        lines.append(f"| {distance} | " + " | ".join(cells) + " |")
    lines.extend(
        [
            "",
            "These are internal-model conversions, not evidence that a physical factory actually achieves these rates. Hardware realism requires an independently justified code-cycle time and factory protocol latency.",
            "",
        ]
    )
    (output / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    rows = collect_rows()
    if not rows:
        raise RuntimeError("no existing sweep rows found")
    write_report(args.output.expanduser().resolve(), rows)
    print(args.output / "summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
