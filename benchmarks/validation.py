from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from itertools import combinations


@dataclass(frozen=True)
class Box:
    ref: str
    bin_ref: str
    x: float
    y: float
    z: float
    dx: float
    dy: float
    dz: float
    weight: float = 0.0


def f(value: float | Decimal) -> float:
    return float(value)


def validate_aabbs(
    placements: list[Box],
    bin_sizes: dict[str, tuple[float, float, float]],
    bin_weight_limits: dict[str, float] | None = None,
    tolerance: float = 1e-7,
) -> list[str]:
    errors: list[str] = []
    for item in placements:
        if item.bin_ref not in bin_sizes:
            errors.append(f"{item.ref}: unknown bin {item.bin_ref}")
            continue
        bx, by, bz = bin_sizes[item.bin_ref]
        if min(item.x, item.y, item.z, item.dx, item.dy, item.dz) < -tolerance:
            errors.append(f"{item.ref}: negative coordinate or dimension")
        if item.x + item.dx > bx + tolerance:
            errors.append(f"{item.ref}: exceeds bin on x")
        if item.y + item.dy > by + tolerance:
            errors.append(f"{item.ref}: exceeds bin on y")
        if item.z + item.dz > bz + tolerance:
            errors.append(f"{item.ref}: exceeds bin on z")

    for left, right in combinations(placements, 2):
        if left.bin_ref != right.bin_ref:
            continue
        separated = (
            left.x + left.dx <= right.x + tolerance
            or right.x + right.dx <= left.x + tolerance
            or left.y + left.dy <= right.y + tolerance
            or right.y + right.dy <= left.y + tolerance
            or left.z + left.dz <= right.z + tolerance
            or right.z + right.dz <= left.z + tolerance
        )
        if not separated:
            errors.append(f"{left.ref} overlaps {right.ref}")

    if bin_weight_limits:
        for bin_ref, limit in bin_weight_limits.items():
            total = sum(p.weight for p in placements if p.bin_ref == bin_ref)
            if total > limit + tolerance:
                errors.append(f"{bin_ref}: weight {total} exceeds {limit}")
    return errors


def cumulative_weight_above(item: Box, placements: list[Box]) -> float:
    """Conservative check for a single vertical stack with overlapping footprints."""
    top = item.z + item.dz
    return sum(
        other.weight
        for other in placements
        if other.bin_ref == item.bin_ref
        and other.ref != item.ref
        and other.z >= top - 1e-7
        and other.x < item.x + item.dx
        and other.x + other.dx > item.x
        and other.y < item.y + item.dy
        and other.y + other.dy > item.y
    )
