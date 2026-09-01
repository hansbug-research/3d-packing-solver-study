#!/usr/bin/env python3
"""Run an exact B04 calibration on a real THPACK9 source instance.

The public IMM source has no published optimum in the repository, so this is
an exact-model calibration, not a claim about the 47-instance corpus.  It
keeps every source item and its six rotation flags, supplies enough identical
candidate bins for feasibility, and validates the returned certificate with
the independent AABB validator before emitting protocol-v3 records.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
import tarfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks" / "campaign"))
from exact_suite import Bin, Case, Item, _solve_mip, rotations, solve_cp_sat  # noqa: E402
from validation import Box, validate_aabbs  # noqa: E402

sys.path.insert(0, str(ROOT / "benchmarks"))
from comprehensive.model import canonical_json, validate_run_record  # noqa: E402

RUNNER = Path(__file__).resolve()
SOURCE_ROOT = ROOT / ".cache" / "packingsolver-fork" / "data" / "box" / "ivancic1989"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_case(number: int) -> tuple[Case, dict[str, Any], str, str]:
    items_path = SOURCE_ROOT / f"thpack9.txt_{number}_items.csv"
    bins_path = SOURCE_ROOT / f"thpack9.txt_{number}_bins.csv"
    if not items_path.exists() or not bins_path.exists():
        raise FileNotFoundError(f"missing source files for THPACK9 instance {number}")
    items: list[Item] = []
    with items_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            dimensions = tuple(int(row[axis]) for axis in ("X", "Y", "Z"))
            allowed = tuple(
                dimensions[index]
                for index in range(3)
            )
            flags = {
                "XYZ": int(row["ROTATION_XYZ"]),
                "YXZ": int(row["ROTATION_YXZ"]),
                "ZYX": int(row["ROTATION_ZYX"]),
                "YZX": int(row["ROTATION_YZX"]),
                "XZY": int(row["ROTATION_XZY"]),
                "ZXY": int(row["ROTATION_ZXY"]),
            }
            orientations = tuple(
                tuple(dimensions[index] for index in order)
                for name, order in (
                    ("XYZ", (0, 1, 2)), ("YXZ", (1, 0, 2)),
                    ("ZYX", (2, 1, 0)), ("YZX", (1, 2, 0)),
                    ("XZY", (0, 2, 1)), ("ZXY", (2, 0, 1)),
                ) if flags[name]
            )
            if not orientations:
                raise ValueError(f"source item {row['ID']} has no permitted orientation")
            for copy_index in range(int(row["COPIES"])):
                items.append(Item(f"{row['ID']}:{copy_index}", dimensions, 1, tuple(sorted(set(orientations)))))
    with bins_path.open(newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    dimensions = tuple(int(row[axis]) for axis in ("X", "Y", "Z"))
    # One candidate bin per item is a finite upper bound; all bins are the
    # source type because this is identical-bin packing.
    bins = tuple(Bin(f"bin-{index}", dimensions, 10**9, 1) for index in range(len(items)))
    case = Case(
        f"THPACK9_{number}", tuple(items), bins, "UNKNOWN", None,
        "Source-derived exact B04 calibration; no published optimum is asserted.",
    )
    payload = {
        "benchmark_id": "B04",
        "problem_variant": "SOURCE_IMM_EXACT_CALIBRATION",
        "source_instance": f"thpack9.txt_{number}",
        "items": [
            {"item_ref": item.ref, "dimensions": list(item.dimensions), "orientations": [list(x) for x in item.orientations]}
            for item in items
        ],
        "bin_dimensions": list(dimensions),
        "candidate_bin_count": len(bins),
        "source_items_sha256": sha256(items_path),
        "source_bins_sha256": sha256(bins_path),
    }
    return case, payload, sha256(items_path), sha256(bins_path)


def validate_solution(case: Case, result: dict[str, Any]) -> list[str]:
    placements = result.get("placements", [])
    errors: list[str] = []
    expected = {item.ref: item for item in case.items}
    refs = [row.get("item_ref") for row in placements]
    if sorted(refs) != sorted(expected):
        errors.append(f"placement refs differ: {len(refs)} returned, {len(expected)} required")
    if len(refs) != len(set(refs)):
        errors.append("duplicate item placement")
    boxes: list[Box] = []
    bin_sizes = {bin_.ref: bin_.dimensions for bin_ in case.bins}
    for row in placements:
        item = expected.get(row.get("item_ref"))
        if item is None:
            continue
        dims = tuple(int(row[key]) for key in ("dx", "dy", "dz"))
        if dims not in item.orientations:
            errors.append(f"{item.ref}: forbidden orientation {dims}")
        if row.get("bin_ref") not in bin_sizes:
            errors.append(f"{item.ref}: unknown bin {row.get('bin_ref')}")
            continue
        boxes.append(Box(item.ref, row["bin_ref"], *(float(row[key]) for key in ("x", "y", "z", "dx", "dy", "dz")), 1))
    errors.extend(validate_aabbs(boxes, bin_sizes))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("cp-sat", "scip", "gurobi", "cplex"), required=True)
    parser.add_argument("--source-number", type=int, default=18)
    parser.add_argument("--time-limit", type=float, default=20.0)
    args = parser.parse_args()
    case, payload, items_hash, bins_hash = source_case(args.source_number)
    impl = {"cp-sat": "exact_cp_sat", "scip": "exact_scip", "gurobi": "exact_gurobi", "cplex": "exact_cplex"}[args.backend]
    raw_dir = ROOT / "raw" / "experiments" / "comprehensive" / "B04" / impl / f"{args.time_limit:g}s"
    cases_dir = raw_dir / "cases" / f"thpack9.txt_{args.source_number}"
    cases_dir.mkdir(parents=True, exist_ok=True)
    (cases_dir / "input.json").write_text(canonical_json(payload), encoding="utf-8")
    try:
        result = solve_cp_sat(case, args.time_limit) if args.backend == "cp-sat" else _solve_mip(case, args.backend, args.time_limit)
    except Exception as exc:
        result = {
            "status": "ERROR", "placements": [], "used_bins": [], "objective": None,
            "bound": None, "gap": None, "solver_time_s": 0.0,
            "nodes_or_branches": None, "validation_errors": [],
            "error": f"{type(exc).__name__}: {exc}",
        }
    backend_error_statuses = {"ERROR", "MEMLIMIT", "NODELIMIT", "GAPLIMIT", "USERINTERRUPT"}
    validation_errors = validate_solution(case, result) if result["status"] not in backend_error_statuses else []
    result["validation_errors"] = validation_errors
    (cases_dir / "output.json").write_text(canonical_json(result), encoding="utf-8")
    (cases_dir / "validation.json").write_text(canonical_json({"status": "PASS" if not validation_errors else "FAIL", "errors": validation_errors}), encoding="utf-8")
    status = result["status"]
    valid = status in {"OPTIMAL", "FEASIBLE", "TIME_LIMIT"} and not validation_errors
    run_status = "TIME_LIMIT" if status in {"FEASIBLE", "TIME_LIMIT"} else "ERROR" if status in backend_error_statuses else "COMPLETED"
    solution_status = "VALID_COMPLETE" if valid else "NO_SOLUTION" if status in {"INFEASIBLE", *backend_error_statuses} else "INVALID_CERTIFICATE"
    proof_status = "PROVEN_OPTIMAL" if status == "OPTIMAL" and valid else "INCUMBENT_WITH_BOUND" if valid else "UNKNOWN"
    source_key = f"THPACK9_{args.source_number}"
    record = {
        "schema_version": 2, "protocol_version": "benchmark-protocol/3", "record_origin": "PROTOCOL_V3",
        "run_id": f"B04/SOURCE_IMM_EXACT_CALIBRATION/{source_key}/{impl}/{args.time_limit:g}s/EXACT_MODEL/rep-0",
        "benchmark_id": "B04", "problem_variant": "SOURCE_IMM_EXACT_CALIBRATION", "instance_id": source_key,
        "implementation_id": impl, "algorithm": f"identical-bin exact {args.backend.upper()}", "adapter": f"run_b04_exact_mip.py/{args.backend}",
        "comparison_track": "EXACT_MODEL", "problem_scope": "FULL_PROBLEM",
        "budget": {"time_limit_s": args.time_limit, "memory_limit_bytes": 4294967296, "thread_limit": 1},
        "item_order": "SOURCE", "bin_order": "SOURCE", "seed": 42, "repetition": 0,
        "input_sha256": hashlib.sha256((items_hash + "\n" + bins_hash + "\n").encode("ascii")).hexdigest(),
        "input_status": "VALID", "capability_status": "SUPPORTED_NATIVE", "run_status": run_status,
        "solution_status": solution_status, "proof_status": proof_status,
        "termination_reason": result.get("error", status),
        "resources": {"solver_s": result.get("solver_time_s"), "wall_s": result.get("wall_time_s", result.get("solver_time_s")), "peak_rss_bytes": None},
        "metrics": {
            "bins_used": len(result.get("used_bins", [])), "required_items": len(case.items), "packed_items": len(result.get("placements", [])),
            "objective": result.get("objective"), "solver_bound": result.get("bound"), "gap": result.get("gap"),
            "validation_error_count": len(validation_errors), "backend": args.backend, "source_items_sha256": items_hash,
            "source_bins_sha256": bins_hash, "runner_sha256": sha256(RUNNER), "backend_error": result.get("error"),
            "calibration_only": True,
        },
        "artifacts": {
            "input": f"raw/experiments/comprehensive/B04/{impl}/{args.time_limit:g}s/cases/thpack9.txt_{args.source_number}/input.json",
            "solver_output": f"raw/experiments/comprehensive/B04/{impl}/{args.time_limit:g}s/cases/thpack9.txt_{args.source_number}/output.json",
            "validation": f"raw/experiments/comprehensive/B04/{impl}/{args.time_limit:g}s/cases/thpack9.txt_{args.source_number}/validation.json",
        },
    }
    validate_run_record(record)
    archive_path = raw_dir / "artifacts.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for path in sorted((raw_dir / "cases").rglob("*")):
            if path.is_file():
                archive.add(path, arcname=path.relative_to(raw_dir))
    output = ROOT / "results" / "comprehensive" / "runs" / f"B04-{impl}-{args.time_limit:g}s-exact-calibration.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    (raw_dir / "metadata.json").write_text(canonical_json({
        "schema_version": 1, "protocol_version": "benchmark-protocol/3", "benchmark_id": "B04", "implementation_id": impl,
        "source_instance": source_key, "backend": args.backend, "time_limit_s": args.time_limit,
        "runner_sha256": sha256(RUNNER), "output_sha256": sha256(output), "archive_sha256": sha256(archive_path),
        "python_version": platform.python_version(), "calibration_only": True,
    }), encoding="utf-8")
    print(output.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
