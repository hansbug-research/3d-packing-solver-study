#!/usr/bin/env python3
"""Run PackingSolver on the small B30/B31 geometry projections.

The fixtures retain shelf and pallet semantics in the canonical input, but
PackingSolver receives only a generated rectangular geometry CSV.  The output
is therefore deliberately recorded as ``PROJECTION_ONLY`` and is rechecked
by the independent B30/B31 validator.  A valid geometric layout that ignores
the industrial rule is a constraint violation, not a successful FULL run.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks" / "comprehensive"))

from model import canonical_json, load_catalogs, validate_run_record  # noqa: E402
from run_constraint_adapters import independent_validate, load_case  # noqa: E402


RUNNER = Path(__file__).resolve()
VALIDATOR = ROOT / "benchmarks" / "validation.py"
OUTPUT_DEFAULT = ROOT / "results" / "comprehensive" / "runs" / "B30-B31-packingsolver-projection.jsonl"
RAW_DEFAULT = ROOT / "raw" / "experiments" / "comprehensive" / "B30-B31-packingsolver-projection"

IMPLEMENTATIONS = (
    "packingsolver_fork_box",
    "packingsolver_fork_boxstacks",
    "packingsolver_upstream_box",
    "packingsolver_upstream_boxstacks",
)
CASES = ("B30/SHELF_SEQUENCE", "B31/FLAT_MIXED", "B31/STACKABLE", "B31/WEIGHT_INFEASIBLE")
BINARY_BY_IMPLEMENTATION = {
    "packingsolver_fork_box": ROOT / ".cache/build-fork/src/box/packingsolver_box",
    "packingsolver_fork_boxstacks": ROOT / ".cache/build-fork/src/boxstacks/packingsolver_boxstacks",
    "packingsolver_upstream_box": ROOT / ".cache/build-upstream-367/src/box/packingsolver_box",
    "packingsolver_upstream_boxstacks": ROOT / ".cache/build-upstream-367/src/boxstacks/packingsolver_boxstacks",
}
SOURCE_BY_IMPLEMENTATION = {
    implementation: ROOT / (".cache/packingsolver-fork" if "fork" in implementation else ".cache/packingsolver-upstream-367")
    for implementation in IMPLEMENTATIONS
}
COMMIT_BY_IMPLEMENTATION = {
    implementation: ("d953148b8f710c06fa6c410949b7272f9e36327b" if "fork" in implementation else "367ebfdaad11424ded3696b7dae799a30c1375d0")
    for implementation in IMPLEMENTATIONS
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def rel(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def checkout_commit(path: Path, expected: str) -> str:
    actual = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
    if actual != expected:
        raise RuntimeError(f"source commit mismatch: expected {expected}, got {actual}")
    return actual


def write_projection_csv(case_key: str, work: Path) -> tuple[Path, Path]:
    spec, _, _, _, _ = load_case(case_key)
    items_path = work / "items.csv"
    bins_path = work / "bins.csv"
    item_fields = [
        "ID", "X", "Y", "Z", "ROTATION_XYZ", "ROTATION_YXZ", "ROTATION_ZYX",
        "ROTATION_YZX", "ROTATION_XZY", "ROTATION_ZXY", "WEIGHT", "COPIES",
        "GROUP_ID", "STACKABILITY_ID", "NESTING_HEIGHT", "MAXIMUM_STACKABILITY", "MAXIMUM_WEIGHT_ABOVE",
    ]
    with items_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=item_fields)
        writer.writeheader()
        for item in spec["items"]:
            # All axis permutations are intentional: the industrial fields
            # are removed only for this explicitly named geometry projection.
            writer.writerow({
                "ID": item["id"], "X": item["size"][0], "Y": item["size"][1], "Z": item["size"][2],
                "ROTATION_XYZ": 1, "ROTATION_YXZ": 1, "ROTATION_ZYX": 1,
                "ROTATION_YZX": 1, "ROTATION_XZY": 1, "ROTATION_ZXY": 1,
                "WEIGHT": item.get("weight", 0), "COPIES": 1, "GROUP_ID": 0,
                "STACKABILITY_ID": 0, "NESTING_HEIGHT": 0,
                "MAXIMUM_STACKABILITY": item.get("max_stackability", 999999),
                "MAXIMUM_WEIGHT_ABOVE": item.get("max_weight_above", 999999999),
            })
    bin_fields = [
        "ID", "X", "Y", "Z", "COST", "COPIES", "MAXIMUM_WEIGHT", "MAXIMUM_STACK_DENSITY",
        "IS_SEMI_TRAILER_TRUCK", "REAR_AXLE_MAXIMUM_WEIGHT", "MIDDLE_AXLE_MAXIMUM_WEIGHT",
    ]
    with bins_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=bin_fields)
        writer.writeheader()
        for bin_spec in spec["bins"]:
            writer.writerow({
                "ID": bin_spec["id"], "X": bin_spec["size"][0], "Y": bin_spec["size"][1], "Z": bin_spec["size"][2],
                "COST": bin_spec.get("cost", 1), "COPIES": 1,
                "MAXIMUM_WEIGHT": bin_spec.get("max_weight", 999999999), "MAXIMUM_STACK_DENSITY": 100,
                "IS_SEMI_TRAILER_TRUCK": 0, "REAR_AXLE_MAXIMUM_WEIGHT": 999999999,
                "MIDDLE_AXLE_MAXIMUM_WEIGHT": 999999999,
            })
    return items_path, bins_path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def parse_certificate(case_key: str, certificate: Path) -> dict[str, Any]:
    """Convert PackingSolver's pattern certificate to canonical placements."""
    spec, _, _, _, _ = load_case(case_key)
    rows = read_csv(certificate)
    # The CSV writer uses a dense numeric row ID even when the input ID is a
    # business identifier such as ``product-14:0``.  Map both the original
    # value and the deterministic row index back to the canonical spec.
    item_ids = [str(item["id"]) for item in spec["items"]]
    bin_ids = [str(row["id"]) for row in spec["bins"]]
    pattern_to_bin: dict[str, list[str]] = {}
    bins_by_id = {str(row["id"]): row for row in spec["bins"]}
    for index, row in enumerate(row for row in rows if row.get("TYPE") == "BIN"):
        source_id = str(row.get("ID", ""))
        if source_id.isdigit() and int(source_id) < len(bin_ids):
            source_id = bin_ids[int(source_id)]
        if source_id not in bins_by_id:
            continue
        pattern = str(row.get("BIN", index))
        copies = int(row.get("COPIES", "0") or 0)
        pattern_to_bin[pattern] = [source_id if copies else source_id for _ in range(max(copies, 1))]
    placements: list[dict[str, Any]] = []
    for index, row in enumerate(row for row in rows if row.get("TYPE") == "ITEM"):
        item_id = str(row.get("ID", ""))
        if item_id.isdigit() and int(item_id) < len(item_ids):
            item_id = item_ids[int(item_id)]
        pattern = str(row.get("BIN", ""))
        physical = pattern_to_bin.get(pattern)
        if not physical:
            # The validator will report an unknown bin; keeping the row gives
            # us a complete failure artifact instead of silently dropping it.
            physical = [pattern]
        copies = int(row.get("COPIES", "0") or 0)
        for copy in range(max(copies, 1)):
            placements.append({
                "item_id": item_id,
                "bin_id": physical[min(copy, len(physical) - 1)],
                "position": [float(row.get(axis, 0)) for axis in ("X", "Y", "Z")],
                "size": [float(row.get(axis, 0)) for axis in ("LX", "LY", "LZ")],
            })
    return {"placements": placements}


def normalized_command(command: list[str]) -> list[str]:
    output = []
    for token in command:
        try:
            output.append(rel(Path(token)))
        except (ValueError, OSError):
            output.append(token)
    return output


def run_one(case_key: str, implementation_id: str, time_limit: float, work_root: Path, archive_rel: str) -> dict[str, Any]:
    spec, item_meta, bin_meta, _, _ = load_case(case_key)
    case_name = case_key.replace("/", "_")
    case_dir = work_root / case_name / implementation_id
    case_dir.mkdir(parents=True, exist_ok=True)
    items_path, bins_path = write_projection_csv(case_key, case_dir)
    output_path = case_dir / "output.json"
    certificate_path = case_dir / "solution.csv"
    stdout_path = case_dir / "stdout.log"
    stderr_path = case_dir / "stderr.log"
    validation_path = case_dir / "validation.json"
    config_path = case_dir / "effective-config.json"
    binary = BINARY_BY_IMPLEMENTATION[implementation_id]
    source_root = SOURCE_BY_IMPLEMENTATION[implementation_id]
    source_commit = checkout_commit(source_root, COMMIT_BY_IMPLEMENTATION[implementation_id])
    command = [
        str(binary), "--items", str(items_path), "--bins", str(bins_path),
        "--objective", "bin-packing", "--time-limit", str(time_limit),
        "--memory-limit", "1024", "--verbosity-level", "0", "--only-write-at-the-end",
        "--output", str(output_path), "--certificate", str(certificate_path),
    ]
    config_path.write_text(canonical_json({
        "benchmark_id": spec["benchmark_id"], "problem_variant": spec["problem_variant"],
        "implementation_id": implementation_id, "source_commit": source_commit,
        "binary_sha256": sha256(binary), "runner_sha256": sha256(RUNNER),
        "validator_sha256": sha256(VALIDATOR), "time_limit_s": time_limit,
        "projection_removed_constraints": ["source_pose_whitelist", "shelf_bay_sequence", "pallet_stack_rules"],
        "command": normalized_command(command),
    }), encoding="utf-8")
    started = perf_counter()
    env = {
        **os.environ, "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1",
    }
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=max(30.0, time_limit + 20.0), env=env, check=False)
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
    except subprocess.TimeoutExpired as exc:
        completed = None
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text(exc.stderr or "", encoding="utf-8")
    wall_s = perf_counter() - started
    process_ok = completed is not None and completed.returncode == 0 and output_path.exists() and certificate_path.exists()
    if process_ok:
        try:
            payload = parse_certificate(case_key, certificate_path)
            solution_status, metrics = independent_validate(spec, item_meta, bin_meta, payload)
        except Exception as exc:  # preserve malformed output as evidence
            payload = {"placements": []}
            solution_status = "INVALID_CERTIFICATE"
            metrics = {"validation_errors": [f"certificate parser: {type(exc).__name__}: {exc}"], "validation_error_count": 1,
                       "packed_items": 0, "required_items": len(spec["items"]), "bins_used": 0, "hard_violation_count": 0}
    else:
        payload = {"placements": []}
        solution_status = "NO_SOLUTION"
        metrics = {"validation_errors": ["solver failed, timed out, or omitted output/certificate"], "validation_error_count": 1,
                   "packed_items": 0, "required_items": len(spec["items"]), "bins_used": 0, "hard_violation_count": 0}
    validation_path.write_text(canonical_json(metrics), encoding="utf-8")
    run_status = "COMPLETED" if process_ok else "ERROR"
    if completed is None:
        run_status = "TIME_LIMIT"
    input_payload = {"benchmark_id": spec["benchmark_id"], "problem_variant": spec["problem_variant"], "items": spec["items"], "bins": spec["bins"]}
    record = {
        "schema_version": 2, "protocol_version": "benchmark-protocol/3", "record_origin": "PROTOCOL_V3",
        "run_id": f"{spec['benchmark_id']}/{spec['problem_variant']}/{implementation_id}/{time_limit:g}s/geometry-projection/rep-0",
        "benchmark_id": spec["benchmark_id"], "problem_variant": spec["problem_variant"],
        "instance_id": spec["scenario"], "implementation_id": implementation_id,
        "algorithm": next(row["algorithm"] for row in load_catalogs()[1]["implementations"] if row["id"] == implementation_id),
        "adapter": "industrial_projection/packingsolver_csv_v1", "comparison_track": "COMPOSED", "problem_scope": "GEOMETRY_PROJECTION",
        "budget": {"time_limit_s": time_limit, "memory_limit_bytes": 1073741824, "thread_limit": 1},
        "item_order": "CANONICAL", "bin_order": "CANONICAL", "seed": None, "repetition": 0,
        "input_sha256": digest(input_payload), "input_status": "VALID", "capability_status": "PROJECTION_ONLY",
        "run_status": run_status, "solution_status": solution_status, "proof_status": "FEASIBLE" if solution_status in {"VALID_COMPLETE", "VALID_PARTIAL", "CONSTRAINT_VIOLATION"} else "UNKNOWN",
        "termination_reason": "RETURNED_PROJECTION" if process_ok else "PROCESS_ERROR",
        "resources": {"wall_s": wall_s, "solver_s": None, "peak_rss_bytes": None},
        "metrics": {
            **metrics, "projection_removed_constraints": ["source_pose_whitelist", "shelf_bay_sequence", "pallet_stack_rules"],
            "projection_reason": "PackingSolver receives rectangular geometry only; original industrial fields remain in validator input",
            "provenance_kind": "FRESH_SOLVER_INVOCATION", "source_commit": source_commit,
            "binary_sha256": sha256(binary), "runner_sha256": sha256(RUNNER), "command": normalized_command(command),
        },
        "artifacts": {
            "input": f"{archive_rel}#{case_name}/{implementation_id}/effective-config.json",
            "effective_config": f"{archive_rel}#{case_name}/{implementation_id}/effective-config.json",
            "solver_output": f"{archive_rel}#{case_name}/{implementation_id}/output.json" if output_path.exists() else None,
            "solution": f"{archive_rel}#{case_name}/{implementation_id}/solution.csv" if certificate_path.exists() else None,
            "validation": f"{archive_rel}#{case_name}/{implementation_id}/validation.json",
            "stdout": f"{archive_rel}#{case_name}/{implementation_id}/stdout.log",
            "stderr": f"{archive_rel}#{case_name}/{implementation_id}/stderr.log",
        },
    }
    validate_run_record(record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--implementation", action="append", choices=IMPLEMENTATIONS)
    parser.add_argument("--case", action="append", choices=CASES)
    parser.add_argument("--time-limit", type=float, default=10.0)
    parser.add_argument("--output", type=Path, default=OUTPUT_DEFAULT)
    parser.add_argument("--raw-root", type=Path, default=RAW_DEFAULT)
    args = parser.parse_args()
    implementations = args.implementation or list(IMPLEMENTATIONS)
    cases = args.case or list(CASES)
    for implementation in implementations:
        if not BINARY_BY_IMPLEMENTATION[implementation].is_file():
            raise SystemExit(f"missing binary: {BINARY_BY_IMPLEMENTATION[implementation]}")
    args.raw_root.mkdir(parents=True, exist_ok=True)
    archive_path = args.raw_root / "artifacts.tar.gz"
    archive_rel = rel(archive_path)
    records: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="b30-b31-ps-projection-") as temporary:
        work_root = Path(temporary)
        for case_key in cases:
            for implementation in implementations:
                records.append(run_one(case_key, implementation, args.time_limit, work_root, archive_rel))
        with tarfile.open(archive_path, "w:gz") as archive:
            for path in sorted(work_root.rglob("*")):
                if path.is_file():
                    archive.add(path, arcname=path.relative_to(work_root))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n" for row in sorted(records, key=lambda row: row["run_id"])), encoding="utf-8")
    print(f"wrote {len(records)} records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
