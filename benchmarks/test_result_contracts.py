from __future__ import annotations

import json
from pathlib import Path

from validation import Box, cumulative_weight_above, validate_aabbs


ROOT = Path(__file__).resolve().parents[1]


def result(name: str) -> dict:
    return json.loads((ROOT / "results" / f"{name}.json").read_text())


def test_independent_aabb_validator_rejects_overlap_bounds_and_weight() -> None:
    placements = [
        Box("a", "bin", 0, 0, 0, 6, 6, 6, 6),
        Box("b", "bin", 5, 5, 5, 6, 6, 6, 6),
    ]
    errors = validate_aabbs(placements, {"bin": (10, 10, 10)}, {"bin": 10})
    assert any("overlaps" in error for error in errors)
    assert any("exceeds bin" in error for error in errors)
    assert any("weight" in error for error in errors)


def test_cumulative_weight_above_uses_vertical_stack() -> None:
    bottom = Box("bottom", "bin", 0, 0, 0, 2, 2, 2, 1)
    top_a = Box("top-a", "bin", 0, 0, 2, 2, 2, 2, 7)
    top_b = Box("top-b", "bin", 0, 0, 4, 2, 2, 2, 11)
    elsewhere = Box("elsewhere", "bin", 3, 0, 2, 2, 2, 2, 100)
    assert cumulative_weight_above(bottom, [bottom, top_a, top_b, elsewhere]) == 18


def test_exact_solver_results_close_their_bounds() -> None:
    ortools = result("ortools")
    assert ortools["status"] == "OPTIMAL"
    assert ortools["objective_bins"] == ortools["best_bound"] == 2

    scip = result("scip")
    assert scip["status"] == "optimal"
    assert scip["objective_bins"] == scip["dual_bound"] == 2
    assert scip["gap"] == 0
    assert scip["validation_errors"] == []


def test_commercial_historical_records_are_excluded_when_fixture_is_inconsistent() -> None:
    for name in ("gurobi_historical", "cplex_historical"):
        record = json.loads((ROOT / "raw" / "experiments" / "commercial" / f"{name}.json").read_text())
        assert record["status"] == "INVALID_HISTORICAL_INCONSISTENT_FIXTURE"
        assert record["objective_bins"] is None
        assert record["reported_objective_bins"] == 8


def test_packingsolver_passes_supported_smoke_cases() -> None:
    cases = result("packingsolver")["cases"]
    for name in ("exact_grid", "rotation_allowed", "weight_limit", "stack_weight_above"):
        assert cases[name]["returncode"] == 0
        assert cases[name]["validation_errors"] == []
    assert cases["rotation_forbidden"]["returncode"] == 0
    assert cases["rotation_forbidden"]["packed"] == 0


def test_packingsolver_known_regressions_remain_visible() -> None:
    cases = result("packingsolver")["cases"]
    for name in ("heterogeneous_cost", "heterogeneous_cost_boxstacks"):
        assert cases[name]["returncode"] != 0
        assert cases[name]["certificate_created"] is False
        assert "VariableSizedBinPacking" in cases[name]["stderr_tail"]
    assert cases["semi_trailer_axle"]["returncode"] != 0
    assert cases["semi_trailer_axle"]["certificate_created"] is False


def test_baselines_keep_their_observed_limitations() -> None:
    py3dbp = result("py3dbp")["scenarios"]
    assert py3dbp["heterogeneous_order_small_first"]["bins_used"] == 2
    assert py3dbp["heterogeneous_order_large_first"]["bins_used"] == 1

    jerry = result("jerry")
    assert jerry["loadbear_is_only_sort_key"] is True
    assert jerry["actual_weight_above_fragile"] == 20


def test_skjolber_java_smoke_contract() -> None:
    scenarios = result("skjolber")["scenarios"]
    assert scenarios["exact_grid"]["success"] is True
    assert scenarios["rotation_allowed_3d"]["success"] is True
    assert scenarios["rotation_forbidden_upright"]["success"] is False
    assert scenarios["weight_limit"]["containers"] == 3
    assert scenarios["hundred_items"]["placements"] == 100
    assert all(case["geometry_valid"] for case in scenarios.values())


def test_public_thpack9_cross_library_contracts() -> None:
    baseline = json.loads((ROOT / "results" / "public" / "thpack9_baselines.json").read_text())
    assert baseline["required_items"] == 70
    assert baseline["source_commit"] == "154a8f006a8e72f65d734f2d1e36777f678f31f8"
    assert baseline["source_sha256"] == "a4f5e3a748709217cdc749f7d27940f15b9f2a31b3e840e725642237036f82cc"
    for result_case in baseline["results"]:
        assert result_case.get("version") or result_case.get("commit")
        assert result_case["validator"] == "benchmarks.validation.validate_aabbs"
        assert result_case["packed"] == result_case["required"] == 70
        assert result_case["unpacked"] == 0
        assert result_case["validation_errors"] == []
        assert result_case["bins_used"] == 50

    patched = json.loads(
        (ROOT / "results" / "public" / "thpack9_instance1_packingsolver_patched.json").read_text()
    )["Output"]["Solution"]
    assert patched["NumberOfItems"] == 70
    assert patched["NumberOfBins"] == patched["BinCost"] == 25

    reverse = json.loads((ROOT / "results" / "public" / "packingsolver_reverse.json").read_text())["Output"]["Solution"]
    reverse_stacks = json.loads(
        (ROOT / "results" / "public" / "packingsolver_boxstacks_reverse.json").read_text()
    )["Output"]["Solution"]
    assert reverse["NumberOfItems"] == reverse_stacks["NumberOfItems"] == 2
    assert reverse["NumberOfBins"] == reverse_stacks["NumberOfBins"] == 2
    assert reverse["BinCost"] == reverse_stacks["BinCost"] == 10

    skjolber = result("skjolber")["scenarios"]["thpack9_instance1"]
    assert skjolber["success"] is True
    assert skjolber["placements"] == 70
    assert skjolber["containers"] == 28
    assert skjolber["geometry_valid"] is True
