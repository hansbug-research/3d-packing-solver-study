#!/usr/bin/env python3
"""Audit the checked-in protocol-v3 constraint fixtures.

The constraint gauntlet is a versioned, repository-owned fixture rather than
an external academic archive. This audit makes that provenance explicit and
refuses malformed CSV, non-positive dimensions, invalid copies, or malformed
pose flags before the suite is marked executable.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = ROOT / "benchmarks" / "data" / "packingsolver"
EXTENSION_FIXTURE = ROOT / "benchmarks" / "data" / "comprehensive" / "constraint-extension-fixture.json"

CASES: dict[str, tuple[str, str]] = {
    "B09/LARGE_CHEAPER": ("heterogeneous_items.csv", "heterogeneous_bins.csv"),
    "B09/SMALL_CHEAPER": ("heterogeneous_items.csv", "heterogeneous_bins_reverse.csv"),
    "B12/ROTATION_REQUIRED": ("rotation_allowed_items.csv", "rotation_bins.csv"),
    "B12/ROTATION_FORBIDDEN": ("rotation_forbidden_items.csv", "rotation_bins.csv"),
    "B13/WEIGHT_LIMIT": ("weight_items.csv", "weight_bins.csv"),
    "B14/MAXIMUM_WEIGHT_ABOVE": ("stack_items.csv", "stack_bins.csv"),
    "B14/MAXIMUM_STACK_COUNT": ("stack_count_items.csv", "stack_count_bins.csv"),
    "B14/NESTING_HEIGHT": ("nesting_items.csv", "nesting_bins.csv"),
    "B15/AXLE_NORMAL": ("axle_realistic_items.csv", "axle_normal_bins.csv"),
    "B15/AXLE_BOUNDARY": ("axle_items.csv", "axle_bins.csv"),
    "B15/AXLE_INFEASIBLE": ("axle_realistic_items.csv", "axle_infeasible_bins.csv"),
    "B17/UNLOADING_NONE": ("unloading_items.csv", "unloading_bins.csv"),
    "B17/INCREASING_X": ("unloading_items.csv", "unloading_bins.csv"),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def validate_table(path: Path, kind: str) -> dict[str, Any]:
    rows = read_csv(path)
    if not rows:
        raise ValueError(f"empty {kind} fixture: {path}")
    required = {"ID", "X", "Y", "Z", "COPIES"}
    if kind == "items":
        required |= {
            "ROTATION_XYZ", "ROTATION_YXZ", "ROTATION_ZYX",
            "ROTATION_YZX", "ROTATION_XZY", "ROTATION_ZXY", "WEIGHT",
        }
    else:
        required |= {"COST"}
    missing = sorted(required - set(rows[0]))
    if missing:
        raise ValueError(f"{path.name} missing columns: {missing}")
    ids = [row["ID"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate IDs in {path}")
    for index, row in enumerate(rows, 1):
        try:
            dimensions = [float(row[axis]) for axis in ("X", "Y", "Z")]
            copies = int(row["COPIES"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid numeric field in {path}:{index}: {exc}") from exc
        if any(value <= 0 for value in dimensions):
            raise ValueError(f"non-positive dimensions in {path}:{index}")
        if copies < 0:
            raise ValueError(f"negative copies in {path}:{index}")
        if kind == "items":
            for name in (
                "ROTATION_XYZ", "ROTATION_YXZ", "ROTATION_ZYX",
                "ROTATION_YZX", "ROTATION_XZY", "ROTATION_ZXY",
            ):
                if row.get(name) not in {"0", "1"}:
                    raise ValueError(f"rotation flag is not 0/1 in {path}:{index}/{name}")
            if float(row["WEIGHT"]) < 0:
                raise ValueError(f"negative item weight in {path}:{index}")
    return {
        "rows": len(rows),
        "total_copies": sum(int(row["COPIES"]) for row in rows),
        "sha256": sha256(path),
    }


def audit() -> dict[str, Any]:
    file_stats: dict[str, dict[str, Any]] = {}
    case_stats: dict[str, dict[str, Any]] = {}
    for case, (item_name, bin_name) in sorted(CASES.items()):
        item_path = DATA_ROOT / item_name
        bin_path = DATA_ROOT / bin_name
        if not item_path.is_file() or not bin_path.is_file():
            raise ValueError(f"missing fixture for {case}: {item_name}, {bin_name}")
        item_stats = validate_table(item_path, "items")
        bin_stats = validate_table(bin_path, "bins")
        file_stats[item_name] = item_stats
        file_stats[bin_name] = bin_stats
        case_stats[case] = {
            "items": item_name,
            "bins": bin_name,
            "required_items": item_stats["total_copies"],
            "bin_copies": bin_stats["total_copies"],
        }
    extension = json.loads(EXTENSION_FIXTURE.read_text(encoding="utf-8"))
    if extension.get("schema_version") != 1 or set(extension.get("cases", {})) != {"B16/KEEP_OUT", "B18/SEGREGATION"}:
        raise ValueError("constraint extension fixture schema mismatch")
    extension_stats = {
        "path": str(EXTENSION_FIXTURE.relative_to(ROOT)),
        "sha256": sha256(EXTENSION_FIXTURE),
        "cases": sorted(extension["cases"]),
    }
    return {
        "schema_version": 1,
        "record_kind": "CONSTRAINT_FIXTURE_SOURCE_AUDIT",
        "audit_date": "2026-09-01",
        "repository": "packing-software-study",
        "fixture_root": "benchmarks/data/packingsolver",
        "input_status": "VALID",
        "cases": case_stats,
        "files": file_stats,
        "extension_fixture": extension_stats,
        "semantic_note": "Repository-owned adversarial conformance fixtures, not published quality benchmarks. Expected behavior and independent validation are defined by run_constraint_gauntlet.py.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = json.dumps(audit(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != content:
            print(f"CONSTRAINT_SOURCE_AUDIT_STALE: {args.output}")
            return 1
        print("CONSTRAINT_SOURCE_AUDIT_OK")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
