#!/usr/bin/env python3
"""Run the audited open-X calibration fixtures through PackingSolver.

The fixtures are fork-owned regression inputs, so this runner reports a
calibration result rather than an independent public-quality score.  The
certificate is independently checked for fixed XYZ orientation, completeness,
bin bounds, overlap, and the used open dimension (XMax).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import tarfile
import tempfile
from collections import Counter
from pathlib import Path
from time import perf_counter
from typing import Any
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks"))
SOURCE = ROOT / "benchmarks" / "data" / "comprehensive" / "b11-open-dimension" / "source.json"
FORK = ROOT / ".cache" / "packingsolver-fork"
UPSTREAM = ROOT / ".cache" / "packingsolver-upstream-367"
FORK_COMMIT = "d953148b8f710c06fa6c410949b7272f9e36327b"
UPSTREAM_COMMIT = "367ebfdaad11424ded3696b7dae799a30c1375d0"
RUNNER = Path(__file__).resolve()
VALIDATOR = ROOT / "benchmarks" / "validation.py"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def payload_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def checkout_commit(path: Path, expected: str) -> str:
    actual = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
    if actual != expected:
        raise RuntimeError(f"source commit mismatch for {path}: expected {expected}, got {actual}")
    dirty = subprocess.check_output(["git", "-C", str(path), "status", "--porcelain"], text=True).strip()
    if dirty:
        raise RuntimeError(f"source checkout is dirty: {path}")
    return actual


def load_cases() -> list[dict[str, Any]]:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = []
    for case in payload["cases"]:
        source_case = case["source_case"]
        directory = FORK / "data" / "box" / "tests" / f"open_dimension_x_4_different_items_{source_case}"
        items_path = directory / "items.csv"
        bins_path = directory / "bins.csv"
        parameters_path = directory / "parameters.csv"
        items = read_csv(items_path)
        bins = read_csv(bins_path)
        if len(bins) != 1 or len(items) != len(case["items"]):
            raise RuntimeError(f"fixture shape mismatch: {case['id']}")
        logical = {"benchmark_id": "B11", "case": case, "items_csv": sha256(items_path), "bins_csv": sha256(bins_path), "parameters_csv": sha256(parameters_path)}
        cases.append({"id": case["id"], "source_case": source_case, "directory": directory, "items_path": items_path, "bins_path": bins_path, "parameters_path": parameters_path, "items": items, "bins": bins, "bin_size": tuple(float(bins[0][axis]) for axis in ("X", "Y", "Z")), "payload": logical, "input_sha256": payload_hash(logical)})
    return cases


def validate_certificate(case: dict[str, Any], output_path: Path, certificate_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    rows = read_csv(certificate_path)
    bins = [row for row in rows if row.get("TYPE") == "BIN"]
    items = [row for row in rows if row.get("TYPE") == "ITEM"]
    if len(bins) != 1:
        errors.append(f"expected one BIN row, got {len(bins)}")
    expected_bin = case["bin_size"]
    bin_ref = "0"
    if bins:
        row = bins[0]
        try:
            dimensions = tuple(float(row[axis]) for axis in ("LX", "LY", "LZ"))
            bin_ref = row.get("BIN", "0")
            if dimensions != expected_bin:
                errors.append(f"bin dimensions differ: {dimensions} != {expected_bin}")
        except (KeyError, ValueError) as exc:
            errors.append(f"invalid BIN row: {exc}")
    placements = []
    expected_ids = {str(index) for index in range(len(case["items"]))}
    seen: Counter[str] = Counter()
    for index, row in enumerate(items):
        item_id = row.get("ID", "")
        if item_id not in expected_ids:
            errors.append(f"unknown item ID {item_id}")
            continue
        seen[item_id] += int(row.get("COPIES", "0") or 0)
        if row.get("ROTATION") != "XYZ":
            errors.append(f"item {item_id} has non-XYZ rotation {row.get('ROTATION')}")
        spec = case["items"][int(item_id)]
        try:
            dimensions = tuple(float(row[axis]) for axis in ("LX", "LY", "LZ"))
            expected = tuple(float(spec[axis]) for axis in ("X", "Y", "Z"))
            if dimensions != expected:
                errors.append(f"item {item_id} dimensions differ from XYZ source")
            placements.append(__import__("validation").Box(ref=f"{item_id}:{index}", bin_ref=bin_ref, x=float(row["X"]), y=float(row["Y"]), z=float(row["Z"]), dx=dimensions[0], dy=dimensions[1], dz=dimensions[2]))
        except (KeyError, ValueError) as exc:
            errors.append(f"invalid ITEM row {index}: {exc}")
    for item_id in expected_ids:
        if seen[item_id] != 1:
            errors.append(f"item {item_id} copies {seen[item_id]} != 1")
    from validation import validate_aabbs
    errors.extend(validate_aabbs(placements, {bin_ref: expected_bin}))
    used_x = max((box.x + box.dx for box in placements), default=0.0)
    output = json.loads(output_path.read_text(encoding="utf-8"))
    final = output.get("Output", {})
    solution = final.get("Solution", {})
    if int(solution.get("NumberOfItems", -1)) != len(placements):
        errors.append("solver item count differs from certificate")
    if int(solution.get("NumberOfUnpackedItems", -1)) != 0:
        errors.append("solver reports unpacked items")
    reported_x = float(solution.get("XMax", 0.0))
    if abs(reported_x - used_x) > 1e-9:
        errors.append(f"XMax {reported_x} differs from certificate extent {used_x}")
    return {"status": "PASS" if not errors else "FAIL", "errors": errors, "packed_items": len(placements), "required_items": len(case["items"]), "complete": len(placements) == len(case["items"]) and not errors, "used_length": used_x, "solver_bound": final.get("OpenDimensionXBound"), "solver_time_s": final.get("Time"), "bins_used": solution.get("NumberOfBins")}


def run_one(case: dict[str, Any], implementation_id: str, binary: Path, source_root: Path, source_commit: str, time_limit: float, work_root: Path, archive_relative: str) -> dict[str, Any]:
    directory = work_root / case["id"] / implementation_id
    directory.mkdir(parents=True)
    output_path = directory / "output.json"
    certificate_path = directory / "solution.csv"
    stdout_path = directory / "stdout.log"
    stderr_path = directory / "stderr.log"
    config_path = directory / "effective-config.json"
    validation_path = directory / "validation.json"
    command = [str(binary), "--items", str(case["items_path"]), "--bins", str(case["bins_path"]), "--parameters", str(case["parameters_path"]), "--objective", "open-dimension-x", "--time-limit", str(time_limit), "--memory-limit", "1024", "--verbosity-level", "0", "--only-write-at-the-end", "--output", str(output_path), "--certificate", str(certificate_path)]
    config_path.write_text(canonical({"command": command, "benchmark_id": "B11", "instance_id": case["id"], "implementation_id": implementation_id, "time_limit_s": time_limit, "source_commit": checkout_commit(source_root, source_commit), "binary_sha256": sha256(binary), "runner_sha256": sha256(RUNNER), "validator_sha256": sha256(VALIDATOR), "pose_semantics": "FIXED_XYZ", "objective": "open-dimension-x"}), encoding="utf-8")
    started = perf_counter()
    env = {**os.environ, "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"}
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=max(30.0, time_limit + 20.0), env=env, check=False)
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        process_ok = completed.returncode == 0 and output_path.exists() and certificate_path.exists()
    except subprocess.TimeoutExpired as exc:
        completed = None
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text(exc.stderr or "", encoding="utf-8")
        process_ok = False
    wall_s = perf_counter() - started
    if process_ok:
        validation = validate_certificate(case, output_path, certificate_path)
    else:
        validation = {"status": "FAIL", "errors": ["solver process failed, timed out, or omitted output/certificate"], "packed_items": 0, "required_items": len(case["items"]), "complete": False, "used_length": None, "solver_bound": None, "solver_time_s": None, "bins_used": None}
    validation_path.write_text(canonical(validation), encoding="utf-8")
    valid = validation["status"] == "PASS"
    run_status = "COMPLETED" if process_ok else "ERROR"
    record = {
        "schema_version": 2, "protocol_version": "benchmark-protocol/3", "record_origin": "PROTOCOL_V3",
        "run_id": f"B11/{case['id']}/{implementation_id}/{time_limit:g}s/native/rep-0", "benchmark_id": "B11", "problem_variant": "OPEN_DIMENSION_X", "instance_id": case["id"], "implementation_id": implementation_id,
        "algorithm": "box portfolio" if implementation_id.endswith("box") else "boxstacks portfolio", "adapter": "b11_open_dimension_fork_fixture_v1", "comparison_track": "NATIVE", "problem_scope": "FULL_PROBLEM",
        "budget": {"time_limit_s": time_limit, "memory_limit_bytes": 1073741824, "thread_limit": 1}, "item_order": "SOLVER_INTERNAL", "bin_order": "SOURCE", "seed": None, "repetition": 0,
        "input_sha256": case["input_sha256"], "input_status": "VALID", "capability_status": "SUPPORTED_NATIVE", "run_status": run_status,
        "solution_status": "VALID_COMPLETE" if valid and validation["complete"] else "INVALID_CERTIFICATE" if process_ok else "NO_SOLUTION", "proof_status": "FEASIBLE" if valid else "UNKNOWN", "termination_reason": "RETURNED_CERTIFICATE" if valid else "PROCESS_ERROR_OR_INVALID_CERTIFICATE",
        "resources": {"wall_s": wall_s, "solver_s": validation.get("solver_time_s")}, "metrics": {"used_length": validation.get("used_length"), "open_dimension_bound": validation.get("solver_bound"), "packed_items": validation["packed_items"], "required_items": validation["required_items"], "bins_used": validation.get("bins_used"), "validation_error_count": len(validation["errors"]), "source_scope": "REPOSITORY_FIXTURE_DERIVED_FROM_FORK_TESTS", "source_commit": source_commit, "binary_sha256": sha256(binary)},
        "artifacts": {"input": f"{archive_relative}#{case['id']}/{implementation_id}/effective-config.json", "effective_config": f"{archive_relative}#{case['id']}/{implementation_id}/effective-config.json", "solver_output": f"{archive_relative}#{case['id']}/{implementation_id}/output.json" if output_path.exists() else None, "solution": f"{archive_relative}#{case['id']}/{implementation_id}/solution.csv" if certificate_path.exists() else None, "validation": f"{archive_relative}#{case['id']}/{implementation_id}/validation.json", "stdout": f"{archive_relative}#{case['id']}/{implementation_id}/stdout.log", "stderr": f"{archive_relative}#{case['id']}/{implementation_id}/stderr.log"},
    }
    from comprehensive.model import validate_run_record
    validate_run_record(record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--time-limit", type=float, default=10.0)
    parser.add_argument("--results-root", type=Path, default=ROOT / "results" / "comprehensive")
    parser.add_argument("--raw-root", type=Path, default=ROOT / "raw" / "experiments" / "comprehensive")
    parser.add_argument("--implementation", action="append", choices=("packingsolver_fork_box", "packingsolver_fork_boxstacks", "packingsolver_upstream_box", "packingsolver_upstream_boxstacks"))
    args = parser.parse_args()
    selected = args.implementation or ["packingsolver_fork_box", "packingsolver_fork_boxstacks", "packingsolver_upstream_box", "packingsolver_upstream_boxstacks"]
    binaries = {"packingsolver_fork_box": ROOT / ".cache/build-fork/src/box/packingsolver_box", "packingsolver_fork_boxstacks": ROOT / ".cache/build-fork/src/boxstacks/packingsolver_boxstacks", "packingsolver_upstream_box": ROOT / ".cache/build-upstream-367/src/box/packingsolver_box", "packingsolver_upstream_boxstacks": ROOT / ".cache/build-upstream-367/src/boxstacks/packingsolver_boxstacks"}
    source_roots = {implementation: (FORK if "fork" in implementation else UPSTREAM) for implementation in selected}
    source_commits = {implementation: (FORK_COMMIT if "fork" in implementation else UPSTREAM_COMMIT) for implementation in selected}
    cases = load_cases()
    raw_dir = args.raw_root / "B11" / "packingsolver" / f"{args.time_limit:g}s"
    archive_path = raw_dir / "artifacts.tar.gz"
    archive_relative = str(archive_path.relative_to(ROOT))
    raw_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="b11-packingsolver-") as temporary:
        work_root = Path(temporary)
        for implementation in selected:
            if not binaries[implementation].is_file():
                raise FileNotFoundError(binaries[implementation])
            for case in cases:
                records.append(run_one(case, implementation, binaries[implementation], source_roots[implementation], source_commits[implementation], args.time_limit, work_root, archive_relative))
        with tarfile.open(archive_path, "w:gz") as archive:
            for path in sorted(work_root.rglob("*")):
                if path.is_file():
                    archive.add(path, arcname=path.relative_to(work_root))
    run_path = args.results_root / "runs" / "B11-packingsolver.jsonl"
    run_path.parent.mkdir(parents=True, exist_ok=True)
    run_path.write_text("".join(json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n" for record in sorted(records, key=lambda row: row["run_id"])), encoding="utf-8")
    metadata = {"schema_version": 1, "protocol_version": "benchmark-protocol/3", "benchmark_id": "B11", "record_count": len(records), "runner_sha256": sha256(RUNNER), "artifact_archive": archive_relative, "artifact_archive_sha256": sha256(archive_path), "run_jsonl_sha256": sha256(run_path), "source_scope": "REPOSITORY_FIXTURE_DERIVED_FROM_FORK_TESTS"}
    (raw_dir / "metadata.json").write_text(canonical(metadata), encoding="utf-8")
    print(run_path.relative_to(ROOT))
    return 0 if all(record["solution_status"] == "VALID_COMPLETE" for record in records if record["implementation_id"].endswith("_box")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
