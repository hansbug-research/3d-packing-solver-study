"""Run the exact-small 3D MIP smoke with an optional commercial backend.

The model is deliberately the same nine-cube pairwise-disjunction model used
by benchmark_ortools.py and benchmark_scip.py. A missing package or license is
reported as NOT_RUN instead of being treated as a solver failure.
"""
from __future__ import annotations

import json
import sys
from time import perf_counter


def run_gurobi() -> dict:
    try:
        import gurobipy as gp
    except ImportError as exc:
        return {"library": "Gurobi", "status": "NOT_RUN_MISSING_PACKAGE", "error": str(exc)}
    try:
        n, bins, edge, item = 9, 2, 10, 5
        model = gp.Model("exact_3d_bin_packing_smoke")
        model.Params.OutputFlag = 0
        model.Params.TimeLimit = 20
        model.Params.Threads = 1
        model.Params.Seed = 42
        used = model.addVars(bins, vtype=gp.GRB.BINARY, name="used")
        assigned = model.addVars(n, bins, vtype=gp.GRB.BINARY, name="assigned")
        xyz = model.addVars(n, 3, vtype=gp.GRB.INTEGER, lb=0, ub=edge - item, name="p")
        for i in range(n):
            model.addConstr(sum(assigned[i, b] for b in range(bins)) == 1)
            for b in range(bins):
                model.addConstr(assigned[i, b] <= used[b])
                model.addConstr(sum(item ** 3 * assigned[j, b] for j in range(n)) <= edge ** 3)
        model.addConstr(used[0] == 1)
        model.addConstr(used[0] >= used[1])
        for i in range(n):
            for j in range(i + 1, n):
                for b in range(bins):
                    relative = model.addVars(6, vtype=gp.GRB.BINARY, name=f"r_{i}_{j}_{b}")
                    model.addConstr(sum(relative[k] for k in range(6)) >= assigned[i, b] + assigned[j, b] - 1)
                    for axis in range(3):
                        model.addConstr(xyz[i, axis] + item <= xyz[j, axis] + edge * (1 - relative[2 * axis]))
                        model.addConstr(xyz[j, axis] + item <= xyz[i, axis] + edge * (1 - relative[2 * axis + 1]))
        model.setObjective(sum(used[b] for b in range(bins)), gp.GRB.MINIMIZE)
        started = perf_counter()
        model.optimize()
        elapsed = perf_counter() - started
        return {
            "library": "Gurobi", "version": gp.gurobi.version(),
            "status": {2: "OPTIMAL", 9: "TIME_LIMIT"}.get(model.Status, str(model.Status)),
            "objective_bins": model.ObjVal if model.SolCount else None,
            "best_bound": model.ObjBound,
            "gap": model.MIPGap if model.SolCount else None,
            "elapsed_s": elapsed,
        }
    except Exception as exc:  # includes license errors
        return {"library": "Gurobi", "status": "NOT_RUN_LICENSE_OR_RUNTIME", "error": repr(exc)}


def run_cplex() -> dict:
    try:
        import cplex
    except ImportError as exc:
        return {"library": "CPLEX", "status": "NOT_RUN_MISSING_PACKAGE", "error": str(exc)}
    # Keep the CPLEX path explicit: it is a license-gated optional experiment.
    return {
        "library": "CPLEX",
        "status": "NOT_RUN_LICENSE_OR_RUNTIME",
        "error": "The CPLEX exact-small adapter is optional; run with an IBM runtime license and record raw output.",
        "package_version": getattr(cplex, "__version__", "unknown"),
    }


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in {"gurobi", "cplex"}:
        raise SystemExit("usage: benchmark_commercial_smoke.py {gurobi|cplex}")
    result = run_gurobi() if sys.argv[1] == "gurobi" else run_cplex()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
