#!/usr/bin/env python3
"""Run a small exact B07 calibration track with source rotation flags.

B07 is a single-container volume-knapsack suite.  The public instances are
usually too large for a direct positional CP-SAT model, so this runner selects
the smallest source instances (or an explicit ``--limit``) and records every
non-optimal termination as an incumbent rather than treating it as a proof.
The model keeps the six source rotation flags and every certificate is checked
again by the shared THPACK validator.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
import tarfile
from dataclasses import asdict
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks" / "campaign" / "python_thpack"))
from model import Instance, ItemType, allowed_oriented_sizes, sha256 as source_sha256, validate_certificate  # noqa: E402

sys.path.insert(0, str(ROOT / "benchmarks"))
from comprehensive.model import canonical_json, validate_run_record  # noqa: E402


SOURCE_COMMIT = "d953148b8f710c06fa6c410949b7272f9e36327b"
RUNNER_PATH = Path(__file__).resolve()
SHARED_VALIDATOR = ROOT / "benchmarks" / "campaign" / "python_thpack" / "model.py"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def discover(source_root: Path, max_items: int, limit: int | None) -> list[tuple[str, str, Path, Path, int]]:
    candidates: list[tuple[str, str, Path, Path, int]] = []
    for item_path in source_root.glob("*_items.csv"):
        stem = item_path.name.removesuffix("_items.csv")
        bin_path = source_root / f"{stem}_bins.csv"
        if not bin_path.exists():
            continue
        group, number_text = stem.rsplit(".txt_", 1)
        item_count = sum(int(row["COPIES"]) for row in read_csv(item_path))
        if item_count <= max_items:
            candidates.append((stem, group, item_path, bin_path, item_count))
    candidates.sort(key=lambda row: (row[4], row[1], int(row[0].rsplit("_", 1)[1])))
    return candidates[:limit] if limit is not None else candidates


def load_instance(source_id: str, group: str, item_path: Path, bin_path: Path) -> tuple[Instance, dict[str, Any]]:
    number = int(source_id.rsplit("_", 1)[1])
    item_types: list[ItemType] = []
    for row in read_csv(item_path):
        item_types.append(
            ItemType(
                type_id=row["ID"],
                size=(int(row["X"]), int(row["Y"]), int(row["Z"])),
                allowed_vertical_dimensions=(
                    int(row["ROTATION_XYZ"]),
                    int(row["ROTATION_YXZ"]),
                    int(row["ROTATION_ZYX"]),
                ),
                copies=int(row["COPIES"]),
            )
        )
    bin_row = read_csv(bin_path)[0]
    container = tuple(int(bin_row[axis]) for axis in ("X", "Y", "Z"))
    instance = Instance(
        family=group,
        instance_id=number,
        problem_kind="single_container_knapsack",
        objective="maximize_packed_volume",
        container=container,
        item_types=item_types,
    )
    payload = {
        "benchmark_id": "B07",
        "problem_variant": "SOURCE_ROTATION_FLAGS",
        "source_commit": SOURCE_COMMIT,
        "source_id": source_id,
        "source_group": group,
        "container": list(container),
        "items": [asdict(item) for item in item_types],
        "source_items_sha256": source_sha256(item_path),
        "source_bins_sha256": source_sha256(bin_path),
    }
    return instance, payload


def payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def solve(instance: Instance, time_limit: float) -> dict[str, Any]:
    from ortools.sat.python import cp_model

    items = []
    for item in instance.item_types:
        for copy_index in range(item.copies):
            items.append(
                {
                    "item_id": f"{item.type_id}:{copy_index}",
                    "type_id": item.type_id,
                    "size": item.size,
                    "flags": item.allowed_vertical_dimensions,
                }
            )
    model = cp_model.CpModel()
    n = len(items)
    max_axis = max(instance.container)
    selected = [model.new_bool_var(f"selected_{index}") for index in range(n)]
    positions = [[model.new_int_var(0, max_axis, f"p_{index}_{axis}") for axis in range(3)] for index in range(n)]
    dimensions = [[model.new_int_var(0, max_axis, f"d_{index}_{axis}") for axis in range(3)] for index in range(n)]
    orientation_vars: list[list[Any]] = []
    orientation_sizes: list[list[tuple[int, int, int]]] = []

    for index, item in enumerate(items):
        allowed = sorted(allowed_oriented_sizes(tuple(item["size"]), tuple(item["flags"])))
        if not allowed:
            return {"status": "INFEASIBLE", "packed_volume": None, "bound": None, "gap": None, "solver_time_s": 0.0, "branches": 0, "conflicts": 0, "placements": [], "validation_errors": [f"no allowed orientation for {item['item_id']}"]}
        choices = [model.new_bool_var(f"o_{index}_{choice}") for choice in range(len(allowed))]
        orientation_vars.append(choices)
        orientation_sizes.append(allowed)
        model.add(sum(choices) == selected[index])
        for choice, size in zip(choices, allowed):
            for axis in range(3):
                model.add(dimensions[index][axis] == size[axis]).only_enforce_if(choice)
        for axis in range(3):
            model.add(dimensions[index][axis] == 0).only_enforce_if(selected[index].Not())
            model.add(positions[index][axis] + dimensions[index][axis] <= instance.container[axis]).only_enforce_if(selected[index])

    for left in range(n):
        for right in range(left + 1, n):
            relative = [model.new_bool_var(f"r_{left}_{right}_{direction}") for direction in range(6)]
            model.add(sum(relative) >= selected[left] + selected[right] - 1)
            for axis in range(3):
                model.add(positions[left][axis] + dimensions[left][axis] <= positions[right][axis]).only_enforce_if(relative[2 * axis])
                model.add(positions[right][axis] + dimensions[right][axis] <= positions[left][axis]).only_enforce_if(relative[2 * axis + 1])

    model.maximize(sum(
        item["size"][0] * item["size"][1] * item["size"][2] * selected[index]
        for index, item in enumerate(items)
    ))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 42
    started = perf_counter()
    status_code = solver.solve(model)
    elapsed = perf_counter() - started
    status = solver.status_name(status_code)
    has_solution = status in {"OPTIMAL", "FEASIBLE"}
    placements: list[dict[str, Any]] = []
    if has_solution:
        for index, item in enumerate(items):
            if not solver.value(selected[index]):
                continue
            dims = tuple(solver.value(dimensions[index][axis]) for axis in range(3))
            placements.append({
                "item_id": item["item_id"],
                "bin_id": "bin-000",
                "x": solver.value(positions[index][0]),
                "y": solver.value(positions[index][1]),
                "z": solver.value(positions[index][2]),
                "dx": dims[0], "dy": dims[1], "dz": dims[2],
            })
    errors = validate_certificate(instance, placements, require_complete=False)
    packed_volume = sum(p["dx"] * p["dy"] * p["dz"] for p in placements) if has_solution else None
    bound = float(solver.best_objective_bound) if status in {"OPTIMAL", "FEASIBLE"} else None
    gap = None
    if has_solution and bound is not None and bound > 0 and packed_volume is not None and status != "OPTIMAL":
        gap = max(0.0, (bound - packed_volume) / bound)
    if status == "OPTIMAL" and bound is not None and packed_volume is not None and abs(bound - packed_volume) > 1e-6:
        errors.append("solver reported OPTIMAL but objective bound differs")
    return {
        "status": status,
        "packed_volume": packed_volume,
        "bound": bound,
        "gap": 0.0 if status == "OPTIMAL" and not errors else gap,
        "solver_time_s": elapsed,
        "branches": solver.num_branches,
        "conflicts": solver.num_conflicts,
        "placements": placements,
        "validation_errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Exact B07 source-rotation calibration")
    parser.add_argument("--source-root", type=Path, default=ROOT / ".cache" / "packingsolver-fork" / "data" / "box" / "davies1999")
    parser.add_argument("--max-items", type=int, default=60)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--time-limit", type=float, default=20.0)
    args = parser.parse_args()
    if args.max_items < 1 or args.time_limit <= 0:
        raise SystemExit("--max-items and --time-limit must be positive")

    candidates = discover(args.source_root, args.max_items, args.limit)
    if not candidates:
        raise SystemExit("no B07 instances satisfy --max-items")
    raw_dir = ROOT / "raw" / "experiments" / "comprehensive" / "B07" / "exact_cp_sat" / f"{args.time_limit:g}s"
    cases_dir = raw_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)
    archive_name = str((raw_dir / "artifacts.tar.gz").relative_to(ROOT))
    records: list[dict[str, Any]] = []
    for source_id, group, item_path, bin_path, item_count in candidates:
        instance, input_payload = load_instance(source_id, group, item_path, bin_path)
        case_dir = cases_dir / source_id
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "input.json").write_text(canonical_json(input_payload), encoding="utf-8")
        input_hash = payload_hash(input_payload)
        result = solve(instance, args.time_limit)
        (case_dir / "output.json").write_text(canonical_json(result), encoding="utf-8")
        (case_dir / "validation.json").write_text(canonical_json({"status": "PASS" if not result["validation_errors"] else "FAIL", "errors": result["validation_errors"]}), encoding="utf-8")
        valid = result["status"] in {"OPTIMAL", "FEASIBLE"} and not result["validation_errors"]
        solution_status = "VALID_PARTIAL" if valid else "NO_SOLUTION" if result["status"] not in {"OPTIMAL", "FEASIBLE"} else "INVALID_CERTIFICATE"
        record = {
            "schema_version": 2,
            "protocol_version": "benchmark-protocol/3",
            "record_origin": "PROTOCOL_V3",
            "run_id": f"B07/SOURCE_ROTATION_FLAGS/{source_id}/exact_cp_sat/{args.time_limit:g}s/EXACT_MODEL/rep-0",
            "benchmark_id": "B07",
            "problem_variant": "SOURCE_ROTATION_FLAGS",
            "instance_id": source_id,
            "implementation_id": "exact_cp_sat",
            "algorithm": "source-pose volume CP-SAT",
            "adapter": "run_b07_exact.py",
            "comparison_track": "EXACT_MODEL",
            "problem_scope": "FULL_PROBLEM",
            "budget": {"time_limit_s": args.time_limit, "memory_limit_bytes": 4294967296, "thread_limit": 1},
            "item_order": "SOURCE",
            "bin_order": "SOURCE",
            "seed": 42,
            "repetition": 0,
            "input_sha256": input_hash,
            "input_status": "VALID",
            "capability_status": "SUPPORTED_NATIVE",
            "run_status": "COMPLETED" if result["status"] in {"OPTIMAL", "FEASIBLE", "INFEASIBLE"} else "ERROR",
            "solution_status": solution_status,
            "proof_status": "PROVEN_OPTIMAL" if result["status"] == "OPTIMAL" and valid else "FEASIBLE" if valid else "UNKNOWN",
            "termination_reason": "OPTIMAL" if result["status"] == "OPTIMAL" else "TIME_LIMIT_WITH_INCUMBENT" if result["status"] == "FEASIBLE" else result["status"],
            "resources": {"solver_s": result["solver_time_s"], "wall_s": result["solver_time_s"], "peak_rss_bytes": None},
            "metrics": {
                "packed_items": len(result["placements"]),
                "required_items": instance.item_count,
                "packed_volume": result["packed_volume"],
                "volume_utilization": result["packed_volume"] / instance.container_volume if result["packed_volume"] is not None else None,
                "solver_bound": result["bound"],
                "gap": result["gap"],
                "validation_error_count": len(result["validation_errors"]),
                "source_group": group,
                "source_item_count": item_count,
                "source_items_sha256": input_payload["source_items_sha256"],
                "source_bins_sha256": input_payload["source_bins_sha256"],
                "branches": result["branches"],
                "conflicts": result["conflicts"],
            },
            "artifacts": {
                "input": f"{archive_name}#cases/{source_id}/input.json",
                "solver_output": f"{archive_name}#cases/{source_id}/output.json",
                "validation": f"{archive_name}#cases/{source_id}/validation.json",
            },
        }
        validate_run_record(record)
        records.append(record)

    archive_path = raw_dir / "artifacts.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for path in sorted(cases_dir.rglob("*")):
            if path.is_file():
                archive.add(path, arcname=path.relative_to(raw_dir))
    output_path = ROOT / "results" / "comprehensive" / "runs" / f"B07-exact_cp_sat-{args.time_limit:g}s.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("".join(json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n" for record in sorted(records, key=lambda row: row["run_id"])), encoding="utf-8")
    summary = {
        "schema_version": 1,
        "protocol_version": "benchmark-protocol/3",
        "benchmark_id": "B07",
        "problem_variant": "SOURCE_ROTATION_FLAGS",
        "comparison_track": "EXACT_MODEL",
        "implementation_id": "exact_cp_sat",
        "implementation_version": "9.15.6755",
        "source_commit": SOURCE_COMMIT,
        "python_version": platform.python_version(),
        "max_items": args.max_items,
        "time_limit_s": args.time_limit,
        "instances": len(records),
        "proven_optimal": sum(record["proof_status"] == "PROVEN_OPTIMAL" for record in records),
        "valid_records": sum(record["solution_status"] == "VALID_PARTIAL" for record in records),
        "artifact_archive": archive_name,
        "artifact_archive_sha256": source_sha256(archive_path),
        "run_jsonl_sha256": source_sha256(output_path),
        "runner_sha256": source_sha256(RUNNER_PATH),
        "shared_validator_sha256": source_sha256(SHARED_VALIDATOR),
    }
    (raw_dir / "metadata.json").write_text(canonical_json(summary), encoding="utf-8")
    (ROOT / "results" / "comprehensive" / "B07-exact_cp_sat-summary.json").write_text(canonical_json(summary), encoding="utf-8")
    print(output_path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
