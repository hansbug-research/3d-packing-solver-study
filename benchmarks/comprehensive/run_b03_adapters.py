from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
import sys
import tarfile
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import permutations
from pathlib import Path
from time import perf_counter
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from comprehensive.model import canonical_json, load_catalogs, validate_run_record
from run_b03_packingsolver import (
    INDEX_PATH,
    input_paths,
    parse_resources,
    payload_hash,
    repository_path,
    sha256,
    validate_source,
)
from validation import Box, validate_aabbs


RUNNER_PATH = Path(__file__).resolve()
PYTHON_WORKER_PATH = RUNNER_PATH.with_name("b03_python_worker.py")
SHARED_VALIDATOR_PATH = ROOT / "benchmarks" / "validation.py"
RUST_STRATEGIES = {
    "rust_extreme_point": "extremepoint",
    "rust_layer": "bottomleftfill",
    "rust_ga": "ga",
    "rust_brkga": "brkga",
    "rust_sa": "sa",
}
PROJECTION_IMPLEMENTATIONS = {"py3dbp", "jerry", "go_bp3d"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def source_payload(index_row: dict[str, Any], source_root: Path, relaxed: bool) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    items_path, bins_path = validate_source(index_row, source_root)
    item_specs: dict[str, dict[str, Any]] = {}
    items = []
    for row in read_csv(items_path):
        copies = int(row["COPIES"])
        for copy in range(copies):
            item_id = row["ID"] if copies == 1 else f"{row['ID']}:{copy}"
            spec = {
                "id": item_id,
                "size": [int(row[axis]) for axis in ("X", "Y", "Z")],
                "weight": 1,
                "profit": int(row["PROFIT"]),
                "orientation_requirement": "any" if relaxed else "fixed",
            }
            item_specs[item_id] = spec
            items.append(spec)
    bin_row = read_csv(bins_path)[0]
    payload = {
        "scenario": index_row["id"],
        "bins": [
            {
                "id": "bin-0",
                "size": [int(bin_row[axis]) for axis in ("X", "Y", "Z")],
                "max_weight": len(items) + 1,
                "cost": 1,
            }
        ],
        "items": items,
    }
    return payload, item_specs


def validate_output(payload: dict[str, Any], specs: dict[str, dict[str, Any]], output: dict[str, Any], relaxed: bool) -> dict[str, Any]:
    errors: list[str] = []
    seen: set[str] = set()
    boxes: list[Box] = []
    packed_profit = 0
    packed_volume = 0
    for index, placement in enumerate(output.get("placements", [])):
        item_id = str(placement.get("item_id"))
        spec = specs.get(item_id)
        if spec is None:
            errors.append(f"placement {index} uses unknown item {item_id}")
            continue
        if item_id in seen:
            errors.append(f"item {item_id} is placed more than once")
            continue
        seen.add(item_id)
        actual = tuple(float(value) for value in placement["size"])
        expected = tuple(float(value) for value in spec["size"])
        allowed = set(permutations(expected)) if relaxed else {expected}
        if actual not in allowed:
            errors.append(f"item {item_id} has forbidden orientation {actual}; expected {sorted(allowed)}")
        position = [float(value) for value in placement["position"]]
        boxes.append(Box(item_id, str(placement["bin_id"]), *position, *actual, 1))
        packed_profit += int(spec["profit"])
        packed_volume += math.prod(int(value) for value in spec["size"])
    bin_spec = payload["bins"][0]
    errors.extend(validate_aabbs(boxes, {bin_spec["id"]: tuple(bin_spec["size"])}))
    reported_unplaced = output.get("unplaced")
    if reported_unplaced is not None:
        unplaced = [str(value) for value in reported_unplaced]
        if len(unplaced) != len(set(unplaced)):
            errors.append("worker reports duplicate unplaced item ids")
        if set(unplaced) != set(specs) - seen:
            errors.append("worker unplaced ids do not complement placed ids")
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "placements": len(boxes),
        "packed_profit": packed_profit,
        "packed_volume": packed_volume,
        "unpacked_items": len(specs) - len(seen),
    }


def command_for(implementation_id: str, input_path: Path, binary: Path | None, time_limit: float) -> list[str]:
    if implementation_id in {"py3dbp", "jerry"}:
        return [
            str(ROOT / ".venv" / "bin" / "python"),
            str(PYTHON_WORKER_PATH),
            "--implementation",
            implementation_id,
            "--input",
            str(input_path),
        ]
    if binary is None:
        raise ValueError(f"--binary is required for {implementation_id}")
    if implementation_id == "go_bp3d":
        return [str(binary), "--input", str(input_path)]
    return [str(binary), "--input", str(input_path), RUST_STRATEGIES[implementation_id], str(round(time_limit * 1000))]


def artifact_reference(archive: str, case_name: str, member: str) -> str:
    return f"{archive}#{case_name}/{member}"


def run_one(
    index_row: dict[str, Any],
    source_root: Path,
    implementation: dict[str, Any],
    binary: Path | None,
    binary_sha256: str | None,
    time_limit: float,
    label: str,
    work_root: Path,
    archive_reference_path: str,
    harness_hashes: dict[str, str],
) -> dict[str, Any]:
    implementation_id = implementation["id"]
    relaxed = implementation_id in PROJECTION_IMPLEMENTATIONS
    problem_variant = "RELAXED_ALL_ROTATIONS" if relaxed else "FIXED_XYZ"
    case_name = index_row["id"].removesuffix(".3kp")
    case_dir = work_root / case_name
    case_dir.mkdir()
    payload, specs = source_payload(index_row, source_root, relaxed)
    input_path = case_dir / "input.json"
    output_path = case_dir / "output.json"
    stdout_path = case_dir / "stdout.log"
    stderr_path = case_dir / "stderr.log"
    resources_path = case_dir / "resources.txt"
    validation_path = case_dir / "validation.json"
    config_path = case_dir / "effective-config.json"
    input_path.write_text(canonical_json(payload), encoding="utf-8")

    solver_command = command_for(implementation_id, input_path, binary, time_limit)
    command = [
        "/usr/bin/time",
        "-v",
        "-o",
        str(resources_path),
        "/usr/bin/timeout",
        "--signal=TERM",
        "--kill-after=1s",
        str(time_limit),
        *solver_command,
    ]
    config = {
        "command": command,
        "implementation_id": implementation_id,
        "implementation_version": implementation["version"],
        "binary_sha256": binary_sha256,
        "time_limit_s": time_limit,
        "memory_limit_bytes": 1073741824,
        "thread_limit": 1,
        "pose_semantics": problem_variant,
        **harness_hashes,
    }
    config_path.write_text(canonical_json(config), encoding="utf-8")
    environment = os.environ.copy()
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "RAYON_NUM_THREADS", "GOMAXPROCS"):
        environment[name] = "1"
    started = perf_counter()
    try:
        completed = subprocess.run(command, text=True, capture_output=True, timeout=time_limit + 5, env=environment)
        wall_s = perf_counter() - started
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
    except subprocess.TimeoutExpired as exc:
        wall_s = perf_counter() - started
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text(exc.stderr or "", encoding="utf-8")
        completed = None

    output: dict[str, Any] | None = None
    candidate_invalid_count = 0
    candidate_count = 1
    if completed is not None and completed.returncode == 0:
        try:
            output = json.loads(completed.stdout)
            if implementation_id in {"go_bp3d", *RUST_STRATEGIES} and output.get("commit") != implementation["version"]:
                raise ValueError(f"worker commit {output.get('commit')} differs from catalog {implementation['version']}")
            if implementation_id in {"py3dbp", "jerry"}:
                candidates = output.pop("candidates")
                candidate_count = len(candidates)
                validated_candidates = []
                for candidate in candidates:
                    candidate_validation = validate_output(
                        payload,
                        specs,
                        {"placements": candidate["placements"]},
                        relaxed,
                    )
                    validated_candidates.append((candidate, candidate_validation))
                candidate_invalid_count = sum(validation["status"] != "PASS" for _, validation in validated_candidates)
                valid_candidates = [
                    (candidate, validation)
                    for candidate, validation in validated_candidates
                    if validation["status"] == "PASS"
                ]
                selectable = valid_candidates or validated_candidates
                selected, _ = max(
                    selectable,
                    key=lambda row: (row[1]["packed_profit"], row[1]["placements"], row[0]["order"]),
                )
                output["selected_order"] = selected["order"]
                output["placements"] = selected["placements"]
                output["candidate_summaries"] = [
                    {
                        "order": candidate["order"],
                        "elapsed_s": candidate["elapsed_s"],
                        "packed_profit": validation["packed_profit"],
                        "validation_status": validation["status"],
                        "validation_errors": validation["errors"],
                    }
                    for candidate, validation in validated_candidates
                ]
            output_path.write_text(canonical_json(output), encoding="utf-8")
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            stderr_path.write_text(stderr_path.read_text(encoding="utf-8") + f"\noutput validation: {exc}\n", encoding="utf-8")
            output = None
    validation = (
        validate_output(payload, specs, output, relaxed)
        if output is not None
        else {
            "status": "FAIL",
            "errors": ["worker timed out, failed, or returned invalid JSON/version metadata"],
            "placements": 0,
            "packed_profit": None,
            "packed_volume": None,
            "unpacked_items": len(specs),
        }
    )
    validation_path.write_text(canonical_json(validation), encoding="utf-8")
    valid = validation["status"] == "PASS"
    timed_out = completed is not None and completed.returncode == 124
    process_resources = parse_resources(resources_path)
    library_s = None
    if output is not None:
        library_s = output.get("elapsed_s")
        if library_s is None and output.get("elapsed_ms") is not None:
            library_s = float(output["elapsed_ms"]) / 1000
    total_profit = index_row["total_profit"]
    packed_profit = validation["packed_profit"]
    record = {
        "schema_version": 2,
        "protocol_version": "benchmark-protocol/3",
        "record_origin": "PROTOCOL_V3",
        "run_id": f"B03/{problem_variant}/{index_row['id']}/{implementation_id}/{label}/SOURCE/rep-0",
        "benchmark_id": "B03",
        "problem_variant": problem_variant,
        "instance_id": index_row["id"],
        "implementation_id": implementation_id,
        "algorithm": implementation["algorithm"],
        "adapter": "b03_python_best_of_orders" if implementation_id in {"py3dbp", "jerry"} else "b03_single_boundary",
        "comparison_track": "COMPOSED",
        "problem_scope": "GEOMETRY_PROJECTION" if relaxed else "FULL_PROBLEM",
        "budget": {"time_limit_s": time_limit, "memory_limit_bytes": 1073741824, "thread_limit": 1},
        "item_order": output.get("selected_order", "SOURCE") if output else "SOURCE",
        "bin_order": "SOURCE",
        "seed": None,
        "repetition": 0,
        "input_sha256": payload_hash(index_row["sha256"]),
        "input_status": "VALID",
        "capability_status": "PROJECTION_ONLY" if relaxed else "SUPPORTED_COMPOSED",
        "run_status": "TIME_LIMIT" if timed_out else "COMPLETED" if output is not None else "ERROR",
        "solution_status": (
            "VALID_COMPLETE"
            if valid and validation["unpacked_items"] == 0
            else "VALID_PARTIAL"
            if valid
            else "NO_SOLUTION"
            if output is None
            else "INVALID_CERTIFICATE"
        ),
        "proof_status": "FEASIBLE" if valid else "UNKNOWN",
        "termination_reason": "EXTERNAL_TIME_LIMIT" if timed_out else "RETURNED_CERTIFICATE" if output is not None else "PROCESS_OR_OUTPUT_ERROR",
        "resources": {
            "wall_s": wall_s,
            "solver_s": library_s,
            "peak_rss_bytes": process_resources.get("peak_rss_bytes"),
            "cpu_user_s": process_resources.get("cpu_user_s"),
            "cpu_system_s": process_resources.get("cpu_system_s"),
        },
        "metrics": {
            "packed_profit": packed_profit,
            "total_available_profit": total_profit,
            "packed_profit_fraction": packed_profit / total_profit if packed_profit is not None else None,
            "packed_volume": validation["packed_volume"],
            "packed_items": validation["placements"],
            "unpacked_items": validation["unpacked_items"],
            "profit_objective_native": False,
            "internal_time_limit_effective": bool(
                output
                and output.get("parameters", {}).get("time_limit_effective", False)
            ),
            "candidate_count": candidate_count,
            "candidate_invalid_count": candidate_invalid_count,
            "validation_error_count": len(validation["errors"]),
        },
        "artifacts": {
            "input": artifact_reference(archive_reference_path, case_name, "input.json"),
            "effective_config": artifact_reference(archive_reference_path, case_name, "effective-config.json"),
            "solver_output": artifact_reference(archive_reference_path, case_name, "output.json") if output_path.exists() else None,
            "validation": artifact_reference(archive_reference_path, case_name, "validation.json"),
            "stdout": artifact_reference(archive_reference_path, case_name, "stdout.log"),
            "stderr": artifact_reference(archive_reference_path, case_name, "stderr.log"),
            "resources": artifact_reference(archive_reference_path, case_name, "resources.txt") if resources_path.exists() else None,
        },
    }
    validate_run_record(record)
    return record


def main() -> int:
    choices = sorted(PROJECTION_IMPLEMENTATIONS | set(RUST_STRATEGIES))
    parser = argparse.ArgumentParser(description="Run B03 through Python, Go, or Rust adapters")
    parser.add_argument("--implementation-id", choices=choices, required=True)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--source-root", type=Path, default=ROOT / ".cache" / "packingsolver-fork")
    parser.add_argument("--time-limit", type=float, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--results-root", type=Path, default=ROOT / "results" / "comprehensive")
    parser.add_argument("--raw-root", type=Path, default=ROOT / "raw" / "experiments" / "comprehensive")
    args = parser.parse_args()

    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    _, implementation_catalog = load_catalogs()
    implementation = next(row for row in implementation_catalog["implementations"] if row["id"] == args.implementation_id)
    binary = args.binary.resolve() if args.binary else None
    if args.implementation_id not in {"py3dbp", "jerry"} and (binary is None or not binary.is_file()):
        raise ValueError(f"external adapter binary is missing: {binary}")
    binary_hash = sha256(binary) if binary else None
    instances = index["instances"][: args.limit] if args.limit is not None else index["instances"]
    raw_dir = args.raw_root / "B03" / args.implementation_id / args.label
    archive_path = raw_dir / "artifacts.tar.gz"
    archive_reference_path = repository_path(archive_path)
    runs_dir = args.results_root / "runs"
    raw_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)
    harness_hashes = {
        "runner_sha256": sha256(RUNNER_PATH),
        "python_worker_sha256": sha256(PYTHON_WORKER_PATH),
        "shared_validator_sha256": sha256(SHARED_VALIDATOR_PATH),
    }
    records: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory(prefix=f"b03-{args.implementation_id}-{args.label}-") as temporary:
        work_root = Path(temporary)
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = {
                executor.submit(
                    run_one,
                    row,
                    args.source_root.resolve(),
                    implementation,
                    binary,
                    binary_hash,
                    args.time_limit,
                    args.label,
                    work_root,
                    archive_reference_path,
                    harness_hashes,
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
    summary = {
        "schema_version": 1,
        "protocol_version": "benchmark-protocol/3",
        "benchmark_id": "B03",
        "problem_variant": ordered[0]["problem_variant"] if ordered else None,
        "comparison_track": "COMPOSED",
        "implementation_id": args.implementation_id,
        "implementation_version": implementation["version"],
        "binary_sha256": binary_hash,
        "time_limit_s": args.time_limit,
        "label": args.label,
        "instances": len(ordered),
        "solution_status_counts": dict(sorted(Counter(row["solution_status"] for row in ordered).items())),
        "run_status_counts": dict(sorted(Counter(row["run_status"] for row in ordered).items())),
        "artifact_archive": archive_reference_path,
        "artifact_archive_sha256": sha256(archive_path),
        "run_jsonl_sha256": sha256(run_path),
        "source_index_sha256": sha256(INDEX_PATH),
        **harness_hashes,
    }
    (raw_dir / "metadata.json").write_text(canonical_json(summary), encoding="utf-8")
    summary_path = args.results_root / f"B03-{args.implementation_id}-{args.label}-summary.json"
    summary_path.write_text(canonical_json(summary), encoding="utf-8")
    print(repository_path(run_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
