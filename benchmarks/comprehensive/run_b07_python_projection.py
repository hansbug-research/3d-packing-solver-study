#!/usr/bin/env python3
"""Run py3dbp and Jerry on B07's explicit all-rotations projection."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks" / "comprehensive"))
import run_b07_external_projection as b07  # noqa: E402
import run_thpack_python_projection as runner  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--time-limit", type=float, action="append")
    parser.add_argument("--library", choices=("py3dbp", "jerry"), action="append")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--repetition", type=int, default=0)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--jerry-fix-point", choices=("true", "false"), default="true")
    args = parser.parse_args()
    if args.workers < 1:
        raise SystemExit("--workers must be positive")
    cases = b07.discover()
    cases = cases[:args.limit] if args.limit else cases
    libraries = args.library or ["py3dbp", "jerry"]
    budgets = args.time_limit or [1.0]
    runner.RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    nofix = libraries == ["jerry"] and args.jerry_fix_point == "false"
    library_label = "-".join(libraries) + ("-nofix" if nofix else "")
    budget_label = "-".join(f"{value:g}s" for value in budgets)
    archive_name = f"raw/experiments/comprehensive/B07-python-projection-{library_label}-{budget_label}-rep-{args.repetition}.tar.gz"
    jobs = [
        (instance, source_id, group, items_sha256, bins_sha256, library, order, budget)
        for budget in budgets
        for instance, source_id, group, items_sha256, bins_sha256 in cases
        for library in libraries
        for order in ("descending", "ascending")
    ]
    records = []
    with tempfile.TemporaryDirectory(prefix="b07-python-projection-") as temporary:
        work_root = Path(temporary)
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [
                executor.submit(
                    runner.run_one,
                    instance,
                    library,
                    order,
                    budget,
                    args.repetition,
                    benchmark_id_override="B07",
                    source_instance_id_override=source_id,
                    source_group=group,
                    source_commit_override=b07.SOURCE_COMMIT,
                    source_items_sha256=items_sha256,
                    source_bins_sha256=bins_sha256,
                    work_root=work_root,
                    archive_name=archive_name,
                    adapter_override="b07_python_projection_nofix_v1" if nofix else "b07_python_projection_v1",
                    source_root_override=b07.DATA_ROOT,
                    jerry_fix_point=args.jerry_fix_point == "true",
                )
                for instance, source_id, group, items_sha256, bins_sha256, library, order, budget in jobs
            ]
            for index, future in enumerate(as_completed(futures), 1):
                records.append(future.result())
                if index % 100 == 0 or index == len(futures):
                    print(f"{index}/{len(futures)}", flush=True)
        with tarfile.open(ROOT / archive_name, "w:gz") as archive:
            for path in sorted(work_root.iterdir()):
                archive.add(path, arcname=path.name)
    records.sort(key=lambda record: record["run_id"])
    output = runner.RESULTS_ROOT / f"B07-python-projection-{library_label}-{budget_label}-rep-{args.repetition}.jsonl"
    output.write_text("".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
