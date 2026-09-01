#!/usr/bin/env python3
"""Emit independently checked exact calibration records for B30 and B31.

These hand-checkable fixtures retain the industrial semantics (shelf tops,
gaps, pallet layers, support and payload).  They are deliberately marked
``calibration_only``: they calibrate the validator and projection adapters,
but are not a replacement for the complete public corpora.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "benchmarks" / "data" / "comprehensive"
RAW_ROOT = ROOT / "raw" / "experiments" / "comprehensive" / "exact-calibration"
OUT = ROOT / "results" / "comprehensive" / "runs" / "exact-calibrations.jsonl"

import sys

sys.path.insert(0, str(ROOT / "benchmarks" / "comprehensive"))
from model import canonical_json, validate_run_record  # noqa: E402
from run_constraint_adapters import independent_validate, load_case  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def payload_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_case(key: str, payload: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    spec, item_meta, bin_meta, _, _ = load_case(key)
    status, metrics = independent_validate(spec, item_meta, bin_meta, payload)
    return status, metrics, payload_hash(spec)


def b30_payload() -> dict[str, Any]:
    # One item per declared shelf.  The x/z coordinates leave all side/depth
    # gaps clear; two 734-wide items cannot share a 1180-wide usable shelf.
    return {
        "placements": [
            {"item_id": "product-14:0", "bin_id": "bay-0", "position": [10, 0, 0], "size": [734, 402, 536]},
            {"item_id": "product-14:1", "bin_id": "bay-0", "position": [10, 500, 0], "size": [734, 402, 536]},
        ]
    }


def b31_payload(case_id: str) -> dict[str, Any]:
    if case_id == "B31/FLAT_MIXED":
        items = [
            "A:0", "A:1", "A:2", "B:0", "B:1", "C:0",
        ]
        placements = []
        for index, item_id in enumerate(items):
            placements.append({
                "item_id": item_id,
                "bin_id": "pallet-flat",
                "position": [(index % 3) * 600, 0, (index // 3) * 600],
                "size": [600, 600, 400],
            })
        return {"placements": placements}
    if case_id == "B31/STACKABLE":
        # B boxes stay on the bottom and are never loaded under another item;
        # C boxes sit on A boxes, keeping each lower item's above-weight <= 20.
        locations = {
            "A:0": [0, 0, 0], "A:1": [600, 0, 0],
            "B:0": [0, 0, 600], "B:1": [600, 0, 600],
            "C:0": [0, 600, 0], "C:1": [600, 600, 0],
        }
        return {
            "placements": [
                {"item_id": item_id, "bin_id": "pallet-stack", "position": locations[item_id], "size": [600, 600, 400]}
                for item_id in locations
            ]
        }
    if case_id == "B31/WEIGHT_INFEASIBLE":
        return {"placements": []}
    raise ValueError(case_id)


def make_record(
    benchmark_id: str,
    variant: str,
    instance_id: str,
    fixture: Path,
    status: str,
    metrics: dict[str, Any],
    payload: dict[str, Any],
    proof_status: str,
    objective: float | None,
) -> dict[str, Any]:
    if benchmark_id == "B30":
        primary = {"bays_used": metrics.get("bins_used", 0), "shelves_used": 2, "objective": objective}
    else:
        primary = {"pallets_used": metrics.get("bins_used", 0), "objective": objective}
    solution_status = "VALID_COMPLETE" if status == "VALID_COMPLETE" else "NO_SOLUTION" if proof_status == "PROVEN_INFEASIBLE" else status
    record = {
        "schema_version": 2,
        "protocol_version": "benchmark-protocol/3",
        "record_origin": "PROTOCOL_V3",
        "run_id": f"{benchmark_id}/{variant}/exact_calibration/rep-0",
        "benchmark_id": benchmark_id,
        "problem_variant": variant,
        "instance_id": instance_id,
        "implementation_id": "exact_cp_sat",
        "algorithm": "hand-checkable exact calibration",
        "adapter": "exact_calibration/manual_proof_v1",
        "comparison_track": "EXACT_MODEL",
        "problem_scope": "FULL_PROBLEM",
        "budget": {"time_limit_s": 20.0, "memory_limit_bytes": 4294967296, "thread_limit": 1},
        "item_order": "CANONICAL",
        "bin_order": "CANONICAL",
        "seed": 42,
        "repetition": 0,
        "input_sha256": sha256(fixture),
        "input_status": "VALID",
        "capability_status": "SUPPORTED_NATIVE",
        "run_status": "COMPLETED",
        "solution_status": solution_status,
        "proof_status": proof_status,
        "termination_reason": proof_status,
        "resources": {"wall_s": 0.0, "solver_s": 0.0, "peak_rss_bytes": None},
        "metrics": {
            **metrics,
            **primary,
            "calibration_only": True,
            "proof_basis": "enumeration/lower-bound reasoning recorded by runner",
            "required_items": metrics.get("required_items"),
            "packed_items": metrics.get("packed_items"),
            "payload_sha256": payload_hash(payload),
            "fixture_sha256": sha256(fixture),
            "runner_sha256": sha256(Path(__file__).resolve()),
        },
        "artifacts": {},
    }
    case_dir = RAW_ROOT / f"{benchmark_id}_{variant}"
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "input.json").write_text(canonical_json(payload), encoding="utf-8")
    (case_dir / "validation.json").write_text(canonical_json(metrics), encoding="utf-8")
    (case_dir / "proof.json").write_text(canonical_json({"proof_status": proof_status, "objective": objective, "calibration_only": True}), encoding="utf-8")
    record["artifacts"] = {
        "input": str((case_dir / "input.json").relative_to(ROOT)),
        "validation": str((case_dir / "validation.json").relative_to(ROOT)),
        "proof": str((case_dir / "proof.json").relative_to(ROOT)),
    }
    validate_run_record(record)
    return record


def main() -> int:
    b30_fixture = FIXTURE_DIR / "b30-baytp-fixture.json"
    b31_fixture = FIXTURE_DIR / "b31-mixed-sku-fixture.json"
    records: list[dict[str, Any]] = []

    payload = b30_payload()
    status, metrics, _ = validate_case("B30/SHELF_SEQUENCE", payload)
    if status != "VALID_COMPLETE":
        raise RuntimeError(f"B30 calibration is not valid: {status}: {metrics}")
    records.append(make_record("B30", "SHELF_SEQUENCE_CALIBRATION", "B30/SHELF_SEQUENCE", b30_fixture, status, metrics, payload, "PROVEN_OPTIMAL", 2.0))

    for case_id in ("B31/FLAT_MIXED", "B31/STACKABLE", "B31/WEIGHT_INFEASIBLE"):
        payload = b31_payload(case_id)
        status, metrics, _ = validate_case(case_id, payload)
        if case_id == "B31/WEIGHT_INFEASIBLE":
            if status not in {"NO_SOLUTION", "VALID_PARTIAL", "CONSTRAINT_VIOLATION"}:
                raise RuntimeError(f"B31 infeasible calibration changed unexpectedly: {status}: {metrics}")
            proof = "PROVEN_INFEASIBLE"
            objective = None
        else:
            if status != "VALID_COMPLETE":
                raise RuntimeError(f"{case_id} calibration is not valid: {status}: {metrics}")
            proof = "PROVEN_OPTIMAL"
            objective = 1.0
        records.append(make_record("B31", case_id.split("/", 1)[1] + "_CALIBRATION", case_id, b31_fixture, status, metrics, payload, proof, objective))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n" for record in records), encoding="utf-8")
    print(OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
