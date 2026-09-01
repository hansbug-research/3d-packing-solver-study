#!/usr/bin/env python3
"""Run gedex/bp3d against the B06 exact-oracle calibration cases."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import subprocess
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(ROOT / "benchmarks" / "comprehensive"))
sys.path.insert(0, str(ROOT / "benchmarks" / "campaign"))
from exact_suite import make_cases, validate_solution  # noqa: E402
from model import canonical_json, validate_run_record  # noqa: E402

GO = Path("/tmp/packing-crosslang-go-build/crosslang_go_bp3d")
RUNNER = Path(__file__).resolve()
OUTPUT = ROOT / "results" / "comprehensive" / "runs" / "B06-go.jsonl"
RAW = ROOT / "raw" / "experiments" / "comprehensive" / "B06-go"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def payload(case):
    return {
        "scenario": f"B06-{case.name}",
        "bins": [{"id": b.ref, "size": list(b.dimensions), "max_weight": b.capacity, "cost": b.cost} for b in case.bins],
        "items": [{"id": i.ref, "size": list(i.dimensions), "weight": i.weight} for i in case.items],
    }


def run_one(case, raw_root: Path):
    case_dir = raw_root / case.name
    case_dir.mkdir(parents=True, exist_ok=True)
    input_value = payload(case)
    input_path = case_dir / "input.json"
    output_path = case_dir / "output.json"
    stderr_path = case_dir / "stderr.log"
    input_path.write_text(canonical_json(input_value), encoding="utf-8")
    started = perf_counter()
    try:
        completed = subprocess.run([str(GO), "--input", str(input_path)], capture_output=True, text=True, timeout=10.0, env={**os.environ, "GOMAXPROCS": "1"}, check=False)
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        process_ok = completed.returncode == 0
        output = json.loads(completed.stdout) if process_ok else {"placements": []}
        output_path.write_text(canonical_json(output), encoding="utf-8")
    except Exception as exc:
        process_ok = False
        output = {"placements": []}
        stderr_path.write_text(str(exc), encoding="utf-8")
    elapsed = perf_counter() - started
    placements = []
    for row in output.get("placements", []):
        placements.append({
            "item_ref": str(row.get("item_id")), "bin_ref": str(row.get("bin_id", case.bins[0].ref)),
            "x": float(row.get("position", [row.get("x", 0), row.get("y", 0), row.get("z", 0)])[0]),
            "y": float(row.get("position", [row.get("x", 0), row.get("y", 0), row.get("z", 0)])[1]),
            "z": float(row.get("position", [row.get("x", 0), row.get("y", 0), row.get("z", 0)])[2]),
            "dx": float(row.get("size", [row.get("dx", 0), row.get("dy", 0), row.get("dz", 0)])[0]),
            "dy": float(row.get("size", [row.get("dx", 0), row.get("dy", 0), row.get("dz", 0)])[1]),
            "dz": float(row.get("size", [row.get("dx", 0), row.get("dy", 0), row.get("dz", 0)])[2]),
        })
    used = sorted({row["bin_ref"] for row in placements})
    objective = sum(b.cost for b in case.bins if b.ref in used)
    errors = validate_solution(case, placements, used, objective)
    if not process_ok:
        status, solution, proof = "ERROR", "NO_SOLUTION", "UNKNOWN"
    elif errors:
        status, solution, proof = "COMPLETED", "INVALID_CERTIFICATE", "UNKNOWN"
    elif len(placements) == len(case.items):
        status, solution, proof = "COMPLETED", "VALID_COMPLETE", "FEASIBLE"
    else:
        status, solution, proof = "COMPLETED", "VALID_PARTIAL", "FEASIBLE"
    validation_path = case_dir / "validation.json"
    validation_path.write_text(canonical_json({"errors": errors, "objective": objective, "packed_items": len(placements)}), encoding="utf-8")
    input_hash = hashlib.sha256(json.dumps(input_value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    record = {
        "schema_version": 2, "protocol_version": "benchmark-protocol/3", "record_origin": "PROTOCOL_V3",
        "run_id": f"B06/{case.name}/go_bp3d/10s/native-go/rep-0", "benchmark_id": "B06", "problem_variant": "EXACT_ORACLE_CASES", "instance_id": case.name,
        "implementation_id": "go_bp3d", "algorithm": "pivot greedy", "adapter": "b06_go_native_v1", "comparison_track": "NATIVE", "problem_scope": "FULL_PROBLEM",
        "budget": {"time_limit_s": 10.0, "memory_limit_bytes": 1073741824, "thread_limit": 1}, "item_order": "SOURCE", "bin_order": "SOURCE", "seed": None, "repetition": 0,
        "input_sha256": input_hash, "input_status": "VALID", "capability_status": "SUPPORTED_NATIVE", "run_status": status, "solution_status": solution, "proof_status": proof,
        "termination_reason": "RETURNED_CERTIFICATE" if process_ok else "PROCESS_ERROR", "resources": {"wall_s": elapsed, "solver_s": elapsed, "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024},
        "metrics": {"objective": objective, "expected_objective": case.expected_objective, "packed_items": len(placements), "required_items": len(case.items), "bins_used": len(used), "validation_error_count": len(errors), "validation_errors": errors, "calibration_only": True, "binary_sha256": sha256(GO) if GO.exists() else None, "runner_sha256": sha256(RUNNER)},
        "artifacts": {"input": str(input_path.relative_to(ROOT)), "solver_output": str(output_path.relative_to(ROOT)) if output_path.exists() else None, "stderr": str(stderr_path.relative_to(ROOT)), "validation": str(validation_path.relative_to(ROOT))},
    }
    validate_run_record(record)
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--raw-root", type=Path, default=RAW)
    args = parser.parse_args()
    cases = {case.name: case for case in make_cases()}
    records = [run_one(cases[name], args.raw_root) for name in ("grid_8", "overflow_9", "rotation_required", "rotation_forbidden", "weight_split")]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n" for record in records), encoding="utf-8")
    print(f"wrote {len(records)} B06 Go records to {args.output}")


if __name__ == "__main__":
    main()
