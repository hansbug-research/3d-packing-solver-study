#!/usr/bin/env python3
"""Promote archived, independently revalidated THPACK runs to protocol-v3.

The original THPACK campaign predates the comprehensive manifest and is kept
as ``LEGACY_BASELINE``.  Its records contain the source hashes, pinned fork
commit, binary hash, harness hashes and offline certificate validation.  This
importer creates separate, explicitly named protocol revalidation records for
the BR/LN and IMM native tracks without changing the historical records or
claiming a new solver invocation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:  # package import for tests
    from .model import ROOT, canonical_json, load_catalogs, validate_run_record
except ImportError:  # pragma: no cover - CLI entry point
    from model import ROOT, canonical_json, load_catalogs, validate_run_record


SOURCE_FILES = {
    1.0: ROOT / "results" / "campaign" / "packingsolver-thpack.jsonl",
    10.0: ROOT / "results" / "campaign" / "packingsolver-thpack-10s.jsonl",
}
BENCHMARK_IDS = {"BR": "B01", "LN": "B02", "IMM": "B04"}
IMPLEMENTATION_ID = "packingsolver_fork_box"


def combined_hash(*values: str) -> str:
    return hashlib.sha256(("\n".join(values) + "\n").encode("ascii")).hexdigest()


def source_record(path: Path, budget: float) -> list[tuple[int, dict[str, Any]]]:
    if not path.exists():
        raise FileNotFoundError(path)
    rows: list[tuple[int, dict[str, Any]]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line:
            row = json.loads(line)
            if row.get("family") in BENCHMARK_IDS:
                rows.append((line_number, row))
    expected = 762
    if len(rows) != expected:
        raise ValueError(f"expected {expected} BR/LN records in {path}, found {len(rows)}")
    return rows


def build_records(budget: float, source_path: Path | None = None) -> list[dict[str, Any]]:
    _, implementations = load_catalogs()
    implementation = next(row for row in implementations["implementations"] if row["id"] == IMPLEMENTATION_ID)
    path = source_path or SOURCE_FILES[budget]
    records: list[dict[str, Any]] = []
    for line_number, source in source_record(path, budget):
        benchmark_id = BENCHMARK_IDS[source["family"]]
        source_valid = source.get("source_status") == "VALID"
        validation_errors = list(source.get("validation_errors", []))
        process_ok = source.get("returncode") == 0 and source.get("status") == "VALID"
        certificate_valid = process_ok and not validation_errors
        if not source_valid:
            run_status = "NOT_RUN"
            solution_status = "NOT_APPLICABLE"
            proof_status = "NOT_APPLICABLE"
            termination_reason = "SOURCE_PENDING"
        elif not process_ok:
            run_status = "ERROR"
            solution_status = "NO_SOLUTION"
            proof_status = "UNKNOWN"
            termination_reason = "PROCESS_ERROR_OR_EXTERNAL_TIMEOUT"
        else:
            solver_s = float(source.get("solver_time_s") or 0.0)
            reached_limit = solver_s >= budget * 0.95
            run_status = "TIME_LIMIT" if reached_limit else "COMPLETED"
            if not certificate_valid:
                solution_status = "INVALID_CERTIFICATE"
                proof_status = "UNKNOWN"
                termination_reason = "INVALID_CERTIFICATE"
            elif source["family"] in {"BR", "LN"}:
                solution_status = "VALID_PARTIAL"
                proof_status = "INCUMBENT_WITH_BOUND" if source.get("proof_status") == "SOLVER_REPORTED_BOUND_CLOSED" else "FEASIBLE"
                termination_reason = "TIME_LIMIT_WITH_INCUMBENT" if reached_limit else "SOLVER_STOPPED"
            else:  # kept defensive for future source-family additions
                solution_status = "VALID_COMPLETE" if int(source.get("unpacked_items") or 0) == 0 else "VALID_PARTIAL"
                proof_status = "FEASIBLE"
                termination_reason = "TIME_LIMIT_WITH_INCUMBENT" if reached_limit else "SOLVER_STOPPED"

        input_hashes = source.get("input_sha256", {})
        input_sha = combined_hash(str(input_hashes["items"]), str(input_hashes["bins"])) if source_valid else None
        record = {
            "schema_version": 2,
            "protocol_version": "benchmark-protocol/3",
            "record_origin": "PROTOCOL_V3",
            "run_id": f"{benchmark_id}/{source['instance_id']}/{IMPLEMENTATION_ID}/{budget:g}s/protocol-revalidation/rep-0",
            "benchmark_id": benchmark_id,
            "problem_variant": "ORIGINAL",
            "instance_id": source["instance_id"],
            "implementation_id": IMPLEMENTATION_ID,
            "algorithm": implementation["algorithm"],
            "adapter": "packingsolver_thpack_protocol_revalidation_v1",
            "comparison_track": "NATIVE",
            "problem_scope": "FULL_PROBLEM",
            "budget": {"time_limit_s": budget, "memory_limit_bytes": 1073741824, "thread_limit": None},
            "item_order": "SOLVER_INTERNAL",
            "bin_order": "SOURCE",
            "seed": None,
            "repetition": 0,
            "input_sha256": input_sha,
            "input_status": "VALID" if source_valid else "SOURCE_INCOMPLETE",
            "capability_status": "SUPPORTED_NATIVE",
            "run_status": run_status,
            "solution_status": solution_status,
            "proof_status": proof_status,
            "termination_reason": termination_reason,
            "resources": {
                "wall_s": source.get("wall_time_s"),
                "solver_s": source.get("solver_time_s"),
                "cpu_user_s": source.get("user_time_s"),
                "cpu_system_s": source.get("system_time_s"),
                "peak_rss_bytes": int(source.get("max_rss_kib") or 0) * 1024,
            },
            "metrics": {
                "packed_items": source.get("packed_items"),
                "unpacked_items": source.get("unpacked_items"),
                "bins_used": source.get("bins_used"),
                "packed_volume": source.get("packed_volume"),
                "volume_utilization": source.get("volume_utilization"),
                "solver_reported_bound": source.get("solver_reported_bound"),
                "solver_reported_gap": source.get("relative_gap_to_solver_reported_bound"),
                "validation_error_count": len(validation_errors),
                "revalidation_source": f"results/campaign/{path.name}#L{line_number}",
                "engine_source_commit": source.get("engine_source_commit"),
                "engine_binary_sha256": source.get("engine_binary_sha256"),
                "harness_sha256": source.get("harness_sha256"),
                "provenance_kind": "ARCHIVED_CERTIFICATE_REVALIDATION",
            },
            "artifacts": {
                "source_result": f"results/campaign/{path.name}#L{line_number}",
                "validation": f"results/campaign/{path.name}#L{line_number}",
            },
        }
        validate_run_record(record)
        records.append(record)
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--time-limit", type=float, choices=(1.0, 10.0), required=True)
    parser.add_argument("--source-file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    records = build_records(args.time_limit, args.source_file.resolve() if args.source_file else None)
    content = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n" for record in records)
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != content:
            print(f"PROTOCOL_REVALIDATION_STALE: {args.output}")
            return 1
        print(f"PROTOCOL_REVALIDATION_OK: {len(records)} records")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
