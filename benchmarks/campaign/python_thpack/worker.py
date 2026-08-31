from __future__ import annotations

import argparse
from dataclasses import replace
import importlib.metadata
import json
import resource
import subprocess
import sys
from pathlib import Path
from time import perf_counter

from model import ESICUP_COMMIT, JERRY_COMMIT, expanded_items, orientation_support, parse_all, validate_certificate


ROOT = Path(__file__).resolve().parents[3]
SOURCE_DIR = ROOT / ".cache" / "esicup-datasets" / "3d_rectangular" / "thpack"
MEMORY_LIMIT_BYTES = 2 * 1024 * 1024 * 1024


def check_checkout(path: Path, expected: str) -> None:
    actual = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
    if actual != expected:
        raise RuntimeError(f"checkout mismatch for {path}: expected {expected}, got {actual}")


def select_instance(key: str):
    matches = [instance for instance in parse_all(SOURCE_DIR) if instance.key == key]
    if len(matches) != 1:
        raise RuntimeError(f"instance key resolved to {len(matches)} records: {key}")
    return matches[0]


def run_py3dbp(instance, order: str) -> dict:
    import py3dbp
    from py3dbp import Bin, Item, Packer

    version = importlib.metadata.version("py3dbp")
    if version != "1.1.2":
        raise RuntimeError(f"py3dbp version mismatch: expected 1.1.2, got {version}")
    items = expanded_items(instance)
    packer = Packer()
    bin_count = 1 if instance.problem_kind == "single_container_knapsack" else len(items)
    for bin_index in range(bin_count):
        packer.add_bin(Bin(f"bin:{bin_index}", *instance.container, len(items) + 1))
    for item in items:
        packer.add_item(Item(item["item_id"], *item["size"], 1))
    started = perf_counter()
    packer.pack(bigger_first=order == "descending", distribute_items=True, number_of_decimals=3)
    solve_seconds = perf_counter() - started
    placements: list[dict] = []
    for container in packer.bins:
        for placed in container.items:
            dx, dy, dz = map(float, placed.get_dimension())
            x, y, z = map(float, placed.position)
            placements.append(
                {
                    "item_id": placed.name,
                    "bin_id": container.name,
                    "x": x,
                    "y": y,
                    "z": z,
                    "dx": dx,
                    "dy": dy,
                    "dz": dz,
                    "rotation": int(placed.rotation_type),
                }
            )
    return {
        "library": "py3dbp",
        "version": version,
        "source": "PyPI wheel",
        "parameters": {"bigger_first": order == "descending", "distribute_items": True, "number_of_decimals": 3},
        "solve_seconds": solve_seconds,
        "placements": placements,
    }


def run_jerry(instance, order: str, fix_point: bool = True, projection: bool = False) -> dict:
    checkout = ROOT / ".cache" / "jerry-3d-bin-packing"
    check_checkout(checkout, JERRY_COMMIT)
    sys.path.insert(0, str(checkout))
    from py3dbp import Bin, Item, Packer

    items = expanded_items(instance)
    item_specs = {item["item_id"]: item for item in items}
    packer = Packer()
    original_gravity = Packer.gravityCenter
    Packer.gravityCenter = lambda self, container: [] if not container.items else original_gravity(self, container)
    bin_count = 1 if instance.problem_kind == "single_container_knapsack" else len(items)
    for bin_index in range(bin_count):
        packer.addBin(Bin(f"bin:{bin_index}", tuple(instance.container), len(items) + 1, 0, 1))
    for item in items:
        flags = (1, 1, 1) if projection else tuple(item["allowed_vertical_dimensions"])
        packer.addItem(
            Item(
                item["item_id"],
                item["item_id"],
                "cube",
                tuple(item["size"]),
                1,
                1,
                0,
                flags == (1, 1, 1),
                "blue",
            )
        )
    started = perf_counter()
    packer.pack(
        bigger_first=order == "descending",
        distribute_items=True,
        fix_point=fix_point,
        check_stable=False,
        number_of_decimals=3,
    )
    solve_seconds = perf_counter() - started
    placements: list[dict] = []
    for container in packer.bins:
        for placed in container.items:
            dx, dy, dz = map(float, placed.getDimension())
            x, y, z = map(float, placed.position)
            item_id = placed.partno
            if item_id not in item_specs:
                raise RuntimeError(f"Jerry returned unknown item id: {item_id}")
            placements.append(
                {
                    "item_id": item_id,
                    "bin_id": container.partno,
                    "x": x,
                    "y": y,
                    "z": z,
                    "dx": dx,
                    "dy": dy,
                    "dz": dz,
                    "rotation": int(placed.rotation_type),
                }
            )
    return {
        "library": "jerry",
        "version": JERRY_COMMIT,
        "source": "pinned Git checkout",
        "parameters": {
            "bigger_first": order == "descending",
            "distribute_items": True,
            "fix_point": fix_point,
            "check_stable": False,
            "number_of_decimals": 3,
        },
        "solve_seconds": solve_seconds,
        "placements": placements,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", choices=("py3dbp", "jerry"), required=True)
    parser.add_argument("--instance", required=True)
    parser.add_argument("--order", choices=("descending", "ascending"), required=True)
    parser.add_argument("--jerry-fix-point", choices=("true", "false"), default="true")
    parser.add_argument("--projection", action="store_true", help="ignore source vertical flags for an explicit all-rotations projection")
    args = parser.parse_args()

    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES))
    check_checkout(ROOT / ".cache" / "esicup-datasets", ESICUP_COMMIT)
    instance = select_instance(args.instance)
    supported, reason = orientation_support(instance, args.library)
    if args.projection:
        reason = "explicit GEOMETRY_PROJECTION: source vertical flags are not enforced; all six axis permutations are allowed"
        supported = True
    if not supported:
        raise RuntimeError(f"worker was called for unsupported instance: {reason}")

    result = (
        run_py3dbp(instance, args.order)
        if args.library == "py3dbp"
        else run_jerry(instance, args.order, fix_point=args.jerry_fix_point == "true", projection=args.projection)
    )
    placements = result["placements"]
    require_complete = instance.problem_kind == "multi_container_bin_packing"
    validation_instance = instance
    if args.projection:
        validation_instance = replace(
            instance,
            item_types=[replace(item, allowed_vertical_dimensions=(1, 1, 1)) for item in instance.item_types],
        )
    validation_errors = validate_certificate(validation_instance, placements, require_complete=require_complete)
    packed_volume = sum(int(round(p["dx"] * p["dy"] * p["dz"])) for p in placements)
    bins_used = len({placement["bin_id"] for placement in placements})
    if validation_errors:
        status = "INVALID"
    elif require_complete and len(placements) != instance.item_count:
        status = "INCOMPLETE"
    elif len(placements) == instance.item_count:
        status = "FEASIBLE_COMPLETE"
    else:
        status = "FEASIBLE_PARTIAL"
    result.update(
        {
            "status": status,
            "instance": instance.to_dict(),
            "order": args.order,
            "orientation_support_reason": reason,
            "packed_items": len(placements),
            "unpacked_items": instance.item_count - len(placements),
            "packed_volume": packed_volume,
            "volume_utilization": packed_volume / instance.container_volume,
            "bins_used": bins_used,
            "validation_errors": validation_errors,
            "validator": "python_thpack.model.validate_certificate",
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        }
    )
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
