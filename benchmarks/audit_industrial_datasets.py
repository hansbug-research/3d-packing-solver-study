#!/usr/bin/env python3
"""Reproduce the Alonso and BAYTP dataset-scope statistics."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any


ESICUP_COMMIT = "154a8f006a8e72f65d734f2d1e36777f678f31f8"
BAYTP_PRODUCTS_SHA256 = (
    "f814947ad7f2cfe2bf43fa3a5ee8d087ecf35f442376a25afa50f72f6147e52e"
)
BAYTP_SHELVES_SHA256 = (
    "914231bd5a53ad890a4e9817e7381d967658bffed4989343eabbc623a845cef7"
)


def integer(value: str) -> int:
    return int(value)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_esicup_commit(root: Path) -> None:
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    actual = completed.stdout.strip()
    if actual != ESICUP_COMMIT:
        raise ValueError(f"ESICUP commit is {actual}, expected {ESICUP_COMMIT}")


def parse_sections(path: Path) -> dict[str, list[list[str]]]:
    sections: dict[str, list[list[str]]] = {}
    current: str | None = None
    expected = 0
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            parts = line.split()
            if len(parts) != 2:
                raise ValueError(f"{path}:{line_number}: malformed section header")
            if current is not None and len(sections[current]) != expected:
                raise ValueError(f"{path}: section {current} has wrong row count")
            current = parts[0][1:].lower()
            expected = integer(parts[1])
            sections[current] = []
            continue
        if current is None:
            raise ValueError(f"{path}:{line_number}: row outside a section")
        sections[current].append(line.split())
    if current is not None and len(sections[current]) != expected:
        raise ValueError(f"{path}: section {current} has wrong row count")
    if set(sections) != {"products", "layers", "pallets", "trucks"}:
        raise ValueError(f"{path}: unexpected sections {sorted(sections)}")
    return sections


def compact_median(values: list[int]) -> int | float:
    result = statistics.median(values)
    return int(result) if float(result).is_integer() else result


def row_summary(values: list[int]) -> dict[str, int | float]:
    return {
        "total": sum(values),
        "per_instance_min": min(values),
        "per_instance_median": compact_median(values),
        "per_instance_max": max(values),
    }


def require_width(rows: list[list[str]], width: int, label: str) -> None:
    widths = Counter(map(len, rows))
    if widths != {width: len(rows)}:
        raise ValueError(f"{label}: expected width {width}, got {dict(widths)}")


def summarize_alonso(directory: Path, pattern: str, year: int) -> dict[str, Any]:
    paths = sorted(directory.glob(pattern))
    if not paths:
        raise ValueError(f"no Alonso {year} instances under {directory}")
    parsed = [parse_sections(path) for path in paths]
    products = [row for instance in parsed for row in instance["products"]]
    layers = [row for instance in parsed for row in instance["layers"]]
    pallets = [row for instance in parsed for row in instance["pallets"]]
    trucks = [row for instance in parsed for row in instance["trucks"]]
    product_width = 14 if year == 2019 else 25
    layer_width = 8 if year == 2019 else 9
    require_width(products, product_width, f"Alonso {year} products")
    require_width(layers, layer_width, f"Alonso {year} layers")
    require_width(pallets, 5, f"Alonso {year} pallets")
    require_width(trucks, 9, f"Alonso {year} trucks")

    summary: dict[str, Any] = {
        "capability_status": "NOT_SUPPORTED",
        "run_status": "NOT_RUN",
        "instances": len(paths),
        "sections": {
            section: row_summary([len(instance[section]) for instance in parsed])
            for section in ("products", "layers", "pallets", "trucks")
        },
        "product_rows": len(products),
        "layer_rows": len(layers),
    }
    if year == 2019:
        summary.update(
            {
                "total_product_demand": sum(integer(row[2]) for row in products),
                "delivery_day_counts": dict(
                    sorted(Counter(integer(row[1]) for row in products).items())
                ),
                "product_rotation_xyz_counts": dict(
                    sorted(Counter("".join(row[7:10]) for row in products).items())
                ),
                "stacking_group_counts": dict(
                    sorted(Counter(integer(row[10]) for row in products).items())
                ),
                "always_top_counts": dict(
                    sorted(Counter(integer(row[11]) for row in products).items())
                ),
                "always_bottom_counts": dict(
                    sorted(Counter(integer(row[12]) for row in products).items())
                ),
                "layer_rotation_z_counts": dict(
                    sorted(Counter(integer(row[5]) for row in layers).items())
                ),
            }
        )
        return summary

    for row in products:
        total = integer(row[2])
        stock_total = integer(row[3])
        case_total = integer(row[4])
        rest = integer(row[5]) + integer(row[8]) + integer(row[11])
        if total != stock_total + case_total + rest:
            raise ValueError("Alonso 2020 total-demand identity failed")
        if stock_total != integer(row[6]) + integer(row[9]) + integer(row[12]):
            raise ValueError("Alonso 2020 stock-demand identity failed")
        if case_total != integer(row[7]) + integer(row[10]) + integer(row[13]):
            raise ValueError("Alonso 2020 case-demand identity failed")

    summary.update(
        {
            "total_product_demand": sum(integer(row[2]) for row in products),
            "readme_delivery_day_column_value_counts": dict(
                sorted(Counter(integer(row[1]) for row in products).items())
            ),
            "demand_by_pallet_class": {
                "stock": sum(integer(row[3]) for row in products),
                "case": sum(integer(row[4]) for row in products),
                "rest": sum(
                    integer(row[5]) + integer(row[8]) + integer(row[11])
                    for row in products
                ),
            },
            "demand_by_day": {
                str(day): sum(
                    integer(row[5 + offset])
                    + integer(row[6 + offset])
                    + integer(row[7 + offset])
                    for row in products
                )
                for day, offset in ((1, 0), (2, 3), (3, 6))
            },
            "product_rotation_xyz_counts": dict(
                sorted(Counter("".join(row[18:21]) for row in products).items())
            ),
            "stacking_group_counts": dict(
                sorted(Counter(integer(row[21]) for row in products).items())
            ),
            "always_top_counts": dict(
                sorted(Counter(integer(row[22]) for row in products).items())
            ),
            "always_bottom_counts": dict(
                sorted(Counter(integer(row[23]) for row in products).items())
            ),
            "layer_rotation_z_counts": dict(
                sorted(Counter(integer(row[5]) for row in layers).items())
            ),
            "demand_identities_verified": True,
        }
    )
    return summary


def parse_integer_rows(path: Path, width: int) -> list[list[int]]:
    rows = [line.split() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    require_width(rows, width, str(path))
    return [[integer(value) for value in row] for row in rows]


def summarize_baytp(
    directory: Path, products_path: Path | None, shelves_path: Path | None
) -> dict[str, Any]:
    readme = directory / "README.txt"
    bay_paths = [directory / "baytp1.txt", directory / "baytp2.txt"]
    snapshot_files = sorted(path.name for path in directory.iterdir() if path.is_file())
    common_products_present = any(
        (directory / filename).is_file() for filename in ("products", "products.txt")
    )
    common_shelves_present = any(
        (directory / filename).is_file() for filename in ("shelves", "shelves.txt")
    )
    result: dict[str, Any] = {
        "capability_status": "ESICUP_SNAPSHOT_INCOMPLETE",
        "run_status": "NOT_RUN",
        "esicup_snapshot_files": snapshot_files,
        "esicup_snapshot_has_required_common_products": common_products_present,
        "esicup_snapshot_has_required_common_shelves": common_shelves_present,
        "esicup_snapshot_complete": common_products_present and common_shelves_present,
        "readme_present": readme.exists(),
        "bays": {},
    }
    for path in bay_paths:
        rows = parse_integer_rows(path, 4)
        result["bays"][path.stem] = {
            "rows": len(rows),
            "distinct_rows": len(set(map(tuple, rows))),
        }

    if products_path is None and shelves_path is None:
        result["official_or_library_recovery"] = "not_provided"
        return result
    if products_path is None or shelves_path is None:
        raise ValueError("provide both --baytp-products and --baytp-shelves")
    hashes = {
        "products": sha256(products_path),
        "shelves": sha256(shelves_path),
    }
    expected = {
        "products": BAYTP_PRODUCTS_SHA256,
        "shelves": BAYTP_SHELVES_SHA256,
    }
    if hashes != expected:
        raise ValueError(f"BAYTP recovery hash mismatch: got {hashes}")
    products = parse_integer_rows(products_path, 5)
    shelves = parse_integer_rows(shelves_path, 7)
    result["official_or_library_recovery"] = {
        "sha256": hashes,
        "product_rows": len(products),
        "product_families": len({row[0] for row in products}),
        "total_quantity": sum(row[1] for row in products),
        "quantity_min": min(row[1] for row in products),
        "quantity_max": max(row[1] for row in products),
        "shelf_rows": len(shelves),
    }
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--esicup-root",
        type=Path,
        required=True,
        help="ESICUP datasets checkout at the pinned commit",
    )
    parser.add_argument("--baytp-products", type=Path)
    parser.add_argument("--baytp-shelves", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    require_esicup_commit(args.esicup_root)
    rectangular = args.esicup_root / "3d_rectangular"
    result = {
        "source": {
            "repository": "https://github.com/ESICUP/datasets.git",
            "commit": ESICUP_COMMIT,
        },
        "alonso_2019": summarize_alonso(
            rectangular / "alonso_2019", "inst3d*.csv", 2019
        ),
        "alonso_2020": summarize_alonso(
            rectangular / "alonso_2020", "inst3d_*.csv", 2020
        ),
        "baytp": summarize_baytp(
            rectangular / "baytp", args.baytp_products, args.baytp_shelves
        ),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
