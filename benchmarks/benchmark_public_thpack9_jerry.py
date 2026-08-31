from __future__ import annotations

import json
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".cache" / "jerry-3d-bin-packing"))
sys.path.insert(0, str(ROOT / "benchmarks"))

from py3dbp import Bin, Item, Packer  # noqa: E402
from validation import Box, validate_aabbs  # noqa: E402


def main() -> None:
    case = json.loads((ROOT / "benchmarks" / "data" / "public" / "thpack9_instance1.json").read_text())
    original_gravity = Packer.gravityCenter
    Packer.gravityCenter = lambda self, container: [] if not container.items else original_gravity(self, container)
    size = case["container_types"][0]["size"]
    items = []
    for item_type in case["item_types"]:
        for copy in range(item_type["copies"]):
            items.append((f"{item_type['id']}-{copy}", *item_type["size"], 1))
    packer = Packer()
    for index in range(80):
        packer.addBin(Bin(f"b{index}", tuple(size), 100000, 0, 1))
    for item in items:
        packer.addItem(Item(item[0], item[0], "cube", tuple(item[1:4]), item[4], 1, 0, True, "blue"))
    started = perf_counter()
    packer.pack(bigger_first=True, distribute_items=True, fix_point=True, check_stable=False, number_of_decimals=3)
    placements = []
    sizes = {}
    limits = {}
    for container in packer.bins:
        sizes[container.partno] = tuple(map(float, (container.width, container.height, container.depth)))
        limits[container.partno] = float(container.max_weight)
        for index, item in enumerate(container.items):
            dx, dy, dz = map(float, item.getDimension())
            x, y, z = map(float, item.position)
            placements.append(Box(f"{item.partno}:{index}", container.partno, x, y, z, dx, dy, dz, float(item.weight)))
    print(json.dumps({
        "library": "jerry800416/3D-bin-packing",
        "commit": "75764a2b8a5c8e0a6713a4f672c0a8ff81b1107a",
        "version": "source checkout at pinned commit",
        "parameters": {"bigger_first": True, "distribute_items": True, "fix_point": True, "check_stable": False, "number_of_decimals": 3},
        "validator": "benchmarks.validation.validate_aabbs",
        "packed": len(placements), "required": len(items), "unpacked": len(packer.unfit_items),
        "bins_used": sum(bool(container.items) for container in packer.bins),
        "elapsed_s": perf_counter() - started,
        "validation_errors": validate_aabbs(placements, sizes, limits),
    }))


if __name__ == "__main__":
    main()
