#!/usr/bin/env python3
"""Audit the public 3DBPPsi source without copying the dataset into the repo."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path


AUDIT_DATE = "2026-09-01"
DATASET_DOI = "10.57760/sciencedb.42066"
DATASET_URL = "https://www.scidb.cn/detail?dataSetId=d290275c2f3142ed967acc479723cbd1"
URL_API = "https://www.scidb.cn/api/sdb-filetree-service/getAllUrl?dataSetId=d290275c2f3142ed967acc479723cbd1&type=&version=V1&global=CN"

ITEM_COLUMNS = [
    "id_item",
    "length",
    "width",
    "height",
    "weight",
    "nesting_height",
    "stackability_code",
    "forced_orientation",
    "max_stackability",
]
VEHICLE_COLUMNS = [
    "id_truck",
    "length",
    "width",
    "height",
    "max_weight",
    "max_weight_stack",
    "cost",
    "max_density",
]

# The ScienceDB file tree exposes these stable file IDs. The file-tree API does
# not publish checksums; these are locally observed hashes of bytes downloaded
# from the corresponding URLs on 2026-09-01. They are rechecked by this script
# when the source directory is available.
FILES = {
    "datasetA/items.csv": ("387adf6ee8f40df8a160588b2f0a54c4", "092f1aa3bce788c0a0fce855461889bc5847f6bd6e74dbcb1b4d572f25b3ade4"),
    "datasetA/vehicles.csv": ("c34381b469843808b4185182c4494c5c", "05173324c721dbe16c56cf3787d2980bb02ec53f6e65d087a2cfcb59ef9d322a"),
    "datasetB/items.csv": ("5a183b555671545f7f1d6ca5d14cddfa", "befa8e20387e9a692f6afdf27a5185def02e27c4842c5b645c8a63a0ad3734c0"),
    "datasetB/vehicles.csv": ("c2cf8b82149c579a5c9cbc94db58a637", "9ace9b95943dfe0956655f59b5dae11df7d19b8a0890bc9ca0dc069b2048dd0b"),
    "datasetC/items.csv": ("c522e74c904071a2b9a06cfa21aec2de", "772301d93c6d0f5286be4e885dfcf79263145f96e6ff94697b714db655595024"),
    "datasetC/vehicles.csv": ("717a636331f7f072c114e6cb9d40729e", "6c1d53dad0e3931c1c6c612c4d59db8539e1d0df41472284e702a30355d5a506"),
    "datasetD/items.csv": ("5ce2dbf8f0129dfd88f7513c9f97223e", "ef1fea209f0ad14201ff55ca1b799d0ec21de04f7fdd72c9178b06d90e6ff740"),
    "datasetD/vehicles.csv": ("c44ad662a13eb9813e5a121f304466a6", "71de8dae95e326239c86e8d668e83a94761c11622ceb94621393a120757461af"),
    "datasetE/items.csv": ("129c8e3829163d4abbd9080a2e2bc3ca", "36449b1d28056c9a9fb61dc81095ad87b4d4eb890155788882173e7df571df92"),
    "datasetE/vehicles.csv": ("09aa8960d1f3da109d12a3c30a512a85", "ca740b96a1688b0e2ce67a5825b6051e3450dae91deb4284d90a62b6b921725c"),
    "datasetF/items.csv": ("ead333ac97e2cfa71c9a7c6663c71e13", "817a978be5dacbb4b0ae3864b2d611c7d06511e377b132e7e35793ada43bfad8"),
    "datasetF/vehicles.csv": ("098f908c943384d670414c4ea4545ff9", "05173324c721dbe16c56cf3787d2980bb02ec53f6e65d087a2cfcb59ef9d322a"),
    "datasetG/items.csv": ("a9fc1f222085ad1822736830b6900e18", "3e538ad6c60a87e45b19843fa8466a1a9dfd435516afba5fff12453b896fa2ff"),
    "datasetG/vehicles.csv": ("ddce0ac34809de6574ccb14973101732", "3dc990d55b5c6dcc3bbdcab443da64f779f3939073ed9d397762f74f72ba7901"),
    "datasetH/items.csv": ("3436f6fb0ac7b13dd09b2efadbeff1e1", "09432f14f733de8d3b6fe20e470ef021936009fc4e17da69183b19060f1b14d0"),
    "datasetH/vehicles.csv": ("0d93c3cfb30405ce8c4e11b877ed5af7", "3dc990d55b5c6dcc3bbdcab443da64f779f3939073ed9d397762f74f72ba7901"),
    "datasetI/items.csv": ("1c56c9ba3baeee77ad8e3e40bd19aee0", "da99bb507ed9c8ef526b435d7322ec750ea083249e127a79d54225fdf2c491db"),
    "datasetI/vehicles.csv": ("d06411761848c9b615e84550297fb08f", "b9ac4f76f651c78eac65f6bceed2199f73246da707a32244a106692920a4dc50"),
    "datasetJ/items.csv": ("3758803ddee50e09ef8e96a0f14433eb", "9697b971f1e9a513aac16226bb44ffa826b8779bf6525af23cd3b169b6086189"),
    "datasetJ/vehicles.csv": ("3f5248385c69c84589b053c4da27727f", "3a9c8f00e29ed595542faf37e25548b1352181da36135f34c6f469fabaeb6d95"),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_number(value: str, field: str, issues: list[str], *, nonnegative: bool = False) -> float | None:
    try:
        number = float(value)
    except ValueError:
        issues.append(f"{field} is not numeric: {value!r}")
        return None
    if nonnegative and number < 0:
        issues.append(f"{field} is negative: {number}")
    elif not nonnegative and number <= 0:
        issues.append(f"{field} is not positive: {number}")
    return number


def parse_csv(path: Path, expected_columns: list[str], kind: str) -> dict:
    issues: list[str] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        if columns != expected_columns:
            issues.append(f"columns mismatch: {columns!r}")
        rows = list(reader)
    ids = [row.get(expected_columns[0], "") for row in rows]
    if any(not value for value in ids):
        issues.append("empty identifier")
    if len(ids) != len(set(ids)):
        issues.append("duplicate identifiers")
    if kind == "items":
        for index, row in enumerate(rows, start=2):
            for field in ("length", "width", "height"):
                parse_number(row.get(field, ""), f"row {index} {field}", issues)
            for field in ("weight", "nesting_height"):
                parse_number(row.get(field, ""), f"row {index} {field}", issues, nonnegative=True)
            parse_number(row.get("stackability_code", ""), f"row {index} stackability_code", issues, nonnegative=True)
            parse_number(row.get("max_stackability", ""), f"row {index} max_stackability", issues)
            if not row.get("forced_orientation", "").strip():
                issues.append(f"row {index} forced_orientation is empty")
    else:
        for index, row in enumerate(rows, start=2):
            for field in ("length", "width", "height", "max_weight", "max_weight_stack", "cost", "max_density"):
                parse_number(row.get(field, ""), f"row {index} {field}", issues)
    return {
        "file": path.as_posix(),
        "kind": kind,
        "columns": columns,
        "row_count": len(rows),
        "unique_id_count": len(set(ids)),
        "parse_status": "PASS" if not issues else "FAIL",
        "parse_errors": issues[:20],
        "parse_error_count": len(issues),
    }


def file_record(root: Path, relative: str, metadata: tuple[str, str]) -> dict:
    file_id, observed_hash = metadata
    path = root / relative.replace("/", "__")
    present = path.exists()
    actual_hash = sha256(path) if present else None
    return {
        "path": relative,
        "file_id": file_id,
        "download_url": f"https://download.scidb.cn/download?fileId={file_id}&path=/V1/{relative}&fileName={Path(relative).name}",
        "observed_sha256": observed_hash,
        "actual_sha256": actual_hash,
        "present": present,
        "hash_status": "PASS" if present and actual_hash == observed_hash else "UNVERIFIED",
    }


def build_audit(root: Path) -> dict:
    records = [file_record(root, relative, metadata) for relative, metadata in sorted(FILES.items())]
    parse_records = []
    dataset_counts = {}
    for dataset in "ABCDEFGHIJ":
        item_rel = f"dataset{dataset}/items.csv"
        vehicle_rel = f"dataset{dataset}/vehicles.csv"
        item_path = root / item_rel.replace("/", "__")
        vehicle_path = root / vehicle_rel.replace("/", "__")
        item = parse_csv(item_path, ITEM_COLUMNS, "items") if item_path.exists() else {"file": item_rel, "parse_status": "FAIL", "parse_errors": ["missing file"]}
        vehicle = parse_csv(vehicle_path, VEHICLE_COLUMNS, "vehicles") if vehicle_path.exists() else {"file": vehicle_rel, "parse_status": "FAIL", "parse_errors": ["missing file"]}
        parse_records.extend([item, vehicle])
        dataset_counts[f"dataset{dataset}"] = {
            "item_rows": item.get("row_count", 0),
            "vehicle_rows": vehicle.get("row_count", 0),
        }
    hashes_verified = all(record["present"] and record["hash_status"] == "PASS" for record in records)
    parsed = all(record.get("parse_status") == "PASS" for record in parse_records)
    return {
        "record_kind": "B34_SOURCE_AUDIT",
        "audit_date": AUDIT_DATE,
        "dataset": {
            "name": "3D Bin Packing Problem with Stackable Items (3DBPPsi)",
            "doi": DATASET_DOI,
            "version": "V1",
            "url": DATASET_URL,
            "license": "CC-BY-4.0",
            "file_tree_api": URL_API,
            "source_file_count": 20,
        },
        "source_verification": {
            "downloaded_source_dir": "external temporary directory (not committed)",
            "file_count": len(records),
            "all_files_present": all(record["present"] for record in records),
            "all_hashes_match_local_manifest": hashes_verified,
            "all_csv_parse": parsed,
        },
        "files": records,
        "dataset_counts": dataset_counts,
        "decision": {
            "input_status": "SOURCE_INCOMPLETE",
            "run_status": "NOT_RUN",
            "reason": "The public CSV source is structurally auditable, but canonical stack master, independent hard validator and exact-small calibration are pending.",
            "not_mpV_substitute": True,
            "published_optimum": "not established by the source metadata; report incumbent and bounds only",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    audit = json.dumps(build_audit(args.source_dir), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != audit:
            print(f"B34_SOURCE_AUDIT_STALE: {args.output}", file=sys.stderr)
            return 1
        print(f"B34_SOURCE_AUDIT_OK: {args.output}")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(audit, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
