#!/usr/bin/env python3
"""Run a bounded, source-derived geometry projection of Alonso 2019/2020.

The original problems build layers and pallets, schedule delivery days and
load trucks with axle constraints.  No candidate geometry library in this
repository can preserve that complete model.  This runner therefore keeps the
source product demand and truck dimensions, removes the non-geometric fields,
and records every result as ``GEOMETRY_PROJECTION``.  It is deliberately
limited to the smallest source instances so the projection remains a bounded
adapter experiment rather than a claim of a full industrial solve.
"""

from __future__ import annotations

import argparse
import hashlib
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

ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = ROOT / ".cache" / "esicup-datasets" / "3d_rectangular"
RESULTS = ROOT / "results" / "comprehensive" / "runs" / "alonso-projection.jsonl"
RAW_ROOT = ROOT / "raw" / "experiments" / "comprehensive" / "Alonso-projection"
RUNNER = Path(__file__).resolve()

sys.path.insert(0, str(ROOT / "benchmarks" / "comprehensive"))
import run_constraint_adapters as constraint_runner  # noqa: E402
from model import canonical_json  # noqa: E402

# The two existing runners both import a module named ``model``.  Load the
# comprehensive model first, then temporarily switch the module binding while
# importing the THPACK external runner; its functions retain their own globals.
comprehensive_model = sys.modules["model"]
sys.modules.pop("model", None)
sys.path.insert(0, str(ROOT / "benchmarks" / "campaign" / "python_thpack"))
import run_thpack_external_projection as external_runner  # noqa: E402

thpack_model = sys.modules["model"]
sys.modules["model"] = comprehensive_model
Instance = thpack_model.Instance
ItemType = thpack_model.ItemType
expanded_items = thpack_model.expanded_items


EXTERNAL_IMPLEMENTATIONS = {
    "go_bp3d": ("go_bp3d", "pivot"),
    "rust_extreme_point": ("rust_unesting", "extremepoint"),
    "rust_layer": ("rust_unesting", "bottomleftfill"),
    "rust_ga": ("rust_unesting", "ga"),
    "rust_brkga": ("rust_unesting", "brkga"),
    "rust_sa": ("rust_unesting", "sa"),
}
PYTHON_IMPLEMENTATIONS = {"py3dbp", "jerry"}
PACKINGSOLVER_IMPLEMENTATIONS = {
    "packingsolver_fork_box": ROOT / ".cache" / "build-fork" / "src" / "box" / "packingsolver_box",
    "packingsolver_upstream_box": ROOT / ".cache" / "build-upstream-367" / "src" / "box" / "packingsolver_box",
}
PACKINGSOLVER_STACK_IMPLEMENTATIONS = {
    "packingsolver_fork_boxstacks": ROOT / ".cache" / "build-fork" / "src" / "boxstacks" / "packingsolver_boxstacks",
    "packingsolver_upstream_boxstacks": ROOT / ".cache" / "build-upstream-367" / "src" / "boxstacks" / "packingsolver_boxstacks",
}
SKJOLBER_IMPLEMENTATIONS = {
    "skjolber_plain": "plain",
    "skjolber_laff": "laff",
    "skjolber_fast_bruteforce": "fast_brute_force",
}


def benchmark_id_for_year(year: int) -> str:
    return "B19" if year == 2019 else "B20"


def variant_for_source(source: dict[str, Any]) -> str:
    return f"ALONSO{source['year']}_GEOMETRY_PROJECTION_{Path(source['path']).stem.upper()}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_sections(path: Path) -> dict[str, list[list[str]]]:
    sections: dict[str, list[list[str]]] = {}
    current: str | None = None
    expected = 0
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            parts = line.split()
            if len(parts) != 2:
                raise ValueError(f"{path}:{line_number}: malformed header")
            if current is not None and len(sections[current]) != expected:
                raise ValueError(f"{path}: section {current} count mismatch")
            current = parts[0][1:].lower()
            expected = int(parts[1])
            sections[current] = []
            continue
        if current is None:
            raise ValueError(f"{path}:{line_number}: row outside section")
        sections[current].append(line.split())
    if current is not None and len(sections[current]) != expected:
        raise ValueError(f"{path}: section {current} count mismatch")
    if set(sections) != {"products", "layers", "pallets", "trucks"}:
        raise ValueError(f"{path}: unexpected sections {sorted(sections)}")
    return sections


def to_instance(path: Path, year: int) -> tuple[Instance, dict[str, Any]]:
    sections = parse_sections(path)
    item_types: list[ItemType] = []
    for row in sections["products"]:
        if year == 2019:
            if len(row) != 14:
                raise ValueError(f"{path}: Alonso 2019 product width mismatch")
            product_id, demand = row[0], int(row[2])
            width, length, height = (int(float(row[index])) for index in (3, 4, 5))
        else:
            if len(row) != 25:
                raise ValueError(f"{path}: Alonso 2020 product width mismatch")
            product_id, demand = row[0], int(row[2])
            width, length, height = (int(float(row[index])) for index in (14, 15, 16))
        if demand > 0:
            item_types.append(ItemType(str(product_id), (width, length, height), (1, 1, 1), demand))
    truck = sections["trucks"][0]
    if len(truck) != 9:
        raise ValueError(f"{path}: truck width mismatch")
    container = tuple(int(float(truck[index])) for index in (1, 2, 3))
    instance = Instance(
        family=f"ALONSO{year}",
        instance_id=int(path.stem.replace("inst3d_", "").replace("inst3d", "")),
        problem_kind="single_container_knapsack",
        objective="maximize_packed_volume_projection",
        container=container,
        item_types=item_types,
        seed=42,
    )
    source = {
        "path": str(path.relative_to(ROOT)),
        "sha256": sha256(path),
        "year": year,
        "source_item_count": instance.item_count,
        "source_product_types": len(item_types),
        "removed_constraints": [
            "delivery_day_and_multi_period_demand",
            "layer_composition_and_max_layers",
            "pallet_type_and_pallet_weight",
            "stacking_group_top_bottom_rules",
            "truck_axle_distances_and_axle_payload_limits",
            "truck_count_and_cost_objective",
        ],
    }
    return instance, source


def discover(year: int, count: int, max_items: int) -> list[tuple[Instance, dict[str, Any]]]:
    pattern = "inst3d*.csv" if year == 2019 else "inst3d_*.csv"
    candidates = []
    for path in (SOURCE_ROOT / f"alonso_{year}").glob(pattern):
        instance, source = to_instance(path, year)
        if instance.item_count <= max_items:
            candidates.append((instance.item_count, path.name, instance, source))
    candidates.sort(key=lambda row: (row[0], row[1]))
    return [(row[2], row[3]) for row in candidates[:count]]


def spec_for(instance: Instance, source: dict[str, Any], benchmark_id: str) -> tuple[dict[str, Any], dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    items = expanded_items(instance)
    item_meta: dict[str, dict[str, str]] = {}
    normalized: list[dict[str, Any]] = []
    for item in items:
        item_id = str(item["item_id"])
        size = [float(value) for value in item["size"]]
        normalized.append({"id": item_id, "type_id": item["type_id"], "size": size, "weight": 1.0, "orientation_requirement": "any"})
        item_meta[item_id] = {
            "ID": item_id,
            "X": str(size[0]), "Y": str(size[1]), "Z": str(size[2]),
            "WEIGHT": "1", "COPIES": "1", "GROUP_ID": "0",
            "ROTATION_XYZ": "1", "ROTATION_YXZ": "1", "ROTATION_ZYX": "1",
            "ROTATION_YZX": "1", "ROTATION_XZY": "1", "ROTATION_ZXY": "1",
        }
    bin_id = f"truck:{source['year']}:{instance.instance_id}"
    bin_row = {
        "ID": bin_id,
        "X": str(instance.container[0]), "Y": str(instance.container[1]), "Z": str(instance.container[2]),
        "COPIES": "1", "COST": "1", "MAXIMUM_WEIGHT": str(float("inf")),
        "IS_SEMI_TRAILER_TRUCK": "0",
    }
    spec = {
        "scenario": f"{benchmark_id.lower()}_{source['year']}_{instance.instance_id:03d}",
        "benchmark_id": benchmark_id,
        "problem_variant": variant_for_source(source),
        "items": normalized,
        "bins": [{"id": bin_id, "type_id": bin_id, "size": list(instance.container), "max_weight": float("inf"), "cost": 1.0}],
        "expected_complete": False,
        "source_files": {source["path"]: source["sha256"]},
        "projection_removed_constraints": source["removed_constraints"],
    }
    return spec, item_meta, {bin_id: bin_row}


def run_python(implementation_id: str, spec: dict[str, Any], item_meta: dict[str, dict[str, str]], bin_meta: dict[str, dict[str, str]]) -> dict[str, Any]:
    record = constraint_runner.run_one(implementation_id, spec, item_meta, bin_meta)
    record["adapter"] = "alonso_geometry_projection_v1"
    record["metrics"]["projection_removed_constraints"] = spec["projection_removed_constraints"]
    record["metrics"]["source_file"] = next(iter(spec["source_files"]))
    record["metrics"]["source_instance_item_count"] = len(spec["items"])
    constraint_runner.validate_run_record(record)
    return record


def run_packingsolver(
    implementation_id: str,
    spec: dict[str, Any],
    item_meta: dict[str, dict[str, str]],
    bin_meta: dict[str, dict[str, str]],
    source: dict[str, Any],
    time_limit: float,
    stack: bool = False,
) -> dict[str, Any]:
    """Run the C++ box binary after projecting an Alonso instance to geometry."""
    binaries = PACKINGSOLVER_STACK_IMPLEMENTATIONS if stack else PACKINGSOLVER_IMPLEMENTATIONS
    binary = binaries[implementation_id]
    work = RAW_ROOT / f"{spec['scenario']}_{implementation_id}"
    work.mkdir(parents=True, exist_ok=True)
    input_path = work / "input.json"
    output_path = work / "output.json"
    certificate_path = work / "solution.csv"
    stdout_path = work / "stdout.log"
    stderr_path = work / "stderr.log"
    validation_path = work / "validation.json"
    items_path, bins_path = constraint_runner.write_packingsolver_csv(spec, work)
    command = [str(binary), "--items", str(items_path), "--bins", str(bins_path), "--objective", "bin-packing" if stack else "knapsack", "--time-limit", str(time_limit), "--memory-limit", "1024", "--verbosity-level", "0", "--only-write-at-the-end", "--output", str(output_path), "--certificate", str(certificate_path)]
    input_path.write_text(canonical_json(spec), encoding="utf-8")
    started = perf_counter()
    env = {**os.environ, "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"}
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=time_limit + 20.0, env=env, check=False)
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        process_ok = completed.returncode == 0 and certificate_path.exists()
    except subprocess.TimeoutExpired as exc:
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text(exc.stderr or "", encoding="utf-8")
        process_ok = False
    elapsed = perf_counter() - started
    if process_ok:
        payload = constraint_runner.parse_packingsolver_certificate(certificate_path, spec)
        status, metrics = constraint_runner.independent_validate(spec, item_meta, bin_meta, payload)
    else:
        payload = {"placements": []}
        status, metrics = "NO_SOLUTION", {"packed_items": 0, "required_items": len(spec["items"]), "bins_used": 0, "validation_error_count": 1, "validation_errors": ["solver process failed or omitted certificate"]}
    validation_path.write_text(canonical_json(metrics), encoding="utf-8")
    solution_status = "VALID_COMPLETE" if status == "VALID_COMPLETE" else "VALID_PARTIAL" if status == "VALID_PARTIAL" else "CONSTRAINT_VIOLATION" if status == "CONSTRAINT_VIOLATION" else "NO_SOLUTION" if status == "NO_SOLUTION" else "INVALID_CERTIFICATE" if process_ok else "NO_SOLUTION"
    implementation = next(row for row in constraint_runner.load_catalogs()[1]["implementations"] if row["id"] == implementation_id)
    record = {
        "schema_version": 2, "protocol_version": "benchmark-protocol/3", "record_origin": "PROTOCOL_V3",
        "run_id": f"{spec['benchmark_id']}/{spec['problem_variant']}/{spec['scenario']}/{implementation_id}/{time_limit:g}s/geometry-projection/rep-0",
        "benchmark_id": spec["benchmark_id"], "problem_variant": spec["problem_variant"], "instance_id": spec["scenario"],
        "implementation_id": implementation_id, "algorithm": implementation["algorithm"], "adapter": "alonso_geometry_projection_v1", "comparison_track": "COMPOSED", "problem_scope": "GEOMETRY_PROJECTION",
        "budget": {"time_limit_s": time_limit, "memory_limit_bytes": 1073741824, "thread_limit": 1}, "item_order": "SOURCE", "bin_order": "SOURCE", "seed": 42, "repetition": 0,
        "input_sha256": constraint_runner.digest(spec), "input_status": "VALID", "capability_status": "PROJECTION_ONLY", "run_status": "COMPLETED" if process_ok else "ERROR", "solution_status": solution_status,
        "proof_status": "FEASIBLE" if solution_status in {"VALID_COMPLETE", "VALID_PARTIAL"} else "UNKNOWN", "termination_reason": "RETURNED_PROJECTION" if process_ok else "PROCESS_ERROR",
        "resources": {"wall_s": elapsed, "solver_s": None, "peak_rss_bytes": None},
        "metrics": {**metrics, "projection_removed_constraints": source["removed_constraints"], "source_file": source["path"], "source_instance_item_count": len(spec["items"]), "binary_family": "boxstacks" if stack else "box", "binary_sha256": constraint_runner.sha256(binary) if binary.exists() else None, "runner_sha256": constraint_runner.sha256(RUNNER)},
        "artifacts": {"input": str(input_path.relative_to(ROOT)), "solver_output": str(output_path.relative_to(ROOT)) if output_path.exists() else None, "solution": str(certificate_path.relative_to(ROOT)) if certificate_path.exists() else None, "stdout": str(stdout_path.relative_to(ROOT)), "stderr": str(stderr_path.relative_to(ROOT)), "validation": str(validation_path.relative_to(ROOT))},
    }
    constraint_runner.validate_run_record(record)
    return record


def run_skjolber(
    implementation_id: str,
    spec: dict[str, Any],
    item_meta: dict[str, dict[str, str]],
    bin_meta: dict[str, dict[str, str]],
    source: dict[str, Any],
    time_limit: float,
) -> dict[str, Any]:
    """Run Plain/LAFF/FastBruteForce through the Java projection sidecar."""
    work = RAW_ROOT / f"{spec['scenario']}_{implementation_id}"
    work.mkdir(parents=True, exist_ok=True)
    input_path = work / "input.json"
    output_path = work / "output.json"
    stdout_path = work / "stdout.log"
    stderr_path = work / "stderr.log"
    validation_path = work / "validation.json"
    items_path, bins_path = constraint_runner.write_skjolber_csv(spec, work)
    java = __import__("shutil").which("java") or "/usr/bin/java"
    command = [java, "-Xms32m", "-Xmx512m", "-XX:ActiveProcessorCount=1", "-cp", constraint_runner.skjolber_classpath(), "study.SkjolberProjection", str(items_path), str(bins_path), SKJOLBER_IMPLEMENTATIONS[implementation_id], str(max(1, round(time_limit * 1000))), str(output_path)]
    input_path.write_text(canonical_json(spec), encoding="utf-8")
    started = perf_counter()
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=time_limit + 20.0, env={**os.environ, "JAVA_TOOL_OPTIONS": "-Djava.util.concurrent.ForkJoinPool.common.parallelism=1"}, check=False)
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        process_ok = completed.returncode == 0 and output_path.exists()
    except subprocess.TimeoutExpired as exc:
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text(exc.stderr or "", encoding="utf-8")
        process_ok = False
    elapsed = perf_counter() - started
    if process_ok:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        status, metrics = constraint_runner.independent_validate(spec, item_meta, bin_meta, payload)
    else:
        payload = {"placements": []}
        status, metrics = "NO_SOLUTION", {"packed_items": 0, "required_items": len(spec["items"]), "bins_used": 0, "validation_error_count": 1, "validation_errors": ["sidecar failed or omitted output"]}
    validation_path.write_text(canonical_json(metrics), encoding="utf-8")
    solution_status = "VALID_COMPLETE" if status == "VALID_COMPLETE" else "VALID_PARTIAL" if status == "VALID_PARTIAL" else "CONSTRAINT_VIOLATION" if status == "CONSTRAINT_VIOLATION" else "NO_SOLUTION" if status == "NO_SOLUTION" else "INVALID_CERTIFICATE" if process_ok else "NO_SOLUTION"
    implementation = next(row for row in constraint_runner.load_catalogs()[1]["implementations"] if row["id"] == implementation_id)
    record = {
        "schema_version": 2, "protocol_version": "benchmark-protocol/3", "record_origin": "PROTOCOL_V3",
        "run_id": f"{spec['benchmark_id']}/{spec['problem_variant']}/{spec['scenario']}/{implementation_id}/{time_limit:g}s/geometry-projection/rep-0",
        "benchmark_id": spec["benchmark_id"], "problem_variant": spec["problem_variant"], "instance_id": spec["scenario"],
        "implementation_id": implementation_id, "algorithm": implementation["algorithm"], "adapter": "alonso_geometry_projection_v1", "comparison_track": "COMPOSED", "problem_scope": "GEOMETRY_PROJECTION",
        "budget": {"time_limit_s": time_limit, "memory_limit_bytes": 1073741824, "thread_limit": 1}, "item_order": "SOURCE", "bin_order": "SOURCE", "seed": 42, "repetition": 0,
        "input_sha256": constraint_runner.digest(spec), "input_status": "VALID", "capability_status": "PROJECTION_ONLY", "run_status": "COMPLETED" if process_ok else "ERROR", "solution_status": solution_status,
        "proof_status": "FEASIBLE" if solution_status in {"VALID_COMPLETE", "VALID_PARTIAL"} else "UNKNOWN", "termination_reason": "RETURNED_PROJECTION" if process_ok else "PROCESS_ERROR",
        "resources": {"wall_s": elapsed, "solver_s": payload.get("elapsed_s") if process_ok else None, "peak_rss_bytes": None},
        "metrics": {**metrics, "projection_removed_constraints": source["removed_constraints"], "source_file": source["path"], "source_instance_item_count": len(spec["items"]), "runner_sha256": constraint_runner.sha256(RUNNER)},
        "artifacts": {"input": str(input_path.relative_to(ROOT)), "solver_output": str(output_path.relative_to(ROOT)) if output_path.exists() else None, "stdout": str(stdout_path.relative_to(ROOT)), "stderr": str(stderr_path.relative_to(ROOT)), "validation": str(validation_path.relative_to(ROOT))},
    }
    constraint_runner.validate_run_record(record)
    return record


def run_external(
    implementation_id: str,
    instance: Instance,
    source: dict[str, Any],
    archive_name: str,
    time_limit: float,
    order: str,
    work_root: Path,
) -> dict[str, Any]:
    library, strategy = EXTERNAL_IMPLEMENTATIONS[implementation_id]
    go = external_runner.DEFAULT_GO
    rust = external_runner.DEFAULT_RUST
    if library == "go_bp3d" and not go.exists():
        raise RuntimeError(f"missing Go binary: {go}")
    if library == "rust_unesting" and not rust.exists():
        raise RuntimeError(f"missing Rust binary: {rust}")
    record = external_runner.run_one(
        instance, library, strategy, order, time_limit, 0, go, rust, work_root,
        archive_name, external_runner.sha256(RUNNER),
        benchmark_id_override=benchmark_id_for_year(source["year"]),
        source_instance_id_override=f"ALONSO{source['year']}:{Path(source['path']).name}",
        source_group=f"ALONSO{source['year']}",
        source_commit_override="154a8f006a8e72f65d734f2d1e36777f678f31f8",
        source_items_sha256=source["sha256"], source_bins_sha256=source["sha256"],
    )
    record["adapter"] = "alonso_geometry_projection_v1"
    record["problem_variant"] = variant_for_source(source)
    record["metrics"]["projection_removed_constraints"] = source["removed_constraints"]
    record["metrics"]["source_file"] = source["path"]
    record["metrics"]["source_instance_item_count"] = instance.item_count
    constraint_runner.validate_run_record(record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--max-items", type=int, default=1200)
    parser.add_argument("--year", type=int, action="append", choices=(2019, 2020), default=None)
    parser.add_argument("--time-limit", type=float, default=1.0)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    cases: list[tuple[Instance, dict[str, Any], str]] = []
    for year in args.year or [2019, 2020]:
        cases.extend((instance, source, benchmark_id_for_year(year)) for instance, source in discover(year, args.count, args.max_items))
    if not cases:
        raise SystemExit("no Alonso instances satisfy the bound")
    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    archive_name = f"raw/experiments/comprehensive/Alonso-projection-{args.time_limit:g}s.tar.gz"
    records: list[dict[str, Any]] = []
    external_jobs = []
    for instance, source, benchmark_id in cases:
        spec, item_meta, bin_meta = spec_for(instance, source, benchmark_id)
        for implementation_id in sorted(PYTHON_IMPLEMENTATIONS):
            records.append(run_python(implementation_id, spec, item_meta, bin_meta))
        for implementation_id in sorted(PACKINGSOLVER_IMPLEMENTATIONS):
            records.append(run_packingsolver(implementation_id, spec, item_meta, bin_meta, source, args.time_limit))
        for implementation_id in sorted(PACKINGSOLVER_STACK_IMPLEMENTATIONS):
            records.append(run_packingsolver(implementation_id, spec, item_meta, bin_meta, source, args.time_limit, stack=True))
        for implementation_id in sorted(SKJOLBER_IMPLEMENTATIONS):
            records.append(run_skjolber(implementation_id, spec, item_meta, bin_meta, source, args.time_limit))
        for implementation_id in sorted(EXTERNAL_IMPLEMENTATIONS):
            for order in ("descending", "ascending"):
                external_jobs.append((implementation_id, instance, source, benchmark_id, order))
    with tempfile.TemporaryDirectory(prefix="alonso-projection-") as temporary:
        work_root = Path(temporary)
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(run_external, implementation_id, instance, source, archive_name, args.time_limit, order, work_root)
                       for implementation_id, instance, source, _benchmark_id, order in external_jobs]
            for future in as_completed(futures):
                records.append(future.result())
        archive_path = ROOT / archive_name
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive_path, "w:gz") as archive:
            for path in sorted(work_root.rglob("*")):
                if path.is_file():
                    archive.add(path, arcname=path.relative_to(work_root).as_posix())
    records.sort(key=lambda row: row["run_id"])
    RESULTS.write_text("".join(json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n" for record in records), encoding="utf-8")
    print(f"wrote {len(records)} records for {len(cases)} source instances to {RESULTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
