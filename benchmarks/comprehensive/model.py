from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = Path(__file__).resolve().parent
RESULTS_DIR = ROOT / "results" / "comprehensive"

PROTOCOL_VERSION = "benchmark-protocol/3"
INPUT_STATUSES = {"VALID", "SOURCE_INVALID", "SOURCE_INCOMPLETE"}
CAPABILITY_STATUSES = {
    "SUPPORTED_NATIVE",
    "SUPPORTED_COMPOSED",
    "PROJECTION_ONLY",
    "NOT_SUPPORTED",
    "ADAPTER_MISSING",
}
RUN_STATUSES = {"COMPLETED", "TIME_LIMIT", "MEMORY_LIMIT", "CANCELLED", "ERROR", "NOT_RUN"}
SOLUTION_STATUSES = {
    "VALID_COMPLETE",
    "VALID_PARTIAL",
    "INVALID_CERTIFICATE",
    "CONSTRAINT_VIOLATION",
    "NO_SOLUTION",
    "NOT_APPLICABLE",
}
PROOF_STATUSES = {
    "PROVEN_OPTIMAL",
    "PROVEN_INFEASIBLE",
    "INCUMBENT_WITH_BOUND",
    "FEASIBLE",
    "UNKNOWN",
    "NOT_APPLICABLE",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_catalogs() -> tuple[dict[str, Any], dict[str, Any]]:
    suites = load_json(CATALOG_DIR / "suites.json")
    implementations = load_json(CATALOG_DIR / "implementations.json")
    validate_catalogs(suites, implementations)
    return suites, implementations


def validate_catalogs(suites: dict[str, Any], implementations: dict[str, Any]) -> None:
    for name, catalog in (("suites", suites), ("implementations", implementations)):
        if catalog.get("schema_version") != 1 or catalog.get("protocol_version") != PROTOCOL_VERSION:
            raise ValueError(f"{name} catalog version mismatch")

    profiles = suites.get("capability_profiles", [])
    if len(profiles) != len(set(profiles)) or not profiles:
        raise ValueError("capability profiles must be unique and non-empty")

    suite_rows = suites.get("suites", [])
    expected_ids = [f"B{index:02d}" for index in range(1, 33)]
    suite_ids = [suite.get("id") for suite in suite_rows]
    if sorted(suite_ids) != expected_ids or len(suite_ids) != len(set(suite_ids)):
        raise ValueError("suite catalog must contain B01-B32 exactly once")
    for suite in suite_rows:
        if suite.get("input_status") not in INPUT_STATUSES:
            raise ValueError(f"invalid input status: {suite.get('id')}")
        coverage = suite.get("capability_by_profile", {})
        if set(coverage) != set(profiles):
            raise ValueError(f"profile coverage is incomplete: {suite.get('id')}")
        invalid = set(coverage.values()) - CAPABILITY_STATUSES
        if invalid:
            raise ValueError(f"invalid capability status in {suite.get('id')}: {sorted(invalid)}")

    implementation_rows = implementations.get("implementations", [])
    implementation_ids = [implementation.get("id") for implementation in implementation_rows]
    if len(implementation_ids) != len(set(implementation_ids)) or not implementation_ids:
        raise ValueError("implementation ids must be unique and non-empty")
    used_profiles = {implementation.get("capability_profile") for implementation in implementation_rows}
    if used_profiles != set(profiles):
        raise ValueError("every capability profile must have at least one implementation")
    for implementation in implementation_rows:
        for field in ("id", "library", "algorithm", "technology", "version", "capability_profile"):
            if not implementation.get(field):
                raise ValueError(f"implementation field is empty: {implementation.get('id')}/{field}")
        if implementation.get("default_track") not in {"NATIVE", "COMPOSED", "EXACT_MODEL"}:
            raise ValueError(f"invalid default track: {implementation.get('id')}")
        if not isinstance(implementation.get("known_issues"), list):
            raise ValueError(f"known_issues must be a list: {implementation.get('id')}")


def comparison_track(implementation: dict[str, Any], capability_status: str) -> str:
    if capability_status == "NOT_SUPPORTED":
        return "NOT_APPLICABLE"
    if implementation["default_track"] == "EXACT_MODEL":
        return "EXACT_MODEL"
    if capability_status in {"SUPPORTED_COMPOSED", "PROJECTION_ONLY"}:
        return "COMPOSED"
    return implementation["default_track"]


def status_reason(suite: dict[str, Any], implementation: dict[str, Any], capability_status: str) -> str:
    reasons: list[str] = []
    if suite["input_status"] != "VALID":
        reasons.append(f"input={suite['input_status']}")
    reasons.append(f"capability={capability_status}")
    if implementation["known_issues"]:
        reasons.append("known_issues=" + " | ".join(implementation["known_issues"]))
    return "; ".join(reasons)


def build_plan_rows(suites: dict[str, Any], implementations: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for suite in sorted(suites["suites"], key=lambda value: value["id"]):
        for implementation in sorted(implementations["implementations"], key=lambda value: value["id"]):
            profile = implementation["capability_profile"]
            capability_status = suite["capability_by_profile"][profile]
            if suite["input_status"] != "VALID":
                termination_reason = "SOURCE_PENDING"
            elif capability_status == "NOT_SUPPORTED":
                termination_reason = "NOT_SUPPORTED"
            elif capability_status == "ADAPTER_MISSING":
                termination_reason = "ADAPTER_MISSING"
            else:
                termination_reason = "PLANNED"
            rows.append(
                {
                    "schema_version": 1,
                    "protocol_version": PROTOCOL_VERSION,
                    "benchmark_id": suite["id"],
                    "benchmark_name": suite["name"],
                    "category": suite["category"],
                    "problem_family": suite["problem_family"],
                    "primary_metric": suite["primary_metric"],
                    "ranking_kind": suite["ranking_kind"],
                    "implementation_id": implementation["id"],
                    "library": implementation["library"],
                    "algorithm": implementation["algorithm"],
                    "technology": implementation["technology"],
                    "implementation_version": implementation["version"],
                    "input_status": suite["input_status"],
                    "capability_status": capability_status,
                    "comparison_track": comparison_track(implementation, capability_status),
                    "problem_scope": (
                        "GEOMETRY_PROJECTION"
                        if capability_status == "PROJECTION_ONLY"
                        else "NOT_APPLICABLE"
                        if capability_status == "NOT_SUPPORTED"
                        else "FULL_PROBLEM"
                    ),
                    "run_status": "NOT_RUN",
                    "solution_status": "NOT_APPLICABLE",
                    "proof_status": "NOT_APPLICABLE",
                    "termination_reason": termination_reason,
                    "status_reason": status_reason(suite, implementation, capability_status),
                }
            )
    return rows


def validate_plan_rows(rows: list[dict[str, Any]], suite_count: int, implementation_count: int) -> None:
    if len(rows) != suite_count * implementation_count:
        raise ValueError("plan does not contain the full suite x implementation matrix")
    keys = [(row["benchmark_id"], row["implementation_id"]) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("plan contains duplicate suite x implementation cells")
    for row in rows:
        if row["input_status"] not in INPUT_STATUSES:
            raise ValueError(f"invalid plan input status: {row}")
        if row["capability_status"] not in CAPABILITY_STATUSES:
            raise ValueError(f"invalid plan capability status: {row}")
        if row["run_status"] != "NOT_RUN" or row["solution_status"] != "NOT_APPLICABLE":
            raise ValueError("unexecuted plan cells must not claim a solution")


def plan_jsonl(rows: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)


def coverage_csv(rows: list[dict[str, Any]]) -> str:
    fields = [
        "benchmark_id",
        "benchmark_name",
        "category",
        "problem_family",
        "primary_metric",
        "implementation_id",
        "library",
        "algorithm",
        "technology",
        "implementation_version",
        "input_status",
        "capability_status",
        "comparison_track",
        "problem_scope",
        "run_status",
        "solution_status",
        "proof_status",
        "termination_reason",
        "status_reason",
    ]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row[field] for field in fields})
    return output.getvalue()


def plan_summary(rows: list[dict[str, Any]], suite_catalog: dict[str, Any], implementation_catalog: dict[str, Any]) -> dict[str, Any]:
    input_counts = Counter(row["input_status"] for row in rows)
    capability_counts = Counter(row["capability_status"] for row in rows)
    track_counts = Counter(row["comparison_track"] for row in rows)
    return {
        "schema_version": 1,
        "protocol_version": PROTOCOL_VERSION,
        "record_kind": "SUITE_IMPLEMENTATION_PLAN_SUMMARY",
        "suite_count": len(suite_catalog["suites"]),
        "implementation_count": len(implementation_catalog["implementations"]),
        "planned_cells": len(rows),
        "executed_cells": 0,
        "input_status_counts": dict(sorted(input_counts.items())),
        "capability_status_counts": dict(sorted(capability_counts.items())),
        "comparison_track_counts": dict(sorted(track_counts.items())),
        "catalog_sha256": {
            "benchmarks/comprehensive/suites.json": sha256_text(canonical_json(suite_catalog)),
            "benchmarks/comprehensive/implementations.json": sha256_text(canonical_json(implementation_catalog)),
        },
        "warning": "This is a deterministic execution plan, not benchmark results.",
    }


def validate_run_record(record: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "protocol_version",
        "run_id",
        "benchmark_id",
        "problem_variant",
        "instance_id",
        "implementation_id",
        "algorithm",
        "adapter",
        "comparison_track",
        "problem_scope",
        "budget",
        "item_order",
        "bin_order",
        "seed",
        "repetition",
        "input_sha256",
        "input_status",
        "capability_status",
        "run_status",
        "solution_status",
        "proof_status",
        "termination_reason",
        "resources",
        "metrics",
        "artifacts",
    }
    missing = required - set(record)
    if missing:
        raise ValueError(f"run record is missing fields: {sorted(missing)}")
    extra = set(record) - required
    if extra:
        raise ValueError(f"run record has unsupported fields: {sorted(extra)}")
    if record["schema_version"] != 1 or record["protocol_version"] != PROTOCOL_VERSION:
        raise ValueError("run record version mismatch")
    if record["input_status"] not in INPUT_STATUSES:
        raise ValueError("invalid run input status")
    if record["capability_status"] not in CAPABILITY_STATUSES:
        raise ValueError("invalid run capability status")
    if record["run_status"] not in RUN_STATUSES:
        raise ValueError("invalid run status")
    if record["solution_status"] not in SOLUTION_STATUSES:
        raise ValueError("invalid solution status")
    if record["proof_status"] not in PROOF_STATUSES:
        raise ValueError("invalid proof status")
    if record["comparison_track"] not in {"NATIVE", "COMPOSED", "EXACT_MODEL", "NOT_APPLICABLE"}:
        raise ValueError("invalid comparison track")
    if record["problem_scope"] not in {"FULL_PROBLEM", "GEOMETRY_PROJECTION", "NOT_APPLICABLE"}:
        raise ValueError("invalid problem scope")
    budget = record["budget"]
    if not isinstance(budget, dict) or set(budget) != {"time_limit_s", "memory_limit_bytes", "thread_limit"}:
        raise ValueError("invalid budget object")
    if budget["time_limit_s"] is not None and budget["time_limit_s"] <= 0:
        raise ValueError("time limit must be positive")
    if budget["memory_limit_bytes"] is not None and budget["memory_limit_bytes"] <= 0:
        raise ValueError("memory limit must be positive")
    if budget["thread_limit"] is not None and budget["thread_limit"] <= 0:
        raise ValueError("thread limit must be positive")
    if record["run_status"] == "NOT_RUN" and record["solution_status"] != "NOT_APPLICABLE":
        raise ValueError("NOT_RUN cannot claim a solution")
    if record["capability_status"] == "NOT_SUPPORTED" and record["solution_status"] != "NOT_APPLICABLE":
        raise ValueError("NOT_SUPPORTED cannot claim a solution")
    if record["input_status"] != "VALID" and record["run_status"] != "NOT_RUN":
        raise ValueError("invalid or incomplete sources cannot be executed")
    if record["run_status"] != "NOT_RUN":
        input_hash = record["input_sha256"]
        if not isinstance(input_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", input_hash):
            raise ValueError("executed runs require an input SHA-256")
