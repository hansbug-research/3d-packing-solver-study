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
    commit = subprocess.run(
        ["git", "-C", str(JERRY_ROOT), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if commit != JERRY_COMMIT:
        raise RuntimeError(f"Jerry checkout mismatch: expected {JERRY_COMMIT}, got {commit}")


def placements_py3dbp(payload: dict[str, Any], descending: bool) -> list[dict[str, Any]]:
    from py3dbp import Bin, Item, Packer

    bin_spec = payload["bins"][0]
    packer = Packer()
    packer.add_bin(Bin(bin_spec["id"], *bin_spec["size"], bin_spec["max_weight"]))
    for spec in payload["items"]:
        packer.add_item(Item(spec["id"], *spec["size"], spec["weight"]))
    packer.pack(bigger_first=descending, distribute_items=True, number_of_decimals=3)
    return [
        {
            "item_id": item.name,
            "bin_id": container.name,
            "position": [float(value) for value in item.position],
            "size": [float(value) for value in item.get_dimension()],
            "rotation": int(item.rotation_type),
        }
        for container in packer.bins
        for item in container.items
    ]


def placements_jerry(payload: dict[str, Any], descending: bool) -> list[dict[str, Any]]:
    from py3dbp import Bin, Item, Packer

    bin_spec = payload["bins"][0]
    packer = Packer()
    original_gravity = Packer.gravityCenter
    Packer.gravityCenter = lambda self, container: [] if not container.items else original_gravity(self, container)
    packer.addBin(Bin(bin_spec["id"], tuple(bin_spec["size"]), bin_spec["max_weight"], 0, 1))
    for spec in payload["items"]:
        packer.addItem(
            Item(
                spec["id"],
                spec["id"],
                "cube",
                tuple(spec["size"]),
                spec["weight"],
                1,
                0,
                True,
                "blue",
            )
        )
    packer.pack(
        bigger_first=descending,
        distribute_items=True,
        fix_point=True,
        check_stable=False,
        number_of_decimals=3,
    )
    return [
        {
            "item_id": item.partno,
            "bin_id": container.partno,
            "position": [float(value) for value in item.position],
            "size": [float(value) for value in item.getDimension()],
            "rotation": int(item.rotation_type),
        }
        for container in packer.bins
        for item in container.items
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Isolated py3dbp/Jerry B03 worker")
    parser.add_argument("--implementation", choices=("py3dbp", "jerry"), required=True)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()

    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES))
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if args.implementation == "py3dbp":
        version = importlib.metadata.version("py3dbp")
        if version != "1.1.2":
            raise RuntimeError(f"py3dbp version mismatch: expected 1.1.2, got {version}")
        solve = placements_py3dbp
    else:
        verify_jerry()
        sys.path.insert(0, str(JERRY_ROOT))
        version = JERRY_COMMIT
        solve = placements_jerry

    profits = {spec["id"]: spec["profit"] for spec in payload["items"]}
    started = perf_counter()
    candidates = []
    for order, descending in (("descending", True), ("ascending", False)):
        candidate_started = perf_counter()
        placements = solve(payload, descending)
        candidates.append(
            {
                "order": order,
                "placements": placements,
                "packed_profit": sum(profits[placement["item_id"]] for placement in placements),
                "elapsed_s": perf_counter() - candidate_started,
            }
        )
    output = {
        "library": args.implementation,
        "version": version,
        "algorithm": "pivot/fix-point greedy" if args.implementation == "jerry" else "pivot greedy",
        "pose_semantics": "RELAXED_ALL_ROTATIONS",
        "selection_policy": "runner validates both public ascending/descending item-order candidates before selecting profit",
        "candidates": candidates,
        "elapsed_s": perf_counter() - started,
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
