#!/usr/bin/env python3
"""Independently validate normalized cross-language campaign certificates."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = ROOT / "raw" / "experiments" / "campaign"
RESULT_ROOT = ROOT / "results" / "campaign"
EPSILON = 1e-8


def close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=EPSILON, abs_tol=EPSILON)


def same_dimensions(left: list[float], right: list[float]) -> bool:
    return all(close(a, b) for a, b in zip(left, right))


def intersects(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return all(
        left["position"][axis] < right["position"][axis] + right["size"][axis] - EPSILON
        and right["position"][axis] < left["position"][axis] + left["size"][axis] - EPSILON
        for axis in range(3)
    )


def read_exitcode(path: Path) -> int | None:
    try:
        return int(path.read_text().strip())
    except (FileNotFoundError, ValueError):
        return None


def validate_payload(payload: dict[str, Any], process_exitcode: int) -> dict[str, Any]:
    scenario = payload["scenario"]
    items = {item["id"]: item for item in payload["items"]}
    bins = {bin_spec["id"]: bin_spec for bin_spec in payload["bins"]}
    placements = payload.get("placements", [])
    unplaced = payload.get("unplaced", [])
    errors: list[str] = []

    item_counts = Counter(placement["item_id"] for placement in placements)
    duplicate_ids = sorted(item_id for item_id, count in item_counts.items() if count > 1)
    unknown_ids = sorted(item_id for item_id in item_counts if item_id not in items)
    unknown_bins = sorted({p["bin_id"] for p in placements if p["bin_id"] not in bins})
    if duplicate_ids:
        errors.append(f"duplicate placement item IDs: {duplicate_ids}")
    if unknown_ids:
        errors.append(f"unknown placement item IDs: {unknown_ids}")
    if unknown_bins:
        errors.append(f"unknown placement bin IDs: {unknown_bins}")

    overlap_pairs: list[list[str]] = []
    boundary_violations: list[str] = []
    orientation_violations: list[str] = []
    by_bin: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for placement in placements:
        item_spec = items.get(placement["item_id"])
        bin_spec = bins.get(placement["bin_id"])
        if item_spec is None or bin_spec is None:
            continue
        position = placement["position"]
        size = placement["size"]
        if any(not math.isfinite(float(value)) for value in [*position, *size]):
            boundary_violations.append(placement["item_id"])
            continue
        if any(float(value) < -EPSILON for value in position) or any(float(value) <= 0 for value in size):
            boundary_violations.append(placement["item_id"])
        elif any(position[axis] + size[axis] > bin_spec["size"][axis] + EPSILON for axis in range(3)):
            boundary_violations.append(placement["item_id"])
        if not same_dimensions(sorted(size), sorted(item_spec["size"])):
            orientation_violations.append(f"{placement['item_id']}: not an axis permutation")
        allowed_orientations = item_spec.get("allowed_orientations")
        if allowed_orientations and placement.get("rotation") not in allowed_orientations:
            orientation_violations.append(
                f"{placement['item_id']}: orientation {placement.get('rotation')} not in {allowed_orientations}"
            )
        if item_spec["orientation_requirement"] == "fixed" and not same_dimensions(size, item_spec["size"]):
            orientation_violations.append(f"{placement['item_id']}: fixed orientation changed")
        by_bin[placement["bin_id"]].append(placement)

    for bin_id, placed in by_bin.items():
        for index, left in enumerate(placed):
            for right in placed[index + 1 :]:
                if intersects(left, right):
                    overlap_pairs.append([left["item_id"], right["item_id"]])
        weight = sum(float(item["weight"]) for item in placed)
        if weight > float(bins[bin_id]["max_weight"]) + EPSILON:
            errors.append(f"bin {bin_id} weight {weight:g} > {bins[bin_id]['max_weight']:g}")

    if boundary_violations:
        errors.append(f"boundary violations: {sorted(set(boundary_violations))}")
    if orientation_violations:
        errors.append(f"orientation violations: {orientation_violations}")
    if overlap_pairs:
        errors.append(f"overlap pairs: {overlap_pairs[:20]}")

    placed_ids = set(item_counts)
    expected_unplaced = set(items) - placed_ids
    reported_unplaced = set(unplaced)
    if reported_unplaced != expected_unplaced:
        errors.append(
            f"unplaced mismatch: reported={sorted(reported_unplaced)} expected={sorted(expected_unplaced)}"
        )
    if placed_ids & reported_unplaced:
        errors.append(f"IDs both placed and unplaced: {sorted(placed_ids & reported_unplaced)}")

    rotation_used = any(
        not same_dimensions(placement["size"], items[placement["item_id"]]["size"])
        for placement in placements
        if placement["item_id"] in items
    )
    bins_used = sorted(by_bin)
    total_cost = sum(float(bins[bin_id]["cost"]) for bin_id in bins_used if bin_id in bins)
    complete = len(placed_ids) == len(items) and not duplicate_ids and not unknown_ids
    geometry_valid = not errors

    if process_exitcode != 0:
        expected_behavior_pass = False
    elif scenario == "rotation_forbidden":
        expected_behavior_pass = geometry_valid and not placements and len(unplaced) == 1
    elif payload["capability_status"] == "NOT_SUPPORTED":
        expected_behavior_pass = geometry_valid and not placements
    else:
        expected_behavior_pass = geometry_valid and complete
        if scenario == "rotation_required":
            expected_behavior_pass = expected_behavior_pass and rotation_used
        elif scenario.startswith("heterogeneous_"):
            expected_behavior_pass = expected_behavior_pass and close(total_cost, 10.0) and len(bins_used) == 1

    return {
        "scenario": scenario,
        "algorithm": payload.get("algorithm"),
        "parameters": payload.get("parameters", {}),
        "process_exitcode": process_exitcode,
        "capability_status": payload["capability_status"],
        "capability_note": payload["capability_note"],
        "geometry_and_constraints_valid": geometry_valid,
        "complete": complete,
        "expected_behavior_pass": expected_behavior_pass,
        "items_total": len(items),
        "items_placed": len(placements),
        "items_unplaced": len(unplaced),
        "bins_used": len(bins_used),
        "total_cost": total_cost,
        "rotation_used": rotation_used,
        "validation_errors": errors,
        "library_elapsed_ms": payload.get("elapsed_ms"),
    }


def validate_directory(name: str) -> dict[str, Any]:
    raw_dir = RAW_ROOT / name
    scenarios: dict[str, Any] = {}
    identity: dict[str, Any] = {"raw_directory": str(raw_dir.relative_to(ROOT))}
    scenario_names = sorted(path.name.removesuffix(".stdout.json") for path in raw_dir.glob("*.stdout.json"))
    for scenario in scenario_names:
        output_path = raw_dir / f"{scenario}.stdout.json"
        process_exitcode = read_exitcode(raw_dir / f"{scenario}.exitcode")
        if process_exitcode is None:
            scenarios[scenario] = {"scenario": scenario, "process_exitcode": None, "parse_error": "missing exit code"}
            continue
        try:
            payload = json.loads(output_path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            scenarios[scenario] = {
                "scenario": scenario,
                "process_exitcode": process_exitcode,
                "parse_error": str(error),
                "expected_behavior_pass": False,
            }
            continue
        if not identity.get("library"):
            identity.update({key: payload.get(key) for key in ("library", "commit", "language", "toolchain", "algorithm")})
        scenarios[scenario] = validate_payload(payload, process_exitcode)

    result = {
        **identity,
        "build_exitcode": read_exitcode(raw_dir / "build.exitcode"),
        "upstream_test_exitcode": read_exitcode(raw_dir / "upstream-test.exitcode"),
        "scenarios": scenarios,
        "all_expected_behaviors_pass": bool(scenarios)
        and all(result.get("expected_behavior_pass", False) for result in scenarios.values()),
    }
    output_dir = RESULT_ROOT / name
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "results.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directories", nargs="*", help="raw campaign directory names")
    arguments = parser.parse_args()
    names = arguments.directories or sorted(
        path.name
        for path in RAW_ROOT.glob("crosslang_*")
        if not path.name.endswith("_thpack9") and any(path.glob("*.stdout.json"))
    )
    summary = {}
    for name in names:
        result = validate_directory(name)
        summary[name] = {
            "library": result.get("library"),
            "all_expected_behaviors_pass": result["all_expected_behaviors_pass"],
            "scenario_count": len(result["scenarios"]),
        }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
