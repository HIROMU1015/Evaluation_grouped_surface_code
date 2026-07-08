#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml


NEEDLE = "LATTICE_SURGERY_MAGIC"
SYMBOL_KEY_RE = re.compile(
    r"(magic[_-]?factory|factory[_-]?symbol|magicFactory|factory|m[_-]?symbol|msymbol|m[_-]?target|mtarget|symbol)",
    re.IGNORECASE,
)
PREFERRED_FIELD_RE = re.compile(
    r"(magic[_-]?factory|factory[_-]?symbol|factory|m[_-]?symbol|msymbol|m[_-]?target|mtarget)",
    re.IGNORECASE,
)
QUBIT_FIELD_RE = re.compile(r"(qubit|qtarget|observable)", re.IGNORECASE)


def _path_text(path: Iterable[str | int]) -> str:
    out = "$"
    for item in path:
        if isinstance(item, int):
            out += f"[{item}]"
        elif re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", item):
            out += f".{item}"
        else:
            out += "[" + json.dumps(item, ensure_ascii=True) + "]"
    return out


def _relative_path_text(path: Iterable[str | int]) -> str:
    parts: list[str] = []
    for item in path:
        if isinstance(item, int):
            parts.append(f"[{item}]")
        elif parts:
            parts.append(f".{item}")
        else:
            parts.append(str(item))
    return "".join(parts) if parts else "$"


def _preview(value: Any, *, depth: int = 2, max_items: int = 8, max_string: int = 140) -> Any:
    if depth <= 0:
        if isinstance(value, dict):
            return {"...": f"{len(value)} keys"}
        if isinstance(value, list):
            return [f"... {len(value)} items"]
        if isinstance(value, str) and len(value) > max_string:
            return value[:max_string] + "...<truncated>"
        return value
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= max_items:
                result["..."] = f"{len(value) - max_items} more keys"
                break
            result[str(key)] = _preview(
                item,
                depth=depth - 1,
                max_items=max_items,
                max_string=max_string,
            )
        return result
    if isinstance(value, list):
        result = [
            _preview(item, depth=depth - 1, max_items=max_items, max_string=max_string)
            for item in value[:max_items]
        ]
        if len(value) > max_items:
            result.append(f"... {len(value) - max_items} more items")
        return result
    if isinstance(value, str) and len(value) > max_string:
        return value[:max_string] + "...<truncated>"
    return value


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _coord_text(coord: Any) -> str:
    if isinstance(coord, (list, tuple)):
        return "(" + ",".join(str(int(x)) if isinstance(x, int) else str(x) for x in coord) + ")"
    return str(coord)


def load_topology_magic_factories(topology_path: Path) -> dict[str, str]:
    with topology_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    result: dict[str, str] = {}
    for grid in data.get("grids", []) if isinstance(data, Mapping) else []:
        if not isinstance(grid, Mapping):
            continue
        for factory in grid.get("magic_factory", []) or []:
            if not isinstance(factory, Mapping):
                continue
            symbol = factory.get("symbol")
            coord = factory.get("coord")
            if symbol is None:
                continue
            result[str(symbol)] = _coord_text(coord)
    return result


def _contains_needle(value: Any, needle_lower: str = NEEDLE.lower(), *, depth: int = 2) -> bool:
    if isinstance(value, str):
        return needle_lower in value.lower()
    if isinstance(value, (int, float, bool)) or value is None:
        return False
    if depth <= 0:
        return False
    if isinstance(value, Mapping):
        for key, item in value.items():
            if needle_lower in str(key).lower():
                return True
            if _contains_needle(item, needle_lower, depth=depth - 1):
                return True
    elif isinstance(value, list):
        return any(_contains_needle(item, needle_lower, depth=depth - 1) for item in value)
    return False


def _direct_scalar_contains_needle(value: Any, needle_lower: str = NEEDLE.lower()) -> bool:
    if isinstance(value, str):
        return needle_lower in value.lower()
    if isinstance(value, Mapping):
        for key, item in value.items():
            if needle_lower in str(key).lower():
                return True
            if isinstance(item, str) and needle_lower in item.lower():
                return True
        return False
    if isinstance(value, list):
        return any(isinstance(item, str) and needle_lower in item.lower() for item in value)
    return False


def _symbol_from_value(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, str):
        matches = re.findall(r"-?\d+", value)
        if len(matches) == 1:
            return str(int(matches[0]))
        if value.strip().isdigit():
            return str(int(value.strip()))
        return None
    if isinstance(value, Mapping):
        for key in ("symbol", "value", "id", "factory", "magic_factory", "mtarget", "m_target"):
            if key in value:
                candidate = _symbol_from_value(value[key])
                if candidate is not None:
                    return candidate
        for item in value.values():
            candidate = _symbol_from_value(item)
            if candidate is not None:
                return candidate
    if isinstance(value, list):
        for item in value:
            candidate = _symbol_from_value(item)
            if candidate is not None:
                return candidate
    return None


def _field_priority(path: tuple[str | int, ...]) -> int:
    text = ".".join(str(part) for part in path).lower()
    if "mtarget" in text or "m_target" in text:
        return 0
    if "magic_factory" in text or "magicfactory" in text:
        return 1
    if "factory_symbol" in text or "factory" in text:
        return 2
    if "m_symbol" in text or "msymbol" in text:
        return 3
    if text.endswith(".symbol") and ("magic" in text or "route" in text):
        return 4
    if text.endswith(".symbol"):
        return 9
    return 10


def _iter_symbol_candidates(
    value: Any,
    *,
    max_depth: int,
    path: tuple[str | int, ...] = (),
) -> Iterable[tuple[tuple[str | int, ...], str, Any]]:
    if max_depth < 0:
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            child_path = (*path, str(key))
            key_text = str(key)
            if SYMBOL_KEY_RE.search(key_text):
                joined_path = ".".join(str(part) for part in child_path)
                if key_text.lower() == "symbol" and QUBIT_FIELD_RE.search(joined_path):
                    pass
                else:
                    symbol = _symbol_from_value(item)
                    if symbol is not None:
                        yield child_path, symbol, item
            yield from _iter_symbol_candidates(item, max_depth=max_depth - 1, path=child_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _iter_symbol_candidates(item, max_depth=max_depth - 1, path=(*path, index))


def _resolve_factory_symbol(obj: Mapping[str, Any]) -> tuple[str | None, str | None, list[dict[str, Any]]]:
    candidates = list(_iter_symbol_candidates(obj, max_depth=6))
    candidates.sort(key=lambda item: (_field_priority(item[0]), len(item[0])))
    details = [
        {
            "field": _relative_path_text(path),
            "symbol": symbol,
            "priority": _field_priority(path),
            "value_preview": _preview(raw_value, depth=1),
        }
        for path, symbol, raw_value in candidates[:8]
    ]
    if not candidates:
        return None, None, details
    path, symbol, _ = candidates[0]
    return symbol, _relative_path_text(path), details


def _is_direct_instruction_candidate(obj: Mapping[str, Any]) -> bool:
    for key in (
        "type",
        "op",
        "kind",
        "name",
        "gate",
        "instruction",
        "instruction_type",
        "operation",
    ):
        if key in obj and _contains_needle(obj[key], depth=3):
            return True
    if not _direct_scalar_contains_needle(obj):
        return False
    return any(
        str(key).lower() in {"mtarget", "m_target", "qtarget", "q_target", "target"}
        for key in obj
    )


def _container_weight(value: Any, *, depth: int = 2) -> int:
    if depth < 0:
        return 0
    if isinstance(value, Mapping):
        return len(value) + sum(_container_weight(item, depth=depth - 1) for item in value.values())
    if isinstance(value, list):
        return len(value) + sum(_container_weight(item, depth=depth - 1) for item in value[:20])
    return 1


def _choose_instruction_dict(
    stack: list[tuple[tuple[str | int, ...], Mapping[str, Any]]],
) -> tuple[tuple[str | int, ...], Mapping[str, Any]]:
    best: tuple[int, int, tuple[str | int, ...], Mapping[str, Any]] | None = None
    for distance, (path, obj) in enumerate(reversed(stack[-10:])):
        if not _contains_needle(obj, depth=3):
            continue
        symbol, field, _ = _resolve_factory_symbol(obj)
        score = 0
        if symbol is not None:
            score += 100 - (_field_priority(tuple(field.split("."))) if field else 0)
        if any(str(key).lower() in {"mtarget", "m_target", "qtarget", "q_target", "target"} for key in obj):
            score += 25
        if _direct_scalar_contains_needle(obj):
            score += 20
        path_text = _path_text(path).lower()
        if any(token in path_text for token in ("instruction", "operation", "program", "body")):
            score += 10
        score += max(0, 10 - distance)
        weight = _container_weight(obj, depth=2)
        if weight > 250:
            score -= 200
        candidate = (score, -distance, path, obj)
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    if best is None:
        return stack[-1]
    return best[2], best[3]


def extract_usage(
    input_path: Path,
    topology_path: Path,
    *,
    case_name: str,
    molecule: str,
    pf_label: str,
    topology_variant: str,
    max_samples: int = 12,
) -> dict[str, Any]:
    topology_symbols = load_topology_magic_factories(topology_path)
    with input_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    selected_paths: set[str] = set()
    symbol_counts: Counter[str] = Counter()
    coordinate_counts: Counter[str] = Counter()
    field_counts: Counter[str] = Counter()
    missing = 0
    sample_instruction_paths: list[str] = []
    unresolved_instruction_paths: list[str] = []
    samples: list[dict[str, Any]] = []

    def record_instruction(obj_path: tuple[str | int, ...], obj: Mapping[str, Any]) -> None:
        nonlocal missing
        path_string = _path_text(obj_path)
        if path_string in selected_paths:
            return
        selected_paths.add(path_string)
        symbol, field_name, candidates = _resolve_factory_symbol(obj)
        if symbol is None:
            missing += 1
            if len(unresolved_instruction_paths) < max_samples:
                unresolved_instruction_paths.append(path_string)
        else:
            symbol_counts[symbol] += 1
            coord = topology_symbols.get(symbol, f"unknown_symbol:{symbol}")
            coordinate_counts[coord] += 1
            if field_name is not None:
                field_counts[field_name] += 1
        if len(sample_instruction_paths) < max_samples:
            sample_instruction_paths.append(path_string)
        if len(samples) < max_samples:
            samples.append(
                {
                    "path": path_string,
                    "resolved_symbol": symbol,
                    "resolved_field": field_name,
                    "candidate_fields": candidates,
                    "preview": _preview(obj, depth=2),
                }
            )

    def fast_visit(value: Any, path: tuple[str | int, ...]) -> None:
        if isinstance(value, Mapping):
            if _is_direct_instruction_candidate(value):
                record_instruction(path, value)
                return
            for key, item in value.items():
                fast_visit(item, (*path, str(key)))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                fast_visit(item, (*path, index))

    fast_visit(data, ())

    def record(stack: list[tuple[tuple[str | int, ...], Mapping[str, Any]]]) -> None:
        if not stack:
            return
        obj_path, obj = _choose_instruction_dict(stack)
        record_instruction(obj_path, obj)

    def visit(value: Any, path: tuple[str | int, ...], stack: list[tuple[tuple[str | int, ...], Mapping[str, Any]]]) -> None:
        if isinstance(value, Mapping):
            new_stack = [*stack, (path, value)]
            for key, item in value.items():
                if NEEDLE.lower() in str(key).lower():
                    record(new_stack)
                visit(item, (*path, str(key)), new_stack)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, (*path, index), stack)
        elif isinstance(value, str) and NEEDLE.lower() in value.lower():
            record(stack)

    if not selected_paths:
        visit(data, (), [])
    total = len(selected_paths)
    candidate_fields = dict(sorted(field_counts.items()))
    if total == 0:
        confidence = "low"
    elif missing == 0 and any(PREFERRED_FIELD_RE.search(field) for field in candidate_fields):
        confidence = "high"
    elif missing < total:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "case_name": case_name,
        "molecule": molecule,
        "pf_label": pf_label,
        "topology_variant": topology_variant,
        "input_json_size_bytes": input_path.stat().st_size,
        "topology_path": str(topology_path),
        "total_lattice_surgery_magic_ops": total,
        "final_factory_symbol_counts": dict(sorted(symbol_counts.items(), key=lambda item: int(item[0]) if item[0].lstrip("-").isdigit() else item[0])),
        "final_factory_coordinate_counts": dict(sorted(coordinate_counts.items())),
        "missing_factory_symbol_count": missing,
        "candidate_field_names_used": candidate_fields,
        "sample_instruction_paths": sample_instruction_paths,
        "unresolved_instruction_paths": unresolved_instruction_paths,
        "topology_factory_symbols": dict(sorted(topology_symbols.items(), key=lambda item: int(item[0]) if item[0].lstrip("-").isdigit() else item[0])),
        "topology_factory_coordinates": sorted(set(topology_symbols.values())),
        "confidence": confidence,
        "sample_previews": samples,
    }


def _csv_row(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "case_name": result.get("case_name"),
        "molecule": result.get("molecule"),
        "pf_label": result.get("pf_label"),
        "topology_variant": result.get("topology_variant"),
        "total_lattice_surgery_magic_ops": result.get("total_lattice_surgery_magic_ops"),
        "final_factory_symbol_counts": _json_dumps(result.get("final_factory_symbol_counts", {})),
        "final_factory_coordinate_counts": _json_dumps(result.get("final_factory_coordinate_counts", {})),
        "missing_factory_symbol_count": result.get("missing_factory_symbol_count"),
        "candidate_field_names_used": _json_dumps(result.get("candidate_field_names_used", {})),
        "confidence": result.get("confidence"),
        "input_json_size_bytes": result.get("input_json_size_bytes"),
        "topology_path": result.get("topology_path"),
        "sample_instruction_paths": _json_dumps(result.get("sample_instruction_paths", [])),
    }


def write_outputs(result: Mapping[str, Any], output_json: Path, output_csv: Path, summary_md: Path) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    summary_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    fieldnames = list(_csv_row(result).keys())
    with output_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(_csv_row(result))
    summary_md.write_text(_summary_markdown([result]), encoding="utf-8")


def _summary_markdown(results: list[Mapping[str, Any]]) -> str:
    lines = [
        "# Post-routing Magic Factory Usage Extraction",
        "",
        "| case | molecule | topology | ops | symbols | coordinates | missing | confidence |",
        "|---|---|---|---:|---|---|---:|---|",
    ]
    for result in results:
        lines.append(
            "| {case} | {molecule} | `{topology}` | {ops} | `{symbols}` | `{coords}` | {missing} | {confidence} |".format(
                case=result.get("case_name"),
                molecule=result.get("molecule"),
                topology=result.get("topology_variant"),
                ops=result.get("total_lattice_surgery_magic_ops"),
                symbols=_json_dumps(result.get("final_factory_symbol_counts", {})),
                coords=_json_dumps(result.get("final_factory_coordinate_counts", {})),
                missing=result.get("missing_factory_symbol_count"),
                confidence=result.get("confidence"),
            )
        )
    lines.extend(
        [
            "",
            "## Field Names Used",
            "",
        ]
    )
    for result in results:
        lines.append(
            "- `{}`: `{}`".format(
                result.get("case_name"),
                _json_dumps(result.get("candidate_field_names_used", {})),
            )
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract compact final magic factory usage from qret post-routing JSON."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--topology", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--output-csv", required=True, type=Path)
    parser.add_argument("--summary-md", required=True, type=Path)
    parser.add_argument("--case-name", required=True)
    parser.add_argument("--molecule", required=True)
    parser.add_argument("--pf-label", required=True)
    parser.add_argument("--topology-variant", required=True)
    args = parser.parse_args()

    result = extract_usage(
        args.input,
        args.topology,
        case_name=args.case_name,
        molecule=args.molecule,
        pf_label=args.pf_label,
        topology_variant=args.topology_variant,
    )
    write_outputs(result, args.output_json, args.output_csv, args.summary_md)


if __name__ == "__main__":
    main()
