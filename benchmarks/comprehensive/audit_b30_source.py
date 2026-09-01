#!/usr/bin/env python3
"""Audit the repository-owned, two-product BAYTP shelf-sequence fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "benchmarks" / "data" / "comprehensive" / "b30-baytp-fixture.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def audit() -> dict[str, Any]:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("record_kind") != "B30_BAYTP_SHELF_SEQUENCE_FIXTURE":
        raise ValueError("B30 fixture schema mismatch")
    source = data.get("source", {})
    case = data.get("case", {})
    if case.get("id") != "B30/SHELF_SEQUENCE":
        raise ValueError("B30 case id mismatch")
    if len(case.get("items", [])) != 2 or len(case.get("shelves", [])) != 2:
        raise ValueError("B30 fixture must contain two products and two shelves")
    if case["items"][0]["size"] != case["items"][1]["size"] or case["items"][0]["size"] != [734, 536, 402]:
        raise ValueError("B30 product dimensions are not the audited source row")
    if case["bay"]["size"] != [1200, 2400, 650] or [s["top_y"] for s in case["shelves"]] != [0, 500]:
        raise ValueError("B30 bay or shelf geometry mismatch")
    expected = source.get("source_sha256", {})
    if set(expected) != {"products.txt", "shelves.txt", "baytp1.txt"}:
        raise ValueError("B30 source hash set mismatch")
    return {
        "schema_version": 1,
        "record_kind": "B30_BAYTP_SOURCE_AUDIT",
        "benchmark_id": "B30",
        "input_status": "VALID",
        "run_status": "NOT_RUN",
        "fixture": str(FIXTURE.relative_to(ROOT)),
        "fixture_sha256": sha256(FIXTURE),
        "source": source,
        "case": {
            "id": case["id"],
            "items": len(case["items"]),
            "required_items": len(case["items"]),
            "shelves": len(case["shelves"]),
            "bay_size": case["bay"]["size"],
            "source_product_family": case["items"][0]["source_family"],
        },
        "semantic_note": "Small source-derived calibration only; it does not claim the complete 6000-product BAYTP corpus has been executed.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = json.dumps(audit(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != content:
            print(f"B30_SOURCE_AUDIT_STALE: {args.output}")
            return 1
        print("B30_SOURCE_AUDIT_OK")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
