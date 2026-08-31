Fixes #538

## Summary

- `-DPACKINGSOLVER_USE_HIGHS=OFF` did not build: in `src/rectangle/conservative_scales.cpp`, `solution` was declared inside the `#ifdef HIGHS_FOUND` block and read after the `#endif` at lines 129, 162 and 168, so the translation unit failed with three `'solution' was not declared in this scope` errors.
- Moved the declaration above the guard, which is the pattern the other five `HIGHS_FOUND` call sites already use (`src/rectangle/onedimentional_contiguity/milp.cpp:353`, `src/rectangle/benders_decomposition_contiguity.cpp:1100`, `src/irregular/linear_programming.cpp:566` and `:1116`, `src/irregular/milp_raster.cpp:412`, `src/onedimensional/milp_assignment.cpp:1522`).

## Changes

**`src/rectangle/conservative_scales.cpp`** — the declaration moves out of the `#ifdef` and the assignment inside it becomes a plain assignment. The comment mirrors the one `milp.cpp` carries for the same reason, so the declaration is not moved back in later.

The default configuration is unaffected: `HIGHS_FOUND` is defined there and the generated code is the same.

## Test plan

- [x] Full build and `ctest --parallel 8` in the default configuration (`-DCMAKE_BUILD_TYPE=Release`, CLP and HiGHS both on): 596 tests pass, unchanged from `master`.
- [x] `cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DPACKINGSOLVER_USE_HIGHS=OFF -DPACKINGSOLVER_BUILD_TEST=ON` followed by `cmake --build build --parallel`: completes with no errors on this branch. The same configuration with this commit reverted stops at `conservative_scales.cpp.o` with the three errors from #538.
- [x] Compiled all six `HIGHS_FOUND` translation units with the macro removed from their real compile commands: after this change all six compile.

One caveat, which #538 covers in more detail: this is a compile fix only. `ctest` in the `PACKINGSOLVER_USE_HIGHS=OFF` build reports 65 of 596 tests failing, 33 of them inside `solve_conservative_scale_lp`, because `optimize()` schedules the conservative scales check for any `BinPacking` or `Feasibility` instance with one bin type, oriented item types and at most 100 items. That is the state of a configuration that could not be built at all before rather than a regression, but the option is not usable until the run-time side is decided as well. I kept that out of this PR since it is a design choice: a CLP path in `solve_conservative_scale_lp`, skipping the task without an LP solver, or having CMake reject such a configuration. Happy to follow up with whichever you prefer.

Environment: Ubuntu 24.04.3 LTS, x86-64, glibc 2.39, GCC 13.3.0, CMake 4.4.3.
