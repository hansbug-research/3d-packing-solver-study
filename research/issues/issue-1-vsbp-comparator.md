[box][boxstacks] `variable-sized-bin-packing` throws in `Solution::operator<` as soon as two bin types remain

---

Hello Florian,

The `variable-sized-bin-packing` objective is listed as supported by both the `box` and the `boxstacks` solver, but as soon as an instance keeps more than one bin type, the run fails: `Solution::operator<` has no case for that objective, so it falls through to its `default` branch and throws. No certificate and no output JSON are written, and the exit code is 1. Instances that reduce to a single bin type do not hit it, because `optimize` then routes the objective to the tree search instead of sequential value correction, so the smallest possible test case does not show the problem.

**Version**

```text
release:      Latest (master), packingsolver-linux-x64.tar.gz, asset updated 2026-08-29
commit:       367ebfdaad11424ded3696b7dae799a30c1375d0
asset SHA256: 1ef068f2041c8199e9ac6ef8a6780b01f636b79b8b2f7e98aaf60360d67c7aa4
```

**Environment**

```text
Ubuntu 24.04.3 LTS, x86-64, glibc 2.39
Intel Core i7-11700
```

**Reproducer**

`items.csv`

```csv
ID,X,Y,Z,ROTATION_XYZ,ROTATION_YXZ,ROTATION_ZYX,ROTATION_YZX,ROTATION_XZY,ROTATION_ZXY,WEIGHT,COPIES
0,6,5,5,1,1,1,1,1,1,1,2
```

`bins.csv`

```csv
ID,X,Y,Z,COST,COPIES,MAXIMUM_WEIGHT
0,6,5,5,7,2,100
1,12,5,5,10,1,100
```

```shell
./packingsolver_box \
        --items items.csv \
        --bins bins.csv \
        --objective variable-sized-bin-packing \
        --linear-programming-solver highs \
        --time-limit 3 \
        --memory-limit 1024 \
        --verbosity-level 0 \
        --certificate solution.csv \
        --output output.json \
        --only-write-at-the-end
```

The same command with `./packingsolver_boxstacks` fails the same way.

**Actual result**

```text
Error: bool packingsolver::box::Solution::operator<(const packingsolver::box::Solution&) const: solution "box::Solution" does not support objective "VariableSizedBinPacking"
```

Exit code 1, no `solution.csv` and no `output.json`. Both binaries fail in under 10 ms, well before the time limit, and the behaviour is the same at `--time-limit 1`, `3` and `10`.

**Expected result**

Both items fit in one bin of type 1, so the expected solution is one bin of type 1 with a total cost of 10 and 2/2 items packed. That is what both solvers produce once the missing case is added.

**Reproducibility**

| program | LP solver | runs | failures | certificates |
|---|---|---:|---:|---:|
| `packingsolver_box` | default | 5 | 5 | 0 |
| `packingsolver_box` | `highs` | 5 | 5 | 0 |
| `packingsolver_boxstacks` | default | 5 | 5 | 0 |
| `packingsolver_boxstacks` | `highs` | 5 | 5 | 0 |

20 out of 20 runs of the official binaries fail. What decides whether the objective works is the number of bin types that survive on the instance, not the size of the instance: with a single bin type, or with two identical bin types, both solvers return a solution normally; with two distinct bin types both fail. `src/box/optimize.cpp:704-715` is where that split happens, since `number_of_bin_types() == 1` sends the objective to the tree search, and anything more disables the tree search in favour of sequential value correction, whose `SolutionPool::add` compares solutions.

**Root cause**

`Objective::VariableSizedBinPacking` is handled along the rest of both pipelines: the CLI (`src/algorithms/common.cpp:156`), the objective enum (`include/packingsolver/algorithms/common.hpp:224`), the bound (`src/box/optimize.cpp:217,540` and `src/boxstacks/optimize.cpp:167,190`), the formatters (`src/box/algorithm_formatter.cpp:136,231,396` and `src/boxstacks/algorithm_formatter.cpp:125,213,330`) and the default tree-search branching scheme (`src/box/tree_search.cpp:702,754` and `src/boxstacks/tree_search.cpp:1425,1477`; the maximal-spaces scheme does not handle it, but `src/box/optimize.cpp:706` disables that scheme for this objective). The objective is missing only from the two solution comparators:

- `src/box/solution.cpp:158-197`, where `Objective::Feasibility` is at line 187 and `default` at 189
- `src/boxstacks/solution.cpp:286-321`, where they are at lines 311 and 313

`rectangle::Solution::operator<` (`src/rectangle/solution.cpp:224-225`) and `onedimensional::Solution::operator<` (`src/onedimensional/solution.cpp:252-253`) already handle it, immediately after the `Objective::Feasibility` case:

```cpp
    } case Objective::VariableSizedBinPacking: {
        return strictly_lesser_cost(solution.cost(), cost());
```

The objective reached the `box` and `boxstacks` optimization pipelines, but the matching cost comparison never reached their comparators.

Both places have to be fixed, which the stderr output alone does not show: `boxstacks` first computes a `box` relaxation bound (`optimize_box_bound`, `src/boxstacks/optimize.cpp:158`) which runs the full `box::optimize`, which is why the unpatched `boxstacks` binary reports `box::Solution`. I checked the call chain with a staged build that patches only `src/box/solution.cpp`; the `boxstacks` run then gets past the bound and fails one level higher:

```text
Error: bool packingsolver::boxstacks::Solution::operator<(const packingsolver::boxstacks::Solution&) const: solution "boxstacks::Solution" does not support objective "VariableSizedBinPacking"
```

**Local verification of the fix**

Adding that case to both comparators is enough. With both in place, 5 runs of `packingsolver_box` and 5 runs of `packingsolver_boxstacks` all succeed. The `box` certificate is

```text
TYPE,ID,COPIES,BIN,X,Y,Z,LX,LY,LZ,ROTATION
BIN,1,1,0,0,0,0,12,5,5,
ITEM,0,1,0,0,0,0,6,5,5,XYZ
ITEM,0,1,0,6,0,0,6,5,5,XYZ
```

and `output.json` reports `NumberOfItems 2`, `NumberOfUnpackedItems 0`, `NumberOfBins 1`, `BinCost 10` and `VariableSizedBinPackingBound 10`. `boxstacks` produces the same packing through `STACK` rows.

I also checked the direction of the comparison with an inverted cost structure (bin type 0 at cost 5 with 2 copies, bin type 1 at cost 20 with 1 copy). Both solvers then select two bins of type 0 for a total cost of 10, which is the cheaper option.

**Test coverage**

`test/box/box_test.cpp` is commented out in its entirety. `test/box/tree_search_test.cpp` does run `optimize`, but only on knapsack and open-dimension-x instances, and no `box` or `boxstacks` test data sets `objective,variable-sized-bin-packing`. `test/boxstacks/boxstacks_test.cpp::BinCopies` does set the objective, but it builds a single solution and asserts `number_of_bins()` and `bin_copies(0)`, so it never reaches `operator<`. `test/boxstacks/tree_search_test.cpp` is an empty file. A comparator-level test that compares two feasible solutions of different cost covers this without an LP solver, a data file or an optimize run.

I can open a pull request with the two cases and those tests.
