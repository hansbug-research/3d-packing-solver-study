#!/usr/bin/env python3
"""Normalize fresh Wave-1 solver invocations into protocol-v3 records.

The historical campaign remains ``LEGACY_BASELINE``.  This importer consumes
only the outputs produced by the current exact-small and Skjolber runners and
marks their provenance explicitly, so a rerun is distinguishable from an
offline archive revalidation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

try:
    from .model import ROOT, load_catalogs, validate_run_record
except ImportError:  # pragma: no cover
    from model import ROOT, load_catalogs, validate_run_record


RESULTS = ROOT / "results" / "campaign"
OUTPUT_DEFAULT = ROOT / "results" / "comprehensive" / "runs" / "wave1-fresh-protocol.jsonl"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def payload_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def finite_or_none(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def implementation_index() -> dict[str, dict[str, Any]]:
    _, catalog = load_catalogs()
    return {row["id"]: row for row in catalog["implementations"]}


def exact_input_hashes() -> dict[str, str]:
    import sys
    from dataclasses import asdict

    sys.path.insert(0, str(ROOT / "benchmarks"))
    sys.path.insert(0, str(ROOT / "benchmarks" / "campaign"))
    from exact_suite import make_cases

    return {case.name: payload_hash(asdict(case)) for case in make_cases()}


def exact_records(implementations: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    input_hashes = exact_input_hashes()
    records: list[dict[str, Any]] = []
    for backend in ("cp-sat", "scip", "gurobi", "cplex"):
        result_path = RESULTS / f"exact-strengthened-{backend}.json"
        result_sha = sha256(result_path)
        data = json.loads(result_path.read_text(encoding="utf-8"))
        implementation_id = {
            "cp-sat": "exact_cp_sat",
            "scip": "exact_scip",
            "gurobi": "exact_gurobi",
            "cplex": "exact_cplex",
        }[backend]
        implementation = implementations[implementation_id]
        for index, row in enumerate(data["cases"]):
            is_cost = row["case"].startswith("heterogeneous_")
            benchmark_id = "B09" if is_cost else "B06"
            status = row["status"]
            if status == "INFEASIBLE":
                solution_status, proof_status = "NO_SOLUTION", "PROVEN_INFEASIBLE"
            elif row.get("validation_errors"):
                solution_status, proof_status = "INVALID_CERTIFICATE", "UNKNOWN"
            elif status == "OPTIMAL":
                solution_status, proof_status = "VALID_COMPLETE", "PROVEN_OPTIMAL"
            elif status in {"FEASIBLE", "TIME_LIMIT"}:
                solution_status, proof_status = "VALID_COMPLETE", "INCUMBENT_WITH_BOUND"
            else:
                solution_status, proof_status = "NO_SOLUTION", "UNKNOWN"
            run_status = "TIME_LIMIT" if status in {"FEASIBLE", "TIME_LIMIT"} else "COMPLETED"
            record = {
                "schema_version": 2,
                "protocol_version": "benchmark-protocol/3",
                "record_origin": "PROTOCOL_V3",
                "run_id": f"{benchmark_id}/{row['case']}/{implementation_id}/20s/strengthened/fresh/rep-0",
                "benchmark_id": benchmark_id,
                "problem_variant": "STRENGTHENED",
                "instance_id": row["case"],
                "implementation_id": implementation_id,
                "algorithm": implementation["algorithm"],
                "adapter": "exact_suite/strengthened_fresh_v1",
                "comparison_track": "EXACT_MODEL",
                "problem_scope": "FULL_PROBLEM",
                "budget": {"time_limit_s": 20.0, "memory_limit_bytes": None, "thread_limit": 1},
                "item_order": "CANONICAL",
                "bin_order": "CANONICAL",
                "seed": 42,
                "repetition": 0,
                "input_sha256": input_hashes[row["case"]],
                "input_status": "VALID",
                "capability_status": "SUPPORTED_NATIVE",
                "run_status": run_status,
                "solution_status": solution_status,
                "proof_status": proof_status,
                "termination_reason": status,
                "resources": {
                    "solver_s": row.get("solver_time_s"),
                    "wall_s": row.get("wall_time_s"),
                    "peak_rss_bytes": None,
                },
                "metrics": {
                    "objective": row.get("objective"),
                    "bound": row.get("bound"),
                    "gap": finite_or_none(row.get("gap")),
                    "bins_used": len(row.get("used_bins", [])),
                    "nodes_or_branches": row.get("nodes_or_branches"),
                    "conflicts": row.get("conflicts"),
                    "validation_error_count": len(row.get("validation_errors", [])),
                    "provenance_kind": "FRESH_SOLVER_INVOCATION",
                    "result_sha256": result_sha,
                    "result_reference": f"results/campaign/{result_path.name}#cases[{index}]",
                    "runner": "benchmarks/campaign/exact_suite.py",
                    "runner_sha256": sha256(ROOT / "benchmarks" / "campaign" / "exact_suite.py"),
                },
                "artifacts": {
                    "source_result": f"results/campaign/{result_path.name}#cases[{index}]",
                    "validation": f"results/campaign/{result_path.name}#cases[{index}].validation_errors",
                    "runner": "benchmarks/campaign/exact_suite.py",
                },
            }
            validate_run_record(record)
            records.append(record)
    return records


def skjolber_records(implementations: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    result_path = RESULTS / "skjolber-thpack9.json"
    result_sha = sha256(result_path)
    data = json.loads(result_path.read_text(encoding="utf-8"))
    algorithm_ids = {"plain": "skjolber_plain", "laff": "skjolber_laff", "fast_brute_force": "skjolber_fast_bruteforce"}
    records: list[dict[str, Any]] = []
    for index, row in enumerate(data["records"]):
        if not row.get("source_line_valid"):
            continue
        implementation_id = algorithm_ids[row["algorithm"]]
        valid = row["status"] == "VALID" and not row.get("validation_errors") and not row.get("independent_validation_errors")
        record = {
            "schema_version": 2,
            "protocol_version": "benchmark-protocol/3",
            "record_origin": "PROTOCOL_V3",
            "run_id": f"B04/{row['instance_id']}/{implementation_id}/10s/fresh/rep-0",
            "benchmark_id": "B04",
            "problem_variant": "ORIGINAL",
            "instance_id": row["instance_id"],
            "implementation_id": implementation_id,
            "algorithm": implementations[implementation_id]["algorithm"],
            "adapter": "skjolber_thpack9_fresh_v1",
            "comparison_track": "NATIVE",
            "problem_scope": "FULL_PROBLEM",
            "budget": {"time_limit_s": 10.0, "memory_limit_bytes": 536870912, "thread_limit": 1},
            "item_order": "SOURCE",
            "bin_order": "SOURCE",
            "seed": None,
            "repetition": 0,
            "input_sha256": hashlib.sha256((row["items_sha256"] + "\n" + row["bins_sha256"] + "\n").encode("ascii")).hexdigest(),
            "input_status": "VALID",
            "capability_status": "SUPPORTED_NATIVE",
            "run_status": "TIME_LIMIT" if row.get("timeout") else "COMPLETED",
            "solution_status": "VALID_COMPLETE" if valid else "INVALID_CERTIFICATE",
            "proof_status": "FEASIBLE" if valid else "UNKNOWN",
            "termination_reason": "RETURNED_CERTIFICATE" if valid else "INVALID_CERTIFICATE",
            "resources": {
                "wall_s": float(row["wall_time_ms"]) / 1000.0,
                "solver_s": float(row["library_duration_ms"]) / 1000.0,
                "peak_rss_bytes": None,
            },
            "metrics": {
                "bins_used": row["bins_used"],
                "packed_items": row["placements"],
                "required_items": row["required_items"],
                "packed_volume": row["packed_volume"],
                "validation_error_count": len(row.get("validation_errors", [])) + len(row.get("independent_validation_errors", [])),
                "provenance_kind": "FRESH_SOLVER_INVOCATION",
                "result_sha256": result_sha,
                "result_reference": f"results/campaign/{result_path.name}#records[{index}]",
                "engine_source_commit": data["source_commit"],
            },
            "artifacts": {
                "source_result": f"results/campaign/{result_path.name}#records[{index}]",
                "validation": f"results/campaign/{result_path.name}#records[{index}].independent_validation",
            },
        }
        validate_run_record(record)
        records.append(record)
    return records


def build_records() -> list[dict[str, Any]]:
    implementations = implementation_index()
    records = exact_records(implementations) + skjolber_records(implementations)
    records.sort(key=lambda record: record["run_id"])
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT_DEFAULT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    records = build_records()
    content = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n" for record in records)
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != content:
            print(f"FRESH_PROTOCOL_STALE: {args.output}")
            return 1
        print(f"FRESH_PROTOCOL_OK: {len(records)} records")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
