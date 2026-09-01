from __future__ import annotations

import copy
import csv
import json
import math
from pathlib import Path

import pytest

from comprehensive.model import build_plan_rows, load_catalogs, validate_plan_rows, validate_run_record
from comprehensive.import_packingsolver_protocol import build_records as build_packingsolver_protocol_records
from comprehensive.import_fresh_protocol import build_records as build_fresh_protocol_records
from comprehensive.record_source_status import build_records as build_status_records


ROOT = Path(__file__).resolve().parents[1]


def plan_cells() -> dict[tuple[str, str], dict]:
    suites, implementations = load_catalogs()
    rows = build_plan_rows(suites, implementations)
    return {(row["benchmark_id"], row["implementation_id"]): row for row in rows}


def valid_run_record() -> dict:
    return {
        "schema_version": 2,
        "protocol_version": "benchmark-protocol/3",
        "record_origin": "PROTOCOL_V3",
        "run_id": "B06/grid/exact_cp_sat/seed-42/rep-0",
        "benchmark_id": "B06",
        "problem_variant": "IDENTICAL_BIN_PACKING",
        "instance_id": "grid",
        "implementation_id": "exact_cp_sat",
        "algorithm": "strengthened CP-SAT model",
        "adapter": "exact_suite/strengthened",
        "comparison_track": "EXACT_MODEL",
        "problem_scope": "FULL_PROBLEM",
        "budget": {"time_limit_s": 20.0, "memory_limit_bytes": 4294967296, "thread_limit": 1},
        "item_order": "ORIGINAL",
        "bin_order": "ORIGINAL",
        "seed": 42,
        "repetition": 0,
        "input_sha256": "0" * 64,
        "input_status": "VALID",
        "capability_status": "SUPPORTED_NATIVE",
        "run_status": "COMPLETED",
        "solution_status": "VALID_COMPLETE",
        "proof_status": "PROVEN_OPTIMAL",
        "termination_reason": "OPTIMAL",
        "resources": {"wall_s": 0.1, "peak_rss_bytes": 1000000},
        "metrics": {"objective": 1, "bound": 1, "gap": 0.0},
        "artifacts": {"solution": "solution.json", "validation": "validation.json"},
    }


def test_comprehensive_catalog_is_full_cartesian_plan() -> None:
    suites, implementations = load_catalogs()
    rows = build_plan_rows(suites, implementations)
    validate_plan_rows(rows, 32, 19)
    assert len(rows) == 608
    assert {row["benchmark_id"] for row in rows} == {f"B{index:02d}" for index in range(1, 33)}
    assert len({row["implementation_id"] for row in rows}) == 19
    assert all(row["run_status"] == "NOT_RUN" for row in rows)
    assert all(row["solution_status"] == "NOT_APPLICABLE" for row in rows)


def test_known_capability_boundaries_remain_explicit() -> None:
    cells = plan_cells()
    assert cells[("B04", "packingsolver_fork_box")]["capability_status"] == "SUPPORTED_NATIVE"
    assert cells[("B04", "rust_extreme_point")]["capability_status"] == "SUPPORTED_COMPOSED"
    assert cells[("B08", "packingsolver_upstream_box")]["capability_status"] == "SUPPORTED_NATIVE"
    assert "#536" in cells[("B08", "packingsolver_upstream_box")]["status_reason"]
    assert cells[("B14", "jerry")]["capability_status"] == "PROJECTION_ONLY"
    assert "loadbear" in cells[("B14", "jerry")]["status_reason"]
    assert cells[("B22", "packingsolver_fork_box")]["capability_status"] == "NOT_SUPPORTED"
    assert cells[("B30", "exact_cp_sat")]["capability_status"] == "ADAPTER_MISSING"
    assert cells[("B32", "py3dbp")]["capability_status"] == "ADAPTER_MISSING"


def test_source_readiness_is_not_inferred_from_solver_capability() -> None:
    cells = plan_cells()
    assert cells[("B05", "packingsolver_fork_box")]["input_status"] == "SOURCE_INCOMPLETE"
    assert cells[("B05", "packingsolver_fork_box")]["termination_reason"] == "SOURCE_PENDING"
    assert cells[("B30", "packingsolver_fork_box")]["input_status"] == "VALID"
    assert cells[("B30", "packingsolver_fork_box")]["termination_reason"] == "ADAPTER_MISSING"


def test_status_materialization_only_emits_unexecutable_cells() -> None:
    unsupported = build_status_records("B22", "benchmarks/comprehensive/suites.json#B22")
    assert len(unsupported) == 19
    assert {record["capability_status"] for record in unsupported} == {"NOT_SUPPORTED"}
    assert {record["termination_reason"] for record in unsupported} == {"NOT_SUPPORTED"}
    assert len({record["run_id"] for record in unsupported}) == len(unsupported)

    adapter_missing = build_status_records("B30", "benchmarks/comprehensive/suites.json#B30")
    assert adapter_missing
    assert {record["capability_status"] for record in adapter_missing} == {"ADAPTER_MISSING"}
    assert all(record["termination_reason"] == record["capability_status"] for record in adapter_missing)
    assert all(record["input_status"] == "VALID" for record in adapter_missing)

    # A valid source with a runnable capability must remain a real execution
    # task; status materialization must never turn it into a false result.
    b04_status = build_status_records("B04", "benchmarks/comprehensive/suites.json#B04")
    assert "packingsolver_fork_box" not in {record["implementation_id"] for record in b04_status}


def test_packingsolver_thpack_protocol_revalidation_is_explicit() -> None:
    records = build_packingsolver_protocol_records(10.0)
    assert len(records) == 762
    assert {record["benchmark_id"] for record in records} == {"B01", "B02", "B04"}
    assert {record["record_origin"] for record in records} == {"PROTOCOL_V3"}
    assert {record["adapter"] for record in records} == {"packingsolver_thpack_protocol_revalidation_v1"}
    assert all(record["metrics"]["provenance_kind"] == "ARCHIVED_CERTIFICATE_REVALIDATION" for record in records)
    assert all(
        record["input_sha256"] and len(record["input_sha256"]) == 64
        for record in records
        if record["input_status"] == "VALID"
    )


def test_fresh_wave1_protocol_records_are_explicit_and_finite() -> None:
    records = build_fresh_protocol_records()
    assert len(records) == 160
    assert {record["record_origin"] for record in records} == {"PROTOCOL_V3"}
    assert {record["metrics"]["provenance_kind"] for record in records} == {"FRESH_SOLVER_INVOCATION"}
    assert {record["benchmark_id"] for record in records} == {"B04", "B06", "B09"}
    assert {record["implementation_id"] for record in records if record["benchmark_id"] == "B04"} == {
        "skjolber_plain", "skjolber_laff", "skjolber_fast_bruteforce"
    }
    assert all(record["input_sha256"] and len(record["input_sha256"]) == 64 for record in records)


def test_run_record_contract_rejects_false_results() -> None:
    record = valid_run_record()
    validate_run_record(record)

    not_run = copy.deepcopy(record)
    not_run["run_status"] = "NOT_RUN"
    with pytest.raises(ValueError, match="cannot claim a solution"):
        validate_run_record(not_run)

    unsupported = copy.deepcopy(record)
    unsupported["capability_status"] = "NOT_SUPPORTED"
    with pytest.raises(ValueError, match="cannot claim a solution"):
        validate_run_record(unsupported)

    incomplete = copy.deepcopy(record)
    incomplete["input_status"] = "SOURCE_INCOMPLETE"
    with pytest.raises(ValueError, match="cannot be executed"):
        validate_run_record(incomplete)

    invalid_hash = copy.deepcopy(record)
    invalid_hash["input_sha256"] = "z" * 64
    with pytest.raises(ValueError, match="SHA-256"):
        validate_run_record(invalid_hash)

    extra = copy.deepcopy(record)
    extra["solver_says_feasible"] = True
    with pytest.raises(ValueError, match="unsupported fields"):
        validate_run_record(extra)

    non_finite = copy.deepcopy(record)
    non_finite["metrics"]["gap"] = float("nan")
    with pytest.raises(ValueError, match="non-finite JSON number"):
        validate_run_record(non_finite)


def test_b09_python_composed_records_keep_cost_master_boundary() -> None:
    comprehensive = ROOT / "results" / "comprehensive"
    records = [json.loads(line) for line in (comprehensive / "runs" / "B09-python-composed.jsonl").read_text().splitlines()]
    assert len(records) == 4
    assert {record["implementation_id"] for record in records} == {"py3dbp", "jerry"}
    assert {record["problem_variant"] for record in records} == {"LARGE_CHEAPER", "SMALL_CHEAPER"}
    assert all(record["capability_status"] == "SUPPORTED_COMPOSED" for record in records)
    assert all(record["comparison_track"] == "COMPOSED" for record in records)
    assert all(record["solution_status"] == "VALID_COMPLETE" for record in records)
    assert all(record["metrics"]["total_cost"] == 10.0 for record in records)
    ranking = list(csv.DictReader((comprehensive / "rankings" / "variable-cost.csv").open(newline="")))
    composed = [row for row in ranking if row["comparison_track"] == "COMPOSED"]
    assert len(composed) == 16
    assert all(float(row["mean_total_cost"]) == 10.0 for row in composed)


def test_run_record_json_schema_is_pinned_to_protocol_v3() -> None:
    schema = json.loads((ROOT / "benchmarks" / "comprehensive" / "run-record.schema.json").read_text())
    assert schema["properties"]["schema_version"]["const"] == 2
    assert schema["properties"]["protocol_version"]["const"] == "benchmark-protocol/3"
    assert schema["properties"]["record_origin"]["enum"] == ["LEGACY_BASELINE", "PROTOCOL_V3"]
    assert schema["properties"]["benchmark_id"]["pattern"].endswith("3[0-2])$")
    assert schema["additionalProperties"] is False


def test_legacy_baseline_import_and_aggregate_regression() -> None:
    comprehensive = ROOT / "results" / "comprehensive"
    summary = json.loads((comprehensive / "baseline-import-summary.json").read_text())
    aggregate = json.loads((comprehensive / "aggregate.json").read_text())
    records = [json.loads(line) for line in (comprehensive / "run-manifest.jsonl").read_text().splitlines()]

    assert summary["run_records"] == 2122
    assert summary["combined_run_records"] == len(records) == 62880
    assert summary["protocol_v3_run_records"] == 60758
    assert len(summary["implementation_ids"]) == 18
    assert aggregate["coverage"]["executed_implementations"] == 19
    assert aggregate["coverage"]["benchmarks_with_runs"] == 21
    assert aggregate["coverage"]["benchmarks_with_status_records"] == 32
    assert aggregate["coverage"]["cells_with_evidence"] == 529
    assert aggregate["coverage"]["legacy_baseline_only_cells"] == 19
    assert aggregate["coverage"]["protocol_v3_executed_cells"] == 228
    assert aggregate["coverage"]["protocol_v3_status_only_cells"] == 282
    assert aggregate["coverage"]["record_origin_counts"] == {"LEGACY_BASELINE": 2122, "PROTOCOL_V3": 60758}
    assert aggregate["coverage"]["records_by_benchmark"]["B03"] == 1234
    assert aggregate["coverage"]["records_by_benchmark"]["B07"] == 34209
    reliability = [record for record in records if record.get("adapter") == "reliability_v3/parameterized_fixture"]
    assert len(reliability) == 347
    assert {record["benchmark_id"] for record in reliability} == {"B24", "B25", "B26", "B27", "B28", "B29"}
    assert len({record["metrics"].get("runner_sha256") for record in reliability}) == 1
    b25_fork = {record["problem_variant"]: record for record in reliability if record["implementation_id"] == "packingsolver_fork_box" and record["benchmark_id"] == "B25"}
    for variant, expected in {"cost_base": 10.0, "cost_permuted": 10.0, "cost_scaled": 70.0}.items():
        assert math.isclose(float(b25_fork[variant]["metrics"]["total_cost"]), expected, abs_tol=1e-9)
    b29_exact = [record for record in reliability if record["benchmark_id"] == "B29" and record["implementation_id"] == "exact_cp_sat"]
    assert {record["problem_variant"]: record["run_status"] for record in b29_exact} == {"invalid_json": "ERROR", "cancelled": "CANCELLED"}
    for ranking in ("reliability-metamorphic.csv", "reliability-numeric.csv", "reliability-repeatability.csv", "reliability-scalability.csv", "reliability-fault.csv"):
        assert (comprehensive / "rankings" / ranking).exists()

    exact_b07 = [
        record for record in records
        if record["benchmark_id"] == "B07" and record["comparison_track"] == "EXACT_MODEL"
    ]
    assert len(exact_b07) == 4
    assert {record["problem_variant"] for record in exact_b07} == {"SOURCE_ROTATION_FLAGS"}
    assert all(record["solution_status"] == "VALID_PARTIAL" for record in exact_b07)
    assert all(record["proof_status"] == "FEASIBLE" for record in exact_b07)
    exact_rankings = json.loads((comprehensive / "aggregate.json").read_text())["headline"]["exact_proof"]
    assert all(row["instances"] == 5 for row in exact_rankings if row["benchmark_id"] == "B06")
    assert all(row["instances"] == 2 for row in exact_rankings if row["benchmark_id"] == "B09")

    def assert_finite_json(value: object) -> None:
        if isinstance(value, float):
            assert math.isfinite(value)
        elif isinstance(value, dict):
            for child in value.values():
                assert_finite_json(child)
        elif isinstance(value, list):
            for child in value:
                assert_finite_json(child)

    assert_finite_json(records)


def test_b01_b02_projection_campaign_keeps_semantics_and_invalid_certificates() -> None:
    comprehensive = ROOT / "results" / "comprehensive"
    projection_paths = sorted((comprehensive / "runs").glob("B01-B02-python-projection-*.jsonl"))
    assert {path.name for path in projection_paths} == {
        "B01-B02-python-projection-py3dbp-jerry-10s-rep-0.jsonl",
        "B01-B02-python-projection-py3dbp-jerry-1s-rep-0.jsonl",
    }
    projection_records = [
        json.loads(line)
        for path in projection_paths
        for line in path.read_text().splitlines()
        if line
    ]
    assert len(projection_records) == 5720
    assert {record["benchmark_id"] for record in projection_records} == {"B01", "B02"}
    assert {record["implementation_id"] for record in projection_records} == {"py3dbp", "jerry"}
    assert {record["item_order"] for record in projection_records} == {"ASCENDING", "DESCENDING"}
    assert {record["budget"]["time_limit_s"] for record in projection_records} == {1.0, 10.0}
    assert {record["problem_variant"] for record in projection_records} == {"RELAXED_ALL_ROTATIONS"}
    assert {record["problem_scope"] for record in projection_records} == {"GEOMETRY_PROJECTION"}
    assert {record["capability_status"] for record in projection_records} == {"PROJECTION_ONLY"}
    assert all(record["metrics"]["projection_removed_constraints"] == ["source_vertical_flags"] for record in projection_records)
    assert sum(record["solution_status"] == "INVALID_CERTIFICATE" for record in projection_records) == 66

    manifest_records = [json.loads(line) for line in (comprehensive / "run-manifest.jsonl").read_text().splitlines()]
    native = [
        record
        for record in manifest_records
        if record["benchmark_id"] in {"B01", "B02"}
        and record["implementation_id"] in {"py3dbp", "jerry"}
        and record["problem_variant"] != "RELAXED_ALL_ROTATIONS"
    ]
    assert native
    assert all(record["problem_scope"] != "GEOMETRY_PROJECTION" for record in native)


def test_b01_b02_external_projection_campaign_uses_catalog_ids_and_budgets() -> None:
    comprehensive = ROOT / "results" / "comprehensive"
    paths = sorted((comprehensive / "runs").glob("B01-B02-external-projection-*.jsonl"))
    assert {path.name for path in paths} == {
        "B01-B02-external-projection-go_bp3d-rust_extreme_point-1s-rep-0.jsonl",
        "B01-B02-external-projection-go_bp3d-rust_extreme_point-10s-rep-0.jsonl",
        "B01-B02-external-projection-rust_layer-rust_ga-rust_brkga-rust_sa-1s-rep-0.jsonl",
        "B01-B02-external-projection-rust_layer-rust_ga-rust_brkga-rust_sa-10s-rep-0.jsonl",
    }
    records = [json.loads(line) for path in paths for line in path.read_text().splitlines() if line]
    assert len(records) == 17160
    assert {record["benchmark_id"] for record in records} == {"B01", "B02"}
    assert {record["implementation_id"] for record in records} == {
        "go_bp3d", "rust_extreme_point", "rust_layer", "rust_ga", "rust_brkga", "rust_sa",
    }
    assert {record["budget"]["time_limit_s"] for record in records} == {1.0, 10.0}
    assert {record["item_order"] for record in records} == {"ASCENDING", "DESCENDING"}
    assert all(record["problem_variant"] == "RELAXED_ALL_ROTATIONS" for record in records)
    assert all(record["problem_scope"] == "GEOMETRY_PROJECTION" for record in records)
    assert all(record["capability_status"] == "PROJECTION_ONLY" for record in records)


def test_b07_version_pairwise_is_complete_and_reproducible() -> None:
    path = ROOT / "results" / "comprehensive" / "rankings" / "B07-version-pairwise.csv"
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 18
    assert {(row["source_group"], row["time_limit_s"]) for row in rows} == {
        (group, budget) for group in ("BR0", "BR8", "BR9", "BR10", "BR11", "BR12", "BR13", "BR14", "BR15")
        for budget in ("1.0", "10.0")
    }
    assert all(int(row["common_instances"]) == 100 for row in rows)
    assert all(int(row["valid_comparable_instances"]) == 100 for row in rows)
    ten_second = [row for row in rows if row["time_limit_s"] == "10.0"]
    assert sum(int(row["upstream_wins"]) for row in ten_second) == 13
    assert sum(int(row["ties"]) for row in ten_second) == 834
    assert sum(int(row["fork_wins"]) for row in ten_second) == 53


def test_b07_external_projection_campaign_is_complete_and_provenanced() -> None:
    comprehensive = ROOT / "results" / "comprehensive"
    paths = sorted((comprehensive / "runs").glob("B07-external-projection-*.jsonl"))
    assert {path.name for path in paths} == {
        "B07-external-projection-go_bp3d-rust_extreme_point-rust_layer-rust_ga-rust_brkga-rust_sa-1s-rep-0.jsonl",
        "B07-external-projection-go_bp3d-rust_extreme_point-rust_layer-rust_ga-rust_brkga-rust_sa-10s-rep-0.jsonl",
    }
    records = [json.loads(line) for path in paths for line in path.read_text().splitlines() if line]
    assert len(records) == 21600
    assert len({record["run_id"] for record in records}) == len(records)
    assert {record["implementation_id"] for record in records} == {
        "go_bp3d", "rust_extreme_point", "rust_layer", "rust_ga", "rust_brkga", "rust_sa",
    }
    assert {record["budget"]["time_limit_s"] for record in records} == {1.0, 10.0}
    assert {record["item_order"] for record in records} == {"ASCENDING", "DESCENDING"}
    assert {record["metrics"]["source_group"] for record in records} == {
        "BR0", "BR8", "BR9", "BR10", "BR11", "BR12", "BR13", "BR14", "BR15",
    }
    assert all(record["problem_variant"] == "RELAXED_ALL_ROTATIONS" for record in records)
    assert all(record["problem_scope"] == "GEOMETRY_PROJECTION" for record in records)
    assert all(record["capability_status"] == "PROJECTION_ONLY" for record in records)
    assert all(record["metrics"]["source_items_sha256"] and record["metrics"]["source_bins_sha256"] for record in records)


def test_b07_python_projection_campaign_and_fixpoint_control() -> None:
    comprehensive = ROOT / "results" / "comprehensive"
    paths = sorted((comprehensive / "runs").glob("B07-python-projection-*.jsonl"))
    assert {path.name for path in paths} == {
        "B07-python-projection-jerry-1s-rep-0.jsonl",
        "B07-python-projection-jerry-10s-rep-0.jsonl",
        "B07-python-projection-jerry-nofix-10s-rep-0.jsonl",
        "B07-python-projection-py3dbp-1s-rep-0.jsonl",
        "B07-python-projection-py3dbp-10s-rep-0.jsonl",
    }
    records = [json.loads(line) for path in paths for line in path.read_text().splitlines() if line]
    assert len(records) == 9000
    assert len({record["run_id"] for record in records}) == len(records)
    assert {record["implementation_id"] for record in records} == {"py3dbp", "jerry"}
    assert {record["metrics"]["source_group"] for record in records} == {
        "BR0", "BR8", "BR9", "BR10", "BR11", "BR12", "BR13", "BR14", "BR15",
    }
    assert all(record["problem_variant"] == "RELAXED_ALL_ROTATIONS" for record in records)
    assert all(record["problem_scope"] == "GEOMETRY_PROJECTION" for record in records)
    assert all(record["metrics"]["source_items_sha256"] and record["metrics"]["source_bins_sha256"] for record in records)
    fix_true = [record for record in records if record["adapter"] == "b07_python_projection_v1" and record["implementation_id"] == "jerry" and record["budget"]["time_limit_s"] == 10.0]
    fix_false = [record for record in records if record["adapter"] == "b07_python_projection_nofix_v1"]
    assert len(fix_true) == len(fix_false) == 1800
    assert sum(record["solution_status"] == "INVALID_CERTIFICATE" for record in fix_true) == 166
    assert sum(record["solution_status"] == "INVALID_CERTIFICATE" for record in fix_false) == 0
    assert sum(record["solution_status"] == "NO_SOLUTION" for record in fix_true) == 151
    assert sum(record["solution_status"] == "NO_SOLUTION" for record in fix_false) == 86


def test_b07_projection_common_and_jerry_control_rankings() -> None:
    rankings = ROOT / "results" / "comprehensive" / "rankings"
    with (rankings / "B07-projection-common.csv").open(newline="") as handle:
        common = list(csv.DictReader(handle))
    assert len(common) == 16
    assert {row["implementation_id"] for row in common} == {
        "go_bp3d", "jerry", "py3dbp", "rust_brkga", "rust_extreme_point", "rust_ga", "rust_layer", "rust_sa",
    }
    assert {row["common_valid_instances"] for row in common if row["item_order"] == "ASCENDING"} == {"855"}
    assert {row["common_valid_instances"] for row in common if row["item_order"] == "DESCENDING"} == {"859"}
    descending = {row["implementation_id"]: float(row["mean_volume_utilization"]) for row in common if row["item_order"] == "DESCENDING"}
    assert descending["rust_extreme_point"] > descending["py3dbp"] == descending["jerry"] > descending["go_bp3d"]
    with (rankings / "B07-jerry-fixpoint-pairwise.csv").open(newline="") as handle:
        controls = {row["item_order"]: row for row in csv.DictReader(handle)}
    overall = controls["ALL"]
    assert (overall["common_records"], overall["common_valid_records"]) == ("1800", "1483")
    assert (overall["fix_true_invalid_certificates"], overall["fix_false_invalid_certificates"]) == ("166", "0")
    assert (overall["fix_false_wins"], overall["ties"], overall["fix_false_losses"]) == ("44", "75", "1364")


def test_constraint_adapter_projection_campaign_is_complete_and_independently_validated() -> None:
    path = ROOT / "results" / "comprehensive" / "runs" / "constraint-adapters-b12-b13-b15-b17.jsonl"
    records = [json.loads(line) for line in path.read_text().splitlines() if line]
    assert len(records) == 80
    assert len({record["run_id"] for record in records}) == 80
    assert {record["benchmark_id"] for record in records} == {"B12", "B13", "B15", "B16", "B17", "B18"}
    assert {record["implementation_id"] for record in records} == {
        "py3dbp", "jerry", "go_bp3d", "rust_extreme_point", "rust_layer", "rust_ga", "rust_brkga", "rust_sa",
    }
    assert all(record["capability_status"] == "PROJECTION_ONLY" for record in records)
    assert all(record["problem_scope"] == "GEOMETRY_PROJECTION" for record in records)
    assert all(record["metrics"]["projection_removed_constraints"] for record in records)
    b13 = [record for record in records if record["benchmark_id"] == "B13"]
    assert {record["solution_status"] for record in b13} == {"CONSTRAINT_VIOLATION", "VALID_COMPLETE"}
    b15_infeasible = [record for record in records if record["benchmark_id"] == "B15" and record["problem_variant"] == "AXLE_INFEASIBLE"]
    assert len(b15_infeasible) == 8
    assert all(record["solution_status"] == "CONSTRAINT_VIOLATION" for record in b15_infeasible)
    for benchmark_id in ("B16", "B18"):
        extension = [record for record in records if record["benchmark_id"] == benchmark_id]
        assert len(extension) == 8
        assert all(record["solution_status"] == "CONSTRAINT_VIOLATION" for record in extension)


def test_b03_rankings_keep_pose_tracks_and_exact_scale_separate() -> None:
    path = ROOT / "results" / "comprehensive" / "rankings" / "profit-knapsack.csv"
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    variants = {row["problem_variant"] for row in rows}
    assert variants == {"FIXED_XYZ", "RELAXED_ALL_ROTATIONS"}
    assert all(row["instances"] == "60" for row in rows)
    assert all(row["valid_rate"] == "1.0" for row in rows if row["implementation_id"] != "jerry" or row["time_limit_s"] == "10.0")
    assert any(row["implementation_id"] == "jerry" and row["invalid_instances"] == "1" for row in rows)

    exact = ROOT / "results" / "comprehensive" / "rankings" / "exact-proof.csv"
    with exact.open(newline="") as handle:
        exact_rows = list(csv.DictReader(handle))
    b03 = [row for row in exact_rows if row["benchmark_id"] == "B03"]
    assert len(b03) == 1
    assert b03[0]["instances"] == "20"
    assert b03[0]["proven"] == "13"


def test_identical_bin_ranking_uses_common_44_instance_set() -> None:
    path = ROOT / "results" / "comprehensive" / "rankings" / "identical-bin-packing.csv"
    with path.open(newline="") as handle:
        rows = {row["implementation_id"]: row for row in csv.DictReader(handle)}
    expected_means = {
        "packingsolver_fork_box": 15.477272727272727,
        "skjolber_plain": 17.795454545454547,
        "rust_extreme_point": 18.40909090909091,
        "py3dbp": 18.431818181818183,
        "go_bp3d": 19.931818181818183,
        "skjolber_laff": 20.84090909090909,
    }
    assert set(rows) == set(expected_means) | {"jerry", "skjolber_fast_bruteforce"}
    assert all(row["common_instances"] == "44" for row in rows.values())
    for implementation_id, expected in expected_means.items():
        assert int(rows[implementation_id]["valid_complete"]) == 44
        assert math.isclose(float(rows[implementation_id]["mean_bins"]), expected, rel_tol=0, abs_tol=1e-12)
    assert int(rows["skjolber_fast_bruteforce"]["valid_complete"]) == 7
    assert int(rows["skjolber_fast_bruteforce"]["invalid"]) == 37
    assert math.isclose(float(rows["skjolber_fast_bruteforce"]["mean_bins"]), 38.57142857142857, rel_tol=0, abs_tol=1e-12)
    assert int(rows["jerry"]["invalid"]) == 1
