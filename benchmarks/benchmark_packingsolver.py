from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path
from time import perf_counter

from validation import Box, cumulative_weight_above, validate_aabbs

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "benchmarks" / "data" / "packingsolver"
RAW = ROOT / "results" / "raw"
BIN = ROOT / ".cache" / "packingsolver"


def run_case(name, executable, items, bins, objective, expected_items, extra=()):
    certificate = RAW / f"packingsolver_{name}.csv"
    output = RAW / f"packingsolver_{name}.json"
    certificate.unlink(missing_ok=True)
    output.unlink(missing_ok=True)
    cmd = [
        str(BIN / executable),
        "--items", str(DATA / items),
        "--bins", str(DATA / bins),
        "--objective", objective,
        "--time-limit", "10",
        "--memory-limit", "1024",
        "--verbosity-level", "0",
        "--certificate", str(certificate),
        "--output", str(output),
        "--only-write-at-the-end",
        *extra,
    ]
    started = perf_counter()
    completed = subprocess.run(cmd, text=True, capture_output=True, timeout=20)
    elapsed = perf_counter() - started
    result = {
        "returncode": completed.returncode,
        "elapsed_s": elapsed,
        "stderr_tail": completed.stderr[-500:],
        "certificate_created": certificate.exists(),
    }
    if not certificate.exists():
        result.update({"packed": 0, "expected": expected_items, "validation_errors": ["no certificate"]})
        return result

    with (DATA / items).open(newline="") as handle:
        item_specs = {row["ID"]: row for row in csv.DictReader(handle)}
    with (DATA / bins).open(newline="") as handle:
        bin_specs = {row["ID"]: row for row in csv.DictReader(handle)}
    with certificate.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    bin_sizes = {}
    bin_weights = {}
    placements = []
    placement_item_ids = []
    for row in rows:
        if row["TYPE"] == "BIN":
            ref = row["BIN"]
            bin_sizes[ref] = (float(row["LX"]), float(row["LY"]), float(row["LZ"]))
            bin_weights[ref] = float(bin_specs[row["ID"]].get("MAXIMUM_WEIGHT", "inf"))
        elif row["TYPE"] == "ITEM":
            copies = int(row["COPIES"])
            for copy in range(copies):
                placements.append(Box(
                    f"{row['ID']}:{copy}:{len(placements)}", row["BIN"],
                    float(row["X"]), float(row["Y"]), float(row["Z"]),
                    float(row["LX"]), float(row["LY"]), float(row["LZ"]),
                    float(item_specs[row["ID"]].get("WEIGHT", 0)),
                ))
                placement_item_ids.append(row["ID"])
    errors = validate_aabbs(placements, bin_sizes, bin_weights)
    if len(placements) != expected_items:
        errors.append(f"packed {len(placements)} != expected {expected_items}")
    used_cost = sum(float(bin_specs[row["ID"]].get("COST", 0)) * int(row["COPIES"])
                    for row in rows if row["TYPE"] == "BIN")
    max_above_violations = []
    for placement, item_id in zip(placements, placement_item_ids):
        limit = item_specs[item_id].get("MAXIMUM_WEIGHT_ABOVE")
        if limit not in (None, ""):
            actual = cumulative_weight_above(placement, placements)
            if actual > float(limit) + 1e-7:
                max_above_violations.append({"item_type": item_id, "actual": actual, "limit": float(limit)})
    result.update({
        "packed": len(placements),
        "expected": expected_items,
        "bins_used": len(bin_sizes),
        "bin_type_rows": [row["ID"] for row in rows if row["TYPE"] == "BIN"],
        "used_cost": used_cost,
        "max_weight_above_violations": max_above_violations,
        "validation_errors": errors,
        "placements": [p.__dict__ for p in placements],
    })
    return result


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    cases = {
        "exact_grid": run_case("grid", "packingsolver_box", "grid_items.csv", "grid_bins.csv", "bin-packing", 8),
        "heterogeneous_cost": run_case(
            "heterogeneous", "packingsolver_box", "heterogeneous_items.csv", "heterogeneous_bins.csv",
            "variable-sized-bin-packing", 2,
        ),
        "heterogeneous_cost_boxstacks": run_case(
            "heterogeneous_boxstacks", "packingsolver_boxstacks", "heterogeneous_items.csv", "heterogeneous_bins.csv",
            "variable-sized-bin-packing", 2,
        ),
        "rotation_allowed": run_case(
            "rotation_allowed", "packingsolver_box", "rotation_allowed_items.csv", "rotation_bins.csv",
            "bin-packing", 1,
        ),
        "rotation_forbidden": run_case(
            "rotation_forbidden", "packingsolver_box", "rotation_forbidden_items.csv", "rotation_bins.csv",
            "bin-packing", 1,
        ),
        "weight_limit": run_case("weight", "packingsolver_box", "weight_items.csv", "weight_bins.csv", "bin-packing", 3),
        "stack_weight_above": run_case(
            "stack", "packingsolver_boxstacks", "stack_items.csv", "stack_bins.csv", "bin-packing", 3,
        ),
        "semi_trailer_axle": run_case(
            "axle", "packingsolver_boxstacks", "axle_items.csv", "axle_bins.csv", "bin-packing", 1,
        ),
    }
    print(json.dumps({"library": "fontanf/packingsolver", "release": "latest-2026-07-28", "cases": cases}, indent=2))


if __name__ == "__main__":
    main()
