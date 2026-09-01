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

## External-library projection campaign

`benchmarks/comprehensive/run_constraint_adapters.py` runs the same B12/B13/B15/B17 fixtures through py3dbp, the Jerry branch, gedex/bp3d and all five u-nesting strategies. These implementations receive a geometry-only projection (all six rotations, no payload/axle/unloading enforcement); the original CSV fields remain in the fixture and are rechecked by an independent validator. Consequently `CONSTRAINT_VIOLATION` is a meaningful result: the library returned a geometric layout, but it cannot satisfy the deleted hard constraint. Skjolber and exact backends remain `ADAPTER_MISSING` until an adapter can preserve the corresponding semantics.

The runner writes one protocol-v3 record per `suite/variant/implementation`, including source-file hashes, command, stdout/stderr, validation errors and runner hash. Its current 64 records are in `results/comprehensive/runs/constraint-adapters-b12-b13-b15-b17.jsonl`; the generated conformance ranking is `results/comprehensive/rankings/constraint-conformance.csv`. Projection records are never merged into a native/full ranking.
