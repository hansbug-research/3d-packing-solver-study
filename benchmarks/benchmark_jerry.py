from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_COMMIT = "75764a2b8a5c8e0a6713a4f672c0a8ff81b1107a"
sys.path.insert(0, str(ROOT / ".cache" / "jerry-3d-bin-packing"))

from py3dbp import Bin, Item, Packer  # noqa: E402

from validation import Box, cumulative_weight_above, f, validate_aabbs  # noqa: E402


def check_source() -> None:
    checkout = ROOT / ".cache" / "jerry-3d-bin-packing"
    actual = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    if actual != EXPECTED_COMMIT:
        raise SystemExit(f"Jerry checkout mismatch: expected {EXPECTED_COMMIT}, got {actual}")


def main():
    check_source()
    packer = Packer()
    packer.addBin(Bin("stack-bin", (2, 2, 6), 100, 0, 1))
    # A high loadbear value only changes sort priority in this library. It is
    # deliberately placed first to demonstrate that no max-weight-above check exists.
    packer.addItem(Item("fragile", "fragile", "cube", (2, 2, 2), 1, 1, 100, False, "red"))
    packer.addItem(Item("heavy-1", "heavy", "cube", (2, 2, 2), 10, 2, 0, False, "blue"))
    packer.addItem(Item("heavy-2", "heavy", "cube", (2, 2, 2), 10, 2, 0, False, "blue"))
    started = perf_counter()
    packer.pack(
        bigger_first=True,
        distribute_items=True,
        fix_point=True,
        check_stable=True,
        support_surface_ratio=1.0,
        number_of_decimals=0,
    )
    elapsed = perf_counter() - started
    container = packer.bins[0]
    placements = []
    for item in container.items:
        dx, dy, dz = map(f, item.getDimension())
        x, y, z = map(f, item.position)
        placements.append(Box(item.partno, container.partno, x, y, z, dx, dy, dz, f(item.weight)))
    errors = validate_aabbs(placements, {container.partno: (2, 2, 6)}, {container.partno: 100})
    fragile = next(p for p in placements if p.ref == "fragile")
    above = cumulative_weight_above(fragile, placements)
    print(json.dumps({
        "library": "jerry800416/3D-bin-packing",
        "commit": EXPECTED_COMMIT,
        "elapsed_s": elapsed,
        "packed": len(placements),
        "validation_errors": errors,
        "fragile_declared_loadbear": 100,
        "actual_weight_above_fragile": above,
        "loadbear_is_only_sort_key": above > 0,
        "placements": [p.__dict__ for p in placements],
    }, indent=2))


if __name__ == "__main__":
    main()
