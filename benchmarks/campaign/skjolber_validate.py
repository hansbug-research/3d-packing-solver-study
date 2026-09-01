from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validation import Box, validate_aabbs


ROTATIONS = {
    "XYZ": (0, 1, 2),
    "YXZ": (1, 0, 2),
    "ZYX": (2, 1, 0),
    "YZX": (1, 2, 0),
    "XZY": (0, 2, 1),
    "ZXY": (2, 0, 1),
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(fraction * (len(ordered) - 1)))]


def validate_record(
    record: dict[str, Any],
    placements: list[dict[str, str]],
    data_root: Path,
) -> list[str]:
    errors: list[str] = []
    number = int(record["instance_id"].rsplit("-", 1)[1])
    stem = data_root / f"thpack9.txt_{number}"
    items = {row["ID"]: row for row in read_csv(stem.with_name(f"{stem.name}_items.csv"))}
    bin_row = read_csv(stem.with_name(f"{stem.name}_bins.csv"))[0]
    bin_size = tuple(float(bin_row[axis]) for axis in ("X", "Y", "Z"))
    counts: Counter[str] = Counter()
    boxes: list[Box] = []
    bin_refs: set[str] = set()
    for index, placement in enumerate(placements):
        item_id = placement["ITEM_ID"]
        item = items.get(item_id)
        if item is None:
            errors.append(f"unknown item {item_id}")
            continue
        counts[item_id] += 1
        original = tuple(int(item[axis]) for axis in ("X", "Y", "Z"))
        oriented = tuple(int(placement[axis]) for axis in ("DX", "DY", "DZ"))
        permitted = {
            tuple(original[axis] for axis in order)
            for name, order in ROTATIONS.items()
            if item[f"ROTATION_{name}"] == "1"
        }
        if oriented not in permitted:
            errors.append(f"item {item_id} uses forbidden orientation {oriented}")
        bin_ref = placement["BIN_INDEX"]
        bin_refs.add(bin_ref)
        boxes.append(Box(
            f"{item_id}:{index}",
            bin_ref,
            *[float(placement[key]) for key in ("X", "Y", "Z", "DX", "DY", "DZ")],
        ))
    errors.extend(validate_aabbs(boxes, {ref: bin_size for ref in bin_refs}))
    for item_id, item in items.items():
        if counts[item_id] != int(item["COPIES"]):
            errors.append(f"item {item_id}: placed {counts[item_id]}, required {item['COPIES']}")
    expected = sum(int(item["COPIES"]) for item in items.values())
    if len(placements) != expected:
        errors.append(f"placed {len(placements)}, required {expected}")
    if len(placements) != record.get("placements"):
        errors.append("certificate placement count differs from Java record")
    if len(bin_refs) != record.get("bins_used"):
        errors.append("certificate bin count differs from Java record")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--java-records", type=Path, required=True)
    parser.add_argument("--certificate", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records = [json.loads(line) for line in args.java_records.read_text().splitlines() if line.strip()]
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in read_csv(args.certificate):
        grouped[(row["INSTANCE"], row["ALGORITHM"])].append(row)

    for record in records:
        if record["status"] == "MALFORMED_SOURCE_EXCLUDED":
            record["independent_validation"] = "NOT_APPLICABLE"
            record["independent_validation_errors"] = []
            continue
        errors = validate_record(
            record,
            grouped[(record["instance_id"], record["algorithm"])],
            args.data_root,
        )
        record["independent_validation_errors"] = errors
        record["independent_validation"] = "PASS" if not errors else "FAIL"
        if errors:
            record["status"] = "INVALID"

    summaries: dict[str, Any] = {}
    for algorithm in ("laff", "plain", "fast_brute_force"):
        selected = [record for record in records if record["algorithm"] == algorithm]
        valid_source = [record for record in selected if record["source_line_valid"]]
        valid = [record for record in valid_source if record["status"] == "VALID"]
        bins = [float(record["bins_used"]) for record in valid]
        wall = [float(record["wall_time_ms"]) for record in valid_source]
        summaries[algorithm] = {
            "records": len(selected),
            "source_valid": len(valid_source),
            "validated": len(valid),
            "invalid": len(valid_source) - len(valid),
            "mean_bins": statistics.fmean(bins) if bins else None,
            "median_bins": statistics.median(bins) if bins else None,
            "p95_bins": percentile(bins, 0.95),
            "mean_wall_time_ms": statistics.fmean(wall) if wall else None,
            "p95_wall_time_ms": percentile(wall, 0.95),
            "max_wall_time_ms": max(wall, default=None),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        "schema_version": 1,
        "campaign": "skjolber-thpack9/1",
        "engine": "skjolber/3d-bin-container-packing",
        "source_commit": "c73d52190c029a14e64f1bbdd2ea70452d1eb83d",
        "jvm": "OpenJDK 21.0.12",
        "parameters": {"deadline_ms_per_run": 10_000, "active_processor_count": 1, "max_heap_mib": 512},
        "summaries": summaries,
        "records": records,
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
