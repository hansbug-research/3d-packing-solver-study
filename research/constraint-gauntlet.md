# Protocol-v3 constraint gauntlet

`benchmarks/comprehensive/run_constraint_gauntlet.py` reruns the checked-in PackingSolver CSV fixtures as protocol-v3 evidence. The fixtures are small, deliberately adversarial cases, not public quality benchmarks:

| Suite | Cases | Required behavior |
|---|---|---|
| B09 | `heterogeneous_large_cheaper`, `heterogeneous_small_cheaper` | Complete placement with total cost 10 in both cost directions |
| B12 | `rotation_required`, `rotation_forbidden` | The first case must be complete using the listed rotation; the second must remain infeasible because neither allowed pose fits the bin |
| B13 | `weight_limit` | Complete placement without exceeding any bin payload |
| B14 | maximum weight above, maximum stack count, nesting height | Complete placement satisfying stack, load-bearing and nesting fields |
| B15 | normal, boundary regression, infeasible axle | Complete normal case; the two infeasible cases must remain incomplete |
| B17 | no unloading constraint, `increasing-x` | Complete placement; the constrained case must preserve group order |

`box` runs B09/B12/B13. `boxstacks` runs B09/B14/B15/B17. Fork and upstream source variants are separate implementation IDs; an upstream dirty checkout is accepted only with `--allow-dirty-source` and its diff hash is recorded.

The runner writes canonical inputs, effective command/configuration, solver output, certificate, independent validation, stdout/stderr and `/usr/bin/time` resource data into `raw/experiments/comprehensive/constraint-gauntlet/`. A tar archive is referenced by each JSONL record, so the record remains reproducible after the temporary run directory is removed. The validator rechecks identity, copies, orientation, AABB bounds, overlap, weight, stack limits, nesting, axle equilibrium and unloading order; it never trusts the solver's feasible flag.
