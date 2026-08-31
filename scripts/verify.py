from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    print(f"VERIFY_FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check_sources() -> None:
    manifest_path = ROOT / "sources" / "manifest.csv"
    quotes_path = ROOT / "sources" / "quotes.md"
    if not manifest_path.exists() or not quotes_path.exists():
        fail("sources/manifest.csv and sources/quotes.md are required")
    with manifest_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"id", "type", "title", "url", "accessed", "commit_or_version", "local_snapshot", "sha256", "used_for"}
        if not required.issubset(reader.fieldnames or set()):
            fail("source manifest is missing required columns")
        rows = list(reader)
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)) or not ids:
        fail("source manifest ids must be non-empty and unique")
    for row in rows:
        for field in ("url", "accessed", "used_for"):
            if not row[field].strip():
                fail(f"source manifest field is empty: {row['id']}/{field}")
        snapshot = row["local_snapshot"].strip()
        if snapshot.lower() in {"", "no"}:
            continue
        path = ROOT / snapshot
        if not path.exists():
            fail(f"source snapshot missing: {row['id']}: {snapshot}")
        expected = row["sha256"].strip()
        if not re.fullmatch(r"[0-9a-f]{64}", expected) or sha256(path) != expected:
            fail(f"source snapshot hash mismatch: {row['id']}: {snapshot}")
    quote_text = quotes_path.read_text()
    quote_ids = re.findall(r"^##\s+(Q\d+)", quote_text, re.MULTILINE)
    if len(quote_ids) != len(set(quote_ids)) or not quote_ids:
        fail("quote ids must be non-empty and unique")
    missing_ids = sorted(set(re.findall(r"\bS\d{2}\b", quote_text)) - set(ids))
    if missing_ids:
        fail(f"quotes refer to unknown source ids: {missing_ids}")


def check_release_metadata() -> None:
    required_paths = [
        "audit/reproducibility_audit.md", "audit/academic_audit.md", "audit/claims.csv", "audit/self_review_log.csv",
        "figures/fig01_thpack9_bins.png", ".github/workflows/verify.yml",
        "raw/provenance.json", "benchmarks/frontend-three-smoke/package.json",
        "benchmarks/frontend-three-smoke/package-lock.json", "benchmarks/frontend-three-smoke/smoke.mjs",
        "benchmarks/data/public/thpack9_instance1.json", "raw/thpack9_instance1.json",
        "raw/experiments/commercial/README.md", "references.bib", "scripts/check_markdown.py", "scripts/check_links.py",
    ]
    for relative in required_paths:
        if not (ROOT / relative).exists():
            fail(f"missing release audit artifact: {relative}")
    cff = (ROOT / "CITATION.cff").read_text()
    for field in ("cff-version:", "title:", "authors:", "version:", "date-released:", "repository-code:"):
        if field not in cff:
            fail(f"CITATION.cff missing field: {field}")
    if not re.search(r"^type:\s+(software|dataset)\s*$", cff, re.MULTILINE):
        fail("CITATION.cff type must be software or dataset")
    try:
        provenance = json.loads((ROOT / "raw" / "provenance.json").read_text())
    except json.JSONDecodeError as exc:
        fail(f"raw/provenance.json is not valid JSON: {exc}")
    source_commits = provenance.get("source_commits", {})
    for name in ("packingsolver_source", "esicup_datasets", "jerry", "skjolber"):
        value = source_commits.get(name, "")
        if not re.fullmatch(r"[0-9a-f]{40}", value):
            fail(f"provenance source commit is not a 40-character SHA: {name}")
    fork = provenance.get("packingsolver_fork", {})
    if fork.get("repository") != "HansBug/packingsolver" or fork.get("branch") != "master":
        fail("PackingSolver fork provenance is missing")
    if not re.fullmatch(r"[0-9a-f]{40}", fork.get("commit", "")):
        fail("PackingSolver fork commit is not a 40-character SHA")
    if fork.get("integrated_upstream_prs") != [540, 541, 542, 543]:
        fail("PackingSolver fork PR provenance is incomplete")
    for name in ("box", "boxstacks"):
        value = provenance.get("packingsolver_binary_sha256", {}).get(name, "")
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            fail(f"provenance binary hash is not SHA-256: {name}")
    tracking = provenance.get("upstream_tracking", {})
    if tracking.get("repository") != "fontanf/packingsolver" or tracking.get("status") != "open_not_merged":
        fail("upstream issue/PR tracking is missing or stale")
    if tracking.get("issues") != [536, 537, 538, 539] or tracking.get("pull_requests") != [540, 541, 542, 543]:
        fail("upstream issue/PR tracking numbers are incomplete")
    benchmark_fixture = json.loads((ROOT / "benchmarks" / "data" / "public" / "thpack9_instance1.json").read_text())
    raw_fixture = json.loads((ROOT / "raw" / "thpack9_instance1.json").read_text())
    if raw_fixture != benchmark_fixture:
        fail("raw/thpack9_instance1.json is not identical to the pinned benchmark fixture")


def main() -> None:
    stats_path = ROOT / "derived" / "stats.json"
    table_path = ROOT / "derived" / "tables" / "public_thpack9.csv"
    manifest_path = ROOT / "raw" / "manifest.json"
    for path in (stats_path, table_path, manifest_path):
        if not path.exists():
            fail(f"missing generated artifact: {path}")

    stats = json.loads(stats_path.read_text())
    if stats["public_required_items"] != 70 or stats["public_volume_lower_bound"] != 19:
        fail("public benchmark headline values changed")
    rows = list(csv.DictReader(table_path.open()))
    expected = {"PackingSolver patched box": 25, "Skjolber LAFF": 28, "py3dbp": 50, "jerry800416/3D-bin-packing": 50}
    observed = {row["library"]: int(row["bins_used"]) for row in rows}
    if observed != expected:
        fail(f"public table mismatch: {observed}")
    for row in rows:
        if row["packed"] != row["required"] or row["status"] != "FEASIBLE":
            fail(f"public result is incomplete or invalid: {row}")

    manifest = json.loads(manifest_path.read_text())
    for entry in manifest["files"]:
        path = ROOT / entry["path"]
        if not path.exists():
            fail(f"manifest file missing: {entry['path']}")
        if path.stat().st_size != entry["bytes"] or sha256(path) != entry["sha256"]:
            fail(f"manifest hash mismatch: {entry['path']}")

    required = ["README.md", "report.md", "LICENSE", "CITATION.cff", "REVIEW.md", "research/benchmarks.md", "research/packingsolver-upstream.md"]
    for relative in required:
        if not (ROOT / relative).exists():
            fail(f"missing release artifact: {relative}")
    check_sources()
    check_release_metadata()
    readme = (ROOT / "README.md").read_text()
    for phrase in ("70 件物品", "25 箱", "28 箱", "50 箱"):
        if phrase not in readme:
            fail(f"README is missing headline result: {phrase}")
    print("VERIFY_OK: generated statistics, public benchmark, raw/source manifests, metadata and release files are consistent")


if __name__ == "__main__":
    main()
