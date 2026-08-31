#!/usr/bin/env python3
"""Run Go bp3d and u-nesting on B07 as an all-rotations projection.

B07 is the Davies-Bischoff BR0/BR8-15 difficult single-container suite.  The
source contains per-item rotation flags; Go and u-nesting cannot express every
subset, so this runner intentionally removes those flags and records a
geometry-only projection.  It reuses the external protocol-v3 worker and
validator used for B01/B02.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks" / "campaign" / "python_thpack"))
from model import Instance, ItemType  # noqa: E402

sys.path.insert(0, str(ROOT / "benchmarks" / "comprehensive"))
import run_thpack_external_projection as runner  # noqa: E402


SOURCE_COMMIT = "d953148b8f710c06fa6c410949b7272f9e36327b"
DATA_ROOT = ROOT / ".cache" / "packingsolver-fork" / "data" / "box" / "davies1999"
GROUPS = ("BR0", "BR8", "BR9", "BR10", "BR11", "BR12", "BR13", "BR14", "BR15")


def read_csv(path: Path) -> list[dict[str, str]]:
    import csv
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def discover() -> list[tuple[Instance, str, str, str, str]]:
    instances: list[tuple[Instance, str, str, str, str]] = []
    for group in GROUPS:
        for item_path in sorted(DATA_ROOT.glob(f"{group}.txt_*_items.csv")):
            stem = item_path.name.removesuffix("_items.csv")
            bin_path = DATA_ROOT / f"{stem}_bins.csv"
            if not bin_path.exists():
                raise RuntimeError(f"missing B07 bin source: {bin_path}")
            item_rows = read_csv(item_path)
            bin_row = read_csv(bin_path)[0]
            item_types = [
                ItemType(
                    type_id=row["ID"],
                    size=(int(row["X"]), int(row["Y"]), int(row["Z"])),
                    allowed_vertical_dimensions=(1, 1, 1),
                    copies=int(row["COPIES"]),
                )
                for row in item_rows
            ]
            number = int(stem.rsplit("_", 2)[1])
            instance = Instance(
                family="THPACK1",
                instance_id=number,
                problem_kind="single_container_knapsack",
                objective="maximize_packed_volume",
                container=(int(bin_row["X"]), int(bin_row["Y"]), int(bin_row["Z"])),
                item_types=item_types,
            )
            source_id = stem
            instances.append((instance, source_id, group, runner.sha256(item_path), runner.sha256(bin_path)))
    if len(instances) != 900:
        raise RuntimeError(f"expected 900 B07 instances, found {len(instances)}")
    return instances


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--go-binary", type=Path, default=runner.DEFAULT_GO)
    parser.add_argument("--rust-binary", type=Path, default=runner.DEFAULT_RUST)
    parser.add_argument("--library", choices=("go_bp3d", "rust_unesting"), action="append")
    parser.add_argument("--strategy", choices=("extremepoint", "bottomleftfill", "ga", "brkga", "sa"), action="append")
    parser.add_argument("--time-limit", type=float, action="append")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--repetition", type=int, default=0)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    libraries = args.library or ["go_bp3d", "rust_unesting"]
    strategies = args.strategy or ["extremepoint"]
    budgets = args.time_limit or [1.0]
    if "go_bp3d" in libraries and not args.go_binary.is_file():
        raise SystemExit(f"missing Go binary: {args.go_binary}")
    if "rust_unesting" in libraries and not args.rust_binary.is_file():
        raise SystemExit(f"missing Rust binary: {args.rust_binary}")
    cases = discover()
    cases = cases[:args.limit] if args.limit else cases
    runner.JOBS_ROOT.mkdir(parents=True, exist_ok=True)
    runner.RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    labels = []
    for library in libraries:
        for strategy in (strategies if library == "rust_unesting" else ["pivot"]):
            labels.append(runner.implementation_id(library, strategy))
    budget_label = "-".join(f"{x:g}s" for x in budgets)
    library_label = "-".join(labels)
    archive_name = f"raw/experiments/comprehensive/B07-external-projection-{library_label}-{budget_label}-rep-{args.repetition}.tar.gz"
    import tempfile
    import tarfile
    from concurrent.futures import ThreadPoolExecutor, as_completed
    with tempfile.TemporaryDirectory(prefix="b07-external-projection-") as temporary:
        work_root = Path(temporary)
        jobs = [
            (instance, source_id, group, items_sha256, bins_sha256, library, strategy, order, budget)
            for budget in budgets
            for instance, source_id, group, items_sha256, bins_sha256 in cases
            for library in libraries
            for strategy in (strategies if library == "rust_unesting" else ["pivot"])
            for order in ("descending", "ascending")
        ]
        records = []
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(
                runner.run_one, instance, library, strategy, order, budget, args.repetition,
                args.go_binary, args.rust_binary, work_root, archive_name, runner.sha256(Path(__file__)),
                "B07", source_id, group, SOURCE_COMMIT, items_sha256, bins_sha256,
            ) for instance, source_id, group, items_sha256, bins_sha256, library, strategy, order, budget in jobs]
            for index, future in enumerate(as_completed(futures), 1):
                records.append(future.result())
                if index % 100 == 0 or index == len(futures):
                    print(f"{index}/{len(futures)}", flush=True)
        with tarfile.open(ROOT / archive_name, "w:gz") as archive:
            for path in sorted(work_root.iterdir()):
                archive.add(path, arcname=path.name)
    records.sort(key=lambda record: record["run_id"])
    output = runner.RESULTS_ROOT / f"B07-external-projection-{library_label}-{budget_label}-rep-{args.repetition}.jsonl"
    output.write_text("".join(__import__("json").dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
