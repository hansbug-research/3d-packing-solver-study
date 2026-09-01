#!/usr/bin/env python3
"""Run the non-exact Python packers on the B06 exact-oracle cases.

The cases are deliberately tiny and hand-checkable.  py3dbp and Jerry are
single-container packers, so this adapter repeatedly solves the remaining
items against the next available bin.  The original orientation and weight
rules are validated after every run; a projection or a malformed certificate
therefore remains visible in the protocol records.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import subprocess
import sys
import tempfile
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks" / "campaign"))
sys.path.insert(0, str(ROOT / "benchmarks" / "comprehensive"))

from exact_suite import make_cases, validate_solution  # noqa: E402
from model import canonical_json, validate_run_record  # noqa: E402

RUNNER = Path(__file__).resolve()
DEFAULT_OUTPUT = ROOT / "results" / "comprehensive" / "runs" / "B06-external.jsonl"
IMPLEMENTATIONS = ("py3dbp", "jerry")
CASE_NAMES = ("grid_8", "overflow_9", "rotation_required", "rotation_forbidden", "weight_split")


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def one_bin_payload(items: list[Any], bin_spec: Any) -> dict[str, Any]:
    return {
        "bins": [{
            "id": bin_spec.ref,
            "size": list(bin_spec.dimensions),
            "max_weight": bin_spec.capacity,
            "cost": bin_spec.cost,
        }],
        "items": [{
            "id": item.ref,
            "size": list(item.dimensions),
            "weight": item.weight,
        } for item in items],
    }


def worker_payload(items: list[Any], bin_spec: Any) -> dict[str, Any]:
    return {
        "instance": {
            "family": "B06_EXACT_ORACLE",
            "instance_id": 1,
            "problem_kind": "single_container_knapsack",
            "objective": "maximize_packed_volume",
            "container": list(bin_spec.dimensions),
            "seed": 42,
            "source_line_errors": [],
            "item_types": [{
                "type_id": item.ref,
                "size": list(item.dimensions),
                "allowed_vertical_dimensions": [1, 1, 1],
                "copies": 1,
            } for item in items],
        }
    }


def invoke_worker(implementation_id: str, items: list[Any], bin_spec: Any) -> tuple[list[dict[str, Any]], str | None]:
    """Run each Python implementation in a fresh process.

    Jerry vendors a module also named ``py3dbp``; process isolation prevents
    import-order contamination between the two implementations.
    """
    worker = ROOT / "benchmarks" / "campaign" / "python_thpack" / "worker.py"
    python = ROOT / ".venv" / "bin" / "python"
    if not python.exists():
        python = Path(sys.executable)
    with tempfile.TemporaryDirectory(prefix="b06-worker-") as directory:
        input_path = Path(directory) / "input.json"
        input_path.write_text(json.dumps(worker_payload(items, bin_spec), sort_keys=True) + "\n", encoding="utf-8")
        command = [str(python), str(worker), "--library", implementation_id, "--input", str(input_path), "--order", "descending"]
        if implementation_id == "jerry":
            command.extend(["--jerry-fix-point", "false"])
        try:
            completed = subprocess.run(
                command, capture_output=True, text=True, timeout=10.0,
                env={**os.environ, "PYTHONHASHSEED": "0", "OMP_NUM_THREADS": "1"}, check=False,
            )
        except subprocess.TimeoutExpired:
            return [], "worker timed out"
        if completed.returncode != 0:
            return [], f"worker exit {completed.returncode}: {completed.stderr.strip()[:300]}"
        try:
            output = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            return [], f"worker output is not JSON: {exc}"
        return output.get("placements", []), None


def solve_case(case: Any, implementation_id: str) -> tuple[list[dict[str, Any]], float, list[str]]:
    """Use each available bin once, preserving exact-suite bin semantics."""
    remaining = list(case.items)
    placements: list[dict[str, Any]] = []
    errors: list[str] = []
    started = perf_counter()
    for bin_spec in case.bins:
        if not remaining:
            break
        raw, error = invoke_worker(implementation_id, remaining, bin_spec)
        if error:
            errors.append(error)
            continue
        selected_ids = set()
        accepted_weight = 0
        for row in raw:
            item_id = str(row.get("item_id", ""))
            # The shared worker expands every type as ``type_id:copy`` even
            # when a case supplied one copy of each distinct exact item.
            if item_id.endswith(":0") and item_id[:-2] in {item.ref for item in remaining}:
                item_id = item_id[:-2]
            if item_id in selected_ids:
                errors.append(f"duplicate item from worker: {item_id}")
                continue
            source_item = next((item for item in remaining if item.ref == item_id), None)
            if source_item is None:
                errors.append(f"unknown item from worker: {item_id}")
                continue
            # The generic worker intentionally has no payload model.  Keep a
            # deterministic feasible subset for this exact-case adapter and
            # leave rejected items for the next physical bin.
            if accepted_weight + source_item.weight > bin_spec.capacity:
                continue
            selected_ids.add(item_id)
            accepted_weight += source_item.weight
            position = row.get("position", [row.get("x", 0), row.get("y", 0), row.get("z", 0)])
            size = row.get("size", [row.get("dx", 0), row.get("dy", 0), row.get("dz", 0)])
            placements.append({
                "item_ref": item_id,
                "bin_ref": bin_spec.ref,
                "x": float(position[0]), "y": float(position[1]), "z": float(position[2]),
                "dx": float(size[0]), "dy": float(size[1]), "dz": float(size[2]),
            })
        remaining = [item for item in remaining if item.ref not in selected_ids]
    return placements, perf_counter() - started, errors


def make_record(case: Any, implementation_id: str, placements: list[dict[str, Any]], elapsed: float, adapter_errors: list[str], raw_dir: Path) -> dict[str, Any]:
    used_bins = sorted({placement["bin_ref"] for placement in placements})
    objective = sum(bin_spec.cost for bin_spec in case.bins if bin_spec.ref in used_bins)
    validation_errors = validate_solution(case, placements, used_bins, objective)
    validation_errors.extend(adapter_errors)
    if validation_errors:
        solution_status = "INVALID_CERTIFICATE" if placements else "NO_SOLUTION"
        proof_status = "UNKNOWN"
    elif len(placements) == len(case.items):
        solution_status = "VALID_COMPLETE"
        proof_status = "FEASIBLE"
    else:
        solution_status = "VALID_PARTIAL"
        proof_status = "FEASIBLE"
    case_dir = raw_dir / f"{case.name}-{implementation_id}"
    case_dir.mkdir(parents=True, exist_ok=True)
    input_payload = {
        "case": case.name,
        "purpose": case.purpose,
        "items": [item.__dict__ if hasattr(item, "__dict__") else {"ref": item.ref, "dimensions": item.dimensions, "weight": item.weight, "orientations": item.orientations} for item in case.items],
        "bins": [bin_spec.__dict__ if hasattr(bin_spec, "__dict__") else {"ref": bin_spec.ref, "dimensions": bin_spec.dimensions, "capacity": bin_spec.capacity, "cost": bin_spec.cost} for bin_spec in case.bins],
    }
    (case_dir / "input.json").write_text(canonical_json(input_payload), encoding="utf-8")
    (case_dir / "output.json").write_text(canonical_json({"placements": placements}), encoding="utf-8")
    (case_dir / "validation.json").write_text(canonical_json({"errors": validation_errors, "objective": objective}), encoding="utf-8")
    source_hash = digest(input_payload)
    record = {
        "schema_version": 2,
        "protocol_version": "benchmark-protocol/3",
        "record_origin": "PROTOCOL_V3",
        "run_id": f"B06/{case.name}/{implementation_id}/10s/external-composed/rep-0",
        "benchmark_id": "B06",
        "problem_variant": "EXACT_ORACLE_CASES",
        "instance_id": case.name,
        "implementation_id": implementation_id,
        "algorithm": "pivot greedy" if implementation_id == "py3dbp" else "pivot/fix-point greedy",
        "adapter": "b06_external_composed_v1",
        "comparison_track": "COMPOSED",
        "problem_scope": "FULL_PROBLEM",
        "budget": {"time_limit_s": 10.0, "memory_limit_bytes": 1073741824, "thread_limit": 1},
        "item_order": "DESCENDING",
        "bin_order": "SOURCE",
        "seed": None,
        "repetition": 0,
        "input_sha256": source_hash,
        "input_status": "VALID",
        "capability_status": "SUPPORTED_COMPOSED",
        "run_status": "COMPLETED",
        "solution_status": solution_status,
        "proof_status": proof_status,
        "termination_reason": "RETURNED_CERTIFICATE" if not adapter_errors else "ADAPTER_ERROR_WITH_EVIDENCE",
        "resources": {"wall_s": elapsed, "solver_s": elapsed, "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024},
        "metrics": {
            "objective": objective,
            "expected_objective": case.expected_objective,
            "packed_items": len(placements),
            "required_items": len(case.items),
            "bins_used": len(used_bins),
            "validation_error_count": len(validation_errors),
            "validation_errors": validation_errors,
            "adapter_errors": adapter_errors,
            "calibration_only": True,
            "runner_sha256": sha256(RUNNER),
        },
        "artifacts": {
            "input": str((case_dir / "input.json").relative_to(ROOT)),
            "solver_output": str((case_dir / "output.json").relative_to(ROOT)),
            "validation": str((case_dir / "validation.json").relative_to(ROOT)),
        },
    }
    validate_run_record(record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--raw-root", type=Path, default=ROOT / "raw" / "experiments" / "comprehensive" / "B06-external")
    args = parser.parse_args()
    cases = {case.name: case for case in make_cases()}
    records = []
    for case_name in CASE_NAMES:
        for implementation_id in IMPLEMENTATIONS:
            placements, elapsed, errors = solve_case(cases[case_name], implementation_id)
            records.append(make_record(cases[case_name], implementation_id, placements, elapsed, errors, args.raw_root))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n" for record in sorted(records, key=lambda row: row["run_id"])), encoding="utf-8")
    print(f"wrote {len(records)} B06 external records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
