from __future__ import annotations

import json
from time import perf_counter

from ortools.sat.python import cp_model


def main():
    # Nine 5x5x5 cubes in 10x10x10 bins. The pairwise disjunction model proves
    # the exact minimum is two bins. This is a solver smoke test, not a proposed
    # production formulation for large 3D instances.
    n, bin_count, edge, item = 9, 2, 10, 5
    model = cp_model.CpModel()
    bin_of = [model.new_int_var(0, bin_count - 1, f"bin_{i}") for i in range(n)]
    xyz = [[model.new_int_var(0, edge - item, f"p_{i}_{a}") for a in range(3)] for i in range(n)]
    assigned = [[model.new_bool_var(f"a_{i}_{b}") for b in range(bin_count)] for i in range(n)]
    used = [model.new_bool_var(f"used_{b}") for b in range(bin_count)]
    for i in range(n):
        model.add_exactly_one(assigned[i])
        for b in range(bin_count):
            model.add(bin_of[i] == b).only_enforce_if(assigned[i][b])
            model.add_implication(assigned[i][b], used[b])
    model.add(used[0] == 1)
    model.add(used[0] >= used[1])
    for i in range(n):
        for j in range(i + 1, n):
            same = model.new_bool_var(f"same_{i}_{j}")
            model.add(bin_of[i] == bin_of[j]).only_enforce_if(same)
            model.add(bin_of[i] != bin_of[j]).only_enforce_if(same.Not())
            relative = [model.new_bool_var(f"r_{i}_{j}_{k}") for k in range(6)]
            model.add(sum(relative) >= 1).only_enforce_if(same)
            model.add(sum(relative) == 0).only_enforce_if(same.Not())
            for axis in range(3):
                model.add(xyz[i][axis] + item <= xyz[j][axis]).only_enforce_if(relative[2 * axis])
                model.add(xyz[j][axis] + item <= xyz[i][axis]).only_enforce_if(relative[2 * axis + 1])
    model.minimize(sum(used))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 20
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 42
    started = perf_counter()
    status = solver.solve(model)
    elapsed = perf_counter() - started
    print(json.dumps({
        "library": "ortools",
        "version": "9.15.6755",
        "status": solver.status_name(status),
        "objective_bins": solver.objective_value,
        "best_bound": solver.best_objective_bound,
        "elapsed_s": elapsed,
        "conflicts": solver.num_conflicts,
        "branches": solver.num_branches,
    }, indent=2))


if __name__ == "__main__":
    main()
