from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import tarfile
import tempfile
from pathlib import Path

from packingsolver_thpack import apply_solver_artifacts, discover, write_summary


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--result-jsonl", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--raw-records-gzip", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--binary-sha256", required=True)
    parser.add_argument(
        "--campaign-label",
        default="packingsolver-thpack/1-offline-revalidation/1",
    )
    parser.add_argument("--time-limit", type=float, default=1.0)
    parser.add_argument(
        "--harness-provenance",
        default="UNVERSIONED_RUNNER; solver artifacts revalidated offline",
    )
    parser.add_argument("--parallel-processes", type=int)
    args = parser.parse_args()

    old_records = {
        record["instance_id"]: record
        for record in (json.loads(line) for line in args.records.read_text().splitlines() if line.strip())
    }
    instances = discover(args.data_root)
    revalidator = Path(__file__).with_name("packingsolver_thpack.py")
    harness_hashes = {
        "revalidator_sha256": sha256(revalidator),
        "offline_driver_sha256": sha256(Path(__file__)),
    }
    records: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="packingsolver-revalidate-") as temporary:
        temporary_path = Path(temporary)
        with tarfile.open(args.archive, "r:gz") as archive:
            archive.extractall(temporary_path, filter="data")
        for instance in instances:
            if instance["source_status"] == "MALFORMED_SOURCE_EXCLUDED":
                record = {
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
            else:
                record = dict(old_records[instance["instance_id"]])
                record["schema_version"] = 2
                record.pop("bound", None)
                record.pop("relative_gap", None)
                safe_id = instance["instance_id"].replace(":", "_").replace(".", "_")
                case_dir = temporary_path / safe_id
                apply_solver_artifacts(
                    record,
                    instance,
                    case_dir / "output.json",
                    case_dir / "certificate.csv",
                )
            record.update({
                "engine_source_commit": args.source_commit,
                "engine_binary_sha256": args.binary_sha256,
                "input_sha256": {
                    "items": sha256(instance["items"]),
                    "bins": sha256(instance["bins"]),
                },
                "original_harness_provenance": args.harness_provenance,
                **harness_hashes,
            })
            records.append(record)

    args.result_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with args.result_jsonl.open("w") as handle:
        for record in records:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")
    metadata = {
        "schema_version": 2,
        "campaign": args.campaign_label,
        "engine": "HansBug/packingsolver",
        "source_commit": args.source_commit,
        "binary_sha256": args.binary_sha256,
        "parameters": {
            "original_time_limit_s": args.time_limit,
            "memory_limit_mib": 1024,
            "thread_limit": "NOT_EXPOSED_BY_CLI",
            "blas_openmp_environment_threads": 1,
            **(
                {"parallel_processes": args.parallel_processes}
                if args.parallel_processes is not None
                else {}
            ),
        },
        "instances": len(records),
        "artifact_archive_sha256": sha256(args.archive),
        "original_harness_provenance": args.harness_provenance,
        "original_harness_sha256": next(
            (
                record.get("harness_sha256")
                for record in old_records.values()
                if record.get("harness_sha256")
            ),
            None,
        ),
        **harness_hashes,
    }
    write_summary(records, args.summary, metadata)
    args.raw_records_gzip.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.raw_records_gzip, "wt") as handle:
        for record in records:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
