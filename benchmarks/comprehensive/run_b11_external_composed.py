#!/usr/bin/env python3
"""Run the B11 open-X fixtures through non-native geometry engines.

The external engines do not expose an open-dimension objective.  This runner
therefore performs an explicit outer search over integer X bounds and chooses
the shortest independently validated complete certificate.  Source pose flags
are deliberately relaxed to ``any`` and every result is recorded as
``PROJECTION_ONLY``; the number is not a native open-X score.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks"))
SOURCE = ROOT / "benchmarks/data/comprehensive/b11-open-dimension/source.json"
PYTHON = ROOT / ".venv/bin/python"
if not PYTHON.exists():
    PYTHON = Path(sys.executable)
GO = Path("/tmp/packing-crosslang-go-build/crosslang_go_bp3d")
RUST = Path("/tmp/packing-crosslang-u-build/target/release/crosslang-rust-unesting")
RUST_STRATEGIES = {
    "rust_extreme_point": "extremepoint",
    "rust_layer": "bottomleftfill",
    "rust_ga": "ga",
    "rust_brkga": "brkga",
    "rust_sa": "sa",
}
IMPLEMENTATIONS = ("py3dbp", "jerry", "go_bp3d", *RUST_STRATEGIES)
GO_COMMIT = "0ba3dcda7ab334c19b0979b1cf1fa05e09f33bc7"
RUST_COMMIT = "8cde85b029e4ade663185dacb93fd74440af170d"
JERRY_COMMIT = "75764a2b8a5c8e0a6713a4f672c0a8ff81b1107a"
RUNNER = Path(__file__).resolve()
VALIDATOR = ROOT / "benchmarks/validation.py"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def load_cases() -> list[dict[str, Any]]:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    return payload["cases"]


def python_input(case: dict[str, Any], length: int) -> dict[str, Any]:
    return {"instance": {
        "family": "B11_OPEN_DIMENSION_PROJECTION",
        "instance_id": 1,
        "problem_kind": "single_container_knapsack",
        "objective": "maximize_packed_volume",
        "container": [length, case["bin"]["size"][1], case["bin"]["size"][2]],
        "seed": 42,
        "source_line_errors": [],
        "item_types": [{
            "type_id": item["id"], "size": item["size"],
            "allowed_vertical_dimensions": [1, 1, 1], "copies": 1,
        } for item in case["items"]],
    }}


def external_input(case: dict[str, Any], length: int) -> dict[str, Any]:
    return {
        "scenario": f"B11-{case['id']}",
        "bins": [{"id": "bin-000", "size": [length, case["bin"]["size"][1], case["bin"]["size"][2]], "max_weight": 100000.0, "cost": 1.0}],
        "items": [{"id": item["id"], "size": item["size"], "weight": item.get("weight", 1.0), "orientation_requirement": "any"} for item in case["items"]],
    }


def normalize(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for raw in payload.get("placements", []):
        position = raw.get("position", [raw.get("x", 0), raw.get("y", 0), raw.get("z", 0)])
        size = raw.get("size", [raw.get("dx", 0), raw.get("dy", 0), raw.get("dz", 0)])
        result.append({"item_id": str(raw.get("item_id", "")), "bin_id": str(raw.get("bin_id", "bin-000")),
                       "position": [float(v) for v in position], "size": [float(v) for v in size]})
    return result


def overlaps(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return all(left["position"][axis] < right["position"][axis] + right["size"][axis]
               and right["position"][axis] < left["position"][axis] + left["size"][axis] for axis in range(3))


def validate(case: dict[str, Any], length: int, placements: list[dict[str, Any]]) -> dict[str, Any]:
    expected = {str(item["id"]): tuple(float(v) for v in item["size"]) for item in case["items"]}
    errors: list[str] = []
    seen: set[str] = set()
    for placement in placements:
        raw_item_id = placement["item_id"]
        # py3dbp expands a type with one copy to ``type:0`` while the
        # cross-language workers retain the source type ID.
        item_id = raw_item_id if raw_item_id in expected else raw_item_id.rsplit(":", 1)[0]
        if item_id not in expected:
            errors.append(f"unknown item {raw_item_id}")
            continue
        if item_id in seen:
            errors.append(f"duplicate item {item_id}")
        seen.add(item_id)
        if any(value < -1e-7 for value in placement["position"]):
            errors.append(f"{item_id}: negative position")
        if placement["position"][0] + placement["size"][0] > length + 1e-7:
            errors.append(f"{item_id}: X bound")
        if placement["position"][1] + placement["size"][1] > case["bin"]["size"][1] + 1e-7:
            errors.append(f"{item_id}: Y bound")
        if placement["position"][2] + placement["size"][2] > case["bin"]["size"][2] + 1e-7:
            errors.append(f"{item_id}: Z bound")
        if sorted(placement["size"]) != sorted(expected[item_id]):
            errors.append(f"{item_id}: invalid orientation dimensions")
    if len(seen) != len(expected):
        errors.append(f"incomplete: {len(seen)} of {len(expected)}")
    for index, left in enumerate(placements):
        for right in placements[index + 1:]:
            if left["item_id"] in expected and right["item_id"] in expected and overlaps(left, right):
                errors.append(f"overlap {left['item_id']}/{right['item_id']}")
    used = max((p["position"][0] + p["size"][0] for p in placements), default=0.0)
    return {"status": "PASS" if not errors else "FAIL", "errors": errors,
            "complete": not errors, "used_length": used, "packed_items": len(seen),
            "required_items": len(expected)}


def command_for(implementation: str, input_path: Path, time_limit: float) -> list[str]:
    if implementation in {"py3dbp", "jerry"}:
        command = [str(PYTHON), str(ROOT / "benchmarks/campaign/python_thpack/worker.py"), "--library", implementation,
                   "--input", str(input_path), "--order", "descending", "--projection"]
        if implementation == "jerry":
            command += ["--jerry-fix-point", "false"]
        return command
    if implementation == "go_bp3d":
        return [str(GO), "--input", str(input_path)]
    return [str(RUST), "--input", str(input_path), RUST_STRATEGIES[implementation], str(max(1, round(time_limit * 1000)))]


def run_candidate(implementation: str, case: dict[str, Any], length: int, time_limit: float, directory: Path) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)
    input_payload = python_input(case, length) if implementation in {"py3dbp", "jerry"} else external_input(case, length)
    input_path = directory / "input.json"
    stdout_path = directory / "stdout.json"
    stderr_path = directory / "stderr.log"
    input_path.write_text(canonical(input_payload), encoding="utf-8")
    started = perf_counter()
    timed_out = False
    try:
        completed = subprocess.run(command_for(implementation, input_path, time_limit), capture_output=True, text=True,
                                   timeout=max(2.0, time_limit + 1.0), env={**os.environ, "OMP_NUM_THREADS": "1", "RAYON_NUM_THREADS": "1", "GOMAXPROCS": "1"}, check=False)
        stdout, stderr = completed.stdout, completed.stderr
        return_code = completed.returncode
    except subprocess.TimeoutExpired as exc:
        stdout, stderr, return_code, timed_out = exc.stdout or "", exc.stderr or "", None, True
    wall = perf_counter() - started
    stdout_path.write_text(stdout if isinstance(stdout, str) else stdout.decode(errors="replace"), encoding="utf-8")
    stderr_path.write_text(stderr if isinstance(stderr, str) else stderr.decode(errors="replace"), encoding="utf-8")
    try:
        payload = json.loads(stdout_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        payload = {"placements": []}
    placements = normalize(payload)
    validation = validate(case, length, placements)
    (directory / "validation.json").write_text(canonical(validation), encoding="utf-8")
    return {"length": length, "wall_s": wall, "returncode": return_code, "timed_out": timed_out,
            "placements": placements, "validation": validation, "payload": payload}


def run_one(implementation: str, case: dict[str, Any], time_limit: float, work_root: Path, archive: str) -> dict[str, Any]:
    started = perf_counter()
    candidate_results = []
    # All source dimensions are integral.  Searching every integer bound is
    # small, deterministic, and avoids baking a heuristic lower bound into
    # the result.
    for length in range(max(1, max(min(item["size"]) for item in case["items"])), int(case["bin"]["size"][0]) + 1):
        candidate = run_candidate(implementation, case, length, time_limit, work_root / case["id"] / implementation / f"x-{length:03d}")
        candidate_results.append(candidate)
    valid = [candidate for candidate in candidate_results if candidate["validation"]["complete"]]
    selected = min(valid, key=lambda candidate: (candidate["validation"]["used_length"], candidate["length"])) if valid else None
    if selected:
        selected_validation = selected["validation"]
        solution_status, run_status, proof = "VALID_COMPLETE", "COMPLETED", "FEASIBLE"
        termination = "COMPOSED_OUTER_SEARCH"
    else:
        selected_validation = {"status": "FAIL", "errors": ["no complete valid candidate"], "complete": False,
                              "used_length": None, "packed_items": 0, "required_items": len(case["items"])}
        solution_status = "NO_SOLUTION"
        run_status = "TIME_LIMIT" if any(candidate["timed_out"] for candidate in candidate_results) else "ERROR"
        proof, termination = "UNKNOWN", "NO_VALID_CANDIDATE"
    case_dir = work_root / case["id"] / implementation
    (case_dir / "selected.json").write_text(canonical(selected or selected_validation), encoding="utf-8")
    source_payload = {"benchmark_id": "B11", "case": case, "search": {"min_length": max(1, max(min(item["size"]) for item in case["items"])), "max_length": int(case["bin"]["size"][0]), "candidate_time_limit_s": time_limit}}
    input_hash = digest(source_payload)
    metrics = {"used_length": selected_validation.get("used_length"), "open_dimension_bound": selected_validation.get("used_length"),
               "packed_items": selected_validation.get("packed_items", 0), "required_items": selected_validation.get("required_items", len(case["items"])),
               "candidate_count": len(candidate_results), "valid_candidate_count": len(valid), "validation_error_count": len(selected_validation.get("errors", [])),
               "projection_removed_constraints": ["source_fixed_xyz_pose"], "outer_search": "integer_X_bound_minimize_validated_used_extent",
               "candidate_time_limit_s": time_limit, "source_commit": "d953148b8f710c06fa6c410949b7272f9e36327b", "source_scope": "REPOSITORY_FIXTURE_DERIVED_FROM_FORK_TESTS",
               "implementation_commit": GO_COMMIT if implementation == "go_bp3d" else RUST_COMMIT if implementation.startswith("rust_") else JERRY_COMMIT if implementation == "jerry" else "py3dbp-1.1.2"}
    from comprehensive.model import load_catalogs, validate_run_record
    _, implementations = load_catalogs()
    catalog = next(row for row in implementations["implementations"] if row["id"] == implementation)
    record = {"schema_version": 2, "protocol_version": "benchmark-protocol/3", "record_origin": "PROTOCOL_V3",
              "run_id": f"B11/{case['id']}/{implementation}/composed/rep-0", "benchmark_id": "B11", "problem_variant": "OPEN_DIMENSION_X_PROJECTION",
              "instance_id": case["id"], "implementation_id": implementation, "algorithm": catalog["algorithm"], "adapter": "b11_open_dimension_outer_search_v1",
              "comparison_track": "COMPOSED", "problem_scope": "GEOMETRY_PROJECTION", "budget": {"time_limit_s": time_limit, "memory_limit_bytes": 1073741824, "thread_limit": 1},
              "item_order": "SOURCE", "bin_order": "SOURCE", "seed": 42, "repetition": 0, "input_sha256": input_hash, "input_status": "VALID",
              "capability_status": "PROJECTION_ONLY", "run_status": run_status, "solution_status": solution_status, "proof_status": proof,
              "termination_reason": termination, "resources": {"wall_s": perf_counter() - started, "solver_s": sum(candidate["wall_s"] for candidate in candidate_results), "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024},
              "metrics": metrics, "artifacts": {"input": f"{archive}#{case['id']}/{implementation}/source-input.json", "effective_config": f"{archive}#{case['id']}/{implementation}/effective-config.json",
              "solver_output": f"{archive}#{case['id']}/{implementation}/selected.json", "solution": f"{archive}#{case['id']}/{implementation}/selected.json", "validation": f"{archive}#{case['id']}/{implementation}/selected.json"}}
    (case_dir / "source-input.json").write_text(canonical(source_payload), encoding="utf-8")
    (case_dir / "effective-config.json").write_text(canonical({"benchmark_id": "B11", "implementation_id": implementation, "candidate_time_limit_s": time_limit,
                                                                  "search_policy": metrics["outer_search"], "runner_sha256": sha256(RUNNER), "validator_sha256": sha256(VALIDATOR), "input_sha256": input_hash}), encoding="utf-8")
    validate_run_record(record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--implementation", action="append", choices=IMPLEMENTATIONS)
    parser.add_argument("--time-limit", type=float, default=0.2)
    parser.add_argument("--results-root", type=Path, default=ROOT / "results/comprehensive")
    parser.add_argument("--raw-root", type=Path, default=ROOT / "raw/experiments/comprehensive")
    args = parser.parse_args()
    implementations = args.implementation or list(IMPLEMENTATIONS)
    required = {"py3dbp": PYTHON, "go_bp3d": GO, "jerry": ROOT / ".cache/jerry-3d-bin-packing", **{key: RUST for key in RUST_STRATEGIES}}
    for implementation in implementations:
        if not required[implementation].exists():
            raise SystemExit(f"missing dependency for {implementation}: {required[implementation]}")
    raw_dir = args.raw_root / "B11-external-composed"
    raw_dir.mkdir(parents=True, exist_ok=True)
    archive_path = raw_dir / "artifacts.tar.gz"
    archive = str(archive_path.relative_to(ROOT))
    with tempfile.TemporaryDirectory(prefix="b11-external-") as temporary:
        work_root = Path(temporary)
        records = [run_one(implementation, case, args.time_limit, work_root, archive) for case in load_cases() for implementation in implementations]
        with tarfile.open(archive_path, "w:gz") as handle:
            for path in sorted(work_root.rglob("*")):
                if path.is_file():
                    handle.add(path, arcname=path.relative_to(work_root))
    output = args.results_root / "runs/B11-external-composed.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n" for record in sorted(records, key=lambda row: row["run_id"])), encoding="utf-8")
    (raw_dir / "metadata.json").write_text(canonical({"schema_version": 1, "protocol_version": "benchmark-protocol/3", "benchmark_id": "B11", "implementations": implementations,
                                                         "runner_sha256": sha256(RUNNER), "validator_sha256": sha256(VALIDATOR), "run_jsonl_sha256": sha256(output), "artifact_archive_sha256": sha256(archive_path),
                                                         "adapter_semantics": "COMPOSED_GEOMETRY_PROJECTION_OUTER_SEARCH"}), encoding="utf-8")
    print(output.relative_to(ROOT))
    return 0 if all(record["solution_status"] == "VALID_COMPLETE" for record in records) else 2


if __name__ == "__main__":
    raise SystemExit(main())
