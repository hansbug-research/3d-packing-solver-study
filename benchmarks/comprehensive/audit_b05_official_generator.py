#!/usr/bin/env python3
"""Audit the MPV official-generator-derived corpus without solving it."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from generate_mpv_official import DEFAULT_OUTPUT, SOURCE_SHA256, SOURCE_URLS


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/comprehensive/b05-official-generator-audit.json"),
    )
    args = parser.parse_args()
    manifest_path = args.corpus / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if manifest.get("corpus") != "MPV_OFFICIAL_GENERATOR_DERIVED":
        errors.append("unexpected corpus name")
    if manifest.get("source_urls") != SOURCE_URLS:
        errors.append("source URL map differs from the pinned script")
    if manifest.get("source_sha256") != SOURCE_SHA256:
        errors.append("source hashes differ from the pinned script")
    instances = manifest.get("instances", [])
    if len(instances) != 150:
        errors.append(f"expected 150 instances, found {len(instances)}")
    hashes: list[str] = []
    type_counts: dict[str, int] = {}
    size_counts: dict[str, int] = {}
    for row in instances:
        path = args.corpus / row["path"]
        if not path.is_file():
            errors.append(f"missing instance: {path}")
            continue
        actual = sha256(path)
        hashes.append(actual)
        if actual != row.get("sha256"):
            errors.append(f"hash mismatch: {path.name}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("instance_id") != row.get("instance_id"):
            errors.append(f"instance id mismatch: {path.name}")
        if len(payload.get("items", [])) != row.get("item_count"):
            errors.append(f"item count mismatch: {path.name}")
        generator = payload.get("generator", {})
        type_counts[str(generator.get("type"))] = type_counts.get(str(generator.get("type")), 0) + 1
        size_counts[str(generator.get("n"))] = size_counts.get(str(generator.get("n")), 0) + 1
    # The generator sorts manifest rows by instance_id before hashing.  Keep
    # that order rather than sorting file hashes independently.
    expected_corpus_hash = hashlib.sha256(("\n".join(hashes) + "\n").encode("ascii")).hexdigest()
    if expected_corpus_hash != manifest.get("corpus_sha256"):
        errors.append("corpus hash mismatch")
    result = {
        "schema_version": 1,
        "corpus": manifest.get("corpus"),
        "status": "VALID" if not errors else "INVALID",
        "original_mpv_archive_status": "SOURCE_INCOMPLETE",
        "source_urls": SOURCE_URLS,
        "source_sha256": SOURCE_SHA256,
        "license_note": manifest.get("license_note"),
        "parameters": manifest.get("parameters"),
        "instance_count": len(instances),
        "type_counts": dict(sorted(type_counts.items())),
        "size_counts": dict(sorted(size_counts.items())),
        "corpus_sha256": manifest.get("corpus_sha256"),
        "errors": errors,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
