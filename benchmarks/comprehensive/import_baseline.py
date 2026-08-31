from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

from model import RESULTS_DIR, ROOT, canonical_json, load_catalogs, validate_run_record


CAMPAIGN = ROOT / "results" / "campaign"
RAW_CAMPAIGN = ROOT / "raw" / "experiments" / "campaign"


def jsonl(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line:
            yield line_number, json.loads(line)


def hash_payload(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def combined_hash(*hashes: str) -> str:
    return hashlib.sha256(("\n".join(hashes) + "\n").encode("ascii")).hexdigest()


def finite_or_none(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fixture_hash(*relative_paths: str) -> str:
    entries = [(path, file_hash(ROOT / path)) for path in relative_paths]
    return hash_payload(entries)


SCENARIO_FILES = {
    "exact_grid": (
        "benchmarks/data/packingsolver/grid_items.csv",
        "benchmarks/data/packingsolver/grid_bins.csv",
    ),
    "rotation_required": (
        "benchmarks/data/packingsolver/rotation_allowed_items.csv",
        "benchmarks/data/packingsolver/rotation_bins.csv",
    ),
    "rotation_forbidden": (
        "benchmarks/data/packingsolver/rotation_forbidden_items.csv",
        "benchmarks/data/packingsolver/rotation_bins.csv",
    ),
    "weight_limit": (
        "benchmarks/data/packingsolver/weight_items.csv",
        "benchmarks/data/packingsolver/weight_bins.csv",
    ),
    "heterogeneous_large_first": (
        "benchmarks/data/packingsolver/heterogeneous_items.csv",
        "benchmarks/data/packingsolver/heterogeneous_bins_reverse.csv",
    ),
    "heterogeneous_small_first": (
        "benchmarks/data/packingsolver/heterogeneous_items.csv",
        "benchmarks/data/packingsolver/heterogeneous_bins.csv",
    ),
    "thpack9_instance1": ("benchmarks/data/public/thpack9_instance1.json",),
}


SCENARIO_BENCHMARK = {
    "exact_grid": ("B06", "EXACT_GRID"),
    "rotation_required": ("B12", "ROTATION_REQUIRED"),
    "rotation_forbidden": ("B12", "ROTATION_FORBIDDEN"),
    "weight_limit": ("B13", "WEIGHT_LIMIT"),
    "heterogeneous_large_first": ("B09", "LARGE_CHEAPER"),
    "heterogeneous_small_first": ("B09", "SMALL_CHEAPER"),
    "thpack9_instance1": ("B04", "ORIGINAL"),
}


def implementation_index() -> dict[str, dict[str, Any]]:
    _, catalog = load_catalogs()
    return {row["id"]: row for row in catalog["implementations"]}


def make_record(
    implementations: dict[str, dict[str, Any]],
    *,
    run_id: str,
    benchmark_id: str,
    problem_variant: str,
    instance_id: str,
    implementation_id: str,
    adapter: str | None,
    comparison_track: str,
    problem_scope: str,
    budget: dict[str, int | float | None],
    item_order: str,
    bin_order: str,
    seed: int | None,
    repetition: int,
    input_sha256: str,
    capability_status: str,
    run_status: str,
    solution_status: str,
    proof_status: str,
    termination_reason: str,
    resources: dict[str, Any],
    metrics: dict[str, Any],
    artifacts: dict[str, str | None],
) -> dict[str, Any]:
    implementation = implementations[implementation_id]
    record = {
        "schema_version": 2,
        "protocol_version": "benchmark-protocol/3",
        "record_origin": "LEGACY_BASELINE",
        "run_id": run_id,
        "benchmark_id": benchmark_id,
        "problem_variant": problem_variant,
        "instance_id": instance_id,
        "implementation_id": implementation_id,
        "algorithm": implementation["algorithm"],
        "adapter": adapter,
        "comparison_track": comparison_track,
        "problem_scope": problem_scope,
        "budget": budget,
        "item_order": item_order,
        "bin_order": bin_order,
        "seed": seed,
        "repetition": repetition,
        "input_sha256": input_sha256,
        "input_status": "VALID",
        "capability_status": capability_status,
        "run_status": run_status,
        "solution_status": solution_status,
        "proof_status": proof_status,
        "termination_reason": termination_reason,
        "resources": resources,
        "metrics": metrics,
        "artifacts": artifacts,
    }
    validate_run_record(record)
    return record


def import_packingsolver_thpack(implementations: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for filename, time_limit in (("packingsolver-thpack.jsonl", 1.0), ("packingsolver-thpack-10s.jsonl", 10.0)):
        path = CAMPAIGN / filename
        for line_number, source in jsonl(path):
            if source["source_status"] != "VALID":
                continue
            benchmark_id = {"BR": "B01", "LN": "B02", "IMM": "B04"}[source["family"]]
            unpacked = int(source["unpacked_items"])
            solution_status = "VALID_COMPLETE" if unpacked == 0 else "VALID_PARTIAL"
            raw_proof = source.get("proof_status")
            proof_status = "INCUMBENT_WITH_BOUND" if raw_proof == "SOLVER_REPORTED_BOUND_CLOSED" else "FEASIBLE"
            reached_limit = float(source.get("solver_time_s") or 0) >= time_limit * 0.95 and proof_status == "FEASIBLE"
            records.append(
                make_record(
                    implementations,
                    run_id=f"{benchmark_id}/{source['instance_id']}/packingsolver_fork_box/{time_limit:g}s/source/rep-0",
                    benchmark_id=benchmark_id,
                    problem_variant="ORIGINAL",
                    instance_id=source["instance_id"],
                    implementation_id="packingsolver_fork_box",
                    adapter="legacy_import/packingsolver_thpack_v2",
                    comparison_track="NATIVE",
                    problem_scope="FULL_PROBLEM",
                    budget={"time_limit_s": time_limit, "memory_limit_bytes": 1073741824, "thread_limit": None},
                    item_order="SOLVER_INTERNAL",
                    bin_order="SOURCE",
                    seed=None,
                    repetition=0,
                    input_sha256=combined_hash(source["input_sha256"]["items"], source["input_sha256"]["bins"]),
                    capability_status="SUPPORTED_NATIVE",
                    run_status="TIME_LIMIT" if reached_limit else "COMPLETED",
                    solution_status=solution_status,
                    proof_status=proof_status,
                    termination_reason="TIME_LIMIT" if reached_limit else "SOLVER_STOPPED",
                    resources={
                        "wall_s": source.get("wall_time_s"),
                        "solver_s": source.get("solver_time_s"),
                        "cpu_user_s": source.get("user_time_s"),
                        "cpu_system_s": source.get("system_time_s"),
                        "peak_rss_bytes": source.get("max_rss_kib", 0) * 1024,
                    },
                    metrics={
                        "packed_items": source["packed_items"],
                        "unpacked_items": unpacked,
                        "bins_used": source["bins_used"],
                        "packed_volume": source["packed_volume"],
                        "volume_utilization": source.get("volume_utilization"),
                        "objective": source.get("primal"),
                        "solver_reported_bound": source.get("solver_reported_bound"),
                        "solver_reported_gap": source.get("relative_gap_to_solver_reported_bound"),
                        "validation_error_count": len(source.get("validation_errors", [])),
                    },
                    artifacts={"source_result": f"results/campaign/{filename}#L{line_number}", "validation": "offline revalidation embedded in source record"},
                )
            )
    return records


def import_python_thpack(implementations: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    path = RAW_CAMPAIGN / "python_thpack" / "records.jsonl"
    records: list[dict[str, Any]] = []
    executed = {"FEASIBLE_COMPLETE", "FEASIBLE_PARTIAL", "INVALID"}
    for line_number, source in jsonl(path):
        if source["status"] not in executed:
            continue
        benchmark_id = "B01" if source["family"] in {f"THPACK{i}" for i in range(1, 8)} else "B02" if source["family"] == "THPACK8" else "B04"
        solution_status = {
            "FEASIBLE_COMPLETE": "VALID_COMPLETE",
            "FEASIBLE_PARTIAL": "VALID_PARTIAL",
            "INVALID": "INVALID_CERTIFICATE",
        }[source["status"]]
        implementation_id = source["library"]
        records.append(
            make_record(
                implementations,
                run_id=f"{benchmark_id}/{source['instance_key']}/{implementation_id}/external-60s/{source['order']}/rep-0",
                benchmark_id=benchmark_id,
                problem_variant="ORIGINAL",
                instance_id=source["instance_key"],
                implementation_id=implementation_id,
                adapter="legacy_import/python_thpack_v1",
                comparison_track="NATIVE",
                problem_scope="FULL_PROBLEM",
                budget={"time_limit_s": 60.0, "memory_limit_bytes": 2147483648, "thread_limit": 1},
                item_order=source["order"].upper(),
                bin_order="SOURCE",
                seed=None,
                repetition=0,
                input_sha256=hash_payload(source["instance"]),
                capability_status="SUPPORTED_NATIVE",
                run_status="COMPLETED",
                solution_status=solution_status,
                proof_status="FEASIBLE" if solution_status.startswith("VALID_") else "UNKNOWN",
                termination_reason="RETURNED_CERTIFICATE",
                resources={
                    "wall_s": source.get("elapsed_seconds"),
                    "solver_s": source.get("solve_seconds"),
                    "peak_rss_bytes": source.get("peak_rss_kib", 0) * 1024,
                },
                metrics={
                    "packed_items": source.get("packed_items"),
                    "unpacked_items": source.get("unpacked_items"),
                    "bins_used": source.get("bins_used"),
                    "packed_volume": source.get("packed_volume"),
                    "volume_utilization": source.get("volume_utilization"),
                    "validation_error_count": len(source.get("validation_errors", [])),
                },
                artifacts={"source_result": f"raw/experiments/campaign/python_thpack/records.jsonl#L{line_number}", "validation": source.get("validator")},
            )
        )
    return records


def import_skjolber_thpack9(implementations: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    path = CAMPAIGN / "skjolber-thpack9.json"
    source = json.loads(path.read_text())
    records: list[dict[str, Any]] = []
    hashes: dict[str, str] = {}
    for index, row in enumerate(source["records"]):
        if not row["source_line_valid"]:
            continue
        input_hash = combined_hash(row["items_sha256"], row["bins_sha256"])
        hashes[row["instance_id"]] = input_hash
        implementation_id = "skjolber_plain" if row["algorithm"] == "plain" else "skjolber_laff"
        valid = row["status"] == "VALID" and not row["validation_errors"] and not row["independent_validation_errors"]
        records.append(
            make_record(
                implementations,
                run_id=f"B04/{row['instance_id']}/{implementation_id}/10s/source/rep-0",
                benchmark_id="B04",
                problem_variant="ORIGINAL",
                instance_id=row["instance_id"],
                implementation_id=implementation_id,
                adapter="legacy_import/skjolber_thpack9_v1",
                comparison_track="NATIVE",
                problem_scope="FULL_PROBLEM",
                budget={"time_limit_s": 10.0, "memory_limit_bytes": 536870912, "thread_limit": 1},
                item_order="SOURCE",
                bin_order="SOURCE",
                seed=None,
                repetition=0,
                input_sha256=input_hash,
                capability_status="SUPPORTED_NATIVE",
                run_status="TIME_LIMIT" if row["timeout"] else "COMPLETED",
                solution_status="VALID_COMPLETE" if valid else "INVALID_CERTIFICATE",
                proof_status="FEASIBLE" if valid else "UNKNOWN",
                termination_reason="TIME_LIMIT" if row["timeout"] else "RETURNED_CERTIFICATE",
                resources={"wall_s": row["wall_time_ms"] / 1000, "solver_s": row["library_duration_ms"] / 1000, "peak_rss_bytes": None},
                metrics={
                    "bins_used": row["bins_used"],
                    "packed_items": row["placements"],
                    "required_items": row["required_items"],
                    "packed_volume": row["packed_volume"],
                    "validation_error_count": len(row["validation_errors"]) + len(row["independent_validation_errors"]),
                },
                artifacts={"source_result": f"results/campaign/skjolber-thpack9.json#records[{index}]", "validation": row["independent_validation"]},
            )
        )
    return records, hashes


def import_crosslang_thpack9(
    implementations: dict[str, dict[str, Any]], instance_hashes: dict[str, str]
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    configurations = (
        ("crosslang_go_bp3d_thpack9", "go_bp3d", "SUPPORTED_NATIVE", "NATIVE"),
        ("crosslang_rust_unesting_thpack9", "rust_extreme_point", "SUPPORTED_COMPOSED", "COMPOSED"),
    )
    for filename, implementation_id, capability_status, track in configurations:
        path = CAMPAIGN / filename / "results.json"
        source = json.loads(path.read_text())
        for index, row in enumerate(source["records"]):
            valid = row["status"] == "VALID_COMPLETE" and not row["validation_errors"]
            records.append(
                make_record(
                    implementations,
                    run_id=f"B04/{row['instance']}/{implementation_id}/external-35s/library-default/rep-0",
                    benchmark_id="B04",
                    problem_variant="ORIGINAL",
                    instance_id=row["instance"],
                    implementation_id=implementation_id,
                    adapter="legacy_import/repeated_single_boundary" if track == "COMPOSED" else "legacy_import/native_multi_bin",
                    comparison_track=track,
                    problem_scope="FULL_PROBLEM",
                    budget={"time_limit_s": 35.0, "memory_limit_bytes": source["memory_limit_bytes"], "thread_limit": 1},
                    item_order="LIBRARY_DEFAULT",
                    bin_order="SOURCE",
                    seed=None,
                    repetition=0,
                    input_sha256=instance_hashes[row["instance"]],
                    capability_status=capability_status,
                    run_status="COMPLETED" if row["process_exitcode"] == 0 else "ERROR",
                    solution_status="VALID_COMPLETE" if valid else "INVALID_CERTIFICATE",
                    proof_status="FEASIBLE" if valid else "UNKNOWN",
                    termination_reason="RETURNED_CERTIFICATE" if row["process_exitcode"] == 0 else "PROCESS_ERROR",
                    resources={
                        "solver_s": row["library_elapsed_ms"] / 1000,
                        "wall_s": None,
                        "peak_rss_bytes": row.get("peak_rss_kib", 0) * 1024,
                    },
                    metrics={
                        "bins_used": row["bins_used"],
                        "packed_items": row["items_placed"],
                        "required_items": row["items_total"],
                        "validation_error_count": len(row["validation_errors"]),
                    },
                    artifacts={"source_result": f"results/campaign/{filename}/results.json#records[{index}]", "validation": "independent cross-language validator"},
                )
            )
    return records


def exact_case_inputs() -> dict[str, str]:
    campaign_dir = ROOT / "benchmarks" / "campaign"
    benchmark_dir = ROOT / "benchmarks"
    sys.path.insert(0, str(benchmark_dir))
    sys.path.insert(0, str(campaign_dir))
    from exact_suite import make_cases

    return {case.name: hash_payload(asdict(case)) for case in make_cases()}


def import_exact(implementations: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    inputs = exact_case_inputs()
    backends = {
        "cp-sat": "exact_cp_sat",
        "scip": "exact_scip",
        "gurobi": "exact_gurobi",
        "cplex": "exact_cplex",
    }
    for backend, implementation_id in backends.items():
        path = CAMPAIGN / f"exact-strengthened-{backend}.json"
        source = json.loads(path.read_text())
        for index, row in enumerate(source["cases"]):
            is_cost = row["case"].startswith("heterogeneous_")
            benchmark_id = "B09" if is_cost else "B06"
            if row["status"] == "INFEASIBLE":
                solution_status, proof_status = "NO_SOLUTION", "PROVEN_INFEASIBLE"
            elif not row["validation_errors"]:
                solution_status = "VALID_COMPLETE"
                proof_status = "PROVEN_OPTIMAL" if row["status"] == "OPTIMAL" else "INCUMBENT_WITH_BOUND"
            else:
                solution_status, proof_status = "INVALID_CERTIFICATE", "UNKNOWN"
            records.append(
                make_record(
                    implementations,
                    run_id=f"{benchmark_id}/{row['case']}/{implementation_id}/20s/strengthened/rep-0",
                    benchmark_id=benchmark_id,
                    problem_variant="STRENGTHENED",
                    instance_id=row["case"],
                    implementation_id=implementation_id,
                    adapter="exact_suite/strengthened",
                    comparison_track="EXACT_MODEL",
                    problem_scope="FULL_PROBLEM",
                    budget={"time_limit_s": 20.0, "memory_limit_bytes": None, "thread_limit": 1},
                    item_order="CANONICAL",
                    bin_order="CANONICAL",
                    seed=42,
                    repetition=0,
                    input_sha256=inputs[row["case"]],
                    capability_status="SUPPORTED_NATIVE",
                    run_status="TIME_LIMIT" if row["status"] in {"FEASIBLE", "UNKNOWN"} else "COMPLETED",
                    solution_status=solution_status,
                    proof_status=proof_status,
                    termination_reason=row["status"],
                    resources={"solver_s": row.get("solver_time_s"), "wall_s": row.get("wall_time_s"), "peak_rss_bytes": None},
                    metrics={
                        "objective": row.get("objective"),
                        "bound": row.get("bound"),
                        "gap": finite_or_none(row.get("gap")),
                        "bins_used": len(row.get("used_bins", [])),
                        "nodes_or_branches": row.get("nodes_or_branches"),
                        "conflicts": row.get("conflicts"),
                        "validation_error_count": len(row["validation_errors"]),
                    },
                    artifacts={"source_result": f"results/campaign/exact-strengthened-{backend}.json#cases[{index}]", "validation": "exact_suite.validate_solution"},
                )
            )
    return records


def import_boxstacks(implementations: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    path = CAMPAIGN / "packingsolver-boxstacks.json"
    source = json.loads(path.read_text())
    mapping = {
        "heterogeneous_cost": ("B09", "VARIABLE_COST"),
        "maximum_weight_above": ("B14", "MAXIMUM_WEIGHT_ABOVE"),
        "maximum_stack_count": ("B14", "MAXIMUM_STACK_COUNT"),
        "nesting_height": ("B14", "NESTING_HEIGHT"),
        "axle_normal": ("B15", "AXLE_NORMAL"),
        "axle_boundary_regression": ("B15", "AXLE_BOUNDARY"),
        "axle_infeasible": ("B15", "AXLE_INFEASIBLE"),
        "unloading_none": ("B17", "UNLOADING_NONE"),
        "unloading_increasing_x": ("B17", "INCREASING_X"),
    }
    records: list[dict[str, Any]] = []
    for index, row in enumerate(source["records"]):
        benchmark_id, variant = mapping[row["case"]]
        complete = bool(row["expected_complete"] and not row["validation_errors"])
        records.append(
            make_record(
                implementations,
                run_id=f"{benchmark_id}/{row['case']}/packingsolver_fork_boxstacks/10s/source/rep-0",
                benchmark_id=benchmark_id,
                problem_variant=variant,
                instance_id=row["case"],
                implementation_id="packingsolver_fork_boxstacks",
                adapter="legacy_import/boxstacks_constraints_v1",
                comparison_track="NATIVE",
                problem_scope="FULL_PROBLEM",
                budget={"time_limit_s": 10.0, "memory_limit_bytes": 1073741824, "thread_limit": None},
                item_order="SOURCE",
                bin_order="SOURCE",
                seed=None,
                repetition=0,
                input_sha256=combined_hash(row["items_sha256"], row["bins_sha256"]),
                capability_status="SUPPORTED_NATIVE",
                run_status="COMPLETED" if row["returncode"] == 0 else "ERROR",
                solution_status="VALID_COMPLETE" if complete else "NO_SOLUTION",
                proof_status="FEASIBLE" if complete else "UNKNOWN",
                termination_reason="EXPECTED_BEHAVIOR_PASS" if row["status"] == "PASS" else "UNEXPECTED_BEHAVIOR",
                resources={"wall_s": row["wall_time_s"], "solver_s": None, "peak_rss_bytes": None},
                metrics={
                    "bins_used": row["bins_used"],
                    "packed_items": row["placements"],
                    "total_cost": row["used_cost"],
                    "validation_error_count": len(row["validation_errors"]),
                    "expected_complete": row["expected_complete"],
                },
                artifacts={"source_result": f"results/campaign/packingsolver-boxstacks.json#records[{index}]", "validation": "packingsolver_boxstacks_suite independent checks"},
            )
        )
    return records


def import_crosslang_packingsolver(implementations: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for directory, implementation_id in (
        ("crosslang_cpp_packingsolver_fixed", "packingsolver_fork_box"),
        ("crosslang_cpp_packingsolver_official", "packingsolver_upstream_box"),
    ):
        path = CAMPAIGN / directory / "results.json"
        source = json.loads(path.read_text())
        for scenario, row in sorted(source["scenarios"].items()):
            benchmark_id, variant = SCENARIO_BENCHMARK[scenario]
            process_ok = row["process_exitcode"] == 0
            valid = process_ok and row["geometry_and_constraints_valid"] and row["complete"]
            no_solution = process_ok and row["geometry_and_constraints_valid"] and not row["complete"]
            solution_status = "VALID_COMPLETE" if valid else "NO_SOLUTION" if no_solution else "INVALID_CERTIFICATE"
            records.append(
                make_record(
                    implementations,
                    run_id=f"{benchmark_id}/{scenario}/{implementation_id}/2s/source/rep-0",
                    benchmark_id=benchmark_id,
                    problem_variant=variant,
                    instance_id=scenario,
                    implementation_id=implementation_id,
                    adapter="legacy_import/crosslang_packingsolver",
                    comparison_track="NATIVE",
                    problem_scope="FULL_PROBLEM",
                    budget={"time_limit_s": 2.0, "memory_limit_bytes": 1073741824, "thread_limit": 1},
                    item_order="SOURCE",
                    bin_order="SOURCE",
                    seed=None,
                    repetition=0,
                    input_sha256=fixture_hash(*SCENARIO_FILES[scenario]),
                    capability_status="SUPPORTED_NATIVE",
                    run_status="COMPLETED" if process_ok else "ERROR",
                    solution_status=solution_status,
                    proof_status="FEASIBLE" if valid else "UNKNOWN",
                    termination_reason="EXPECTED_BEHAVIOR_PASS" if row["expected_behavior_pass"] else "EXPECTED_BEHAVIOR_FAIL",
                    resources={"solver_s": row["library_elapsed_ms"] / 1000, "wall_s": None, "peak_rss_bytes": None},
                    metrics={
                        "bins_used": row["bins_used"],
                        "packed_items": row["items_placed"],
                        "required_items": row["items_total"],
                        "total_cost": row["total_cost"],
                        "validation_error_count": len(row["validation_errors"]),
                        "expected_behavior_pass": row["expected_behavior_pass"],
                    },
                    artifacts={"source_result": f"results/campaign/{directory}/results.json#scenarios.{scenario}", "validation": "crosslang_validate"},
                )
            )
    return records


def rust_implementation(strategy: str) -> str:
    return {
        "bottomleftfill": "rust_layer",
        "extremepoint": "rust_extreme_point",
        "ga": "rust_ga",
        "brkga": "rust_brkga",
        "sa": "rust_sa",
    }[strategy]


def import_rust_strategies(implementations: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    sources = (
        "crosslang_rust_unesting_strategies",
        "crosslang_rust_unesting_strategy_repeats",
    )
    for directory in sources:
        path = CAMPAIGN / directory / "results.json"
        source = json.loads(path.read_text())
        for key, row in sorted(source["scenarios"].items()):
            scenario = row["scenario"]
            benchmark_id, variant = SCENARIO_BENCHMARK[scenario]
            strategy = row["parameters"]["strategy_requested"]
            implementation_id = rust_implementation(strategy)
            repeat_match = re.search(r"repeat_(\d+)$", key)
            repetition = int(repeat_match.group(1)) if repeat_match else 0
            valid_geometry = bool(row["geometry_and_constraints_valid"])
            complete = bool(row["complete"])
            solution_status = "VALID_COMPLETE" if valid_geometry and complete else "NO_SOLUTION" if valid_geometry else "INVALID_CERTIFICATE"
            time_limit_ms = row["parameters"].get("time_limit_ms_requested_per_bin")
            records.append(
                make_record(
                    implementations,
                    run_id=f"{benchmark_id}/{scenario}/{implementation_id}/strategy/{strategy}/rep-{repetition}",
                    benchmark_id=benchmark_id,
                    problem_variant=variant,
                    instance_id=scenario,
                    implementation_id=implementation_id,
                    adapter="legacy_import/rust_repeated_single_boundary",
                    comparison_track="COMPOSED",
                    problem_scope="FULL_PROBLEM",
                    budget={"time_limit_s": time_limit_ms / 1000 if time_limit_ms else None, "memory_limit_bytes": None, "thread_limit": 1},
                    item_order="STRATEGY_INTERNAL",
                    bin_order="SOURCE",
                    seed=row["parameters"].get("seed_requested"),
                    repetition=repetition,
                    input_sha256=fixture_hash(*SCENARIO_FILES[scenario]),
                    capability_status="SUPPORTED_COMPOSED",
                    run_status="COMPLETED" if row["process_exitcode"] == 0 else "ERROR",
                    solution_status=solution_status,
                    proof_status="FEASIBLE" if solution_status == "VALID_COMPLETE" else "UNKNOWN",
                    termination_reason="EXPECTED_BEHAVIOR_PASS" if row["expected_behavior_pass"] else "EXPECTED_BEHAVIOR_FAIL",
                    resources={"solver_s": row["library_elapsed_ms"] / 1000, "wall_s": None, "peak_rss_bytes": None},
                    metrics={
                        "bins_used": row["bins_used"],
                        "packed_items": row["items_placed"],
                        "required_items": row["items_total"],
                        "total_cost": row["total_cost"],
                        "validation_error_count": len(row["validation_errors"]),
                        "expected_behavior_pass": row["expected_behavior_pass"],
                        "seed_effective": row["parameters"].get("seed_effective"),
                        "time_limit_effective": row["parameters"].get("time_limit_effective"),
                    },
                    artifacts={"source_result": f"results/campaign/{directory}/results.json#scenarios.{key}", "validation": "crosslang_validate"},
                )
            )
    return records


def import_skjolber_small(implementations: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    path = CAMPAIGN / "skjolber-algorithms.json"
    source = json.loads(path.read_text())
    logical_input = {
        "container": [10, 10, 10],
        "items": [[2, 2, 2], [2, 2, 3], [2, 3, 2], [3, 2, 2], [3, 3, 2], [2, 3, 3]],
        "rotations": "all_axis_permutations",
    }
    implementation_ids = {
        "plain": "skjolber_plain",
        "laff": "skjolber_laff",
        "fast_brute_force": "skjolber_fast_bruteforce",
    }
    records: list[dict[str, Any]] = []
    for index, row in enumerate(source["records"]):
        implementation_id = implementation_ids[row["algorithm"]]
        valid = row["validation_status"] == "PASS" and row["placements"] == 6
        records.append(
            make_record(
                implementations,
                run_id=f"B06/six_distinct_items_one_bin/{implementation_id}/10s/source/rep-0",
                benchmark_id="B06",
                problem_variant="SMALL_FEASIBILITY",
                instance_id="six_distinct_items_one_bin",
                implementation_id=implementation_id,
                adapter="legacy_import/skjolber_algorithm_small",
                comparison_track="NATIVE",
                problem_scope="FULL_PROBLEM",
                budget={"time_limit_s": 10.0, "memory_limit_bytes": 536870912, "thread_limit": 1},
                item_order="SOURCE",
                bin_order="SOURCE",
                seed=None,
                repetition=0,
                input_sha256=hash_payload(logical_input),
                capability_status="SUPPORTED_NATIVE",
                run_status="TIME_LIMIT" if row["timeout"] else "COMPLETED",
                solution_status="VALID_COMPLETE" if valid else "INVALID_CERTIFICATE",
                proof_status="FEASIBLE" if valid else "UNKNOWN",
                termination_reason="RETURNED_CERTIFICATE",
                resources={"solver_s": row["library_duration_ms"] / 1000, "wall_s": row["wall_time_ms"] / 1000, "peak_rss_bytes": None},
                metrics={"bins_used": row["bins_used"], "packed_items": row["placements"], "required_items": 6, "validation_error_count": len(row["validation_errors"])},
                artifacts={"source_result": f"results/campaign/skjolber-algorithms.json#records[{index}]", "validation": "SkjolberAlgorithmSuite AABB checks"},
            )
        )
    return records


def build_records() -> list[dict[str, Any]]:
    implementations = implementation_index()
    records: list[dict[str, Any]] = []
    records.extend(import_packingsolver_thpack(implementations))
    records.extend(import_python_thpack(implementations))
    skjolber, instance_hashes = import_skjolber_thpack9(implementations)
    records.extend(skjolber)
    records.extend(import_crosslang_thpack9(implementations, instance_hashes))
    records.extend(import_exact(implementations))
    records.extend(import_boxstacks(implementations))
    records.extend(import_crosslang_packingsolver(implementations))
    records.extend(import_rust_strategies(implementations))
    records.extend(import_skjolber_small(implementations))
    records.sort(key=lambda row: row["run_id"])
    run_ids = [row["run_id"] for row in records]
    if len(run_ids) != len(set(run_ids)):
        duplicates = sorted(run_id for run_id in set(run_ids) if run_ids.count(run_id) > 1)
        raise ValueError(f"duplicate normalized run ids: {duplicates}")
    for record in records:
        validate_run_record(record)
    return records


def generated_files() -> dict[Path, str]:
    records = build_records()
    manifest = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n" for record in records)
    counts: dict[str, int] = {}
    for record in records:
        source = record["adapter"] or "NONE"
        counts[source] = counts.get(source, 0) + 1
    summary = {
        "schema_version": 1,
        "protocol_version": "benchmark-protocol/3",
        "record_kind": "LEGACY_BASELINE_IMPORT",
        "run_records": len(records),
        "benchmark_ids": sorted({record["benchmark_id"] for record in records}),
        "implementation_ids": sorted({record["implementation_id"] for record in records}),
        "records_by_adapter": dict(sorted(counts.items())),
        "run_manifest_sha256": hashlib.sha256(manifest.encode("utf-8")).hexdigest(),
        "warning": "These records normalize already archived v1/v2 experiments; artifacts remain at their original paths.",
    }
    return {
        RESULTS_DIR / "run-manifest.jsonl": manifest,
        RESULTS_DIR / "baseline-import-summary.json": canonical_json(summary),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize archived campaign evidence into protocol v3 run records")
    parser.add_argument("--check", action="store_true", help="fail if normalized artifacts are missing or stale")
    args = parser.parse_args()
    files = generated_files()
    if args.check:
        stale = [path for path, content in files.items() if not path.exists() or path.read_text() != content]
        if stale:
            for path in stale:
                print(f"BASELINE_IMPORT_STALE: {path}", file=sys.stderr)
            return 1
        print(f"BASELINE_IMPORT_OK: {len(files)} normalized artifacts are current")
        return 0
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    for path, content in files.items():
        path.write_text(content, encoding="utf-8")
        print(path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
