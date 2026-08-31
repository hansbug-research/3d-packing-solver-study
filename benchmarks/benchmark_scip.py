from __future__ import annotations

import json
from time import perf_counter

from pyscipopt import Model, quicksum

from validation import Box, validate_aabbs


def main():
    n, bin_count, edge, item = 9, 2, 10, 5
    model = Model("exact_3d_bin_packing_smoke")
    model.setParam("display/verblevel", 0)
    model.setParam("limits/time", 20.0)
    model.setParam("limits/memory", 1024.0)
    model.setParam("parallel/maxnthreads", 1)
    model.setParam("randomization/randomseedshift", 42)

    used = [model.addVar(vtype="B", name=f"used_{b}") for b in range(bin_count)]
    assigned = [[model.addVar(vtype="B", name=f"a_{i}_{b}") for b in range(bin_count)] for i in range(n)]
    xyz = [[model.addVar(vtype="I", lb=0, ub=edge - item, name=f"p_{i}_{axis}") for axis in range(3)] for i in range(n)]
    for i in range(n):
        model.addCons(quicksum(assigned[i]) == 1)
        for b in range(bin_count):
            model.addCons(assigned[i][b] <= used[b])
    model.addCons(used[0] >= used[1])
    for b in range(bin_count):
        model.addCons(quicksum(item ** 3 * assigned[i][b] for i in range(n)) <= edge ** 3)

    big_m = edge
    for i in range(n):
        for j in range(i + 1, n):
            for b in range(bin_count):
                relative = [model.addVar(vtype="B", name=f"r_{i}_{j}_{b}_{k}") for k in range(6)]
                model.addCons(quicksum(relative) >= assigned[i][b] + assigned[j][b] - 1)
                for axis in range(3):
                    model.addCons(xyz[i][axis] + item <= xyz[j][axis] + big_m * (1 - relative[2 * axis]))
                    model.addCons(xyz[j][axis] + item <= xyz[i][axis] + big_m * (1 - relative[2 * axis + 1]))
    model.setObjective(quicksum(used), "minimize")

    started = perf_counter()
    model.optimize()
    elapsed = perf_counter() - started
    status = str(model.getStatus())
    solution = model.getBestSol()
    placements = []
    if solution is not None:
        for i in range(n):
            bin_id = next(b for b in range(bin_count) if model.getSolVal(solution, assigned[i][b]) > 0.5)
            placements.append(Box(
                f"cube-{i}", str(bin_id),
                *(model.getSolVal(solution, xyz[i][axis]) for axis in range(3)),
                item, item, item, 1,
            ))
    errors = validate_aabbs(placements, {str(b): (edge, edge, edge) for b in range(bin_count)})
    print(json.dumps({
        "library": "PySCIPOpt/SCIP",
        "version": "6.2.1",
        "status": status,
        "objective_bins": model.getObjVal() if solution is not None else None,
        "dual_bound": model.getDualbound(),
        "gap": model.getGap(),
        "elapsed_s": elapsed,
        "nodes": model.getNNodes(),
        "placements": len(placements),
        "validation_errors": errors,
    }, indent=2))


if __name__ == "__main__":
    main()
