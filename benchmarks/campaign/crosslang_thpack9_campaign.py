#!/usr/bin/env python3
"""Run and independently validate Go/Rust candidates on valid THPACK9 instances."""

from __future__ import annotations

import json
import math
import os
import resource
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / "benchmarks" / "campaign" / "python_thpack"
sys.path.insert(0, str(MODEL_DIR))

from model import ESICUP_COMMIT, expanded_items, parse_family, validate_certificate  # noqa: E402


SOURCE = ROOT / ".cache" / "esicup-datasets" / "3d_rectangular" / "thpack" / "thpack9.txt"
RAW_ROOT = ROOT / "raw" / "experiments" / "campaign"
RESULT_ROOT = ROOT / "results" / "campaign"
PROCESS_TIMEOUT_SECONDS = 35
MEMORY_LIMIT_BYTES = 2 * 1024 * 1024 * 1024


def child_limits() -> None:
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES))


def percentile_nearest_rank(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def numeric_statistics(values: list[float]) -> dict[str, float | None]:
    return {
        "mean": statistics.fmean(values) if values else None,
        "median": statistics.median(values) if values else None,
        "p95_nearest_rank": percentile_nearest_rank(values, 0.95),
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
    }


def resource_value(path: Path, label: str) -> int | None:
    prefix = f"\t{label}: "
    for line in path.read_text().splitlines():
        if line.startswith(prefix):
            return int(line.removeprefix(prefix))
    return None


def make_input(instance: Any) -> dict[str, Any]:
    items = [
        {
            "id": item["item_id"],
            "size": list(item["size"]),
            "weight": 1.0,
            "orientation_requirement": "any",
        }
        for item in expanded_items(instance)
    ]
    bins = [
        {
            "id": f"bin:{index:03}",
            "size": list(instance.container),
            "max_weight": float(instance.item_count + 1),
            "cost": 1.0,
        }
        for index in range(instance.item_count)
    ]
    return {"scenario": instance.key, "bins": bins, "items": items}


def validate(instance: Any, payload: dict[str, Any], process_exitcode: int) -> dict[str, Any]:
    placements = [
        {
            "item_id": placement["item_id"],
            "bin_id": placement["bin_id"],
            "x": placement["position"][0],
            "y": placement["position"][1],
            "z": placement["position"][2],
            "dx": placement["size"][0],
            "dy": placement["size"][1],
            "dz": placement["size"][2],
            "rotation": placement["rotation"],
        }
        for placement in payload.get("placements", [])
    ]
    errors = validate_certificate(instance, placements, require_complete=True)
    known_bins = {bin_spec["id"] for bin_spec in payload.get("bins", [])}
    unknown_bins = sorted({p["bin_id"] for p in placements if p["bin_id"] not in known_bins})
    if unknown_bins:
        errors.append(f"unknown bins: {unknown_bins}")
    reported_unplaced = set(payload.get("unplaced", []))
    placed_ids = {placement["item_id"] for placement in placements}
    expected_unplaced = {item["item_id"] for item in expanded_items(instance)} - placed_ids
    if reported_unplaced != expected_unplaced:
        errors.append("reported unplaced IDs do not match certificate complement")

    orientation_valid = not any("orientation" in error for error in errors)
    boundary_valid = not any("exceeds container" in error or "negative coordinate" in error for error in errors)
    overlap_valid = not any(" overlaps " in error for error in errors)
    complete = len(placed_ids) == instance.item_count and not reported_unplaced
    identity_valid = not any(
        marker in error
        for error in errors
        for marker in ("unknown item", "duplicate placement", "item accounting", "reported unplaced")
    )
    invalid = process_exitcode != 0 or bool(errors) or not complete
    return {
        "status": "VALID_COMPLETE" if not invalid else "INVALID_OR_INCOMPLETE",
        "process_exitcode": process_exitcode,
        "items_total": instance.item_count,
        "items_placed": len(placements),
        "bins_used": len({placement["bin_id"] for placement in placements}),
        "complete": complete,
        "identity_valid": identity_valid,
        "orientation_valid": orientation_valid,
        "boundary_valid": boundary_valid,
        "overlap_valid": overlap_valid,
        "invalid": invalid,
        "validation_errors": errors,
        "library_elapsed_ms": payload.get("elapsed_ms"),
        "capability_status": payload.get("capability_status"),
    }


def run_library(name: str, binary: Path, instances: list[Any]) -> dict[str, Any]:
    raw_dir = RAW_ROOT / name
    raw_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for instance in instances:
        run_id = instance.key.lower()
        input_path = raw_dir / f"{run_id}.input.json"
        stdout_path = raw_dir / f"{run_id}.stdout.json"
        stderr_path = raw_dir / f"{run_id}.stderr"
        resource_path = raw_dir / f"{run_id}.resources.txt"
        exitcode_path = raw_dir / f"{run_id}.exitcode"
        input_path.write_text(json.dumps(make_input(instance), separators=(",", ":")) + "\n")
        adapter_arguments = ["--input", str(input_path)]
        if "rust" in name:
            adapter_arguments.extend(["extremepoint", "1000"])
        command = [
            "/usr/bin/time",
            "-v",
            "-o",
            str(resource_path),
            "timeout",
            "--signal=TERM",
            "--kill-after=5s",
            f"{PROCESS_TIMEOUT_SECONDS}s",
            str(binary),
            *adapter_arguments,
        ]
        environment = os.environ.copy()
        environment.update(
            GOMAXPROCS="1",
            RAYON_NUM_THREADS="1",
            OMP_NUM_THREADS="1",
            OPENBLAS_NUM_THREADS="1",
            MKL_NUM_THREADS="1",
            NUMEXPR_NUM_THREADS="1",
        )
        with stdout_path.open("w") as stdout, stderr_path.open("w") as stderr:
            completed = subprocess.run(
                command,
                stdout=stdout,
                stderr=stderr,
                env=environment,
                preexec_fn=child_limits,
                check=False,
            )
        exitcode_path.write_text(f"{completed.returncode}\n")
        try:
            payload = json.loads(stdout_path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            record = {
                "instance": instance.key,
                "status": "PROCESS_ERROR",
                "process_exitcode": completed.returncode,
                "items_total": instance.item_count,
                "items_placed": 0,
                "bins_used": None,
                "complete": False,
                "identity_valid": False,
                "orientation_valid": False,
                "boundary_valid": False,
                "overlap_valid": False,
                "invalid": True,
                "validation_errors": [f"missing/invalid JSON output: {error}"],
                "library_elapsed_ms": None,
                "capability_status": None,
            }
        else:
            record = {"instance": instance.key, **validate(instance, payload, completed.returncode)}
        record["peak_rss_kib"] = resource_value(resource_path, "Maximum resident set size (kbytes)")
        records.append(record)

    valid_bins = [float(record["bins_used"]) for record in records if not record["invalid"]]
    valid_elapsed = [
        float(record["library_elapsed_ms"])
        for record in records
        if not record["invalid"] and record["library_elapsed_ms"] is not None
    ]
    peak_rss = [float(record["peak_rss_kib"]) for record in records if record["peak_rss_kib"] is not None]
    invalid_count = sum(record["invalid"] for record in records)
    summary = {
        "schema_version": 1,
        "library": name,
        "source_dataset": "ESICUP THPACK9",
        "source_commit": ESICUP_COMMIT,
        "source_file": str(SOURCE.relative_to(ROOT)),
        "malformed_excluded": ["THPACK9-018", "THPACK9-019", "THPACK9-020"],
        "valid_instances_expected": 44,
        "instances_executed": len(records),
        "valid_complete_instances": len(records) - invalid_count,
        "invalid_instances": invalid_count,
        "invalid_rate": invalid_count / len(records),
        "bins_used_statistics_valid_complete_only": numeric_statistics(valid_bins),
        "library_elapsed_ms_statistics_valid_complete_only": numeric_statistics(valid_elapsed),
        "peak_rss_kib_statistics_all_runs": numeric_statistics(peak_rss),
        "capability_statuses": sorted({record["capability_status"] for record in records}),
        "checks": ["identity", "completeness", "vertical-orientation flags", "boundary", "same-bin AABB overlap"],
        "process_timeout_seconds": PROCESS_TIMEOUT_SECONDS,
        "memory_limit_bytes": MEMORY_LIMIT_BYTES,
        "thread_limits": {"GOMAXPROCS": 1, "RAYON_NUM_THREADS": 1, "BLAS_OMP_FAMILY": 1},
        "records": records,
    }
    output_dir = RESULT_ROOT / name
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "results.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    with (raw_dir / "records.jsonl").open("w") as stream:
        for record in records:
            stream.write(json.dumps(record, separators=(",", ":")) + "\n")
    return summary


def main() -> None:
    actual_source_commit = subprocess.check_output(
        ["git", "-C", str(ROOT / ".cache" / "esicup-datasets"), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual_source_commit != ESICUP_COMMIT:
        raise SystemExit(f"ESICUP checkout mismatch: {actual_source_commit}")
    instances = [instance for instance in parse_family(SOURCE, 9) if not instance.source_line_errors]
    if len(instances) != 44:
        raise SystemExit(f"expected 44 valid THPACK9 instances, found {len(instances)}")
    libraries = {
        "crosslang_go_bp3d_thpack9": Path("/tmp/packing-crosslang-go-build/crosslang_go_bp3d"),
        "crosslang_rust_unesting_thpack9": Path("/tmp/packing-crosslang-u-build/target/release/crosslang-rust-unesting"),
    }
    summaries = {}
    for name, binary in libraries.items():
        if not binary.is_file():
            raise SystemExit(f"missing campaign binary: {binary}")
        summary = run_library(name, binary, instances)
        summaries[name] = {
            "valid_complete_instances": summary["valid_complete_instances"],
            "invalid_rate": summary["invalid_rate"],
            "bins": summary["bins_used_statistics_valid_complete_only"],
        }
    print(json.dumps(summaries, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
