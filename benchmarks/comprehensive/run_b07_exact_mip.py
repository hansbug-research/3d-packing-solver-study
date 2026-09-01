#!/usr/bin/env python3
"""Run the B07 source-rotation calibration with MIP backends.

The model is deliberately the same integer, axis-aligned model as
``run_b07_exact.py``: each item is optional, allowed source rotations are
explicit binaries, and pairwise non-overlap uses six disjunctive directions.
Only the backend changes, so the results are useful for exact-proof backend
selection rather than as a large-scale heuristic ranking.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import tarfile
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks"))
from run_b07_exact import (  # noqa: E402
    SOURCE_COMMIT,
    SHARED_VALIDATOR,
    discover,
    load_instance,
    payload_hash,
    read_csv,
)
from comprehensive.model import canonical_json, validate_run_record  # noqa: E402
sys.path.insert(0, str(ROOT / "benchmarks" / "campaign" / "python_thpack"))
from model import allowed_oriented_sizes, validate_certificate  # noqa: E402

RUNNER = Path(__file__).resolve()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def solve_mip(instance: Any, backend: str, time_limit: float) -> dict[str, Any]:
    if backend == "scip":
        from pyscipopt import Model, quicksum
        model = Model(f"B07-{instance.family}-{instance.instance_id}")
        model.hideOutput()
        model.setParam("limits/time", time_limit)
        model.setParam("limits/memory", 4096.0)
        model.setParam("parallel/maxnthreads", 1)
        model.setParam("randomization/randomseedshift", 42)
        binary = lambda name: model.addVar(vtype="B", name=name)
        integer = lambda name, upper: model.addVar(vtype="I", lb=0, ub=upper, name=name)
        add = model.addCons
        total = quicksum
    elif backend == "gurobi":
        import gurobipy as gp
        model = gp.Model(f"B07-{instance.family}-{instance.instance_id}")
        model.Params.OutputFlag = 0
        model.Params.TimeLimit = time_limit
        model.Params.Threads = 1
        model.Params.Seed = 42
        binary = lambda name: model.addVar(vtype=gp.GRB.BINARY, name=name)
        integer = lambda name, upper: model.addVar(vtype=gp.GRB.INTEGER, lb=0, ub=upper, name=name)
        add = model.addConstr
        total = gp.quicksum
    elif backend == "cplex":
        from docplex.mp.model import Model
        model = Model(name=f"B07-{instance.family}-{instance.instance_id}")
        model.parameters.timelimit = time_limit
        model.parameters.threads = 1
        model.parameters.randomseed = 42
        binary = model.binary_var
        integer = lambda name, upper: model.integer_var(lb=0, ub=upper, name=name)
        add = model.add_constraint
        total = model.sum
    else:
        raise ValueError(backend)

    items = []
    for item in instance.item_types:
        for copy_index in range(item.copies):
            items.append({"item_id": f"{item.type_id}:{copy_index}", "size": tuple(item.size), "flags": tuple(item.allowed_vertical_dimensions)})
    n = len(items)
    max_axis = max(instance.container)
    big_m = max_axis + max(max(item["size"]) for item in items)
    selected = [binary(f"selected_{i}") for i in range(n)]
    positions = [[integer(f"p_{i}_{axis}", max_axis) for axis in range(3)] for i in range(n)]
    dimensions = [[integer(f"d_{i}_{axis}", max_axis) for axis in range(3)] for i in range(n)]
    orientation_sizes: list[list[tuple[int, int, int]]] = []
    orientation_vars: list[list[Any]] = []
    for i, item in enumerate(items):
        allowed = sorted(allowed_oriented_sizes(item["size"], item["flags"]))
        if not allowed:
            return {"status": "INFEASIBLE", "placements": [], "bound": None, "objective": None, "gap": None, "solver_time_s": 0.0, "nodes": 0}
        orientation_sizes.append(allowed)
        choices = [binary(f"o_{i}_{j}") for j in range(len(allowed))]
        orientation_vars.append(choices)
        add(total(choices) == selected[i])
        for axis in range(3):
            add(dimensions[i][axis] == total(choices[j] * allowed[j][axis] for j in range(len(allowed))))
            add(positions[i][axis] + dimensions[i][axis] <= instance.container[axis] + big_m * (1 - selected[i]))
    for left in range(n):
        for right in range(left + 1, n):
            relative = [binary(f"r_{left}_{right}_{direction}") for direction in range(6)]
            add(total(relative) >= selected[left] + selected[right] - 1)
            for axis in range(3):
                add(positions[left][axis] + dimensions[left][axis] <= positions[right][axis] + big_m * (1 - relative[2 * axis]))
                add(positions[right][axis] + dimensions[right][axis] <= positions[left][axis] + big_m * (1 - relative[2 * axis + 1]))
    objective_expr = total(items[i]["size"][0] * items[i]["size"][1] * items[i]["size"][2] * selected[i] for i in range(n))
    if backend == "scip":
        model.setObjective(objective_expr, "maximize")
    elif backend == "gurobi":
        import gurobipy as gp
        model.setObjective(objective_expr, gp.GRB.MAXIMIZE)
    else:
        model.maximize(objective_expr)

    started = perf_counter()
    if backend == "scip":
        model.optimize()
        elapsed = perf_counter() - started
        status = str(model.getStatus()).lower()
        mapped = "OPTIMAL" if status == "optimal" else "INFEASIBLE" if status == "infeasible" else "TIME_LIMIT" if status == "timelimit" else status.upper()
        solution = model.getBestSol()
        has_solution = solution is not None and mapped != "INFEASIBLE"
        value = lambda var: model.getSolVal(solution, var)
        objective = model.getObjVal() if has_solution else None
        bound = model.getDualbound() if mapped != "INFEASIBLE" else None
        nodes = model.getNNodes()
    elif backend == "gurobi":
        import gurobipy as gp
        model.optimize()
        elapsed = perf_counter() - started
        mapped = {gp.GRB.OPTIMAL: "OPTIMAL", gp.GRB.INFEASIBLE: "INFEASIBLE", gp.GRB.TIME_LIMIT: "TIME_LIMIT"}.get(model.Status, str(model.Status))
        has_solution = model.SolCount > 0 and mapped != "INFEASIBLE"
        value = lambda var: var.X
        objective = model.ObjVal if has_solution else None
        bound = model.ObjBound if mapped != "INFEASIBLE" else None
        nodes = model.NodeCount
    else:
        solution = model.solve(log_output=False)
        elapsed = perf_counter() - started
        raw = (model.solve_details.status or "unknown").lower()
        mapped = "OPTIMAL" if solution is not None and "optimal" in raw else "INFEASIBLE" if "infeasible" in raw else "TIME_LIMIT" if "time" in raw else raw.upper()
        has_solution = solution is not None and mapped != "INFEASIBLE"
        value = lambda var: solution.get_value(var)
        objective = solution.objective_value if has_solution else None
        bound = getattr(model.solve_details, "best_bound", None) if mapped != "INFEASIBLE" else None
        nodes = getattr(model.solve_details, "nb_nodes_processed", None)

    placements: list[dict[str, Any]] = []
    if has_solution:
        for i, item in enumerate(items):
            if value(selected[i]) < 0.5:
                continue
            placements.append({"item_id": item["item_id"], "bin_id": "bin-000", "x": round(value(positions[i][0])), "y": round(value(positions[i][1])), "z": round(value(positions[i][2])), "dx": round(value(dimensions[i][0])), "dy": round(value(dimensions[i][1])), "dz": round(value(dimensions[i][2]))})
    errors = validate_certificate(instance, placements, require_complete=False)
    packed_volume = sum(p["dx"] * p["dy"] * p["dz"] for p in placements) if has_solution else None
    gap = None if objective is None or bound is None or bound <= 0 or mapped == "OPTIMAL" else max(0.0, (float(bound) - float(objective)) / float(bound))
    return {"status": mapped, "placements": placements, "packed_volume": packed_volume, "objective": objective, "bound": bound, "gap": 0.0 if mapped == "OPTIMAL" and not errors else gap, "solver_time_s": elapsed, "nodes": nodes, "validation_errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("scip", "gurobi", "cplex"), required=True)
    parser.add_argument("--source-root", type=Path, default=ROOT / ".cache" / "packingsolver-fork" / "data" / "box" / "davies1999")
    parser.add_argument("--max-items", type=int, default=60)
    parser.add_argument("--time-limit", type=float, default=20.0)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    candidates = discover(args.source_root, args.max_items, args.limit)
    if not candidates:
        raise SystemExit("no B07 instances satisfy the item limit")
    impl_id = {"scip": "exact_scip", "gurobi": "exact_gurobi", "cplex": "exact_cplex"}[args.backend]
    raw_dir = ROOT / "raw" / "experiments" / "comprehensive" / "B07" / impl_id / f"{args.time_limit:g}s"
    cases_dir = raw_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for source_id, group, item_path, bin_path, item_count in candidates:
        instance, input_payload = load_instance(source_id, group, item_path, bin_path)
        try:
            result = solve_mip(instance, args.backend, args.time_limit)
        except Exception as exc:  # backend license/runtime failures are evidence, not a harness crash
            result = {
                "status": "ERROR",
                "placements": [],
                "packed_volume": None,
                "objective": None,
                "bound": None,
                "gap": None,
                "solver_time_s": 0.0,
                "nodes": None,
                "validation_errors": [],
                "error": f"{type(exc).__name__}: {exc}",
            }
        case_dir = cases_dir / source_id
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "input.json").write_text(canonical_json(input_payload), encoding="utf-8")
        (case_dir / "output.json").write_text(canonical_json(result), encoding="utf-8")
        (case_dir / "validation.json").write_text(canonical_json({"status": "PASS" if not result.get("validation_errors") else "FAIL", "errors": result.get("validation_errors", [])}), encoding="utf-8")
        valid = result["status"] in {"OPTIMAL", "TIME_LIMIT"} and not result.get("validation_errors")
        solution_status = "VALID_PARTIAL" if valid else "NO_SOLUTION" if result["status"] in {"INFEASIBLE", "TIME_LIMIT", "ERROR"} else "INVALID_CERTIFICATE"
        record = {
            "schema_version": 2, "protocol_version": "benchmark-protocol/3", "record_origin": "PROTOCOL_V3",
            "run_id": f"B07/SOURCE_ROTATION_FLAGS/{source_id}/{impl_id}/{args.time_limit:g}s/EXACT_MODEL/rep-0",
            "benchmark_id": "B07", "problem_variant": "SOURCE_ROTATION_FLAGS", "instance_id": source_id,
            "implementation_id": impl_id, "algorithm": f"source-pose volume {args.backend.upper()}", "adapter": f"run_b07_exact_mip.py/{args.backend}",
            "comparison_track": "EXACT_MODEL", "problem_scope": "FULL_PROBLEM", "budget": {"time_limit_s": args.time_limit, "memory_limit_bytes": 4294967296, "thread_limit": 1},
            "item_order": "SOURCE", "bin_order": "SOURCE", "seed": 42, "repetition": 0, "input_sha256": payload_hash(input_payload), "input_status": "VALID", "capability_status": "SUPPORTED_NATIVE",
            "run_status": "TIME_LIMIT" if result["status"] == "TIME_LIMIT" else "ERROR" if result["status"] == "ERROR" else "COMPLETED", "solution_status": solution_status,
            "proof_status": "PROVEN_OPTIMAL" if result["status"] == "OPTIMAL" and valid else "FEASIBLE" if valid else "PROVEN_INFEASIBLE" if result["status"] == "INFEASIBLE" else "UNKNOWN",
            "termination_reason": result.get("error", result["status"]), "resources": {"solver_s": result.get("solver_time_s"), "wall_s": result.get("solver_time_s"), "peak_rss_bytes": None},
            "metrics": {"packed_items": len(result.get("placements", [])), "required_items": instance.item_count, "packed_volume": result.get("packed_volume"), "volume_utilization": result.get("packed_volume") / instance.container_volume if result.get("packed_volume") is not None else None, "solver_bound": result.get("bound"), "gap": result.get("gap"), "nodes": result.get("nodes"), "validation_error_count": len(result.get("validation_errors", [])), "backend": args.backend, "backend_error": result.get("error"), "source_group": group, "source_item_count": item_count, "source_items_sha256": input_payload["source_items_sha256"], "source_bins_sha256": input_payload["source_bins_sha256"], "runner_sha256": sha256(RUNNER)},
            "artifacts": {"input": f"raw/experiments/comprehensive/B07/{impl_id}/{args.time_limit:g}s/cases/{source_id}/input.json", "solver_output": f"raw/experiments/comprehensive/B07/{impl_id}/{args.time_limit:g}s/cases/{source_id}/output.json", "validation": f"raw/experiments/comprehensive/B07/{impl_id}/{args.time_limit:g}s/cases/{source_id}/validation.json"},
        }
        validate_run_record(record)
        records.append(record)
    archive_path = raw_dir / "artifacts.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for path in sorted(cases_dir.rglob("*")):
            if path.is_file():
                archive.add(path, arcname=path.relative_to(raw_dir))
    output = ROOT / "results" / "comprehensive" / "runs" / f"B07-{impl_id}-{args.time_limit:g}s.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n" for record in sorted(records, key=lambda row: row["run_id"])), encoding="utf-8")
    (raw_dir / "metadata.json").write_text(canonical_json({"schema_version": 1, "protocol_version": "benchmark-protocol/3", "benchmark_id": "B07", "implementation_id": impl_id, "backend": args.backend, "instances": len(records), "time_limit_s": args.time_limit, "runner_sha256": sha256(RUNNER), "shared_validator_sha256": sha256(SHARED_VALIDATOR), "output_sha256": sha256(output), "archive_sha256": sha256(archive_path), "python_version": platform.python_version()}), encoding="utf-8")
    print(output.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
