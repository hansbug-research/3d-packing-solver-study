#!/usr/bin/env python3
"""Audit the public Q4RealBPP source without redistributing its GPL data."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


AUDIT_DATE = "2026-09-01"
DATASET_DOI = "10.17632/y258s6d939.2"
DATASET_URL = "https://data.mendeley.com/datasets/y258s6d939/2"
PUBLIC_FILE_URL = "https://data.mendeley.com/public-files/datasets/y258s6d939/files/{file_id}/file_downloaded"

# These IDs and hashes are returned by the Mendeley public API for version 2.
AUXILIARY_FILES = {
    "Constraints_and_variables.txt": ("2fba8b11-2916-4a73-bfc5-41578335a4fc", "c29d6a0206ebac99e25065fe2de1e77eb5325edc0eb344947940d5d60b45f32b"),
    "Description.txt": ("19ef1a83-1ba5-4fcc-94d8-1883f76d23f8", "65ebbb961da33745dc8a7e0e9eb9c6243a3be0d6cce05844595cf0229f83ecf4"),
    "Q4RealBPP-DataGen.py": ("9f154613-95b7-4d13-948b-55ed74de79ae", "fa812f7f437cf3e793f8721fd29c138068357e7e7de207509dae238965bb3913"),
}

INPUT_FILES = {
    "3dBPP_1.txt": ("9de04c51-c6a9-4cca-a065-c039149bc42d", "97d62d38f65dc23729cca2904232170f2c641150044974df244f27f5b77bee0e"),
    "3dBPP_2.txt": ("98d79022-2c33-4c0d-bf05-fe137d143bc0", "0a31f3c87ca6458c145f64c9f8f594bbd2ca0558e0962912f34f613974bc30f5"),
    "3dBPP_3.txt": ("092c974e-8556-413b-8d79-90d0006d948c", "c723c24d530ca61d9d0d67fff0ad8423761b66cfc071efb28ff8d487b6647034"),
    "3dBPP_4.txt": ("4a743abc-7829-4c9a-918f-ed9b22014641", "224e62e317eecfb6c837eb5ddbd73b60b2900e45c996ae7ddb40cebe9120768c"),
    "3dBPP_5.txt": ("519287ae-dd5f-48b5-acd0-cb3c49b5d01f", "78dfddd4f5370c753cb247d799b3ab66eb927a1788098ca15a6883024c330d3f"),
    "3dBPP_6.txt": ("8d60b2af-7cae-467f-8aba-6c185df4d340", "313e6d43dc35ba833fb0364e096985ec1a7ef579110d3ca56a423dea41623cc9"),
    "3dBPP_7.txt": ("a564f2e3-54de-4d16-ba8d-94aed153db9a", "6e06fd72a8459c6a27706ec062cbd20556e2fff1b71e0f8e58c0ba1209564fac"),
    "3dBPP_8.txt": ("eb2eea4e-ea3b-4087-829c-05311d84a31b", "4391c8342a2952c2903542e31a7ab11116a3e3e718366ac5272b0ea6b1d7bb96"),
    "3dBPP_9.txt": ("c20b0cb1-8199-4f23-a2d9-e54d81ee90a2", "a501d469e9143b081ca7110cb3acaef392b3903cef58ea4211ae92940da026aa"),
    "3dBPP_10.txt": ("37e73cd2-3032-4bee-835e-5b55805e6134", "bf9b1d0c00b61fafed393f54a7cf07b0225c4ca0b534a4e8b1a01104bb039b03"),
    "3dBPP_11.txt": ("f944baa6-b25b-44de-ac43-e2d6936bb1f4", "f58c104ad2049ea676bb9014cfb4f36c7accb5e258c4da1a3b91e0c84a5f1af2"),
    "3dBPP_12.txt": ("0d4553b2-ee2d-48e7-9431-a21fbb423867", "e4a2c44792c2b6175f5f4ea8957f9c27bb841f76f6b3ef26a8cde98635dfa621"),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_instance(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    max_bins_match = re.search(r"^# Max num of bins\s*:\s*(\d+)\s*$", text, re.MULTILINE)
    dimensions_match = re.search(r"^# Bin dimensions \(L \* W \* H\):\s*\((\d+),(\d+),(\d+)\)\s*$", text, re.MULTILINE)
    max_weight_match = re.search(r"^# Max weight:\s*(\d*)\s*$", text, re.MULTILINE)
    row_pattern = re.compile(r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$", re.MULTILINE)
    rows = [tuple(int(value) for value in match.groups()) for match in row_pattern.finditer(text)]
    errors: list[str] = []
    if not max_bins_match:
        errors.append("missing max-bin header")
    if not dimensions_match:
        errors.append("missing bin-dimension header")
    if len(rows) != 10:
        errors.append(f"expected 10 item-type rows, found {len(rows)}")
    if dimensions_match:
        bin_dimensions = tuple(int(value) for value in dimensions_match.groups())
        for item_id, quantity, length, width, height, weight in rows:
            if quantity < 1 or min(length, width, height) < 1 or weight < 0:
                errors.append(f"invalid item row {item_id}")
            if any(size > limit for size, limit in zip((length, width, height), bin_dimensions)):
                errors.append(f"item {item_id} exceeds declared bin dimensions")
    else:
        bin_dimensions = None
    return {
        "file": path.name,
        "declared_max_bins": int(max_bins_match.group(1)) if max_bins_match else None,
        "bin_dimensions": list(bin_dimensions) if bin_dimensions else None,
        "max_weight": int(max_weight_match.group(1)) if max_weight_match and max_weight_match.group(1) else None,
        "item_type_rows": len(rows),
        "item_count": sum(row[1] for row in rows),
        "nonempty_constraint_headers": {
            # Keep the match on one physical line; ``\s`` would otherwise
            # consume the newline and falsely mark the next header as set.
            "relative_pos": bool(re.search(r"^# Relative pos:[^\r\n]*\S[^\r\n]*$", text, re.MULTILINE)),
            "incompatibilities": bool(re.search(r"^# Incompatibilities:[^\r\n]*\S[^\r\n]*$", text, re.MULTILINE)),
            "positive_affinities": bool(re.search(r"^# Positive affinities:[^\r\n]*\S[^\r\n]*$", text, re.MULTILINE)),
            "center_of_mass": bool(re.search(r"^# Center of mass:[^\r\n]*\S[^\r\n]*$", text, re.MULTILINE)),
        },
        "parse_status": "PASS" if not errors else "FAIL",
        "parse_errors": errors,
    }


def file_record(root: Path, name: str, metadata: tuple[str, str]) -> dict:
    file_id, expected_hash = metadata
    path = root / name
    present = path.exists()
    actual_hash = sha256(path) if present else None
    return {
        "filename": name,
        "file_id": file_id,
        "download_url": PUBLIC_FILE_URL.format(file_id=file_id),
        "expected_sha256": expected_hash,
        "actual_sha256": actual_hash,
        "present": present,
        "hash_status": "PASS" if present and actual_hash == expected_hash else "FAIL",
    }


def build_audit(root: Path) -> dict:
    files = [file_record(root, name, metadata) for name, metadata in [*AUXILIARY_FILES.items(), *INPUT_FILES.items()]]
    instances = [parse_instance(root / name) for name in INPUT_FILES]
    description = (root / "Description.txt").read_text(encoding="utf-8") if (root / "Description.txt").exists() else ""
    description_counts = {
        int(index): int(count)
        for index, count in re.findall(r"3dBPP_(\d+):\s*(\d+)\s+(?:items?|packages?)", description)
    }
    metadata_inconsistencies = []
    for instance in instances:
        index = int(re.search(r"_(\d+)\.txt$", instance["file"]).group(1))
        described = description_counts.get(index)
        if described is not None and described != instance["item_count"]:
            metadata_inconsistencies.append(
                {
                    "file": instance["file"],
                    "description_item_count": described,
                    "input_quantity_sum": instance["item_count"],
                }
            )
    input_counts = [instance["item_count"] for instance in instances]
    all_hashes_pass = all(file["hash_status"] == "PASS" for file in files)
    all_parse_pass = all(instance["parse_status"] == "PASS" for instance in instances)
    return {
        "record_kind": "B33_SOURCE_AUDIT",
        "audit_date": AUDIT_DATE,
        "dataset": {
            "name": "Q4RealBPP",
            "doi": DATASET_DOI,
            "version": 2,
            "url": DATASET_URL,
            "license": "GPL-3.0",
            "source_api": "Mendeley public API v1 media metadata",
            "redistribution": "Do not copy raw GPL dataset into a closed distribution without license review.",
        },
        "source_verification": {
            "downloaded_source_dir": "external temporary directory (not committed)",
            "file_count": len(files),
            "all_declared_hashes_match": all_hashes_pass,
            "all_input_files_parse": all_parse_pass,
        },
        "files": files,
        "instances": instances,
        "summary": {
            "input_instance_count": len(instances),
            "total_item_count": sum(input_counts),
            "min_item_count": min(input_counts) if input_counts else None,
            "max_item_count": max(input_counts) if input_counts else None,
            "item_counts_by_file": {instance["file"]: instance["item_count"] for instance in instances},
            "description_item_counts": {f"3dBPP_{index}.txt": count for index, count in sorted(description_counts.items())},
        },
        "metadata_inconsistencies": metadata_inconsistencies,
        "decision": {
            "input_status": "SOURCE_INCOMPLETE",
            "run_status": "NOT_RUN",
            "reason": "Source bytes and hashes are verified, but the canonical converter, independent validator and GPL redistribution review are still pending.",
            "canonical_count_source": "input quantity column, not Description.txt prose",
            "not_mpV_substitute": True,
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
            print(f"B33_SOURCE_AUDIT_STALE: {args.output}", file=sys.stderr)
            return 1
        print(f"B33_SOURCE_AUDIT_OK: {args.output}")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(audit, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
