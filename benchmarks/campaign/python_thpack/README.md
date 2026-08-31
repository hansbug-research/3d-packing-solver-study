# Python THPACK campaign

This campaign preserves the original ESICUP semantics at commit `154a8f006a8e72f65d734f2d1e36777f678f31f8`:

- THPACK1-8 are single-container knapsack instances. The score is packed
  volume; leaving items unpacked is legal.
- THPACK9 is multiple-container bin packing. Every item must be packed and the
  score is the number of used containers.
- The three flags after item dimensions say whether that dimension may be
  vertical. They are not independent rotation-axis switches.

`py3dbp` can exactly represent only `(1,1,1)`. Pinned Jerry can exactly represent `(1,1,1)` and `(0,0,1)` using its `updown` switch. All other records are emitted with `UNSUPPORTED_ORIENTATION_SEMANTICS`; malformed source records are emitted with `MALFORMED_SOURCE_EXCLUDED` and are never sent to a solver.

Run from the repository root with the pinned source checkouts already present:

```bash
.venv/bin/python benchmarks/campaign/python_thpack/run_campaign.py
.venv/bin/python benchmarks/campaign/python_thpack/cross_validate_invalid.py
.venv/bin/python benchmarks/campaign/python_thpack/analyze.py
```

Each supported instance is run in descending-volume and ascending-volume item order. Every worker has a 60-second wall timeout, a 2 GiB address-space limit, one-thread numerical-library environment variables, and `PYTHONHASHSEED=0`. The libraries themselves are deterministic for these parameter sets and do not expose a random seed.

Canonical placements and statuses are in `raw/experiments/campaign/python_thpack/records.jsonl`; derived summaries are in `results/campaign/python_thpack/`. The validator checks item identity, completeness where required, allowed vertical dimensions, container bounds and pairwise AABB overlap independently of either packer.
