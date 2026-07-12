#!/usr/bin/env python3
"""Summarize artifact disk usage and Git publication status."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class DirectoryUsage:
    name: str
    classification: str
    disk_bytes: int
    apparent_bytes: int
    file_count: int
    directory_count: int
    tracked_file_count: int
    tracked_bytes: int


def _git(repo_root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _repo_root(start: Path) -> Path:
    result = _git(start, "rev-parse", "--show-toplevel")
    return Path(result.stdout.decode().strip()).resolve()


def _tracked_files(repo_root: Path, artifact_root: Path) -> dict[str, list[Path]]:
    relative_root = artifact_root.relative_to(repo_root)
    result = _git(repo_root, "ls-files", "-z", "--", str(relative_root))
    by_directory: dict[str, list[Path]] = {}
    prefix_parts = len(relative_root.parts)

    for raw_path in result.stdout.split(b"\0"):
        if not raw_path:
            continue
        relative_path = Path(os.fsdecode(raw_path))
        if len(relative_path.parts) <= prefix_parts:
            continue
        directory_name = relative_path.parts[prefix_parts]
        by_directory.setdefault(directory_name, []).append(repo_root / relative_path)

    return by_directory


def _is_ignored(repo_root: Path, path: Path) -> bool:
    relative_path = path.relative_to(repo_root)
    result = _git(
        repo_root,
        "check-ignore",
        "-q",
        "--",
        str(relative_path),
        check=False,
    )
    return result.returncode == 0


def _allocated_bytes(stat_result: os.stat_result) -> int:
    blocks = getattr(stat_result, "st_blocks", None)
    return int(blocks * 512) if blocks is not None else int(stat_result.st_size)


def _walk_usage(root: Path) -> tuple[int, int, int, int]:
    disk_bytes = 0
    apparent_bytes = 0
    file_count = 0
    directory_count = 0
    pending = [root]

    while pending:
        current = pending.pop()
        try:
            with os.scandir(current) as iterator:
                for entry in iterator:
                    try:
                        stat_result = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    disk_bytes += _allocated_bytes(stat_result)
                    apparent_bytes += int(stat_result.st_size)
                    if entry.is_dir(follow_symlinks=False):
                        directory_count += 1
                        pending.append(Path(entry.path))
                    else:
                        file_count += 1
        except OSError:
            continue

    return disk_bytes, apparent_bytes, file_count, directory_count


def _file_size(path: Path) -> int:
    try:
        return int(path.lstat().st_size)
    except OSError:
        return 0


def collect_inventory(repo_root: Path, artifact_root: Path) -> list[DirectoryUsage]:
    tracked = _tracked_files(repo_root, artifact_root)
    inventory: list[DirectoryUsage] = []

    for path in sorted(artifact_root.iterdir(), key=lambda item: item.name):
        if not path.is_dir():
            continue
        tracked_paths = tracked.get(path.name, [])
        if tracked_paths:
            classification = "published"
        elif _is_ignored(repo_root, path):
            classification = "local"
        else:
            classification = "untracked"

        disk_bytes, apparent_bytes, file_count, directory_count = _walk_usage(path)
        inventory.append(
            DirectoryUsage(
                name=path.name,
                classification=classification,
                disk_bytes=disk_bytes,
                apparent_bytes=apparent_bytes,
                file_count=file_count,
                directory_count=directory_count,
                tracked_file_count=len(tracked_paths),
                tracked_bytes=sum(_file_size(item) for item in tracked_paths),
            )
        )

    return sorted(inventory, key=lambda item: item.disk_bytes, reverse=True)


def _human_size(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    size = float(value)
    for unit in units:
        if abs(size) < 1024.0 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    raise AssertionError("unreachable")


def _print_table(inventory: list[DirectoryUsage], limit: int | None) -> None:
    shown = inventory if limit is None else inventory[:limit]
    print(f"{'directory':<58} {'class':<10} {'disk':>10} {'files':>9} {'tracked':>8}")
    print("-" * 101)
    for item in shown:
        print(
            f"{item.name:<58} {item.classification:<10} "
            f"{_human_size(item.disk_bytes):>10} {item.file_count:>9,} "
            f"{item.tracked_file_count:>8,}"
        )

    if limit is not None and len(inventory) > limit:
        print(f"... {len(inventory) - limit} more directories; use --all to show them")

    counts = Counter(item.classification for item in inventory)
    print()
    print(f"Total disk usage:    {_human_size(sum(item.disk_bytes for item in inventory))}")
    print(f"Tracked file bytes:  {_human_size(sum(item.tracked_bytes for item in inventory))}")
    print(f"Files:               {sum(item.file_count for item in inventory):,}")
    print(
        "Directory classes:   "
        + ", ".join(f"{name}={count}" for name, count in sorted(counts.items()))
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("artifacts"),
        help="artifact directory relative to the repository root (default: artifacts)",
    )
    parser.add_argument("--all", action="store_true", help="show every directory")
    parser.add_argument("--top", type=int, default=20, help="number of rows to show")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    repo_root = _repo_root(Path.cwd())
    artifact_root = args.root
    if not artifact_root.is_absolute():
        artifact_root = repo_root / artifact_root
    artifact_root = artifact_root.resolve()
    artifact_root.relative_to(repo_root)

    if not artifact_root.is_dir():
        raise SystemExit(f"artifact directory does not exist: {artifact_root}")

    inventory = collect_inventory(repo_root, artifact_root)
    if args.json:
        payload = {
            "artifact_root": str(artifact_root.relative_to(repo_root)),
            "total_disk_bytes": sum(item.disk_bytes for item in inventory),
            "total_tracked_bytes": sum(item.tracked_bytes for item in inventory),
            "directories": [asdict(item) for item in inventory],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_table(inventory, None if args.all else max(args.top, 0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
