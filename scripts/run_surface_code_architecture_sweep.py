#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from trotterlib.architecture_sweep import run_surface_code_architecture_sweep


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run single-step grouped H-chain surface-code architecture sweep."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to surface-code architecture sweep YAML.",
    )
    args = parser.parse_args()

    summary = run_surface_code_architecture_sweep(args.config)
    print(f"jsonl: {summary['jsonl_path']}")
    print(f"csv: {summary['csv_path']}")
    print(
        "cases: "
        f"success={summary['success_count']} "
        f"failed={summary['failed_count']} "
        f"skipped={summary['skipped_count']}"
    )
    return 0 if summary["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
