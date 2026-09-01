#!/usr/bin/env python3
"""Materialize audited source/capability status for unexecutable suite cells.

This command deliberately emits ``NOT_RUN`` records only for cells that cannot
be executed without changing the benchmark semantics: incomplete sources,
missing adapters, or explicitly unsupported capabilities.  A valid source and
supported capability remains a real execution task and is never silently
converted into a status-only record.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:  # support both ``python record_source_status.py`` and package imports
    from .model import comparison_track, load_catalogs, validate_run_record
except ImportError:  # pragma: no cover - exercised by the CLI entry point
    from model import comparison_track, load_catalogs, validate_run_record


def build_records(benchmark_id: str, audit_artifact: str) -> list[dict]:
    suites, implementations = load_catalogs()
    suite = next(row for row in suites["suites"] if row["id"] == benchmark_id)
    records: list[dict] = []
    for implementation in sorted(implementations["implementations"], key=lambda row: row["id"]):
        capability = suite["capability_by_profile"][implementation["capability_profile"]]
        track = comparison_track(implementation, capability)
        scope = "GEOMETRY_PROJECTION" if capability == "PROJECTION_ONLY" else "NOT_APPLICABLE" if capability == "NOT_SUPPORTED" else "FULL_PROBLEM"
        # A source audit blocks every implementation in the suite, while a
        # valid source only permits status materialization for an unexecutable
        # capability.  Supported cells must be run by a real adapter.
        blocked_by_source = suite["input_status"] != "VALID"
        blocked_by_capability = capability in {"NOT_SUPPORTED", "ADAPTER_MISSING"}
        if not (blocked_by_source or blocked_by_capability):
            continue
        if blocked_by_source:
            termination_reason = "SOURCE_PENDING"
        else:
            termination_reason = capability
        if capability == "NOT_SUPPORTED":
            scope = "NOT_APPLICABLE"
        elif capability == "PROJECTION_ONLY":
            scope = "GEOMETRY_PROJECTION"
        else:
            scope = "FULL_PROBLEM"
        record = {
            "schema_version": 2,
            "protocol_version": "benchmark-protocol/3",
            "record_origin": "PROTOCOL_V3",
            "run_id": f"{benchmark_id}/STATUS/{implementation['id']}/rep-0",
            "benchmark_id": benchmark_id,
            "problem_variant": "ORIGINAL",
            "instance_id": "STATUS_ONLY",
            "implementation_id": implementation["id"],
            "algorithm": implementation["algorithm"],
            "adapter": None,
            "comparison_track": track,
            "problem_scope": scope,
            "budget": {"time_limit_s": None, "memory_limit_bytes": None, "thread_limit": 1},
            "item_order": "NOT_APPLICABLE",
            "bin_order": "NOT_APPLICABLE",
            "seed": None,
            "repetition": 0,
            "input_sha256": None,
            "input_status": suite["input_status"],
            "capability_status": capability,
            "run_status": "NOT_RUN",
            "solution_status": "NOT_APPLICABLE",
            "proof_status": "NOT_APPLICABLE",
            "termination_reason": termination_reason,
            "resources": {},
            "metrics": {
                "source_audit": audit_artifact,
                "executable_source": False,
                "status_only_reason": termination_reason,
            },
            "artifacts": {"source_audit": audit_artifact},
        }
        validate_run_record(record)
        records.append(record)
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--audit-artifact", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    records = build_records(args.benchmark, args.audit_artifact)
    content = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records)
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != content:
            print(f"SOURCE_STATUS_STALE: {args.output}")
            return 1
        print(f"SOURCE_STATUS_OK: {len(records)} records")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
