from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
from collections import Counter
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks"))

from comprehensive.model import canonical_json, load_catalogs, validate_run_record  # noqa: E402
from validation import Box, cumulative_weight_above, validate_aabbs  # noqa: E402


DATA_ROOT = ROOT / "benchmarks" / "data" / "packingsolver"
RUNNER_PATH = Path(__file__).resolve()
VALIDATOR_PATH = ROOT / "benchmarks" / "validation.py"
FORK_COMMIT = "d953148b8f710c06fa6c410949b7272f9e36327b"
UPSTREAM_COMMIT = "367ebfdaad11424ded3696b7dae799a30c1375d0"

ROTATIONS = {
    "XYZ": (0, 1, 2),
    "YXZ": (1, 0, 2),
    "ZYX": (2, 1, 0),
    "YZX": (1, 2, 0),
    "XZY": (0, 2, 1),
    "ZXY": (2, 0, 1),
}


CASES: dict[str, dict[str, Any]] = {
    "heterogeneous_large_cheaper": {
        "benchmark_id": "B09",
        "variant": "LARGE_CHEAPER",
        "items": "heterogeneous_items.csv",
        "bins": "heterogeneous_bins.csv",
        "objective": "variable-sized-bin-packing",
        "expected_complete": True,
        "expected_cost": 10.0,
        "engine": "box",
    },
    "heterogeneous_small_cheaper": {
        "benchmark_id": "B09",
        "variant": "SMALL_CHEAPER",
        "items": "heterogeneous_items.csv",
        "bins": "heterogeneous_bins_reverse.csv",
        "objective": "variable-sized-bin-packing",
        "expected_complete": True,
        "expected_cost": 10.0,
        "engine": "box",
    },
    "rotation_required": {
        "benchmark_id": "B12",
        "variant": "ROTATION_REQUIRED",
        "items": "rotation_allowed_items.csv",
        "bins": "rotation_bins.csv",
        "objective": "bin-packing",
        "expected_complete": True,
        "expected_cost": None,
        "engine": "box",
    },
    "rotation_forbidden": {
        "benchmark_id": "B12",
        "variant": "ROTATION_FORBIDDEN",
        "items": "rotation_forbidden_items.csv",
        "bins": "rotation_bins.csv",
        "objective": "bin-packing",
        "expected_complete": False,
        "expected_cost": None,
        "engine": "box",
    },
    "weight_limit": {
        "benchmark_id": "B13",
        "variant": "WEIGHT_LIMIT",
        "items": "weight_items.csv",
        "bins": "weight_bins.csv",
        "objective": "bin-packing",
        "expected_complete": True,
        "expected_cost": None,
        "engine": "box",
    },
    "maximum_weight_above": {
        "benchmark_id": "B14",
        "variant": "MAXIMUM_WEIGHT_ABOVE",
        "items": "stack_items.csv",
        "bins": "stack_bins.csv",
        "objective": "bin-packing",
        "expected_complete": True,
        "expected_cost": None,
        "engine": "boxstacks",
    },
    "maximum_stack_count": {
        "benchmark_id": "B14",
        "variant": "MAXIMUM_STACK_COUNT",
        "items": "stack_count_items.csv",
        "bins": "stack_count_bins.csv",
        "objective": "bin-packing",
        "expected_complete": True,
        "expected_cost": None,
        "engine": "boxstacks",
    },
    "nesting_height": {
        "benchmark_id": "B14",
        "variant": "NESTING_HEIGHT",
        "items": "nesting_items.csv",
        "bins": "nesting_bins.csv",
        "objective": "bin-packing",
        "expected_complete": True,
        "expected_cost": None,
        "engine": "boxstacks",
    },
    "axle_normal": {
        "benchmark_id": "B15",
        "variant": "AXLE_NORMAL",
        "items": "axle_realistic_items.csv",
        "bins": "axle_normal_bins.csv",
        "objective": "bin-packing",
        "expected_complete": True,
        "expected_cost": None,
        "engine": "boxstacks",
    },
    "axle_boundary_regression": {
        "benchmark_id": "B15",
        "variant": "AXLE_BOUNDARY",
        "items": "axle_items.csv",
        "bins": "axle_bins.csv",
        "objective": "bin-packing",
        "expected_complete": False,
        "expected_cost": None,
        "engine": "boxstacks",
    },
    "axle_infeasible": {
        "benchmark_id": "B15",
        "variant": "AXLE_INFEASIBLE",
        "items": "axle_realistic_items.csv",
        "bins": "axle_infeasible_bins.csv",
        "objective": "bin-packing",
        "expected_complete": False,
        "expected_cost": None,
        "engine": "boxstacks",
    },
    "unloading_none": {
        "benchmark_id": "B17",
        "variant": "UNLOADING_NONE",
        "items": "unloading_items.csv",
        "bins": "unloading_bins.csv",
        "objective": "bin-packing",
        "expected_complete": True,
        "expected_cost": None,
        "engine": "boxstacks",
        "extra": (),
    },
    "unloading_increasing_x": {
        "benchmark_id": "B17",
        "variant": "INCREASING_X",
        "items": "unloading_items.csv",
        "bins": "unloading_bins.csv",
        "objective": "bin-packing",
        "expected_complete": True,
        "expected_cost": None,
        "engine": "boxstacks",
        "extra": ("--unloading-constraint", "increasing-x"),
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def payload_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def float_field(row: dict[str, str], name: str, default: float = 0.0) -> float:
    value = row.get(name)
    return default if value in (None, "") else float(value)


def expected_rotations(spec: dict[str, str]) -> set[tuple[float, float, float]]:
    original = tuple(float(spec[axis]) for axis in ("X", "Y", "Z"))
    return {
        tuple(original[index] for index in order)
        for name, order in ROTATIONS.items()
        if spec.get(f"ROTATION_{name}") == "1"
    }


def intersects(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return all(
        left[axis] < right[axis] + right[f"d{axis}"]
        and right[axis] < left[axis] + left[f"d{axis}"]
        for axis in ("x", "y", "z")
    )


def axle_weights(bin_spec: dict[str, str], weighted_sum: float, weight: float) -> tuple[float, float]:
    if not int(float_field(bin_spec, "IS_SEMI_TRAILER_TRUCK")) or weight == 0:
        return (0.0, 0.0)
    harness_rear = float_field(bin_spec, "HARNESS_REAR_AXLE_DISTANCE")
    if harness_rear <= 0:
        return (0.0, 0.0)
    center = weighted_sum / weight
    center_to_rear = float_field(bin_spec, "TRAILER_START_HARNESS_DISTANCE") + harness_rear - center
    harness_weight = (
        weight * center_to_rear
        + float_field(bin_spec, "EMPTY_TRAILER_WEIGHT") * float_field(bin_spec, "TRAILER_GRAVITY_CENTER_REAR_AXLE_DISTANCE")
    ) / harness_rear
    rear = weight + float_field(bin_spec, "EMPTY_TRAILER_WEIGHT") - harness_weight
    front_middle = float_field(bin_spec, "FRONT_AXLE_MIDDLE_AXLE_DISTANCE")
    middle = 0.0
    if front_middle > 0:
        middle = (
            float_field(bin_spec, "TRACTOR_WEIGHT") * float_field(bin_spec, "FRONT_AXLE_TRACTOR_GRAVITY_CENTER_DISTANCE")
            + harness_weight * float_field(bin_spec, "FRONT_AXLE_HARNESS_DISTANCE")
        ) / front_middle
    return middle, rear


def validate_plain(items_path: Path, bins_path: Path, certificate: Path, expected_complete: bool) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    item_specs = {row["ID"]: row for row in read_csv(items_path)}
    bin_specs = {row["ID"]: row for row in read_csv(bins_path)}
    rows = read_csv(certificate)
    physical_bins: dict[str, dict[str, Any]] = {}
    pattern_bins: dict[str, list[str]] = {}
    for index, row in enumerate(row for row in rows if row.get("TYPE") == "BIN"):
        spec = bin_specs.get(row.get("ID"))
        if spec is None:
            errors.append(f"unknown bin type {row.get('ID')}")
            continue
        try:
            copies = int(row["COPIES"])
            dims = tuple(float(row[axis]) for axis in ("LX", "LY", "LZ"))
        except (KeyError, ValueError) as exc:
            errors.append(f"invalid bin row {index}: {exc}")
            continue
        expected_dims = tuple(float(spec[axis]) for axis in ("X", "Y", "Z"))
        if dims != expected_dims:
            errors.append(f"bin {row.get('ID')} dimensions differ from source")
        refs = [f"{row.get('BIN', index)}:{copy}" for copy in range(copies)]
        pattern_bins[row.get("BIN", str(index))] = refs
        for ref in refs:
            physical_bins[ref] = {"dims": dims, "spec": spec}
    placements: list[Box] = []
    counts: Counter[str] = Counter()
    for index, row in enumerate(row for row in rows if row.get("TYPE") == "ITEM"):
        spec = item_specs.get(row.get("ID"))
        if spec is None:
            errors.append(f"unknown item type {row.get('ID')}")
            continue
        refs = pattern_bins.get(row.get("BIN", ""), [])
        try:
            copies = int(row["COPIES"])
            dims = tuple(float(row[axis]) for axis in ("LX", "LY", "LZ"))
            pos = tuple(float(row[axis]) for axis in ("X", "Y", "Z"))
        except (KeyError, ValueError) as exc:
            errors.append(f"invalid item row {index}: {exc}")
            continue
        if copies != len(refs):
            errors.append(f"item {row.get('ID')} copies do not match bin pattern")
            continue
        if dims not in expected_rotations(spec):
            errors.append(f"item {row.get('ID')} uses a forbidden rotation")
        for copy, ref in enumerate(refs):
            placements.append(Box(f"{row['ID']}:{index}:{copy}", ref, *pos, *dims, float_field(spec, "WEIGHT")))
            counts[row["ID"]] += 1
    errors.extend(validate_aabbs(placements, {ref: value["dims"] for ref, value in physical_bins.items()}, {ref: float_field(value["spec"], "MAXIMUM_WEIGHT", float("inf")) for ref, value in physical_bins.items()}))
    for item_id, spec in item_specs.items():
        required = int(spec["COPIES"])
        if expected_complete and counts[item_id] != required:
            errors.append(f"item {item_id}: placed {counts[item_id]}, required {required}")
    metrics = {
        "packed_items": len(placements),
        "required_items": sum(int(spec["COPIES"]) for spec in item_specs.values()),
        "bins_used": len(physical_bins),
        "total_cost": sum(float_field(value["spec"], "COST") for value in physical_bins.values()),
        "validation_error_count": len(errors),
    }
    return errors, metrics


def validate_stack(items_path: Path, bins_path: Path, certificate: Path, expected_complete: bool, increasing_x: bool) -> tuple[list[str], dict[str, Any]]:
    # Keep the stack validator independent from the solver and deliberately
    # mirror only the public CSV semantics needed by this conformance suite.
    errors: list[str] = []
    item_specs = {row["ID"]: row for row in read_csv(items_path)}
    bin_specs = {row["ID"]: row for row in read_csv(bins_path)}
    rows = read_csv(certificate)
    physical_bins: dict[str, dict[str, str]] = {}
    pattern_bins: dict[str, list[str]] = {}
    used_cost = 0.0
    for index, row in enumerate(row for row in rows if row.get("TYPE") == "BIN"):
        spec = bin_specs.get(row.get("ID"))
        if spec is None:
            errors.append(f"unknown bin type {row.get('ID')}")
            continue
        copies = int(row["COPIES"])
        refs = [f"{row.get('BIN', index)}:{copy}" for copy in range(copies)]
        pattern_bins[row.get("BIN", str(index))] = refs
        for ref in refs:
            physical_bins[ref] = spec
        used_cost += float_field(spec, "COST") * copies
    placements: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    stacks: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for index, row in enumerate(row for row in rows if row.get("TYPE") == "ITEM"):
        spec = item_specs.get(row.get("ID"))
        if spec is None:
            errors.append(f"unknown item type {row.get('ID')}")
            continue
        refs = pattern_bins.get(row.get("BIN", ""), [])
        copies = int(row["COPIES"])
        if copies != len(refs):
            errors.append(f"item {row.get('ID')} copies do not match bin pattern")
            continue
        for copy, ref in enumerate(refs):
            placement = {
                "ref": f"{row['ID']}:{index}:{copy}",
                "item_id": row["ID"],
                "bin_ref": ref,
                "stack": row.get("STACK", ""),
                "group": int(float_field(spec, "GROUP_ID")),
                "x": float(row["X"]), "y": float(row["Y"]), "z": float(row["Z"]),
                "dx": float(row["LX"]), "dy": float(row["LY"]), "dz": float(row["LZ"]),
                "weight": float_field(spec, "WEIGHT"),
                "nesting": float_field(spec, "NESTING_HEIGHT"),
                "max_stack": int(float_field(spec, "MAXIMUM_STACKABILITY", 10**9)),
                "max_weight_above": float_field(spec, "MAXIMUM_WEIGHT_ABOVE", float("inf")),
            }
            placements.append(placement)
            stacks.setdefault((ref, placement["stack"]), []).append(placement)
            counts[row["ID"]] += 1
    for placement in placements:
        spec = physical_bins.get(placement["bin_ref"])
        if spec is None:
            errors.append(f"{placement['ref']}: unknown physical bin")
            continue
        dims = tuple(float(spec[axis]) for axis in ("X", "Y", "Z"))
        if any(placement[axis] < -1e-7 or placement[axis] + placement[f"d{axis}"] > dims[index] + 1e-7 for index, axis in enumerate(("x", "y", "z"))):
            errors.append(f"{placement['ref']}: out of bounds")
    for left_index, left in enumerate(placements):
        for right in placements[left_index + 1:]:
            if left["bin_ref"] == right["bin_ref"] and left["stack"] != right["stack"] and intersects(left, right):
                errors.append(f"{left['ref']} overlaps {right['ref']}")
    for stack_ref, stack in stacks.items():
        ordered = sorted(stack, key=lambda value: value["z"])
        if len(ordered) > min(item["max_stack"] for item in ordered):
            errors.append(f"stack {stack_ref} exceeds maximum stack count")
        for index, item in enumerate(ordered):
            above = sum(other["weight"] for other in ordered[index + 1:])
            if above > item["max_weight_above"] + 1e-7:
                errors.append(f"{item['ref']} exceeds maximum weight above")
            if index:
                previous = ordered[index - 1]
                expected_z = previous["z"] + previous["dz"] - item["nesting"]
                if abs(item["z"] - expected_z) > 1e-7:
                    errors.append(f"{item['ref']} violates nesting height")
    if expected_complete:
        for item_id, spec in item_specs.items():
            if counts[item_id] != int(spec["COPIES"]):
                errors.append(f"item {item_id}: placed {counts[item_id]}, required {spec['COPIES']}")
    axle_metrics: dict[str, Any] = {}
    for ref, spec in physical_bins.items():
        selected = [item for item in placements if item["bin_ref"] == ref]
        weight = sum(item["weight"] for item in selected)
        weighted_sum = sum((item["x"] + item["dx"] / 2) * item["weight"] for item in selected)
        middle, rear = axle_weights(spec, weighted_sum, weight)
        axle_metrics[ref] = {"middle": middle, "rear": rear}
        if middle > float_field(spec, "MIDDLE_AXLE_MAXIMUM_WEIGHT", float("inf")) + 1e-7 or rear > float_field(spec, "REAR_AXLE_MAXIMUM_WEIGHT", float("inf")) + 1e-7:
            errors.append(f"{ref}: axle limit violated")
    if increasing_x:
        groups: dict[int, list[float]] = {}
        for item in placements:
            groups.setdefault(item["group"], []).append(item["x"])
        ordered_groups = sorted(groups)
        for left, right in zip(ordered_groups, ordered_groups[1:]):
            if min(groups[left]) < max(groups[right]):
                errors.append(f"unloading group {right} is not closer to exit than {left}")
    return errors, {
        "packed_items": len(placements),
        "required_items": sum(int(spec["COPIES"]) for spec in item_specs.values()),
        "bins_used": len(physical_bins),
        "total_cost": used_cost,
        "axle_metrics": json.dumps(axle_metrics, sort_keys=True),
        "validation_error_count": len(errors),
    }


def source_payload(case: dict[str, Any], case_name: str) -> tuple[dict[str, Any], Path, Path]:
    items_path = DATA_ROOT / case["items"]
    bins_path = DATA_ROOT / case["bins"]
    payload = {
        "benchmark_id": case["benchmark_id"],
        "problem_variant": case["variant"],
        "instance_id": case_name,
        "objective": case["objective"],
        "items": read_csv(items_path),
        "bins": read_csv(bins_path),
        "source_files": {str(path.relative_to(ROOT)): sha256(path) for path in (items_path, bins_path)},
    }
    return payload, items_path, bins_path


def source_commit(source_root: Path, expected: str, allow_dirty: bool) -> tuple[str, str | None]:
    commit = subprocess.run(["git", "-C", str(source_root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    if commit != expected:
        raise ValueError(f"source commit mismatch: expected {expected}, got {commit}")
    diff = subprocess.run(["git", "-C", str(source_root), "diff", "--binary"], check=True, capture_output=True).stdout
    if diff and not allow_dirty:
        raise ValueError(f"source checkout is dirty: {source_root}")
    return commit, hashlib.sha256(diff).hexdigest() if diff else None


def parse_resources(path: Path) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if not path.exists():
        return values
    for line in path.read_text(errors="replace").splitlines():
        if line.startswith("Maximum resident set size"):
            values["peak_rss_bytes"] = int(line.rsplit(": ", 1)[-1]) * 1024
        elif line.startswith("User time"):
            values["cpu_user_s"] = float(line.rsplit(": ", 1)[-1])
        elif line.startswith("System time"):
            values["cpu_system_s"] = float(line.rsplit(": ", 1)[-1])
    return values


def run_case(case_name: str, case: dict[str, Any], binary: Path, implementation: dict[str, Any], source_root: Path, time_limit: float, raw_dir: Path) -> dict[str, Any]:
    payload, items_path, bins_path = source_payload(case, case_name)
    input_hash = payload_hash(payload)
    case_dir = raw_dir / case_name
    case_dir.mkdir(parents=True, exist_ok=True)
    input_path = case_dir / "input.json"
    output_path = case_dir / "output.json"
    certificate_path = case_dir / "solution.csv"
    stdout_path = case_dir / "stdout.log"
    stderr_path = case_dir / "stderr.log"
    resources_path = case_dir / "resources.txt"
    validation_path = case_dir / "validation.json"
    config_path = case_dir / "effective-config.json"
    input_path.write_text(canonical_json(payload), encoding="utf-8")
    command = [
        "/usr/bin/time", "-v", "-o", str(resources_path), str(binary),
        "--items", str(items_path), "--bins", str(bins_path), "--objective", case["objective"],
        "--time-limit", str(time_limit), "--memory-limit", "1024", "--verbosity-level", "0",
        "--only-write-at-the-end", "--linear-programming-solver", "highs",
        "--output", str(output_path), "--certificate", str(certificate_path),
        *case.get("extra", ()),
    ]
    config_path.write_text(canonical_json({
        "command": command, "payload_sha256": input_hash, "source_files": payload["source_files"],
        "benchmark_id": case["benchmark_id"], "problem_variant": case["variant"], "instance_id": case_name,
        "implementation_id": implementation["id"], "implementation_version": implementation["version"],
        "binary_sha256": sha256(binary), "runner_sha256": sha256(RUNNER_PATH), "validator_sha256": sha256(VALIDATOR_PATH),
        "source_root": str(source_root), "time_limit_s": time_limit, "memory_limit_bytes": 1073741824, "thread_limit": 1,
        "pose_semantics": "SOURCE_ROTATION_FLAGS",
    }), encoding="utf-8")
    for path in (output_path, certificate_path):
        path.unlink(missing_ok=True)
    env = os.environ.copy()
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[name] = "1"
    started = perf_counter()
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=max(30.0, time_limit + 20.0), env=env, check=False)
        wall_s = perf_counter() - started
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
    except subprocess.TimeoutExpired as exc:
        completed = None
        wall_s = perf_counter() - started
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text(exc.stderr or "", encoding="utf-8")
    process_ok = completed is not None and completed.returncode == 0 and output_path.exists() and certificate_path.exists()
    if process_ok:
        if case["engine"] == "boxstacks":
            errors, metrics = validate_stack(items_path, bins_path, certificate_path, case["expected_complete"], case.get("extra") == ("--unloading-constraint", "increasing-x"))
        else:
            errors, metrics = validate_plain(items_path, bins_path, certificate_path, case["expected_complete"])
    else:
        errors, metrics = ["solver failed, timed out, or omitted output/certificate"], {"packed_items": 0, "required_items": sum(int(row["COPIES"]) for row in read_csv(items_path)), "bins_used": 0, "total_cost": None, "validation_error_count": 1}
    validation = {"status": "PASS" if not errors else "FAIL", "errors": errors, **metrics}
    resources = parse_resources(resources_path)
    solver_s = None
    if output_path.exists():
        try:
            solver_s = float(json.loads(output_path.read_text(encoding="utf-8"))["Output"]["Solution"].get("Time", 0.0))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            solver_s = None
    valid = validation["status"] == "PASS"
    expected_no_solution = not case["expected_complete"] and valid and metrics["packed_items"] < metrics["required_items"]
    if not process_ok:
        run_status, termination = "ERROR", "PROCESS_ERROR_OR_EXTERNAL_TIMEOUT"
    elif expected_no_solution:
        run_status, termination = "COMPLETED", "EXPECTED_INFEASIBILITY_BEHAVIOR"
    elif solver_s is not None and solver_s >= time_limit * 0.95:
        run_status, termination = "TIME_LIMIT", "TIME_LIMIT_WITH_CERTIFICATE"
    else:
        run_status, termination = "COMPLETED", "RETURNED_CERTIFICATE"
    solution_status = "VALID_COMPLETE" if valid and not expected_no_solution and case["expected_complete"] else "NO_SOLUTION" if expected_no_solution else "INVALID_CERTIFICATE" if process_ok else "NO_SOLUTION"
    if not case["expected_complete"] and valid and not expected_no_solution:
        solution_status = "INVALID_CERTIFICATE"
    if case["expected_cost"] is not None and valid and abs(float(metrics["total_cost"]) - case["expected_cost"]) > 1e-7:
        validation["errors"].append(f"cost {metrics['total_cost']} differs from expected {case['expected_cost']}")
        validation["status"] = "FAIL"
        solution_status = "INVALID_CERTIFICATE"
        valid = False
    validation_path.write_text(canonical_json(validation), encoding="utf-8")
    expected_behavior_pass = bool(
        process_ok
        and ((case["expected_complete"] and solution_status == "VALID_COMPLETE")
             or (not case["expected_complete"] and solution_status == "NO_SOLUTION"))
    )
    record = {
        "schema_version": 2, "protocol_version": "benchmark-protocol/3", "record_origin": "PROTOCOL_V3",
        "run_id": f"{case['benchmark_id']}/{case['variant']}/{case_name}/{implementation['id']}/{time_limit:g}s/SOURCE/rep-0",
        "benchmark_id": case["benchmark_id"], "problem_variant": case["variant"], "instance_id": case_name,
        "implementation_id": implementation["id"], "algorithm": implementation["algorithm"],
        "adapter": "constraint_gauntlet/native_csv_v1", "comparison_track": "NATIVE", "problem_scope": "FULL_PROBLEM",
        "budget": {"time_limit_s": time_limit, "memory_limit_bytes": 1073741824, "thread_limit": 1},
        "item_order": "SOURCE", "bin_order": "SOURCE", "seed": None, "repetition": 0,
        "input_sha256": input_hash, "input_status": "VALID", "capability_status": "SUPPORTED_NATIVE",
        "run_status": run_status, "solution_status": solution_status,
        "proof_status": "FEASIBLE" if valid else "UNKNOWN", "termination_reason": termination,
        "resources": {"wall_s": wall_s, "solver_s": solver_s, **resources},
        "metrics": {**metrics, "expected_complete": case["expected_complete"], "expected_cost": case["expected_cost"], "expected_behavior_pass": expected_behavior_pass, "binary_sha256": sha256(binary)},
        "artifacts": {
            "input": f"{str((raw_dir / 'artifacts.tar.gz').resolve().relative_to(ROOT))}#{case_name}/input.json",
            "effective_config": f"{str((raw_dir / 'artifacts.tar.gz').resolve().relative_to(ROOT))}#{case_name}/effective-config.json",
            "solver_output": f"{str((raw_dir / 'artifacts.tar.gz').resolve().relative_to(ROOT))}#{case_name}/output.json" if output_path.exists() else None,
            "solution": f"{str((raw_dir / 'artifacts.tar.gz').resolve().relative_to(ROOT))}#{case_name}/solution.csv" if certificate_path.exists() else None,
            "validation": f"{str((raw_dir / 'artifacts.tar.gz').resolve().relative_to(ROOT))}#{case_name}/validation.json",
            "stdout": f"{str((raw_dir / 'artifacts.tar.gz').resolve().relative_to(ROOT))}#{case_name}/stdout.log",
            "stderr": f"{str((raw_dir / 'artifacts.tar.gz').resolve().relative_to(ROOT))}#{case_name}/stderr.log",
            "resources": f"{str((raw_dir / 'artifacts.tar.gz').resolve().relative_to(ROOT))}#{case_name}/resources.txt" if resources_path.exists() else None,
        },
    }
    validate_run_record(record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="Run protocol-v3 PackingSolver constraint conformance cases")
    parser.add_argument("--implementation-id", choices=("packingsolver_fork_box", "packingsolver_fork_boxstacks", "packingsolver_upstream_box", "packingsolver_upstream_boxstacks"), required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--time-limit", type=float, default=10.0)
    parser.add_argument("--results-root", type=Path, default=ROOT / "results" / "comprehensive")
    parser.add_argument("--raw-root", type=Path, default=ROOT / "raw" / "experiments" / "comprehensive")
    parser.add_argument("--case", action="append", choices=sorted(CASES))
    parser.add_argument("--allow-dirty-source", action="store_true")
    args = parser.parse_args()
    binary = args.binary.resolve()
    source_root = args.source_root.resolve()
    if not binary.is_file():
        raise ValueError(f"missing binary: {binary}")
    expected_commit = FORK_COMMIT if "fork" in args.implementation_id else UPSTREAM_COMMIT
    source_commit_value, source_diff = source_commit(source_root, expected_commit, args.allow_dirty_source)
    _, catalog = load_catalogs()
    implementations = {row["id"]: row for row in catalog["implementations"]}
    implementation = implementations[args.implementation_id]
    is_stack = "boxstacks" in args.implementation_id
    selected = args.case or list(CASES)
    selected = [
        name for name in selected
        if (CASES[name]["engine"] == "boxstacks" if is_stack else CASES[name]["engine"] == "box")
        or (is_stack and CASES[name]["benchmark_id"] == "B09")
    ]
    if not selected:
        raise ValueError("no cases match the selected binary family")
    raw_dir = args.raw_root / "constraint-gauntlet" / args.implementation_id / f"{args.time_limit:g}s"
    raw_dir.mkdir(parents=True, exist_ok=True)
    records = [run_case(name, CASES[name], binary, implementation, source_root, args.time_limit, raw_dir) for name in selected]
    archive_path = raw_dir / "artifacts.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for path in sorted(raw_dir.rglob("*")):
            if path.is_file() and path != archive_path:
                archive.add(path, arcname=path.relative_to(raw_dir))
    run_path = args.results_root / "runs" / f"constraint-gauntlet-{args.implementation_id}-{args.time_limit:g}s.jsonl"
    run_path.parent.mkdir(parents=True, exist_ok=True)
    run_path.write_text("".join(json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n" for record in records), encoding="utf-8")
    metadata = {
        "schema_version": 1, "protocol_version": "benchmark-protocol/3", "implementation_id": args.implementation_id,
        "implementation_version": implementation["version"], "source_commit": source_commit_value,
        "source_diff_sha256": source_diff, "binary_sha256": sha256(binary), "runner_sha256": sha256(RUNNER_PATH),
        "validator_sha256": sha256(VALIDATOR_PATH), "time_limit_s": args.time_limit, "cases": selected,
        "run_jsonl_sha256": sha256(run_path), "artifact_archive_sha256": sha256(archive_path),
        "platform": platform.platform(), "python_version": platform.python_version(),
    }
    (raw_dir / "metadata.json").write_text(canonical_json(metadata), encoding="utf-8")
    print(run_path.relative_to(ROOT))
    return 0 if all(record["solution_status"] in {"VALID_COMPLETE", "NO_SOLUTION"} for record in records) else 2


if __name__ == "__main__":
    raise SystemExit(main())
