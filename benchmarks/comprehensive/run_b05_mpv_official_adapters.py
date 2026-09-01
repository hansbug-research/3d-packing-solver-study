#!/usr/bin/env python3
"""Run non-PackingSolver adapters on the MPV official-generator-derived track.

This is a supplemental protocol-v4 candidate runner.  Fixed-orientation runs
and all-rotation geometry projections are emitted separately, so results are
never used to claim the original MPV archive has been recovered.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from time import perf_counter
from typing import Any

from generate_mpv_official import DEFAULT_OUTPUT


ROOT = Path(__file__).resolve().parents[2]
RUNNER = Path(__file__).resolve()
PYTHON_WORKER = RUNNER.with_name("b05_mpv_python_worker.py")
PYTHON = ROOT / ".venv" / "bin" / "python"
GO = Path("/tmp/packing-crosslang-go-build/crosslang_go_bp3d")
RUST = Path("/tmp/packing-crosslang-u-build/target/release/crosslang-rust-unesting")
GO_COMMIT = "0ba3dcda7ab334c19b0979b1cf1fa05e09f33bc7"
RUST_COMMIT = "8cde85b029e4ade663185dacb93fd74440af170d"
JERRY_COMMIT = "75764a2b8a5c8e0a6713a4f672c0a8ff81b1107a"
RUST_STRATEGIES = ("extremepoint", "bottomleftfill", "ga", "brkga", "sa")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def resource_value(path: Path, label: str) -> int | None:
    if not path.exists():
        return None
    prefix = f"\t{label}: "
    for line in path.read_text(errors="replace").splitlines():
        if line.startswith(prefix):
            try:
                return int(line.removeprefix(prefix)) * 1024 if "kbytes" in label else int(line.removeprefix(prefix))
            except ValueError:
                return None
    return None


def load_cases(corpus: Path) -> list[tuple[dict[str, Any], str]]:
    manifest = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("corpus") != "MPV_OFFICIAL_GENERATOR_DERIVED":
        raise ValueError("not the MPV official-generator-derived corpus")
    cases: list[tuple[dict[str, Any], str]] = []
    for row in manifest["instances"]:
        path = corpus / row["path"]
        if sha256(path) != row["sha256"]:
            raise ValueError(f"input hash mismatch: {path}")
        cases.append((json.loads(path.read_text(encoding="utf-8")), row["sha256"]))
    if len(cases) != 150:
        raise ValueError(f"expected 150 cases, got {len(cases)}")
    return sorted(cases, key=lambda value: value[0]["instance_id"])


def adapter_input(case: dict[str, Any], pose: str) -> dict[str, Any]:
    container = case["container"]
    items = case["items"]
    return {
        "scenario": case["instance_id"],
        "bins": [
            {"id": f"bin-{index:03d}", "size": container, "max_weight": 1_000_000_000, "cost": 1}
            for index in range(len(items))
        ],
        "items": [
            {"id": item["id"], "size": item["size"], "weight": 1, "orientation_requirement": pose}
            for item in items
        ],
    }


def normalize_placements(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for placement in payload.get("placements", []):
        position = placement.get("position", [placement.get("x", 0), placement.get("y", 0), placement.get("z", 0)])
        size = placement.get("size", [placement.get("dx", 0), placement.get("dy", 0), placement.get("dz", 0)])
        result.append({
            "item_id": str(placement["item_id"]),
            "bin_id": str(placement.get("bin_id", "bin-000")),
            "position": [float(value) for value in position],
            "size": [float(value) for value in size],
        })
    return result


def validate(case: dict[str, Any], placements: list[dict[str, Any]], pose: str) -> dict[str, Any]:
    errors: list[str] = []
    expected = {item["id"]: tuple(float(value) for value in item["size"]) for item in case["items"]}
    container = tuple(float(value) for value in case["container"])
    seen: set[str] = set()
    tolerance = 1e-7
    by_bin: dict[str, list[dict[str, Any]]] = {}
    for index, placement in enumerate(placements):
        item_id = placement["item_id"]
        if item_id not in expected:
            errors.append(f"placement {index}: unknown item {item_id}")
            continue
        if item_id in seen:
            errors.append(f"placement {index}: duplicate item {item_id}")
            continue
        seen.add(item_id)
        size = tuple(placement["size"])
        allowed = {expected[item_id]} if pose == "fixed" else set(itertools.permutations(expected[item_id]))
        if size not in allowed:
            errors.append(f"placement {index}: forbidden orientation {size} for {item_id}")
        coordinates = tuple(placement["position"])
        if min(*coordinates, *size) < -tolerance:
            errors.append(f"placement {index}: negative coordinate/dimension")
        if any(coordinate + dimension > limit + tolerance for coordinate, dimension, limit in zip(coordinates, size, container)):
            errors.append(f"placement {index}: exceeds bin boundary")
        by_bin.setdefault(placement["bin_id"], []).append(placement)
    for bin_id, boxes in by_bin.items():
        for left, right in itertools.combinations(boxes, 2):
            separated = any(
                left["position"][axis] + left["size"][axis] <= right["position"][axis] + tolerance
                or right["position"][axis] + right["size"][axis] <= left["position"][axis] + tolerance
                for axis in range(3)
            )
            if not separated:
                errors.append(f"overlap in {bin_id}: {left['item_id']} / {right['item_id']}")
    complete = len(seen) == len(expected)
    return {
        "status": "PASS" if not errors and complete else "FAIL",
        "errors": errors,
        "packed_items": len(seen),
        "required_items": len(expected),
        "bins_used": len(by_bin),
        "packed_volume": sum(size[0] * size[1] * size[2] for item_id, size in expected.items() if item_id in seen),
        "complete": complete,
    }


def command_for(implementation: str, input_path: Path, strategy: str, budget_s: float) -> list[str]:
    if implementation in {"py3dbp", "jerry"}:
        return [str(PYTHON), str(PYTHON_WORKER), "--implementation", implementation, "--input", str(input_path)]
    if implementation == "go_bp3d":
        return [str(GO), "--input", str(input_path)]
    return [str(RUST), "--input", str(input_path), strategy, str(round(budget_s * 1000))]


def metadata_for(implementation: str, strategy: str, pose: str) -> dict[str, Any]:
    if implementation == "py3dbp":
        return {"implementation_id": "py3dbp", "algorithm": "pivot greedy", "version": "py3dbp-1.1.2", "track": "COMPOSED", "scope": "GEOMETRY_PROJECTION"}
    if implementation == "jerry":
        return {"implementation_id": "jerry", "algorithm": "Jerry pivot/fix-point greedy", "version": JERRY_COMMIT, "track": "COMPOSED", "scope": "GEOMETRY_PROJECTION"}
    if implementation == "go_bp3d":
        return {"implementation_id": "go_bp3d", "algorithm": "pivot greedy", "version": GO_COMMIT, "track": "COMPOSED", "scope": "GEOMETRY_PROJECTION"}
    return {
        "implementation_id": f"rust_{'layer' if strategy == 'bottomleftfill' else strategy}",
        "algorithm": strategy,
        "version": RUST_COMMIT,
        "track": "COMPOSED",
        "scope": "FULL_PROBLEM" if pose == "fixed" else "GEOMETRY_PROJECTION",
    }


def run_one(
    case: dict[str, Any],
    source_hash: str,
    implementation: str,
    strategy: str,
    pose: str,
    budget_s: float,
    work_root: Path,
    archive_name: str,
    runner_sha: str,
) -> dict[str, Any]:
    info = metadata_for(implementation, strategy, pose)
    case_name = f"{case['instance_id']}__{info['implementation_id']}__{pose}__{budget_s:g}s"
    case_dir = work_root / case_name
    case_dir.mkdir(parents=True, exist_ok=True)
    payload = adapter_input(case, pose)
    input_path = case_dir / "input.json"
    output_path = case_dir / "output.json"
    stderr_path = case_dir / "stderr.log"
    resource_path = case_dir / "resources.txt"
    validation_path = case_dir / "validation.json"
    config_path = case_dir / "effective-config.json"
    input_path.write_text(canonical_json(payload), encoding="utf-8")
    command = command_for(implementation, input_path, strategy, budget_s)
    config_path.write_text(canonical_json({
        "command": command,
        "implementation": info,
        "pose": pose,
        "time_limit_s": budget_s,
        "thread_limit": 1,
        "input_source_sha256": source_hash,
        "runner_sha256": runner_sha,
    }), encoding="utf-8")
    environment = os.environ.copy()
    environment.update({
        "GOMAXPROCS": "1", "RAYON_NUM_THREADS": "1", "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1", "PYTHONHASHSEED": "0",
    })
    started = perf_counter()
    try:
        completed = subprocess.run(
            ["/usr/bin/time", "-v", "-o", str(resource_path), "timeout", "--signal=TERM", "--kill-after=1s", str(budget_s + 1), *command],
            capture_output=True,
            text=True,
            timeout=budget_s + 5,
            env=environment,
        )
        returncode, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
    except subprocess.TimeoutExpired as exc:
        returncode = 124
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
    wall_s = perf_counter() - started
    stderr_path.write_text(stderr, encoding="utf-8")
    payload_out: dict[str, Any] | None = None
    try:
        payload_out = json.loads(stdout) if returncode == 0 else None
    except json.JSONDecodeError:
        pass
    selected_order = "SOURCE"
    candidate_count = 1
    candidate_invalid_count = 0
    if implementation in {"py3dbp", "jerry"} and payload_out is not None:
        candidates = payload_out.get("candidates", [])
        candidate_count = len(candidates)
        evaluated = []
        for candidate in candidates:
            placements = normalize_placements({"placements": candidate.get("placements", [])})
            evaluated.append((candidate, placements, validate(case, placements, pose)))
        candidate_invalid_count = sum(result[2]["status"] != "PASS" for result in evaluated)
        complete = [result for result in evaluated if result[2]["status"] == "PASS"]
        candidates_to_choose = complete or evaluated
        if candidates_to_choose:
            candidate, placements, validation = min(
                candidates_to_choose,
                key=lambda result: (-result[2]["packed_items"], result[2]["bins_used"], result[0].get("solver_s", float("inf")), result[0].get("item_order", "")),
            )
            selected_order = candidate.get("item_order", "SOURCE")
        else:
            placements, validation = [], validate(case, [], pose)
        payload_out["selected_order"] = selected_order
    else:
        placements = normalize_placements(payload_out or {})
        validation = validate(case, placements, pose)
    if payload_out is not None:
        output_path.write_text(canonical_json(payload_out), encoding="utf-8")
    validation_path.write_text(canonical_json(validation), encoding="utf-8")
    if returncode in {124, 137, -9, -15}:
        run_status, termination = "TIME_LIMIT", "EXTERNAL_TIME_LIMIT"
    elif returncode != 0 or payload_out is None:
        run_status, termination = "ERROR", "PROCESS_OR_OUTPUT_ERROR"
    else:
        run_status, termination = "COMPLETED", "RETURNED_CERTIFICATE"
    if validation["status"] == "PASS":
        solution_status = "VALID_COMPLETE"
    elif validation["packed_items"] == 0:
        solution_status = "NO_SOLUTION"
    else:
        solution_status = "INVALID_CERTIFICATE" if validation["errors"] else "NO_SOLUTION"
    record = {
        "schema_version": 1,
        "record_kind": "SUPPLEMENTAL_ADAPTER_RUN",
        "protocol_version": "benchmark-protocol/3-supplemental",
        "benchmark_id": "B05-MPV-OFFICIAL-GEN",
        "problem_variant": "FIXED_XYZ" if pose == "fixed" else "RELAXED_ALL_ROTATIONS",
        "instance_id": case["instance_id"],
        "implementation_id": info["implementation_id"],
        "algorithm": info["algorithm"],
        "implementation_version": info["version"],
        "adapter": "b05_mpv_official_adapter_v1",
        "comparison_track": info["track"],
        "problem_scope": info["scope"],
        "budget": {"time_limit_s": budget_s, "memory_limit_bytes": 1073741824, "thread_limit": 1},
        "item_order": selected_order,
        "seed": 42 if implementation == "rust_unesting" else None,
        "input_source_sha256": source_hash,
        "input_adapter_sha256": hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest(),
        "run_status": run_status,
        "solution_status": solution_status,
        "termination_reason": termination if solution_status != "NO_SOLUTION" else "NO_FEASIBLE_COMPLETE_CERTIFICATE",
        "resources": {
            "wall_s": wall_s,
            "solver_s": payload_out.get("elapsed_s") if payload_out else None,
            "peak_rss_bytes": resource_value(resource_path, "Maximum resident set size (kbytes)"),
        },
        "metrics": {
            **{key: validation[key] for key in ("packed_items", "required_items", "bins_used", "packed_volume")},
            "validation_error_count": len(validation["errors"]),
            "candidate_count": candidate_count,
            "candidate_invalid_count": candidate_invalid_count,
            "projection_removed_constraints": [] if pose == "fixed" else ["fixed_orientation"],
        },
        "artifacts": {
            "input": f"{archive_name}#{case_name}/input.json",
            "effective_config": f"{archive_name}#{case_name}/effective-config.json",
            "solver_output": f"{archive_name}#{case_name}/output.json" if output_path.exists() else None,
            "stderr": f"{archive_name}#{case_name}/stderr.log",
            "resources": f"{archive_name}#{case_name}/resources.txt" if resource_path.exists() else None,
            "validation": f"{archive_name}#{case_name}/validation.json",
        },
    }
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--implementation", choices=("py3dbp", "jerry", "go_bp3d", "rust_unesting"), required=True)
    parser.add_argument("--strategy", choices=RUST_STRATEGIES, default="extremepoint")
    parser.add_argument("--pose", choices=("fixed", "any"), required=True)
    parser.add_argument("--time-limit", type=float, choices=(1.0, 10.0), required=True)
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--label", required=True)
    parser.add_argument("--results-root", type=Path, default=ROOT / "results/comprehensive/runs")
    parser.add_argument("--raw-root", type=Path, default=ROOT / "raw/experiments/comprehensive")
    args = parser.parse_args()
    if args.implementation in {"py3dbp", "jerry"} and args.pose != "any":
        raise SystemExit("py3dbp/Jerry cannot represent fixed orientation; use --pose any projection")
    if args.implementation == "go_bp3d" and args.pose != "any":
        raise SystemExit("Go bp3d worker cannot enforce fixed orientation; use --pose any projection")
    if args.implementation == "go_bp3d" and not GO.is_file():
        raise SystemExit(f"missing Go worker: {GO}")
    if args.implementation == "rust_unesting" and not RUST.is_file():
        raise SystemExit(f"missing Rust worker: {RUST}")
    if args.implementation in {"py3dbp", "jerry"} and not PYTHON.is_file():
        raise SystemExit(f"missing Python environment: {PYTHON}")
    cases = load_cases(args.corpus)
    if args.limit:
        cases = cases[:args.limit]
    args.results_root.mkdir(parents=True, exist_ok=True)
    raw_dir = args.raw_root / "B05-MPV-GEN-adapters" / args.label
    raw_dir.mkdir(parents=True, exist_ok=True)
    archive = raw_dir / "artifacts.tar.gz"
    archive_name = str(archive.relative_to(ROOT))
    runner_sha = sha256(RUNNER)
    with tempfile.TemporaryDirectory(prefix=f"b05-mpv-{args.label}-") as temp_name:
        work_root = Path(temp_name)
        records: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = [executor.submit(run_one, case, source_hash, args.implementation, args.strategy, args.pose, args.time_limit, work_root, archive_name, runner_sha) for case, source_hash in cases]
            for count, future in enumerate(as_completed(futures), 1):
                records.append(future.result())
                if count % 25 == 0 or count == len(futures):
                    print(f"{args.label}: {count}/{len(futures)}", flush=True)
        with tarfile.open(archive, "w:gz") as handle:
            for path in sorted(work_root.rglob("*")):
                if path.is_file():
                    handle.add(path, arcname=path.relative_to(work_root))
    records.sort(key=lambda row: row["instance_id"])
    output = args.results_root / f"{args.label}.jsonl"
    output.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in records), encoding="utf-8")
    metadata = {
        "schema_version": 1,
        "benchmark_id": "B05-MPV-OFFICIAL-GEN",
        "label": args.label,
        "records": len(records),
        "implementation": args.implementation,
        "strategy": args.strategy,
        "pose": args.pose,
        "time_limit_s": args.time_limit,
        "runner_sha256": runner_sha,
        "output_sha256": sha256(output),
        "artifact_sha256": sha256(archive),
    }
    (raw_dir / "metadata.json").write_text(canonical_json(metadata), encoding="utf-8")
    print(output.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
