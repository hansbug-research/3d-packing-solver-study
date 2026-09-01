#!/usr/bin/env python3
"""Run Go bp3d and u-nesting through the B09 composed cost master."""

from __future__ import annotations

import argparse
import json
import os
import resource
import subprocess
import sys
import tarfile
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
COMPREHENSIVE = Path(__file__).resolve().parent
sys.path.insert(0, str(COMPREHENSIVE))
sys.path.insert(0, str(ROOT / "benchmarks"))
from run_b09_python_composed import (  # noqa: E402
    CASES,
    portfolios,
    payload_hash,
    sha256,
    source_payload,
    validate_solution,
)
from comprehensive.model import canonical_json, load_catalogs, validate_run_record  # noqa: E402

RUST_STRATEGIES = {
    "rust_extreme_point": "extremepoint",
    "rust_layer": "bottomleftfill",
    "rust_ga": "ga",
    "rust_brkga": "brkga",
    "rust_sa": "sa",
}
RUST_IMPLEMENTATIONS = tuple(RUST_STRATEGIES)
DEFAULT_BINARIES = {
    "go_bp3d": Path("/tmp/packing-crosslang-go-build/crosslang_go_bp3d"),
    "rust_unesting": Path("/tmp/packing-crosslang-u-build/target/release/crosslang-rust-unesting"),
}


def external_payload(payload: dict[str, Any], items: list[dict[str, str]], bins: list[dict[str, str]], order: str) -> dict[str, Any]:
    ordered_items = items if order == "ASCENDING" else list(reversed(items))
    return {
        "scenario": f"B09-{payload['problem_variant']}",
        "bins": [
            {
                "id": row["ID"],
                "size": [float(row[axis]) for axis in ("X", "Y", "Z")],
                "max_weight": float(row["MAXIMUM_WEIGHT"]),
                "cost": float(row["COST"]),
            }
            for row in bins
        ],
        "items": [
            {
                "id": row["ID"],
                "size": [float(row[axis]) for axis in ("X", "Y", "Z")],
                "weight": float(row["WEIGHT"]),
                "orientation_requirement": "any",
            }
            for row in ordered_items
        ],
    }


def command(implementation_id: str, binary: Path, input_path: Path, order: str, time_limit: float) -> list[str]:
    command = [
        "/usr/bin/timeout", "--signal=TERM", "--kill-after=1s", str(time_limit),
        str(binary), "--input", str(input_path),
    ]
    if implementation_id in RUST_STRATEGIES:
        command.extend([RUST_STRATEGIES[order], str(round(time_limit * 1000))])
    return command


def run_one(variant: str, implementation_id: str, binary: Path, time_limit: float, raw_root: Path) -> dict[str, Any]:
    payload, items, source_bins = source_payload(variant)
    input_hash = payload_hash(payload)
    case_dir = raw_root / variant / implementation_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "source-input.json").write_text(canonical_json(payload), encoding="utf-8")
    candidates: list[dict[str, Any]] = []
    started = perf_counter()
    for portfolio in portfolios(source_bins):
        for order in ("DESCENDING", "ASCENDING"):
            candidate_dir = case_dir / f"candidate-{len(candidates):03d}"
            candidate_dir.mkdir(parents=True, exist_ok=True)
            input_value = external_payload(payload, items, portfolio, order)
            input_path = candidate_dir / "input.json"
            stdout_path = candidate_dir / "stdout.log"
            stderr_path = candidate_dir / "stderr.log"
            input_path.write_text(canonical_json(input_value), encoding="utf-8")
            candidate_started = perf_counter()
            try:
                completed = subprocess.run(
                    command(implementation_id, binary, input_path, implementation_id, time_limit),
                    capture_output=True, text=True, timeout=time_limit + 5,
                    env={**os.environ, "OMP_NUM_THREADS": "1", "RAYON_NUM_THREADS": "1", "GOMAXPROCS": "1"},
                    check=False,
                )
                stdout_path.write_text(completed.stdout, encoding="utf-8")
                stderr_path.write_text(completed.stderr, encoding="utf-8")
                if completed.returncode != 0:
                    raise RuntimeError(f"external process exit {completed.returncode}: {completed.stderr.strip()[:300]}")
                output = json.loads(completed.stdout)
                if implementation_id == "go_bp3d" and output.get("commit") != "0ba3dcda7ab334c19b0979b1cf1fa05e09f33bc7":
                    raise RuntimeError(f"Go commit mismatch: {output.get('commit')}")
                if implementation_id in RUST_STRATEGIES and output.get("commit") != "8cde85b029e4ade663185dacb93fd74440af170d":
                    raise RuntimeError(f"Rust commit mismatch: {output.get('commit')}")
                validation = validate_solution(items, portfolio, output.get("placements", []))
                candidate = {
                    "portfolio": [row["ID"] for row in portfolio],
                    "order": order,
                    "elapsed_s": perf_counter() - candidate_started,
                    "placements": output.get("placements", []),
                    "unplaced": output.get("unplaced", []),
                    "validation": validation,
                }
            except Exception as exc:
                candidate = {
                    "portfolio": [row["ID"] for row in portfolio], "order": order,
                    "elapsed_s": perf_counter() - candidate_started, "placements": [], "unplaced": [],
                    "validation": {"status": "ERROR", "errors": [f"{type(exc).__name__}: {exc}"], "complete": False, "total_cost": None, "bins_used": 0, "packed_items": 0, "required_items": len(items)},
                }
            (candidate_dir / "result.json").write_text(canonical_json(candidate), encoding="utf-8")
            candidates.append(candidate)
    valid = [candidate for candidate in candidates if candidate["validation"]["status"] == "PASS"]
    complete = [candidate for candidate in valid if candidate["validation"]["complete"]]
    selected = min(
        complete or valid,
        key=lambda candidate: (candidate["validation"]["total_cost"], candidate["validation"]["bins_used"], -candidate["validation"]["packed_items"], candidate["order"]),
    ) if (complete or valid) else None
    selected_validation = selected["validation"] if selected else {"status": "FAIL", "errors": ["no valid candidate"], "complete": False, "total_cost": None, "bins_used": 0, "packed_items": 0, "required_items": len(items)}
    (case_dir / "selected-validation.json").write_text(canonical_json(selected_validation), encoding="utf-8")
    elapsed = perf_counter() - started
    implementation = next(row for row in load_catalogs()[1]["implementations"] if row["id"] == implementation_id)
    expected_cost = 10.0
    metrics = {
        "total_cost": selected_validation.get("total_cost"), "expected_cost": expected_cost,
        "cost_delta": selected_validation.get("total_cost") - expected_cost if selected_validation.get("total_cost") is not None else None,
        "bins_used": selected_validation.get("bins_used", 0), "packed_items": selected_validation.get("packed_items", 0),
        "required_items": selected_validation.get("required_items", len(items)), "candidate_count": len(candidates),
        "candidate_invalid_count": sum(candidate["validation"]["status"] != "PASS" for candidate in candidates),
        "master_policy": "enumerate every non-empty source-bin portfolio and both item orders; choose cheapest valid complete certificate",
        "validation_error_count": len(selected_validation.get("errors", [])),
    }
    (case_dir / "effective-config.json").write_text(canonical_json({
        "benchmark_id": "B09", "problem_variant": variant, "implementation_id": implementation_id,
        "binary": str(binary), "binary_sha256": sha256(binary), "runner_sha256": sha256(Path(__file__).resolve()),
        "validator_sha256": sha256(ROOT / "benchmarks" / "validation.py"), "input_sha256": input_hash,
        "time_limit_s": time_limit, "process_isolation": True, "pose_semantics": "SOURCE_ROTATION_FLAGS",
    }), encoding="utf-8")
    record = {
        "schema_version": 2, "protocol_version": "benchmark-protocol/3", "record_origin": "PROTOCOL_V3",
        "run_id": f"B09/{variant}/{implementation_id}/10s/external-composed/rep-0",
        "benchmark_id": "B09", "problem_variant": variant, "instance_id": "heterogeneous_fixture",
        "implementation_id": implementation_id, "algorithm": implementation["algorithm"],
        "adapter": "b09_cost_master_external_v1", "comparison_track": "COMPOSED", "problem_scope": "FULL_PROBLEM",
        "budget": {"time_limit_s": time_limit, "memory_limit_bytes": 1073741824, "thread_limit": 1},
        "item_order": "BOTH_ENUMERATED", "bin_order": "PORTFOLIO_ENUMERATED", "seed": None, "repetition": 0,
        "input_sha256": input_hash, "input_status": "VALID", "capability_status": "SUPPORTED_COMPOSED",
        "run_status": "COMPLETED", "solution_status": "VALID_COMPLETE" if selected and selected_validation["complete"] else "VALID_PARTIAL" if selected else "INVALID_CERTIFICATE",
        "proof_status": "FEASIBLE" if selected else "UNKNOWN", "termination_reason": "COMPOSED_MASTER_ENUMERATION",
        "resources": {"wall_s": elapsed, "solver_s": elapsed, "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024},
        "metrics": metrics,
        "artifacts": {
            "input": f"{(raw_root / 'artifacts.tar.gz').relative_to(ROOT)}#{variant}/{implementation_id}/source-input.json",
            "effective_config": f"{(raw_root / 'artifacts.tar.gz').relative_to(ROOT)}#{variant}/{implementation_id}/effective-config.json",
            "solver_output": f"{(raw_root / 'artifacts.tar.gz').relative_to(ROOT)}#{variant}/{implementation_id}/candidate-000/result.json",
            "solution": f"{(raw_root / 'artifacts.tar.gz').relative_to(ROOT)}#{variant}/{implementation_id}/candidate-000/result.json",
            "validation": f"{(raw_root / 'artifacts.tar.gz').relative_to(ROOT)}#{variant}/{implementation_id}/selected-validation.json",
        },
    }
    validate_run_record(record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--implementation", choices=("go_bp3d", *RUST_IMPLEMENTATIONS), action="append", dest="implementations")
    parser.add_argument("--binary", type=Path, action="append", dest="binaries")
    parser.add_argument("--time-limit", type=float, default=10.0)
    parser.add_argument("--results-root", type=Path, default=ROOT / "results" / "comprehensive")
    parser.add_argument("--raw-root", type=Path, default=ROOT / "raw" / "experiments" / "comprehensive")
    args = parser.parse_args()
    implementations = args.implementations or ["go_bp3d", *RUST_IMPLEMENTATIONS]
    supplied = args.binaries or []
    binaries = {implementation_id: (supplied[index] if index < len(supplied) else DEFAULT_BINARIES["rust_unesting" if implementation_id in RUST_IMPLEMENTATIONS else "go_bp3d"]).resolve() for index, implementation_id in enumerate(implementations)}
    for implementation_id, binary in binaries.items():
        if not binary.is_file():
            raise ValueError(f"missing binary for {implementation_id}: {binary}")
    raw_root = args.raw_root / "b09-external-composed"
    records = [run_one(variant, implementation_id, binaries[implementation_id], args.time_limit, raw_root) for variant in CASES for implementation_id in implementations]
    archive_path = raw_root / "artifacts.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for path in sorted(raw_root.rglob("*")):
            if path.is_file() and path != archive_path:
                archive.add(path, arcname=path.relative_to(raw_root))
    run_path = args.results_root / "runs" / "B09-external-composed.jsonl"
    run_path.parent.mkdir(parents=True, exist_ok=True)
    run_path.write_text("".join(json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n" for record in records), encoding="utf-8")
    (raw_root / "metadata.json").write_text(canonical_json({
        "schema_version": 1, "protocol_version": "benchmark-protocol/3", "benchmark_id": "B09",
        "implementations": implementations, "binary_sha256": {key: sha256(value) for key, value in binaries.items()},
        "runner_sha256": sha256(Path(__file__).resolve()), "validator_sha256": sha256(ROOT / "benchmarks" / "validation.py"),
        "run_jsonl_sha256": sha256(run_path), "artifact_archive_sha256": sha256(archive_path),
        "adapter_semantics": "COMPOSED_FULL_PROBLEM",
    }), encoding="utf-8")
    print(run_path.relative_to(ROOT))
    return 0 if all(record["solution_status"] == "VALID_COMPLETE" for record in records) else 2


if __name__ == "__main__":
    raise SystemExit(main())
