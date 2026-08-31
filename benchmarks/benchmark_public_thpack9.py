from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks"))

from validation import Box, validate_aabbs  # noqa: E402


DATA = ROOT / "benchmarks" / "data" / "public" / "thpack9_instance1.json"


def specs() -> tuple[dict, list[tuple[str, int, int, int, int]]]:
    case = json.loads(DATA.read_text())
    items = []
    for item_type in case["item_types"]:
        for copy in range(item_type["copies"]):
            items.append((f"{item_type['id']}-{copy}", *item_type["size"], 1))
    return case, items


def run_py3dbp(case: dict, items: list[tuple[str, int, int, int, int]]) -> dict:
    from py3dbp import Bin, Item, Packer

    size = case["container_types"][0]["size"]
    packer = Packer()
    for index in range(80):
        packer.add_bin(Bin(f"b{index}", *size, 100000))
    for item in items:
        packer.add_item(Item(item[0], *item[1:]))
    started = perf_counter()
    packer.pack(bigger_first=True, distribute_items=True, number_of_decimals=3)
    elapsed = perf_counter() - started
    placements = []
    sizes = {}
    limits = {}
    for container in packer.bins:
        sizes[container.name] = tuple(map(float, (container.width, container.height, container.depth)))
        limits[container.name] = float(container.max_weight)
        for index, item in enumerate(container.items):
            dx, dy, dz = map(float, item.get_dimension())
            x, y, z = map(float, item.position)
            placements.append(Box(f"{item.name}:{index}", container.name, x, y, z, dx, dy, dz, float(item.weight)))
    return {
        "library": "py3dbp",
        "packed": len(placements),
        "required": len(items),
        "unpacked": len(packer.items),
        "bins_used": sum(bool(container.items) for container in packer.bins),
        "elapsed_s": elapsed,
        "validation_errors": validate_aabbs(placements, sizes, limits),
    }


def run_jerry(case: dict, items: list[tuple[str, int, int, int, int]]) -> dict:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "benchmarks" / "benchmark_public_thpack9_jerry.py")],
        check=True, text=True, capture_output=True,
    )
    return json.loads(completed.stdout)


def main() -> None:
    case, items = specs()
    print(json.dumps({
        "dataset": "ESICUP THPACK9 instance 1",
        "source": case["source_url"],
        "container_size": case["container_types"][0]["size"],
        "required_items": len(items),
        "results": [run_py3dbp(case, items), run_jerry(case, items)],
    }, indent=2))


if __name__ == "__main__":
    main()
