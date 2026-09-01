#!/usr/bin/env python3
"""Run both pinned PackingSolver boxstacks binaries on B06 calibration cases."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import tarfile
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(ROOT / "benchmarks" / "comprehensive"))
from model import canonical_json, load_catalogs, validate_run_record  # noqa: E402
from run_b06_external import CASE_NAMES  # noqa: E402
from run_constraint_gauntlet import validate_plain  # noqa: E402
from exact_suite import make_cases  # noqa: E402

FORK = ROOT / ".cache" / "build-fork" / "src" / "boxstacks" / "packingsolver_boxstacks"
UPSTREAM = ROOT / ".cache" / "build-upstream-367" / "src" / "boxstacks" / "packingsolver_boxstacks"
DEFAULT_OUTPUT = ROOT / "results" / "comprehensive" / "runs" / "B06-boxstacks.jsonl"
DEFAULT_RAW = ROOT / "raw" / "experiments" / "comprehensive" / "B06-boxstacks"
RUNNER = Path(__file__).resolve()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_sources(case: Any, directory: Path) -> tuple[Path, Path]:
    items = directory / "items.csv"
    bins = directory / "bins.csv"
    with items.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ID", "X", "Y", "Z", "ROTATION_XYZ", "ROTATION_YXZ", "ROTATION_ZYX", "ROTATION_YZX", "ROTATION_XZY", "ROTATION_ZXY", "WEIGHT", "COPIES", "GROUP_ID", "STACKABILITY_ID", "NESTING_HEIGHT", "MAXIMUM_STACKABILITY", "MAXIMUM_WEIGHT_ABOVE"])
        for index, item in enumerate(case.items):
            flags = []
            for order in ((0, 1, 2), (1, 0, 2), (2, 1, 0), (1, 2, 0), (0, 2, 1), (2, 0, 1)):
                flags.append(int(tuple(item.dimensions[i] for i in order) in set(item.orientations)))
            writer.writerow([index, *item.dimensions, *flags, item.weight, 1, 0, 0, 0, 100, 100000])
    with bins.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ID", "X", "Y", "Z", "COST", "COPIES", "MAXIMUM_WEIGHT", "MAXIMUM_STACK_DENSITY"])
        for index, bin_spec in enumerate(case.bins):
            writer.writerow([index, *bin_spec.dimensions, bin_spec.cost, 1, bin_spec.capacity, 100])
    return items, bins


def run_one(case: Any, implementation_id: str, binary: Path, raw_root: Path) -> dict[str, Any]:
    case_dir = raw_root / f"{case.name}-{implementation_id}"
    case_dir.mkdir(parents=True, exist_ok=True)
    items, bins = write_sources(case, case_dir)
    output = case_dir / "output.json"
    certificate = case_dir / "solution.csv"
    stderr = case_dir / "stderr.log"
    command = [str(binary), "--items", str(items), "--bins", str(bins), "--objective", "bin-packing", "--time-limit", "10", "--memory-limit", "1024", "--verbosity-level", "0", "--only-write-at-the-end", "--output", str(output), "--certificate", str(certificate)]
    started = perf_counter()
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=20.0, env={**os.environ, "OMP_NUM_THREADS": "1"}, check=False)
        stderr.write_text(completed.stderr, encoding="utf-8")
        process_ok = completed.returncode == 0 and output.exists() and certificate.exists()
    except subprocess.TimeoutExpired as exc:
        stderr.write_text(str(exc), encoding="utf-8")
        completed = None
        process_ok = False
    wall = perf_counter() - started
    if process_ok:
        errors, metrics = validate_plain(items, bins, certificate, case.expected_status != "INFEASIBLE")
    else:
        errors, metrics = ["solver process failed or omitted output/certificate"], {"packed_items": 0, "required_items": len(case.items), "bins_used": 0, "total_cost": None, "validation_error_count": 1}
    if case.expected_status == "INFEASIBLE" and process_ok and not errors and metrics["packed_items"] == 0:
        solution_status, proof = "NO_SOLUTION", "UNKNOWN"
    elif errors:
        solution_status, proof = "INVALID_CERTIFICATE" if metrics.get("packed_items", 0) else "NO_SOLUTION", "UNKNOWN"
    elif metrics.get("packed_items") == len(case.items):
        solution_status, proof = "VALID_COMPLETE", "FEASIBLE"
    else:
        solution_status, proof = "VALID_PARTIAL", "FEASIBLE"
    if not binary.exists():
        process_ok = False
        solution_status, proof = "NO_SOLUTION", "UNKNOWN"
        errors = [f"missing binary: {binary}"]
    case_input = {"case": case.name, "items": [{"ref": x.ref, "dimensions": x.dimensions, "weight": x.weight, "orientations": x.orientations} for x in case.items], "bins": [{"ref": x.ref, "dimensions": x.dimensions, "capacity": x.capacity, "cost": x.cost} for x in case.bins]}
    (case_dir / "input.json").write_text(canonical_json(case_input), encoding="utf-8")
    (case_dir / "validation.json").write_text(canonical_json({"errors": errors, **metrics}), encoding="utf-8")
    _, catalog = load_catalogs()
    implementation = next(x for x in catalog["implementations"] if x["id"] == implementation_id)
    input_hash = hashlib.sha256(json.dumps(case_input, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    record = {
        "schema_version": 2, "protocol_version": "benchmark-protocol/3", "record_origin": "PROTOCOL_V3",
        "run_id": f"B06/{case.name}/{implementation_id}/10s/native-boxstacks/rep-0", "benchmark_id": "B06", "problem_variant": "EXACT_ORACLE_CASES", "instance_id": case.name,
        "implementation_id": implementation_id, "algorithm": implementation["algorithm"], "adapter": "b06_boxstacks_native_v1", "comparison_track": "NATIVE", "problem_scope": "FULL_PROBLEM",
        "budget": {"time_limit_s": 10.0, "memory_limit_bytes": 1073741824, "thread_limit": 1}, "item_order": "SOURCE", "bin_order": "SOURCE", "seed": None, "repetition": 0,
        "input_sha256": input_hash, "input_status": "VALID", "capability_status": "SUPPORTED_NATIVE", "run_status": "COMPLETED" if process_ok else "ERROR", "solution_status": solution_status, "proof_status": proof,
        "termination_reason": "RETURNED_CERTIFICATE" if process_ok else "PROCESS_ERROR", "resources": {"wall_s": wall, "solver_s": None, "peak_rss_bytes": None},
        "metrics": {**metrics, "validation_errors": errors, "calibration_only": True, "binary_sha256": sha256(binary) if binary.exists() else None, "runner_sha256": sha256(RUNNER)},
        "artifacts": {"input": str((case_dir / "input.json").relative_to(ROOT)), "solver_output": str(output.relative_to(ROOT)) if output.exists() else None, "solution": str(certificate.relative_to(ROOT)) if certificate.exists() else None, "validation": str((case_dir / "validation.json").relative_to(ROOT)), "stderr": str(stderr.relative_to(ROOT))},
    }
    validate_run_record(record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW)
    args = parser.parse_args()
    cases = {x.name: x for x in make_cases()}
    binaries = (("packingsolver_fork_boxstacks", FORK), ("packingsolver_upstream_boxstacks", UPSTREAM))
    records = [run_one(cases[name], implementation, binary, args.raw_root) for name in CASE_NAMES for implementation, binary in binaries]
    archive = args.raw_root / "artifacts.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        for path in sorted(args.raw_root.rglob("*")):
            if path.is_file() and path != archive:
                handle.add(path, arcname=path.relative_to(args.raw_root))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n" for record in records), encoding="utf-8")
    print(f"wrote {len(records)} B06 boxstacks records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
