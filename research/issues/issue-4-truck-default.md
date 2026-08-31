[boxstacks] A bin file with axle weight limits but no truck geometry silently returns an empty solution

---

Hello Florian,

A `boxstacks` bin file that declares `REAR_AXLE_MAXIMUM_WEIGHT` but no truck geometry makes the solver return an empty solution, with exit code 0 and no message. Two things combine: `read_bin_types` flags every bin read from a CSV file as a semi-trailer truck, and `compute_axle_weights` then divides by distances that are still 0, so the rear axle weight comes out as `+inf` and exceeds any finite limit for every candidate solution of that instance.

**Version**

```text
release:      Latest (master), packingsolver-linux-x64.tar.gz, asset updated 2026-08-29
commit:       367ebfdaad11424ded3696b7dae799a30c1375d0
asset SHA256: 1ef068f2041c8199e9ac6ef8a6780b01f636b79b8b2f7e98aaf60360d67c7aa4
```

**Environment**

```text
Ubuntu 24.04.3 LTS, x86-64, glibc 2.39
Run with the prebuilt Linux binary from the release above.
```

**Reproducer**

Three pallets and one bin that declares a rear axle limit and nothing else about the truck.

`items.csv`

```csv
ID,X,Y,Z,ROTATION_XYZ,ROTATION_YXZ,ROTATION_ZYX,ROTATION_YZX,ROTATION_XZY,ROTATION_ZXY,WEIGHT,COPIES,GROUP_ID,STACKABILITY_ID,NESTING_HEIGHT,MAXIMUM_STACKABILITY,MAXIMUM_WEIGHT_ABOVE
0,200,200,200,1,0,0,0,0,0,2000,3,0,0,0,1,10000
```

`bins.csv`

```csv
ID,X,Y,Z,COST,COPIES,MAXIMUM_WEIGHT,REAR_AXLE_MAXIMUM_WEIGHT
0,1000,240,260,1,2,24000,9000
```

```shell
./packingsolver_boxstacks \
        --items items.csv \
        --bins bins.csv \
        --objective bin-packing \
        --time-limit 3 \
        --verbosity-level 1 \
        --certificate solution.csv \
        --only-write-at-the-end
```

**Actual result**

Exit code 0, and a `solution.csv` that contains only its header line. From the summary (excerpt):

```text
Number of items:   0 / 3 (0%)
...
Number of bins:    0 / 2 (0%)
...
X max:             0
Y max:             0
```

`--objective knapsack` and `--objective feasibility` behave the same way. Adding one column to the same bin file makes it pack normally:

```csv
ID,X,Y,Z,COST,COPIES,MAXIMUM_WEIGHT,IS_SEMI_TRAILER_TRUCK,REAR_AXLE_MAXIMUM_WEIGHT
0,1000,240,260,1,2,24000,0,9000
```

```text
Number of items:   3 / 3 (100%)
Number of bins:    1 / 2 (50%)
```

```text
TYPE,ID,COPIES,BIN,STACK,X,Y,Z,LX,LY,LZ,GROUP_ID
BIN,0,1,0,-1,0,0,0,1000,240,260,
STACK,0,1,0,0,0,0,0,200,200,200,
ITEM,0,1,0,0,0,0,0,200,200,200,0
STACK,1,1,0,1,200,0,0,200,200,200,
ITEM,0,1,0,1,200,0,0,200,200,200,0
STACK,2,1,0,2,400,0,0,200,200,200,
ITEM,0,1,0,2,400,0,0,200,200,200,0
```

**Expected result**

Either the three pallets are packed, or the run fails with a message saying the axle limits cannot be used without the truck geometry. An empty solution with a success exit code gives the caller no way to notice that the input was not understood as intended.

**Root cause**

`SemiTrailerTruckData::is` defaults to `false` in `include/packingsolver/algorithms/truck.hpp:14`, and `read()` assigns it only when an `IS_SEMI_TRAILER_TRUCK` column is present (`truck.hpp:92`). `src/boxstacks/instance_builder.cpp:686-687` overrides that default before the parsing loop:

```cpp
        SemiTrailerTruckData semi_trailer_truck_data;
        semi_trailer_truck_data.is = true;
```

`git grep -n "is = true" -- src include` returns only that line, and `src/rectangle/instance_builder.cpp:721` declares the same struct without overriding the default, so `boxstacks` is the only reader that does this.

For the bin file above, `is` therefore stays `true` while every distance stays 0. In `compute_axle_weights` (`truck.hpp:51-88`), `harness_weight` divides by `harness_rear_axle_distance` and `middle_axle_weight` divides by `front_axle_middle_axle_distance`, so the rear axle weight becomes `+inf` and the middle axle weight becomes NaN. `Solution::feasible_axle_weights` (`src/boxstacks/solution.cpp:130-147`) compares the `+inf` against the finite `REAR_AXLE_MAXIMUM_WEIGHT` of 9000, marks every candidate infeasible, and `boxstacks::tree_search` prunes on the matching violation, so the search has nothing left to return. The NaN middle axle weight plays no part: NaN never satisfies the strict `>` comparison. A bin file that declares only `MIDDLE_AXLE_MAXIMUM_WEIGHT` and no distances therefore packs normally, while one that declares `REAR_AXLE_MAXIMUM_WEIGHT` does not.

A bin file with no axle columns at all does work today, but the reason is delicate rather than by design: both limits then keep their default of `std::numeric_limits<Weight>::max()`, and `max() * PSTOL` overflows to `+inf`, so the strict comparison `inf > inf` is false. Were `PSTOL` exactly 1, `inf > max()` would be true and those files would fail too. The infinite and NaN axle weights are still computed on every feasibility check of every such instance.

**On whether this is simply invalid input**

Declaring `IS_SEMI_TRAILER_TRUCK=0` is a workaround, but it is not one a user can be expected to find: `IS_SEMI_TRAILER_TRUCK` appears nowhere in the repository except `include/packingsolver/algorithms/truck.hpp`, and while the README advertises "Maximum weight on middle and rear axles" as a `boxstacks` feature (README line 583), it documents no bin-CSV column names at all. `truck.hpp` itself documents the default as `false`. Whatever you decide about the flag, the silent success with an empty result looks like the part worth fixing. Setting `no-check-weight-constraints` in a parameters file also avoids it, but that turns off the weight constraints the user asked for.

**Suggested fix**

The narrow fix I would suggest is to skip the axle weights the geometry cannot produce, in `compute_axle_weights`, rather than change what the reader flags. Without `harness_rear_axle_distance` neither weight can be computed, since both are derived from `harness_weight`, so the function returns `{0, 0}`. Without `front_axle_middle_axle_distance` only the middle axle weight is lost, so the rear axle stays constrained.

I checked that this does not silently drop a constraint that works today. A bin that declares `IS_SEMI_TRAILER_TRUCK=1` with a full geometry except `FRONT_AXLE_MIDDLE_AXLE_DISTANCE=0` does have its rear axle limit enforced at the moment: with the three pallets above, `REAR_AXLE_MAXIMUM_WEIGHT=4600` gives one bin and `4400` splits the load into two, and both still hold after the change. Any bin type that provides both distances is bit-for-bit unaffected.

Two things this does not cover, in case you would rather solve it elsewhere. `compute_axle_weights` also divides by `weight`, which is 0 for an empty bin; that case already produces NaN and no violation today, and I left it alone. And the reader still flags every bin from a CSV file as a semi-trailer truck, which is the reason the degenerate state is reachable from an ordinary bin file at all. Removing that override, or applying it only when the `IS_SEMI_TRAILER_TRUCK` column is absent, looks like a policy decision about existing bin files, so I did not make it. I have not been able to check what the ROADEF 2022 bin files contain, since `scripts/download_data.py` fetches them rather than the repository shipping them.

I can open a pull request with the `compute_axle_weights` change and unit tests for both degenerate cases.
