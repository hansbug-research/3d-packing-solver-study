[boxstacks] Out-of-range read in the axle-weight repair loop of `sequential_onedimensional_rectangle` (`std::bad_array_new_length`)

---

Hello Florian,

When a `boxstacks` bin is a semi-trailer truck and the first packing violates the middle axle weight limit, `sequential_onedimensional_rectangle` enters its axle weight repair loop and reads `fixed_items_solutions` one element past the end. The out-of-range element is then copy-constructed into a `boxstacks::Solution`, which aborts the run. The message is `std::bad_array_new_length`, or `std::bad_alloc` depending on the objective, which both look like memory exhaustion; the process actually fails within a few milliseconds, with a peak RSS of about 11 MB.

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

One pallet in a semi-trailer truck, with a middle axle weight limit that the leftmost placement exceeds. Dimensions are in centimetres and weights in kilograms, and the truck data describes a 13.6 m trailer behind an 8 t tractor.

`items.csv`

```csv
ID,X,Y,Z,ROTATION_XYZ,ROTATION_YXZ,ROTATION_ZYX,ROTATION_YZX,ROTATION_XZY,ROTATION_ZXY,WEIGHT,COPIES,GROUP_ID,STACKABILITY_ID,NESTING_HEIGHT,MAXIMUM_STACKABILITY,MAXIMUM_WEIGHT_ABOVE
0,200,200,200,1,0,0,0,0,0,2000,1,0,0,0,1,10000
```

`bins.csv`

```csv
ID,X,Y,Z,COST,COPIES,MAXIMUM_WEIGHT,MAXIMUM_STACK_DENSITY,IS_SEMI_TRAILER_TRUCK,TRACTOR_WEIGHT,FRONT_AXLE_MIDDLE_AXLE_DISTANCE,FRONT_AXLE_TRACTOR_GRAVITY_CENTER_DISTANCE,FRONT_AXLE_HARNESS_DISTANCE,EMPTY_TRAILER_WEIGHT,HARNESS_REAR_AXLE_DISTANCE,TRAILER_GRAVITY_CENTER_REAR_AXLE_DISTANCE,TRAILER_START_HARNESS_DISTANCE,REAR_AXLE_MAXIMUM_WEIGHT,MIDDLE_AXLE_MAXIMUM_WEIGHT
0,1360,240,260,1,1,24000,1000,1,8000,380,100,320,6000,800,400,100,9000,6200
```

```shell
./packingsolver_boxstacks \
        --items items.csv \
        --bins bins.csv \
        --objective bin-packing \
        --time-limit 3 \
        --verbosity-level 0 \
        --certificate solution.csv \
        --only-write-at-the-end
```

**Actual result**

```text
Error: std::bad_array_new_length
```

Exit code 1 and no certificate.

**Expected result**

The instance is feasible. Using `SemiTrailerTruckData::compute_axle_weights` with the values above, a load of 2000 kg whose centre of gravity sits at `x = cx` gives a middle axle weight of `(2480000 - 800 * cx) / 380` and a rear axle weight of `2750 + 2.5 * cx`. The middle axle limit of 6200 kg therefore needs `cx >= 155`, and the rear axle limit of 9000 kg holds over the whole trailer, the maximum being 5900 kg. Since the pallet is 200 long, every placement with `x >= 55` respects both limits, so the expected result is a single bin containing the pallet placed at `x >= 55`.

**Reproducibility**

Five consecutive runs of the official binary all fail with `std::bad_array_new_length`. The only field I change below is `MIDDLE_AXLE_MAXIMUM_WEIGHT`; everything else stays as in the reproducer.

| `MIDDLE_AXLE_MAXIMUM_WEIGHT` | leftmost placement legal? | result over 3 runs |
|---|---|---|
| 6200 | no, it needs 6315.8 kg | 3/3 `std::bad_array_new_length` |
| 6400 | yes | 3/3 succeed, certificate written |

So the difference between a crash and a correct answer is the value of one advertised constraint field, and both values are physically plausible.

The objective changes only the exception:

| objective | result over 3 runs |
|---|---|
| `bin-packing` | `std::bad_array_new_length` |
| `knapsack` | `std::bad_array_new_length` |
| `feasibility` | `std::bad_alloc` |

The exception type varies because the bytes read past the end of the vector are, presumably, whatever happens to be on the heap at that moment. libstdc++'s `std::allocator::allocate` throws `std::bad_array_new_length` when the element count is large enough that the byte count would overflow `size_t`, and `std::bad_alloc` when it merely exceeds `max_size()` or when `operator new` fails; that split is an implementation detail rather than standard behaviour. Either way the message points at memory rather than at the actual cause.

**Root cause**

In `src/boxstacks/sequential_onedimensional_rectangle.cpp`, `fixed_items_solutions_pos` indexes `fixed_items_solutions` at the top of the main loop, at lines 561-562:

```cpp
        // Part of solution which is fixed.
        Solution fixed_items = fixed_items_solutions[fixed_items_solutions_pos];
```

At the bottom of the loop, lines 1275-1288, the middle axle failure branch recomputes that index:

```cpp
        if (failed_middle_axle_weight_constraint) {
            // If the solution is infeasible.
            fixed_items_solutions_pos_lower_bound = fixed_items_solutions_pos + 1;
            fixed_items_solutions_pos = 0;
            for (ItemPos pos = 0; pos < (ItemPos)fixed_items_solutions.size(); ++pos) {
                if (pos + 1 < (ItemPos)fixed_items_solutions.size()
                        && fixed_items_solutions[pos + 1].x_max() > xi - x_max)
                    break;
                // ...
                fixed_items_solutions_pos++;
            }
            if (fixed_items_solutions_pos < fixed_items_solutions_pos_lower_bound)
                fixed_items_solutions_pos = fixed_items_solutions_pos_lower_bound;
        }
```

On the last iteration of that scan, `pos + 1 < fixed_items_solutions.size()` is false, so the `break` is skipped and `fixed_items_solutions_pos` is incremented one time too many. When no earlier `break` happens, the scan therefore leaves `fixed_items_solutions_pos == fixed_items_solutions.size()`. The clamp that follows only raises the index to the lower bound, it never caps it, and the loop-termination check at line 1304 only breaks when `fixed_items_solutions_pos_lower_bound > fixed_items_solutions_pos_upper_bound`, which is not the case here: the first failure sets the lower bound to 1 while the upper bound is still `size() - 1`. The next iteration then indexes one past the end with `std::vector::operator[]`, so nothing checks the range, and copy-constructing a `Solution` from that memory throws.

I confirmed this by adding a temporary bounds check in front of the indexing. On the reproducer above it reports:

```text
[DBG] iteration=0 pos=0 size=2 lower=0 upper=1
[DBG] after scan: x_max=200 xi=1360 pos=2 lower=1 upper=1 size=2
[DBG] iteration=1 pos=2 size=2 lower=1 upper=1
Error: out-of-range fixed_items_solutions_pos 2 with fixed_items_solutions.size() 2
```

The `std::bad_array_new_length` is replaced by the explicit out-of-range report, which puts the cause and the symptom in the same place.

**When it triggers**

Four things have to hold together. The instance has a single bin, since that is the condition under which `optimize` calls this algorithm at all (`src/boxstacks/optimize.cpp:203`). The bin is a semi-trailer truck and the first packing violates the middle axle limit. `fixed_items_solutions` holds at least two entries, otherwise the lower bound passes the upper bound and line 1304 breaks first. And the scan never breaks early, which happens when every entry from index 1 onwards satisfies `x_max() <= xi - x_max`, where `x_max` is the extent of the current failed packing. That last condition is what makes this easy to hit with a long trailer holding a small load near the front. With four pallets in the same trailer the scan does stop early, at `pos = 2` of `size() = 5`, and the run exits 0, although it still returns an empty solution; with two and three pallets it still crashes.

**Suggested fix**

Making the scan stop on the last entry instead of running past it is a one-line change:

```cpp
                if (pos + 1 >= (ItemPos)fixed_items_solutions.size()
                        || fixed_items_solutions[pos + 1].x_max() > xi - x_max)
                    break;
```

With that change the reproducer no longer crashes, the loop terminates through the existing lower and upper bound check, and the exit code is 0. It is also safe at the boundary: if the last entry does fail the length test, the lower bound becomes `size()` and line 1304 breaks before anything is indexed.

The fix does not make this instance solvable. After it the run terminates cleanly but still returns an empty solution, even though a feasible placement exists as computed above, which is the outcome the four-pallet case already has today. That looks like a separate limitation of the repair strategy rather than the same defect, so I have not tried to address it here.

Since the failure is an out-of-range read on a `std::vector`, `-D_GLIBCXX_ASSERTIONS` in one CI configuration would catch this class of bug directly. I rebuilt that translation unit with the flag, and the run aborts at the indexing itself:

```text
/usr/include/c++/13/bits/stl_vector.h:1128: std::vector<_Tp, _Alloc>::reference std::vector<_Tp, _Alloc>::operator[](size_type) [with _Tp = packingsolver::boxstacks::Solution; ...]: Assertion '__n < this->size()' failed.
```

That names the vector being indexed and leaves a core dump pointing at the call site, instead of surfacing later as an allocation exception.

I have not run the ROADEF 2022 instances, so I do not know whether they hit this.

I can open a pull request with the one-line fix.
