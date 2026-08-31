from __future__ import annotations

import json
from pathlib import Path

from model import expanded_items, orientation_support, parse_all, validate_certificate


ROOT = Path(__file__).resolve().parents[3]
SOURCE_DIR = ROOT / ".cache" / "esicup-datasets" / "3d_rectangular" / "thpack"
OUTPUT = ROOT / "raw" / "experiments" / "campaign" / "python_thpack" / "self-check.json"


def main() -> None:
    instances = parse_all(SOURCE_DIR)
    family_counts = {family: sum(instance.family == family for instance in instances) for family in {i.family for i in instances}}
    assert len(instances) == 762
    assert all(family_counts[f"THPACK{number}"] == 100 for number in range(1, 8))
    assert family_counts["THPACK8"] == 15
    assert family_counts["THPACK9"] == 47
    malformed = [instance.key for instance in instances if instance.source_line_errors]
    assert malformed == ["THPACK9-018", "THPACK9-019", "THPACK9-020"]

    expressible = {
        library: [instance.key for instance in instances if orientation_support(instance, library)[0]]
        for library in ("py3dbp", "jerry")
    }
    assert len(expressible["py3dbp"]) == 53
    assert len(expressible["jerry"]) == 87

    upright = next(
        instance
        for instance in instances
        if any(item.allowed_vertical_dimensions == (0, 0, 1) and len(set(item.size)) == 3 for item in instance.item_types)
    )
    item = next(item for item in upright.item_types if item.allowed_vertical_dimensions == (0, 0, 1) and len(set(item.size)) == 3)
    item_id = next(spec["item_id"] for spec in expanded_items(upright) if spec["type_id"] == item.type_id)
    forbidden = {
        "item_id": item_id,
        "bin_id": "bin:0",
        "x": 0,
        "y": 0,
        "z": 0,
        "dx": item.size[1],
        "dy": item.size[2],
        "dz": item.size[0],
    }
    orientation_errors = validate_certificate(upright, [forbidden], require_complete=False)
    assert any("violates vertical flags" in error for error in orientation_errors)

    public = next(instance for instance in instances if instance.key == "THPACK9-001")
    ids = [item["item_id"] for item in expanded_items(public)[:2]]
    overlapping = [
        {"item_id": ids[0], "bin_id": "bin:0", "x": 0, "y": 0, "z": 0, "dx": 2, "dy": 6, "dz": 8},
        {"item_id": ids[1], "bin_id": "bin:0", "x": 0, "y": 0, "z": 0, "dx": 2, "dy": 6, "dz": 8},
    ]
    overlap_errors = validate_certificate(public, overlapping, require_complete=False)
    assert any("overlaps" in error for error in overlap_errors)

    result = {
        "status": "PASS",
        "parsed_instances": len(instances),
        "family_counts": dict(sorted(family_counts.items())),
        "malformed_instances": malformed,
        "expressible_instances": {library: len(keys) for library, keys in expressible.items()},
        "negative_checks": {
            "forbidden_orientation_rejected": True,
            "overlap_rejected": True,
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
