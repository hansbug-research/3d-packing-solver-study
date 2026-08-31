from __future__ import annotations

import argparse
import contextlib
import io
import json
import platform
import sys
from dataclasses import dataclass
from itertools import permutations
from time import perf_counter
from typing import Any, Callable

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from validation import Box, validate_aabbs


@dataclass(frozen=True)
class Item:
    ref: str
    dimensions: tuple[int, int, int]
    weight: int
    orientations: tuple[tuple[int, int, int], ...]


@dataclass(frozen=True)
class Bin:
    ref: str
    dimensions: tuple[int, int, int]
    capacity: int
    cost: int


@dataclass(frozen=True)
class Case:
    name: str
    items: tuple[Item, ...]
    bins: tuple[Bin, ...]
    expected_status: str
    expected_objective: int | None
    purpose: str


def rotations(dimensions: tuple[int, int, int]) -> tuple[tuple[int, int, int], ...]:
    return tuple(sorted(set(permutations(dimensions))))


def make_cases() -> tuple[Case, ...]:
    cube = lambda ref, edge=5, weight=1: Item(ref, (edge, edge, edge), weight, ((edge, edge, edge),))
    return (
        Case(
            "grid_8",
            tuple(cube(f"cube-{i}") for i in range(8)),
            (Bin("bin-0", (10, 10, 10), 100, 1),),
            "OPTIMAL",
            1,
            "A full 2x2x2 grid checks assignment and pairwise non-overlap without rotation.",
        ),
        Case(
            "overflow_9",
            tuple(cube(f"cube-{i}") for i in range(9)),
            tuple(Bin(f"bin-{i}", (10, 10, 10), 100, 1) for i in range(2)),
            "OPTIMAL",
            2,
            "The ninth cube forces a second bin and gives a hand-checkable lower bound.",
        ),
        Case(
            "rotation_required",
            (Item("rotated", (3, 2, 4), 1, rotations((3, 2, 4))),),
            (Bin("bin-0", (4, 3, 2), 100, 1),),
            "OPTIMAL",
            1,
            "The item fits only after choosing a permitted axis-aligned orientation.",
        ),
        Case(
            "rotation_forbidden",
            (Item("upright", (3, 2, 4), 1, ((3, 2, 4),)),),
            (Bin("bin-0", (4, 3, 2), 100, 1),),
            "INFEASIBLE",
            None,
            "The same geometry must be rejected when the required orientation is absent.",
        ),
        Case(
            "weight_split",
            tuple(cube(f"heavy-{i}", edge=4, weight=6) for i in range(3)),
            tuple(Bin(f"bin-{i}", (10, 10, 10), 10, 1) for i in range(3)),
            "OPTIMAL",
            3,
            "Geometry permits one bin, but payload capacity forces one item per bin.",
        ),
        Case(
            "heterogeneous_large_cheaper",
            tuple(Item(f"item-{i}", (6, 5, 5), 1, ((6, 5, 5),)) for i in range(2)),
            (
                Bin("small-0", (6, 5, 5), 100, 7),
                Bin("small-1", (6, 5, 5), 100, 7),
                Bin("large-0", (12, 5, 5), 100, 10),
            ),
            "OPTIMAL",
            10,
            "One large bin is cheaper than two small bins, despite using fewer candidate rows last.",
        ),
        Case(
            "heterogeneous_small_cheaper",
            tuple(Item(f"item-{i}", (6, 5, 5), 1, ((6, 5, 5),)) for i in range(2)),
            (
                Bin("small-0", (6, 5, 5), 100, 5),
                Bin("small-1", (6, 5, 5), 100, 5),
                Bin("large-0", (12, 5, 5), 100, 20),
            ),
            "OPTIMAL",
            10,
            "Reversing costs must reverse the choice and rules out a hard-coded large-bin preference.",
        ),
    )


def validate_solution(case: Case, placements: list[dict[str, Any]], used_bins: list[str], objective: float | None) -> list[str]:
    errors: list[str] = []
    if case.expected_status == "INFEASIBLE":
        if placements:
            errors.append("infeasible case returned placements")
        return errors
    item_by_ref = {item.ref: item for item in case.items}
    bin_by_ref = {bin_.ref: bin_ for bin_ in case.bins}
    placement_refs = [p["item_ref"] for p in placements]
    if sorted(placement_refs) != sorted(item_by_ref):
        errors.append(f"placement refs differ: {sorted(placement_refs)}")
    if len(placement_refs) != len(set(placement_refs)):
        errors.append("duplicate item placement")
    if sorted(set(used_bins)) != sorted(used_bins):
        errors.append("used bin ids are duplicated")
    if any(ref not in bin_by_ref for ref in used_bins):
        errors.append("solution uses an unknown bin")
    boxes: list[Box] = []
    for placement in placements:
        item = item_by_ref.get(placement["item_ref"])
        if item is None:
            continue
        oriented = tuple(int(round(placement[k])) for k in ("dx", "dy", "dz"))
        if oriented not in item.orientations:
            errors.append(f"{item.ref}: orientation {oriented} is not permitted")
        boxes.append(Box(
            item.ref,
            placement["bin_ref"],
            *[float(placement[k]) for k in ("x", "y", "z", "dx", "dy", "dz")],
            item.weight,
        ))
    sizes = {ref: bin_by_ref[ref].dimensions for ref in used_bins if ref in bin_by_ref}
    capacities = {ref: bin_by_ref[ref].capacity for ref in used_bins if ref in bin_by_ref}
    errors.extend(validate_aabbs(boxes, sizes, capacities))
    recalculated = sum(bin_by_ref[ref].cost for ref in used_bins if ref in bin_by_ref)
    if objective is None or abs(objective - recalculated) > 1e-6:
        errors.append(f"reported objective {objective} differs from recalculated cost {recalculated}")
    if case.expected_objective is not None and recalculated != case.expected_objective:
        errors.append(f"cost {recalculated} differs from expected {case.expected_objective}")
    return errors


def solve_cp_sat(case: Case, time_limit: float, formulation: str = "strengthened") -> dict[str, Any]:
    from ortools.sat.python import cp_model

    model = cp_model.CpModel()
    n, m = len(case.items), len(case.bins)
    max_axis = max(max(bin_.dimensions) for bin_ in case.bins)
    assign = [[model.new_bool_var(f"a_{i}_{b}") for b in range(m)] for i in range(n)]
    used = [model.new_bool_var(f"u_{b}") for b in range(m)]
    orient = [[model.new_bool_var(f"o_{i}_{r}") for r in range(len(item.orientations))] for i, item in enumerate(case.items)]
    xyz = [[model.new_int_var(0, max_axis, f"p_{i}_{axis}") for axis in range(3)] for i in range(n)]
    dims = [[model.new_int_var(0, max_axis, f"d_{i}_{axis}") for axis in range(3)] for i in range(n)]
    for i, item in enumerate(case.items):
        model.add_exactly_one(assign[i])
        model.add_exactly_one(orient[i])
        for axis in range(3):
            model.add(dims[i][axis] == sum(orient[i][r] * item.orientations[r][axis] for r in range(len(item.orientations))))
        for b, bin_ in enumerate(case.bins):
            model.add_implication(assign[i][b], used[b])
            for axis in range(3):
                model.add(xyz[i][axis] + dims[i][axis] <= bin_.dimensions[axis]).only_enforce_if(assign[i][b])
    for b, bin_ in enumerate(case.bins):
        model.add(sum(case.items[i].weight * assign[i][b] for i in range(n)) <= bin_.capacity * used[b])
        model.add(used[b] <= sum(assign[i][b] for i in range(n)))
        if formulation == "strengthened":
            model.add(sum(
                case.items[i].dimensions[0] * case.items[i].dimensions[1] * case.items[i].dimensions[2] * assign[i][b]
                for i in range(n)
            ) <= bin_.dimensions[0] * bin_.dimensions[1] * bin_.dimensions[2] * used[b])
        if formulation == "strengthened" and b > 0 and case.bins[b - 1].dimensions == bin_.dimensions and case.bins[b - 1].capacity == bin_.capacity and case.bins[b - 1].cost == bin_.cost:
            model.add(used[b - 1] >= used[b])
    for i in range(n):
        for j in range(i + 1, n):
            for b in range(m):
                relative = [model.new_bool_var(f"r_{i}_{j}_{b}_{k}") for k in range(6)]
                model.add(sum(relative) >= assign[i][b] + assign[j][b] - 1)
                if formulation == "legacy":
                    for direction in relative:
                        model.add(direction <= assign[i][b])
                        model.add(direction <= assign[j][b])
                for axis in range(3):
                    model.add(xyz[i][axis] + dims[i][axis] <= xyz[j][axis]).only_enforce_if(relative[2 * axis])
                    model.add(xyz[j][axis] + dims[j][axis] <= xyz[i][axis]).only_enforce_if(relative[2 * axis + 1])
    model.minimize(sum(case.bins[b].cost * used[b] for b in range(m)))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 42
    started = perf_counter()
    status_code = solver.solve(model)
    elapsed = perf_counter() - started
    status = solver.status_name(status_code)
    has_solution = status in {"OPTIMAL", "FEASIBLE"}
    used_bins = [case.bins[b].ref for b in range(m) if has_solution and solver.value(used[b])]
    placements = []
    if has_solution:
        for i, item in enumerate(case.items):
            b = next(b for b in range(m) if solver.value(assign[i][b]))
            placements.append({
                "item_ref": item.ref,
                "bin_ref": case.bins[b].ref,
                **{k: solver.value(xyz[i][axis]) for axis, k in enumerate(("x", "y", "z"))},
                **{k: solver.value(dims[i][axis]) for axis, k in enumerate(("dx", "dy", "dz"))},
            })
    bound = solver.best_objective_bound if status != "INFEASIBLE" else None
    return {
        "status": status,
        "objective": solver.objective_value if has_solution else None,
        "bound": bound,
        "gap": 0.0 if status == "OPTIMAL" else None,
        "solver_time_s": elapsed,
        "nodes_or_branches": solver.num_branches,
        "conflicts": solver.num_conflicts,
        "used_bins": used_bins,
        "placements": placements,
    }


def _solve_mip(case: Case, backend: str, time_limit: float, formulation: str = "strengthened") -> dict[str, Any]:
    if backend == "scip":
        from pyscipopt import Model, quicksum

        model = Model(case.name)
        model.setParam("display/verblevel", 0)
        model.setParam("limits/time", time_limit)
        model.setParam("limits/memory", 1024.0)
        model.setParam("parallel/maxnthreads", 1)
        model.setParam("randomization/randomseedshift", 42)
        binary = lambda name: model.addVar(vtype="B", name=name)
        integer = lambda lb, ub, name: model.addVar(vtype="I", lb=lb, ub=ub, name=name)
        add = model.addCons
        total = quicksum
    elif backend == "gurobi":
        import gurobipy as gp

        model = gp.Model(case.name)
        model.Params.OutputFlag = 0
        model.Params.TimeLimit = time_limit
        model.Params.Threads = 1
        model.Params.Seed = 42
        binary = lambda name: model.addVar(vtype=gp.GRB.BINARY, name=name)
        integer = lambda lb, ub, name: model.addVar(vtype=gp.GRB.INTEGER, lb=lb, ub=ub, name=name)
        add = model.addConstr
        total = gp.quicksum
    elif backend == "cplex":
        from docplex.mp.model import Model

        model = Model(name=case.name)
        model.parameters.timelimit = time_limit
        model.parameters.threads = 1
        model.parameters.randomseed = 42
        binary = model.binary_var
        integer = lambda lb, ub, name: model.integer_var(lb=lb, ub=ub, name=name)
        add = model.add_constraint
        total = model.sum
    else:
        raise ValueError(backend)

    n, m = len(case.items), len(case.bins)
    max_axis = max(max(bin_.dimensions) for bin_ in case.bins)
    max_item_axis = max(max(item.dimensions) for item in case.items)
    big_m = max_axis + max_item_axis
    assign = [[binary(f"a_{i}_{b}") for b in range(m)] for i in range(n)]
    used = [binary(f"u_{b}") for b in range(m)]
    orient = [[binary(f"o_{i}_{r}") for r in range(len(item.orientations))] for i, item in enumerate(case.items)]
    xyz = [[integer(0, max_axis, f"p_{i}_{axis}") for axis in range(3)] for i in range(n)]
    dims = [[integer(0, max_axis, f"d_{i}_{axis}") for axis in range(3)] for i in range(n)]
    for i, item in enumerate(case.items):
        add(total(assign[i]) == 1)
        add(total(orient[i]) == 1)
        for axis in range(3):
            add(dims[i][axis] == total(orient[i][r] * item.orientations[r][axis] for r in range(len(item.orientations))))
        for b, bin_ in enumerate(case.bins):
            add(assign[i][b] <= used[b])
            for axis in range(3):
                add(xyz[i][axis] + dims[i][axis] <= bin_.dimensions[axis] + big_m * (1 - assign[i][b]))
    for b, bin_ in enumerate(case.bins):
        add(total(case.items[i].weight * assign[i][b] for i in range(n)) <= bin_.capacity * used[b])
        add(used[b] <= total(assign[i][b] for i in range(n)))
        if formulation == "strengthened":
            add(total(
                case.items[i].dimensions[0] * case.items[i].dimensions[1] * case.items[i].dimensions[2] * assign[i][b]
                for i in range(n)
            ) <= bin_.dimensions[0] * bin_.dimensions[1] * bin_.dimensions[2] * used[b])
        if formulation == "strengthened" and b > 0 and case.bins[b - 1].dimensions == bin_.dimensions and case.bins[b - 1].capacity == bin_.capacity and case.bins[b - 1].cost == bin_.cost:
            add(used[b - 1] >= used[b])
    for i in range(n):
        for j in range(i + 1, n):
            for b in range(m):
                relative = [binary(f"r_{i}_{j}_{b}_{k}") for k in range(6)]
                add(total(relative) >= assign[i][b] + assign[j][b] - 1)
                if formulation == "legacy":
                    for direction in relative:
                        add(direction <= assign[i][b])
                        add(direction <= assign[j][b])
                for axis in range(3):
                    add(xyz[i][axis] + dims[i][axis] <= xyz[j][axis] + big_m * (1 - relative[2 * axis]))
                    add(xyz[j][axis] + dims[j][axis] <= xyz[i][axis] + big_m * (1 - relative[2 * axis + 1]))
    objective_expr = total(case.bins[b].cost * used[b] for b in range(m))
    if backend == "scip":
        model.setObjective(objective_expr, "minimize")
        started = perf_counter()
        model.optimize()
        elapsed = perf_counter() - started
        solution = model.getBestSol()
        raw_status = str(model.getStatus())
        status = {"optimal": "OPTIMAL", "infeasible": "INFEASIBLE", "timelimit": "TIME_LIMIT"}.get(raw_status, raw_status.upper())
        value: Callable[[Any], float] = lambda var: model.getSolVal(solution, var)
        objective = model.getObjVal() if solution is not None else None
        bound = model.getDualbound() if status != "INFEASIBLE" else None
        gap = model.getGap() if solution is not None else None
        nodes = model.getNNodes()
        version = __import__("pyscipopt").__version__
    elif backend == "gurobi":
        import gurobipy as gp

        model.setObjective(objective_expr, gp.GRB.MINIMIZE)
        started = perf_counter()
        model.optimize()
        elapsed = perf_counter() - started
        status = {gp.GRB.OPTIMAL: "OPTIMAL", gp.GRB.INFEASIBLE: "INFEASIBLE", gp.GRB.TIME_LIMIT: "TIME_LIMIT"}.get(model.Status, str(model.Status))
        solution = model.SolCount > 0
        value = lambda var: var.X
        objective = model.ObjVal if solution else None
        bound = model.ObjBound if status != "INFEASIBLE" else None
        gap = model.MIPGap if solution else None
        nodes = model.NodeCount
        version = ".".join(map(str, gp.gurobi.version()))
    else:
        model.minimize(objective_expr)
        started = perf_counter()
        solution = model.solve(log_output=False)
        elapsed = perf_counter() - started
        details = model.solve_details
        raw_status = (details.status or "unknown").lower()
        if solution is not None and "optimal" in raw_status:
            status = "OPTIMAL"
        elif "infeasible" in raw_status:
            status = "INFEASIBLE"
        elif "time" in raw_status:
            status = "TIME_LIMIT"
        else:
            status = raw_status.upper()
        value = lambda var: solution.get_value(var)
        objective = solution.objective_value if solution is not None else None
        bound = getattr(details, "best_bound", None) if status != "INFEASIBLE" else None
        gap = getattr(details, "mip_relative_gap", None)
        nodes = getattr(details, "nb_nodes_processed", None)
        version = __import__("cplex").__version__

    has_solution = solution is not None and status != "INFEASIBLE"
    used_bins = [case.bins[b].ref for b in range(m) if has_solution and value(used[b]) > 0.5]
    placements = []
    if has_solution:
        for i, item in enumerate(case.items):
            bin_index = next(b for b in range(m) if value(assign[i][b]) > 0.5)
            placements.append({
                "item_ref": item.ref,
                "bin_ref": case.bins[bin_index].ref,
                **{k: round(value(xyz[i][axis])) for axis, k in enumerate(("x", "y", "z"))},
                **{k: round(value(dims[i][axis])) for axis, k in enumerate(("dx", "dy", "dz"))},
            })
    return {
        "status": status,
        "objective": objective,
        "bound": bound,
        "gap": gap,
        "solver_time_s": elapsed,
        "nodes_or_branches": nodes,
        "used_bins": used_bins,
        "placements": placements,
        "version": version,
    }


def solve_case(case: Case, backend: str, time_limit: float, formulation: str = "strengthened") -> dict[str, Any]:
    started = perf_counter()
    try:
        backend_log = io.StringIO()
        with contextlib.redirect_stdout(backend_log):
            result = solve_cp_sat(case, time_limit, formulation) if backend == "cp-sat" else _solve_mip(case, backend, time_limit, formulation)
        if backend_log.getvalue():
            result["backend_log"] = backend_log.getvalue()
    except Exception as exc:
        return {
            "case": case.name,
            "purpose": case.purpose,
            "expected_status": case.expected_status,
            "expected_objective": case.expected_objective,
            "status": "ERROR",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "wall_time_s": perf_counter() - started,
            "validation_errors": ["solver did not return a checkable result"],
        }
    result["wall_time_s"] = perf_counter() - started
    result["case"] = case.name
    result["purpose"] = case.purpose
    result["expected_status"] = case.expected_status
    result["expected_objective"] = case.expected_objective
    result["formulation"] = formulation
    errors = validate_solution(case, result.get("placements", []), result.get("used_bins", []), result.get("objective"))
    if result["status"] != case.expected_status:
        errors.append(f"status {result['status']} differs from expected {case.expected_status}")
    result["validation_errors"] = errors
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("cp-sat", "scip", "gurobi", "cplex"), required=True)
    parser.add_argument("--time-limit", type=float, default=20.0)
    parser.add_argument("--formulation", choices=("legacy", "reduced", "strengthened"), default="strengthened")
    args = parser.parse_args()
    cases = [solve_case(case, args.backend, args.time_limit, args.formulation) for case in make_cases()]
    versions: dict[str, str] = {"python": platform.python_version()}
    if args.backend == "cp-sat":
        versions["ortools"] = __import__("ortools").__version__
    elif args.backend == "scip":
        versions["pyscipopt"] = __import__("pyscipopt").__version__
    elif args.backend == "gurobi":
        import gurobipy as gp

        versions["gurobi"] = ".".join(map(str, gp.gurobi.version()))
    else:
        versions["cplex"] = __import__("cplex").__version__
        versions["docplex"] = __import__("docplex").__version__
    suite_status = "PASS" if all(
        case["status"] == case["expected_status"] and not case["validation_errors"]
        for case in cases
    ) else "FAIL"
    print(json.dumps({
        "schema_version": 1,
        "suite": "exact-small-3d/2",
        "backend": args.backend,
        "formulation": args.formulation,
        "suite_status": suite_status,
        "versions": versions,
        "parameters": {"time_limit_s": args.time_limit, "threads": 1, "seed": 42},
        "cases": cases,
    }, indent=2))
    if suite_status != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
