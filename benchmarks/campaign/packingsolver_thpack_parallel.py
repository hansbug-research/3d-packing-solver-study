from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import tarfile
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from packingsolver_thpack import discover, run_instance, sha256, write_summary


def excluded_record(instance: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "instance_id": instance["instance_id"],
        "family": instance["family"],
        "number": instance["number"],
        "source_status": instance["source_status"],
        "objective_kind": instance["objective"],
        "status": "MALFORMED_SOURCE_EXCLUDED",
        "proof_status": None,
        "validation_errors": [],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--time-limit", type=float, default=10.0)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--label", default="10s")
    args = parser.parse_args()
    args.results_dir.mkdir(parents=True, exist_ok=True)
    args.raw_dir.mkdir(parents=True, exist_ok=True)
    instances = discover(args.data_root)
    metadata = {
        "schema_version": 2,
        "campaign": f"packingsolver-thpack-{args.label}/2",
        "engine": "HansBug/packingsolver",
        "source_commit": args.source_commit,
        "binary_sha256": sha256(args.binary),
        "parameters": {
            "time_limit_s": args.time_limit,
            "memory_limit_mib_per_process": 1024,
            "parallel_processes": args.jobs,
            "engine_thread_limit": "NOT_EXPOSED_BY_CLI",
            "blas_openmp_environment_threads": 1,
        },
        "instances": len(instances),
        "harness_sha256": {
            "parallel_runner": sha256(Path(__file__)),
            "certificate_validator": sha256(Path(__file__).with_name("packingsolver_thpack.py")),
        },
    }
    records_by_id: dict[str, dict[str, Any]] = {}
    archive_path = args.raw_dir / f"packingsolver-thpack-{args.label}-artifacts.tar.gz"
    with tempfile.TemporaryDirectory(prefix=f"packingsolver-thpack-{args.label}-") as temporary:
        work_dir = Path(temporary)
        for instance in instances:
            if instance["source_status"] == "MALFORMED_SOURCE_EXCLUDED":
                records_by_id[instance["instance_id"]] = excluded_record(instance)
        runnable = [instance for instance in instances if instance["source_status"] == "VALID"]
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = {
                executor.submit(run_instance, instance, args.binary, args.time_limit, work_dir): instance
                for instance in runnable
            }
            for completed_count, future in enumerate(as_completed(futures), start=1):
                instance = futures[future]
                record, _ = future.result()
                record["engine_source_commit"] = args.source_commit
                record["engine_binary_sha256"] = metadata["binary_sha256"]
                record["harness_sha256"] = metadata["harness_sha256"]
                records_by_id[instance["instance_id"]] = record
                if completed_count % 25 == 0 or completed_count == len(runnable):
                    print(f"packingsolver-thpack-{args.label} {completed_count}/{len(runnable)}", flush=True)
        with tarfile.open(archive_path, "w:gz") as archive:
            for path in sorted(work_dir.rglob("*")):
                if path.is_file():
                    archive.add(path, arcname=path.relative_to(work_dir))

    records = [records_by_id[instance["instance_id"]] for instance in instances]
    result_jsonl = args.results_dir / f"packingsolver-thpack-{args.label}.jsonl"
    with result_jsonl.open("w") as handle:
        for record in records:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")
    write_summary(
        records,
        args.results_dir / f"packingsolver-thpack-{args.label}-summary.json",
        {**metadata, "artifact_archive_sha256": sha256(archive_path)},
    )
    with gzip.open(args.raw_dir / f"packingsolver-thpack-{args.label}-records.jsonl.gz", "wt") as handle:
        for record in records:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
