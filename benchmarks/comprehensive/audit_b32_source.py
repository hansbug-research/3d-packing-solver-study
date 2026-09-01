#!/usr/bin/env python3
"""Audit the repository-owned B32 online/incremental arrival fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "benchmarks" / "data" / "comprehensive" / "b32-online-fixture.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def audit() -> dict:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("record_kind") != "B32_ONLINE_PACKING_FIXTURE":
        raise ValueError("B32 fixture schema mismatch")
    policies = data.get("policies", [])
    if [row.get("id") for row in policies] != ["NO_REORDER", "LOOKAHEAD_2", "OFFLINE_REBUILD"]:
        raise ValueError("B32 policy order changed")
    cases = data.get("cases", [])
    if [case.get("id") for case in cases] != ["B32/ADVERSARIAL_ORDER", "B32/STACKED_ORDER"]:
        raise ValueError("B32 case order or identifiers changed")
    case_records = []
    for case in cases:
        items = case.get("items", [])
        if len(items) < 4 or [item.get("arrival") for item in items] != list(range(len(items))):
            raise ValueError(f"B32 arrival trace invalid: {case.get('id')}")
        ids = [item.get("id") for item in items]
        if len(ids) != len(set(ids)):
            raise ValueError(f"B32 item ids are not unique: {case.get('id')}")
        container = case.get("container", {})
        if len(container.get("size", [])) != 3 or any(float(value) <= 0 for value in container["size"]):
            raise ValueError(f"B32 container geometry invalid: {case.get('id')}")
        for item in items:
            if len(item.get("size", [])) != 3 or any(float(value) <= 0 for value in item["size"]):
                raise ValueError(f"B32 item geometry invalid: {case.get('id')}/{item.get('id')}")
            if any(float(item["size"][axis]) > float(container["size"][axis]) for axis in range(3)):
                # All six rotations are allowed; at least one dimension order
                # must fit the container.
                if not any(
                    all(float(item["size"][index]) <= float(container["size"][axis]) for axis, index in enumerate(order))
                    for order in ((0, 1, 2), (0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0))
                ):
                    raise ValueError(f"B32 item cannot fit in container: {case.get('id')}/{item.get('id')}")
        case_records.append({
            "id": case["id"],
            "items": len(items),
            "required_items": len(items),
            "container_size": container["size"],
            "deadline_s": case["deadline_s"],
        })
    return {
        "schema_version": 1,
        "record_kind": "B32_SOURCE_AUDIT",
        "benchmark_id": "B32",
        "input_status": "VALID",
        "run_status": "NOT_RUN",
        "fixture": str(FIXTURE.relative_to(ROOT)),
        "fixture_sha256": sha256(FIXTURE),
        "license": data["source"]["license"],
        "policies": policies,
        "cases": case_records,
        "semantic_note": data["source"]["semantic_note"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = json.dumps(audit(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != content:
            print(f"B32_SOURCE_AUDIT_STALE: {args.output}")
            return 1
        print("B32_SOURCE_AUDIT_OK")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
