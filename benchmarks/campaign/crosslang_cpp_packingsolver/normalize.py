#!/usr/bin/env python3
"""Convert a PackingSolver CSV certificate to the campaign JSON contract."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


ROTATION_COLUMNS = (
    "ROTATION_XYZ",
    "ROTATION_YXZ",
    "ROTATION_ZYX",
    "ROTATION_YZX",
    "ROTATION_XZY",
    "ROTATION_ZXY",
)


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=("official", "fixed"), required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--items", type=Path, required=True)
    parser.add_argument("--bins", type=Path, required=True)
    parser.add_argument("--certificate", type=Path, required=True)
    parser.add_argument("--exitcode", type=int, required=True)
    parser.add_argument("--elapsed-ms", type=float, required=True)
    parser.add_argument("--toolchain", required=True)
    arguments = parser.parse_args()

    item_rows = rows(arguments.items)
    bin_rows = rows(arguments.bins)
    item_type_by_certificate_id = {str(index): row["ID"] for index, row in enumerate(item_rows)}
    bin_type_by_certificate_id = {str(index): row["ID"] for index, row in enumerate(bin_rows)}
    item_specs = []
    item_specs_by_type: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in item_rows:
        allowed = [column.removeprefix("ROTATION_").lower() for column in ROTATION_COLUMNS if row[column] == "1"]
        requirement = "fixed" if allowed == ["xyz"] else "any"
        for copy_index in range(int(row["COPIES"])):
            spec = {
                "id": f"{row['ID']}-{copy_index:03}",
                "size": [float(row["X"]), float(row["Y"]), float(row["Z"])],
                "weight": float(row["WEIGHT"]),
                "orientation_requirement": requirement,
                "allowed_orientations": allowed,
            }
            item_specs.append(spec)
            item_specs_by_type[row["ID"]].append(spec)

    bin_specs = []
    available_bins: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in bin_rows:
        for copy_index in range(int(row["COPIES"])):
            spec = {
                "id": f"{row['ID']}-{copy_index:03}",
                "size": [float(row["X"]), float(row["Y"]), float(row["Z"])],
                "max_weight": float(row["MAXIMUM_WEIGHT"]),
                "cost": float(row["COST"]),
            }
            bin_specs.append(spec)
            available_bins[row["ID"]].append(spec)

    placements = []
    placed_ids: set[str] = set()
    if arguments.exitcode == 0 and arguments.certificate.exists():
        certificate_rows = rows(arguments.certificate)
        solution_bins: dict[str, list[str]] = {}
        bin_offsets: dict[str, int] = defaultdict(int)
        item_offsets: dict[str, int] = defaultdict(int)
        for row in certificate_rows:
            if row["TYPE"] != "BIN":
                continue
            bin_type = bin_type_by_certificate_id[row["ID"]]
            count = int(row["COPIES"])
            offset = bin_offsets[bin_type]
            candidates = available_bins[bin_type][offset : offset + count]
            solution_bins[row["BIN"]] = [candidate["id"] for candidate in candidates]
            bin_offsets[bin_type] += count
        for row in certificate_rows:
            if row["TYPE"] != "ITEM":
                continue
            item_type = item_type_by_certificate_id[row["ID"]]
            count = int(row["COPIES"])
            target_bins = solution_bins[row["BIN"]]
            if count > len(target_bins):
                raise SystemExit(f"item row copies {count} exceed bin pattern copies {len(target_bins)}")
            offset = item_offsets[item_type]
            source_items = item_specs_by_type[item_type][offset : offset + count]
            for source, bin_id in zip(source_items, target_bins):
                placements.append(
                    {
                        "item_id": source["id"],
                        "bin_id": bin_id,
                        "position": [float(row["X"]), float(row["Y"]), float(row["Z"])],
                        "size": [float(row["LX"]), float(row["LY"]), float(row["LZ"])],
                        "original_size": source["size"],
                        "weight": source["weight"],
                        "rotation": row["ROTATION"].lower(),
                        "rotation_index": list(source["allowed_orientations"]).index(row["ROTATION"].lower()),
                    }
                )
                placed_ids.add(str(source["id"]))
            item_offsets[item_type] += count

    capability = "SUPPORTED"
    note = "native PackingSolver box model"
    if arguments.variant == "official" and arguments.scenario.startswith("heterogeneous_"):
        capability = "KNOWN_BUG"
        note = "official comparator omits VariableSizedBinPacking; issue #536 / PR #540"
    output = {
        "campaign_version": "crosslang-1",
        "library": f"fontanf/packingsolver ({arguments.variant})",
        "commit": arguments.commit,
        "language": "C++",
        "toolchain": arguments.toolchain,
        "algorithm": "PackingSolver box default portfolio/tree-search pipeline",
        "scenario": arguments.scenario,
        "capability_status": capability,
        "capability_note": note,
        "parameters": {
            "objective": "variable-sized-bin-packing" if arguments.scenario.startswith("heterogeneous_") else "bin-packing",
            "time_limit_s": 2,
            "memory_limit_mb": 1024,
            "threads_requested": 1,
            "solver_exitcode": arguments.exitcode,
        },
        "bins": bin_specs,
        "items": item_specs,
        "placements": placements,
        "unplaced": [spec["id"] for spec in item_specs if spec["id"] not in placed_ids],
        "elapsed_ms": arguments.elapsed_ms,
    }
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
