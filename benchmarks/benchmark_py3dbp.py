from __future__ import annotations

import json
from time import perf_counter

from py3dbp import Bin, Item, Packer

from validation import Box, f, validate_aabbs


def solve(bin_specs, item_specs, *, bigger_first=True):
    packer = Packer()
    for spec in bin_specs:
        packer.add_bin(Bin(spec[0], *spec[1:]))
    for spec in item_specs:
        packer.add_item(Item(spec[0], *spec[1:]))
    started = perf_counter()
    packer.pack(bigger_first=bigger_first, distribute_items=True, number_of_decimals=3)
    elapsed = perf_counter() - started

    placements: list[Box] = []
    bin_sizes = {}
    limits = {}
    for container in packer.bins:
        bin_sizes[container.name] = tuple(map(f, (container.width, container.height, container.depth)))
        limits[container.name] = f(container.max_weight)
        for index, item in enumerate(container.items):
            dx, dy, dz = map(f, item.get_dimension())
            x, y, z = map(f, item.position)
            placements.append(Box(f"{item.name}:{index}", container.name, x, y, z, dx, dy, dz, f(item.weight)))
    errors = validate_aabbs(placements, bin_sizes, limits)
    return {
        "elapsed_s": elapsed,
        "packed": len(placements),
        "unpacked": len(packer.items),
        "bins_used": sum(bool(container.items) for container in packer.bins),
        "rotations": [int(item.rotation_type) for container in packer.bins for item in container.items],
        "validation_errors": errors,
    }


def main():
    scenarios = {
        "exact_grid": solve(
            [("B", 10, 10, 10, 100)],
            [(f"cube-{i}", 5, 5, 5, 1) for i in range(8)],
        ),
        "rotation_required": solve(
            [("B", 4, 3, 2, 100)],
            [("rotated", 3, 2, 4, 1)],
        ),
        "weight_limit": solve(
            [("B1", 10, 10, 10, 10), ("B2", 10, 10, 10, 10), ("B3", 10, 10, 10, 10)],
            [(f"heavy-{i}", 4, 4, 4, 6) for i in range(3)],
        ),
        "heterogeneous_order_small_first": solve(
            [("small-1", 6, 5, 5, 100), ("small-2", 6, 5, 5, 100), ("large", 12, 5, 5, 100)],
            [("cargo-1", 6, 5, 5, 1), ("cargo-2", 6, 5, 5, 1)],
            bigger_first=False,
        ),
        "heterogeneous_order_large_first": solve(
            [("small-1", 6, 5, 5, 100), ("small-2", 6, 5, 5, 100), ("large", 12, 5, 5, 100)],
            [("cargo-1", 6, 5, 5, 1), ("cargo-2", 6, 5, 5, 1)],
            bigger_first=True,
        ),
    }
    print(json.dumps({"library": "py3dbp", "version": "1.1.2", "scenarios": scenarios}, indent=2))


if __name__ == "__main__":
    main()
