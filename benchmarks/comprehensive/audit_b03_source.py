from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "benchmarks" / "data" / "comprehensive" / "b03-source-index.json"
SOURCE_COMMIT = "d953148b8f710c06fa6c410949b7272f9e36327b"
DATASET_ADDITION_COMMIT = "03b1e218df45be5e5f33fee1b7901b97610718e1"
REFERENCE_ADDITION_COMMIT = "9d83d632edf5686823bb7b5b51e6e3a7dd641234"
EXPECTED_MISSING_REFERENCES = {
    "ep3d-60-U-C-90.3kp",
    "ep3d-60-U-R-50.3kp",
    "ep3d-60-U-R-90.3kp",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def parse_raw(path: Path) -> tuple[tuple[int, int, int], list[dict[str, int]]]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    dimensions = [part.strip() for part in lines[0].split(",")]
    if dimensions[0] != "dim" or len(dimensions) != 4:
        raise ValueError(f"invalid B03 dimension row: {path}")
    container = tuple(int(value) for value in dimensions[1:])
    items: list[dict[str, int]] = []
    for line in lines[1:]:
        parts = [part.strip() for part in line.split(",")]
        if parts[0] != "box" or len(parts) != 7:
            raise ValueError(f"invalid B03 item row: {path}: {line}")
        values = [int(value) for value in parts[1:]]
        items.append(dict(zip(("id", "x", "y", "z", "profit", "copies"), values, strict=True)))
    return container, items


def expected_names() -> set[str]:
    return {
        f"ep3d-{count}-{shape}-{distribution}-{capacity}.3kp"
        for count in (20, 40, 60)
        for shape in ("F", "L", "C", "U", "D")
        for distribution in ("C", "R")
        for capacity in ("50", "90")
    }


def build_index(source_root: Path) -> dict[str, Any]:
    raw_dir = source_root / "data" / "box_raw" / "egeblad2009"
    converted_dir = source_root / "data" / "box" / "egeblad2009"
    reference_path = source_root / "data" / "box" / "data_knapsack_egeblad2009.csv"
    required = [raw_dir / "format.txt", raw_dir / "generator3d.c", reference_path]
    for path in required:
        if not path.exists():
            raise ValueError(f"B03 source file is missing: {path}")

    expected = expected_names()
    actual_names = {path.name for path in raw_dir.glob("*.3kp")}
    if actual_names != expected:
        raise ValueError(f"B03 source corpus is not the expected 60 instances: {sorted(actual_names ^ expected)}")

    references: dict[str, int] = {}
    for row in read_csv(reference_path):
        name = Path(row["Path"]).name
        references[name] = int(row["Best known solution value"])
    missing_references = expected - set(references)
    if len(references) != 57 or missing_references != EXPECTED_MISSING_REFERENCES:
        raise ValueError(f"unexpected B03 best-known coverage: {len(references)}/60; missing={sorted(missing_references)}")

    files_for_corpus_hash: list[tuple[str, str]] = []
    instances: list[dict[str, Any]] = []
    pattern = re.compile(r"ep3d-(20|40|60)-([FLCUD])-([CR])-(50|90)\.3kp")
    for name in sorted(actual_names):
        match = pattern.fullmatch(name)
        if match is None:
            raise ValueError(f"unexpected B03 instance name: {name}")
        raw_path = raw_dir / name
        items_path = converted_dir / f"{name}_items.csv"
        bins_path = converted_dir / f"{name}_bins.csv"
        for path in (raw_path, items_path, bins_path):
            if not path.exists():
                raise ValueError(f"B03 converted source file is missing: {path}")

        container, raw_items = parse_raw(raw_path)
        item_rows = read_csv(items_path)
        bin_rows = read_csv(bins_path)
        if tuple(item_rows[0]) != ("ID", "X", "Y", "Z", "PROFIT", "COPIES"):
            raise ValueError(f"B03 conversion unexpectedly changes item semantics: {items_path}")
        if len(bin_rows) != 1 or tuple(bin_rows[0]) != ("ID", "X", "Y", "Z"):
            raise ValueError(f"B03 conversion has invalid bin schema: {bins_path}")
        converted_container = tuple(int(bin_rows[0][axis]) for axis in ("X", "Y", "Z"))
        converted_items = [
            {
                "id": int(row["ID"]),
                "x": int(row["X"]),
                "y": int(row["Y"]),
                "z": int(row["Z"]),
                "profit": int(row["PROFIT"]),
                "copies": int(row["COPIES"]),
            }
            for row in item_rows
        ]
        if converted_container != container or converted_items != raw_items:
            raise ValueError(f"B03 raw-to-CSV conversion mismatch: {name}")
        expected_count = int(match.group(1))
        if len(raw_items) != expected_count or [item["id"] for item in raw_items] != list(range(expected_count)):
            raise ValueError(f"B03 item IDs/count mismatch: {name}")
        if any(item["copies"] != 1 for item in raw_items):
            raise ValueError(f"B03 corpus contains unexpected multiplicity: {name}")
        if any(item[axis] > container[index] for item in raw_items for index, axis in enumerate(("x", "y", "z"))):
            raise ValueError(f"B03 fixed-pose item exceeds its container: {name}")

        relative_hashes = {
            "raw": sha256(raw_path),
            "items": sha256(items_path),
            "bins": sha256(bins_path),
        }
        for kind, digest in relative_hashes.items():
            files_for_corpus_hash.append((f"{name}:{kind}", digest))
        maximum_item_profit = max(item["profit"] for item in raw_items)
        upstream_reference = references.get(name)
        instances.append(
            {
                "id": name,
                "item_count": expected_count,
                "shape_class": match.group(2),
                "distribution": "CLUSTERED" if match.group(3) == "C" else "RANDOM",
                "capacity_class": int(match.group(4)),
                "container": list(container),
                "total_profit": sum(item["profit"] * item["copies"] for item in raw_items),
                "maximum_item_profit": maximum_item_profit,
                "upstream_reference_profit": upstream_reference,
                "reference_status": "INVALID_REFERENCE_TABLE" if name in references else "MISSING_REFERENCE",
                "reference_below_single_item_lower_bound": (
                    upstream_reference < maximum_item_profit if upstream_reference is not None else None
                ),
                "pose_semantics": "FIXED_XYZ",
                "sha256": relative_hashes,
            }
        )

    corpus_hash = hashlib.sha256(canonical_json(files_for_corpus_hash).encode("utf-8")).hexdigest()
    return {
        "schema_version": 1,
        "benchmark_id": "B03",
        "source_repository": "HansBug/packingsolver",
        "source_commit": SOURCE_COMMIT,
        "dataset_addition_commit": DATASET_ADDITION_COMMIT,
        "reference_addition_commit": REFERENCE_ADDITION_COMMIT,
        "source_paths": {
            "raw": "data/box_raw/egeblad2009",
            "converted": "data/box/egeblad2009",
            "best_known": "data/box/data_knapsack_egeblad2009.csv",
        },
        "source_file_sha256": {
            "format.txt": sha256(raw_dir / "format.txt"),
            "generator3d.c": sha256(raw_dir / "generator3d.c"),
            "data_knapsack_egeblad2009.csv": sha256(reference_path),
        },
        "corpus_sha256": corpus_hash,
        "instance_count": len(instances),
        "best_known_reference_count": len(references),
        "missing_best_known_references": sorted(missing_references),
        "invalid_reference_table": {
            "status": "INVALID_SCALE_FOR_CURRENT_CORPUS",
            "rows": len(references),
            "rows_below_single_item_lower_bound": sum(
                row["reference_below_single_item_lower_bound"] is True for row in instances
            ),
            "ranking_use": "FORBIDDEN",
        },
        "license_status": "NO_STANDALONE_DATASET_LICENSE_LOCATED; full corpus is fetched from the pinned upstream repository and is not vendored here",
        "generator_audit": {
            "fixed_seed": 0,
            "profit_formula": "x*y*z+200",
            "known_source_defect": "container fit loop assigns d=items[i].h instead of items[i].d; no fixed-pose item exceeds its container in the committed 60-instance corpus",
        },
        "instances": instances,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit and index the pinned Egeblad-Pisinger B03 source corpus")
    parser.add_argument("--source-root", type=Path, default=ROOT / ".cache" / "packingsolver-fork")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = canonical_json(build_index(args.source_root.resolve()))
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != content:
            print(f"B03_SOURCE_STALE: {OUTPUT}", file=sys.stderr)
            return 1
        print("B03_SOURCE_OK: 60 fixed-pose instances; upstream 57-row reference table is invalid for ranking")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(content, encoding="utf-8")
    print(OUTPUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
