Fixes #536

## Summary

- `Objective::VariableSizedBinPacking` is advertised for both the `box` and the `boxstacks` solver and is handled all along their optimization pipelines, but neither `Solution::operator<` had a case for it, so every comparison of two feasible solutions fell through to the `default` branch and threw `std::logic_error`. The objective was unusable in both solvers.
- Added the missing case to both comparators, using the same comparison `rectangle::Solution::operator<` and `onedimensional::Solution::operator<` already use, in the same position in the switch (right after `Objective::Feasibility`).

## Changes

**`src/box/solution.cpp`, `src/boxstacks/solution.cpp`** — two lines each:

```cpp
} case Objective::VariableSizedBinPacking: {
    return strictly_lesser_cost(solution.cost(), cost());
```

Both places are needed. `boxstacks` first computes a `box` relaxation bound (`optimize_box_bound`, `src/boxstacks/optimize.cpp:158`), which runs the full `box::optimize`, so the unpatched `boxstacks` binary reports `box::Solution` in its error message; with only `src/box/solution.cpp` fixed, the failure moves one level up to `boxstacks::Solution::operator<`.

**`test/box/box_test.cpp`, `test/boxstacks/boxstacks_test.cpp`** — one solution comparison test each, built from the `InstanceBuilder` and `SolutionBuilder` APIs so they need no LP solver, no data file and no optimize run. Each test builds two feasible, full solutions of the same instance, one using two bins of cost 7 and one using a single bin of cost 10, and checks that the cheaper one compares as the better solution in both directions. `test/box/box_test.cpp` currently has all of its content commented out, so the test comes with the includes it needs, placed at the top of the file with the test itself after the commented-out block, which is left untouched.

## Test plan

- [x] Both new tests fail on `master` (`std::logic_error` from the `default` branch) and pass with this change.
- [x] Full build, default configuration (`-DCMAKE_BUILD_TYPE=Release`, CLP and HiGHS both on, `liblapack-dev` and `libbz2-dev` installed, as in `.github/workflows/build.yml`).
- [x] `ctest --output-on-failure --parallel 8` in `build/test`: 598 tests pass, which is the 596 on `master` plus the two added here.
- [x] The reproducer from #536 now returns one bin of type 1 with a cost of 10 and 2/2 items packed, for both `packingsolver_box` and `packingsolver_boxstacks`, over 5 runs each.
- [x] Checked the direction of the comparison with an inverted cost structure (bin type 0 at cost 5 with 2 copies, bin type 1 at cost 20 with 1 copy): both solvers then select the two cheaper bins for a total cost of 10.

Environment: Ubuntu 24.04.3 LTS, x86-64, glibc 2.39, GCC 13.3.0, CMake 4.4.3.
