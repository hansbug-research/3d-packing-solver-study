#!/usr/bin/env python3
"""Run the checked-in variable-cost fixture through a transparent Python master.

The two Python packers do not expose a variable-cost multi-bin objective.  This
adapter enumerates the finite bin portfolios in the fixture, invokes the
single solve for every portfolio, and chooses the cheapest valid complete
certificate.  The protocol record therefore describes a composed master, not
native comparator support.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import itertools
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
DATA_ROOT = ROOT / "benchmarks" / "data" / "packingsolver"
JERRY_ROOT = ROOT / ".cache" / "jerry-3d-bin-packing"
JERRY_COMMIT = "75764a2b8a5c8e0a6713a4f672c0a8ff81b1107a"
RUNNER_PATH = Path(__file__).resolve()
VALIDATOR_PATH = ROOT / "benchmarks" / "validation.py"
sys.path.insert(0, str(ROOT / "benchmarks"))
sys.path.insert(0, str(ROOT / "benchmarks" / "comprehensive"))
from comprehensive.model import canonical_json, load_catalogs, validate_run_record  # noqa: E402
from validation import Box, validate_aabbs  # noqa: E402

CASES = {
    "LARGE_CHEAPER": "heterogeneous_bins.csv",
    "SMALL_CHEAPER": "heterogeneous_bins_reverse.csv",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def payload_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def source_payload(variant: str) -> tuple[dict[str, Any], list[dict[str, str]], list[dict[str, str]]]:
    items_path = DATA_ROOT / "heterogeneous_items.csv"
    bins_path = DATA_ROOT / CASES[variant]
    source_items = read_csv(items_path)
    items = []
    for row in source_items:
        for copy in range(int(row["COPIES"])):
            expanded = dict(row)
            expanded["ID"] = f"{row['ID']}:{copy}"
            expanded["COPIES"] = "1"
            items.append(expanded)
    source_bins = read_csv(bins_path)
    bins = []
    for row in source_bins:
        for copy in range(int(row["COPIES"])):
            expanded = dict(row)
            expanded["ID"] = f"{row['ID']}:{copy}"
            expanded["COPIES"] = "1"
            bins.append(expanded)
    payload = {
        "benchmark_id": "B09",
        "problem_variant": variant,
        "objective": "variable-sized-bin-packing",
        "items": items,
        "source_items": source_items,
        "bins": bins,
        "source_bins": source_bins,
        "source_files": {
            str(items_path.relative_to(ROOT)): sha256(items_path),
            str(bins_path.relative_to(ROOT)): sha256(bins_path),
        },
    }
    return payload, items, bins


def verify_jerry() -> None:
    actual = subprocess.check_output(["git", "-C", str(JERRY_ROOT), "rev-parse", "HEAD"], text=True).strip()
    if actual != JERRY_COMMIT:
        raise RuntimeError(f"Jerry checkout mismatch: expected {JERRY_COMMIT}, got {actual}")


def solve_py3dbp(items: list[dict[str, str]], bins: list[dict[str, str]], descending: bool) -> dict[str, Any]:
    sys.path[:] = [path for path in sys.path if path != str(JERRY_ROOT)]
    for module in list(sys.modules):
        if module == "py3dbp" or module.startswith("py3dbp."):
            del sys.modules[module]
    from py3dbp import Bin, Item, Packer

    packer = Packer()
    for spec in bins:
        packer.add_bin(Bin(spec["ID"], float(spec["X"]), float(spec["Y"]), float(spec["Z"]), float(spec["MAXIMUM_WEIGHT"])))
    for spec in items:
        packer.add_item(Item(spec["ID"], float(spec["X"]), float(spec["Y"]), float(spec["Z"]), float(spec["WEIGHT"])))
    started = perf_counter()
    packer.pack(bigger_first=descending, distribute_items=True, number_of_decimals=3)
    elapsed = perf_counter() - started
    placements = []
    for container in packer.bins:
        for item in container.items:
            placements.append({
                "item_id": item.name,
                "bin_id": container.name,
                "position": [float(value) for value in item.position],
                "size": [float(value) for value in item.get_dimension()],
            })
    return {"placements": placements, "elapsed_s": elapsed}


def solve_jerry(items: list[dict[str, str]], bins: list[dict[str, str]], descending: bool) -> dict[str, Any]:
    verify_jerry()
    for module in list(sys.modules):
        if module == "py3dbp" or module.startswith("py3dbp."):
            del sys.modules[module]
    sys.path.insert(0, str(JERRY_ROOT))
    from py3dbp import Bin, Item, Packer

    packer = Packer()
    original_gravity = getattr(Packer, "gravityCenter", None)
    if original_gravity is not None:
        Packer.gravityCenter = lambda self, container: [] if not container.items else original_gravity(self, container)
    try:
        for spec in bins:
            packer.addBin(Bin(spec["ID"], (float(spec["X"]), float(spec["Y"]), float(spec["Z"])), float(spec["MAXIMUM_WEIGHT"]), 0, 1))
        for spec in items:
            packer.addItem(Item(spec["ID"], spec["ID"], "cube", (float(spec["X"]), float(spec["Y"]), float(spec["Z"])), float(spec["WEIGHT"]), 1, 0, True, "blue"))
        started = perf_counter()
        packer.pack(bigger_first=descending, distribute_items=True, fix_point=False, check_stable=False, number_of_decimals=3)
        elapsed = perf_counter() - started
        placements = []
        for container in packer.bins:
            for item in container.items:
                placements.append({
                    "item_id": item.partno,
                    "bin_id": container.partno,
                    "position": [float(value) for value in item.position],
                    "size": [float(value) for value in item.getDimension()],
                })
        return {"placements": placements, "elapsed_s": elapsed}
    finally:
        if original_gravity is not None:
            Packer.gravityCenter = original_gravity


def validate_solution(items: list[dict[str, str]], bins: list[dict[str, str]], placements: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    item_specs = {row["ID"]: row for row in items}
    bin_specs = {row["ID"]: row for row in bins}
    seen: set[str] = set()
    boxes: list[Box] = []
    bin_sizes = {}
    weight_limits = {}
    cost_by_bin = {}
    for row in bins:
        bin_sizes[row["ID"]] = (float(row["X"]), float(row["Y"]), float(row["Z"]))
        weight_limits[row["ID"]] = float(row["MAXIMUM_WEIGHT"])
        cost_by_bin[row["ID"]] = float(row["COST"])
    for index, placement in enumerate(placements):
        item_id = str(placement.get("item_id"))
        bin_id = str(placement.get("bin_id"))
        spec = item_specs.get(item_id)
        if spec is None:
            errors.append(f"placement {index}: unknown item {item_id}")
            continue
        if item_id in seen:
            errors.append(f"item {item_id}: duplicate placement")
            continue
        if bin_id not in bin_specs:
            errors.append(f"placement {index}: unknown bin {bin_id}")
            continue
        seen.add(item_id)
        actual = tuple(float(value) for value in placement["size"])
        original = tuple(float(spec[axis]) for axis in ("X", "Y", "Z"))
        allowed = set(itertools.permutations(original))
        if actual not in allowed:
            errors.append(f"item {item_id}: forbidden dimensions {actual}")
        position = tuple(float(value) for value in placement["position"])
        boxes.append(Box(f"{item_id}:{index}", bin_id, *position, *actual, float(spec["WEIGHT"])))
    errors.extend(validate_aabbs(boxes, bin_sizes, weight_limits))
    required = len(items)
    for item_id, spec in item_specs.items():
        expected = int(spec["COPIES"])
        actual = sum(1 for placement in placements if placement.get("item_id") == item_id)
        if actual != expected:
            errors.append(f"item {item_id}: placed {actual}, required {expected}")
    used_bins = sorted({str(placement.get("bin_id")) for placement in placements})
    total_cost = sum(cost_by_bin[bin_id] for bin_id in used_bins if bin_id in cost_by_bin)
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "packed_items": len(seen),
        "required_items": required,
        "complete": len(seen) == required and not errors,
        "bins_used": len(used_bins),
        "used_bin_ids": used_bins,
        "total_cost": total_cost,
    }


def portfolios(bins: list[dict[str, str]]) -> list[list[dict[str, str]]]:
    result: list[list[dict[str, str]]] = []
    for size in range(1, len(bins) + 1):
        result.extend([list(choice) for choice in itertools.combinations(bins, size)])
    return result


def run_one(variant: str, implementation_id: str, time_limit: float, raw_root: Path) -> dict[str, Any]:
    payload, items, source_bins = source_payload(variant)
    input_hash = payload_hash(payload)
    case_dir = raw_root / variant / implementation_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "input.json").write_text(canonical_json(payload), encoding="utf-8")
    all_candidates: list[dict[str, Any]] = []
    solve = solve_py3dbp if implementation_id == "py3dbp" else solve_jerry
    started = perf_counter()
    process_error = None
    try:
        for portfolio in portfolios(source_bins):
            for order, descending in (("DESCENDING", True), ("ASCENDING", False)):
                candidate_started = perf_counter()
                try:
                    output = solve(items, portfolio, descending)
                    validation = validate_solution(items, portfolio, output["placements"])
                    candidate = {
                        "portfolio": [row["ID"] for row in portfolio],
                        "order": order,
                        "elapsed_s": output["elapsed_s"],
                        "placements": output["placements"],
                        "validation": validation,
                    }
                except Exception as exc:  # preserve a failed candidate as evidence
                    candidate = {
                        "portfolio": [row["ID"] for row in portfolio],
                        "order": order,
                        "elapsed_s": perf_counter() - candidate_started,
                        "placements": [],
                        "validation": {"status": "ERROR", "errors": [f"{type(exc).__name__}: {exc}"], "complete": False, "total_cost": None, "bins_used": 0, "packed_items": 0, "required_items": 2},
                    }
                all_candidates.append(candidate)
    except Exception as exc:
        process_error = f"{type(exc).__name__}: {exc}"
    valid_candidates = [candidate for candidate in all_candidates if candidate["validation"]["status"] == "PASS"]
    complete_candidates = [candidate for candidate in valid_candidates if candidate["validation"]["complete"]]
    selectable = complete_candidates or valid_candidates
    selected = min(
        selectable,
        key=lambda candidate: (candidate["validation"]["total_cost"], candidate["validation"]["bins_used"], -candidate["validation"]["packed_items"], candidate["order"]),
    ) if selectable else None
    elapsed = perf_counter() - started
    output = {
        "benchmark_id": "B09",
        "problem_variant": variant,
        "implementation_id": implementation_id,
        "adapter": "b09_cost_master_python_v1",
        "master_policy": "enumerate every non-empty source-bin portfolio and both item orders; choose cheapest valid complete certificate",
        "candidate_count": len(all_candidates),
        "candidates": all_candidates,
        "selected": selected,
        "process_error": process_error,
        "elapsed_s": elapsed,
    }
    (case_dir / "output.json").write_text(canonical_json(output), encoding="utf-8")
    selected_validation = selected["validation"] if selected else {"status": "FAIL", "errors": [process_error or "no valid candidate"], "complete": False, "total_cost": None, "bins_used": 0, "packed_items": 0, "required_items": 2}
    (case_dir / "validation.json").write_text(canonical_json(selected_validation), encoding="utf-8")
    (case_dir / "effective-config.json").write_text(canonical_json({
        "benchmark_id": "B09", "problem_variant": variant, "implementation_id": implementation_id,
        "time_limit_s": time_limit, "input_sha256": input_hash, "runner_sha256": sha256(RUNNER_PATH),
        "validator_sha256": sha256(VALIDATOR_PATH), "source_files": payload["source_files"],
        "pose_semantics": "SOURCE_ROTATION_FLAGS", "process_isolation": False,
    }), encoding="utf-8")
    valid = selected is not None and selected_validation["status"] == "PASS"
    complete = bool(selected_validation.get("complete"))
    expected_cost = 10.0
    metrics = {
        "total_cost": selected_validation.get("total_cost"),
        "expected_cost": expected_cost,
        "cost_delta": (selected_validation.get("total_cost") - expected_cost) if selected_validation.get("total_cost") is not None else None,
        "bins_used": selected_validation.get("bins_used", 0),
        "packed_items": selected_validation.get("packed_items", 0),
        "required_items": selected_validation.get("required_items", 2),
        "candidate_count": len(all_candidates),
        "candidate_invalid_count": sum(candidate["validation"]["status"] != "PASS" for candidate in all_candidates),
        "master_policy": output["master_policy"],
        "validation_error_count": len(selected_validation.get("errors", [])),
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
    }
    implementation = next(row for row in load_catalogs()[1]["implementations"] if row["id"] == implementation_id)
    record = {
        "schema_version": 2, "protocol_version": "benchmark-protocol/3", "record_origin": "PROTOCOL_V3",
        "run_id": f"B09/{variant}/{implementation_id}/10s/composed/rep-0",
        "benchmark_id": "B09", "problem_variant": variant, "instance_id": "heterogeneous_fixture",
        "implementation_id": implementation_id, "algorithm": implementation["algorithm"],
        "adapter": "b09_cost_master_python_v1", "comparison_track": "COMPOSED", "problem_scope": "FULL_PROBLEM",
        "budget": {"time_limit_s": time_limit, "memory_limit_bytes": 1073741824, "thread_limit": 1},
        "item_order": "BOTH_ENUMERATED", "bin_order": "PORTFOLIO_ENUMERATED", "seed": None, "repetition": 0,
        "input_sha256": input_hash, "input_status": "VALID", "capability_status": "SUPPORTED_COMPOSED",
        "run_status": "ERROR" if process_error and not all_candidates else "COMPLETED",
        "solution_status": "VALID_COMPLETE" if valid and complete else "VALID_PARTIAL" if valid else "INVALID_CERTIFICATE",
        "proof_status": "FEASIBLE" if valid else "UNKNOWN", "termination_reason": "COMPOSED_MASTER_ENUMERATION",
        "resources": {"wall_s": elapsed, "solver_s": elapsed, "peak_rss_bytes": metrics["peak_rss_bytes"]},
        "metrics": metrics,
        "artifacts": {
            "input": f"{(raw_root / 'artifacts.tar.gz').relative_to(ROOT)}#{variant}/{implementation_id}/input.json",
            "effective_config": f"{(raw_root / 'artifacts.tar.gz').relative_to(ROOT)}#{variant}/{implementation_id}/effective-config.json",
            "solver_output": f"{(raw_root / 'artifacts.tar.gz').relative_to(ROOT)}#{variant}/{implementation_id}/output.json",
            "solution": f"{(raw_root / 'artifacts.tar.gz').relative_to(ROOT)}#{variant}/{implementation_id}/output.json",
            "validation": f"{(raw_root / 'artifacts.tar.gz').relative_to(ROOT)}#{variant}/{implementation_id}/validation.json",
        },
    }
    validate_run_record(record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--implementation", choices=("py3dbp", "jerry"), action="append", dest="implementations")
    parser.add_argument("--time-limit", type=float, default=10.0)
    parser.add_argument("--results-root", type=Path, default=ROOT / "results" / "comprehensive")
    parser.add_argument("--raw-root", type=Path, default=ROOT / "raw" / "experiments" / "comprehensive")
    args = parser.parse_args()
    implementations = args.implementations or ["py3dbp", "jerry"]
    raw_root = args.raw_root / "b09-python-composed"
    records = [run_one(variant, implementation, args.time_limit, raw_root) for variant in CASES for implementation in implementations]
    archive_path = raw_root / "artifacts.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for path in sorted(raw_root.rglob("*")):
            if path.is_file() and path != archive_path:
                archive.add(path, arcname=path.relative_to(raw_root))
    run_path = args.results_root / "runs" / "B09-python-composed.jsonl"
    run_path.parent.mkdir(parents=True, exist_ok=True)
    run_path.write_text("".join(json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n" for record in records), encoding="utf-8")
    metadata = {
        "schema_version": 1, "protocol_version": "benchmark-protocol/3", "benchmark_id": "B09",
        "implementations": implementations, "variants": list(CASES), "runner_sha256": sha256(RUNNER_PATH),
        "validator_sha256": sha256(VALIDATOR_PATH), "run_jsonl_sha256": sha256(run_path),
        "artifact_archive_sha256": sha256(archive_path), "adapter_semantics": "COMPOSED_FULL_PROBLEM",
    }
    (raw_root / "metadata.json").write_text(canonical_json(metadata), encoding="utf-8")
    print(run_path.relative_to(ROOT))
    return 0 if all(record["solution_status"] == "VALID_COMPLETE" for record in records) else 2


if __name__ == "__main__":
    raise SystemExit(main())
