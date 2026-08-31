Build fails with `-DPACKINGSOLVER_USE_HIGHS=OFF`: `'solution' was not declared in this scope`

---

Hello Florian,

`PACKINGSOLVER_USE_HIGHS` is an option in the top-level `CMakeLists.txt`, but turning it off makes the build fail. In `src/rectangle/conservative_scales.cpp`, the `solution` vector is declared inside an `#ifdef HIGHS_FOUND` block and used after the corresponding `#endif`, so that translation unit does not compile when the macro is undefined. This is independent of `PACKINGSOLVER_USE_CLP`, since that file has no CLP path at all. I ran into it while trying to build a HiGHS-free binary to check whether an unrelated failure I was seeing depended on the LP backend.

**Version**

```text
commit: 367ebfdaad11424ded3696b7dae799a30c1375d0
```

**Environment**

```text
Ubuntu 24.04.3 LTS, x86-64, glibc 2.39
GCC 13.3.0, CMake 4.4.3, Unix Makefiles generator
liblapack-dev and libbz2-dev installed, as in .github/workflows/build.yml
```

**Reproducer**

From a fresh checkout and a fresh build directory:

```shell
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DPACKINGSOLVER_USE_HIGHS=OFF
cmake --build build --config Release --parallel
```

Configuration succeeds; the build then stops while compiling `src/rectangle/conservative_scales.cpp`, which is one source among 22 in `PackingSolver_rectangle`, so with `--parallel` the other objects of that target compile first and the errors are interleaved with them.

**Actual result**

Paths shortened to the repository root:

```text
Building CXX object src/rectangle/CMakeFiles/PackingSolver_rectangle.dir/conservative_scales.cpp.o
src/rectangle/conservative_scales.cpp: In function ‘std::vector<double> {anonymous}::solve_conservative_scale_lp(const std::vector<long int>&, packingsolver::Length, const std::vector<double>&)’:
src/rectangle/conservative_scales.cpp:129:28: error: ‘solution’ was not declared in this scope
  129 |             double value = solution[variable_pos[copy_id]];
      |                            ^~~~~~~~
src/rectangle/conservative_scales.cpp:162:45: error: ‘solution’ was not declared in this scope
  162 |             achieved += selected[copy_id] * solution[variable_pos[copy_id]];
      |                                             ^~~~~~~~
src/rectangle/conservative_scales.cpp:168:35: error: ‘solution’ was not declared in this scope
  168 |                 result[copy_id] = solution[variable_pos[copy_id]];
      |                                   ^~~~~~~~
```

**Expected result**

The build completes, and `solve_conservative_scale_lp` throws at run time if it is actually reached without HiGHS, which is how the other `HIGHS_FOUND` call sites behave.

**Root cause**

In `solve_conservative_scale_lp`, the declaration sits inside the guarded block:

```cpp
#ifdef HIGHS_FOUND
        Highs highs;
        mathoptsolverscmake::reduce_printout(highs);
        mathoptsolverscmake::load(highs, model);
        mathoptsolverscmake::solve(highs);
        std::vector<double> solution = mathoptsolverscmake::get_solution(highs);
#else
        throw std::invalid_argument(FUNC_SIGNATURE);
#endif
```

The `#else` branch throws, so the code below is unreachable at run time, but it is still compiled, and it reads `solution` at lines 129, 162 and 168.

`HIGHS_FOUND` comes from the `MathOptSolversCMake_mathopt` target, which adds it as a public compile definition only when `MATHOPTSOLVERSCMAKE_USE_HIGHS` is on, and `extern/CMakeLists.txt` switches that on when `PACKINGSOLVER_USE_HIGHS` is on. So a fresh configure with `-DPACKINGSOLVER_USE_HIGHS=OFF` leaves `HIGHS_FOUND` undefined and that file cannot be compiled, whether or not CLP is enabled.

Every other file that uses `HIGHS_FOUND` already declares its result vector before the guard and reads it after the `#endif`: `src/rectangle/onedimentional_contiguity/milp.cpp` (line 353), `src/rectangle/benders_decomposition_contiguity.cpp` (line 1100), `src/irregular/linear_programming.cpp` (lines 566 and 1116), `src/irregular/milp_raster.cpp` (line 412) and `src/onedimensional/milp_assignment.cpp` (line 1522). `milp.cpp` even documents why:

```cpp
    // Only retrieving raw results from HiGHS here (whether it proved the
    // model infeasible, and its solution vector if not); interpreting them
    // into 'result' happens below, after '#endif', so that logic is not
    // duplicated (or silently skipped) when HiGHS is not available.
    bool proven_infeasible = false;
    std::vector<double> solution;
#ifdef HIGHS_FOUND
```

I compiled all six `HIGHS_FOUND` translation units with the macro removed from their real compile commands (taken from `compile_commands.json`, with `-fsyntax-only`): the other five compile cleanly and `conservative_scales.cpp` is the only one where the guard cuts across a variable's scope.

**Why the default CI build does not cover this**

`.github/workflows/build.yml` runs `cmake -S . -B build -DCMAKE_BUILD_TYPE=Release` with no other `-D`, and `release.yml` adds only `-DPACKINGSOLVER_BUILD_TEST=OFF`, so no job ever compiles that file without `HIGHS_FOUND`.

**Suggested fix**

Moving the declaration above the `#ifdef` is enough, which is the pattern already used in the five files listed above:

```cpp
        std::vector<double> solution;
#ifdef HIGHS_FOUND
        Highs highs;
        ...
        solution = mathoptsolverscmake::get_solution(highs);
#else
        throw std::invalid_argument(FUNC_SIGNATURE);
#endif
```

The default configuration is unaffected: `HIGHS_FOUND` is defined there and the generated code is the same.

**What this does not fix**

The compile fix alone does not make a HiGHS-free build usable for `rectangle`. `optimize()` schedules the conservative scales check whenever the objective is `BinPacking` or `Feasibility`, there is a single bin type, all item types are oriented, and the instance has at most 100 items (`src/rectangle/optimize.cpp:1188-1194`); `use_conservative_scales` only forces it beyond that item limit, it is not what enables it. So on an ordinary small oriented bin packing instance, a CLP-only build compiles but then reports `Error: std::vector<double> {anonymous}::solve_conservative_scale_lp(...)` and exits 1. With the declaration moved, a full `-DPACKINGSOLVER_USE_HIGHS=OFF -DPACKINGSOLVER_BUILD_TEST=ON` build completes and `ctest` then reports 65 of 596 tests failing, 33 of them inside `solve_conservative_scale_lp`. That is the state of a configuration that could not be built at all before, not a regression from the fix, but it does mean the option is not usable yet.

One more detail: `extern/CMakeLists.txt` calls `FetchContent_MakeAvailable(highs)` unconditionally, so `PACKINGSOLVER_USE_HIGHS=OFF` still downloads and configures HiGHS, it only stops it from being compiled and linked.

There is a second decision behind this, and it is yours rather than mine: give `solve_conservative_scale_lp` a CLP path, skip the conservative scales task when no LP solver is available, or have CMake reject a configuration with no usable LP solver. I can send the one-line compile fix on its own and follow up with whichever of those you prefer.
