from __future__ import annotations

"""Run protocol-v3 reliability cases against every executable candidate.

The suite uses repository-owned, hashable fixtures.  It deliberately records
adapter/process failures instead of turning them into status-only rows.
"""

import argparse
import csv
import hashlib
import json
import math
import os
import resource
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results" / "comprehensive" / "runs" / "reliability-v3.jsonl"
RAW = ROOT / "raw" / "experiments" / "comprehensive" / "reliability-v3"
sys.path.insert(0, str(ROOT / "benchmarks"))
sys.path.insert(0, str(ROOT / "benchmarks" / "comprehensive"))
sys.path.insert(0, str(ROOT / "benchmarks" / "campaign"))
from model import load_catalogs, validate_run_record  # noqa: E402


IMPLEMENTATIONS = [row for row in load_catalogs()[1]["implementations"]]
BY_ID = {row["id"]: row for row in IMPLEMENTATIONS}
PS_BINARIES = {
    "packingsolver_fork_box": ROOT / ".cache/build-fork/src/box/packingsolver_box",
    "packingsolver_fork_boxstacks": ROOT / ".cache/build-fork/src/boxstacks/packingsolver_boxstacks",
    "packingsolver_upstream_box": ROOT / ".cache/build-upstream-367/src/box/packingsolver_box",
    "packingsolver_upstream_boxstacks": ROOT / ".cache/build-upstream-367/src/boxstacks/packingsolver_boxstacks",
}
GO = Path("/tmp/packing-crosslang-go-build/crosslang_go_bp3d")
RUST = Path("/tmp/packing-crosslang-u-build/target/release/crosslang-rust-unesting")
JAVA_CLASSES = ROOT / "benchmarks/java-skjolber/target/classes"
JAVA_CP = ROOT / "benchmarks/java-skjolber/classpath.txt"
PYTHON = ROOT / ".venv/bin/python"
if not PYTHON.exists():
    PYTHON = Path(sys.executable)
RUNNER_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def fixture(variant: str, count: int = 8, scale: int = 1) -> dict[str, Any]:
    if variant.startswith("cost_"):
        bins = [
            {"id": "small-0", "size": [6, 5, 5], "max_weight": 100.0, "cost": 5.0},
            {"id": "small-1", "size": [6, 5, 5], "max_weight": 100.0, "cost": 5.0},
            {"id": "large-0", "size": [12, 5, 5], "max_weight": 100.0, "cost": 20.0},
        ]
        if variant == "cost_permuted":
            bins.reverse()
        if variant == "cost_scaled":
            for item in bins:
                item["cost"] *= 7.0
        return {"scenario": f"reliability-{variant}", "bins": bins,
                "items": [{"id": "cost-0", "size": [6, 5, 5], "weight": 1.0, "orientation_requirement": "any"},
                          {"id": "cost-1", "size": [6, 5, 5], "weight": 1.0, "orientation_requirement": "any"}]}
    size = [5 * scale] * 3
    if variant == "axis_swap":
        size = [size[1], size[0], size[2]]
    ids = [f"cube-{i}" for i in range(count)]
    if variant == "renamed":
        ids = [f"renamed-{i}" for i in range(count)]
    if variant == "permuted":
        ids.reverse()
    return {
        "scenario": f"reliability-{variant}-{count}-{scale}",
        "bins": [{"id": f"bin-{i:03d}", "size": [10 * scale] * 3, "max_weight": float(count + 1), "cost": 1.0}
                 for i in range(max(1, math.ceil(count / 8)))],
        "items": [{"id": item_id, "size": size, "weight": 1.0, "orientation_requirement": "any"} for item_id in ids],
    }


def python_input(spec: dict[str, Any], multi: bool) -> dict[str, Any]:
    return {"instance": {"family": "RELIABILITY", "instance_id": 1, "problem_kind":
            "multi_container_bin_packing" if multi else "single_container_knapsack",
            "objective": "minimize_bins", "container": spec["bins"][0]["size"], "seed": 42,
            "source_line_errors": [], "item_types": [
                {"type_id": item["id"], "size": item["size"], "allowed_vertical_dimensions": [1, 1, 1], "copies": 1}
                for item in spec["items"]]}}


def write_artifacts(run_id: str, spec: Any, stdout: str, stderr: str, validation: dict[str, Any], extra: dict[str, Path] | None = None) -> dict[str, str]:
    safe = run_id.replace("/", "_")
    directory = RAW / safe
    directory.mkdir(parents=True, exist_ok=True)
    input_path = directory / "input.json"
    stdout_path = directory / "stdout.log"
    stderr_path = directory / "stderr.log"
    validation_path = directory / "validation.json"
    input_path.write_text(json.dumps(spec, indent=2) + "\n")
    stdout_path.write_text(stdout)
    stderr_path.write_text(stderr)
    validation_path.write_text(json.dumps(validation, indent=2, sort_keys=True) + "\n")
    artifacts = {"input": str(input_path.relative_to(ROOT)), "stdout": str(stdout_path.relative_to(ROOT)),
                 "stderr": str(stderr_path.relative_to(ROOT)), "validation": str(validation_path.relative_to(ROOT))}
    for name, source in (extra or {}).items():
        if source.exists() and source.is_file():
            destination = directory / name
            shutil.copyfile(source, destination)
            artifacts[name] = str(destination.relative_to(ROOT))
    return artifacts


def parse_packingsolver_certificate(cert: Path, spec: dict[str, Any]) -> dict[str, Any]:
    """Resolve certificate row/index IDs to the canonical fixture IDs."""
    available = list(range(len(spec["bins"])))
    bin_tokens: dict[str, str] = {}
    with cert.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        if row.get("TYPE") != "BIN":
            continue
        token = str(row.get("BIN", ""))
        dims = tuple(float(row.get(key, 0) or 0) for key in ("LX", "LY", "LZ"))
        match = next((index for index in available if tuple(float(x) for x in spec["bins"][index]["size"]) == dims), None)
        if match is None:
            bin_tokens[token] = f"__certificate_bin_{token}"
        else:
            bin_tokens[token] = spec["bins"][match]["id"]
            available.remove(match)
    item_rows = [row for row in rows if row.get("TYPE") == "ITEM"]
    placements = []
    for ordinal, row in enumerate(item_rows):
        item_token = str(row.get("ID", ""))
        try:
            item_index = int(item_token)
        except ValueError:
            item_index = ordinal
        item_id = spec["items"][item_index]["id"] if 0 <= item_index < len(spec["items"]) else item_token
        placements.append({
            "item_id": item_id,
            "bin_id": bin_tokens.get(str(row.get("BIN", "")), str(row.get("BIN", ""))),
            "position": [float(row.get(key, 0) or 0) for key in ("X", "Y", "Z")],
            "size": [float(row.get(key, 0) or 0) for key in ("LX", "LY", "LZ")],
        })
    return {"placements": placements}


def basic_payload(payload: dict[str, Any], spec: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if isinstance(payload.get("placements"), int) and "geometry_valid" in payload:
        placed = int(payload["placements"])
        valid = bool(payload.get("geometry_valid"))
        status = "VALID_COMPLETE" if placed == len(spec["items"]) and valid else "VALID_PARTIAL" if placed and valid else "INVALID_CERTIFICATE" if not valid else "NO_SOLUTION"
        return status, {"placements": placed, "required_items": len(spec["items"]), "bins_used": int(payload.get("bins_used", 0)),
                        "validation_error_count": 0 if valid else 1, "validation_errors": [] if valid else ["library geometry validator failed"],
                        "objective": int(payload.get("bins_used", 0)), "library_reported": payload.get("success")}
    placements = payload.get("placements", [])
    expected = len(spec["items"])
    errors = []
    seen = set()
    bins = {b["id"]: tuple(b["size"]) for b in spec["bins"]}
    normalized_bins: set[str] = set()
    for placement in placements:
        item_id = placement.get("item_id")
        if item_id in seen:
            errors.append(f"duplicate item {item_id}")
        seen.add(item_id)
        bin_id = placement.get("bin_id")
        if bin_id not in bins:
            # Native libraries use either ``bin-000``, ``bin:0`` or a
            # certificate row index.  They are equivalent only after this
            # explicit canonicalization; unknown names still fail closed.
            aliases = {f"bin:{i}": key for i, key in enumerate(bins)}
            aliases.update({str(i): key for i, key in enumerate(bins)})
            bin_id = aliases.get(str(bin_id))
        if bin_id is None or bin_id not in bins:
            errors.append(f"unknown bin {placement.get('bin_id')}")
            continue
        normalized_bins.add(bin_id)
        pos = placement.get("position", [0, 0, 0])
        dim = placement.get("size", [0, 0, 0])
        if any(pos[i] < -1e-7 or pos[i] + dim[i] > bins[bin_id][i] + 1e-7 for i in range(3)):
            errors.append(f"out of bounds {item_id}")
    used_bin_ids = normalized_bins
    total_cost = sum(float(b["cost"]) for b in spec["bins"] if b["id"] in used_bin_ids)
    status = "VALID_COMPLETE" if len(placements) == expected and not errors else "VALID_PARTIAL" if placements and not errors else "INVALID_CERTIFICATE" if errors else "NO_SOLUTION"
    return status, {"placements": len(placements), "required_items": expected, "bins_used": len(used_bin_ids),
                    "validation_error_count": len(errors), "validation_errors": errors, "objective": len(used_bin_ids), "total_cost": total_cost}


def invoke(implementation_id: str, spec: dict[str, Any], variant: str, count: int, scale: int, timeout_s: float = 12.0) -> tuple[str, dict[str, Any], str, str, float, int | None, dict[str, Path]]:
    """Return status, metrics, stdout, stderr, wall seconds, peak RSS."""
    RAW.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="reliability-", dir=str(RAW)))
    input_path = work / "input.json"
    input_path.write_text(json.dumps(spec) + "\n")
    started = perf_counter()
    command: list[str]
    env = os.environ.copy()
    env.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", NUMEXPR_NUM_THREADS="1", RAYON_NUM_THREADS="1", GOMAXPROCS="1")
    if implementation_id.startswith("exact_"):
        try:
            from exact_suite import Bin, Case, Item, _solve_mip, rotations, solve_cp_sat
            items = tuple(Item(item["id"], tuple(int(x) for x in item["size"]), 1, rotations(tuple(int(x) for x in item["size"]))) for item in spec["items"])
            bins = tuple(
                Bin(b["id"], tuple(int(x) for x in b["size"]), int(b["max_weight"]), int(b["cost"]))
                for b in spec["bins"]
            )
            case = Case("reliability", items, bins, "OPTIMAL", None, "protocol reliability fixture")
            started_exact = perf_counter()
            if implementation_id == "exact_cp_sat": result = solve_cp_sat(case, 10.0)
            else: result = _solve_mip(case, implementation_id.removeprefix("exact_"), 10.0)
            wall_exact = perf_counter() - started_exact
            payload = {"placements": [{"item_id": p["item_ref"], "bin_id": p["bin_ref"], "position": [p["x"], p["y"], p["z"]], "size": [p["dx"], p["dy"], p["dz"]]} for p in result.get("placements", [])]}
            status, metrics = basic_payload(payload, spec)
            metrics.update({"objective": result.get("objective"), "bound": result.get("bound"), "gap": result.get("gap"), "proof_status": result.get("status")})
            return status, metrics, json.dumps(result, sort_keys=True), "", wall_exact, None, {}
        except Exception as error:  # preserve backend availability/configuration failures as evidence
            return "ERROR", {"placements": 0, "required_items": len(spec["items"]), "validation_error_count": 1, "validation_errors": [f"exact backend error: {error}"], "objective": None}, "", str(error), perf_counter() - started, None, {}
    if implementation_id in {"py3dbp", "jerry"}:
        input_path.write_text(json.dumps(python_input(spec, len(spec["bins"]) > 1)) + "\n")
        command = [str(PYTHON), str(ROOT / "benchmarks/campaign/python_thpack/worker.py"), "--library", implementation_id,
                   "--input", str(input_path), "--order", "descending", "--projection"]
    elif implementation_id == "go_bp3d":
        command = [str(GO), "--input", str(input_path)]
    elif implementation_id.startswith("rust_"):
        strategy = {"rust_layer": "bottomleftfill", "rust_ga": "ga", "rust_brkga": "brkga", "rust_sa": "sa", "rust_extreme_point": "extremepoint"}[implementation_id]
        command = [str(RUST), "--input", str(input_path), strategy, "10000"]
    elif implementation_id.startswith("packingsolver_"):
        binary = PS_BINARIES[implementation_id]
        items = work / "items.csv"
        bins = work / "bins.csv"
        with items.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["ID", "X", "Y", "Z", "ROTATION_XYZ", "ROTATION_YXZ", "ROTATION_ZYX", "ROTATION_YZX", "ROTATION_XZY", "ROTATION_ZXY", "WEIGHT", "COPIES"])
            for item in spec["items"]:
                writer.writerow([item["id"], *item["size"], 1, 1, 1, 1, 1, 1, 1, 1])
        with bins.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["ID", "X", "Y", "Z", "COST", "COPIES", "MAXIMUM_WEIGHT"])
            for b in spec["bins"]:
                writer.writerow([b["id"], *b["size"], b["cost"], 1, b["max_weight"]])
        cert = work / "solution.csv"
        output = work / "solver.json"
        objective = "variable-sized-bin-packing" if variant.startswith("cost_") else "bin-packing"
        command = [str(binary), "--items", str(items), "--bins", str(bins), "--objective", objective, "--time-limit", "10", "--memory-limit", "512", "--verbosity-level", "0", "--certificate", str(cert), "--output", str(output), "--only-write-at-the-end"]
    elif implementation_id.startswith("skjolber_"):
        classpath = f"{JAVA_CLASSES}:{JAVA_CP.read_text().strip()}"
        algorithm = {"skjolber_plain": "plain", "skjolber_laff": "laff", "skjolber_fast_bruteforce": "fast_brute_force"}[implementation_id]
        command = ["java", "-Xms32m", "-Xmx512m", "-XX:ActiveProcessorCount=1", "-cp", classpath, "study.SkjolberReliability", algorithm, str(count), str(scale), variant]
    else:
        command = []
    if not command or (command[0].endswith("packingsolver_boxstacks") and not Path(command[0]).exists()):
        return "ERROR", {"placements": 0, "required_items": len(spec["items"]), "validation_error_count": 1, "validation_errors": ["adapter or binary unavailable"]}, "", "adapter or binary unavailable", 0.0, None, {}
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout_s, env=env, check=False)
        wall = perf_counter() - started
    except subprocess.TimeoutExpired as exc:
        return "TIME_LIMIT", {"placements": 0, "required_items": len(spec["items"]), "validation_error_count": 0, "validation_errors": [], "objective": None}, exc.stdout or "", exc.stderr or "", perf_counter() - started, None, {}
    stdout, stderr = completed.stdout, completed.stderr
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        # PackingSolver writes a CSV certificate; resolve row/index IDs first.
        cert = work / "solution.csv"
        placements = []
        if cert.exists():
            payload = parse_packingsolver_certificate(cert, spec)
        else:
            payload = {"placements": placements}
    status, metrics = basic_payload(payload, spec)
    if completed.returncode != 0 and status == "NO_SOLUTION": status = "ERROR"
    metrics["library_reported"] = payload.get("success", payload.get("status"))
    metrics["variant"] = variant
    metrics["scale"] = scale
    extra: dict[str, Path] = {}
    if implementation_id.startswith("packingsolver_"):
        if cert.exists():
            extra["solution.csv"] = cert
        if output.exists():
            extra["solver.json"] = output
    return status, metrics, stdout, stderr, wall, None, extra


def invoke_fault(implementation_id: str, kind: str, spec: dict[str, Any]) -> tuple[str, dict[str, Any], str, str, float, int | None, Any]:
    """Exercise the process boundary with malformed input or cancellation."""
    RAW.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="fault-", dir=str(RAW)))
    env = os.environ.copy()
    env.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", NUMEXPR_NUM_THREADS="1", RAYON_NUM_THREADS="1", GOMAXPROCS="1")
    if kind == "invalid_json":
        input_path = work / "invalid.json"
        input_path.write_text('{"scenario":')
    else:
        input_path = work / "input.json"
        large = fixture("base", 512, 1)
        input_path.write_text(json.dumps(large) + "\n")
    if implementation_id in {"py3dbp", "jerry"}:
        command = [str(PYTHON), str(ROOT / "benchmarks/campaign/python_thpack/worker.py"), "--library", implementation_id, "--input", str(input_path), "--order", "descending", "--projection"]
    elif implementation_id == "go_bp3d":
        command = [str(GO), "--input", str(input_path)]
    elif implementation_id.startswith("rust_"):
        strategy = {"rust_layer": "bottomleftfill", "rust_ga": "ga", "rust_brkga": "brkga", "rust_sa": "sa", "rust_extreme_point": "extremepoint"}[implementation_id]
        command = [str(RUST), "--input", str(input_path), strategy, "10000"]
    elif implementation_id.startswith("packingsolver_"):
        binary = PS_BINARIES[implementation_id]
        if kind == "invalid_json":
            bad_items, bad_bins = work / "items.csv", work / "bins.csv"
            bad_items.write_text("not,csv\n")
            bad_bins.write_text("not,csv\n")
            command = [str(binary), "--items", str(bad_items), "--bins", str(bad_bins), "--objective", "bin-packing", "--time-limit", "1", "--memory-limit", "128", "--verbosity-level", "0"]
        else:
            valid_items, valid_bins = work / "items.csv", work / "bins.csv"
            valid_items.write_text("ID,X,Y,Z,ROTATION_XYZ,ROTATION_YXZ,ROTATION_ZYX,ROTATION_YZX,ROTATION_XZY,ROTATION_ZXY,WEIGHT,COPIES\n0,5,5,5,1,1,1,1,1,1,1,512\n")
            valid_bins.write_text("ID,X,Y,Z,COST,COPIES,MAXIMUM_WEIGHT\n0,10,10,10,1,64,1000\n")
            command = [str(binary), "--items", str(valid_items), "--bins", str(valid_bins), "--objective", "bin-packing", "--time-limit", "10", "--memory-limit", "512", "--verbosity-level", "0"]
    elif implementation_id.startswith("exact_"):
        command = [str(PYTHON), str(ROOT / "benchmarks/comprehensive/exact_reliability_worker.py"),
                   "--backend", implementation_id.removeprefix("exact_"), "--input", str(input_path)]
    elif implementation_id.startswith("skjolber_"):
        classpath = f"{JAVA_CLASSES}:{JAVA_CP.read_text().strip()}"
        algorithm = {"skjolber_plain": "plain", "skjolber_laff": "laff", "skjolber_fast_bruteforce": "fast_brute_force"}[implementation_id]
        command = ["java", "-Xms32m", "-Xmx512m", "-XX:ActiveProcessorCount=1", "-cp", classpath, "study.SkjolberReliability", algorithm, "512", "1", "base"]
    else:
        command = []
    if not command or (command[0].endswith("boxstacks") and not Path(command[0]).exists()):
        return "ERROR", {"placements": 0, "required_items": 0, "validation_error_count": 1, "validation_errors": ["adapter or binary unavailable"]}, "", "adapter or binary unavailable", 0.0, None, {"scenario": f"fault-{kind}", "fault": kind}
    started = perf_counter()
    if kind == "cancelled":
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        try:
            stdout, stderr = process.communicate(timeout=0.02)
            status = "COMPLETED"
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
            status = "CANCELLED"
        return status, {"placements": 0, "required_items": 512, "validation_error_count": 0, "validation_errors": [], "objective": None, "cancel_latency_s": perf_counter() - started}, stdout or "", stderr or "", perf_counter() - started, None, {"scenario": f"fault-{kind}", "fault": kind, "command": command}
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=5.0, env=env, check=False)
    except subprocess.TimeoutExpired as exc:
        return "CANCELLED", {"placements": 0, "required_items": 8, "validation_error_count": 0, "validation_errors": [], "objective": None}, exc.stdout or "", exc.stderr or "", perf_counter() - started, None, {"scenario": f"fault-{kind}", "fault": kind, "command": command}
    status = "ERROR" if completed.returncode != 0 else "INVALID_CERTIFICATE"
    return status, {"placements": 0, "required_items": 8, "validation_error_count": 1, "validation_errors": ["malformed input rejected"], "objective": None}, completed.stdout, completed.stderr, perf_counter() - started, None, {"scenario": f"fault-{kind}", "fault": kind, "command": command}


def planned_cases() -> list[tuple[str, str, int, int, int]]:
    cases: list[tuple[str, str, int, int, int]] = []
    for variant in ("base", "permuted", "renamed", "axis_swap"):
        cases.append(("B24", variant, 8, 1, 0))
    for variant, scale in (("base", 1), ("scale10", 10)):
        cases.append(("B26", variant, 8, scale, 0))
    for variant in ("cost_base", "cost_permuted", "cost_scaled"):
        cases.append(("B25", variant, 2, 1, 0))
    for rep in range(5):
        cases.append(("B27", "base", 8, 1, rep))
    for count in (8, 16, 32, 64):
        cases.append(("B28", f"n{count}", count, 1, 0))
    for variant in ("invalid_json", "cancelled"):
        cases.append(("B29", variant, 8, 1, 0))
    return cases


def make_record(benchmark_id: str, variant: str, impl: dict[str, Any], count: int, scale: int, repetition: int) -> dict[str, Any]:
    spec = fixture("base" if variant in {"base", "scale10"} or variant.startswith("n") or variant in {"invalid_json", "cancelled"} else variant, count, scale)
    if variant == "scale10": spec["scenario"] = "reliability-scale10"
    run_id = f"{benchmark_id}/{variant}/{impl['id']}/rep-{repetition}"
    suite = next(row for row in load_catalogs()[0]["suites"] if row["id"] == benchmark_id)
    capability = suite["capability_by_profile"][impl["capability_profile"]]
    extra: dict[str, Path] = {}
    if variant in {"invalid_json", "cancelled"}:
        status, metrics, stdout, stderr, wall, rss, fault_spec = invoke_fault(impl["id"], variant, spec)
        spec = fault_spec
        if isinstance(fault_spec, dict) and fault_spec.get("command"):
            metrics["fault_command"] = fault_spec["command"]
    else:
        status, metrics, stdout, stderr, wall, rss, extra = invoke(impl["id"], spec, variant, count, scale)
    if status in {"VALID_COMPLETE", "VALID_PARTIAL", "INVALID_CERTIFICATE", "CONSTRAINT_VIOLATION", "NO_SOLUTION"}:
        solution = status
    else:
        solution = "NO_SOLUTION"
    artifacts = write_artifacts(run_id, spec, stdout, stderr, {"status": status, **metrics}, extra)
    run_status = status if status in {"ERROR", "CANCELLED", "TIME_LIMIT"} else "COMPLETED"
    record = {
        "schema_version": 2, "protocol_version": "benchmark-protocol/3", "record_origin": "PROTOCOL_V3",
        "run_id": run_id, "benchmark_id": benchmark_id, "problem_variant": variant, "instance_id": spec["scenario"],
        "implementation_id": impl["id"], "algorithm": impl["algorithm"], "adapter": "reliability_v3/parameterized_fixture",
        "comparison_track": "EXACT_MODEL" if impl["default_track"] == "EXACT_MODEL" else "NATIVE",
        "problem_scope": "FULL_PROBLEM", "budget": {"time_limit_s": 12.0, "memory_limit_bytes": 536870912, "thread_limit": 1},
        "item_order": variant.upper(), "bin_order": "CANONICAL", "seed": 42, "repetition": repetition,
        "input_sha256": digest(spec), "input_status": "VALID", "capability_status": capability,
        "run_status": run_status,
        "solution_status": solution, "proof_status": "FEASIBLE" if solution.startswith("VALID") else "UNKNOWN",
        "termination_reason": status, "resources": {"wall_s": wall, "solver_s": wall, "peak_rss_bytes": rss},
        "metrics": {**metrics, "provenance_kind": "FRESH_SOLVER_INVOCATION", "runner_sha256": RUNNER_SHA256, "metamorphic_variant": variant},
        "artifacts": artifacts,
    }
    validate_run_record(record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=RESULTS)
    parser.add_argument("--benchmark", choices=("B24", "B25", "B26", "B27", "B28", "B29"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for benchmark_id, variant, count, scale, repetition in planned_cases():
        if args.benchmark and benchmark_id != args.benchmark:
            continue
        for impl in IMPLEMENTATIONS:
            suite = next(row for row in load_catalogs()[0]["suites"] if row["id"] == benchmark_id)
            capability = suite["capability_by_profile"][impl["capability_profile"]]
            if capability in {"ADAPTER_MISSING", "NOT_SUPPORTED"}:
                continue
            records.append(make_record(benchmark_id, variant, impl, count, scale, repetition))
    if args.benchmark and args.output.exists():
        prior = [json.loads(line) for line in args.output.read_text().splitlines() if line]
        records = [row for row in prior if row["benchmark_id"] != args.benchmark] + records
    args.output.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in sorted(records, key=lambda r: r["run_id"])))
    print(f"wrote {len(records)} reliability records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
