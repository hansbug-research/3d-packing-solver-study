#!/usr/bin/env python3
"""Parse and audit the complete OR-Library BAYTP source.

The BAYTP corpus is kept outside the repository because the upstream page does
not provide a redistributable snapshot.  This parser therefore takes a local
download, verifies the registered content hashes, and emits a compact canonical
audit.  It deliberately does not solve the shelf assignment problem.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {
    "products.txt": "f814947ad7f2cfe2bf43fa3a5ee8d087ecf35f442376a25afa50f72f6147e52e",
    "shelves.txt": "914231bd5a53ad890a4e9817e7381d967658bffed4989343eabbc623a845cef7",
    "baytp1.txt": "9a9b06a40628e87d03fbe36e6a0db220043e4fe45891cc9c2d7498b394621c63",
    "baytp2.txt": "f334858c23120de183424bbda24784435311b263ce8c730cd78c17b649bcc125",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def integer_rows(path: Path, width: int) -> list[list[int]]:
    rows: list[list[int]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        values = raw.split()
        if not values:
            continue
        if len(values) != width:
            raise ValueError(f"{path}:{line_number}: expected {width} fields, got {len(values)}")
        try:
            rows.append([int(value) for value in values])
        except ValueError as exc:
            raise ValueError(f"{path}:{line_number}: non-integer field") from exc
    return rows


def positive(rows: list[list[int]], label: str, indexes: tuple[int, ...]) -> None:
    for row_number, row in enumerate(rows, 1):
        if any(row[index] <= 0 for index in indexes):
            raise ValueError(f"{label}:{row_number}: dimensions/counts must be positive")


def audit(source_dir: Path) -> dict[str, Any]:
    paths = {name: source_dir / name for name in EXPECTED}
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing BAYTP source files: {', '.join(missing)}")
    hashes = {name: sha256(path) for name, path in paths.items()}
    mismatched = {
        name: {"expected": EXPECTED[name], "actual": digest}
        for name, digest in hashes.items()
        if digest != EXPECTED[name]
    }
    if mismatched:
        raise ValueError(f"BAYTP source hash mismatch: {mismatched}")

    products = integer_rows(paths["products.txt"], 5)
    shelves = integer_rows(paths["shelves.txt"], 7)
    bays = {name[:-4]: integer_rows(paths[name], 4) for name in ("baytp1.txt", "baytp2.txt")}
    if len(products) != 6000:
        raise ValueError(f"products.txt: expected 6000 rows, got {len(products)}")
    if len(shelves) != 49:
        raise ValueError(f"shelves.txt: expected 49 rows, got {len(shelves)}")
    if any(len(rows) != 350 for rows in bays.values()):
        raise ValueError("each BAYTP bay file must contain 350 rows")

    positive(products, "products", (1, 2, 3, 4))
    positive(shelves, "shelves", (0, 1, 3, 4, 5, 6))
    positive([row for rows in bays.values() for row in rows], "bays", (0, 1, 2, 3))
    shelf_numbers = [row[0] for row in shelves]
    if shelf_numbers != list(range(1, 50)):
        raise ValueError("shelves.txt: shelf numbers must be 1..49 in source order")
    family_counts = Counter(row[0] for row in products)
    quantities = [row[1] for row in products]
    dimensions = [value for row in products for value in row[2:]]
    bay_summary = {
        name: {
            "rows": len(rows),
            "distinct_rows": len({tuple(row) for row in rows}),
            "first": rows[0],
            "last": rows[-1],
            "available_height_min": min(row[3] for row in rows),
            "available_height_max": max(row[3] for row in rows),
        }
        for name, rows in bays.items()
    }
    return {
        "schema_version": 1,
        "record_kind": "B30_BAYTP_CANONICAL_SOURCE_AUDIT",
        "benchmark_id": "B30",
        "input_status": "VALID",
        "run_status": "NOT_RUN",
        "source": {
            "repository": "OR-Library",
            "products_url": "https://people.brunel.ac.uk/~mastjjb/jeb/orlib/files/products.txt",
            "shelves_url": "https://people.brunel.ac.uk/~mastjjb/jeb/orlib/files/shelves.txt",
            "baytp1_url": "https://people.brunel.ac.uk/~mastjjb/jeb/orlib/files/baytp1.txt",
            "baytp2_url": "https://people.brunel.ac.uk/~mastjjb/jeb/orlib/files/baytp2.txt",
            "sha256": hashes,
        },
        "products": {
            "rows": len(products),
            "product_families": len(family_counts),
            "family_id_min": min(family_counts),
            "family_id_max": max(family_counts),
            "total_quantity": sum(quantities),
            "quantity_min": min(quantities),
            "quantity_max": max(quantities),
            "dimension_min": min(dimensions),
            "dimension_max": max(dimensions),
        },
        "shelves": {
            "rows": len(shelves),
            "number_min": shelf_numbers[0],
            "number_max": shelf_numbers[-1],
            "position_min": min(row[2] for row in shelves),
            "position_max": max(row[2] for row in shelves),
            "thickness_values": sorted({row[1] for row in shelves}),
        },
        "bays": bay_summary,
        "semantic_contract": {
            "all_orientations_allowed": True,
            "shelf_overhang_allowed": False,
            "bay_sequence_is_fixed": True,
            "shelf_sequence_is_fixed": True,
            "shelf_fields": ["number", "thickness", "position", "top_gap", "left_gap", "inter_gap", "right_gap"],
            "bay_fields": ["width", "height", "depth", "available_height"],
            "product_fields": ["family", "quantity", "length", "width", "height"],
            "note": "This is a source audit only; no shelf assignment or quality result is implied.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = json.dumps(audit(args.source_dir), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != content:
            print(f"B30_CANONICAL_AUDIT_STALE: {args.output}")
            return 1
        print("B30_CANONICAL_AUDIT_OK")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
