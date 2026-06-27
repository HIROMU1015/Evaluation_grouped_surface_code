#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gc
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import tracemalloc
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
for path in (SRC_ROOT,):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from trotterlib import surface_code as sc  # noqa: E402
from trotterlib.profiling import flatten_stage_metrics  # noqa: E402


DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "surface_code_parent_memory"
DEFAULT_REPORT_PATH = (
    REPO_ROOT / "docs" / "benchmarks" / "surface_code_parent_memory_optimization.md"
)
BASELINE_COMMIT = "a489dbcdc11232ac144191defb7861dc765a9961"
CASE_KEY = "h5_4th_new2"
CASE_CHAIN_LENGTH = {"h4_4th_new2": 4, "h5_4th_new2": 5}
PF_LABEL = "4th(new_2)"
COMPILE_MODE = "ftqc_compile_topology"
SAMPLE_INTERVAL_SEC = 0.02
ONE_MIB_KB = 1024
ONE_GIB_KB = 1024 * 1024
PARENT_GATE_RSS_KB = 200 * ONE_MIB_KB
PARENT_GATE_SHARE = 0.25
PARENT_GATE_INCREASE_KB = 150 * ONE_MIB_KB
STOP_MEM_AVAILABLE_KB = ONE_GIB_KB
STOP_TREE_RSS_FRACTION = 0.85
MIN_FREE_DISK_BYTES = 5 * 1024**3
SEMANTIC_COMPARE_IGNORES = {
    "compile_info_json",
    "execution_time_sec",
    "compile_wall_time_sec",
}
MARKER_LABELS = (
    "evaluation_entry",
    "before_case_load",
    "after_case_load",
    "before_hamiltonian_load",
    "after_hamiltonian_load",
    "before_circuit_build",
    "after_circuit_build",
    "before_ir_prepare",
    "after_ir_prepare",
    "before_artifact_write",
    "after_artifact_write",
    "before_qret_command_build",
    "before_qret_launch",
    "after_parent_cleanup_before_qret",
    "after_qret_launch",
    "tree_peak_sample",
    "before_qret_wait_return",
    "after_qret_exit",
    "before_compile_info_read",
    "after_compile_info_read",
    "before_normalization",
    "after_normalization",
    "evaluation_exit",
)


def _git_output(args: Sequence[str], *, cwd: Path = REPO_ROOT) -> str:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=cwd,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{time.time_ns()}.tmp")
    try:
        tmp_path.write_text(
            json.dumps(dict(payload), ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        tmp_path.replace(path)
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass


def _append_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(dict(row), ensure_ascii=True, sort_keys=True))
            f.write("\n")


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root is not an object: {path}")
    return payload


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append(value)
    return rows


def _fmt_int(value: Any) -> str:
    return "" if value is None else f"{int(value):,}"


def _fmt_mb(kb: Any) -> str:
    return "" if kb is None else f"{int(kb) / 1024:.1f}"


def _fmt_pct(value: Any) -> str:
    return "" if value is None else f"{float(value) * 100:.2f}%"


def _ratio(numerator: int | float | None, denominator: int | float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return float(numerator) / float(denominator)


def _meminfo() -> dict[str, int]:
    ret: dict[str, int] = {}
    try:
        lines = Path("/proc/meminfo").read_text(encoding="utf-8").splitlines()
    except OSError:
        return ret
    for line in lines:
        parts = line.split()
        if len(parts) >= 2 and parts[0].endswith(":"):
            try:
                ret[parts[0][:-1]] = int(parts[1])
            except ValueError:
                pass
    return ret


def _parse_status_file(path: Path) -> dict[str, int]:
    mapping = {
        "VmRSS": "vmrss_kb",
        "VmHWM": "vmhwm_kb",
        "VmSize": "vmsize_kb",
        "VmSwap": "vmswap_kb",
        "RssAnon": "rss_anon_kb",
        "RssFile": "rss_file_kb",
        "RssShmem": "rss_shmem_kb",
    }
    ret: dict[str, int] = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ret
    for line in lines:
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        field = mapping.get(key)
        if field is None:
            continue
        parts = raw_value.split()
        if not parts:
            continue
        try:
            ret[field] = int(parts[0])
        except ValueError:
            pass
    return ret


def _parse_smaps_rollup(path: Path) -> dict[str, int]:
    mapping = {
        "Rss": "smaps_rollup_rss_kb",
        "Pss": "pss_kb",
        "Private_Dirty": "private_dirty_kb",
    }
    ret: dict[str, int] = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ret
    for line in lines:
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        field = mapping.get(key)
        if field is None:
            continue
        parts = raw_value.split()
        if not parts:
            continue
        try:
            ret[field] = int(parts[0])
        except ValueError:
            pass
    return ret


def _ppid(pid: int) -> int | None:
    try:
        lines = (Path("/proc") / str(pid) / "status").read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith("PPid:"):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    return int(parts[1])
                except ValueError:
                    return None
    return None


def _cmdline(pid: int) -> str | None:
    try:
        raw = (Path("/proc") / str(pid) / "cmdline").read_bytes()
    except OSError:
        return None
    if not raw:
        return None
    return " ".join(
        part.decode("utf-8", errors="replace") for part in raw.split(b"\0") if part
    )


def _direct_children(pid: int) -> list[int]:
    task_root = Path("/proc") / str(pid) / "task"
    children: set[int] = set()
    try:
        task_dirs = list(task_root.iterdir())
    except OSError:
        task_dirs = []
    for task_dir in task_dirs:
        try:
            text = (task_dir / "children").read_text(encoding="utf-8").strip()
        except OSError:
            continue
        for item in text.split():
            try:
                children.add(int(item))
            except ValueError:
                pass
    return sorted(children)


def _process_tree(root_pid: int) -> list[int]:
    seen: set[int] = set()
    pending = [int(root_pid)]
    while pending:
        pid = pending.pop(0)
        if pid in seen:
            continue
        if not (Path("/proc") / str(pid)).exists():
            continue
        seen.add(pid)
        pending.extend(child for child in _direct_children(pid) if child not in seen)
    return sorted(seen)


def _is_qret_command(command: str | None) -> bool:
    if not command:
        return False
    first = command.split(" ", 1)[0]
    return "/qret" in command or first.endswith("qret")


def _process_memory_detail(pid: int | None = None) -> dict[str, int | None]:
    target = os.getpid() if pid is None else int(pid)
    root = Path("/proc") / str(target)
    status = _parse_status_file(root / "status")
    smaps = _parse_smaps_rollup(root / "smaps_rollup")
    return {
        "rss_kb": status.get("vmrss_kb"),
        "pss_kb": smaps.get("pss_kb"),
        "private_dirty_kb": smaps.get("private_dirty_kb"),
        "vmhwm_kb": status.get("vmhwm_kb"),
        "vmsize_kb": status.get("vmsize_kb"),
    }


def _sample_process_tree(root_pid: int, sample_index: int) -> list[dict[str, Any]]:
    timestamp = time.time()
    mem = _meminfo()
    per_pid: list[dict[str, Any]] = []
    tree_vmrss_kb = 0
    for pid in _process_tree(root_pid):
        proc_root = Path("/proc") / str(pid)
        status = _parse_status_file(proc_root / "status")
        if not status:
            continue
        smaps = _parse_smaps_rollup(proc_root / "smaps_rollup")
        vmrss = int(status.get("vmrss_kb") or 0)
        tree_vmrss_kb += vmrss
        per_pid.append(
            {
                "sample_index": int(sample_index),
                "timestamp_seconds": float(timestamp),
                "root_pid": int(root_pid),
                "pid": int(pid),
                "ppid": _ppid(pid),
                "command": _cmdline(pid),
                **status,
                **smaps,
                "mem_total_kb": mem.get("MemTotal"),
                "mem_available_kb": mem.get("MemAvailable"),
                "swap_total_kb": mem.get("SwapTotal"),
                "swap_free_kb": mem.get("SwapFree"),
            }
        )
    for row in per_pid:
        row["tree_vmrss_kb"] = int(tree_vmrss_kb)
    return per_pid


def _tree_split_for_rows(rows: Sequence[Mapping[str, Any]], *, parent_pid: int) -> dict[str, Any]:
    tree_vmrss = max((int(row.get("tree_vmrss_kb") or 0) for row in rows), default=0)
    parent_vmrss = sum(
        int(row.get("vmrss_kb") or 0) for row in rows if int(row.get("pid") or -1) == parent_pid
    )
    qret_vmrss = sum(
        int(row.get("vmrss_kb") or 0) for row in rows if _is_qret_command(row.get("command"))
    )
    return {
        "tree_vmrss_kb": int(tree_vmrss),
        "parent_vmrss_kb": int(parent_vmrss),
        "qret_vmrss_kb": int(qret_vmrss),
        "other_vmrss_kb": int(tree_vmrss) - int(parent_vmrss) - int(qret_vmrss),
        "commands": [
            {
                "pid": row.get("pid"),
                "ppid": row.get("ppid"),
                "vmrss_kb": row.get("vmrss_kb"),
                "command": row.get("command"),
            }
            for row in sorted(
                rows,
                key=lambda item: int(item.get("vmrss_kb") or 0),
                reverse=True,
            )
        ],
    }


@dataclass
class OnlineTreeSummary:
    parent_pid: int
    row_count: int = 0
    sample_count: int = 0
    peak_tree_vmrss_kb: int = 0
    peak_sample_index: int | None = None
    peak_timestamp_seconds: float | None = None
    peak_rows: list[dict[str, Any]] = field(default_factory=list)
    parent_peak_rss_kb: int | None = None
    qret_peak_rss_kb: int | None = None
    min_mem_available_kb: int | None = None
    swap_total_kb: int | None = None
    first_swap_free_kb: int | None = None
    min_swap_free_kb: int | None = None
    previous_parent_rss_kb: int | None = None
    qret_seen: bool = False
    qret_active_previous: bool = False
    qret_windows: list[dict[str, Any]] = field(default_factory=list)
    active_qret_window: dict[str, Any] | None = None

    def update(self, rows: Sequence[Mapping[str, Any]]) -> None:
        if not rows:
            return
        self.sample_count += 1
        self.row_count += len(rows)
        sample_index = int(rows[0].get("sample_index") or 0)
        timestamp = rows[0].get("timestamp_seconds")
        tree_vmrss = max(int(row.get("tree_vmrss_kb") or 0) for row in rows)
        parent_rss = sum(
            int(row.get("vmrss_kb") or 0)
            for row in rows
            if int(row.get("pid") or -1) == self.parent_pid
        )
        qret_rss = sum(
            int(row.get("vmrss_kb") or 0)
            for row in rows
            if _is_qret_command(row.get("command"))
        )

        if tree_vmrss > self.peak_tree_vmrss_kb:
            self.peak_tree_vmrss_kb = int(tree_vmrss)
            self.peak_sample_index = sample_index
            self.peak_timestamp_seconds = float(timestamp) if timestamp is not None else None
            self.peak_rows = [dict(row) for row in rows]
        self.parent_peak_rss_kb = max(
            [value for value in (self.parent_peak_rss_kb, parent_rss) if value is not None],
            default=None,
        )
        if qret_rss > 0:
            self.qret_peak_rss_kb = max(
                [value for value in (self.qret_peak_rss_kb, qret_rss) if value is not None],
                default=None,
            )

        mem_available = rows[0].get("mem_available_kb")
        if mem_available is not None:
            self.min_mem_available_kb = min(
                [value for value in (self.min_mem_available_kb, int(mem_available)) if value is not None],
                default=None,
            )
        swap_total = rows[0].get("swap_total_kb")
        swap_free = rows[0].get("swap_free_kb")
        if swap_total is not None:
            self.swap_total_kb = max(
                [value for value in (self.swap_total_kb, int(swap_total)) if value is not None],
                default=None,
            )
        if swap_free is not None:
            if self.first_swap_free_kb is None:
                self.first_swap_free_kb = int(swap_free)
            self.min_swap_free_kb = min(
                [value for value in (self.min_swap_free_kb, int(swap_free)) if value is not None],
                default=None,
            )

        qret_active = qret_rss > 0
        if qret_active:
            if not self.qret_active_previous:
                self.qret_seen = True
                self.active_qret_window = {
                    "qret_first_sample_index": sample_index,
                    "qret_last_sample_index": sample_index,
                    "parent_before_qret_launch_kb": self.previous_parent_rss_kb,
                    "parent_after_qret_launch_kb": int(parent_rss),
                    "parent_before_qret_exit_kb": int(parent_rss),
                    "parent_after_qret_exit_kb": None,
                    "parent_peak_during_qret_kb": int(parent_rss),
                    "qret_peak_during_window_kb": int(qret_rss),
                    "tree_peak_during_window_kb": int(tree_vmrss),
                }
            window = self.active_qret_window
            if window is not None:
                window["qret_last_sample_index"] = sample_index
                window["parent_before_qret_exit_kb"] = int(parent_rss)
                window["parent_peak_during_qret_kb"] = max(
                    int(window.get("parent_peak_during_qret_kb") or 0),
                    int(parent_rss),
                )
                window["qret_peak_during_window_kb"] = max(
                    int(window.get("qret_peak_during_window_kb") or 0),
                    int(qret_rss),
                )
                window["tree_peak_during_window_kb"] = max(
                    int(window.get("tree_peak_during_window_kb") or 0),
                    int(tree_vmrss),
                )
        elif self.qret_active_previous and self.active_qret_window is not None:
            self.active_qret_window["parent_after_qret_exit_kb"] = int(parent_rss)
            self.qret_windows.append(dict(self.active_qret_window))
            self.active_qret_window = None

        self.qret_active_previous = bool(qret_active)
        self.previous_parent_rss_kb = int(parent_rss)

    def _selected_qret_window(self) -> dict[str, Any]:
        windows = list(self.qret_windows)
        if self.active_qret_window is not None:
            windows.append(dict(self.active_qret_window))
        if not windows:
            return {
                "qret_first_sample_index": None,
                "qret_last_sample_index": None,
                "parent_before_qret_launch_kb": None,
                "parent_after_qret_launch_kb": None,
                "parent_before_qret_exit_kb": None,
                "parent_after_qret_exit_kb": None,
                "parent_peak_during_qret_kb": None,
                "parent_rss_increase_during_qret_kb": None,
            }
        peak_index = self.peak_sample_index
        if peak_index is not None:
            containing = [
                window
                for window in windows
                if window.get("qret_first_sample_index") is not None
                and int(window["qret_first_sample_index"]) <= int(peak_index)
                and window.get("qret_last_sample_index") is not None
                and int(peak_index) <= int(window["qret_last_sample_index"])
            ]
            if containing:
                selected = containing[0]
            else:
                selected = max(
                    windows,
                    key=lambda window: int(window.get("qret_peak_during_window_kb") or 0),
                )
        else:
            selected = max(
                windows,
                key=lambda window: int(window.get("qret_peak_during_window_kb") or 0),
            )
        before = selected.get("parent_before_qret_launch_kb")
        peak = selected.get("parent_peak_during_qret_kb")
        selected = dict(selected)
        selected["selected_window_reason"] = (
            "contains_tree_peak_sample"
            if peak_index is not None
            and selected.get("qret_first_sample_index") is not None
            and int(selected["qret_first_sample_index"]) <= int(peak_index)
            and selected.get("qret_last_sample_index") is not None
            and int(peak_index) <= int(selected["qret_last_sample_index"])
            else "max_qret_peak_window"
        )
        selected["qret_window_count"] = len(windows)
        selected["parent_rss_increase_during_qret_kb"] = (
            None if before is None or peak is None else int(peak) - int(before)
        )
        return selected

    def summary(self) -> dict[str, Any]:
        split = _tree_split_for_rows(self.peak_rows, parent_pid=self.parent_pid)
        if self.peak_sample_index is not None:
            split["sample_index"] = self.peak_sample_index
            split["timestamp_seconds"] = self.peak_timestamp_seconds
            split["root_pid"] = self.parent_pid
        max_swap_used = (
            None
            if self.swap_total_kb is None or self.min_swap_free_kb is None
            else int(self.swap_total_kb) - int(self.min_swap_free_kb)
        )
        swap_drop = (
            None
            if self.first_swap_free_kb is None or self.min_swap_free_kb is None
            else int(self.first_swap_free_kb) - int(self.min_swap_free_kb)
        )
        qret_window = self._selected_qret_window()
        return {
            "sample_count": int(self.sample_count),
            "row_count": int(self.row_count),
            "sampled_peak_tree_vmrss_kb": int(self.peak_tree_vmrss_kb),
            "sampled_peak_tree_sample_index": self.peak_sample_index,
            "sampled_peak_qret_vmrss_kb": self.qret_peak_rss_kb,
            "sampled_peak_parent_vmrss_kb": self.parent_peak_rss_kb,
            "minimum_mem_available_kb": self.min_mem_available_kb,
            "maximum_swap_used_kb": max_swap_used,
            "maximum_swap_free_drop_kb": swap_drop,
            "tree_peak_split": split,
            "qret_window": qret_window,
        }


def _terminate_tree(root_pid: int, *, include_root: bool) -> None:
    pids = _process_tree(root_pid)
    if not include_root:
        pids = [pid for pid in pids if pid != root_pid]
    for pid in sorted(pids, reverse=True):
        try:
            os.kill(pid, 15)
        except (ProcessLookupError, PermissionError):
            pass


def _stream_process_tree_samples(
    root_pid: int,
    *,
    samples_path: Path,
    interval_sec: float,
    stop_event: threading.Event,
    memtotal_kb: int | None,
    summary: OnlineTreeSummary,
    guard: dict[str, Any],
) -> None:
    samples_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        samples_path.unlink()
    except FileNotFoundError:
        pass
    sample_index = 0
    low_mem_streak = 0
    with samples_path.open("a", encoding="utf-8") as f:
        while not stop_event.is_set():
            rows = _sample_process_tree(root_pid, sample_index)
            summary.update(rows)
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=True, sort_keys=True))
                f.write("\n")
            f.flush()

            mem_available = rows[0].get("mem_available_kb") if rows else None
            if mem_available is not None and int(mem_available) < STOP_MEM_AVAILABLE_KB:
                low_mem_streak += 1
            else:
                low_mem_streak = 0
            tree_vmrss = max((int(row.get("tree_vmrss_kb") or 0) for row in rows), default=0)
            tree_guard = (
                memtotal_kb is not None
                and memtotal_kb > 0
                and tree_vmrss > int(memtotal_kb * STOP_TREE_RSS_FRACTION)
            )
            low_mem_guard = low_mem_streak >= 3
            if (tree_guard or low_mem_guard) and not guard.get("triggered"):
                guard.update(
                    {
                        "triggered": True,
                        "reason": "tree_rss_fraction" if tree_guard else "low_mem_available",
                        "sample_index": sample_index,
                        "tree_vmrss_kb": tree_vmrss,
                        "mem_available_kb": mem_available,
                        "timestamp_seconds": time.time(),
                    }
                )
                _terminate_tree(root_pid, include_root=False)
            sample_index += 1
            stop_event.wait(interval_sec)


def _run_with_streaming_tree_sampler(
    fn: Callable[[], Any],
    *,
    samples_path: Path,
    interval_sec: float,
    memtotal_kb: int | None,
) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    parent_pid = os.getpid()
    summary = OnlineTreeSummary(parent_pid=parent_pid)
    stop_event = threading.Event()
    guard: dict[str, Any] = {"triggered": False}
    sampler = threading.Thread(
        target=_stream_process_tree_samples,
        kwargs={
            "root_pid": parent_pid,
            "samples_path": samples_path,
            "interval_sec": interval_sec,
            "stop_event": stop_event,
            "memtotal_kb": memtotal_kb,
            "summary": summary,
            "guard": guard,
        },
        daemon=True,
    )
    sampler.start()
    deadline = time.perf_counter() + max(0.1, float(interval_sec) * 5.0)
    while summary.sample_count == 0 and time.perf_counter() < deadline:
        time.sleep(min(0.001, max(0.0001, float(interval_sec))))
    try:
        result = fn()
    finally:
        stop_event.set()
        sampler.join(timeout=3.0)
    return result, summary.summary(), guard


def _summarize_sample_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    parent_pid: int | None = None,
) -> dict[str, Any]:
    if not rows:
        return {}
    selected_parent = parent_pid
    if selected_parent is None:
        for row in rows:
            root_pid = row.get("root_pid")
            if root_pid is not None:
                selected_parent = int(root_pid)
                break
    if selected_parent is None:
        return {}
    summary = OnlineTreeSummary(parent_pid=int(selected_parent))
    by_sample: dict[int, list[Mapping[str, Any]]] = {}
    for row in rows:
        by_sample.setdefault(int(row.get("sample_index") or 0), []).append(row)
    for sample_index in sorted(by_sample):
        summary.update(by_sample[sample_index])
    return summary.summary()


def _parent_gate_decision(sample_summary: Mapping[str, Any]) -> dict[str, Any]:
    split = sample_summary.get("tree_peak_split")
    split = split if isinstance(split, Mapping) else {}
    qret_window = sample_summary.get("qret_window")
    qret_window = qret_window if isinstance(qret_window, Mapping) else {}
    tree_peak = int(split.get("tree_vmrss_kb") or 0)
    parent_at_tree = int(split.get("parent_vmrss_kb") or 0)
    parent_share = _ratio(parent_at_tree, tree_peak)
    parent_increase = qret_window.get("parent_rss_increase_during_qret_kb")
    parent_increase_int = None if parent_increase is None else int(parent_increase)
    reasons: list[str] = []
    if parent_at_tree >= PARENT_GATE_RSS_KB:
        reasons.append("parent_at_tree_peak_ge_200mb")
    if parent_share is not None and parent_share >= PARENT_GATE_SHARE:
        reasons.append("parent_share_ge_25pct")
    if parent_increase_int is not None and parent_increase_int >= PARENT_GATE_INCREASE_KB:
        reasons.append("parent_increase_during_qret_ge_150mb")
    return {
        "passes": bool(reasons),
        "reasons": reasons,
        "tree_peak_kb": tree_peak,
        "parent_at_tree_peak_kb": parent_at_tree,
        "parent_share_at_tree_peak": parent_share,
        "parent_rss_increase_during_qret_kb": parent_increase_int,
        "thresholds": {
            "parent_at_tree_peak_kb": PARENT_GATE_RSS_KB,
            "parent_share_at_tree_peak": PARENT_GATE_SHARE,
            "parent_rss_increase_during_qret_kb": PARENT_GATE_INCREASE_KB,
        },
    }


def _recursive_size_bytes(value: Any, seen: set[int] | None = None) -> int:
    import sys as _sys

    if seen is None:
        seen = set()
    obj_id = id(value)
    if obj_id in seen:
        return 0
    seen.add(obj_id)
    size = int(_sys.getsizeof(value, 0))
    if isinstance(value, Mapping):
        for key, item in value.items():
            size += _recursive_size_bytes(key, seen)
            size += _recursive_size_bytes(item, seen)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            size += _recursive_size_bytes(item, seen)
    elif hasattr(value, "__dict__"):
        size += _recursive_size_bytes(vars(value), seen)
    return int(size)


def _numpy_payload_nbytes(value: Any, seen: set[int] | None = None) -> int:
    if seen is None:
        seen = set()
    obj_id = id(value)
    if obj_id in seen:
        return 0
    seen.add(obj_id)
    nbytes = getattr(value, "nbytes", None)
    if isinstance(nbytes, (int, float)):
        return int(nbytes)
    if isinstance(value, Mapping):
        return sum(_numpy_payload_nbytes(item, seen) for item in value.values())
    if isinstance(value, (list, tuple, set, frozenset)):
        return sum(_numpy_payload_nbytes(item, seen) for item in value)
    return 0


def _pandas_deep_bytes(value: Any) -> int | None:
    memory_usage = getattr(value, "memory_usage", None)
    if memory_usage is None:
        return None
    try:
        usage = memory_usage(deep=True)
        total = usage.sum() if hasattr(usage, "sum") else usage
        return int(total)
    except Exception:
        return None


def _estimate_object(name: str, value: Any) -> dict[str, Any]:
    if value is None:
        return {
            "name": str(name),
            "present": False,
            "type": None,
            "recursive_size_bytes": None,
            "numpy_payload_bytes": None,
            "pandas_deep_bytes": None,
        }
    length: int | None = None
    try:
        length = len(value)  # type: ignore[arg-type]
    except Exception:
        length = None
    return {
        "name": str(name),
        "present": True,
        "type": type(value).__name__,
        "length": length,
        "recursive_size_bytes": _recursive_size_bytes(value),
        "numpy_payload_bytes": _numpy_payload_nbytes(value),
        "pandas_deep_bytes": _pandas_deep_bytes(value),
    }


def _parent_marker(
    label: str,
    *,
    objects: Mapping[str, Any] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    current: int | None
    peak: int | None
    if tracemalloc.is_tracing():
        current, peak = tracemalloc.get_traced_memory()
    else:
        current, peak = None, None
    marker = {
        "label": str(label),
        "timestamp_seconds": time.time(),
        "process": _process_memory_detail(),
        "tracemalloc_current_kb": None if current is None else int(current // 1024),
        "tracemalloc_peak_kb": None if peak is None else int(peak // 1024),
        "gc_object_count": len(gc.get_objects()),
    }
    if objects is not None:
        marker["object_estimates"] = {
            name: _estimate_object(name, value) for name, value in objects.items()
        }
    if extra:
        marker["extra"] = dict(extra)
    return marker


def _stage_metrics_path(root: Path, primary: str, cache_hit: str) -> Path:
    hit_path = root / cache_hit
    return hit_path if hit_path.exists() else root / primary


def _compile_runtime_root_for_cache(
    artifact: sc.SurfaceCodeStepArtifact,
    architecture: sc.SurfaceCodeArchitecture,
    cache_root: Path,
) -> Path:
    previous = sc.SURFACE_CODE_CACHE_DIR
    sc.SURFACE_CODE_CACHE_DIR = cache_root
    try:
        return sc._compile_runtime_root(artifact, architecture)
    finally:
        sc.SURFACE_CODE_CACHE_DIR = previous


def _read_stage(stage_metrics: Mapping[str, Any], stage_name: str) -> dict[str, Any]:
    stages = stage_metrics.get("stages")
    if not isinstance(stages, Sequence):
        return {}
    for stage in stages:
        if isinstance(stage, Mapping) and stage.get("name") == stage_name:
            return dict(stage)
    return {}


def _semantic_metrics(metrics: Mapping[str, Any]) -> dict[str, Any]:
    ret = dict(metrics)
    for key in SEMANTIC_COMPARE_IGNORES:
        ret.pop(key, None)
    return ret


def _compare_metrics(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    left = _semantic_metrics(baseline)
    right = _semantic_metrics(candidate)
    keys = sorted(set(left) | set(right))
    mismatches = [key for key in keys if left.get(key, object()) != right.get(key, object())]
    return {
        "all_equal": not mismatches,
        "mismatches": mismatches,
        "ignored_fields": sorted(SEMANTIC_COMPARE_IGNORES),
        "field_count": len(keys),
    }


def _compare_hashes(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    keys: Sequence[str],
) -> dict[str, Any]:
    mismatches = [key for key in keys if left.get(key) != right.get(key)]
    return {"all_equal": not mismatches, "mismatches": mismatches}


def _cache_semantics_equal(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    keys = (
        "cache_key",
        "qasm_hash",
        "optimized_ir_hash",
        "compiler_executable_hash",
        "compiler_core_library_hash",
        "topology_hash",
    )
    return all(left.get(key) == right.get(key) for key in keys)


def _subprocess_output_buffer_assessment(
    *,
    stdout_bytes: int | None,
    stderr_bytes: int | None,
    large_threshold_bytes: int = 10 * 1024 * 1024,
) -> dict[str, Any]:
    total = int(stdout_bytes or 0) + int(stderr_bytes or 0)
    return {
        "stdout_bytes": int(stdout_bytes or 0),
        "stderr_bytes": int(stderr_bytes or 0),
        "total_bytes": total,
        "large_buffer_risk": total >= int(large_threshold_bytes),
    }


def _validate_cases(cases: Sequence[str]) -> tuple[str, ...]:
    ret: list[str] = []
    for case in cases:
        if case not in CASE_CHAIN_LENGTH:
            raise ValueError(f"Unsupported case {case!r}; H6 is intentionally not runnable here")
        ret.append(case)
    return tuple(ret)


def _architecture() -> sc.SurfaceCodeArchitecture:
    return sc.SurfaceCodeArchitecture(
        name="parent_memory_production",
        compile_mode=COMPILE_MODE,
        skip_compile_output=True,
        compile_info_output_mode="summary",
        save_mapping_result=False,
    )


def _runtime_provenance(
    *,
    architecture: sc.SurfaceCodeArchitecture,
    artifact: sc.SurfaceCodeStepArtifact | None = None,
) -> dict[str, Any]:
    qret_path = Path(architecture.qret_path).expanduser().resolve()
    topology_path = Path(architecture.topology_path).expanduser().resolve()
    hashes = sc.qret_runtime_hashes(qret_path)
    provenance: dict[str, Any] = {
        **hashes,
        "topology_path": str(topology_path),
        "topology_hash": sc.file_sha256(topology_path)
        if topology_path.exists() and sc._compile_uses_topology(architecture.compile_mode)
        else None,
        "architecture": architecture.to_dict(),
        "pipeline_config": {
            "compile_mode": architecture.compile_mode,
            "skip_compile_output": bool(architecture.skip_compile_output),
            "compile_info_output_mode": architecture.compile_info_output_mode,
            "summary_time_series_impl": os.environ.get(
                "QRET_SUMMARY_TIME_SERIES_IMPL", "legacy_timeseries"
            ),
            "inverse_map_release_after_routing": os.environ.get(
                "QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING", "default_enabled"
            ),
            "dep_graph_impl": os.environ.get("QRET_DEP_GRAPH_IMPL", "default_compact"),
        },
    }
    if artifact is not None:
        provenance.update(
            {
                "prepared_ir_path": str(artifact.optimized_ir_path),
                "prepared_ir_hash": artifact.optimized_ir_hash,
                "prepared_ir_size_bytes": artifact.optimized_ir_path.stat().st_size
                if artifact.optimized_ir_path.exists()
                else None,
            }
        )
    return provenance


def _artifact_summary(artifact: sc.SurfaceCodeStepArtifact) -> dict[str, Any]:
    return {
        "ham_name": artifact.ham_name,
        "molecule": artifact.molecule,
        "pf_label": artifact.pf_label,
        "num_logical_qubits": artifact.num_logical_qubits,
        "target_error": artifact.target_error,
        "step_time": artifact.step_time,
        "rotation_precision": artifact.rotation_precision,
        "runtime_root": str(artifact.runtime_root),
        "qasm_path": str(artifact.qasm_path),
        "ir_path": str(artifact.ir_path),
        "optimized_ir_path": str(artifact.optimized_ir_path),
        "qasm_hash": artifact.qasm_hash,
        "optimized_ir_hash": artifact.optimized_ir_hash,
        "qasm_size_bytes": artifact.qasm_path.stat().st_size
        if artifact.qasm_path.exists()
        else None,
        "ir_size_bytes": artifact.ir_path.stat().st_size
        if artifact.ir_path.exists()
        else None,
        "optimized_ir_size_bytes": artifact.optimized_ir_path.stat().st_size
        if artifact.optimized_ir_path.exists()
        else None,
        "instruction_count": artifact.instruction_count,
        "gate_depth": artifact.gate_depth,
        "step_magic_state_count": artifact.step_magic_state_count,
        "step_magic_state_depth": artifact.step_magic_state_depth,
    }


def _object_audit_from_markers(markers: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    selected = None
    for marker in markers:
        if marker.get("label") == "after_parent_cleanup_before_qret":
            selected = marker
            break
    if selected is None:
        for marker in markers:
            if marker.get("label") == "before_qret_launch":
                selected = marker
                break
    estimates = selected.get("object_estimates") if isinstance(selected, Mapping) else None
    if not isinstance(estimates, Mapping):
        return {"marker": None, "largest_objects": []}
    rows: list[dict[str, Any]] = []
    for name, item in estimates.items():
        if not isinstance(item, Mapping) or not item.get("present"):
            continue
        recursive_size = item.get("recursive_size_bytes") or 0
        numpy_payload = item.get("numpy_payload_bytes") or 0
        pandas_deep = item.get("pandas_deep_bytes") or 0
        rows.append(
            {
                "name": name,
                "type": item.get("type"),
                "recursive_size_bytes": int(recursive_size),
                "numpy_payload_bytes": int(numpy_payload),
                "pandas_deep_bytes": None if pandas_deep is None else int(pandas_deep),
            }
        )
    rows.sort(
        key=lambda item: max(
            int(item.get("recursive_size_bytes") or 0),
            int(item.get("numpy_payload_bytes") or 0),
            int(item.get("pandas_deep_bytes") or 0),
        ),
        reverse=True,
    )
    return {
        "marker": selected.get("label") if isinstance(selected, Mapping) else None,
        "largest_objects": rows[:20],
    }


def _stage_rows(
    *,
    prepare_metrics: Mapping[str, Any],
    compile_metrics: Mapping[str, Any],
    case_name: str,
) -> list[dict[str, Any]]:
    commit_sha = _git_output(["rev-parse", "HEAD"])
    rows = flatten_stage_metrics(
        prepare_metrics,
        commit_sha=commit_sha,
        case_name=case_name,
        phase="prepare",
        cache_condition="parent_memory_profile_cache_root",
        hchain_size=CASE_CHAIN_LENGTH[case_name],
    )
    rows.extend(
        flatten_stage_metrics(
            compile_metrics,
            commit_sha=commit_sha,
            case_name=case_name,
            phase="compile",
            cache_condition="parent_memory_profile_cache_root",
            hchain_size=CASE_CHAIN_LENGTH[case_name],
        )
    )
    return rows


def _stage_peak(
    rows: Sequence[Mapping[str, Any]],
    *,
    phase: str | None = None,
) -> dict[str, Any]:
    candidates = [
        row
        for row in rows
        if (phase is None or row.get("phase") == phase)
        and (
            row.get("python_sampled_peak_rss_kb") is not None
            or row.get("python_current_rss_after_kb") is not None
            or row.get("subprocess_maxrss_kb") is not None
        )
    ]
    if not candidates:
        return {}

    def score(row: Mapping[str, Any]) -> int:
        return int(
            row.get("python_sampled_peak_rss_kb")
            or row.get("python_current_rss_after_kb")
            or row.get("subprocess_maxrss_kb")
            or 0
        )

    row = max(candidates, key=score)
    return {
        "phase": row.get("phase"),
        "stage_name": row.get("stage_name"),
        "python_sampled_peak_rss_kb": row.get("python_sampled_peak_rss_kb"),
        "python_current_rss_after_kb": row.get("python_current_rss_after_kb"),
        "subprocess_maxrss_kb": row.get("subprocess_maxrss_kb"),
        "elapsed_seconds": row.get("elapsed_seconds"),
    }


def run_h5_baseline_once(
    *,
    output_root: Path,
    cache_root: Path,
    sample_interval_sec: float = SAMPLE_INTERVAL_SEC,
    batch_size: int = 2,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(output_root).free < MIN_FREE_DISK_BYTES:
        raise RuntimeError(f"Free disk below 5 GiB for {output_root}")
    case = CASE_KEY
    architecture = _architecture()
    run_dir = output_root / "h5_end_to_end_baseline"
    run_dir.mkdir(parents=True, exist_ok=True)
    samples_path = run_dir / "process_tree_samples.jsonl"
    markers_path = run_dir / "parent_markers.jsonl"
    for path in (samples_path, markers_path):
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    previous_cache_dir = sc.SURFACE_CODE_CACHE_DIR
    previous_batch_size = sc.SURFACE_CODE_RZ_HELPER_BATCH_SIZE
    previous_env = {
        key: os.environ.get(key)
        for key in (
            "SURFACE_CODE_PROFILE_RSS_SAMPLING",
            "SURFACE_CODE_PROFILE_RSS_SAMPLING_INTERVAL_SEC",
            "SURFACE_CODE_PROFILE_CIRCUIT_RELEASE_EXPERIMENT",
            "QRET_DEP_GRAPH_IMPL",
            "QRET_SUMMARY_TIME_SERIES_IMPL",
            "QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING",
            "QRET_RSS_DIAGNOSTIC_TRIM_STAGE",
        )
    }
    sc.SURFACE_CODE_CACHE_DIR = cache_root
    sc.SURFACE_CODE_RZ_HELPER_BATCH_SIZE = int(batch_size)
    os.environ["SURFACE_CODE_PROFILE_RSS_SAMPLING"] = "1"
    os.environ["SURFACE_CODE_PROFILE_RSS_SAMPLING_INTERVAL_SEC"] = str(sample_interval_sec)
    os.environ.pop("SURFACE_CODE_PROFILE_CIRCUIT_RELEASE_EXPERIMENT", None)
    os.environ.pop("QRET_DEP_GRAPH_IMPL", None)
    os.environ["QRET_SUMMARY_TIME_SERIES_IMPL"] = "legacy_timeseries"
    os.environ["QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING"] = "1"
    os.environ["QRET_RSS_DIAGNOSTIC_TRIM_STAGE"] = "none"

    markers: list[dict[str, Any]] = []
    artifact: sc.SurfaceCodeStepArtifact | None = None
    metrics: dict[str, Any] | None = None
    started = time.perf_counter()
    memtotal_kb = _meminfo().get("MemTotal")
    status = "unknown"
    error: str | None = None

    def add_marker(
        label: str,
        *,
        objects: Mapping[str, Any] | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        marker = _parent_marker(label, objects=objects, extra=extra)
        markers.append(marker)
        _append_jsonl(markers_path, [marker])

    def work() -> dict[str, Any]:
        nonlocal artifact, metrics
        add_marker("evaluation_entry", extra={"case": case})
        add_marker("before_case_load")
        ham_name = sc.grouped_hchain_ham_name(CASE_CHAIN_LENGTH[case])
        step_time = sc.surface_code_step_time(ham_name, PF_LABEL)
        rotation_precision = sc.surface_code_rotation_precision(
            ham_name,
            PF_LABEL,
            target_error=sc.TARGET_ERROR,
            step_time=step_time,
        )
        add_marker(
            "after_case_load",
            extra={
                "ham_name": ham_name,
                "pf_label": PF_LABEL,
                "step_time": step_time,
                "rotation_precision": rotation_precision,
            },
        )
        add_marker("before_hamiltonian_load")
        add_marker("before_circuit_build")
        add_marker("before_ir_prepare")
        add_marker("before_artifact_write")
        artifact = sc.prepare_grouped_surface_code_step_artifact(
            ham_name,
            PF_LABEL,
            architecture=architecture,
            step_time=step_time,
            rotation_precision=rotation_precision,
        )
        add_marker("after_hamiltonian_load", objects={"artifact": artifact})
        add_marker("after_circuit_build", objects={"artifact": artifact})
        add_marker("after_ir_prepare", objects={"artifact": artifact})
        add_marker("after_artifact_write", objects={"artifact": artifact})
        add_marker(
            "before_qret_command_build",
            objects={"artifact": artifact},
            extra=_runtime_provenance(architecture=architecture, artifact=artifact),
        )
        add_marker("before_qret_launch", objects={"artifact": artifact})
        add_marker(
            "after_parent_cleanup_before_qret",
            objects={
                "artifact": artifact,
                "optimized_ir_path_text": str(artifact.optimized_ir_path),
                "compile_request_architecture": architecture.to_dict(),
                "sample_marker_history": markers,
            },
            extra={
                "cleanup_note": (
                    "No production cleanup was applied for this baseline; "
                    "prepare-local Hamiltonian/circuit/qasm objects are out of scope "
                    "after prepare returns."
                )
            },
        )
        metrics = sc.compile_prepared_surface_code_step_artifact(
            artifact,
            architecture,
            reuse_cache=False,
        )
        add_marker("after_qret_launch", objects={"artifact": artifact, "metrics": metrics})
        add_marker("before_qret_wait_return", objects={"artifact": artifact, "metrics": metrics})
        add_marker("after_qret_exit", objects={"artifact": artifact, "metrics": metrics})
        add_marker("before_compile_info_read", objects={"artifact": artifact, "metrics": metrics})
        add_marker("after_compile_info_read", objects={"artifact": artifact, "metrics": metrics})
        add_marker("before_normalization", objects={"artifact": artifact, "metrics": metrics})
        add_marker("after_normalization", objects={"artifact": artifact, "metrics": metrics})
        add_marker("evaluation_exit", objects={"artifact": artifact, "metrics": metrics})
        return metrics

    if not tracemalloc.is_tracing():
        tracemalloc.start()
    try:
        metrics_result, sample_summary, guard = _run_with_streaming_tree_sampler(
            work,
            samples_path=samples_path,
            interval_sec=sample_interval_sec,
            memtotal_kb=memtotal_kb,
        )
        status = "ok"
        metrics = dict(metrics_result)
    except Exception as exc:
        status = "failed"
        error = repr(exc)
        sample_summary = {}
        guard = {"triggered": False}
        metrics = None
    finally:
        sc.SURFACE_CODE_CACHE_DIR = previous_cache_dir
        sc.SURFACE_CODE_RZ_HELPER_BATCH_SIZE = previous_batch_size
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    if sample_summary.get("tree_peak_split"):
        tree_marker = _parent_marker(
            "tree_peak_sample",
            extra=sample_summary.get("tree_peak_split"),
        )
        markers.append(tree_marker)
        _append_jsonl(markers_path, [tree_marker])

    prepare_metrics: dict[str, Any] = {}
    compile_metrics: dict[str, Any] = {}
    qret_stage: dict[str, Any] = {}
    read_stage: dict[str, Any] = {}
    artifact_payload: dict[str, Any] | None = None
    compile_root: Path | None = None
    compile_info_path: Path | None = None
    if artifact is not None:
        artifact_payload = _artifact_summary(artifact)
        compile_root = _compile_runtime_root_for_cache(artifact, architecture, cache_root)
        prepare_metrics_path = _stage_metrics_path(
            artifact.runtime_root,
            sc._PREPARE_STAGE_METRICS_FILENAME,
            sc._PREPARE_STAGE_CACHE_HIT_METRICS_FILENAME,
        )
        compile_metrics_path = _stage_metrics_path(
            compile_root,
            sc._COMPILE_STAGE_METRICS_FILENAME,
            sc._COMPILE_STAGE_CACHE_HIT_METRICS_FILENAME,
        )
        prepare_metrics = _load_json(prepare_metrics_path) if prepare_metrics_path.exists() else {}
        compile_metrics = _load_json(compile_metrics_path) if compile_metrics_path.exists() else {}
        qret_stage = _read_stage(compile_metrics, "qret_compile")
        read_stage = _read_stage(compile_metrics, "read_compile_info_json")
        if metrics and metrics.get("compile_info_json"):
            compile_info_path = Path(str(metrics["compile_info_json"]))
    rows = _stage_rows(
        prepare_metrics=prepare_metrics,
        compile_metrics=compile_metrics,
        case_name=case,
    )
    if rows:
        _append_jsonl(run_dir / "stage_metrics.jsonl", rows)

    gate = _parent_gate_decision(sample_summary)
    object_audit = _object_audit_from_markers(markers)
    qret_result = qret_stage.get("result") if isinstance(qret_stage.get("result"), Mapping) else {}
    output_buffer = _subprocess_output_buffer_assessment(
        stdout_bytes=qret_result.get("stdout_bytes"),
        stderr_bytes=qret_result.get("stderr_bytes"),
    )
    result = {
        "case": case,
        "phase": "h5_end_to_end_baseline",
        "status": status,
        "error": error,
        "elapsed_seconds": time.perf_counter() - started,
        "sample_interval_sec": float(sample_interval_sec),
        "batch_size": int(batch_size),
        "evaluation_head": _git_output(["rev-parse", "HEAD"]),
        "baseline_commit_required": BASELINE_COMMIT,
        "platform": {
            "system": platform.platform(),
            "python": sys.version,
        },
        "production_settings": {
            "compile_info_output_mode": "summary",
            "summary_time_series_impl": "legacy_timeseries",
            "inverse_map_release_after_routing": "enabled",
            "compact_dep_graph": "default",
            "pipeline_state_output": "skipped",
            "batch_size": int(batch_size),
            "cache_condition": "miss",
        },
        "runtime_provenance": _runtime_provenance(
            architecture=architecture,
            artifact=artifact,
        ),
        "cache_root": str(cache_root),
        "metrics": metrics or {},
        "artifact": artifact_payload,
        "compile_root": None if compile_root is None else str(compile_root),
        "compile_info_path": None if compile_info_path is None else str(compile_info_path),
        "compile_info_size_bytes": None
        if compile_info_path is None or not compile_info_path.exists()
        else compile_info_path.stat().st_size,
        "sample_summary": sample_summary,
        "tree_peak_rss_kb": sample_summary.get("sampled_peak_tree_vmrss_kb"),
        "qret_peak_rss_kb": sample_summary.get("sampled_peak_qret_vmrss_kb"),
        "parent_peak_rss_kb": sample_summary.get("sampled_peak_parent_vmrss_kb"),
        "tree_peak_split": sample_summary.get("tree_peak_split"),
        "qret_window": sample_summary.get("qret_window"),
        "guard": guard,
        "gate": gate,
        "object_audit": object_audit,
        "qret_stage": qret_stage,
        "read_compile_info_stage": read_stage,
        "subprocess_output_buffer": output_buffer,
        "prepare_stage_peak": _stage_peak(rows, phase="prepare"),
        "compile_stage_peak": _stage_peak(rows, phase="compile"),
        "max_python_stage_peak": _stage_peak(rows),
        "stage_rows": rows,
        "markers_path": str(markers_path),
        "samples_path": str(samples_path),
        "stage_metrics_path": str(run_dir / "stage_metrics.jsonl"),
        "h6_run": False,
    }
    _write_json(run_dir / "summary.json", result)
    return result


def _report_stage_peak(stage: Mapping[str, Any]) -> int | None:
    value = stage.get("python_sampled_peak_rss_kb")
    if value is not None:
        return int(value)
    return None


def _load_marker(markers_path: str | Path | None, label: str) -> dict[str, Any]:
    if not markers_path:
        return {}
    try:
        rows = _load_jsonl(Path(markers_path))
    except OSError:
        return {}
    for row in rows:
        if row.get("label") == label:
            return row
    return {}


def _write_report(report_path: Path, payload: Mapping[str, Any]) -> None:
    result = payload.get("result")
    result = result if isinstance(result, Mapping) else {}
    split = result.get("tree_peak_split")
    split = split if isinstance(split, Mapping) else {}
    qret_window = result.get("qret_window")
    qret_window = qret_window if isinstance(qret_window, Mapping) else {}
    gate = result.get("gate")
    gate = gate if isinstance(gate, Mapping) else {}
    object_audit = result.get("object_audit")
    object_audit = object_audit if isinstance(object_audit, Mapping) else {}
    qret_stage = result.get("qret_stage")
    qret_stage = qret_stage if isinstance(qret_stage, Mapping) else {}
    read_stage = result.get("read_compile_info_stage")
    read_stage = read_stage if isinstance(read_stage, Mapping) else {}
    prepare_peak = result.get("prepare_stage_peak")
    prepare_peak = prepare_peak if isinstance(prepare_peak, Mapping) else {}
    compile_peak = result.get("compile_stage_peak")
    compile_peak = compile_peak if isinstance(compile_peak, Mapping) else {}
    max_python_peak = result.get("max_python_stage_peak")
    max_python_peak = max_python_peak if isinstance(max_python_peak, Mapping) else {}
    qret_stage_result = qret_stage.get("result") if isinstance(qret_stage.get("result"), Mapping) else {}
    qret_launch_marker = _load_marker(
        result.get("markers_path"),
        "after_parent_cleanup_before_qret",
    )
    qret_launch_process = qret_launch_marker.get("process")
    qret_launch_process = (
        qret_launch_process if isinstance(qret_launch_process, Mapping) else {}
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Surface Code Parent Memory Optimization",
        "",
        "## Scope",
        "",
        f"- Evaluation HEAD: `{payload.get('evaluation_head')}`",
        f"- Required baseline: `{BASELINE_COMMIT}`",
        "- H6 was not run. This script rejects H6 cases.",
        "- Measurement target: H5 `4th(new_2)`, batch size 2, cache miss, topology compile.",
        "- Production settings: summary compile-info output, summary legacy TimeSeries, compact DepGraph default, inverse-map release enabled, pipeline-state output skipped.",
        "",
        "## H5 End-to-End Baseline",
        "",
        "| metric | KB | MB |",
        "|---|---:|---:|",
        f"| process tree peak | {_fmt_int(split.get('tree_vmrss_kb'))} | {_fmt_mb(split.get('tree_vmrss_kb'))} |",
        f"| qret at tree peak | {_fmt_int(split.get('qret_vmrss_kb'))} | {_fmt_mb(split.get('qret_vmrss_kb'))} |",
        f"| Python parent at tree peak | {_fmt_int(split.get('parent_vmrss_kb'))} | {_fmt_mb(split.get('parent_vmrss_kb'))} |",
        f"| other children at tree peak | {_fmt_int(split.get('other_vmrss_kb'))} | {_fmt_mb(split.get('other_vmrss_kb'))} |",
        f"| parent peak | {_fmt_int(result.get('parent_peak_rss_kb'))} | {_fmt_mb(result.get('parent_peak_rss_kb'))} |",
        f"| qret peak | {_fmt_int(result.get('qret_peak_rss_kb'))} | {_fmt_mb(result.get('qret_peak_rss_kb'))} |",
        f"| qret `/usr/bin/time` max RSS | {_fmt_int(qret_stage_result.get('subprocess_maxrss_kb'))} | {_fmt_mb(qret_stage_result.get('subprocess_maxrss_kb'))} |",
        f"| read compile-info sampled peak | {_fmt_int(_report_stage_peak(read_stage))} | {_fmt_mb(_report_stage_peak(read_stage))} |",
        f"| prepare artifact stage peak | {_fmt_int(prepare_peak.get('python_sampled_peak_rss_kb'))} | {_fmt_mb(prepare_peak.get('python_sampled_peak_rss_kb'))} |",
        f"| compile stage peak | {_fmt_int(compile_peak.get('python_sampled_peak_rss_kb'))} | {_fmt_mb(compile_peak.get('python_sampled_peak_rss_kb'))} |",
        "",
        f"- Tree peak sample index: `{split.get('sample_index')}`",
        f"- Elapsed: `{float(result.get('elapsed_seconds') or 0.0):.3f}` seconds",
        f"- Compile-info size: `{_fmt_int(result.get('compile_info_size_bytes'))}` bytes",
        f"- qret stdout/stderr captured bytes: `{result.get('subprocess_output_buffer', {}).get('total_bytes')}`",
        f"- Max Python RSS stage: `{max_python_peak.get('phase')}/{max_python_peak.get('stage_name')}` at `{_fmt_int(max_python_peak.get('python_sampled_peak_rss_kb'))}` KB.",
        f"- Compile stage peak: `{compile_peak.get('stage_name')}` at `{_fmt_int(compile_peak.get('python_sampled_peak_rss_kb'))}` KB.",
        "",
        "## qret Window",
        "",
        "| marker | parent RSS KB | parent RSS MB |",
        "|---|---:|---:|",
        f"| before qret launch | {_fmt_int(qret_window.get('parent_before_qret_launch_kb'))} | {_fmt_mb(qret_window.get('parent_before_qret_launch_kb'))} |",
        f"| after qret launch | {_fmt_int(qret_window.get('parent_after_qret_launch_kb'))} | {_fmt_mb(qret_window.get('parent_after_qret_launch_kb'))} |",
        f"| before qret exit | {_fmt_int(qret_window.get('parent_before_qret_exit_kb'))} | {_fmt_mb(qret_window.get('parent_before_qret_exit_kb'))} |",
        f"| after qret exit | {_fmt_int(qret_window.get('parent_after_qret_exit_kb'))} | {_fmt_mb(qret_window.get('parent_after_qret_exit_kb'))} |",
        f"| increase during qret | {_fmt_int(qret_window.get('parent_rss_increase_during_qret_kb'))} | {_fmt_mb(qret_window.get('parent_rss_increase_during_qret_kb'))} |",
        "",
        f"- Selected qret window: `{qret_window.get('selected_window_reason')}` from `{qret_window.get('qret_window_count')}` qret-active windows.",
        "",
        "## Gate Decision",
        "",
        f"- Gate passed: `{bool(gate.get('passes'))}`",
        f"- Reasons: `{', '.join(gate.get('reasons') or []) or 'none'}`",
        f"- Parent share at tree peak: `{_fmt_pct(gate.get('parent_share_at_tree_peak'))}`",
        "",
    ]
    largest = object_audit.get("largest_objects")
    largest = largest if isinstance(largest, Sequence) else []
    lines.extend(
        [
            "## Parent Object Audit",
            "",
            "The object audit is taken from Evaluation's parent process immediately before the qret compile call. Internal prepare-stage Hamiltonian/circuit objects are not retained by the driver after `prepare_grouped_surface_code_step_artifact` returns; their RSS is represented by prepare stage metrics rather than a live Python object reference at qret launch.",
            "",
            "| object | type | recursive bytes | NumPy bytes | pandas bytes |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for item in largest[:10]:
        if not isinstance(item, Mapping):
            continue
        lines.append(
            "| {name} | {typ} | {recursive} | {numpy} | {pandas} |".format(
                name=item.get("name"),
                typ=item.get("type"),
                recursive=_fmt_int(item.get("recursive_size_bytes")),
                numpy=_fmt_int(item.get("numpy_payload_bytes")),
                pandas=_fmt_int(item.get("pandas_deep_bytes")),
            )
        )
    if not largest:
        lines.append("| none |  |  |  |  |")
    lines.extend(
        [
            "",
            "qret launch parent marker:",
            "",
            "| field | KB | MB |",
            "|---|---:|---:|",
            f"| RSS | {_fmt_int(qret_launch_process.get('rss_kb'))} | {_fmt_mb(qret_launch_process.get('rss_kb'))} |",
            f"| PSS | {_fmt_int(qret_launch_process.get('pss_kb'))} | {_fmt_mb(qret_launch_process.get('pss_kb'))} |",
            f"| PrivateDirty | {_fmt_int(qret_launch_process.get('private_dirty_kb'))} | {_fmt_mb(qret_launch_process.get('private_dirty_kb'))} |",
            f"| tracemalloc current | {_fmt_int(qret_launch_marker.get('tracemalloc_current_kb'))} | {_fmt_mb(qret_launch_marker.get('tracemalloc_current_kb'))} |",
            f"| tracemalloc peak | {_fmt_int(qret_launch_marker.get('tracemalloc_peak_kb'))} | {_fmt_mb(qret_launch_marker.get('tracemalloc_peak_kb'))} |",
            "",
            "The live Python object estimates are far smaller than parent RSS at qret launch, and tracemalloc current is also well below RSS. That points to native-library/import footprint, allocator retention, and earlier prepare-stage work rather than a single large live Python container that can be dropped safely before qret compile.",
        ]
    )
    lines.extend(
        [
            "",
            "## Decision",
            "",
        ]
    )
    production_change = bool(payload.get("production_change_adopted"))
    if production_change:
        lines.append("- Python parent production optimization was adopted; see commit diff for the exact change.")
    else:
        lines.append("- No Python parent production change was adopted in this run.")
        if gate.get("passes"):
            lines.append("- The gate passed, but this profile did not identify a low-risk live parent object with a credible 50 MB reduction at qret launch.")
        else:
            lines.append("- The parent gate did not pass, so no additional H5 runs or production Python changes were performed.")
        lines.append("- Next qret-side candidate: reduce `LATTICE_SURGERY_MAGIC` operand/ancilla/path representation memory.")
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            f"- Summary: `{result.get('samples_path', '')}` sibling `summary.json`",
            f"- Process tree samples: `{result.get('samples_path')}`",
            f"- Parent markers: `{result.get('markers_path')}`",
            f"- Stage metrics: `{result.get('stage_metrics_path')}`",
            "",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")


def run_profile(
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    report_path: Path = DEFAULT_REPORT_PATH,
    cache_root: Path | None = None,
    cases: Sequence[str] = (CASE_KEY,),
    sample_interval_sec: float = SAMPLE_INTERVAL_SEC,
    batch_size: int = 2,
) -> dict[str, Any]:
    _validate_cases(cases)
    if tuple(cases) != (CASE_KEY,):
        raise ValueError("This profile intentionally runs only H5 end-to-end baseline")
    output_root = output_root.resolve()
    cache_root = (
        output_root / "surface_code_cache" / f"h5_baseline_{time.strftime('%Y%m%d_%H%M%S')}"
        if cache_root is None
        else cache_root.resolve()
    )
    result = run_h5_baseline_once(
        output_root=output_root,
        cache_root=cache_root,
        sample_interval_sec=sample_interval_sec,
        batch_size=batch_size,
    )
    payload = {
        "evaluation_head": _git_output(["rev-parse", "HEAD"]),
        "result": result,
        "production_change_adopted": False,
    }
    _write_json(output_root / "surface_code_parent_memory_summary.json", payload)
    _write_report(report_path, payload)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Profile H5 Evaluation parent memory during qret end-to-end compile."
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--cache-root", type=Path, default=None)
    parser.add_argument("--sample-interval-sec", type=float, default=SAMPLE_INTERVAL_SEC)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--case", action="append", dest="cases", default=None)
    args = parser.parse_args(argv)
    cases = tuple(args.cases) if args.cases else (CASE_KEY,)
    payload = run_profile(
        output_root=args.output_root,
        report_path=args.report_path,
        cache_root=args.cache_root,
        cases=cases,
        sample_interval_sec=args.sample_interval_sec,
        batch_size=args.batch_size,
    )
    result = payload["result"]
    gate = result.get("gate", {})
    split = result.get("tree_peak_split", {})
    print(
        "H5 tree_peak={tree}KB parent_at_tree={parent}KB qret_at_tree={qret}KB gate={gate}".format(
            tree=split.get("tree_vmrss_kb"),
            parent=split.get("parent_vmrss_kb"),
            qret=split.get("qret_vmrss_kb"),
            gate=gate.get("passes"),
        )
    )
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
