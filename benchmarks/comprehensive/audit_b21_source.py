#!/usr/bin/env python3
"""Audit the pinned ESICUP VRPTW-CLP source before any B21 execution.

The archive is useful, but its README count and record shape must be checked
before a converter is allowed to infer missing orientation flags.  This audit
keeps the raw files external and records every file hash and malformed row.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = ROOT / ".cache" / "esicup-datasets" / "misc" / "vrptw_clp"
OUTPUT = ROOT / "results" / "comprehensive" / "b21-source-audit.json"
SOURCE_COMMIT = "154a8f006a8e72f65d734f2d1e36777f678f31f8"
GROUPS = ("GI_I1", "GI_I2", "GII_I1", "GII_I2")
README_DECLARED_INSTANCES = 46


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def nonempty_lines(path: Path) -> list[tuple[int, str, list[str]]]:
    rows: list[tuple[int, str, list[str]]] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        text = raw.strip()
        if text:
            rows.append((number, text, text.split()))
    return rows


def audit_instance(path: Path) -> dict[str, Any]:
    rows = nonempty_lines(path)
    anomalies: list[dict[str, Any]] = []
    if len(rows) < 3:
        anomalies.append({"kind": "TOO_SHORT", "line_count": len(rows)})
        return {"path": str(path.relative_to(ROOT)), "sha256": sha256(path), "anomalies": anomalies}

    if len(rows[0][2]) != 3:
        anomalies.append({"kind": "BAD_HEADER", "line": rows[0][0], "fields": len(rows[0][2])})
    if len(rows[1][2]) != 3:
        anomalies.append({"kind": "BAD_CONTAINER", "line": rows[1][0], "fields": len(rows[1][2])})

    # The format reserves exactly 26 customer rows.  Do not identify the
    # boundary by field count: a truncated customer row can otherwise make all
    # following rows look like malformed item records.
    customer_rows: list[dict[str, Any]] = []
    for number, text, fields in rows[2:28]:
        customer_rows.append({"line": number, "customer": fields[0] if fields else None, "raw": text, "field_count": len(fields)})
    if len(customer_rows) != 26:
        anomalies.append({"kind": "CUSTOMER_ROW_COUNT", "observed": len(customer_rows), "expected": 26})
    for row in customer_rows:
        if row["field_count"] != 6:
            anomalies.append({"kind": "MALFORMED_CUSTOMER_ROW", "line": row["line"], "field_count": row["field_count"], "raw": row["raw"]})

    item_rows: list[dict[str, Any]] = []
    malformed: list[dict[str, Any]] = []
    for number, text, fields in rows[28:]:
        if len(fields) != 9:
            malformed.append({"line": number, "field_count": len(fields), "raw": text})
            continue
        try:
            values = [int(value) for value in fields]
        except ValueError:
            malformed.append({"line": number, "field_count": len(fields), "raw": text, "kind": "NON_INTEGER"})
            continue
        customer, box_type, maximum, max_flag, medium, medium_flag, minimum, min_flag, copies = values
        item_rows.append({
            "line": number,
            "customer": customer,
            "box_type": box_type,
            "dimensions": [maximum, medium, minimum],
            "height_flags": [max_flag, medium_flag, min_flag],
            "copies": copies,
        })
    if malformed:
        anomalies.append({"kind": "MALFORMED_ITEM_ROWS", "count": len(malformed), "rows": malformed})
    if any(row["copies"] < 0 or any(value <= 0 for value in row["dimensions"]) for row in item_rows):
        anomalies.append({"kind": "INVALID_ITEM_VALUES"})
    if any(flag not in (0, 1, 2) for row in item_rows for flag in row["height_flags"]):
        anomalies.append({"kind": "INVALID_HEIGHT_FLAG"})

    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": sha256(path),
        "header": rows[0][2],
        "container": rows[1][2],
        "customer_rows": len(customer_rows),
        "item_rows": len(item_rows),
        "malformed_item_rows": malformed,
        "parsed_copies": sum(row["copies"] for row in item_rows),
        "anomalies": anomalies,
    }


def audit(source_root: Path) -> dict[str, Any]:
    files: list[Path] = []
    group_summary: dict[str, dict[str, Any]] = {}
    for group in GROUPS:
        group_root = source_root / group
        instances = sorted(path for path in group_root.glob("*.txt") if path.name != "Info.txt")
        files.extend(instances)
        group_summary[group] = {
            "instance_files": len(instances),
            "info_sha256": sha256(group_root / "Info.txt") if (group_root / "Info.txt").exists() else None,
        }
    instance_audits = [audit_instance(path) for path in files]
    malformed_files = [row["path"] for row in instance_audits if row["anomalies"]]
    readme = source_root / "readme.txt"
    anomaly_kinds: dict[str, int] = {}
    for row in instance_audits:
        for anomaly in row["anomalies"]:
            kind = str(anomaly["kind"])
            anomaly_kinds[kind] = anomaly_kinds.get(kind, 0) + 1
    source_valid = len(files) == README_DECLARED_INSTANCES and not malformed_files
    return {
        "schema_version": 1,
        "record_kind": "B21_SOURCE_AUDIT",
        "benchmark_id": "B21",
        "source_repository": "ESICUP/datasets",
        "source_commit": SOURCE_COMMIT,
        "source_root": str(source_root.relative_to(ROOT)),
        "readme_sha256": sha256(readme) if readme.exists() else None,
        "readme_declared_instances": README_DECLARED_INSTANCES,
        "observed_instance_files": len(files),
        "group_summary": group_summary,
        "anomaly_counts": dict(sorted(anomaly_kinds.items())),
        "instances": instance_audits,
        "decision": {
            "input_status": "VALID" if source_valid else "SOURCE_INVALID",
            "run_status": "NOT_RUN",
            "termination_reason": None if source_valid else "SOURCE_PENDING",
            "reason": (
                "The pinned corpus has a reproducible format and count mismatch; "
                "a converter must not infer missing height flags from repeated values."
                if not source_valid else "No source anomalies detected."
            ),
            "forbidden_substitutions": [
                "silently adding the missing height flag",
                "dropping malformed demand rows and calling the result B21",
                "using a repaired projection as the original integrated VRPTW-CLP problem",
            ],
            "next_action": "Ask upstream for a corrected archive or create a separately named, explicitly source-repaired variant with a diff and validator proof.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=SOURCE_ROOT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = json.dumps(audit(args.source_root.resolve()), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != result:
            print(f"B21_SOURCE_AUDIT_STALE: {args.output}")
            return 1
        print("B21_SOURCE_AUDIT_OK")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
