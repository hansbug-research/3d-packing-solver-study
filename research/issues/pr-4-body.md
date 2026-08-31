Fixes #539

## Summary

- `compute_axle_weights` divides by `harness_rear_axle_distance` and by `front_axle_middle_axle_distance`. A bin file that gives axle weight limits but no truck geometry leaves both at 0, and `boxstacks::InstanceBuilder::read_bin_types` flags every bin read from a CSV file as a semi-trailer truck, so the divisions produced an infinite rear axle weight and a NaN middle axle weight. The infinite weight exceeds any finite `REAR_AXLE_MAXIMUM_WEIGHT`, so `Solution::feasible_axle_weights` rejected every candidate and the solver returned an empty solution with exit code 0 and no message.
- Skip the axle weights the geometry cannot produce instead of computing them from a zero divisor.

## Changes

**`include/packingsolver/algorithms/truck.hpp`** — two guards in `compute_axle_weights`. Without `harness_rear_axle_distance` neither weight can be computed, since both are derived from `harness_weight`, so the function returns `{0, 0}`. Without `front_axle_middle_axle_distance` only the middle axle weight is lost, so the rear axle stays constrained. The original expression and its variable-name comments are kept as they are.

**`test/algorithms/truck_test.cpp`** (new) — three unit tests: the complete geometry, and each of the two degenerate cases. The first passes both before and after this change, which is what shows the change is inert for a well-formed truck.

I deliberately left two nearby things alone. `compute_axle_weights` also divides by `weight`, which is 0 for an empty bin; that already yields NaN and no violation today. And `read_bin_types` still flags every bin from a CSV file as a semi-trailer truck, which is why the degenerate state is reachable from an ordinary bin file at all; changing that is a policy decision about existing bin files, so it is yours to make rather than mine.

## Test plan

- [x] The two degenerate tests fail on `master` and pass with this change; `Truck.ComputeAxleWeights` passes both ways.
- [x] Full build, default configuration (`-DCMAKE_BUILD_TYPE=Release`, CLP and HiGHS both on, `liblapack-dev` and `libbz2-dev` installed, as in `.github/workflows/build.yml`).
- [x] `ctest --parallel 8` in `build/test`: 599 tests pass, which is the 596 on `master` plus the three added here.
- [x] The reproducer from #539 now packs 3/3 items into one bin instead of returning an empty solution.
- [x] Checked that no constraint that works today is silently dropped: a bin with `IS_SEMI_TRAILER_TRUCK=1`, a full geometry and `FRONT_AXLE_MIDDLE_AXLE_DISTANCE=0` still has its rear axle limit enforced, `REAR_AXLE_MAXIMUM_WEIGHT=4600` giving one bin and `4400` splitting the load into two, both before and after the change.
- [x] Checked that a bin type providing both distances is unaffected, using the semi-trailer instance from #537: it behaves identically on this branch and on `master`.

Environment: Ubuntu 24.04.3 LTS, x86-64, glibc 2.39, GCC 13.3.0, CMake 4.4.3.
