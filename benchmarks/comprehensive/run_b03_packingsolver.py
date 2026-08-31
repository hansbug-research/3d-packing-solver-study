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
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from time import perf_counter
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks"))

from comprehensive.model import canonical_json, load_catalogs, validate_run_record
from validation import Box, validate_aabbs


INDEX_PATH = ROOT / "benchmarks" / "data" / "comprehensive" / "b03-source-index.json"
RUNNER_PATH = Path(__file__).resolve()
SHARED_VALIDATOR_PATH = ROOT / "benchmarks" / "validation.py"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def payload_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def verified_source_commit(source_root: Path, expected_commit: str) -> str:
    commit = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "-C", str(source_root), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if commit != expected_commit:
        raise ValueError(f"binary source commit {commit} differs from catalog version {expected_commit}")
    if dirty:
        raise ValueError(f"binary source worktree is dirty: {source_root}")
    return commit


def repository_path(path: Path) -> str:
    resolved = path.resolve()
    return str(resolved.relative_to(ROOT)) if resolved.is_relative_to(ROOT) else str(resolved)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def parse_resources(path: Path) -> dict[str, float | int | str]:
    resources: dict[str, float | int | str] = {}
    for line in path.read_text(errors="replace").splitlines() if path.exists() else []:
        line = line.strip()
        if line.startswith("Maximum resident set size"):
            resources["peak_rss_bytes"] = int(line.rsplit(": ", 1)[-1]) * 1024
        elif line.startswith("User time"):
            resources["cpu_user_s"] = float(line.rsplit(": ", 1)[-1])
        elif line.startswith("System time"):
            resources["cpu_system_s"] = float(line.rsplit(": ", 1)[-1])
        elif line.startswith("Elapsed (wall clock) time"):
            resources["process_elapsed_text"] = line.rsplit(": ", 1)[-1]
    return resources


def input_paths(source_root: Path, instance_id: str) -> tuple[Path, Path, Path]:
    raw = source_root / "data" / "box_raw" / "egeblad2009" / instance_id
    items = source_root / "data" / "box" / "egeblad2009" / f"{instance_id}_items.csv"
    bins = source_root / "data" / "box" / "egeblad2009" / f"{instance_id}_bins.csv"
    return raw, items, bins


def validate_source(index_row: dict[str, Any], source_root: Path) -> tuple[Path, Path]:
    raw, items, bins = input_paths(source_root, index_row["id"])
    for kind, path in (("raw", raw), ("items", items), ("bins", bins)):
        if not path.exists() or sha256(path) != index_row["sha256"][kind]:
            raise ValueError(f"B03 input hash mismatch: {index_row['id']}:{kind}:{path}")
    return items, bins


def validate_certificate(
    index_row: dict[str, Any],
    items_path: Path,
    bins_path: Path,
    output_path: Path,
    certificate_path: Path,
) -> dict[str, Any]:
    errors: list[str] = []
    output = json.loads(output_path.read_text(encoding="utf-8"))
    final = output["Output"]
    solution = final["Solution"]
    item_specs = {row["ID"]: row for row in read_csv(items_path)}
    bin_specs = {row["ID"]: row for row in read_csv(bins_path)}
    rows = read_csv(certificate_path)
    bin_rows = [row for row in rows if row["TYPE"] == "BIN"]
    item_rows = [row for row in rows if row["TYPE"] == "ITEM"]
    if len(bin_rows) > 1:
        errors.append(f"certificate uses {len(bin_rows)} bin rows for a one-container knapsack")

    physical_bins: dict[str, list[str]] = {}
    bin_sizes: dict[str, tuple[float, float, float]] = {}
    for row_index, row in enumerate(bin_rows):
        copies = int(row["COPIES"])
        pattern = row["BIN"]
        ids = [f"pattern-{pattern}-row-{row_index}-copy-{copy}" for copy in range(copies)]
        physical_bins[pattern] = ids
        dimensions = tuple(float(row[axis]) for axis in ("LX", "LY", "LZ"))
        for ref in ids:
            bin_sizes[ref] = dimensions
        spec = bin_specs.get(row["ID"])
        if spec is None:
            errors.append(f"unknown bin type {row['ID']}")
        elif dimensions != tuple(float(spec[axis]) for axis in ("X", "Y", "Z")):
            errors.append(f"bin {row['ID']} dimensions differ from input")

    counts: Counter[str] = Counter()
    placements: list[Box] = []
    packed_profit = 0.0
    packed_volume = 0.0
    for row_index, row in enumerate(item_rows):
        spec = item_specs.get(row["ID"])
        if spec is None:
            errors.append(f"unknown item type {row['ID']}")
            continue
        pattern_bins = physical_bins.get(row["BIN"], [])
        copies = int(row["COPIES"])
        if copies != len(pattern_bins):
            errors.append(f"item row {row_index} copies {copies} differ from physical pattern copies {len(pattern_bins)}")
            continue
        if row["ROTATION"] != "XYZ":
            errors.append(f"item {row['ID']} uses forbidden fixed-pose rotation {row['ROTATION']}")
        expected_dimensions = tuple(float(spec[axis]) for axis in ("X", "Y", "Z"))
        actual_dimensions = tuple(float(row[axis]) for axis in ("LX", "LY", "LZ"))
        if actual_dimensions != expected_dimensions:
            errors.append(f"item {row['ID']} dimensions differ from fixed XYZ input")
        for copy, bin_ref in enumerate(pattern_bins):
            counts[row["ID"]] += 1
            packed_profit += float(spec["PROFIT"])
            packed_volume += float(spec["X"]) * float(spec["Y"]) * float(spec["Z"])
            placements.append(
                Box(
                    ref=f"{row['ID']}:{row_index}:{copy}",
                    bin_ref=bin_ref,
                    x=float(row["X"]),
                    y=float(row["Y"]),
                    z=float(row["Z"]),
                    dx=float(row["LX"]),
                    dy=float(row["LY"]),
                    dz=float(row["LZ"]),
                )
            )
    errors.extend(validate_aabbs(placements, bin_sizes))
    for item_id, count in counts.items():
        available = int(item_specs[item_id]["COPIES"])
        if count > available:
            errors.append(f"item type {item_id} placed {count}, available {available}")

    reported_items = int(solution["NumberOfItems"])
    reported_profit = float(solution["ItemProfit"])
    reported_volume = float(solution["ItemVolume"])
    if len(placements) != reported_items:
        errors.append(f"certificate has {len(placements)} placements, solver reports {reported_items}")
    if packed_profit != reported_profit:
        errors.append(f"certificate profit {packed_profit} differs from solver {reported_profit}")
    if packed_volume != reported_volume:
        errors.append(f"certificate volume {packed_volume} differs from solver {reported_volume}")
    if reported_items and len(bin_sizes) != 1:
        errors.append(f"nonempty solution has {len(bin_sizes)} physical containers")
    if int(solution["NumberOfUnpackedItems"]) != index_row["item_count"] - reported_items:
        errors.append("solver packed/unpacked counts do not sum to the source item count")

    bound = float(final["KnapsackBound"]) if final.get("KnapsackBound") is not None else None
    gap = (bound - reported_profit) / bound if bound and bound > 0 else None
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "placements": len(placements),
        "packed_profit": reported_profit,
        "packed_volume": packed_volume,
        "solver_bound": bound,
        "solver_relative_gap": gap,
        "solver_time_s": float(final["Time"]),
        "bins_used": int(solution["NumberOfBins"]),
        "unpacked_items": int(solution["NumberOfUnpackedItems"]),
    }


def artifact_reference(archive_relative: str, case_name: str, member: str) -> str:
    return f"{archive_relative}#{case_name}/{member}"


def run_one(
    index_row: dict[str, Any],
    source_root: Path,
    binary: Path,
    implementation: dict[str, Any],
    time_limit: float,
    label: str,
    work_root: Path,
    archive_relative: str,
    source_commit: str,
    binary_source_commit: str,
    binary_sha256: str,
    runner_sha256: str,
    shared_validator_sha256: str,
) -> dict[str, Any]:
    instance_id = index_row["id"]
    case_name = instance_id.removesuffix(".3kp")
    case_dir = work_root / case_name
    case_dir.mkdir()
    items_path, bins_path = validate_source(index_row, source_root)
    output_path = case_dir / "output.json"
    certificate_path = case_dir / "solution.csv"
    stdout_path = case_dir / "stdout.log"
    stderr_path = case_dir / "stderr.log"
    resource_path = case_dir / "resources.txt"
    validation_path = case_dir / "validation.json"
    input_reference_path = case_dir / "input.json"
    config_path = case_dir / "effective-config.json"

    command = [
        "/usr/bin/time", "-v", "-o", str(resource_path),
        str(binary),
        "--items", str(items_path),
        "--bins", str(bins_path),
        "--objective", "knapsack",
        "--no-item-rotation",
        "--time-limit", str(time_limit),
        "--memory-limit", "1024",
        "--verbosity-level", "0",
        "--only-write-at-the-end",
        "--output", str(output_path),
        "--certificate", str(certificate_path),
    ]
    input_payload = {
        "benchmark_id": "B03",
        "instance": index_row,
        "source_repository": "HansBug/packingsolver",
        "source_commit": source_commit,
        "source_paths": {
            "items": str(items_path.relative_to(source_root)),
            "bins": str(bins_path.relative_to(source_root)),
        },
    }
    config = {
        "command": command,
        "implementation_id": implementation["id"],
        "implementation_version": implementation["version"],
        "binary_sha256": binary_sha256,
        "binary_source_commit": binary_source_commit,
        "runner_sha256": runner_sha256,
        "shared_validator_sha256": shared_validator_sha256,
        "time_limit_s": time_limit,
        "memory_limit_bytes": 1073741824,
        "thread_limit": None,
        "pose_semantics": "FIXED_XYZ",
        "environment_threads": 1,
    }
    input_reference_path.write_text(canonical_json(input_payload), encoding="utf-8")
    config_path.write_text(canonical_json(config), encoding="utf-8")

    environment = os.environ.copy()
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        environment[name] = "1"
    started = perf_counter()
    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=max(30.0, time_limit + 20.0),
            env=environment,
        )
        wall_s = perf_counter() - started
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        process_ok = completed.returncode == 0 and output_path.exists() and certificate_path.exists()
    except subprocess.TimeoutExpired as exc:
        wall_s = perf_counter() - started
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text(exc.stderr or "", encoding="utf-8")
        completed = None
        process_ok = False

    if process_ok:
        validation = validate_certificate(index_row, items_path, bins_path, output_path, certificate_path)
    else:
        validation = {
            "status": "FAIL",
            "errors": ["solver process failed, timed out externally, or omitted output/certificate"],
            "placements": 0,
            "packed_profit": None,
            "packed_volume": None,
            "solver_bound": None,
            "solver_relative_gap": None,
            "solver_time_s": None,
            "bins_used": None,
            "unpacked_items": index_row["item_count"],
        }
    validation_path.write_text(canonical_json(validation), encoding="utf-8")
    process_resources = parse_resources(resource_path)
    solver_s = validation["solver_time_s"]
    reached_limit = solver_s is not None and solver_s >= time_limit * 0.95
    valid = validation["status"] == "PASS"
    proof_closed = valid and validation["solver_relative_gap"] is not None and abs(validation["solver_relative_gap"]) <= 1e-12
    if not process_ok:
        run_status = "ERROR"
        termination_reason = "PROCESS_ERROR_OR_EXTERNAL_TIMEOUT"
    elif reached_limit and not proof_closed:
        run_status = "TIME_LIMIT"
        termination_reason = "TIME_LIMIT_WITH_INCUMBENT"
    else:
        run_status = "COMPLETED"
        termination_reason = "BOUND_CLOSED" if proof_closed else "SOLVER_STOPPED"

    input_sha = payload_hash(index_row["sha256"])
    upstream_reference = index_row["upstream_reference_profit"]
    packed_profit = validation["packed_profit"]
    total_available_profit = index_row["total_profit"]
    record = {
        "schema_version": 2,
        "protocol_version": "benchmark-protocol/3",
        "record_origin": "PROTOCOL_V3",
        "run_id": f"B03/FIXED_XYZ/{instance_id}/{implementation['id']}/{label}/SOLVER_INTERNAL/rep-0",
        "benchmark_id": "B03",
        "problem_variant": "FIXED_XYZ",
        "instance_id": instance_id,
        "implementation_id": implementation["id"],
        "algorithm": implementation["algorithm"],
        "adapter": None,
        "comparison_track": "NATIVE",
        "problem_scope": "FULL_PROBLEM",
        "budget": {"time_limit_s": time_limit, "memory_limit_bytes": 1073741824, "thread_limit": None},
        "item_order": "SOLVER_INTERNAL",
        "bin_order": "SOURCE",
        "seed": None,
        "repetition": 0,
        "input_sha256": input_sha,
        "input_status": "VALID",
        "capability_status": "SUPPORTED_NATIVE",
        "run_status": run_status,
        "solution_status": "VALID_PARTIAL" if valid else "INVALID_CERTIFICATE" if process_ok else "NO_SOLUTION",
        "proof_status": "PROVEN_OPTIMAL" if proof_closed else "FEASIBLE" if valid else "UNKNOWN",
        "termination_reason": termination_reason,
        "resources": {
            "wall_s": wall_s,
            "solver_s": solver_s,
            "peak_rss_bytes": process_resources.get("peak_rss_bytes"),
            "cpu_user_s": process_resources.get("cpu_user_s"),
            "cpu_system_s": process_resources.get("cpu_system_s"),
        },
        "metrics": {
            "packed_profit": packed_profit,
            "total_available_profit": total_available_profit,
            "packed_profit_fraction": packed_profit / total_available_profit if packed_profit is not None else None,
            "packed_volume": validation["packed_volume"],
            "packed_items": validation["placements"],
            "unpacked_items": validation["unpacked_items"],
            "solver_bound": validation["solver_bound"],
            "solver_relative_gap": validation["solver_relative_gap"],
            "upstream_reference_profit": upstream_reference,
            "upstream_reference_status": index_row["reference_status"],
            "gap_to_upstream_reference": None,
            "validation_error_count": len(validation["errors"]),
        },
        "artifacts": {
            "input": artifact_reference(archive_relative, case_name, "input.json"),
            "effective_config": artifact_reference(archive_relative, case_name, "effective-config.json"),
            "solver_output": artifact_reference(archive_relative, case_name, "output.json") if output_path.exists() else None,
            "solution": artifact_reference(archive_relative, case_name, "solution.csv") if certificate_path.exists() else None,
            "validation": artifact_reference(archive_relative, case_name, "validation.json"),
            "stdout": artifact_reference(archive_relative, case_name, "stdout.log"),
            "stderr": artifact_reference(archive_relative, case_name, "stderr.log"),
            "resources": artifact_reference(archive_relative, case_name, "resources.txt") if resource_path.exists() else None,
        },
    }
    validate_run_record(record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="Run B03 fixed-pose profit knapsack with PackingSolver")
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--implementation-id", choices=("packingsolver_fork_box", "packingsolver_upstream_box"), required=True)
    parser.add_argument("--source-root", type=Path, default=ROOT / ".cache" / "packingsolver-fork")
    parser.add_argument("--binary-source-root", type=Path, required=True)
    parser.add_argument("--time-limit", type=float, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--results-root", type=Path, default=ROOT / "results" / "comprehensive")
    parser.add_argument("--raw-root", type=Path, default=ROOT / "raw" / "experiments" / "comprehensive")
    args = parser.parse_args()

    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    _, implementation_catalog = load_catalogs()
    implementations = {row["id"]: row for row in implementation_catalog["implementations"]}
    implementation = implementations[args.implementation_id]
    binary = args.binary.resolve()
    source_root = args.source_root.resolve()
    binary_source_root = args.binary_source_root.resolve()
    if not binary.is_file():
        raise ValueError(f"PackingSolver binary is missing: {binary}")
    binary_source_commit = verified_source_commit(binary_source_root, implementation["version"])
    binary_sha256 = sha256(binary)
    runner_sha256 = sha256(RUNNER_PATH)
    shared_validator_sha256 = sha256(SHARED_VALIDATOR_PATH)
    instances = index["instances"][: args.limit] if args.limit is not None else index["instances"]

    raw_dir = args.raw_root / "B03" / args.implementation_id / args.label
    archive_path = raw_dir / "artifacts.tar.gz"
    archive_relative = repository_path(archive_path)
    runs_dir = args.results_root / "runs"
    raw_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)
    records: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory(prefix=f"b03-{args.implementation_id}-{args.label}-") as temporary:
        work_root = Path(temporary)
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = {
                executor.submit(
                    run_one,
                    row,
                    source_root,
                    binary,
                    implementation,
                    args.time_limit,
                    args.label,
                    work_root,
                    archive_relative,
                    index["source_commit"],
                    binary_source_commit,
                    binary_sha256,
                    runner_sha256,
                    shared_validator_sha256,
                ): row
                for row in instances
            }
            for completed_count, future in enumerate(as_completed(futures), 1):
                row = futures[future]
                records[row["id"]] = future.result()
                if completed_count % 10 == 0 or completed_count == len(instances):
                    print(f"B03 {args.implementation_id} {args.label}: {completed_count}/{len(instances)}", flush=True)
        with tarfile.open(archive_path, "w:gz") as archive:
            for path in sorted(work_root.rglob("*")):
                if path.is_file():
                    archive.add(path, arcname=path.relative_to(work_root))

    ordered = [records[row["id"]] for row in instances]
    run_path = runs_dir / f"B03-{args.implementation_id}-{args.label}.jsonl"
    run_path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n" for row in ordered), encoding="utf-8")
    status_counts = Counter(row["solution_status"] for row in ordered)
    summary = {
        "schema_version": 1,
        "protocol_version": "benchmark-protocol/3",
        "benchmark_id": "B03",
        "implementation_id": args.implementation_id,
        "implementation_version": implementation["version"],
        "binary_sha256": binary_sha256,
        "binary_source_commit": binary_source_commit,
        "runner_sha256": runner_sha256,
        "shared_validator_sha256": shared_validator_sha256,
        "time_limit_s": args.time_limit,
        "label": args.label,
        "instances": len(ordered),
        "solution_status_counts": dict(sorted(status_counts.items())),
        "artifact_archive": archive_relative,
        "artifact_archive_sha256": sha256(raw_dir / "artifacts.tar.gz"),
        "run_jsonl_sha256": sha256(run_path),
        "source_index_sha256": sha256(INDEX_PATH),
    }
    (raw_dir / "metadata.json").write_text(canonical_json(summary), encoding="utf-8")
    summary_path = args.results_root / f"B03-{args.implementation_id}-{args.label}-summary.json"
    summary_path.write_text(canonical_json(summary), encoding="utf-8")
    print(run_path.relative_to(ROOT) if run_path.is_relative_to(ROOT) else run_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
