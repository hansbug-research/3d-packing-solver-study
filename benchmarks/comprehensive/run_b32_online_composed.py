#!/usr/bin/env python3
"""Run bounded online policies through geometry-only packing adapters.

The candidate libraries do not expose a common incremental API.  This runner
therefore implements the policy layer (first-fit bins, bounded lookahead, and
offline rebuild) and invokes each library on the contents of one candidate bin.
Every record is explicitly ``COMPOSED/GEOMETRY_PROJECTION``; it is evidence for
the adapter policy, not a claim that the library itself is online-aware.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import statistics
import subprocess
import sys
from pathlib import Path
from time import perf_counter
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "benchmarks" / "data" / "comprehensive" / "b32-online-fixture.json"
RESULTS = ROOT / "results" / "comprehensive" / "runs" / "B32-online-composed.jsonl"
RAW_ROOT = ROOT / "raw" / "experiments" / "comprehensive" / "B32-online-composed"
RUNNER = Path(__file__).resolve()
sys.path.insert(0, str(ROOT / "benchmarks" / "comprehensive"))

from model import load_catalogs, validate_run_record  # noqa: E402
from run_constraint_adapters import command_for, independent_validate  # noqa: E402


IMPLEMENTATIONS = [
    "py3dbp",
    "jerry",
    "go_bp3d",
    "rust_extreme_point",
    "rust_layer",
    "rust_ga",
    "rust_brkga",
    "rust_sa",
]
POLICIES = {
    "NO_REORDER": {"lookahead": 0, "reorder_budget": 0},
    "LOOKAHEAD_2": {"lookahead": 2, "reorder_budget": 0},
    "OFFLINE_REBUILD": {"lookahead": None, "reorder_budget": 999},
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p * len(ordered)) - 1)]


def fixture_cases() -> list[dict[str, Any]]:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return data["cases"]


def build_spec(case: dict[str, Any], items: list[dict[str, Any]], bin_id: str) -> tuple[dict[str, Any], dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    container = case["container"]
    normalized_items = []
    item_meta: dict[str, dict[str, str]] = {}
    for source in items:
        item = {**source, "type_id": source["id"], "orientation_requirement": "any"}
        normalized_items.append(item)
        item_meta[source["id"]] = {
            "ID": source["id"],
            "X": str(source["size"][0]), "Y": str(source["size"][1]), "Z": str(source["size"][2]),
            "WEIGHT": str(source.get("weight", 0.0)), "COPIES": "1", "GROUP_ID": "0",
            "ROTATION_XYZ": "1", "ROTATION_YXZ": "1", "ROTATION_ZYX": "1",
            "ROTATION_YZX": "1", "ROTATION_XZY": "1", "ROTATION_ZXY": "1",
        }
    bin_row = {
        "ID": bin_id,
        "X": str(container["size"][0]), "Y": str(container["size"][1]), "Z": str(container["size"][2]),
        "COPIES": "1", "COST": str(container.get("cost", 1.0)), "MAXIMUM_WEIGHT": str(container.get("max_weight", float("inf"))),
        "IS_SEMI_TRAILER_TRUCK": "0",
    }
    spec = {
        "scenario": f"b32_{case['id'].replace('/', '_').lower()}_{bin_id}",
        "benchmark_id": "B32",
        "problem_variant": "GEOMETRY_CANDIDATE",
        "items": normalized_items,
        "bins": [{"id": bin_id, "type_id": bin_id, "size": container["size"], "max_weight": container.get("max_weight", float("inf")), "cost": container.get("cost", 1.0)}],
        "expected_complete": True,
        "source_files": {str(FIXTURE.relative_to(ROOT)): sha256(FIXTURE)},
    }
    return spec, item_meta, {bin_id: bin_row}


def remap_payload(payload: dict[str, Any], item_ids: set[str], bin_id: str) -> dict[str, Any]:
    remapped = copy.deepcopy(payload)
    for placement in remapped.get("placements", []):
        item_id = str(placement.get("item_id", ""))
        if item_id not in item_ids and item_id.endswith(":0") and item_id[:-2] in item_ids:
            placement["item_id"] = item_id[:-2]
        placement["bin_id"] = bin_id
    return remapped


def invoke(
    implementation_id: str,
    case: dict[str, Any],
    items: list[dict[str, Any]],
    bin_id: str,
    work: Path,
    candidate_index: int,
) -> tuple[str, dict[str, Any], dict[str, Any], float, str]:
    spec, item_meta, bin_meta = build_spec(case, items, bin_id)
    candidate = work / f"candidate-{candidate_index:03d}"
    candidate.mkdir(parents=True, exist_ok=True)
    input_path = candidate / "input.json"
    stdout_path = candidate / "stdout.log"
    stderr_path = candidate / "stderr.log"
    validation_path = candidate / "validation.json"
    input_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    command = command_for(implementation_id, input_path, spec)
    env = os.environ.copy()
    env.update({"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1", "RAYON_NUM_THREADS": "1", "GOMAXPROCS": "1"})
    if command is None:
        stderr = "adapter unavailable"
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text(stderr, encoding="utf-8")
        validation = {"validation_error_count": 1, "errors": [stderr]}
        validation_path.write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
        return "ERROR", {"placements": []}, validation, 0.0, stderr
    started = perf_counter()
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=2.0, env=env, check=False)
        wall_s = perf_counter() - started
        stdout, stderr = completed.stdout, completed.stderr
        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text(stderr, encoding="utf-8")
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = {"placements": []}
        payload = remap_payload(payload, {item["id"] for item in items}, bin_id)
        status, validation = independent_validate(spec, item_meta, bin_meta, payload)
        validation["candidate_returncode"] = completed.returncode
        validation["candidate_status"] = status
        validation_path.write_text(json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if completed.returncode != 0 and status == "NO_SOLUTION":
            return "ERROR", payload, validation, wall_s, stderr
        return "COMPLETED", payload, validation, wall_s, stderr
    except subprocess.TimeoutExpired as exc:
        wall_s = perf_counter() - started
        stdout = exc.stdout or ""
        stderr = exc.stderr or "TIME_LIMIT"
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text(stderr, encoding="utf-8")
        validation = {"validation_error_count": 0, "timeout": True}
        validation_path.write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
        return "TIME_LIMIT", {"placements": []}, validation, wall_s, stderr


def policy_order(items: list[dict[str, Any]], policy_id: str) -> list[dict[str, Any]]:
    arrival = sorted(items, key=lambda item: int(item["arrival"]))
    if policy_id == "NO_REORDER":
        return arrival
    if policy_id == "OFFLINE_REBUILD":
        return sorted(arrival, key=lambda item: (-float(math.prod(item["size"])), item["arrival"], item["id"]))
    window = POLICIES[policy_id]["lookahead"] + 1
    output: list[dict[str, Any]] = []
    for start in range(0, len(arrival), window):
        chunk = arrival[start:start + window]
        output.extend(sorted(chunk, key=lambda item: (-float(math.prod(item["size"])), item["arrival"], item["id"])))
    return output


def run_policy(implementation_id: str, case: dict[str, Any], policy_id: str) -> dict[str, Any]:
    work = RAW_ROOT / case["id"].replace("/", "_") / implementation_id / policy_id
    work.mkdir(parents=True, exist_ok=True)
    order = policy_order(case["items"], policy_id)
    bins: list[dict[str, Any]] = []
    latencies: list[float] = []
    candidate_calls = 0
    candidate_failures = 0
    deadline_misses = 0
    relocation_count = 0
    next_index = 0
    for item in order:
        decided = False
        decision_started = perf_counter()
        for bin_state in bins:
            candidate_calls += 1
            status, payload, validation, wall_s, _ = invoke(
                implementation_id, case, [*bin_state["items"], item], bin_state["id"], work, next_index
            )
            next_index += 1
            if status == "COMPLETED" and validation.get("candidate_status") == "VALID_COMPLETE":
                bin_state["items"].append(item)
                bin_state["placements"] = payload.get("placements", [])
                decided = True
                latencies.append(perf_counter() - decision_started)
                break
            candidate_failures += 1
        if not decided:
            bin_id = f"{case['container']['id']}:{len(bins)}"
            candidate_calls += 1
            status, payload, validation, wall_s, _ = invoke(implementation_id, case, [item], bin_id, work, next_index)
            next_index += 1
            if status == "COMPLETED" and validation.get("candidate_status") == "VALID_COMPLETE":
                bins.append({"id": bin_id, "items": [item], "placements": payload.get("placements", [])})
                latencies.append(perf_counter() - decision_started)
            else:
                candidate_failures += 1
                latencies.append(perf_counter() - decision_started)
        if latencies and latencies[-1] > float(case["deadline_s"]):
            deadline_misses += 1

    all_items = [item for item in case["items"]]
    final_bins = [{"id": state["id"], "type_id": state["id"], "size": case["container"]["size"], "max_weight": case["container"].get("max_weight", float("inf")), "cost": case["container"].get("cost", 1.0)} for state in bins]
    final_spec, final_meta, final_bin_meta = build_spec(case, all_items, final_bins[0]["id"] if final_bins else f"{case['container']['id']}:0")
    final_spec["bins"] = final_bins
    final_bin_meta = {}
    for row in final_bins:
        final_bin_meta[row["id"]] = {
            "ID": row["id"], "X": str(row["size"][0]), "Y": str(row["size"][1]), "Z": str(row["size"][2]),
            "COPIES": "1", "COST": str(row["cost"]), "MAXIMUM_WEIGHT": str(row["max_weight"]), "IS_SEMI_TRAILER_TRUCK": "0",
        }
    final_payload = {"placements": []}
    for state in bins:
        final_payload["placements"].extend(state["placements"])
    solution_status, validation = independent_validate(final_spec, final_meta, final_bin_meta, final_payload)
    final_solution = work / "solution.json"
    final_validation = work / "validation.json"
    decisions = work / "decisions.json"
    final_solution.write_text(json.dumps(final_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    final_validation.write_text(json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    decisions.write_text(json.dumps({"policy": policy_id, "order": [item["id"] for item in order], "arrival_order": [item["id"] for item in sorted(all_items, key=lambda item: item["arrival"])], "bins": [{"id": state["id"], "items": [item["id"] for item in state["items"]]} for state in bins]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    run_status = "COMPLETED" if solution_status == "VALID_COMPLETE" else "ERROR" if candidate_failures and not bins else "COMPLETED"
    return {
        "solution_status": solution_status,
        "run_status": run_status,
        "validation": validation,
        "bins": bins,
        "order": order,
        "latencies": latencies,
        "candidate_calls": candidate_calls,
        "candidate_failures": candidate_failures,
        "deadline_misses": deadline_misses,
        "relocation_count": relocation_count,
        "artifacts": {"solution": str(final_solution.relative_to(ROOT)), "validation": str(final_validation.relative_to(ROOT)), "decisions": str(decisions.relative_to(ROOT))},
    }


def make_record(implementation_id: str, case: dict[str, Any], policy_id: str, result: dict[str, Any]) -> dict[str, Any]:
    _, catalog = load_catalogs()
    implementation = next(row for row in catalog["implementations"] if row["id"] == implementation_id)
    latencies = result["latencies"]
    metrics = {
        "packed_items": result["validation"].get("packed_items", 0),
        "required_items": len(case["items"]),
        "bins_used": len(result["bins"]),
        "total_cost": len(result["bins"]) * float(case["container"].get("cost", 1.0)),
        "candidate_calls": result["candidate_calls"],
        "candidate_failures": result["candidate_failures"],
        "decision_latency_p50_s": statistics.median(latencies) if latencies else None,
        "decision_latency_p95_s": percentile(latencies, 0.95),
        "deadline_misses": result["deadline_misses"],
        "deadline_hit_rate": (len(latencies) - result["deadline_misses"]) / len(latencies) if latencies else 0.0,
        "relocation_count": result["relocation_count"],
        "offline_rebuild": policy_id == "OFFLINE_REBUILD",
        "provenance_kind": "FRESH_SOLVER_INVOCATION",
        "runner_sha256": sha256(RUNNER),
        "fixture_sha256": sha256(FIXTURE),
        "validation_error_count": result["validation"].get("validation_error_count", 0),
        "hard_violation_count": result["validation"].get("hard_violation_count", 0),
        "geometry_error_count": result["validation"].get("geometry_error_count", 0),
    }
    variant = f"{case['id'].split('/', 1)[1]}__{policy_id}"
    run_id = f"B32/{variant}/{implementation_id}/2s/online-composed/rep-0"
    record = {
        "schema_version": 2,
        "protocol_version": "benchmark-protocol/3",
        "record_origin": "PROTOCOL_V3",
        "run_id": run_id,
        "benchmark_id": "B32",
        "problem_variant": variant,
        "instance_id": case["id"],
        "implementation_id": implementation_id,
        "algorithm": implementation["algorithm"],
        "adapter": "b32_online_composed_v1",
        "comparison_track": "COMPOSED",
        "problem_scope": "GEOMETRY_PROJECTION",
        "budget": {"time_limit_s": 1.0, "memory_limit_bytes": 536870912, "thread_limit": 1},
        "item_order": policy_id,
        "bin_order": "FIRST_FIT",
        "seed": 42,
        "repetition": 0,
        "input_sha256": digest(case),
        "input_status": "VALID",
        "capability_status": "PROJECTION_ONLY",
        "run_status": result["run_status"],
        "solution_status": result["solution_status"],
        "proof_status": "FEASIBLE" if result["solution_status"] in {"VALID_COMPLETE", "VALID_PARTIAL"} else "UNKNOWN",
        "termination_reason": "RETURNED_COMPOSED_POLICY" if result["run_status"] == "COMPLETED" else result["run_status"],
        "resources": {"wall_s": sum(latencies), "solver_s": None, "peak_rss_bytes": None},
        "metrics": metrics,
        "artifacts": result["artifacts"],
    }
    validate_run_record(record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=RESULTS)
    parser.add_argument("--implementation", action="append", choices=IMPLEMENTATIONS)
    parser.add_argument("--policy", action="append", choices=tuple(POLICIES))
    args = parser.parse_args()
    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    implementations = args.implementation or IMPLEMENTATIONS
    policies = args.policy or list(POLICIES)
    records = []
    for case in fixture_cases():
        for implementation_id in implementations:
            for policy_id in policies:
                records.append(make_record(implementation_id, case, policy_id, run_policy(implementation_id, case, policy_id)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n" for record in sorted(records, key=lambda row: row["run_id"])), encoding="utf-8")
    print(f"wrote {len(records)} B32 records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
