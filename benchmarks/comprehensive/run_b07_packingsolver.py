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
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
import sys

sys.path.insert(0, str(ROOT / "benchmarks"))
from comprehensive.model import canonical_json, load_catalogs, validate_run_record  # noqa: E402
from validation import Box, validate_aabbs  # noqa: E402

SOURCE_COMMIT = "d953148b8f710c06fa6c410949b7272f9e36327b"
SOURCE_ROOT_DEFAULT = ROOT / ".cache" / "packingsolver-fork"
DATA_ROOT_DEFAULT = SOURCE_ROOT_DEFAULT / "data" / "box"
GROUPS = ("BR0", "BR8", "BR9", "BR10", "BR11", "BR12", "BR13", "BR14", "BR15")
RUNNER_PATH = Path(__file__).resolve()
SHARED_VALIDATOR_PATH = ROOT / "benchmarks" / "validation.py"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def payload_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def verify_checkout(source_root: Path, expected_commit: str, allow_dirty: bool = False) -> str:
    commit = subprocess.run(["git", "-C", str(source_root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(source_root), "status", "--porcelain"], check=True, capture_output=True, text=True).stdout.strip()
    if commit != expected_commit:
        raise ValueError(f"source commit mismatch: expected {expected_commit}, got {commit}")
    if dirty and not allow_dirty:
        raise ValueError(f"source checkout is dirty: {source_root}")
    return commit


def diff_sha256(source_root: Path) -> str | None:
    diff = subprocess.run(["git", "-C", str(source_root), "diff", "--binary"], check=True, capture_output=True).stdout
    return hashlib.sha256(diff).hexdigest() if diff else None


def discover(source_root: Path) -> list[dict[str, Any]]:
    data_root = source_root / "data" / "box" / "davies1999"
    raw_root = source_root / "data" / "box_raw" / "davies1999"
    rows: list[dict[str, Any]] = []
    for group in GROUPS:
        for item_path in sorted(data_root.glob(f"{group}.txt_*_items.csv"), key=lambda p: int(p.stem.rsplit("_", 2)[1])):
            suffix = item_path.name.removesuffix("_items.csv").split("_", 1)[1]
            instance_id = f"{group}.txt_{suffix}"
            bins_path = data_root / f"{instance_id}_bins.csv"
            raw_path = raw_root / f"{group}.txt"
            if not bins_path.exists() or not raw_path.exists():
                raise ValueError(f"missing source for {instance_id}")
            item_rows = read_csv(item_path)
            bin_rows = read_csv(bins_path)
            if len(bin_rows) != 1:
                raise ValueError(f"expected one bin row for {instance_id}")
            if not item_rows:
                raise ValueError(f"empty item input for {instance_id}")
            item_count = sum(int(row["COPIES"]) for row in item_rows)
            input_payload = {
                "benchmark_id": "B07",
                "instance_id": instance_id,
                "source_commit": SOURCE_COMMIT,
                "source_group": group,
                "items": item_rows,
                "bins": bin_rows,
                "raw_sha256": sha256(raw_path),
            }
            rows.append({
                "id": instance_id,
                "group": group,
                "items": item_path,
                "bins": bins_path,
                "raw": raw_path,
                "item_rows": item_rows,
                "bin_rows": bin_rows,
                "item_count": item_count,
                "bin_size": tuple(float(bin_rows[0][axis]) for axis in ("X", "Y", "Z")),
                "input_payload": input_payload,
                "input_sha256": payload_hash(input_payload),
            })
    if len(rows) != 900:
        raise ValueError(f"expected 900 B07 instances, found {len(rows)}")
    return rows


def parse_resources(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if not path.exists():
        return result
    for raw in path.read_text(errors="replace").splitlines():
        line = raw.strip()
        if line.startswith("Maximum resident set size"):
            result["peak_rss_bytes"] = int(line.rsplit(": ", 1)[-1]) * 1024
        elif line.startswith("User time"):
            result["cpu_user_s"] = float(line.rsplit(": ", 1)[-1])
        elif line.startswith("System time"):
            result["cpu_system_s"] = float(line.rsplit(": ", 1)[-1])
    return result


def rotation_dimensions(spec: dict[str, str], rotation: str) -> tuple[float, float, float] | None:
    if len(rotation) != 3 or set(rotation) != {"X", "Y", "Z"}:
        return None
    return tuple(float(spec[axis]) for axis in rotation)


def allowed_rotations(spec: dict[str, str]) -> set[str]:
    names = ("XYZ", "YXZ", "ZYX", "YZX", "XZY", "ZXY")
    return {name for name in names if spec.get(f"ROTATION_{name}") == "1"}


def validate_certificate(instance: dict[str, Any], output_path: Path, certificate_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    output = json.loads(output_path.read_text(encoding="utf-8"))
    final = output["Output"]
    solution = final["Solution"]
    item_specs = {row["ID"]: row for row in instance["item_rows"]}
    bin_specs = {row["ID"]: row for row in instance["bin_rows"]}
    rows = read_csv(certificate_path)
    bin_rows = [row for row in rows if row["TYPE"] == "BIN"]
    item_rows = [row for row in rows if row["TYPE"] == "ITEM"]
    if len(bin_rows) > 1:
        errors.append(f"certificate uses {len(bin_rows)} bin rows for one-container knapsack")

    physical_bins: dict[str, list[str]] = {}
    bin_sizes: dict[str, tuple[float, float, float]] = {}
    for row_index, row in enumerate(bin_rows):
        try:
            copies = int(row["COPIES"])
            dimensions = tuple(float(row[axis]) for axis in ("LX", "LY", "LZ"))
        except (KeyError, ValueError) as exc:
            errors.append(f"invalid bin row {row_index}: {exc}")
            continue
        spec = bin_specs.get(row.get("ID"))
        if spec is None:
            errors.append(f"unknown bin type {row.get('ID')}")
        elif dimensions != tuple(float(spec[axis]) for axis in ("X", "Y", "Z")):
            errors.append(f"bin {row.get('ID')} dimensions differ from input")
        pattern = row.get("BIN", str(row_index))
        ids = [f"pattern-{pattern}-row-{row_index}-copy-{copy}" for copy in range(copies)]
        physical_bins[pattern] = ids
        for ref in ids:
            bin_sizes[ref] = dimensions

    counts: Counter[str] = Counter()
    placements: list[Box] = []
    packed_volume = 0.0
    for row_index, row in enumerate(item_rows):
        spec = item_specs.get(row.get("ID"))
        if spec is None:
            errors.append(f"unknown item type {row.get('ID')}")
            continue
        rotation = row.get("ROTATION", "")
        permitted = allowed_rotations(spec)
        if rotation not in permitted:
            errors.append(f"item {row.get('ID')} rotation {rotation} is not allowed ({sorted(permitted)})")
        expected_dimensions = rotation_dimensions(spec, rotation)
        try:
            actual_dimensions = tuple(float(row[axis]) for axis in ("LX", "LY", "LZ"))
            copies = int(row["COPIES"])
            pattern_bins = physical_bins.get(row.get("BIN", ""), [])
        except (KeyError, ValueError) as exc:
            errors.append(f"invalid item row {row_index}: {exc}")
            continue
        if expected_dimensions is None or actual_dimensions != expected_dimensions:
            errors.append(f"item {row.get('ID')} dimensions do not match rotation {rotation}")
        if copies != len(pattern_bins):
            errors.append(f"item row {row_index} copies {copies} differ from physical pattern copies {len(pattern_bins)}")
            continue
        for copy, bin_ref in enumerate(pattern_bins):
            counts[row["ID"]] += 1
            packed_volume += actual_dimensions[0] * actual_dimensions[1] * actual_dimensions[2]
            placements.append(Box(
                ref=f"{row['ID']}:{row_index}:{copy}",
                bin_ref=bin_ref,
                x=float(row["X"]), y=float(row["Y"]), z=float(row["Z"]),
                dx=actual_dimensions[0], dy=actual_dimensions[1], dz=actual_dimensions[2],
            ))
    errors.extend(validate_aabbs(placements, bin_sizes))
    for item_id, count in counts.items():
        available = int(item_specs[item_id]["COPIES"])
        if count > available:
            errors.append(f"item type {item_id} placed {count}, available {available}")

    reported_items = int(solution["NumberOfItems"])
    reported_volume = float(solution["ItemVolume"])
    if len(placements) != reported_items:
        errors.append(f"certificate has {len(placements)} placements, solver reports {reported_items}")
    if packed_volume != reported_volume:
        errors.append(f"certificate volume {packed_volume} differs from solver {reported_volume}")
    if int(solution["NumberOfUnpackedItems"]) != instance["item_count"] - reported_items:
        errors.append("solver packed/unpacked counts do not sum to source item count")
    bound = float(final["KnapsackBound"]) if final.get("KnapsackBound") is not None else None
    gap = (bound - reported_volume) / bound if bound and bound > 0 else None
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "placements": len(placements),
        "packed_volume": reported_volume,
        "solver_bound": bound,
        "solver_relative_gap": gap,
        "solver_time_s": float(final["Time"]),
        "bins_used": int(solution["NumberOfBins"]),
        "unpacked_items": int(solution["NumberOfUnpackedItems"]),
    }


def artifact_ref(archive_relative: str, case_name: str, member: str) -> str:
    return f"{archive_relative}#{case_name}/{member}"


def run_one(instance: dict[str, Any], binary: Path, implementation: dict[str, Any], time_limit: float, label: str, work_root: Path, archive_relative: str, binary_sha: str, runner_sha: str, validator_sha: str, binary_source_commit: str, binary_source_diff_sha: str | None) -> dict[str, Any]:
    case_name = instance["id"]
    case_dir = work_root / case_name
    case_dir.mkdir()
    output_path = case_dir / "output.json"
    certificate_path = case_dir / "solution.csv"
    stdout_path = case_dir / "stdout.log"
    stderr_path = case_dir / "stderr.log"
    resource_path = case_dir / "resources.txt"
    validation_path = case_dir / "validation.json"
    input_path = case_dir / "input.json"
    config_path = case_dir / "effective-config.json"
    input_path.write_text(canonical_json(instance["input_payload"]), encoding="utf-8")
    command = [
        "/usr/bin/time", "-v", "-o", str(resource_path), str(binary),
        "--items", str(instance["items"]), "--bins", str(instance["bins"]),
        "--objective", "knapsack", "--time-limit", str(time_limit),
        "--memory-limit", "1024", "--verbosity-level", "0", "--only-write-at-the-end",
        "--output", str(output_path), "--certificate", str(certificate_path),
    ]
    config_path.write_text(canonical_json({
        "command": command, "benchmark_id": "B07", "instance_id": instance["id"],
        "implementation_id": implementation["id"], "implementation_version": implementation["version"],
        "binary_sha256": binary_sha, "runner_sha256": runner_sha, "shared_validator_sha256": validator_sha,
        "time_limit_s": time_limit, "memory_limit_bytes": 1073741824, "thread_limit": 1,
        "pose_semantics": "SOURCE_ROTATION_FLAGS", "input_source_commit": SOURCE_COMMIT,
        "binary_source_commit": binary_source_commit,
        "binary_source_diff_sha256": binary_source_diff_sha,
    }), encoding="utf-8")
    env = os.environ.copy()
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[name] = "1"
    started = perf_counter()
    try:
        completed = subprocess.run(command, capture_output=True, text=True, env=env, timeout=max(30.0, time_limit + 20.0), check=False)
        wall_s = perf_counter() - started
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        process_ok = completed.returncode == 0 and output_path.exists() and certificate_path.exists()
    except subprocess.TimeoutExpired as exc:
        wall_s = perf_counter() - started
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text(exc.stderr or "", encoding="utf-8")
        process_ok = False
    if process_ok:
        validation = validate_certificate(instance, output_path, certificate_path)
    else:
        validation = {"status": "FAIL", "errors": ["solver process failed, timed out, or omitted output/certificate"], "placements": 0, "packed_volume": None, "solver_bound": None, "solver_relative_gap": None, "solver_time_s": None, "bins_used": None, "unpacked_items": instance["item_count"]}
    validation_path.write_text(canonical_json(validation), encoding="utf-8")
    resources = parse_resources(resource_path)
    solver_s = validation["solver_time_s"]
    reached_limit = solver_s is not None and solver_s >= time_limit * 0.95
    valid = validation["status"] == "PASS"
    proof_closed = valid and validation["solver_relative_gap"] is not None and abs(validation["solver_relative_gap"]) <= 1e-12
    if not process_ok:
        run_status, termination = "ERROR", "PROCESS_ERROR_OR_EXTERNAL_TIMEOUT"
    elif reached_limit and not proof_closed:
        run_status, termination = "TIME_LIMIT", "TIME_LIMIT_WITH_INCUMBENT"
    else:
        run_status, termination = "COMPLETED", "BOUND_CLOSED" if proof_closed else "SOLVER_STOPPED"
    record = {
        "schema_version": 2, "protocol_version": "benchmark-protocol/3", "record_origin": "PROTOCOL_V3",
        "run_id": f"B07/SOURCE_ROTATION_FLAGS/{instance['id']}/{implementation['id']}/{label}/SOLVER_INTERNAL/rep-0",
        "benchmark_id": "B07", "problem_variant": "SOURCE_ROTATION_FLAGS", "instance_id": instance["id"],
        "implementation_id": implementation["id"], "algorithm": implementation["algorithm"], "adapter": None,
        "comparison_track": "NATIVE", "problem_scope": "FULL_PROBLEM",
        "budget": {"time_limit_s": time_limit, "memory_limit_bytes": 1073741824, "thread_limit": 1},
        "item_order": "SOLVER_INTERNAL", "bin_order": "SOURCE", "seed": None, "repetition": 0,
        "input_sha256": instance["input_sha256"], "input_status": "VALID", "capability_status": "SUPPORTED_NATIVE",
        "run_status": run_status,
        "solution_status": "VALID_PARTIAL" if valid else "INVALID_CERTIFICATE" if process_ok else "NO_SOLUTION",
        "proof_status": "PROVEN_OPTIMAL" if proof_closed else "FEASIBLE" if valid else "UNKNOWN",
        "termination_reason": termination,
        "resources": {"wall_s": wall_s, "solver_s": solver_s, **resources},
        "metrics": {
            "packed_volume": validation["packed_volume"], "container_volume": instance["bin_size"][0] * instance["bin_size"][1] * instance["bin_size"][2],
            "volume_utilization": validation["packed_volume"] / (instance["bin_size"][0] * instance["bin_size"][1] * instance["bin_size"][2]) if validation["packed_volume"] is not None else None,
            "packed_items": validation["placements"], "unpacked_items": validation["unpacked_items"], "solver_bound": validation["solver_bound"],
            "solver_relative_gap": validation["solver_relative_gap"], "bins_used": validation["bins_used"], "validation_error_count": len(validation["errors"]),
            "source_group": instance["group"], "binary_source_commit": binary_source_commit,
            "binary_source_diff_sha256": binary_source_diff_sha,
        },
        "artifacts": {
            "input": artifact_ref(archive_relative, case_name, "input.json"), "effective_config": artifact_ref(archive_relative, case_name, "effective-config.json"),
            "solver_output": artifact_ref(archive_relative, case_name, "output.json") if output_path.exists() else None,
            "solution": artifact_ref(archive_relative, case_name, "solution.csv") if certificate_path.exists() else None,
            "validation": artifact_ref(archive_relative, case_name, "validation.json"), "stdout": artifact_ref(archive_relative, case_name, "stdout.log"),
            "stderr": artifact_ref(archive_relative, case_name, "stderr.log"), "resources": artifact_ref(archive_relative, case_name, "resources.txt") if resource_path.exists() else None,
        },
    }
    validate_run_record(record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="Run B07 Davies-Bischoff single-container knapsack with PackingSolver")
    parser.add_argument("--binary", type=Path, default=ROOT / ".cache" / "build-fork" / "src" / "box" / "packingsolver_box")
    parser.add_argument("--source-root", type=Path, default=SOURCE_ROOT_DEFAULT)
    parser.add_argument("--binary-source-root", type=Path)
    parser.add_argument("--implementation-id", choices=("packingsolver_fork_box", "packingsolver_upstream_box"), default="packingsolver_fork_box")
    parser.add_argument("--time-limit", type=float, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--results-root", type=Path, default=ROOT / "results" / "comprehensive")
    parser.add_argument("--raw-root", type=Path, default=ROOT / "raw" / "experiments" / "comprehensive")
    args = parser.parse_args()
    source_root = args.source_root.resolve()
    binary = args.binary.resolve()
    verify_checkout(source_root, SOURCE_COMMIT)
    if not binary.is_file():
        raise ValueError(f"missing binary: {binary}")
    _, catalog = load_catalogs()
    implementations = {row["id"]: row for row in catalog["implementations"]}
    implementation = implementations[args.implementation_id]
    binary_source_root = (args.binary_source_root or source_root).resolve()
    binary_source_commit = verify_checkout(binary_source_root, implementation["version"], allow_dirty=args.implementation_id == "packingsolver_upstream_box")
    binary_source_diff_sha = diff_sha256(binary_source_root)
    instances = discover(source_root)
    if args.limit is not None:
        instances = instances[: args.limit]
    raw_dir = args.raw_root / "B07" / args.implementation_id / args.label
    archive_path = raw_dir / "artifacts.tar.gz"
    archive_relative = str(archive_path.resolve().relative_to(ROOT))
    runs_dir = args.results_root / "runs"
    raw_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)
    binary_sha = sha256(binary)
    runner_sha = sha256(RUNNER_PATH)
    validator_sha = sha256(SHARED_VALIDATOR_PATH)
    records: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory(prefix=f"b07-{args.implementation_id}-{args.label}-") as temporary:
        work_root = Path(temporary)
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = {executor.submit(run_one, instance, binary, implementation, args.time_limit, args.label, work_root, archive_relative, binary_sha, runner_sha, validator_sha, binary_source_commit, binary_source_diff_sha): instance for instance in instances}
            for count, future in enumerate(as_completed(futures), 1):
                instance = futures[future]
                records[instance["id"]] = future.result()
                if count % 25 == 0 or count == len(instances):
                    print(f"B07 {args.implementation_id} {args.label}: {count}/{len(instances)}", flush=True)
        with tarfile.open(archive_path, "w:gz") as archive:
            for path in sorted(work_root.rglob("*")):
                if path.is_file():
                    archive.add(path, arcname=path.relative_to(work_root))
    ordered = [records[instance["id"]] for instance in instances]
    run_path = runs_dir / f"B07-{args.implementation_id}-{args.label}.jsonl"
    run_path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n" for row in ordered), encoding="utf-8")
    summary = {
        "schema_version": 1, "protocol_version": "benchmark-protocol/3", "benchmark_id": "B07", "implementation_id": args.implementation_id,
        "implementation_version": implementation["version"], "binary_sha256": binary_sha, "runner_sha256": runner_sha, "shared_validator_sha256": validator_sha,
        "time_limit_s": args.time_limit, "label": args.label, "instances": len(ordered), "input_source_commit": SOURCE_COMMIT,
        "binary_source_commit": binary_source_commit,
        "binary_source_diff_sha256": binary_source_diff_sha,
        "solution_status_counts": dict(sorted(Counter(row["solution_status"] for row in ordered).items())), "artifact_archive": archive_relative,
        "artifact_archive_sha256": sha256(archive_path), "run_jsonl_sha256": sha256(run_path), "source_commit": SOURCE_COMMIT,
    }
    (raw_dir / "metadata.json").write_text(canonical_json(summary), encoding="utf-8")
    (args.results_root / f"B07-{args.implementation_id}-{args.label}-summary.json").write_text(canonical_json(summary), encoding="utf-8")
    print(run_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
