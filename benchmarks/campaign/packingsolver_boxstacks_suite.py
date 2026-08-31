from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any


ROTATIONS = {
    "XYZ": (0, 1, 2),
    "YXZ": (1, 0, 2),
    "ZYX": (2, 1, 0),
    "YZX": (1, 2, 0),
    "XZY": (0, 2, 1),
    "ZXY": (2, 0, 1),
}


@dataclass(frozen=True)
class Case:
    name: str
    items: str
    bins: str
    objective: str
    expected_items: int
    expected_bins: int | None
    expected_cost: float | None = None
    extra_args: tuple[str, ...] = ()
    expect_complete: bool = True


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def float_field(row: dict[str, str], name: str, default: float = 0.0) -> float:
    value = row.get(name)
    return default if value in (None, "") else float(value)


def axle_weights(bin_spec: dict[str, str], weighted_sum: float, weight: float) -> tuple[float, float]:
    if not int(float_field(bin_spec, "IS_SEMI_TRAILER_TRUCK")) or weight == 0:
        return (0.0, 0.0)
    harness_rear = float_field(bin_spec, "HARNESS_REAR_AXLE_DISTANCE")
    if harness_rear <= 0:
        return (0.0, 0.0)
    center = weighted_sum / weight
    center_to_rear = (
        float_field(bin_spec, "TRAILER_START_HARNESS_DISTANCE") + harness_rear - center
    )
    harness_weight = (
        weight * center_to_rear
        + float_field(bin_spec, "EMPTY_TRAILER_WEIGHT")
        * float_field(bin_spec, "TRAILER_GRAVITY_CENTER_REAR_AXLE_DISTANCE")
    ) / harness_rear
    rear = weight + float_field(bin_spec, "EMPTY_TRAILER_WEIGHT") - harness_weight
    front_middle = float_field(bin_spec, "FRONT_AXLE_MIDDLE_AXLE_DISTANCE")
    middle = 0.0
    if front_middle > 0:
        middle = (
            float_field(bin_spec, "TRACTOR_WEIGHT")
            * float_field(bin_spec, "FRONT_AXLE_TRACTOR_GRAVITY_CENTER_DISTANCE")
            + harness_weight * float_field(bin_spec, "FRONT_AXLE_HARNESS_DISTANCE")
        ) / front_middle
    return middle, rear


def intersects(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return all(
        left[axis] < right[axis] + right[f"d{axis}"]
        and right[axis] < left[axis] + left[f"d{axis}"]
        for axis in ("x", "y", "z")
    )


def validate_certificate(
    case: Case,
    items_path: Path,
    bins_path: Path,
    certificate: Path,
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    item_specs = {row["ID"]: row for row in read_csv(items_path)}
    bin_specs = {row["ID"]: row for row in read_csv(bins_path)}
    rows = read_csv(certificate)
    bin_rows = [row for row in rows if row["TYPE"] == "BIN"]
    item_rows = [row for row in rows if row["TYPE"] == "ITEM"]
    pattern_bins: dict[str, list[str]] = {}
    physical_bin_specs: dict[str, dict[str, str]] = {}
    used_cost = 0.0
    for index, row in enumerate(bin_rows):
        spec = bin_specs.get(row["ID"])
        if spec is None:
            errors.append(f"unknown bin type {row['ID']}")
            continue
        reported = tuple(float(row[axis]) for axis in ("LX", "LY", "LZ"))
        expected = tuple(float(spec[axis]) for axis in ("X", "Y", "Z"))
        if reported != expected:
            errors.append(f"bin {row['ID']} dimensions {reported} differ from {expected}")
        copies = int(row["COPIES"])
        refs = [f"pattern-{row['BIN']}-row-{index}-copy-{copy}" for copy in range(copies)]
        pattern_bins[row["BIN"]] = refs
        for ref in refs:
            physical_bin_specs[ref] = spec
        used_cost += float_field(spec, "COST") * copies

    placements: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    stacks: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row_index, row in enumerate(item_rows):
        spec = item_specs.get(row["ID"])
        if spec is None:
            errors.append(f"unknown item type {row['ID']}")
            continue
        bins = pattern_bins.get(row["BIN"], [])
        if int(row["COPIES"]) != len(bins):
            errors.append(f"item row {row_index} copies do not match bin pattern copies")
            continue
        oriented = tuple(float(row[axis]) for axis in ("LX", "LY", "LZ"))
        original = tuple(float(spec[axis]) for axis in ("X", "Y", "Z"))
        permitted = {
            tuple(original[index] for index in order)
            for name, order in ROTATIONS.items()
            if spec.get(f"ROTATION_{name}") == "1"
        }
        if oriented not in permitted:
            errors.append(f"item {row['ID']} dimensions {oriented} are not a permitted rotation")
        for copy, bin_ref in enumerate(bins):
            placement = {
                "ref": f"{row['ID']}:{row_index}:{copy}",
                "item_id": row["ID"],
                "bin_ref": bin_ref,
                "stack": row["STACK"],
                "x": float(row["X"]),
                "y": float(row["Y"]),
                "z": float(row["Z"]),
                "dx": float(row["LX"]),
                "dy": float(row["LY"]),
                "dz": float(row["LZ"]),
                "weight": float_field(spec, "WEIGHT"),
                "group": int(float_field(spec, "GROUP_ID")),
                "nesting": float_field(spec, "NESTING_HEIGHT"),
                "max_stack": int(float_field(spec, "MAXIMUM_STACKABILITY", float("inf"))) if spec.get("MAXIMUM_STACKABILITY") not in (None, "") else None,
                "max_weight_above": float_field(spec, "MAXIMUM_WEIGHT_ABOVE", float("inf")),
            }
            placements.append(placement)
            stacks[(bin_ref, row["STACK"])].append(placement)
            counts[row["ID"]] += 1

    for placement in placements:
        bin_spec = physical_bin_specs[placement["bin_ref"]]
        for axis, source_axis in (("x", "X"), ("y", "Y"), ("z", "Z")):
            if placement[axis] < 0 or placement[axis] + placement[f"d{axis}"] > float(bin_spec[source_axis]):
                errors.append(f"{placement['ref']} is out of bounds on {axis}")
    for i, left in enumerate(placements):
        for right in placements[i + 1:]:
            if left["bin_ref"] != right["bin_ref"] or left["stack"] == right["stack"]:
                continue
            if intersects(left, right):
                errors.append(f"{left['ref']} overlaps {right['ref']}")

    for stack_ref, stack in stacks.items():
        ordered = sorted(stack, key=lambda placement: placement["z"])
        limits = [placement["max_stack"] for placement in ordered if placement["max_stack"] is not None]
        if limits and len(ordered) > min(limits):
            errors.append(f"stack {stack_ref} has {len(ordered)} items, limit {min(limits)}")
        for index, placement in enumerate(ordered):
            weight_above = sum(item["weight"] for item in ordered[index + 1:])
            if weight_above > placement["max_weight_above"] + 1e-7:
                errors.append(
                    f"{placement['ref']} has weight above {weight_above}, limit {placement['max_weight_above']}"
                )
            if index:
                previous = ordered[index - 1]
                expected_z = previous["z"] + previous["dz"] - placement["nesting"]
                if placement["z"] != expected_z:
                    errors.append(
                        f"{placement['ref']} starts at z={placement['z']}, expected nested z={expected_z}"
                    )

    for item_id, spec in item_specs.items():
        required = int(spec["COPIES"])
        if counts[item_id] != required and case.expect_complete:
            errors.append(f"item {item_id}: placed {counts[item_id]}, required {required}")
    if case.expect_complete and len(placements) != case.expected_items:
        errors.append(f"placed {len(placements)}, required {case.expected_items}")
    if not case.expect_complete and len(placements) == case.expected_items:
        errors.append("case expected infeasibility but returned a complete solution")
    if case.expected_bins is not None and len(physical_bin_specs) != case.expected_bins:
        errors.append(f"used {len(physical_bin_specs)} bins, expected {case.expected_bins}")
    if case.expected_cost is not None and used_cost != case.expected_cost:
        errors.append(f"cost {used_cost}, expected {case.expected_cost}")

    axle_results: dict[str, Any] = {}
    for bin_ref, bin_spec in physical_bin_specs.items():
        selected = [placement for placement in placements if placement["bin_ref"] == bin_ref]
        weight = sum(placement["weight"] for placement in selected)
        weighted_sum = sum((placement["x"] + placement["dx"] / 2) * placement["weight"] for placement in selected)
        middle, rear = axle_weights(bin_spec, weighted_sum, weight)
        middle_limit = float_field(bin_spec, "MIDDLE_AXLE_MAXIMUM_WEIGHT", float("inf"))
        rear_limit = float_field(bin_spec, "REAR_AXLE_MAXIMUM_WEIGHT", float("inf"))
        axle_results[bin_ref] = {
            "middle": middle,
            "middle_limit": middle_limit,
            "rear": rear,
            "rear_limit": rear_limit,
        }
        if middle > middle_limit + 1e-7 or rear > rear_limit + 1e-7:
            errors.append(f"bin {bin_ref} violates axle limits")

    unloading_positions: dict[int, list[float]] = defaultdict(list)
    for placement in placements:
        unloading_positions[placement["group"]].append(placement["x"])
    if "increasing-x" in case.extra_args and len(unloading_positions) > 1:
        ordered_groups = sorted(unloading_positions)
        for left, right in zip(ordered_groups, ordered_groups[1:]):
            if min(unloading_positions[left]) < max(unloading_positions[right]):
                errors.append(f"higher unloading group {right} is not closer to the x=0 exit than {left}")

    return errors, {
        "placements": len(placements),
        "bins_used": len(physical_bin_specs),
        "used_cost": used_cost,
        "axle_weights": axle_results,
        "unloading_x_by_group": {str(key): value for key, value in unloading_positions.items()},
    }


def run_case(case: Case, binary: Path, data_dir: Path, work_dir: Path) -> dict[str, Any]:
    items = data_dir / case.items
    bins = data_dir / case.bins
    output = work_dir / f"{case.name}.json"
    certificate = work_dir / f"{case.name}.csv"
    stdout = work_dir / f"{case.name}.stdout"
    stderr = work_dir / f"{case.name}.stderr"
    resources = work_dir / f"{case.name}.resources.txt"
    command = [
        "/usr/bin/time", "-v", "-o", str(resources),
        str(binary), "--items", str(items), "--bins", str(bins),
        "--objective", case.objective, "--time-limit", "10", "--memory-limit", "1024",
        "--verbosity-level", "0", "--only-write-at-the-end",
        "--output", str(output), "--certificate", str(certificate), *case.extra_args,
    ]
    started = perf_counter()
    completed = subprocess.run(command, text=True, capture_output=True, timeout=25)
    wall = perf_counter() - started
    stdout.write_text(completed.stdout)
    stderr.write_text(completed.stderr)
    errors: list[str] = []
    metrics: dict[str, Any] = {}
    if completed.returncode != 0 or not output.exists() or not certificate.exists():
        errors.append("solver did not produce both output and certificate")
    else:
        errors, metrics = validate_certificate(case, items, bins, certificate)
    return {
        "case": case.name,
        "status": "PASS" if not errors else "FAIL",
        "expected_complete": case.expect_complete,
        "returncode": completed.returncode,
        "wall_time_s": wall,
        "command": command,
        "items_sha256": sha256(items),
        "bins_sha256": sha256(bins),
        "stderr": completed.stderr,
        "validation_errors": errors,
        **metrics,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    args = parser.parse_args()
    cases = (
        Case("heterogeneous_cost", "heterogeneous_items.csv", "heterogeneous_bins.csv", "variable-sized-bin-packing", 2, 1, 10),
        Case("maximum_weight_above", "stack_items.csv", "stack_bins.csv", "bin-packing", 3, 1),
        Case("maximum_stack_count", "stack_count_items.csv", "stack_count_bins.csv", "bin-packing", 3, 2),
        Case("nesting_height", "nesting_items.csv", "nesting_bins.csv", "bin-packing", 2, 1),
        Case("axle_normal", "axle_realistic_items.csv", "axle_normal_bins.csv", "bin-packing", 1, 1),
        Case("axle_boundary_regression", "axle_items.csv", "axle_bins.csv", "bin-packing", 1, 0, expect_complete=False),
        Case("axle_infeasible", "axle_realistic_items.csv", "axle_infeasible_bins.csv", "bin-packing", 1, 0, expect_complete=False),
        Case("unloading_none", "unloading_items.csv", "unloading_bins.csv", "bin-packing", 2, 1),
        Case("unloading_increasing_x", "unloading_items.csv", "unloading_bins.csv", "bin-packing", 2, 1, extra_args=("--unloading-constraint", "increasing-x")),
    )
    args.raw_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="boxstacks-suite-") as temporary:
        temporary_path = Path(temporary)
        records = [run_case(case, args.binary, args.data_dir, temporary_path) for case in cases]
        for path in temporary_path.iterdir():
            path.replace(args.raw_dir / path.name)
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(json.dumps({
        "schema_version": 1,
        "suite": "packingsolver-boxstacks-constraints/1",
        "engine": "HansBug/packingsolver",
        "source_commit": "d953148b8f710c06fa6c410949b7272f9e36327b",
        "binary_sha256": sha256(args.binary),
        "parameters": {"time_limit_s": 10, "memory_limit_mib": 1024, "thread_limit": "NOT_EXPOSED_BY_CLI"},
        "suite_status": "PASS" if all(record["status"] == "PASS" for record in records) else "FAIL",
        "records": records,
    }, indent=2) + "\n")
    if any(record["status"] != "PASS" for record in records):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
