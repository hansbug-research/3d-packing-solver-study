from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results" / "campaign"
OUTPUT = RESULTS / "aggregate.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def distribution(values: list[float]) -> dict[str, float | None]:
    return {
        "mean": statistics.fmean(values) if values else None,
        "median": statistics.median(values) if values else None,
        "p95": percentile(values, 0.95),
        "min": min(values) if values else None,
        "max": max(values) if values else None,
    }


def summarize_packingsolver(records: list[dict[str, Any]]) -> dict[str, Any]:
    families: dict[str, Any] = {}
    for family in ("BR", "LN", "IMM"):
        selected = [record for record in records if record["family"] == family]
        source_valid = [record for record in selected if record["source_status"] == "VALID"]
        accepted = [record for record in source_valid if record["status"] == "VALID"]
        quality_field = "packed_volume" if family in {"BR", "LN"} else "bins_used"
        quality = [float(record[quality_field]) for record in accepted]
        families[family] = {
            "objective_kind": selected[0]["objective_kind"],
            "primary_metric": quality_field,
            "instances": len(selected),
            "source_valid": len(source_valid),
            "validated": len(accepted),
            "invalid": sum(record["status"] == "INVALID" for record in source_valid),
            "errors": sum(record["status"] == "ERROR" for record in source_valid),
            "zero_item_incumbents": sum(record.get("packed_items") == 0 for record in accepted),
            "solver_reported_bound_closed": sum(
                record.get("proof_status") == "SOLVER_REPORTED_BOUND_CLOSED" for record in accepted
            ),
            "quality": distribution(quality),
            "volume_utilization": distribution([
                float(record["volume_utilization"])
                for record in accepted
                if record.get("volume_utilization") is not None
            ]) if family in {"BR", "LN"} else None,
            "relative_gap_to_solver_reported_bound": distribution([
                float(record["relative_gap_to_solver_reported_bound"])
                for record in accepted
                if record.get("relative_gap_to_solver_reported_bound") is not None
            ]),
            "wall_time_s": distribution([float(record["wall_time_s"]) for record in source_valid]),
            "max_rss_kib": max((int(record.get("max_rss_kib", 0)) for record in source_valid), default=0),
        }
    return families


def compare_packingsolver_budgets(
    one_second: list[dict[str, Any]],
    ten_seconds: list[dict[str, Any]],
) -> dict[str, Any]:
    one_by_id = {record["instance_id"]: record for record in one_second}
    ten_by_id = {record["instance_id"]: record for record in ten_seconds}
    comparison: dict[str, Any] = {}
    for family in ("BR", "LN", "IMM"):
        pairs = [
            (one_by_id[instance_id], ten_by_id[instance_id])
            for instance_id in sorted(one_by_id.keys() & ten_by_id.keys())
            if one_by_id[instance_id]["family"] == family
            and one_by_id[instance_id].get("status") == "VALID"
            and ten_by_id[instance_id].get("status") == "VALID"
        ]
        if family in {"BR", "LN"}:
            deltas = [float(ten["volume_utilization"]) - float(one["volume_utilization"]) for one, ten in pairs]
            improved = sum(delta > 1e-12 for delta in deltas)
            worsened = sum(delta < -1e-12 for delta in deltas)
            metric = "volume_utilization_delta"
        else:
            deltas = [float(one["bins_used"]) - float(ten["bins_used"]) for one, ten in pairs]
            improved = sum(delta > 0 for delta in deltas)
            worsened = sum(delta < 0 for delta in deltas)
            metric = "bins_saved"
        comparison[family] = {
            "paired_valid": len(pairs),
            "metric": metric,
            "improved": improved,
            "tied": len(pairs) - improved - worsened,
            "worsened": worsened,
            "delta": distribution(deltas),
            "zero_item_incumbents_1s": sum(one.get("packed_items") == 0 for one, _ in pairs),
            "zero_item_incumbents_10s": sum(ten.get("packed_items") == 0 for _, ten in pairs),
        }
    return comparison


def summarize_skjolber(path: Path) -> dict[str, Any]:
    data = read_json(path)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_instance: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for record in data["records"]:
        grouped[record["algorithm"]].append(record)
        by_instance[record["instance_id"]][record["algorithm"]] = record
    algorithms = {}
    for algorithm, records in sorted(grouped.items()):
        valid = [record for record in records if record["status"] == "VALID"]
        algorithms[algorithm] = {
            "records": len(records),
            "validated": len(valid),
            "malformed_source_excluded": sum(
                record["status"] == "MALFORMED_SOURCE_EXCLUDED" for record in records
            ),
            "invalid": sum(record["status"] == "INVALID" for record in records),
            "bins_used": distribution([float(record["bins_used"]) for record in valid]),
            "wall_time_ms": distribution([float(record["wall_time_ms"]) for record in valid]),
        }
    wins = Counter()
    bin_deltas = []
    for algorithms_by_name in by_instance.values():
        if {"laff", "plain"} <= algorithms_by_name.keys():
            laff = algorithms_by_name["laff"]
            plain = algorithms_by_name["plain"]
            if laff["status"] != "VALID" or plain["status"] != "VALID":
                continue
            delta = int(laff["bins_used"]) - int(plain["bins_used"])
            bin_deltas.append(float(delta))
            wins["plain" if delta > 0 else "laff" if delta < 0 else "tie"] += 1
    return {
        "source_commit": data["source_commit"],
        "algorithms": algorithms,
        "paired_laff_vs_plain": {**wins, "laff_minus_plain_bins": distribution(bin_deltas)},
    }


def summarize_exact() -> dict[str, Any]:
    canonical = {}
    for backend in ("cp-sat", "scip", "gurobi", "cplex"):
        data = read_json(RESULTS / f"exact-{backend}.json")
        canonical[backend] = {
            "formulation": data["formulation"],
            "suite_status": data["suite_status"],
            "status_counts": dict(Counter(case["status"] for case in data["cases"])),
            "validation_error_cases": sum(bool(case["validation_errors"]) for case in data["cases"]),
            "wall_time_s": distribution([float(case["wall_time_s"]) for case in data["cases"]]),
        }
    sensitivity = []
    for formulation in ("legacy", "reduced", "strengthened"):
        for backend in ("cp-sat", "scip", "gurobi", "cplex"):
            data = read_json(RESULTS / f"exact-{formulation}-{backend}.json")
            overflow = next(case for case in data["cases"] if case["case"] == "overflow_9")
            sensitivity.append({
                "backend": backend,
                "formulation": formulation,
                "suite_status": data["suite_status"],
                "overflow_status": overflow["status"],
                "overflow_wall_time_s": overflow["wall_time_s"],
                "overflow_error": overflow.get("error"),
            })
    return {"canonical_strengthened": canonical, "formulation_sensitivity": sensitivity}


def summarize_crosslang() -> dict[str, Any]:
    names = (
        "crosslang_cpp_packingsolver_official",
        "crosslang_cpp_packingsolver_fixed",
        "crosslang_go_bp3d",
        "crosslang_rust_unesting",
        "crosslang_rust_unesting_strategies",
    )
    output = {}
    for name in names:
        path = RESULTS / name / "results.json"
        if not path.exists():
            continue
        data = read_json(path)
        scenarios = data["scenarios"]
        summary = {
            "library": data["library"],
            "language": data["language"],
            "commit": data["commit"],
            "algorithm": data["algorithm"],
            "scenario_records": len(scenarios),
            "expected_behavior_pass": sum(
                bool(scenario["expected_behavior_pass"]) for scenario in scenarios.values()
            ),
            "valid_geometry_and_constraints": sum(
                bool(scenario["geometry_and_constraints_valid"]) for scenario in scenarios.values()
            ),
            "invalid_scenarios": sorted(
                scenario_id
                for scenario_id, scenario in scenarios.items()
                if not scenario["geometry_and_constraints_valid"]
            ),
            "capability_status_counts": dict(Counter(
                scenario["capability_status"] for scenario in scenarios.values()
            )),
            "all_expected_behaviors_pass": data["all_expected_behaviors_pass"],
        }
        strategies = sorted({
            scenario.get("parameters", {}).get("strategy_requested")
            for scenario in scenarios.values()
            if scenario.get("parameters", {}).get("strategy_requested")
        })
        if strategies:
            summary["strategy_validation"] = {
                strategy: {
                    "records": sum(
                        scenario.get("parameters", {}).get("strategy_requested") == strategy
                        for scenario in scenarios.values()
                    ),
                    "valid_geometry_and_constraints": sum(
                        scenario.get("parameters", {}).get("strategy_requested") == strategy
                        and bool(scenario["geometry_and_constraints_valid"])
                        for scenario in scenarios.values()
                    ),
                }
                for strategy in strategies
            }
        output[name] = summary
    return output


def summarize_full_thpack9(
    one_second: list[dict[str, Any]],
    ten_seconds: list[dict[str, Any]],
) -> dict[str, Any]:
    implementations: dict[str, list[dict[str, Any]]] = defaultdict(list)
    volume_bounds: dict[str, int] = {}

    for record in one_second:
        if record["family"] == "IMM" and record["source_status"] == "VALID":
            implementations["packingsolver_1s"].append({
                "instance": f"THPACK9-{record['number']:03d}",
                "bins_used": record["bins_used"],
                "valid": record["status"] == "VALID",
            })
    for record in ten_seconds:
        if record["family"] == "IMM" and record["source_status"] == "VALID":
            implementations["packingsolver_10s"].append({
                "instance": f"THPACK9-{record['number']:03d}",
                "bins_used": record["bins_used"],
                "valid": record["status"] == "VALID",
            })

    skjolber = read_json(RESULTS / "skjolber-thpack9.json")
    for record in skjolber["records"]:
        if not record.get("source_line_valid"):
            continue
        implementations[f"skjolber_{record['algorithm']}"].append({
            "instance": record["instance_id"],
            "bins_used": record["bins_used"],
            "valid": record["status"] == "VALID",
        })

    for name, label in (
        ("crosslang_go_bp3d_thpack9", "go_bp3d"),
        ("crosslang_rust_unesting_thpack9", "rust_unesting_extreme_point_adapter"),
    ):
        data = read_json(RESULTS / name / "results.json")
        for record in data["records"]:
            implementations[label].append({
                "instance": record["instance"],
                "bins_used": record["bins_used"],
                "valid": record["status"] == "VALID_COMPLETE",
            })

    python_records_path = ROOT / "raw" / "experiments" / "campaign" / "python_thpack" / "records.jsonl"
    for record in read_jsonl(python_records_path):
        if (
            record.get("family") != "THPACK9"
            or record.get("status") == "MALFORMED_SOURCE_EXCLUDED"
            or "instance" not in record
        ):
            continue
        instance = record["instance"]
        instance_key = record["instance_key"]
        volume_bounds[instance_key] = math.ceil(instance["item_volume"] / instance["container_volume"])
        label = f"{record['library']}_{record['order']}"
        valid = record["status"] == "FEASIBLE_COMPLETE" and not record["validation_errors"]
        implementations[label].append({
            "instance": instance_key,
            "bins_used": record["bins_used"],
            "valid": valid,
        })

    summary = {}
    for label, records in sorted(implementations.items()):
        valid = [record for record in records if record["valid"]]
        bins = [float(record["bins_used"]) for record in valid]
        gaps = [
            (float(record["bins_used"]) - volume_bounds[record["instance"]])
            / volume_bounds[record["instance"]]
            for record in valid
            if record["instance"] in volume_bounds
        ]
        summary[label] = {
            "records": len(records),
            "valid_complete": len(valid),
            "invalid": len(records) - len(valid),
            "bins_used": distribution(bins),
            "relative_gap_to_volume_lower_bound": distribution(gaps),
        }
    return summary


def summarize_rust_strategy_repeats() -> dict[str, Any] | None:
    path = RESULTS / "crosslang_rust_unesting_strategy_repeats" / "results.json"
    if not path.exists():
        return None
    data = read_json(path)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in data["scenarios"].values():
        grouped[record["parameters"]["strategy_requested"]].append(record)
    return {
        strategy: {
            "records": len(records),
            "valid_geometry_and_constraints": sum(
                record["geometry_and_constraints_valid"] for record in records
            ),
            "invalid": sum(not record["geometry_and_constraints_valid"] for record in records),
            "reported_bins_including_invalid": distribution([
                float(record["bins_used"]) for record in records
            ]),
            "seed_effective": all(record["parameters"]["seed_effective"] for record in records),
            "time_limit_effective": all(
                record["parameters"]["time_limit_effective"] for record in records
            ),
        }
        for strategy, records in sorted(grouped.items())
    }


def summarize_targeted_suites() -> dict[str, Any]:
    boxstacks = read_json(RESULTS / "packingsolver-boxstacks.json")
    strategies = read_json(RESULTS / "packingsolver-strategies.json")
    strategy_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in strategies["records"]:
        strategy_groups[record["strategy"]].append(record)
    return {
        "packingsolver_boxstacks": {
            "suite_status": boxstacks["suite_status"],
            "records": len(boxstacks["records"]),
            "status_counts": dict(Counter(record["status"] for record in boxstacks["records"])),
            "cases": [record["case"] for record in boxstacks["records"]],
        },
        "packingsolver_strategies": {
            strategy: {
                "records": len(records),
                "valid": sum(record["status"] == "VALID" for record in records),
                "invalid": sum(record["status"] == "INVALID" for record in records),
                "invalid_instances": [
                    record["instance_id"] for record in records if record["status"] == "INVALID"
                ],
            }
            for strategy, records in sorted(strategy_groups.items())
        },
        "skjolber_algorithm_small": read_json(RESULTS / "skjolber-algorithms.json"),
    }


def main() -> None:
    source_paths = [
        RESULTS / "packingsolver-thpack.jsonl",
        RESULTS / "packingsolver-thpack-summary.json",
        RESULTS / "python_thpack" / "summary.json",
        ROOT / "raw" / "experiments" / "campaign" / "python_thpack" / "records.jsonl",
        RESULTS / "skjolber-thpack9.json",
        RESULTS / "skjolber-algorithms.json",
        RESULTS / "packingsolver-boxstacks.json",
        RESULTS / "packingsolver-strategies.json",
        RESULTS / "industrial-dataset-audit.json",
    ]
    source_paths.extend(
        RESULTS / f"exact-{formulation}{backend}.json"
        for formulation in ("", "legacy-", "reduced-", "strengthened-")
        for backend in ("cp-sat", "scip", "gurobi", "cplex")
    )
    source_paths.extend(
        RESULTS / name / "results.json"
        for name in (
            "crosslang_cpp_packingsolver_official",
            "crosslang_cpp_packingsolver_fixed",
            "crosslang_go_bp3d",
            "crosslang_go_bp3d_thpack9",
            "crosslang_rust_unesting",
            "crosslang_rust_unesting_strategies",
            "crosslang_rust_unesting_strategy_repeats",
            "crosslang_rust_unesting_thpack9",
        )
    )
    one_second = read_jsonl(RESULTS / "packingsolver-thpack.jsonl")
    ten_second_path = RESULTS / "packingsolver-thpack-10s.jsonl"
    ten_seconds = read_jsonl(ten_second_path) if ten_second_path.exists() else []
    if ten_seconds:
        source_paths.extend((
            ten_second_path,
            RESULTS / "packingsolver-thpack-10s-summary.json",
        ))
    python_summary = read_json(RESULTS / "python_thpack" / "summary.json")
    output = {
        "schema_version": 1,
        "source_sha256": {
            path.relative_to(ROOT).as_posix(): sha256(path)
            for path in source_paths
        },
        "packingsolver_thpack": {
            "one_second": summarize_packingsolver(one_second),
            "ten_seconds": summarize_packingsolver(ten_seconds) if ten_seconds else None,
            "paired_budget_comparison": (
                compare_packingsolver_budgets(one_second, ten_seconds) if ten_seconds else None
            ),
        },
        "python_thpack": {
            "coverage": python_summary["coverage"],
            "status_counts": python_summary["status_counts"],
            "library_summary": python_summary["library_summary"],
            "order_sensitivity": python_summary["order_sensitivity"],
            "paired_winners": python_summary["paired_winners"],
        },
        "skjolber_thpack9": summarize_skjolber(RESULTS / "skjolber-thpack9.json"),
        "full_thpack9_quality": summarize_full_thpack9(one_second, ten_seconds),
        "exact_small": summarize_exact(),
        "crosslang": summarize_crosslang(),
        "rust_strategy_repeats": summarize_rust_strategy_repeats(),
        "industrial_dataset_audit": read_json(RESULTS / "industrial-dataset-audit.json"),
        "targeted_suites": summarize_targeted_suites(),
    }
    OUTPUT.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(f"campaign aggregate -> {OUTPUT}")


if __name__ == "__main__":
    main()
