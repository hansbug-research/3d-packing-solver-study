#!/usr/bin/env python3
"""Run the pinned PackingSolver ``box`` binary on THPACK as protocol-v3.

The historical campaign runner writes legacy records and is intentionally kept
unchanged.  This runner reuses its parser and independent certificate checker,
but emits immutable protocol-v3 records for a separately pinned fork/upstream
binary.  BR/LN are partial knapsack problems; IMM is a complete bin-packing
problem and excludes the three malformed source rows in the same way as the
legacy parser.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks" / "campaign"))
from packingsolver_thpack import discover, run_instance  # noqa: E402

sys.path.insert(0, str(ROOT / "benchmarks"))
from comprehensive.model import canonical_json, load_catalogs, validate_run_record  # noqa: E402

RUNNER = Path(__file__).resolve()
BENCHMARKS = {"BR": "B01", "LN": "B02", "IMM": "B04"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def combined_hash(*values: str) -> str:
    return hashlib.sha256(("\n".join(values) + "\n").encode("ascii")).hexdigest()


def checkout_commit(data_root: Path) -> str:
    checkout = data_root.resolve().parent.parent
    return subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()


def one_record(
    instance: dict[str, Any],
    result: dict[str, Any],
    implementation: dict[str, Any],
    implementation_id: str,
    time_limit: float,
    source_commit: str,
    binary_hash: str,
    runner_hash: str,
    archive: str,
    case_name: str,
) -> dict[str, Any]:
    benchmark_id = BENCHMARKS[instance["family"]]
    source_valid = instance["source_status"] == "VALID"
    errors = list(result.get("validation_errors", []))
    process_ok = result.get("returncode") == 0 and result.get("status") == "VALID"
    if not source_valid:
        run_status, solution_status, proof_status, termination = "NOT_RUN", "NOT_APPLICABLE", "NOT_APPLICABLE", "SOURCE_PENDING"
    elif not process_ok:
        run_status, solution_status, proof_status, termination = "ERROR", "NO_SOLUTION", "UNKNOWN", "PROCESS_ERROR"
    else:
        solver_time = float(result.get("solver_time_s") or 0.0)
        run_status = "TIME_LIMIT" if solver_time >= time_limit * 0.95 else "COMPLETED"
        if errors:
            solution_status, proof_status, termination = "INVALID_CERTIFICATE", "UNKNOWN", "INVALID_CERTIFICATE"
        elif instance["family"] in {"BR", "LN"}:
            solution_status = "VALID_PARTIAL"
            proof_status = "INCUMBENT_WITH_BOUND" if result.get("proof_status") == "SOLVER_REPORTED_BOUND_CLOSED" else "FEASIBLE"
            termination = "TIME_LIMIT_WITH_INCUMBENT" if run_status == "TIME_LIMIT" else "SOLVER_STOPPED"
        else:
            complete = int(result.get("unpacked_items") or 0) == 0
            solution_status = "VALID_COMPLETE" if complete else "VALID_PARTIAL"
            proof_status, termination = "FEASIBLE", "TIME_LIMIT_WITH_INCUMBENT" if run_status == "TIME_LIMIT" else "SOLVER_STOPPED"
    input_hash = None
    if source_valid:
        input_hash = combined_hash(result["input_sha256"]["items"], result["input_sha256"]["bins"])
    record = {
        "schema_version": 2,
        "protocol_version": "benchmark-protocol/3",
        "record_origin": "PROTOCOL_V3",
        "run_id": f"{benchmark_id}/{instance['instance_id']}/{implementation_id}/{time_limit:g}s/protocol-native/rep-0",
        "benchmark_id": benchmark_id,
        "problem_variant": "ORIGINAL",
        "instance_id": instance["instance_id"],
        "implementation_id": implementation_id,
        "algorithm": implementation["algorithm"],
        "adapter": "packingsolver_thpack_native_v1",
        "comparison_track": "NATIVE",
        "problem_scope": "FULL_PROBLEM",
        "budget": {"time_limit_s": time_limit, "memory_limit_bytes": 1073741824, "thread_limit": None},
        "item_order": "SOLVER_INTERNAL",
        "bin_order": "SOURCE",
        "seed": None,
        "repetition": 0,
        "input_sha256": input_hash,
        "input_status": "VALID" if source_valid else "SOURCE_INCOMPLETE",
        "capability_status": "SUPPORTED_NATIVE",
        "run_status": run_status,
        "solution_status": solution_status,
        "proof_status": proof_status,
        "termination_reason": termination,
        "resources": {
            "wall_s": result.get("wall_time_s"),
            "solver_s": result.get("solver_time_s"),
            "cpu_user_s": result.get("user_time_s"),
            "cpu_system_s": result.get("system_time_s"),
            "peak_rss_bytes": int(result.get("max_rss_kib") or 0) * 1024,
        },
        "metrics": {
            "packed_items": result.get("packed_items"),
            "unpacked_items": result.get("unpacked_items"),
            "bins_used": result.get("bins_used"),
            "packed_volume": result.get("packed_volume"),
            "volume_utilization": result.get("volume_utilization"),
            "objective": result.get("primal"),
            "solver_reported_bound": result.get("solver_reported_bound"),
            "solver_reported_gap": result.get("relative_gap_to_solver_reported_bound"),
            "validation_error_count": len(errors),
            "engine_source_commit": source_commit,
            "engine_binary_sha256": binary_hash,
            "runner_sha256": runner_hash,
            "provenance_kind": "FRESH_SOLVER_INVOCATION",
        },
        "artifacts": {
            "source_result": f"{archive}#{case_name}/result.json",
            "solver_output": f"{archive}#{case_name}/output.json",
            "certificate": f"{archive}#{case_name}/certificate.csv",
            "validation": f"{archive}#{case_name}/validation.json",
        },
    }
    validate_run_record(record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument(
        "--implementation-id",
        choices=(
            "packingsolver_fork_box",
            "packingsolver_upstream_box",
            "packingsolver_fork_boxstacks",
            "packingsolver_upstream_boxstacks",
        ),
        required=True,
    )
    parser.add_argument("--time-limit", type=float, choices=(1.0, 10.0), required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--family", choices=("BR", "LN", "IMM"), action="append")
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--results-root", type=Path, default=ROOT / "results" / "comprehensive")
    parser.add_argument("--raw-root", type=Path, default=ROOT / "raw" / "experiments" / "comprehensive")
    args = parser.parse_args()
    if args.jobs < 1 or not args.binary.is_file():
        raise SystemExit("--jobs must be positive and --binary must exist")
    if checkout_commit(args.data_root) != args.source_commit:
        raise SystemExit("data checkout does not match --source-commit")
    suites, implementations = load_catalogs()
    implementation = next(row for row in implementations["implementations"] if row["id"] == args.implementation_id)
    instances = discover(args.data_root)
    families = set(args.family or ("BR", "LN"))
    instances = [row for row in instances if row["family"] in families]
    binary_hash, runner_hash = sha256(args.binary), sha256(RUNNER)
    raw_dir = args.raw_root / "packingsolver-thpack" / args.label
    raw_dir.mkdir(parents=True, exist_ok=True)
    archive_path = raw_dir / "artifacts.tar.gz"
    archive = str(archive_path.relative_to(ROOT))
    output = args.results_root / "runs" / f"{args.label}.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix=f"ps-thpack-{args.label}-") as temporary:
        work_root = Path(temporary)
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = {}
            for instance in instances:
                if instance["source_status"] != "VALID":
                    continue
                futures[executor.submit(run_instance, instance, args.binary, args.time_limit, work_root)] = instance
            for count, future in enumerate(as_completed(futures), 1):
                instance = futures[future]
                result, files = future.result()
                case_name = instance["instance_id"].replace(":", "_").replace(".", "_")
                records.append(one_record(instance, result, implementation, args.implementation_id, args.time_limit, args.source_commit, binary_hash, runner_hash, archive, case_name))
                # Keep a compact source result alongside the solver artifacts.
                case_dir = work_root / case_name
                case_dir.mkdir(exist_ok=True)
                (case_dir / "result.json").write_text(canonical_json(result), encoding="utf-8")
                if count % 25 == 0 or count == len(futures):
                    print(f"{args.label}: {count}/{len(futures)}", flush=True)
        with tarfile.open(archive_path, "w:gz") as archive_handle:
            for path in sorted(work_root.rglob("*")):
                if path.is_file():
                    archive_handle.add(path, arcname=path.relative_to(work_root))
    records.sort(key=lambda row: row["run_id"])
    output.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n" for row in records), encoding="utf-8")
    (raw_dir / "metadata.json").write_text(canonical_json({
        "schema_version": 1, "protocol_version": "benchmark-protocol/3", "implementation_id": args.implementation_id,
        "source_commit": args.source_commit, "binary_sha256": binary_hash, "runner_sha256": runner_hash,
        "time_limit_s": args.time_limit, "families": sorted(families), "records": len(records),
        "output_sha256": sha256(output), "archive_sha256": sha256(archive_path),
    }), encoding="utf-8")
    print(output.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
