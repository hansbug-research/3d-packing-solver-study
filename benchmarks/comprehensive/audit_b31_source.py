#!/usr/bin/env python3
"""Audit the repository-owned B31 mixed-SKU pallet fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "benchmarks" / "data" / "comprehensive" / "b31-mixed-sku-fixture.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def audit() -> dict[str, Any]:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("record_kind") != "B31_MIXED_SKU_PALLET_FIXTURE":
        raise ValueError("B31 fixture schema mismatch")
    cases = data.get("cases", [])
    if [case.get("id") for case in cases] != ["B31/FLAT_MIXED", "B31/STACKABLE", "B31/WEIGHT_INFEASIBLE"]:
        raise ValueError("B31 case order or identifiers changed")
    for case in cases:
        if len(case.get("items", [])) < 3:
            raise ValueError(f"B31 case too small: {case.get('id')}")
        pallet = case.get("pallet", {})
        if len(pallet.get("size", [])) != 3 or any(float(value) <= 0 for value in pallet["size"]):
            raise ValueError(f"B31 pallet geometry invalid: {case.get('id')}")
        if float(case.get("rules", {}).get("max_layers", 0)) < 1:
            raise ValueError(f"B31 max_layers invalid: {case.get('id')}")
        ids = [item.get("id") for item in case["items"]]
        if len(ids) != len(set(ids)):
            raise ValueError(f"B31 item ids are not unique: {case.get('id')}")
    return {
        "schema_version": 1,
        "record_kind": "B31_SOURCE_AUDIT",
        "benchmark_id": "B31",
        "input_status": "VALID",
        "run_status": "NOT_RUN",
        "fixture": str(FIXTURE.relative_to(ROOT)),
        "fixture_sha256": sha256(FIXTURE),
        "license": data["source"]["license"],
        "cases": [
            {
                "id": case["id"],
                "items": len(case["items"]),
                "required_items": len(case["items"]),
                "pallet_size": case["pallet"]["size"],
                "max_weight": case["pallet"]["max_weight"],
                "max_layers": case["rules"]["max_layers"],
            }
            for case in cases
        ],
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
            print(f"B31_SOURCE_AUDIT_STALE: {args.output}")
            return 1
        print("B31_SOURCE_AUDIT_OK")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
