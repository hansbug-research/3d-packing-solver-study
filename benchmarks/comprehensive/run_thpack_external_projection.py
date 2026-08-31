#!/usr/bin/env python3
"""Run Go bp3d and u-nesting on the explicit all-rotations THPACK projection.

This runner deliberately removes the source vertical flags and records the
result as ``GEOMETRY_PROJECTION``.  It is useful for comparing geometry
engines, but its output must never be merged with the source-semantic native
track.  Raw case artifacts are stored in one content-addressed tarball so a
large all-instance campaign remains auditable without creating another layer
of tracked files.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
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
MODEL_DIR = ROOT / "benchmarks" / "campaign" / "python_thpack"
sys.path.insert(0, str(MODEL_DIR))
from model import ESICUP_COMMIT, expanded_items, parse_all, validate_certificate  # noqa: E402

sys.path.insert(0, str(ROOT / "benchmarks"))
from comprehensive.model import canonical_json, validate_run_record  # noqa: E402

JOBS_ROOT = ROOT / "raw" / "experiments" / "comprehensive" / "B01-B02-external-projection"
RESULTS_ROOT = ROOT / "results" / "comprehensive" / "runs"
GO_COMMIT = "0ba3dcda7ab334c19b0979b1cf1fa05e09f33bc7"
RUST_COMMIT = "8cde85b029e4ade663185dacb93fd74440af170d"
DEFAULT_GO = Path("/tmp/packing-crosslang-go-build/crosslang_go_bp3d")
DEFAULT_RUST = Path("/tmp/packing-crosslang-u-build/target/release/crosslang-rust-unesting")


def implementation_id(library: str, strategy: str) -> str:
    if library == "go_bp3d":
        return "go_bp3d"
    if strategy == "bottomleftfill":
        return "rust_layer"
    if strategy == "extremepoint":
        return "rust_extreme_point"
    return f"rust_{strategy}"


def payload_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resource_value(path: Path, label: str) -> int | None:
    if not path.exists():
        return None
    prefix = f"\t{label}: "
    for line in path.read_text(errors="replace").splitlines():
        if line.startswith(prefix):
            try:
                return int(line.removeprefix(prefix)) * 1024 if "kbytes" in label else int(line.removeprefix(prefix))
            except ValueError:
                return None
    return None


def make_input(instance: Any, order: str) -> dict[str, Any]:
    items = expanded_items(instance)
    if order == "ascending":
        items = sorted(items, key=lambda item: (item["size"][0] * item["size"][1] * item["size"][2], item["item_id"]))
    else:
        items = sorted(items, key=lambda item: (-item["size"][0] * item["size"][1] * item["size"][2], item["item_id"]))
    return {
        "scenario": instance.key,
        "bins": [{
            "id": "bin-000",
            "size": list(instance.container),
            "max_weight": float(instance.item_count + 1),
            "cost": 1.0,
        }],
        "items": [{
            "id": item["item_id"],
            "size": list(item["size"]),
            "weight": 1.0,
            "orientation_requirement": "any",
        } for item in items],
    }


def normalize_placements(payload: dict[str, Any]) -> list[dict[str, Any]]:
    placements = []
    for placement in payload.get("placements", []):
        position = placement.get("position", [placement.get("x", 0), placement.get("y", 0), placement.get("z", 0)])
        size = placement.get("size", [placement.get("dx", 0), placement.get("dy", 0), placement.get("dz", 0)])
        placements.append({
            "item_id": placement["item_id"],
            "bin_id": placement.get("bin_id", "bin-000"),
            "x": position[0], "y": position[1], "z": position[2],
            "dx": size[0], "dy": size[1], "dz": size[2],
            "rotation": placement.get("rotation", "any"),
        })
    return placements


def run_one(
    instance: Any,
    library: str,
    strategy: str,
    order: str,
    time_limit_s: float,
    repetition: int,
    go_binary: Path,
    rust_binary: Path,
    work_root: Path,
    archive_name: str,
    runner_sha: str,
) -> dict[str, Any]:
    benchmark_id = "B01" if int(instance.family.removeprefix("THPACK")) <= 7 else "B02"
    algorithm = "pivot greedy" if library == "go_bp3d" else strategy
    case_name = f"{benchmark_id}/{instance.key}/{library}/{strategy}/{order}/{time_limit_s:g}s/rep-{repetition}"
    case_dir = work_root / case_name.replace("/", "__")
    case_dir.mkdir(parents=True, exist_ok=True)
    input_payload = make_input(instance, order)
    input_hash = payload_hash(input_payload)
    input_path = case_dir / "input.json"
    input_path.write_text(canonical_json(input_payload), encoding="utf-8")
    binary = go_binary if library == "go_bp3d" else rust_binary
    command = [str(binary), "--input", str(input_path)]
    if library == "rust_unesting":
        command.extend([strategy, str(round(time_limit_s * 1000))])
    config = {
        "command": command,
        "benchmark_id": benchmark_id,
        "problem_variant": "RELAXED_ALL_ROTATIONS",
        "instance_id": instance.key,
        "implementation_id": implementation_id(library, strategy),
        "implementation_version": GO_COMMIT if library == "go_bp3d" else RUST_COMMIT,
        "source_commit": ESICUP_COMMIT,
        "input_sha256": input_hash,
        "item_order": order.upper(),
        "time_limit_s": time_limit_s,
        "memory_limit_bytes": 2147483648,
        "thread_limit": 1,
        "runner_sha256": runner_sha,
    }
    (case_dir / "effective-config.json").write_text(canonical_json(config), encoding="utf-8")
    resources = case_dir / "resources.txt"
    env = os.environ.copy()
    env.update({
        "GOMAXPROCS": "1", "RAYON_NUM_THREADS": "1", "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1",
        "PYTHONHASHSEED": "0",
    })
    started = perf_counter()
    timed_out = False
    return_code: int | None = None
    try:
        completed = subprocess.run(
            ["/usr/bin/time", "-v", "-o", str(resources), "timeout", "--signal=TERM", "--kill-after=1s", str(time_limit_s + 1), *command],
            capture_output=True, text=True, env=env, timeout=time_limit_s + 4,
        )
        return_code = completed.returncode
        timed_out = return_code in {124, 137, -15, -9}
        stdout, stderr = completed.stdout, completed.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
    wall_s = perf_counter() - started
    (case_dir / "stdout.json").write_text(stdout, encoding="utf-8")
    (case_dir / "stderr.log").write_text(stderr, encoding="utf-8")
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        payload = {"validation_errors": [f"invalid worker JSON: {exc}"], "placements": []}
    placements = normalize_placements(payload)
    relaxed_instance = replace(
        instance,
        item_types=[replace(item, allowed_vertical_dimensions=(1, 1, 1)) for item in instance.item_types],
    )
    validation_errors = validate_certificate(
        relaxed_instance,
        placements,
        require_complete=False,
    )
    expected = {item["item_id"] for item in expanded_items(instance)}
    placed = {placement["item_id"] for placement in placements}
    unknown = sorted(placed - expected)
    if unknown:
        validation_errors.append(f"unknown item ids: {unknown}")
    packed_volume = sum(float(p["dx"]) * float(p["dy"]) * float(p["dz"]) for p in placements if p["item_id"] in expected)
    if timed_out:
        run_status = "TIME_LIMIT"
        termination = "TIME_LIMIT"
    elif return_code == 0:
        run_status = "COMPLETED"
        termination = "RETURNED_CERTIFICATE"
    else:
        run_status = "ERROR"
        termination = "PROCESS_ERROR"
    if validation_errors:
        solution_status = "INVALID_CERTIFICATE"
    elif placements and len(placed) == len(expected):
        solution_status = "VALID_COMPLETE"
    elif placements:
        solution_status = "VALID_PARTIAL"
    else:
        solution_status = "NO_SOLUTION"
    validation = {
        "status": "PASS" if solution_status in {"VALID_COMPLETE", "VALID_PARTIAL"} else "FAIL",
        "errors": validation_errors,
        "packed_items": len(placed),
        "required_items": len(expected),
        "packed_volume": packed_volume,
    }
    (case_dir / "validation.json").write_text(canonical_json(validation), encoding="utf-8")
    impl_id = implementation_id(library, strategy)
    record = {
        "schema_version": 2,
        "protocol_version": "benchmark-protocol/3",
        "record_origin": "PROTOCOL_V3",
        "run_id": f"{benchmark_id}/{instance.key}/{impl_id}/projection/{order}/{time_limit_s:g}s/rep-{repetition}",
        "benchmark_id": benchmark_id,
        "problem_variant": "RELAXED_ALL_ROTATIONS",
        "instance_id": (
            f"BR:BR{int(instance.family.removeprefix('THPACK'))}.txt:{instance.instance_id}"
            if benchmark_id == "B01"
            else f"LN:thpack8.txt:{instance.instance_id}"
        ),
        "implementation_id": impl_id,
        "algorithm": algorithm,
        "adapter": "thpack_external_projection_v1",
        "comparison_track": "COMPOSED",
        "problem_scope": "GEOMETRY_PROJECTION",
        "budget": {"time_limit_s": time_limit_s, "memory_limit_bytes": 2147483648, "thread_limit": 1},
        "item_order": order.upper(),
        "bin_order": "SOURCE",
        "seed": 42 if library == "rust_unesting" else None,
        "repetition": repetition,
        "input_sha256": input_hash,
        "input_status": "VALID",
        "capability_status": "PROJECTION_ONLY",
        "run_status": run_status,
        "solution_status": solution_status,
        "proof_status": "FEASIBLE" if solution_status in {"VALID_COMPLETE", "VALID_PARTIAL"} else "UNKNOWN",
        "termination_reason": termination,
        "resources": {
            "wall_s": wall_s,
            "solver_s": payload.get("elapsed_ms", 0.0) / 1000.0 if payload.get("elapsed_ms") is not None else None,
            "peak_rss_bytes": resource_value(resources, "Maximum resident set size (kbytes)"),
        },
        "metrics": {
            "packed_items": len(placed),
            "unpacked_items": len(expected - placed),
            "packed_volume": packed_volume,
            "volume_utilization": packed_volume / instance.container_volume,
            "bins_used": len({p["bin_id"] for p in placements}),
            "validation_error_count": len(validation_errors),
            "projection_removed_constraints": ["source_vertical_flags"],
            "process_returncode": return_code,
        },
        "artifacts": {
            "input": f"{archive_name}#{case_dir.name}/input.json",
            "effective_config": f"{archive_name}#{case_dir.name}/effective-config.json",
            "solver_output": f"{archive_name}#{case_dir.name}/stdout.json",
            "stderr": f"{archive_name}#{case_dir.name}/stderr.log",
            "validation": f"{archive_name}#{case_dir.name}/validation.json",
        },
    }
    validate_run_record(record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--go-binary", type=Path, default=DEFAULT_GO)
    parser.add_argument("--rust-binary", type=Path, default=DEFAULT_RUST)
    parser.add_argument("--library", choices=("go_bp3d", "rust_unesting"), action="append")
    parser.add_argument("--strategy", choices=("extremepoint", "bottomleftfill", "ga", "brkga", "sa"), action="append")
    parser.add_argument("--time-limit", type=float, action="append")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--repetition", type=int, default=0)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    libraries = args.library or ["go_bp3d", "rust_unesting"]
    strategies = args.strategy or ["extremepoint"]
    time_limits = args.time_limit or [1.0]
    if "go_bp3d" in libraries and not args.go_binary.is_file():
        raise SystemExit(f"missing Go binary: {args.go_binary}")
    if "rust_unesting" in libraries and not args.rust_binary.is_file():
        raise SystemExit(f"missing Rust binary: {args.rust_binary}")
    source_dir = ROOT / ".cache" / "esicup-datasets"
    instances = [instance for instance in parse_all(source_dir / "3d_rectangular" / "thpack") if instance.family in {f"THPACK{i}" for i in range(1, 9)}]
    instances = instances[:args.limit] if args.limit else instances
    JOBS_ROOT.mkdir(parents=True, exist_ok=True)
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    runner_sha = sha256(Path(__file__))
    labels = []
    for library in libraries:
        for strategy in (strategies if library == "rust_unesting" else ["pivot"]):
            labels.append(implementation_id(library, strategy))
    budget_label = "-".join(f"{x:g}s" for x in time_limits)
    library_label = "-".join(labels)
    archive_name = f"raw/experiments/comprehensive/B01-B02-external-projection-{library_label}-{budget_label}-rep-{args.repetition}.tar.gz"
    with tempfile.TemporaryDirectory(prefix="thpack-external-projection-") as temporary:
        work_root = Path(temporary)
        jobs = [
            (instance, library, strategy, order, budget)
            for budget in time_limits
            for instance in instances
            for library in libraries
            for strategy in (strategies if library == "rust_unesting" else ["pivot"])
            for order in ("descending", "ascending")
        ]
        records: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(run_one, instance, library, strategy, order, budget, args.repetition, args.go_binary, args.rust_binary, work_root, archive_name, runner_sha) for instance, library, strategy, order, budget in jobs]
            for index, future in enumerate(as_completed(futures), 1):
                records.append(future.result())
                if index % 100 == 0 or index == len(futures):
                    print(f"{index}/{len(futures)}", flush=True)
        with tarfile.open(ROOT / archive_name, "w:gz") as archive:
            for path in sorted(work_root.iterdir()):
                archive.add(path, arcname=path.name)
    records.sort(key=lambda record: record["run_id"])
    output = RESULTS_ROOT / f"B01-B02-external-projection-{library_label}-{budget_label}-rep-{args.repetition}.jsonl"
    output.write_text("".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
