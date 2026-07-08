#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable


FIELD_HINT_RE = re.compile(
    r"(factory|magic|symbol|coord|route|path|target|mtarget|m_target)",
    re.IGNORECASE,
)


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


def _preview(value: Any, *, depth: int = 2, max_items: int = 8, max_string: int = 160) -> Any:
    if depth <= 0:
        if isinstance(value, dict):
            return {"...": f"{len(value)} keys"}
        if isinstance(value, list):
            return [f"... {len(value)} items"]
        if isinstance(value, str) and len(value) > max_string:
            return value[:max_string] + "...<truncated>"
        return value
    if isinstance(value, dict):
        items = list(value.items())
        result: dict[str, Any] = {}
        for key, item in items[:max_items]:
            result[str(key)] = _preview(
                item,
                depth=depth - 1,
                max_items=max_items,
                max_string=max_string,
            )
        if len(items) > max_items:
            result["..."] = f"{len(items) - max_items} more keys"
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


def _contains_needle(value: Any, needle_lower: str, *, depth: int) -> bool:
    if isinstance(value, str):
        return needle_lower in value.lower()
    if isinstance(value, (int, float, bool)) or value is None:
        return False
    if depth <= 0:
        return False
    if isinstance(value, dict):
        for key, item in value.items():
            if needle_lower in str(key).lower():
                return True
            if _contains_needle(item, needle_lower, depth=depth - 1):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_needle(item, needle_lower, depth=depth - 1) for item in value)
    return False


def _candidate_fields(value: Any, *, depth: int, path: tuple[str | int, ...] = ()) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    if depth < 0:
        return fields
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = (*path, str(key))
            if FIELD_HINT_RE.search(str(key)):
                fields.append(
                    {
                        "path": _path_text(child_path),
                        "key": str(key),
                        "preview": _preview(item, depth=1),
                    }
                )
            fields.extend(_candidate_fields(item, depth=depth - 1, path=child_path))
    elif isinstance(value, list):
        for index, item in enumerate(value[:32]):
            fields.extend(_candidate_fields(item, depth=depth - 1, path=(*path, index)))
    return fields[:80]


def _iter_matching_dicts(
    value: Any,
    *,
    needle_lower: str,
    context_depth: int,
    path: tuple[str | int, ...] = (),
) -> Iterable[tuple[tuple[str | int, ...], dict[str, Any]]]:
    if isinstance(value, dict):
        if _contains_needle(value, needle_lower, depth=max(1, context_depth)):
            yield path, value
        for key, item in value.items():
            yield from _iter_matching_dicts(
                item,
                needle_lower=needle_lower,
                context_depth=context_depth,
                path=(*path, str(key)),
            )
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _iter_matching_dicts(
                item,
                needle_lower=needle_lower,
                context_depth=context_depth,
                path=(*path, index),
            )


def inspect_schema(
    input_path: Path,
    *,
    needle: str,
    max_records: int,
    context_depth: int,
) -> dict[str, Any]:
    with input_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path, obj in _iter_matching_dicts(
        data,
        needle_lower=needle.lower(),
        context_depth=context_depth,
    ):
        path_string = _path_text(path)
        if path_string in seen:
            continue
        seen.add(path_string)
        records.append(
            {
                "json_path": path_string,
                "keys": [str(key) for key in obj.keys()],
                "candidate_fields": _candidate_fields(obj, depth=context_depth),
                "preview": _preview(obj, depth=context_depth),
            }
        )
        if len(records) >= max_records:
            break

    return {
        "input": str(input_path),
        "needle": needle,
        "max_records": max_records,
        "context_depth": context_depth,
        "records_emitted": len(records),
        "records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect qret pipeline-state JSON near matching instructions."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--needle", default="LATTICE_SURGERY_MAGIC")
    parser.add_argument("--max-records", default=20, type=int)
    parser.add_argument("--context-depth", default=2, type=int)
    args = parser.parse_args()

    result = inspect_schema(
        args.input,
        needle=args.needle,
        max_records=max(1, args.max_records),
        context_depth=max(1, args.context_depth),
    )
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
