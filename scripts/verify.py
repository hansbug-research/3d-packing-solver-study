from __future__ import annotations

import csv
import hashlib
import json
import math
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
    rows_by_id = {row["id"]: row for row in rows}
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
    expected_baytp_hashes = {
        "S116": "f814947ad7f2cfe2bf43fa3a5ee8d087ecf35f442376a25afa50f72f6147e52e",
        "S117": "914231bd5a53ad890a4e9817e7381d967658bffed4989343eabbc623a845cef7",
        "S118": "9a9b06a40628e87d03fbe36e6a0db220043e4fe45891cc9c2d7498b394621c63",
        "S119": "f334858c23120de183424bbda24784435311b263ce8c730cd78c17b649bcc125",
    }
    for source_id, expected_hash in expected_baytp_hashes.items():
        if rows_by_id.get(source_id, {}).get("sha256") != expected_hash:
            fail(f"BAYTP source hash missing or changed: {source_id}")
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
    protocol = (ROOT / "research" / "test-protocol.md").read_text()
    if "`benchmark-protocol/3`" not in protocol:
        fail("comprehensive benchmark protocol version is not v3")
    benchmark_ids = re.findall(r"^\| (B\d{2}) \|", protocol, re.MULTILINE)
    expected_benchmark_ids = [f"B{index:02d}" for index in range(1, 33)]
    if sorted(benchmark_ids) != expected_benchmark_ids or len(benchmark_ids) != len(set(benchmark_ids)):
        fail(f"comprehensive benchmark catalog must contain B01-B32 exactly once: {benchmark_ids}")
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
    for name in ("packingsolver_source", "esicup_datasets", "jerry", "skjolber", "bp3d", "u_nesting"):
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
        patched_value = provenance.get("packingsolver_patched_binary_sha256", {}).get(name, "")
        if not re.fullmatch(r"[0-9a-f]{64}", patched_value):
            fail(f"provenance patched binary hash is not SHA-256: {name}")
    patch = provenance.get("packingsolver_patch", {})
    patch_path = ROOT / patch.get("path", "")
    if not patch_path.exists() or not re.fullmatch(r"[0-9a-f]{64}", patch.get("sha256", "")):
        fail("PackingSolver patch provenance is missing or malformed")
    if sha256(patch_path) != patch["sha256"]:
        fail("PackingSolver patch provenance hash mismatch")
    patched_build = provenance.get("packingsolver_patched_build", {})
    if not re.fullmatch(r"[0-9a-f]{40}", patched_build.get("source_commit", "")) or patched_build.get("linear_programming_solver") != "HiGHS":
        fail("PackingSolver patched build provenance is missing or stale")
    for relative in patched_build.get("output_files", []):
        if not (ROOT / relative).exists():
            fail(f"PackingSolver patched output is missing: {relative}")
    campaign_build = provenance.get("packingsolver_campaign_build", {})
    if campaign_build.get("source_commit") != fork.get("commit"):
        fail("PackingSolver campaign build is not bound to the current fork commit")
    for name in ("box", "boxstacks"):
        value = campaign_build.get("binary_sha256", {}).get(name, "")
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            fail(f"PackingSolver campaign binary hash is not SHA-256: {name}")
    tracking = provenance.get("upstream_tracking", {})
    if tracking.get("repository") != "fontanf/packingsolver" or tracking.get("status") != "open_not_merged":
        fail("upstream issue/PR tracking is missing or stale")
    if tracking.get("issues") != [536, 537, 538, 539] or tracking.get("pull_requests") != [540, 541, 542, 543]:
        fail("upstream issue/PR tracking numbers are incomplete")
    benchmark_fixture = json.loads((ROOT / "benchmarks" / "data" / "public" / "thpack9_instance1.json").read_text())
    raw_fixture = json.loads((ROOT / "raw" / "thpack9_instance1.json").read_text())
    if raw_fixture != benchmark_fixture:
        fail("raw/thpack9_instance1.json is not identical to the pinned benchmark fixture")


def check_campaign_results() -> None:
    aggregate_path = ROOT / "results" / "campaign" / "aggregate.json"
    if not aggregate_path.exists():
        fail("missing campaign aggregate")
    aggregate = json.loads(aggregate_path.read_text())
    for relative, expected_hash in aggregate.get("source_sha256", {}).items():
        path = ROOT / relative
        if not path.exists() or sha256(path) != expected_hash:
            fail(f"campaign aggregate source hash mismatch: {relative}")

    one = aggregate["packingsolver_thpack"]["one_second"]
    ten = aggregate["packingsolver_thpack"]["ten_seconds"]
    paired = aggregate["packingsolver_thpack"]["paired_budget_comparison"]
    expected_family_counts = {"BR": (700, 166, 0), "LN": (15, 5, 0), "IMM": (44, 0, 0)}
    for family, (validated, zero_1s, zero_10s) in expected_family_counts.items():
        if one[family]["validated"] != validated or ten[family]["validated"] != validated:
            fail(f"PackingSolver campaign validation count changed: {family}")
        if one[family]["zero_item_incumbents"] != zero_1s or ten[family]["zero_item_incumbents"] != zero_10s:
            fail(f"PackingSolver zero-item count changed: {family}")
    if (paired["BR"]["improved"], paired["LN"]["improved"], paired["IMM"]["improved"]) != (673, 7, 0):
        fail("PackingSolver 1s/10s paired comparison changed")

    python = aggregate["python_thpack"]
    if python["coverage"]["executed_records"] != 280 or python["coverage"]["valid_records"] != 276:
        fail("Python THPACK campaign coverage changed")
    if python["status_counts"].get("INVALID") != 4:
        fail("Python THPACK invalid-certificate count changed")

    quality = aggregate["full_thpack9_quality"]
    expected_quality = {
        "packingsolver_1s": (44, 15.477272727272727),
        "packingsolver_10s": (44, 15.477272727272727),
        "skjolber_plain": (44, 17.795454545454547),
        "rust_unesting_extreme_point_adapter": (44, 18.40909090909091),
        "py3dbp_descending": (44, 18.431818181818183),
        "go_bp3d": (44, 19.931818181818183),
        "skjolber_laff": (44, 20.84090909090909),
    }
    for implementation, (valid, mean_bins) in expected_quality.items():
        observed = quality[implementation]
        if observed["valid_complete"] != valid or not math.isclose(
            observed["bins_used"]["mean"], mean_bins, rel_tol=0, abs_tol=1e-12
        ):
            fail(f"THPACK9 quality summary changed: {implementation}")

    exact = aggregate["exact_small"]["canonical_strengthened"]
    if any(data["suite_status"] != "PASS" or data["validation_error_cases"] for data in exact.values()):
        fail("canonical exact-small suite is not fully valid")
    rust_main = aggregate["crosslang"]["crosslang_rust_unesting_strategies"]
    expected_rust_main = {
        "bottomleftfill": (5, 3),
        "ga": (5, 3),
        "brkga": (5, 4),
        "sa": (5, 4),
        "extremepoint": (5, 5),
    }
    for strategy, (records, valid) in expected_rust_main.items():
        observed = rust_main["strategy_validation"].get(strategy, {})
        if observed.get("records") != records or observed.get("valid_geometry_and_constraints") != valid:
            fail(f"Rust main strategy result changed: {strategy}")
    if rust_main["scenario_records"] != 25 or rust_main["valid_geometry_and_constraints"] != 19:
        fail("Rust five-strategy aggregate changed")
    repeats = aggregate["rust_strategy_repeats"]
    for strategy in ("bottomleftfill", "ga", "brkga", "sa"):
        if repeats[strategy]["valid_geometry_and_constraints"] != 0 or repeats[strategy]["invalid"] != 5:
            fail(f"Rust invalid strategy result changed: {strategy}")
    if repeats["extremepoint"]["valid_geometry_and_constraints"] != 5:
        fail("Rust ExtremePoint repeat result changed")
    boxstacks = aggregate["targeted_suites"]["packingsolver_boxstacks"]
    if boxstacks["suite_status"] != "PASS" or boxstacks["status_counts"] != {"PASS": 9}:
        fail("PackingSolver boxstacks targeted suite changed")
    industrial = aggregate["industrial_dataset_audit"]
    for dataset in ("alonso_2019", "alonso_2020"):
        if industrial[dataset].get("capability_status") != "NOT_SUPPORTED" or industrial[dataset].get("run_status") != "NOT_RUN":
            fail(f"industrial dataset run status changed: {dataset}")
    if industrial["baytp"].get("capability_status") != "ESICUP_SNAPSHOT_INCOMPLETE" or industrial["baytp"].get("run_status") != "NOT_RUN":
        fail("industrial dataset run status changed: baytp")


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
    check_campaign_results()
    readme = (ROOT / "README.md").read_text()
    for phrase in (
        "759 个合法源",
        "44 个跨实现实例",
        "15.48",
        "17.80",
        "18.41",
        "18.43",
        "19.93",
        "20.84",
    ):
        if phrase not in readme:
            fail(f"README is missing headline result: {phrase}")
    print("VERIFY_OK: generated statistics, public benchmark, raw/source manifests, metadata and release files are consistent")


if __name__ == "__main__":
    main()
