#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import resource
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from trotterlib import surface_code as sc  # noqa: E402


METHODS = ("full", "full_release", "metric_fields")


def _current_rss_kb() -> int | None:
    status_path = Path("/proc/self/status")
    try:
        with status_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(parts[1])
                    return None
    except (OSError, ValueError):
        return None
    return None


class _Sampler:
    def __init__(self, interval_seconds: float) -> None:
        self._interval_seconds = float(interval_seconds)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.peak_kb: int | None = None
        self.sample_count = 0

    def start(self) -> None:
        first = _current_rss_kb()
        if first is not None:
            self.peak_kb = int(first)
            self.sample_count = 1
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            sample = _current_rss_kb()
            if sample is None:
                continue
            self.sample_count += 1
            if self.peak_kb is None or int(sample) > self.peak_kb:
                self.peak_kb = int(sample)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self._interval_seconds * 4.0))
        final = _current_rss_kb()
        if final is not None:
            self.sample_count += 1
            if self.peak_kb is None or int(final) > self.peak_kb:
                self.peak_kb = int(final)


def _metrics_hash(metrics: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(metrics),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_full(path: Path) -> tuple[Mapping[str, Any], int]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, Mapping):
        raise ValueError(f"compile_info root is not an object: {path}")
    return payload, len(payload)


def _extract_metric_fields(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        field: payload[field]
        for field in sc._SURFACE_CODE_COMPILE_INFO_METRIC_FIELDS
        if field in payload
    }


def _measure_child(path: Path, method: str, interval: float) -> dict[str, Any]:
    path = path.expanduser().resolve()
    before = _current_rss_kb()
    sampler = _Sampler(interval)
    sampler.start()
    started = time.perf_counter()

    after_extraction: int | None = None
    after_del: int | None = None
    after_release: int | None = None
    gc_collected: int | None = None
    field_count: int | None = None
    extracted_field_count: int | None = None
    extraction_mode = method

    if method == "full":
        payload, field_count = _load_full(path)
        extracted_field_count = len(payload)
        normalized = sc.normalize_surface_code_step_metrics(payload, context=str(path))
        after_extraction = _current_rss_kb()
    elif method == "full_release":
        payload, field_count = _load_full(path)
        metric_fields = _extract_metric_fields(payload)
        extracted_field_count = len(metric_fields)
        normalized = sc.normalize_surface_code_step_metrics(
            metric_fields,
            context=str(path),
        )
        after_extraction = _current_rss_kb()
        del payload
        after_del = _current_rss_kb()
        gc_collected = int(gc.collect())
        after_release = _current_rss_kb()
    elif method == "metric_fields":
        metric_fields, field_count = sc._load_compile_info_metric_fields_from_json(path)
        extracted_field_count = len(metric_fields)
        normalized = sc.normalize_surface_code_step_metrics(
            metric_fields,
            context=str(path),
        )
        after_extraction = _current_rss_kb()
        extraction_mode = "top_level_metric_fields"
    else:
        raise ValueError(f"unknown method: {method}")

    elapsed = float(time.perf_counter() - started)
    sampler.stop()
    ru_maxrss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return {
        "path": str(path),
        "method": method,
        "extraction_mode": extraction_mode,
        "input_size_bytes": int(path.stat().st_size),
        "field_count": field_count,
        "extracted_field_count": extracted_field_count,
        "elapsed_seconds": elapsed,
        "current_rss_before_kb": before,
        "current_rss_after_extraction_kb": after_extraction,
        "current_rss_after_del_kb": after_del,
        "current_rss_after_release_kb": after_release,
        "current_rss_delta_after_extraction_kb": (
            None
            if before is None or after_extraction is None
            else int(after_extraction) - int(before)
        ),
        "current_rss_delta_after_release_kb": (
            None
            if before is None or after_release is None
            else int(after_release) - int(before)
        ),
        "rss_drop_after_del_kb": (
            None
            if after_extraction is None or after_del is None
            else int(after_extraction) - int(after_del)
        ),
        "rss_drop_after_gc_kb": (
            None
            if after_extraction is None or after_release is None
            else int(after_extraction) - int(after_release)
        ),
        "sampled_peak_rss_kb": sampler.peak_kb,
        "sample_count": int(sampler.sample_count),
        "ru_maxrss_kb": ru_maxrss,
        "gc_collected_count": gc_collected,
        "normalized_metrics": normalized,
        "normalized_metrics_hash": _metrics_hash(normalized),
    }


def _run_child(path: Path, method: str, interval: float) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--child",
        "--path",
        str(path),
        "--method",
        method,
        "--rss-sampling-interval",
        str(interval),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    started = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    process_elapsed = float(time.perf_counter() - started)
    if proc.returncode != 0:
        raise RuntimeError(
            f"child failed for {path} {method}: code={proc.returncode}\n{proc.stderr}"
        )
    payload = json.loads(proc.stdout)
    payload["child_process_elapsed_seconds"] = process_elapsed
    return payload


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{time.time_ns()}.tmp")
    try:
        tmp.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        tmp.replace(path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _add_comparisons(rows: list[dict[str, Any]]) -> None:
    by_path: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        by_path.setdefault(str(row["path"]), {})[str(row["method"])] = row
    for methods in by_path.values():
        baseline = methods.get("full")
        if baseline is None:
            continue
        baseline_metrics = baseline.get("normalized_metrics")
        baseline_hash = baseline.get("normalized_metrics_hash")
        for row in methods.values():
            row["normalized_metrics_equal_to_full"] = (
                row.get("normalized_metrics") == baseline_metrics
            )
            row["normalized_metrics_hash_equal_to_full"] = (
                row.get("normalized_metrics_hash") == baseline_hash
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", action="append", type=Path, required=True)
    parser.add_argument(
        "--method",
        action="append",
        choices=METHODS,
        default=[],
        help="Method to measure. Can be repeated. Default: all methods.",
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--rss-sampling-interval", type=float, default=0.005)
    parser.add_argument("--child", action="store_true")
    args = parser.parse_args()

    methods = args.method or list(METHODS)
    if args.child:
        if len(args.path) != 1 or len(methods) != 1:
            raise SystemExit("--child requires exactly one --path and one --method")
        payload = _measure_child(
            args.path[0],
            methods[0],
            float(args.rss_sampling_interval),
        )
        print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
        return 0

    rows: list[dict[str, Any]] = []
    for path in args.path:
        for method in methods:
            rows.append(_run_child(path, method, float(args.rss_sampling_interval)))
    _add_comparisons(rows)
    payload = {
        "rows": rows,
        "method_count": len(methods),
        "path_count": len(args.path),
        "required_fields": list(sc._SURFACE_CODE_STEP_METRIC_REQUIRED_FIELDS),
        "optional_fields": list(sc._SURFACE_CODE_STEP_METRIC_OPTIONAL_FIELDS),
        "passthrough_fields": list(sc._SURFACE_CODE_STEP_METRIC_PASSTHROUGH_FIELDS),
    }
    if args.output is not None:
        _write_json(args.output, payload)
    print(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
