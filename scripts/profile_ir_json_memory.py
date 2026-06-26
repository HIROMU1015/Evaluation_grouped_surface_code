#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gc
import json
import resource
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from trotterlib import surface_code as sc  # noqa: E402


def _rss() -> int | None:
    return sc._current_rss_kb()


def _maxrss() -> int:
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)


def _skip_ws(text: str, index: int) -> int:
    while index < len(text) and text[index] in " \t\r\n":
        index += 1
    return index


def _expect(text: str, index: int, token: str) -> int:
    index = _skip_ws(text, index)
    if not text.startswith(token, index):
        raise ValueError(f"expected {token!r} at {index}")
    return index + len(token)


def _iter_circuit_objects(text: str) -> Any:
    decoder = json.JSONDecoder()
    key = '"circuit_list"'
    index = text.find(key)
    if index < 0:
        return
    index = _expect(text, index + len(key), ":")
    index = _expect(text, index, "[")
    first = True
    while True:
        index = _skip_ws(text, index)
        if index >= len(text):
            return
        if text[index] == "]":
            return
        if not first:
            index = _expect(text, index, ",")
            index = _skip_ws(text, index)
        circuit, index = decoder.raw_decode(text, index)
        yield circuit
        first = False


def _mode_full(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    circuits = payload.get("circuit_list", [])
    instruction_count = 0
    helper_count = 0
    for circuit in circuits:
        name = str(circuit.get("name", ""))
        if name != "main":
            helper_count += 1
        for bb in circuit.get("bb_list", []):
            instruction_count += len(bb.get("inst_list", []))
    return {
        "circuit_count": len(circuits),
        "helper_count": helper_count,
        "extracted_instruction_count": instruction_count,
        "retained_object_type": type(payload).__name__,
    }


def _mode_circuit_scan(path: Path, *, retain: str) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    circuit_count = 0
    helper_count = 0
    extracted_instruction_count = 0
    retained: list[Any] = []
    for circuit in _iter_circuit_objects(text):
        circuit_count += 1
        name = str(circuit.get("name", ""))
        is_helper = name != "main"
        helper_count += int(is_helper)
        keep = retain == "all" or (retain == "helpers" and is_helper) or (
            retain == "main_metadata" and name == "main"
        )
        if keep:
            if retain == "main_metadata":
                retained.append({key: value for key, value in circuit.items() if key != "bb_list"})
            else:
                retained.append(circuit)
        if keep or retain == "scan_only":
            for bb in circuit.get("bb_list", []):
                extracted_instruction_count += len(bb.get("inst_list", []))
    return {
        "circuit_count": circuit_count,
        "helper_count": helper_count,
        "extracted_instruction_count": extracted_instruction_count,
        "retained_count": len(retained),
        "retained_mode": retain,
        "text_bytes": len(text.encode("utf-8")),
    }


def run_mode(path: Path, mode: str) -> dict[str, Any]:
    before = _rss()
    max_before = _maxrss()
    started = time.perf_counter()
    if mode == "full_json_load":
        details = _mode_full(path)
    elif mode == "scan_only":
        details = _mode_circuit_scan(path, retain="scan_only")
    elif mode == "helpers_only":
        details = _mode_circuit_scan(path, retain="helpers")
    elif mode == "main_metadata_only":
        details = _mode_circuit_scan(path, retain="main_metadata")
    else:
        raise ValueError(f"unknown mode: {mode}")
    elapsed = time.perf_counter() - started
    after = _rss()
    max_after = _maxrss()
    gc.collect()
    after_gc = _rss()
    return {
        "mode": mode,
        "path": str(path),
        "input_size_bytes": path.stat().st_size,
        "elapsed_seconds": elapsed,
        "python_current_rss_before_kb": before,
        "python_current_rss_after_kb": after,
        "python_current_rss_after_gc_kb": after_gc,
        "python_current_rss_delta_kb": (
            None if before is None or after is None else int(after) - int(before)
        ),
        "python_current_rss_delta_after_gc_kb": (
            None if before is None or after_gc is None else int(after_gc) - int(before)
        ),
        "python_self_maxrss_before_kb": max_before,
        "python_self_maxrss_after_kb": max_after,
        "python_self_maxrss_delta_kb": max(0, max_after - max_before),
        **details,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ir_json", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "benchmark_results" / "profiling" / "ir_json_memory.json",
    )
    parser.add_argument(
        "--mode",
        action="append",
        default=[],
        choices=["full_json_load", "scan_only", "helpers_only", "main_metadata_only"],
    )
    args = parser.parse_args()
    modes = args.mode or [
        "full_json_load",
        "scan_only",
        "helpers_only",
        "main_metadata_only",
    ]
    results = [run_mode(args.ir_json.expanduser().resolve(), mode) for mode in modes]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"results": results}, ensure_ascii=True, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
