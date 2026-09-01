#!/usr/bin/env python3
"""Run non-PackingSolver implementations on the constraint conformance fixtures.

The libraries in this runner intentionally receive a geometry projection.  The
source constraint fields are retained in the canonical fixture and are checked
again by this process, so a library that ignores a hard field is reported as a
constraint violation rather than as a successful native run.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = ROOT / "benchmarks" / "data" / "packingsolver"
RESULTS = ROOT / "results" / "comprehensive" / "runs" / "constraint-adapters-b12-b13-b15-b16-b17-b18-b30.jsonl"
RAW_ROOT = ROOT / "raw" / "experiments" / "comprehensive" / "constraint-adapters"
EXTENSION_FIXTURE = ROOT / "benchmarks" / "data" / "comprehensive" / "constraint-extension-fixture.json"
B30_FIXTURE = ROOT / "benchmarks" / "data" / "comprehensive" / "b30-baytp-fixture.json"
B31_FIXTURE = ROOT / "benchmarks" / "data" / "comprehensive" / "b31-mixed-sku-fixture.json"
RUNNER = Path(__file__).resolve()
sys.path.insert(0, str(ROOT / "benchmarks"))
sys.path.insert(0, str(ROOT / "benchmarks" / "comprehensive"))

from model import load_catalogs, validate_run_record  # noqa: E402
from run_constraint_gauntlet import axle_weights, read_csv, sha256  # noqa: E402


PYTHON = ROOT / ".venv" / "bin" / "python"
if not PYTHON.exists():
    PYTHON = Path(sys.executable)
GO = Path("/tmp/packing-crosslang-go-build/crosslang_go_bp3d")
RUST = Path("/tmp/packing-crosslang-u-build/target/release/crosslang-rust-unesting")

CASE_FILES: dict[str, tuple[str, str, bool]] = {
    "B12/ROTATION_REQUIRED": ("rotation_allowed_items.csv", "rotation_bins.csv", True),
    "B12/ROTATION_FORBIDDEN": ("rotation_forbidden_items.csv", "rotation_bins.csv", False),
    "B13/WEIGHT_LIMIT": ("weight_items.csv", "weight_bins.csv", True),
    "B15/AXLE_NORMAL": ("axle_realistic_items.csv", "axle_normal_bins.csv", True),
    "B15/AXLE_BOUNDARY": ("axle_items.csv", "axle_bins.csv", False),
    "B15/AXLE_INFEASIBLE": ("axle_realistic_items.csv", "axle_infeasible_bins.csv", False),
    "B17/UNLOADING_NONE": ("unloading_items.csv", "unloading_bins.csv", True),
    "B17/INCREASING_X": ("unloading_items.csv", "unloading_bins.csv", True),
}

EXTENSION_CASES = {"B16/KEEP_OUT", "B18/SEGREGATION"}
B31_CASES = {"B31/FLAT_MIXED", "B31/STACKABLE", "B31/WEIGHT_INFEASIBLE"}

RUST_STRATEGIES = {
    "rust_extreme_point": "extremepoint",
    "rust_layer": "bottomleftfill",
    "rust_ga": "ga",
    "rust_brkga": "brkga",
    "rust_sa": "sa",
}


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def float_value(row: dict[str, str], field: str, default: float = 0.0) -> float:
    value = row.get(field)
    return default if value in (None, "") else float(value)


def rotation_sizes(row: dict[str, str]) -> set[tuple[float, float, float]]:
    original = tuple(float(row[axis]) for axis in ("X", "Y", "Z"))
    orders = {
        "ROTATION_XYZ": (0, 1, 2),
        "ROTATION_YXZ": (1, 0, 2),
        "ROTATION_ZYX": (2, 1, 0),
        "ROTATION_YZX": (1, 2, 0),
        "ROTATION_XZY": (0, 2, 1),
        "ROTATION_ZXY": (2, 0, 1),
    }
    return {
        tuple(original[index] for index in order)
        for flag, order in orders.items()
        if row.get(flag) == "1"
    }


def load_case(key: str) -> tuple[dict[str, Any], dict[str, dict[str, str]], dict[str, dict[str, str]], str, str]:
    if key in B31_CASES:
        fixture = json.loads(B31_FIXTURE.read_text(encoding="utf-8"))
        case = next(case for case in fixture["cases"] if case["id"] == key)
        item_meta: dict[str, dict[str, str]] = {}
        for item in case["items"]:
            item_meta[item["id"]] = {
                "ID": item["id"],
                "X": str(item["size"][0]), "Y": str(item["size"][1]), "Z": str(item["size"][2]),
                "WEIGHT": str(item.get("weight", 0.0)), "COPIES": "1", "GROUP_ID": "0",
                "ROTATION_XYZ": "1", "ROTATION_YXZ": "1", "ROTATION_ZYX": "1",
                "ROTATION_YZX": "1", "ROTATION_XZY": "1", "ROTATION_ZXY": "1",
            }
        pallet = case["pallet"]
        bin_meta = {
            pallet["id"]: {
                "ID": pallet["id"], "X": str(pallet["size"][0]), "Y": str(pallet["size"][1]), "Z": str(pallet["size"][2]),
                "COPIES": "1", "COST": str(pallet.get("cost", 1.0)),
                "MAXIMUM_WEIGHT": str(pallet.get("max_weight", float("inf"))),
            }
        }
        spec = {
            "scenario": key.replace("/", "_").lower(), "benchmark_id": "B31", "problem_variant": key.split("/", 1)[1],
            "items": case["items"], "bins": [{"id": pallet["id"], "type_id": pallet["id"], "size": pallet["size"],
                                                   "max_weight": pallet.get("max_weight", float("inf")), "cost": pallet.get("cost", 1.0)}],
            "expected_complete": bool(case["expected_complete"]), "stack_rules": case["rules"],
            "source_files": {str(B31_FIXTURE.relative_to(ROOT)): sha256(B31_FIXTURE)},
        }
        return spec, item_meta, bin_meta, str(B31_FIXTURE), str(B31_FIXTURE)
    if key == "B30/SHELF_SEQUENCE":
        fixture = json.loads(B30_FIXTURE.read_text(encoding="utf-8"))
        case = fixture["case"]
        item_meta = {}
        for item in case["items"]:
            item_meta[item["id"]] = {
                "ID": item["type_id"], "X": str(item["size"][0]), "Y": str(item["size"][1]), "Z": str(item["size"][2]),
                "WEIGHT": str(item.get("weight", 0)), "COPIES": "1",
                "ROTATION_XYZ": "1", "ROTATION_YXZ": "1", "ROTATION_ZYX": "1",
                "ROTATION_YZX": "1", "ROTATION_XZY": "1", "ROTATION_ZXY": "1", "GROUP_ID": "0",
            }
        bay = case["bay"]
        bin_meta = {bay["id"]: {"ID": bay["id"], "X": str(bay["size"][0]), "Y": str(bay["size"][1]), "Z": str(bay["size"][2]), "COPIES": "1", "COST": "1", "MAXIMUM_WEIGHT": "100000"}}
        spec = {
            "scenario": "b30_shelf_sequence", "benchmark_id": "B30", "problem_variant": "SHELF_SEQUENCE",
            "items": case["items"], "bins": [{"id": bay["id"], "type_id": bay["id"], "size": bay["size"], "max_weight": bay.get("max_weight", 100000), "cost": bay.get("cost", 1)}],
            "expected_complete": bool(case["expected_complete"]), "shelves": case["shelves"],
            "source_files": {str(B30_FIXTURE.relative_to(ROOT)): sha256(B30_FIXTURE), **{f"source/{name}": value for name, value in fixture["source"]["source_sha256"].items()}},
        }
        return spec, item_meta, bin_meta, str(B30_FIXTURE), str(B30_FIXTURE)
    if key in EXTENSION_CASES:
        extension = json.loads(EXTENSION_FIXTURE.read_text(encoding="utf-8"))
        case = extension["cases"][key]
        item_meta = {}
        for item in case["items"]:
            item_meta[item["id"]] = {
                "ID": item["type_id"], "X": str(item["size"][0]), "Y": str(item["size"][1]), "Z": str(item["size"][2]),
                "WEIGHT": str(item.get("weight", 0)), "COPIES": "1",
                "ROTATION_XYZ": "1", "ROTATION_YXZ": "1", "ROTATION_ZYX": "1",
                "ROTATION_YZX": "1", "ROTATION_XZY": "1", "ROTATION_ZXY": "1",
                "GROUP_ID": "0",
            }
        bin_meta = {item["id"]: {"ID": item["id"], "X": str(item["size"][0]), "Y": str(item["size"][1]), "Z": str(item["size"][2]), "COPIES": "1", "COST": str(item.get("cost", 0)), "MAXIMUM_WEIGHT": str(item.get("max_weight", 0))} for item in case["bins"]}
        spec = {
            "scenario": key.replace("/", "_").lower(), "benchmark_id": key.split("/", 1)[0], "problem_variant": key.split("/", 1)[1],
            "items": case["items"], "bins": case["bins"], "expected_complete": bool(case["expected_complete"]),
            "obstacles": case.get("obstacles", []), "incompatible_groups": case.get("incompatible_groups", []),
            "source_files": {str(EXTENSION_FIXTURE.relative_to(ROOT)): sha256(EXTENSION_FIXTURE)},
        }
        return spec, item_meta, bin_meta, str(EXTENSION_FIXTURE), str(EXTENSION_FIXTURE)
    items_name, bins_name, expected_complete = CASE_FILES[key]
    item_path = DATA_ROOT / items_name
    bin_path = DATA_ROOT / bins_name
    item_rows = read_csv(item_path)
    bin_rows = read_csv(bin_path)
    items: list[dict[str, Any]] = []
    item_meta: dict[str, dict[str, str]] = {}
    for row in item_rows:
        for copy in range(int(float_value(row, "COPIES", 1))):
            item_id = f"{row['ID']}:{copy}"
            item = {
                "id": item_id,
                "type_id": row["ID"],
                "size": [float(row[axis]) for axis in ("X", "Y", "Z")],
                "weight": float_value(row, "WEIGHT"),
                "orientation_requirement": "any",
            }
            items.append(item)
            item_meta[item_id] = row
    bins: list[dict[str, Any]] = []
    bin_meta: dict[str, dict[str, str]] = {}
    for row in bin_rows:
        for copy in range(int(float_value(row, "COPIES", 1))):
            bin_id = f"{row['ID']}:{copy}"
            bin_spec = {
                "id": bin_id,
                "type_id": row["ID"],
                "size": [float(row[axis]) for axis in ("X", "Y", "Z")],
                "max_weight": float_value(row, "MAXIMUM_WEIGHT", float("inf")),
                "cost": float_value(row, "COST"),
            }
            bins.append(bin_spec)
            bin_meta[bin_id] = row
    scenario = key.replace("/", "_").lower()
    spec = {
        "scenario": scenario,
        "benchmark_id": key.split("/", 1)[0],
        "problem_variant": key.split("/", 1)[1],
        "items": items,
        "bins": bins,
        "expected_complete": expected_complete,
        "source_files": {
            str(item_path.relative_to(ROOT)): sha256(item_path),
            str(bin_path.relative_to(ROOT)): sha256(bin_path),
        },
    }
    return spec, item_meta, bin_meta, str(item_path), str(bin_path)


def python_input(spec: dict[str, Any], item_meta: dict[str, dict[str, str]]) -> dict[str, Any]:
    # The worker's three vertical flags are only used for capability checks;
    # this campaign deliberately asks for the all-rotation geometry projection.
    grouped: dict[str, dict[str, Any]] = {}
    for item in spec["items"]:
        grouped.setdefault(item["type_id"], {
            "type_id": item["type_id"],
            "size": [int(round(value)) for value in item["size"]],
            "allowed_vertical_dimensions": [1, 1, 1],
            "copies": 0,
        })["copies"] += 1
    item_types = list(grouped.values())
    return {
        "instance": {
            "family": "CONSTRAINT_ADAPTER",
            "instance_id": 1,
            "problem_kind": "multi_container_bin_packing" if len(spec["bins"]) > 1 else "single_container_knapsack",
            "objective": "minimize_bins",
            "container": [int(round(value)) for value in spec["bins"][0]["size"]],
            "seed": 42,
            "source_line_errors": [],
            "item_types": item_types,
        }
    }


def normalize_placements(payload: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for raw in payload.get("placements", []):
        if all(key in raw for key in ("x", "y", "z", "dx", "dy", "dz")):
            position = [float(raw[key]) for key in ("x", "y", "z")]
            size = [float(raw[key]) for key in ("dx", "dy", "dz")]
        else:
            position = [float(value) for value in raw.get("position", [0, 0, 0])]
            size = [float(value) for value in raw.get("size", [0, 0, 0])]
        output.append({
            "item_id": str(raw.get("item_id", "")),
            "bin_id": str(raw.get("bin_id", "")),
            "position": position,
            "size": size,
        })
    return output


def resolve_bin(raw_id: str, bins: list[dict[str, Any]]) -> str | None:
    ids = [str(row["id"]) for row in bins]
    if raw_id in ids:
        return raw_id
    aliases: dict[str, str] = {}
    for index, row in enumerate(bins):
        aliases[str(index)] = str(row["id"])
        aliases[f"bin:{index}"] = str(row["id"])
        aliases[f"bin-{index:03d}"] = str(row["id"])
    return aliases.get(raw_id)


def intersects(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return all(
        left["position"][axis] < right["position"][axis] + right["size"][axis]
        and right["position"][axis] < left["position"][axis] + left["size"][axis]
        for axis in range(3)
    )


def independent_validate(
    spec: dict[str, Any],
    item_meta: dict[str, dict[str, str]],
    bin_meta: dict[str, dict[str, str]],
    payload: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    placements = normalize_placements(payload)
    errors: list[str] = []
    geometry_errors: list[str] = []
    constraint_errors: list[str] = []
    item_ids = {str(item["id"]) for item in spec["items"]}
    seen: set[str] = set()
    by_bin: dict[str, list[dict[str, Any]]] = {}
    for index, placement in enumerate(placements):
        item_id = placement["item_id"]
        if item_id not in item_ids:
            geometry_errors.append(f"placement {index}: unknown item {item_id}")
            continue
        if item_id in seen:
            geometry_errors.append(f"duplicate item {item_id}")
        seen.add(item_id)
        bin_id = resolve_bin(placement["bin_id"], spec["bins"])
        if bin_id is None:
            geometry_errors.append(f"{item_id}: unknown bin {placement['bin_id']}")
            continue
        placement["bin_id"] = bin_id
        by_bin.setdefault(bin_id, []).append(placement)
        source_item = item_meta[item_id]
        size = tuple(placement["size"])
        if tuple(round(value, 7) for value in size) not in {
            tuple(round(value, 7) for value in allowed)
            for allowed in rotation_sizes(source_item)
        }:
            constraint_errors.append(f"{item_id}: forbidden source rotation {size}")
        bin_spec = next(row for row in spec["bins"] if row["id"] == bin_id)
        for axis in range(3):
            if placement["position"][axis] < -1e-7 or placement["position"][axis] + size[axis] > bin_spec["size"][axis] + 1e-7:
                geometry_errors.append(f"{item_id}: out of bounds on axis {axis}")
    for bin_id, rows in by_bin.items():
        for left_index, left in enumerate(rows):
            for right in rows[left_index + 1:]:
                if intersects(left, right):
                    geometry_errors.append(f"{left['item_id']} overlaps {right['item_id']} in {bin_id}")
        bin_row = next(row for row in spec["bins"] if row["id"] == bin_id)
        total_weight = sum(float_value(item_meta[row["item_id"]], "WEIGHT") for row in rows)
        max_weight = float(bin_row["max_weight"])
        if total_weight > max_weight + 1e-7:
            constraint_errors.append(f"{bin_id}: weight {total_weight} exceeds {max_weight}")
        source_bin = bin_meta[bin_id]
        weighted_sum = sum((row["position"][0] + row["size"][0] / 2) * float_value(item_meta[row["item_id"]], "WEIGHT") for row in rows)
        middle, rear = axle_weights(source_bin, weighted_sum, total_weight)
        if middle > float_value(source_bin, "MIDDLE_AXLE_MAXIMUM_WEIGHT", float("inf")) + 1e-7:
            constraint_errors.append(f"{bin_id}: middle axle {middle} exceeds limit")
        if rear > float_value(source_bin, "REAR_AXLE_MAXIMUM_WEIGHT", float("inf")) + 1e-7:
            constraint_errors.append(f"{bin_id}: rear axle {rear} exceeds limit")
        for obstacle in spec.get("obstacles", []):
            obstacle_row = {"position": obstacle["position"], "size": obstacle["size"]}
            if any(intersects(row, obstacle_row) for row in rows):
                constraint_errors.append(f"{bin_id}: keep-out {obstacle['id']} intersects cargo")
        groups = {str(next(item for item in spec["items"] if item["id"] == row["item_id"]).get("compatibility_group", "")) for row in rows}
        for left, right in spec.get("incompatible_groups", []):
            if left in groups and right in groups:
                constraint_errors.append(f"{bin_id}: incompatible groups {left}/{right} share a compartment")
    if spec["benchmark_id"] == "B30":
        # BAYTP is a shelf sequence problem: a placement must sit on a declared
        # shelf top and remain within that shelf's side/depth clearances.
        shelves = spec.get("shelves", [])
        bin_spec = spec["bins"][0]
        for placement in placements:
            matching = [shelf for shelf in shelves if abs(placement["position"][1] - float(shelf["top_y"])) <= 1e-7]
            if not matching:
                constraint_errors.append(f"{placement['item_id']}: placement y={placement['position'][1]} is not a declared shelf top")
                continue
            shelf = matching[0]
            left = float(shelf["left_gap"])
            right = float(shelf["right_gap"])
            if placement["position"][0] < left - 1e-7 or placement["position"][0] + placement["size"][0] > float(bin_spec["size"][0]) - right + 1e-7:
                constraint_errors.append(f"{placement['item_id']}: shelf side gap/overhang violation")
            if placement["position"][2] < -1e-7 or placement["position"][2] + placement["size"][2] > float(bin_spec["size"][2]) + 1e-7:
                constraint_errors.append(f"{placement['item_id']}: shelf depth overhang violation")
        for shelf in shelves:
            rows = [row for row in placements if abs(row["position"][1] - float(shelf["top_y"])) <= 1e-7]
            rows.sort(key=lambda row: row["position"][0])
            for left_row, right_row in zip(rows, rows[1:]):
                gap = right_row["position"][0] - (left_row["position"][0] + left_row["size"][0])
                if gap < float(shelf["inter_gap"]) - 1e-7:
                    constraint_errors.append(f"shelf {shelf['id']}: inter-gap {gap} below {shelf['inter_gap']}")
    if spec["benchmark_id"] == "B31":
        # B31 uses the canonical y axis as pallet height.  This is a small
        # deterministic stack validator, not a material-mechanics model.
        rules = spec.get("stack_rules", {})
        max_layers = int(rules.get("max_layers", 1))
        levels = sorted({round(float(row["position"][1]), 7) for row in placements})
        if len(levels) > max_layers:
            constraint_errors.append(f"pallet has {len(levels)} layers, maximum is {max_layers}")
        item_by_id = {str(item["id"]): item for item in spec["items"]}
        max_above = float(rules.get("max_above_weight", float("inf")))
        for lower in placements:
            lower_item = item_by_id[lower["item_id"]]
            lower_top = lower["position"][1] + lower["size"][1]
            above_weight = 0.0
            for upper in placements:
                if upper is lower or upper["position"][1] < lower_top - 1e-7:
                    continue
                overlap_x = max(0.0, min(lower["position"][0] + lower["size"][0], upper["position"][0] + upper["size"][0]) - max(lower["position"][0], upper["position"][0]))
                overlap_z = max(0.0, min(lower["position"][2] + lower["size"][2], upper["position"][2] + upper["size"][2]) - max(lower["position"][2], upper["position"][2]))
                if overlap_x > 1e-7 and overlap_z > 1e-7:
                    above_weight += float(item_by_id[upper["item_id"]].get("weight", 0.0))
                    if not lower_item.get("stackable", True):
                        constraint_errors.append(f"{lower['item_id']}: non-stackable SKU has an item above it")
            if above_weight > max_above + 1e-7:
                constraint_errors.append(f"{lower['item_id']}: above weight {above_weight} exceeds {max_above}")
        min_support_ratio = float(rules.get("min_support_ratio", 1.0))
        for upper in placements:
            if upper["position"][1] <= 1e-7:
                continue
            upper_bottom = upper["position"][1]
            upper_area = upper["size"][0] * upper["size"][2]
            support_area = 0.0
            for lower in placements:
                lower_top = lower["position"][1] + lower["size"][1]
                if abs(lower_top - upper_bottom) > 1e-7:
                    continue
                overlap_x = max(0.0, min(lower["position"][0] + lower["size"][0], upper["position"][0] + upper["size"][0]) - max(lower["position"][0], upper["position"][0]))
                overlap_z = max(0.0, min(lower["position"][2] + lower["size"][2], upper["position"][2] + upper["size"][2]) - max(lower["position"][2], upper["position"][2]))
                support_area += overlap_x * overlap_z
            support_ratio = min(1.0, support_area / upper_area) if upper_area else 0.0
            if support_ratio + 1e-7 < min_support_ratio:
                constraint_errors.append(f"{upper['item_id']}: support ratio {support_ratio} below minimum")
    if spec["problem_variant"] == "INCREASING_X":
        groups: dict[int, list[float]] = {}
        for item_id in seen:
            group = int(float_value(item_meta[item_id], "GROUP_ID"))
            matching = next((row for row in placements if row["item_id"] == item_id), None)
            if matching is not None:
                groups.setdefault(group, []).append(matching["position"][0])
        ordered = sorted(groups)
        for left, right in zip(ordered, ordered[1:]):
            if min(groups[left]) < max(groups[right]) - 1e-7:
                constraint_errors.append(f"unloading group {right} is not closer to exit than {left}")
    required = len(spec["items"])
    if spec["expected_complete"] and len(seen) != required:
        constraint_errors.append(f"missing required items: {required - len(seen)}")
    errors.extend(geometry_errors)
    errors.extend(constraint_errors)
    metrics = {
        "packed_items": len(seen),
        "required_items": required,
        "bins_used": len(by_bin),
        "total_cost": sum(float(next(row for row in spec["bins"] if row["id"] == bin_id)["cost"]) for bin_id in by_bin),
        "validation_error_count": len(errors),
        "geometry_error_count": len(geometry_errors),
        "hard_violation_count": len(constraint_errors),
        "validation_errors": errors,
        "constraint_errors": constraint_errors,
        "geometry_errors": geometry_errors,
    }
    if geometry_errors:
        return "INVALID_CERTIFICATE", metrics
    if constraint_errors:
        return "CONSTRAINT_VIOLATION", metrics
    if len(seen) == required:
        return "VALID_COMPLETE", metrics
    return "VALID_PARTIAL" if seen else "NO_SOLUTION", metrics


def command_for(implementation_id: str, input_path: Path, spec: dict[str, Any]) -> list[str] | None:
    if implementation_id in {"py3dbp", "jerry"}:
        python_input_path = input_path.with_name("python-input.json")
        python_input_path.write_text(json.dumps(python_input(spec, {})) + "\n", encoding="utf-8")
        command = [str(PYTHON), str(ROOT / "benchmarks/campaign/python_thpack/worker.py"), "--library", implementation_id,
                   "--input", str(python_input_path), "--order", "descending", "--projection"]
        if implementation_id == "jerry":
            command.extend(["--jerry-fix-point", "false"])
        return command
    if implementation_id == "go_bp3d":
        return [str(GO), "--input", str(input_path)]
    if implementation_id in RUST_STRATEGIES:
        return [str(RUST), "--input", str(input_path), RUST_STRATEGIES[implementation_id], "10000"]
    return None


def run_one(implementation_id: str, spec: dict[str, Any], item_meta: dict[str, dict[str, str]], bin_meta: dict[str, dict[str, str]]) -> dict[str, Any]:
    key = f"{spec['benchmark_id']}/{spec['problem_variant']}"
    # Deterministic artifact paths make a rerun produce the same references in
    # the manifest; no random tempfile name is part of the evidence.
    work = RAW_ROOT / f"{key.replace('/', '_')}_{implementation_id}"
    work.mkdir(parents=True, exist_ok=True)
    input_path = work / "input.json"
    stdout_path = work / "stdout.log"
    stderr_path = work / "stderr.log"
    validation_path = work / "validation.json"
    input_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    command = command_for(implementation_id, input_path, spec)
    started = perf_counter()
    env = os.environ.copy()
    env.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", NUMEXPR_NUM_THREADS="1", RAYON_NUM_THREADS="1", GOMAXPROCS="1")
    if command is None or (command[0] in {str(GO), str(RUST)} and not Path(command[0]).exists()):
        run_status, solution_status, payload, stderr = "ERROR", "NO_SOLUTION", {"placements": []}, "adapter or binary unavailable"
        wall_s = 0.0
        return make_record(implementation_id, spec, run_status, solution_status, payload, stderr, wall_s, validation_path, stdout_path, stderr_path, work, item_meta, bin_meta, command)
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=20.0, env=env, check=False)
        wall_s = perf_counter() - started
        stdout, stderr = completed.stdout, completed.stderr
        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text(stderr, encoding="utf-8")
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = {"placements": []}
        solution_status, metrics = independent_validate(spec, item_meta, bin_meta, payload)
        validation_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if completed.returncode != 0 and solution_status == "NO_SOLUTION":
            run_status = "ERROR"
            solution_status = "NO_SOLUTION"
        else:
            run_status = "COMPLETED"
        return make_record(implementation_id, spec, run_status, solution_status, payload, stderr, wall_s, validation_path, stdout_path, stderr_path, work, item_meta, bin_meta, command, metrics)
    except subprocess.TimeoutExpired as exc:
        wall_s = perf_counter() - started
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text(exc.stderr or "", encoding="utf-8")
        validation = {"validation_error_count": 0, "hard_violation_count": 0, "timeout": True}
        validation_path.write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
        return make_record(implementation_id, spec, "TIME_LIMIT", "NO_SOLUTION", {"placements": []}, exc.stderr or "", wall_s, validation_path, stdout_path, stderr_path, work, item_meta, bin_meta, command, validation)


def make_record(
    implementation_id: str,
    spec: dict[str, Any],
    run_status: str,
    solution_status: str,
    payload: dict[str, Any],
    stderr: str,
    wall_s: float,
    validation_path: Path,
    stdout_path: Path,
    stderr_path: Path,
    work: Path,
    item_meta: dict[str, dict[str, str]],
    bin_meta: dict[str, dict[str, str]],
    command: list[str] | None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _, implementation_catalog = load_catalogs()
    implementation = next(row for row in implementation_catalog["implementations"] if row["id"] == implementation_id)
    if metrics is None:
        solution_status, metrics = independent_validate(spec, item_meta, bin_meta, payload)
    capability = "PROJECTION_ONLY"
    if solution_status == "VALID_COMPLETE":
        proof = "FEASIBLE"
    elif solution_status == "VALID_PARTIAL":
        proof = "FEASIBLE"
    else:
        proof = "UNKNOWN"
    if run_status in {"ERROR", "TIME_LIMIT"}:
        proof = "UNKNOWN"
    projection_removed_constraints = ["source_pose_whitelist", "payload", "axle_statics", "unloading_order"]
    if spec["benchmark_id"] == "B16":
        projection_removed_constraints.append("keep_out")
    if spec["benchmark_id"] == "B18":
        projection_removed_constraints.append("compatibility_segregation")
    if spec["benchmark_id"] == "B30":
        projection_removed_constraints.append("shelf_bay_sequence")
    if spec["benchmark_id"] == "B31":
        projection_removed_constraints.append("pallet_stack_rules")
    run_id = f"{spec['benchmark_id']}/{spec['problem_variant']}/{implementation_id}/10s/constraint-projection/rep-0"
    normalized_command = None
    if command:
        normalized_command = []
        for token in command:
            path = Path(token)
            try:
                normalized_command.append(str(path.relative_to(ROOT)))
            except ValueError:
                normalized_command.append(token)
    record = {
        "schema_version": 2,
        "protocol_version": "benchmark-protocol/3",
        "record_origin": "PROTOCOL_V3",
        "run_id": run_id,
        "benchmark_id": spec["benchmark_id"],
        "problem_variant": spec["problem_variant"],
        "instance_id": spec["scenario"],
        "implementation_id": implementation_id,
        "algorithm": implementation["algorithm"],
        "adapter": "constraint_adapters/projection_v1",
        "comparison_track": "COMPOSED",
        "problem_scope": "GEOMETRY_PROJECTION",
        "budget": {"time_limit_s": 10.0, "memory_limit_bytes": 536870912, "thread_limit": 1},
        "item_order": "DESCENDING",
        "bin_order": "CANONICAL",
        "seed": 42,
        "repetition": 0,
        "input_sha256": digest(spec),
        "input_status": "VALID",
        "capability_status": capability,
        "run_status": run_status,
        "solution_status": solution_status,
        "proof_status": proof,
        "termination_reason": "RETURNED_PROJECTION" if run_status == "COMPLETED" else run_status,
        "resources": {"wall_s": wall_s, "solver_s": None, "peak_rss_bytes": None},
        "metrics": {
            **metrics,
            "projection_removed_constraints": projection_removed_constraints,
            "projection_reason": "library adapter accepts geometry only; independent validator retains original hard fields",
            "provenance_kind": "FRESH_SOLVER_INVOCATION" if run_status != "ERROR" or command else "ADAPTER_ATTEMPT",
            "runner_sha256": sha256(RUNNER),
            "stderr_bytes": len(stderr.encode()),
            "command": normalized_command,
        },
        "artifacts": {
            "input": str((work / "input.json").relative_to(ROOT)),
            "stdout": str(stdout_path.relative_to(ROOT)),
            "stderr": str(stderr_path.relative_to(ROOT)),
            "validation": str(validation_path.relative_to(ROOT)),
        },
    }
    validate_run_record(record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", action="append", choices=("B12", "B13", "B15", "B16", "B17", "B18", "B30", "B31"))
    parser.add_argument("--output", type=Path, default=RESULTS)
    args = parser.parse_args()
    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    all_cases = list(CASE_FILES) + sorted(EXTENSION_CASES) + ["B30/SHELF_SEQUENCE"] + sorted(B31_CASES)
    selected = [key for key in all_cases if not args.benchmark or key.split("/", 1)[0] in args.benchmark]
    implementations = ["py3dbp", "jerry", "go_bp3d", *RUST_STRATEGIES]
    records: list[dict[str, Any]] = []
    for key in selected:
        spec, item_meta, bin_meta, _, _ = load_case(key)
        for implementation_id in implementations:
            records.append(run_one(implementation_id, spec, item_meta, bin_meta))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n" for record in sorted(records, key=lambda row: row["run_id"])), encoding="utf-8")
    counts = Counter((row["benchmark_id"], row["implementation_id"], row["solution_status"]) for row in records)
    print(f"wrote {len(records)} constraint adapter records to {args.output}")
    for key, value in sorted(counts.items()):
        print(" ".join(key), value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
