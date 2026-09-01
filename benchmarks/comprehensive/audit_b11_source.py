#!/usr/bin/env python3
"""Audit the repository-owned B11 open-dimension calibration fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "benchmarks" / "data" / "comprehensive" / "b11-open-dimension" / "source.json"
FORK = ROOT / ".cache" / "packingsolver-fork"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit() -> dict:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    errors: list[str] = []
    if payload.get("benchmark_id") != "B11":
        errors.append("benchmark_id is not B11")
    if payload.get("source_scope") != "REPOSITORY_FIXTURE_DERIVED_FROM_FORK_TESTS":
        errors.append("source scope is not explicit")
    actual_commit = __import__("subprocess").check_output(["git", "-C", str(FORK), "rev-parse", "HEAD"], text=True).strip()
    if actual_commit != payload.get("source_commit"):
        errors.append(f"fork commit mismatch: {actual_commit}")
    files = payload.get("upstream_source_sha256", {})
    for relative, expected in files.items():
        case, filename = relative.split("/", 1)
        path = FORK / "data" / "box" / "tests" / f"open_dimension_x_4_different_items_{case}" / filename
        if not path.is_file():
            errors.append(f"missing upstream file: {relative}")
        elif sha256(path) != expected:
            errors.append(f"upstream hash mismatch: {relative}")
    cases = payload.get("cases", [])
    ids: set[str] = set()
    for case in cases:
        case_id = case.get("id")
        if case_id in ids:
            errors.append(f"duplicate case id: {case_id}")
        ids.add(case_id)
        if case.get("objective") not in (None, payload.get("objective")):
            errors.append(f"case objective mismatch: {case_id}")
        bin_spec = case.get("bin", {})
        if len(bin_spec.get("size", [])) != 3 or any(float(value) <= 0 for value in bin_spec.get("size", [])):
            errors.append(f"invalid bin size: {case_id}")
        item_ids: set[str] = set()
        for item in case.get("items", []):
            item_id = item.get("id")
            if item_id in item_ids:
                errors.append(f"duplicate item id {case_id}/{item_id}")
            item_ids.add(item_id)
            if len(item.get("size", [])) != 3 or any(float(value) <= 0 for value in item.get("size", [])):
                errors.append(f"invalid item size: {case_id}/{item_id}")
            if item.get("orientation") != "XYZ":
                errors.append(f"unexpected orientation: {case_id}/{item_id}")
    return {
        "schema_version": 1,
        "benchmark_id": "B11",
        "source_scope": payload.get("source_scope"),
        "source_repository": payload.get("source_repository"),
        "source_commit": payload.get("source_commit"),
        "case_count": len(cases),
        "item_counts": {case["id"]: len(case.get("items", [])) for case in cases},
        "upstream_file_count": len(files),
        "errors": errors,
        "decision": {
            "input_status": "VALID" if not errors else "SOURCE_INVALID",
            "run_status": "NOT_RUN",
            "termination_reason": "CALIBRATION_FIXTURE_ONLY",
            "warning": "This is a fork-owned conformance/calibration fixture, not an independent public B11 distribution.",
        },
        "source_sha256": sha256(SOURCE),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = audit()
    content = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != content:
            print(f"B11_SOURCE_AUDIT_STALE: {args.output}")
            return 1
        print("B11_SOURCE_AUDIT_OK")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(args.output)
    return 0 if not result["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
