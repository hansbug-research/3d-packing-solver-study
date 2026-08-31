from __future__ import annotations

import copy
import csv
import json
import math
from pathlib import Path

import pytest

from comprehensive.model import build_plan_rows, load_catalogs, validate_plan_rows, validate_run_record


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

    assert summary["run_records"] == 2078
    assert summary["combined_run_records"] == len(records) == 6947
    assert summary["protocol_v3_run_records"] == 4869
    assert len(summary["implementation_ids"]) == 18
    assert aggregate["coverage"]["executed_implementations"] == 19
    assert aggregate["coverage"]["benchmarks_with_runs"] == 13
    assert aggregate["coverage"]["cells_with_evidence"] == 91
    assert aggregate["coverage"]["legacy_baseline_only_cells"] == 45
    assert aggregate["coverage"]["protocol_v3_executed_cells"] == 27
    assert aggregate["coverage"]["protocol_v3_status_only_cells"] == 19
    assert aggregate["coverage"]["record_origin_counts"] == {"LEGACY_BASELINE": 2078, "PROTOCOL_V3": 4869}
    assert aggregate["coverage"]["records_by_benchmark"]["B03"] == 1220
    assert aggregate["coverage"]["records_by_benchmark"]["B07"] == 3600

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
    assert set(rows) == set(expected_means) | {"jerry"}
    assert all(row["common_instances"] == "44" for row in rows.values())
    for implementation_id, expected in expected_means.items():
        assert int(rows[implementation_id]["valid_complete"]) == 44
        assert math.isclose(float(rows[implementation_id]["mean_bins"]), expected, rel_tol=0, abs_tol=1e-12)
    assert int(rows["jerry"]["invalid"]) == 1
