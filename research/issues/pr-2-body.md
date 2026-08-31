Fixes #537

## Summary

- When a `boxstacks` bin is a semi-trailer truck and the first packing violates the middle axle weight limit, the axle weight repair loop in `sequential_onedimensional_rectangle` left `fixed_items_solutions_pos` equal to `fixed_items_solutions.size()`, and the next iteration read one element past the end of the vector. Copy-constructing a `Solution` from that memory threw `std::bad_array_new_length`, or `std::bad_alloc` depending on the objective.
- The scan that recomputes the index skipped its `break` on the last entry, because the `pos + 1 < fixed_items_solutions.size()` guard is false there, so the counter was incremented one time too many.

## Changes

**`src/boxstacks/sequential_onedimensional_rectangle.cpp`** — one condition, so the scan breaks on the last entry instead of running past it:

```cpp
                if (pos + 1 >= (ItemPos)fixed_items_solutions.size()
                        || fixed_items_solutions[pos + 1].x_max() > xi - x_max)
                    break;
```

Nothing else was needed. The clamp below it only raises the index to the lower bound, and the loop's own end condition covers the case where the last entry does fail the length test: the lower bound then becomes `size()` and the loop breaks before anything is indexed.

## Test plan

- [x] Full build, default configuration (`-DCMAKE_BUILD_TYPE=Release`, CLP and HiGHS both on, `liblapack-dev` and `libbz2-dev` installed, as in `.github/workflows/build.yml`).
- [x] `ctest --parallel 8` in `build/test`: 596 tests pass, unchanged from `master`.
- [x] The reproducer from #537, built from this branch: 3/3 runs exit 0 and write a certificate. The same build with this commit reverted: 3/3 runs fail with `Error: std::bad_array_new_length`.
- [x] Same reproducer with `--objective knapsack` and `--objective feasibility`, which fail with `std::bad_array_new_length` and `std::bad_alloc` on `master`: both exit 0 with this change.
- [x] Confirmed the index really was out of range before the change, by temporarily adding a bounds check in front of the indexing: it reports `fixed_items_solutions_pos 2 with fixed_items_solutions.size() 2` on the second iteration.

I did not add a regression test. Reaching this code needs a full `optimize` run on a semi-trailer instance, and neither `test/boxstacks` nor `data/boxstacks` currently has a data-driven optimize suite to hang it on. If you would like one, I am glad to add it in the shape you prefer, either a `data/boxstacks/tests/...` set like `rectangleguillotine` has, or a unit test on the loop extracted into its own function.

As noted in #537, this stops the crash but the instance still returns an empty solution, which looks like a separate limitation of the repair strategy. This PR does not touch that.

Environment: Ubuntu 24.04.3 LTS, x86-64, glibc 2.39, GCC 13.3.0, CMake 4.4.3.
