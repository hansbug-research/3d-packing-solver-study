#!/usr/bin/env python3
"""Isolated py3dbp/Jerry worker for the MPV generator-derived projection."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import resource
import subprocess
import sys
from pathlib import Path
from time import perf_counter
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
JERRY_ROOT = ROOT / ".cache" / "jerry-3d-bin-packing"
JERRY_COMMIT = "75764a2b8a5c8e0a6713a4f672c0a8ff81b1107a"
MEMORY_LIMIT_BYTES = 1024 * 1024 * 1024


def verify_jerry() -> None:
    actual = subprocess.check_output(["git", "-C", str(JERRY_ROOT), "rev-parse", "HEAD"], text=True).strip()
    if actual != JERRY_COMMIT:
        raise RuntimeError(f"Jerry checkout mismatch: expected {JERRY_COMMIT}, got {actual}")


def solve_py3dbp(payload: dict[str, Any], descending: bool) -> list[dict[str, Any]]:
    from py3dbp import Bin, Item, Packer

    packer = Packer()
    for spec in payload["bins"]:
        packer.add_bin(Bin(spec["id"], *spec["size"], spec["max_weight"]))
    for spec in payload["items"]:
        packer.add_item(Item(spec["id"], *spec["size"], spec["weight"]))
    packer.pack(bigger_first=descending, distribute_items=True, number_of_decimals=3)
    return [
        {
            "item_id": item.name,
            "bin_id": container.name,
            "position": [float(value) for value in item.position],
            "size": [float(value) for value in item.get_dimension()],
        }
        for container in packer.bins
        for item in container.items
    ]


def solve_jerry(payload: dict[str, Any], descending: bool) -> list[dict[str, Any]]:
    from py3dbp import Bin, Item, Packer

    packer = Packer()
    original_gravity = Packer.gravityCenter
    Packer.gravityCenter = lambda self, container: [] if not container.items else original_gravity(self, container)
    try:
        for spec in payload["bins"]:
            packer.addBin(Bin(spec["id"], tuple(spec["size"]), spec["max_weight"], 0, 1))
        for spec in payload["items"]:
            packer.addItem(Item(spec["id"], spec["id"], "cube", tuple(spec["size"]), spec["weight"], 1, 0, True, "blue"))
        packer.pack(bigger_first=descending, distribute_items=True, fix_point=False, check_stable=False, number_of_decimals=3)
        return [
            {
                "item_id": item.partno,
                "bin_id": container.partno,
                "position": [float(value) for value in item.position],
                "size": [float(value) for value in item.getDimension()],
            }
            for container in packer.bins
            for item in container.items
        ]
    finally:
        Packer.gravityCenter = original_gravity


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--implementation", choices=("py3dbp", "jerry"), required=True)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES))
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if args.implementation == "py3dbp":
        version = importlib.metadata.version("py3dbp")
        if version != "1.1.2":
            raise RuntimeError(f"py3dbp version mismatch: expected 1.1.2, got {version}")
        solve = solve_py3dbp
    else:
        verify_jerry()
        sys.path.insert(0, str(JERRY_ROOT))
        version = JERRY_COMMIT
        solve = solve_jerry
    started = perf_counter()
    candidates = []
    for order, descending in (("DESCENDING", True), ("ASCENDING", False)):
        candidate_started = perf_counter()
        candidates.append({"item_order": order, "placements": solve(payload, descending), "solver_s": perf_counter() - candidate_started})
    print(json.dumps({
        "library": args.implementation,
        "version": version,
        "algorithm": "pivot greedy" if args.implementation == "py3dbp" else "Jerry pivot/fix-point greedy",
        "pose_semantics": "RELAXED_ALL_ROTATIONS",
        "candidates": candidates,
        "elapsed_s": perf_counter() - started,
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
    }, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
