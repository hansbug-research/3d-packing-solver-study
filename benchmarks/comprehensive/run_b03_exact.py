from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
from itertools import permutations
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks"))

from comprehensive.model import canonical_json, validate_run_record
from run_b03_packingsolver import INDEX_PATH, input_paths, payload_hash, sha256, validate_source
from validation import Box, validate_aabbs


RUNNER_PATH = Path(__file__).resolve()
SHARED_VALIDATOR_PATH = ROOT / "benchmarks" / "validation.py"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_case(index_row: dict[str, Any], source_root: Path) -> tuple[list[dict[str, Any]], tuple[int, int, int]]:
    items_path, bins_path = validate_source(index_row, source_root)
    items = []
    for row in read_csv(items_path):
        for copy in range(int(row["COPIES"])):
            items.append(
                {
                    "id": row["ID"] if int(row["COPIES"]) == 1 else f"{row['ID']}:{copy}",
                    "size": tuple(int(row[axis]) for axis in ("X", "Y", "Z")),
                    "profit": int(row["PROFIT"]),
                }
            )
    bin_row = read_csv(bins_path)[0]
    return items, tuple(int(bin_row[axis]) for axis in ("X", "Y", "Z"))


def solve(items: list[dict[str, Any]], bin_size: tuple[int, int, int], time_limit: float) -> dict[str, Any]:
    from ortools.sat.python import cp_model

    model = cp_model.CpModel()
    n = len(items)
    selected = [model.new_bool_var(f"selected_{i}") for i in range(n)]
    max_axis = max(bin_size)
    positions = [[model.new_int_var(0, max_axis, f"p_{i}_{axis}") for axis in range(3)] for i in range(n)]
    for i, item in enumerate(items):
        for axis in range(3):
            model.add(positions[i][axis] + item["size"][axis] <= bin_size[axis]).only_enforce_if(selected[i])
    for i in range(n):
        for j in range(i + 1, n):
            relative = [model.new_bool_var(f"r_{i}_{j}_{k}") for k in range(6)]
            model.add(sum(relative) >= selected[i] + selected[j] - 1)
            for axis in range(3):
                model.add(positions[i][axis] + items[i]["size"][axis] <= positions[j][axis]).only_enforce_if(relative[2 * axis])
                model.add(positions[j][axis] + items[j]["size"][axis] <= positions[i][axis]).only_enforce_if(relative[2 * axis + 1])
    model.maximize(sum(item["profit"] * selected[i] for i, item in enumerate(items)))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 42
    started = perf_counter()
    code = solver.solve(model)
    elapsed = perf_counter() - started
    status = solver.status_name(code)
    has_solution = status in {"OPTIMAL", "FEASIBLE"}
    placements = []
    if has_solution:
        for i, item in enumerate(items):
            if solver.value(selected[i]):
                placements.append(
                    {
                        "item_id": item["id"],
                        "x": solver.value(positions[i][0]),
                        "y": solver.value(positions[i][1]),
                        "z": solver.value(positions[i][2]),
                        "dx": item["size"][0],
                        "dy": item["size"][1],
                        "dz": item["size"][2],
                    }
                )
    boxes = [
        Box(p["item_id"], "bin-0", p["x"], p["y"], p["z"], p["dx"], p["dy"], p["dz"], 1)
        for p in placements
    ]
    errors = validate_aabbs(boxes, {"bin-0": bin_size})
    packed_profit = sum(items[next(i for i, item in enumerate(items) if item["id"] == p["item_id"])] ["profit"] for p in placements)
    if status == "OPTIMAL" and solver.best_objective_bound != packed_profit:
        errors.append("solver reported OPTIMAL but objective bound differs")
    return {
        "status": status,
        "packed_profit": packed_profit if has_solution else None,
        "bound": solver.best_objective_bound if status != "INFEASIBLE" else None,
        "gap": 0.0 if status == "OPTIMAL" else None,
        "solver_time_s": elapsed,
        "branches": solver.num_branches,
        "conflicts": solver.num_conflicts,
        "placements": placements,
        "validation_errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Exact fixed-pose B03 20-item CP-SAT track")
    parser.add_argument("--source-root", type=Path, default=ROOT / ".cache" / "packingsolver-fork")
    parser.add_argument("--time-limit", type=float, default=20.0)
    parser.add_argument("--results-root", type=Path, default=ROOT / "results" / "comprehensive")
    parser.add_argument("--raw-root", type=Path, default=ROOT / "raw" / "experiments" / "comprehensive")
    args = parser.parse_args()
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    cases = [row for row in index["instances"] if row["item_count"] == 20]
    raw_dir = args.raw_root / "B03" / "exact_cp_sat" / "20s"
    archive_reference = str((raw_dir / "artifacts.tar.gz").resolve().relative_to(ROOT))
    raw_dir.mkdir(parents=True, exist_ok=True)
    work_root = raw_dir / "cases"
    work_root.mkdir(parents=True, exist_ok=True)
    runner_hash = sha256(RUNNER_PATH)
    validator_hash = sha256(SHARED_VALIDATOR_PATH)
    records = []
    for index_row in cases:
        case_name = index_row["id"].removesuffix(".3kp")
        case_dir = work_root / case_name
        case_dir.mkdir(exist_ok=True)
        items, bin_size = load_case(index_row, args.source_root.resolve())
        input_payload = {"benchmark_id": "B03", "instance": index_row, "items": items, "bin_size": bin_size}
        (case_dir / "input.json").write_text(canonical_json(input_payload), encoding="utf-8")
        result = solve(items, bin_size, args.time_limit)
        (case_dir / "output.json").write_text(canonical_json(result), encoding="utf-8")
        (case_dir / "validation.json").write_text(canonical_json({"status": "PASS" if not result["validation_errors"] else "FAIL", "errors": result["validation_errors"]}), encoding="utf-8")
        has_solution = result["status"] in {"OPTIMAL", "FEASIBLE"}
        valid = has_solution and not result["validation_errors"]
        total_profit = index_row["total_profit"]
        record = {
            "schema_version": 2,
            "protocol_version": "benchmark-protocol/3",
            "record_origin": "PROTOCOL_V3",
            "run_id": f"B03/FIXED_XYZ/{index_row['id']}/exact_cp_sat/20s/EXACT_MODEL/rep-0",
            "benchmark_id": "B03",
            "problem_variant": "FIXED_XYZ",
            "instance_id": index_row["id"],
            "implementation_id": "exact_cp_sat",
            "algorithm": "fixed-pose profit CP-SAT",
            "adapter": "run_b03_exact.py",
            "comparison_track": "EXACT_MODEL",
            "problem_scope": "FULL_PROBLEM",
            "budget": {"time_limit_s": args.time_limit, "memory_limit_bytes": 4294967296, "thread_limit": 1},
            "item_order": "SOURCE",
            "bin_order": "SOURCE",
            "seed": 42,
            "repetition": 0,
            "input_sha256": payload_hash(index_row["sha256"]),
            "input_status": "VALID",
            "capability_status": "SUPPORTED_COMPOSED",
            "run_status": "COMPLETED" if result["status"] in {"OPTIMAL", "FEASIBLE", "INFEASIBLE"} else "ERROR",
            "solution_status": "VALID_COMPLETE" if valid else "NO_SOLUTION" if not has_solution else "INVALID_CERTIFICATE",
            "proof_status": "PROVEN_OPTIMAL" if result["status"] == "OPTIMAL" and valid else "FEASIBLE" if valid else "UNKNOWN",
            "termination_reason": "OPTIMAL" if result["status"] == "OPTIMAL" else "TIME_LIMIT_WITH_INCUMBENT" if result["status"] == "FEASIBLE" else "SOLVER_STATUS",
            "resources": {"solver_s": result["solver_time_s"], "wall_s": result["solver_time_s"]},
            "metrics": {
                "packed_profit": result["packed_profit"],
                "total_available_profit": total_profit,
                "packed_profit_fraction": result["packed_profit"] / total_profit if result["packed_profit"] is not None else None,
                "solver_bound": result["bound"],
                "solver_relative_gap": result["gap"],
                "packed_items": len(result["placements"]),
                "unpacked_items": len(items) - len(result["placements"]),
                "validation_error_count": len(result["validation_errors"]),
                "branches": result["branches"],
                "conflicts": result["conflicts"],
            },
            "artifacts": {
                "input": f"{archive_reference}#{case_name}/input.json",
                "solver_output": f"{archive_reference}#{case_name}/output.json",
                "validation": f"{archive_reference}#{case_name}/validation.json",
            },
        }
        validate_run_record(record)
        records.append(record)
    archive_path = raw_dir / "artifacts.tar.gz"
    with __import__("tarfile").open(archive_path, "w:gz") as archive:
        for path in sorted(work_root.rglob("*")):
            if path.is_file():
                archive.add(path, arcname=path.relative_to(work_root))
    run_path = args.results_root / "runs" / "B03-exact_cp_sat-20s.jsonl"
    run_path.parent.mkdir(parents=True, exist_ok=True)
    run_path.write_text("".join(json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n" for record in records), encoding="utf-8")
    summary = {
        "schema_version": 1,
        "protocol_version": "benchmark-protocol/3",
        "benchmark_id": "B03",
        "problem_variant": "FIXED_XYZ",
        "comparison_track": "EXACT_MODEL",
        "implementation_id": "exact_cp_sat",
        "implementation_version": "9.15.6755",
        "python_version": platform.python_version(),
        "time_limit_s": args.time_limit,
        "instances": len(records),
        "proof_rate": sum(record["proof_status"] == "PROVEN_OPTIMAL" for record in records) / len(records),
        "artifact_archive": archive_reference,
        "artifact_archive_sha256": sha256(archive_path),
        "run_jsonl_sha256": sha256(run_path),
        "runner_sha256": runner_hash,
        "shared_validator_sha256": validator_hash,
        "source_index_sha256": sha256(INDEX_PATH),
    }
    (raw_dir / "metadata.json").write_text(canonical_json(summary), encoding="utf-8")
    (args.results_root / "B03-exact_cp_sat-20s-summary.json").write_text(canonical_json(summary), encoding="utf-8")
    print(str(run_path.relative_to(ROOT)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
