from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from itertools import combinations, permutations
from pathlib import Path


ESICUP_COMMIT = "154a8f006a8e72f65d734f2d1e36777f678f31f8"
JERRY_COMMIT = "75764a2b8a5c8e0a6713a4f672c0a8ff81b1107a"


@dataclass(frozen=True)
class ItemType:
    type_id: str
    size: tuple[int, int, int]
    allowed_vertical_dimensions: tuple[int, int, int]
    copies: int


@dataclass
class Instance:
    family: str
    instance_id: int
    problem_kind: str
    objective: str
    container: tuple[int, int, int]
    item_types: list[ItemType] = field(default_factory=list)
    seed: int | None = None
    source_line_errors: list[dict] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.family}-{self.instance_id:03d}"

    @property
    def item_count(self) -> int:
        return sum(item.copies for item in self.item_types)

    @property
    def item_volume(self) -> int:
        return sum(item.size[0] * item.size[1] * item.size[2] * item.copies for item in self.item_types)

    @property
    def container_volume(self) -> int:
        return self.container[0] * self.container[1] * self.container[2]

    def to_dict(self) -> dict:
        value = asdict(self)
        value.update(
            key=self.key,
            item_count=self.item_count,
            item_volume=self.item_volume,
            container_volume=self.container_volume,
        )
        return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_family(path: Path, family_number: int) -> list[Instance]:
    lines = [(line_number, line.strip()) for line_number, line in enumerate(path.read_text().splitlines(), 1) if line.strip()]
    expected = int(lines[0][1])
    cursor = 1
    instances: list[Instance] = []
    for _ in range(expected):
        header_line, header_text = lines[cursor]
        cursor += 1
        header = [int(value) for value in header_text.split()]
        if family_number <= 7:
            if len(header) != 2:
                raise ValueError(f"{path}:{header_line}: expected instance id and seed")
            instance_id, seed = header
        else:
            if len(header) != 1:
                raise ValueError(f"{path}:{header_line}: expected instance id")
            instance_id, seed = header[0], None

        container_line, container_text = lines[cursor]
        cursor += 1
        container_values = [int(value) for value in container_text.split()]
        if len(container_values) != 3:
            raise ValueError(f"{path}:{container_line}: expected three container dimensions")

        type_count_line, type_count_text = lines[cursor]
        cursor += 1
        type_count_values = type_count_text.split()
        if len(type_count_values) != 1:
            raise ValueError(f"{path}:{type_count_line}: expected item type count")
        type_count = int(type_count_values[0])
        instance = Instance(
            family=f"THPACK{family_number}",
            instance_id=instance_id,
            seed=seed,
            problem_kind="single_container_knapsack" if family_number <= 8 else "multi_container_bin_packing",
            objective="maximize_packed_volume" if family_number <= 8 else "minimize_bins_complete",
            container=tuple(container_values),
        )
        for _type_index in range(type_count):
            line_number, item_text = lines[cursor]
            cursor += 1
            values = [int(value) for value in item_text.split()]
            if len(values) != 8:
                instance.source_line_errors.append(
                    {
                        "line": line_number,
                        "field_count": len(values),
                        "raw": item_text,
                        "expected": "ID L vertical_L W vertical_W H vertical_H copies",
                    }
                )
                continue
            type_id, length, vertical_length, width, vertical_width, height, vertical_height, copies = values
            flags = (vertical_length, vertical_width, vertical_height)
            if any(flag not in (0, 1) for flag in flags) or copies < 0 or min(length, width, height) <= 0:
                instance.source_line_errors.append(
                    {"line": line_number, "field_count": len(values), "raw": item_text, "expected": "positive dimensions/copies and 0/1 flags"}
                )
                continue
            instance.item_types.append(ItemType(str(type_id), (length, width, height), flags, copies))
        instances.append(instance)

    if cursor != len(lines):
        raise ValueError(f"{path}: parser left {len(lines) - cursor} non-empty lines")
    if len(instances) != expected:
        raise ValueError(f"{path}: expected {expected} instances, parsed {len(instances)}")
    return instances


def parse_all(source_dir: Path) -> list[Instance]:
    instances: list[Instance] = []
    for family_number in range(1, 10):
        instances.extend(parse_family(source_dir / f"thpack{family_number}.txt", family_number))
    return instances


def orientation_support(instance: Instance, library: str) -> tuple[bool, str]:
    if instance.source_line_errors:
        return False, "source record is malformed; missing fields are not inferred"
    patterns = {item.allowed_vertical_dimensions for item in instance.item_types}
    if library == "py3dbp":
        unsupported = patterns - {(1, 1, 1)}
        if unsupported:
            return False, f"py3dbp exposes all six axis permutations only; unsupported vertical-flag patterns: {sorted(unsupported)}"
        return True, "all item dimensions may be vertical; py3dbp's six permutations are exact for this instance"
    if library == "jerry":
        unsupported = patterns - {(1, 1, 1), (0, 0, 1)}
        if unsupported:
            return False, f"Jerry exposes only all-six or height-preserving two-rotation modes; unsupported patterns: {sorted(unsupported)}"
        return True, "each item maps exactly to Jerry updown=true (six) or updown=false (height-preserving two)"
    raise ValueError(f"unknown library: {library}")


def expanded_items(instance: Instance) -> list[dict]:
    items: list[dict] = []
    for item_type in instance.item_types:
        for copy_index in range(item_type.copies):
            items.append(
                {
                    "item_id": f"{item_type.type_id}:{copy_index}",
                    "type_id": item_type.type_id,
                    "size": item_type.size,
                    "allowed_vertical_dimensions": item_type.allowed_vertical_dimensions,
                }
            )
    return items


def allowed_oriented_sizes(size: tuple[int, int, int], vertical_flags: tuple[int, int, int]) -> set[tuple[int, int, int]]:
    allowed: set[tuple[int, int, int]] = set()
    for order in permutations(range(3)):
        if vertical_flags[order[2]]:
            allowed.add((size[order[0]], size[order[1]], size[order[2]]))
    return allowed


def validate_certificate(instance: Instance, placements: list[dict], require_complete: bool) -> list[str]:
    errors: list[str] = []
    expected = {item["item_id"]: item for item in expanded_items(instance)}
    seen: set[str] = set()
    container = tuple(float(value) for value in instance.container)
    tolerance = 1e-7

    for placement in placements:
        item_id = placement["item_id"]
        if item_id not in expected:
            errors.append(f"{item_id}: unknown item instance")
            continue
        if item_id in seen:
            errors.append(f"{item_id}: duplicate placement")
            continue
        seen.add(item_id)
        item = expected[item_id]
        oriented = tuple(int(round(float(placement[name]))) for name in ("dx", "dy", "dz"))
        if oriented not in allowed_oriented_sizes(tuple(item["size"]), tuple(item["allowed_vertical_dimensions"])):
            errors.append(f"{item_id}: orientation {oriented} violates vertical flags {item['allowed_vertical_dimensions']}")
        coordinates = tuple(float(placement[name]) for name in ("x", "y", "z"))
        dimensions = tuple(float(placement[name]) for name in ("dx", "dy", "dz"))
        if min(*coordinates, *dimensions) < -tolerance:
            errors.append(f"{item_id}: negative coordinate or dimension")
        for axis, (coordinate, dimension, limit) in enumerate(zip(coordinates, dimensions, container)):
            if coordinate + dimension > limit + tolerance:
                errors.append(f"{item_id}: exceeds container on axis {axis}")

    for left, right in combinations(placements, 2):
        if left["bin_id"] != right["bin_id"]:
            continue
        separated = any(
            float(left[coordinate]) + float(left[dimension]) <= float(right[coordinate]) + tolerance
            or float(right[coordinate]) + float(right[dimension]) <= float(left[coordinate]) + tolerance
            for coordinate, dimension in (("x", "dx"), ("y", "dy"), ("z", "dz"))
        )
        if not separated:
            errors.append(f"{left['item_id']} overlaps {right['item_id']} in {left['bin_id']}")

    missing = sorted(set(expected) - seen)
    if require_complete and missing:
        errors.append(f"missing {len(missing)} required items")
    if len(seen) + len(missing) != len(expected):
        errors.append("item accounting mismatch")
    return errors
