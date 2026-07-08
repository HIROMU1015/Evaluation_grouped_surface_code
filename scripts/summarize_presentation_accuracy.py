#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


TOPOLOGY_SUMMARY = "presentation_accuracy_topology_summary.csv"
MAGIC_SUPPLY_SUMMARY = "presentation_accuracy_magic_supply_summary.csv"
REPRESENTATIVE_CASES = "presentation_accuracy_representative_cases.csv"

TOPOLOGY_ORDER = ("left_edge", "center_block", "right_edge")
MAGIC_PERIOD_ORDER = (15, 8, 4, 2, 1)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _format_csv_value(row.get(key)) for key in fieldnames})


def _format_csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return ""
        return f"{value:.10g}"
    return value


def _int_value(row: dict[str, str], key: str) -> int | None:
    value = row.get(key)
    if value in (None, ""):
        return None
    return int(float(value))


def _float_value(row: dict[str, str], key: str) -> float | None:
    value = row.get(key)
    if value in (None, ""):
        return None
    return float(value)


def _topology_short(row: dict[str, str]) -> str:
    raw = row.get("topology_name") or row.get("case_name") or ""
    for prefix in ("factory_", "baseline_", "fast_supply_"):
        raw = raw.replace(prefix, "")
    if raw.endswith("_center"):
        raw = raw[: -len("_center")]
    return raw


def _magic_condition(row: dict[str, str]) -> str:
    period = _int_value(row, "magic_generation_period")
    stock = _int_value(row, "resolved_maximum_magic_state_stock")
    if period is None:
        return "unknown"
    if period == 15:
        label = "baseline_p15"
    elif period == 8:
        label = "fast_p8"
    else:
        label = f"cheap_p{period}"
    if period == 1 and stock is not None and stock > 10000:
        label = f"{label}_large_stock"
    return label


def _metric(row: dict[str, str], primary: str, fallback: str | None = None) -> int | None:
    value = _int_value(row, primary)
    if value is None and fallback is not None:
        value = _int_value(row, fallback)
    return value


def _display_path(value: str | None) -> str | None:
    if not value:
        return value
    path = Path(value)
    if not path.is_absolute():
        return value
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return value


def _spread_pct(values: list[int | None]) -> float | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    minimum = min(present)
    if minimum == 0:
        return None
    return 100.0 * (max(present) - minimum) / minimum


def _min_names(values_by_name: dict[str, int | None]) -> list[str]:
    present = {name: value for name, value in values_by_name.items() if value is not None}
    if not present:
        return []
    minimum = min(present.values())
    return sorted(name for name, value in present.items() if value == minimum)


def _max_names(values_by_name: dict[str, int | None]) -> list[str]:
    present = {name: value for name, value in values_by_name.items() if value is not None}
    if not present:
        return []
    maximum = max(present.values())
    return sorted(name for name, value in present.items() if value == maximum)


def _average(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return sum(present) / len(present)


def _pct_improvement(before: int | None, after: int | None) -> float | None:
    if before in (None, 0) or after is None:
        return None
    return 100.0 * (before - after) / before


def _case_sort_key(row: dict[str, str]) -> tuple[int, int, int, str]:
    molecule = row.get("molecule") or "H999"
    try:
        molecule_key = int(molecule.removeprefix("H"))
    except ValueError:
        molecule_key = 999
    pf_key = 0 if row.get("pf_label") == "2nd" else 1
    period = _int_value(row, "magic_generation_period") or 999
    return molecule_key, pf_key, period, row.get("case_name") or ""


def build_topology_summary(rows: list[dict[str, str]], source_path: Path) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row.get("status") != "success":
            continue
        key = (row.get("molecule", ""), row.get("pf_label", ""), _magic_condition(row))
        groups[key].append(row)

    group_summaries: list[dict[str, Any]] = []
    for (molecule, pf_label, magic_condition), group_rows in sorted(groups.items()):
        by_topology = {_topology_short(row): row for row in group_rows}
        if not all(name in by_topology for name in TOPOLOGY_ORDER):
            continue

        runtime_by_topology = {
            name: _metric(by_topology[name], "runtime_with_topology")
            for name in TOPOLOGY_ORDER
        }
        qv_by_topology = {
            name: _metric(by_topology[name], "qubit_volume")
            for name in TOPOLOGY_ORDER
        }
        physical_by_topology = {
            name: _metric(by_topology[name], "physical_qubits")
            for name in TOPOLOGY_ORDER
        }
        distance_by_topology = {
            name: _metric(by_topology[name], "code_distance")
            for name in TOPOLOGY_ORDER
        }
        chip_by_topology = {
            name: _metric(by_topology[name], "chip_cells")
            for name in TOPOLOGY_ORDER
        }

        group_summaries.append(
            {
                "molecule": molecule,
                "pf_label": pf_label,
                "magic_condition": magic_condition,
                "runtime_spread_pct": _spread_pct(list(runtime_by_topology.values())),
                "qubit_volume_spread_pct": _spread_pct(list(qv_by_topology.values())),
                "runtime_min_topologies": ",".join(_min_names(runtime_by_topology)),
                "qubit_volume_min_topologies": ",".join(_min_names(qv_by_topology)),
                "qubit_volume_max_topologies": ",".join(_max_names(qv_by_topology)),
                "physical_qubits_spread": len(set(physical_by_topology.values())) > 1,
                "code_distance_spread": len(set(distance_by_topology.values())) > 1,
                "chip_cell_count_values": ",".join(
                    str(value) for value in sorted({v for v in chip_by_topology.values() if v is not None})
                ),
            }
        )

    aggregate_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in group_summaries:
        aggregate_groups[(row["pf_label"], row["magic_condition"])].append(row)

    output: list[dict[str, Any]] = []
    for (pf_label, magic_condition), rows_for_group in sorted(
        aggregate_groups.items(),
        key=lambda item: (item[0][0] != "2nd", item[0][1]),
    ):
        runtime_spreads = [row["runtime_spread_pct"] for row in rows_for_group]
        qv_spreads = [row["qubit_volume_spread_pct"] for row in rows_for_group]
        runtime_max_row = max(
            rows_for_group,
            key=lambda row: -1.0 if row["runtime_spread_pct"] is None else row["runtime_spread_pct"],
        )
        qv_max_row = max(
            rows_for_group,
            key=lambda row: -1.0 if row["qubit_volume_spread_pct"] is None else row["qubit_volume_spread_pct"],
        )
        runtime_min_counts = {name: 0 for name in TOPOLOGY_ORDER}
        qv_max_counts = {name: 0 for name in TOPOLOGY_ORDER}
        center_qv_min_cases = 0
        for row in rows_for_group:
            runtime_min_set = set(str(row["runtime_min_topologies"]).split(","))
            for name in TOPOLOGY_ORDER:
                if name in runtime_min_set:
                    runtime_min_counts[name] += 1
            qv_min_set = set(str(row["qubit_volume_min_topologies"]).split(","))
            if "center_block" in qv_min_set:
                center_qv_min_cases += 1
            qv_max_set = set(str(row["qubit_volume_max_topologies"]).split(","))
            for name in TOPOLOGY_ORDER:
                if name in qv_max_set:
                    qv_max_counts[name] += 1

        output.append(
            {
                "pf_label": pf_label,
                "magic_condition": magic_condition,
                "groups": len(rows_for_group),
                "runtime_spread_avg_pct": _average(runtime_spreads),
                "runtime_spread_max_pct": runtime_max_row["runtime_spread_pct"],
                "runtime_spread_max_case": (
                    f"{runtime_max_row['molecule']} {runtime_max_row['pf_label']} "
                    f"{runtime_max_row['magic_condition']}"
                ),
                "qubit_volume_spread_avg_pct": _average(qv_spreads),
                "qubit_volume_spread_max_pct": qv_max_row["qubit_volume_spread_pct"],
                "qubit_volume_spread_max_case": (
                    f"{qv_max_row['molecule']} {qv_max_row['pf_label']} "
                    f"{qv_max_row['magic_condition']}"
                ),
                "center_block_qubit_volume_min_cases": center_qv_min_cases,
                "left_edge_runtime_min_cases": runtime_min_counts["left_edge"],
                "center_block_runtime_min_cases": runtime_min_counts["center_block"],
                "right_edge_runtime_min_cases": runtime_min_counts["right_edge"],
                "left_edge_qubit_volume_max_cases": qv_max_counts["left_edge"],
                "center_block_qubit_volume_max_cases": qv_max_counts["center_block"],
                "right_edge_qubit_volume_max_cases": qv_max_counts["right_edge"],
                "chip_cell_count_values": ",".join(
                    sorted({str(row["chip_cell_count_values"]) for row in rows_for_group})
                ),
                "physical_qubits_spread_cases": sum(bool(row["physical_qubits_spread"]) for row in rows_for_group),
                "code_distance_spread_cases": sum(bool(row["code_distance_spread"]) for row in rows_for_group),
                "source_artifact": str(source_path),
            }
        )
    return output


def build_magic_supply_summary(rows: list[dict[str, str]], source_path: Path) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row.get("status") == "success":
            groups[(row.get("molecule", ""), row.get("pf_label", ""))].append(row)

    output: list[dict[str, Any]] = []
    case_rows: list[dict[str, Any]] = []
    for (molecule, pf_label), group_rows in sorted(groups.items(), key=lambda item: _case_sort_key(item[1][0])):
        by_condition = {_magic_condition(row): row for row in group_rows}
        p15 = by_condition.get("baseline_p15")
        p8 = by_condition.get("fast_p8")
        p4 = by_condition.get("cheap_p4")
        p2 = by_condition.get("cheap_p2")
        p1 = by_condition.get("cheap_p1")
        p1_large = by_condition.get("cheap_p1_large_stock")

        runtime_values = {
            "p15_runtime": _metric(p15 or {}, "total_runtime_with_topology"),
            "p8_runtime": _metric(p8 or {}, "total_runtime_with_topology"),
            "p4_runtime": _metric(p4 or {}, "total_runtime_with_topology"),
            "p2_runtime": _metric(p2 or {}, "total_runtime_with_topology"),
            "p1_runtime": _metric(p1 or {}, "total_runtime_with_topology"),
            "p1_large_stock_runtime": _metric(p1_large or {}, "total_runtime_with_topology"),
        }
        qv_values = {
            "p15_qubit_volume": _metric(p15 or {}, "total_qubit_volume"),
            "p8_qubit_volume": _metric(p8 or {}, "total_qubit_volume"),
            "p4_qubit_volume": _metric(p4 or {}, "total_qubit_volume"),
            "p2_qubit_volume": _metric(p2 or {}, "total_qubit_volume"),
            "p1_qubit_volume": _metric(p1 or {}, "total_qubit_volume"),
            "p1_large_stock_qubit_volume": _metric(p1_large or {}, "total_qubit_volume"),
        }
        magic_counts = {
            _metric(row, "total_magic_state_count", "step_magic_state_count")
            for row in group_rows
        }
        magic_depths = {
            _metric(row, "total_magic_state_depth", "step_magic_state_depth")
            for row in group_rows
        }
        chip_values = {_metric(row, "chip_cells") for row in group_rows}
        physical_values = {_metric(row, "physical_qubits") for row in group_rows}
        distance_values = {_metric(row, "code_distance") for row in group_rows}

        row = {
            "row_scope": "case",
            "molecule": molecule,
            "pf_label": pf_label,
            "topology": _topology_short(group_rows[0]),
            **runtime_values,
            **qv_values,
            "p15_to_p8_runtime_improvement_pct": _pct_improvement(
                runtime_values["p15_runtime"], runtime_values["p8_runtime"]
            ),
            "p15_to_p4_runtime_improvement_pct": _pct_improvement(
                runtime_values["p15_runtime"], runtime_values["p4_runtime"]
            ),
            "p15_to_p2_runtime_improvement_pct": _pct_improvement(
                runtime_values["p15_runtime"], runtime_values["p2_runtime"]
            ),
            "p15_to_p1_runtime_improvement_pct": _pct_improvement(
                runtime_values["p15_runtime"], runtime_values["p1_runtime"]
            ),
            "p8_to_p1_runtime_improvement_pct": _pct_improvement(
                runtime_values["p8_runtime"], runtime_values["p1_runtime"]
            ),
            "p15_to_p1_qubit_volume_improvement_pct": _pct_improvement(
                qv_values["p15_qubit_volume"], qv_values["p1_qubit_volume"]
            ),
            "p8_to_p1_qubit_volume_improvement_pct": _pct_improvement(
                qv_values["p8_qubit_volume"], qv_values["p1_qubit_volume"]
            ),
            "p1_large_stock_matches_p1_runtime": runtime_values["p1_runtime"]
            == runtime_values["p1_large_stock_runtime"],
            "p1_large_stock_matches_p1_qubit_volume": qv_values["p1_qubit_volume"]
            == qv_values["p1_large_stock_qubit_volume"],
            "magic_state_count": next(iter(magic_counts)) if len(magic_counts) == 1 else "",
            "magic_state_depth": next(iter(magic_depths)) if len(magic_depths) == 1 else "",
            "magic_state_count_invariant": len(magic_counts) == 1,
            "magic_state_depth_invariant": len(magic_depths) == 1,
            "chip_cell_count_invariant": len(chip_values) == 1,
            "physical_qubits_invariant": len(physical_values) == 1,
            "code_distance_invariant": len(distance_values) == 1,
            "source_artifact": str(source_path),
        }
        case_rows.append(row)
        output.append(row)

    by_pf: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in case_rows:
        by_pf[row["pf_label"]].append(row)
    for pf_label, pf_rows in sorted(by_pf.items(), key=lambda item: item[0] != "2nd"):
        p15_total = sum(row["p15_runtime"] or 0 for row in pf_rows)
        p8_total = sum(row["p8_runtime"] or 0 for row in pf_rows)
        p1_total = sum(row["p1_runtime"] or 0 for row in pf_rows)
        p15_qv_total = sum(row["p15_qubit_volume"] or 0 for row in pf_rows)
        p1_qv_total = sum(row["p1_qubit_volume"] or 0 for row in pf_rows)
        p8_qv_total = sum(row["p8_qubit_volume"] or 0 for row in pf_rows)
        output.append(
            {
                "row_scope": "pf_summary",
                "molecule": "ALL",
                "pf_label": pf_label,
                "topology": "center_block",
                "p15_runtime": p15_total,
                "p8_runtime": p8_total,
                "p1_runtime": p1_total,
                "p15_qubit_volume": p15_qv_total,
                "p8_qubit_volume": p8_qv_total,
                "p1_qubit_volume": p1_qv_total,
                "p15_to_p8_runtime_improvement_pct": _pct_improvement(p15_total, p8_total),
                "p15_to_p1_runtime_improvement_pct": _pct_improvement(p15_total, p1_total),
                "p8_to_p1_runtime_improvement_pct": _pct_improvement(p8_total, p1_total),
                "p15_to_p1_qubit_volume_improvement_pct": _pct_improvement(p15_qv_total, p1_qv_total),
                "p8_to_p1_qubit_volume_improvement_pct": _pct_improvement(p8_qv_total, p1_qv_total),
                "p1_large_stock_matches_p1_runtime": all(
                    row["p1_large_stock_matches_p1_runtime"] for row in pf_rows
                ),
                "p1_large_stock_matches_p1_qubit_volume": all(
                    row["p1_large_stock_matches_p1_qubit_volume"] for row in pf_rows
                ),
                "magic_state_count_invariant": all(row["magic_state_count_invariant"] for row in pf_rows),
                "magic_state_depth_invariant": all(row["magic_state_depth_invariant"] for row in pf_rows),
                "chip_cell_count_invariant": all(row["chip_cell_count_invariant"] for row in pf_rows),
                "physical_qubits_invariant": all(row["physical_qubits_invariant"] for row in pf_rows),
                "code_distance_invariant": all(row["code_distance_invariant"] for row in pf_rows),
                "source_artifact": str(source_path),
            }
        )
    return output


def build_representative_cases(
    topology_rows: list[dict[str, str]],
    magic_rows: list[dict[str, str]],
    representative_molecules: set[str],
    topology_source: Path,
    magic_source: Path,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for source_name, rows, source_path in (
        ("topology_sweep", topology_rows, topology_source),
        ("magic_supply_sweep", magic_rows, magic_source),
    ):
        for row in sorted(rows, key=_case_sort_key):
            if row.get("status") != "success" or row.get("molecule") not in representative_molecules:
                continue
            output.append(
                {
                    "source_sweep": source_name,
                    "molecule": row.get("molecule"),
                    "pf_label": row.get("pf_label"),
                    "circuit_scope": row.get("compiled_circuit_scope"),
                    "qpe_scaling_model": row.get("qpe_scaling_model"),
                    "magic_condition": _magic_condition(row),
                    "topology_condition": _topology_short(row),
                    "case_name": row.get("case_name"),
                    "compile_mode": row.get("compile_mode"),
                    "status": row.get("status"),
                    "qpe_action_count": _metric(row, "qpe_action_count"),
                    "runtime": _metric(row, "runtime_with_topology"),
                    "runtime_without_topology": _metric(row, "runtime_without_topology"),
                    "total_runtime": _metric(row, "total_runtime_with_topology"),
                    "qubit_volume": _metric(row, "qubit_volume"),
                    "total_qubit_volume": _metric(row, "total_qubit_volume"),
                    "magic_state_count": _metric(row, "step_magic_state_count"),
                    "magic_state_depth": _metric(row, "step_magic_state_depth"),
                    "total_magic_state_count": _metric(row, "total_magic_state_count"),
                    "total_magic_state_depth": _metric(row, "total_magic_state_depth"),
                    "chip_cell_count": _metric(row, "chip_cells"),
                    "physical_qubits": _metric(row, "physical_qubits"),
                    "code_distance": _metric(row, "code_distance"),
                    "topology_path": _display_path(row.get("topology_path")),
                    "source_artifact": str(source_path),
                }
            )
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Regenerate presentation accuracy CSV summaries from existing "
            "surface-code architecture sweep artifacts. This script only reads "
            "CSV artifacts; it does not call qret or compile circuits."
        )
    )
    parser.add_argument(
        "--topology-results",
        required=True,
        type=Path,
        help="Existing topology sweep results.csv artifact.",
    )
    parser.add_argument(
        "--magic-results",
        required=True,
        type=Path,
        help="Existing magic-supply sweep results.csv artifact.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory where presentation_accuracy_*.csv files are written.",
    )
    parser.add_argument(
        "--representative-molecules",
        default="H2,H4,H6,H8,H10,H11",
        help="Comma-separated molecule labels for representative_cases output.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    topology_results = args.topology_results.expanduser()
    magic_results = args.magic_results.expanduser()
    output_dir = args.output_dir.expanduser()

    topology_rows = _read_csv(topology_results)
    magic_rows = _read_csv(magic_results)
    representative_molecules = {
        item.strip() for item in str(args.representative_molecules).split(",") if item.strip()
    }

    topology_summary = build_topology_summary(topology_rows, topology_results)
    magic_summary = build_magic_supply_summary(magic_rows, magic_results)
    representative_cases = build_representative_cases(
        topology_rows,
        magic_rows,
        representative_molecules,
        topology_results,
        magic_results,
    )

    topology_fields = [
        "pf_label",
        "magic_condition",
        "groups",
        "runtime_spread_avg_pct",
        "runtime_spread_max_pct",
        "runtime_spread_max_case",
        "qubit_volume_spread_avg_pct",
        "qubit_volume_spread_max_pct",
        "qubit_volume_spread_max_case",
        "center_block_qubit_volume_min_cases",
        "left_edge_runtime_min_cases",
        "center_block_runtime_min_cases",
        "right_edge_runtime_min_cases",
        "left_edge_qubit_volume_max_cases",
        "center_block_qubit_volume_max_cases",
        "right_edge_qubit_volume_max_cases",
        "chip_cell_count_values",
        "physical_qubits_spread_cases",
        "code_distance_spread_cases",
        "source_artifact",
    ]
    magic_fields = [
        "row_scope",
        "molecule",
        "pf_label",
        "topology",
        "p15_runtime",
        "p8_runtime",
        "p4_runtime",
        "p2_runtime",
        "p1_runtime",
        "p1_large_stock_runtime",
        "p15_qubit_volume",
        "p8_qubit_volume",
        "p4_qubit_volume",
        "p2_qubit_volume",
        "p1_qubit_volume",
        "p1_large_stock_qubit_volume",
        "p15_to_p8_runtime_improvement_pct",
        "p15_to_p4_runtime_improvement_pct",
        "p15_to_p2_runtime_improvement_pct",
        "p15_to_p1_runtime_improvement_pct",
        "p8_to_p1_runtime_improvement_pct",
        "p15_to_p1_qubit_volume_improvement_pct",
        "p8_to_p1_qubit_volume_improvement_pct",
        "p1_large_stock_matches_p1_runtime",
        "p1_large_stock_matches_p1_qubit_volume",
        "magic_state_count",
        "magic_state_depth",
        "magic_state_count_invariant",
        "magic_state_depth_invariant",
        "chip_cell_count_invariant",
        "physical_qubits_invariant",
        "code_distance_invariant",
        "source_artifact",
    ]
    representative_fields = [
        "source_sweep",
        "molecule",
        "pf_label",
        "circuit_scope",
        "qpe_scaling_model",
        "magic_condition",
        "topology_condition",
        "case_name",
        "compile_mode",
        "status",
        "qpe_action_count",
        "runtime",
        "runtime_without_topology",
        "total_runtime",
        "qubit_volume",
        "total_qubit_volume",
        "magic_state_count",
        "magic_state_depth",
        "total_magic_state_count",
        "total_magic_state_depth",
        "chip_cell_count",
        "physical_qubits",
        "code_distance",
        "topology_path",
        "source_artifact",
    ]

    _write_csv(output_dir / TOPOLOGY_SUMMARY, topology_summary, topology_fields)
    _write_csv(output_dir / MAGIC_SUPPLY_SUMMARY, magic_summary, magic_fields)
    _write_csv(output_dir / REPRESENTATIVE_CASES, representative_cases, representative_fields)
    print(f"wrote {output_dir / TOPOLOGY_SUMMARY}")
    print(f"wrote {output_dir / MAGIC_SUPPLY_SUMMARY}")
    print(f"wrote {output_dir / REPRESENTATIVE_CASES}")


if __name__ == "__main__":
    main()
