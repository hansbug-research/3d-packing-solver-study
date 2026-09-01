from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from model import RESULTS_DIR, ROOT, canonical_json, validate_run_record


VALID_SOLUTIONS = {"VALID_COMPLETE", "VALID_PARTIAL"}


def executed(record: dict[str, Any]) -> bool:
    """Return whether a run has actually executed.

    Capability/source status rows are intentionally part of the manifest, but
    they have no budget or objective sample and must not enter rankings.
    """

    return record["run_status"] != "NOT_RUN"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def nearest_rank(values: list[float], percentile: float) -> float | None:
    finite = [value for value in values if math.isfinite(value)]
    if not finite:
        return None
    ordered = sorted(finite)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def mean(values: Iterable[float | int | None]) -> float | None:
    present = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return statistics.fmean(present) if present else None


def median(values: Iterable[float | int | None]) -> float | None:
    present = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return statistics.median(present) if present else None


def write_csv(rows: list[dict[str, Any]], fields: list[str]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field) for field in fields})
    return output.getvalue()


def canonical_instance(record: dict[str, Any]) -> str:
    instance_id = record["instance_id"]
    if record["benchmark_id"] == "B01":
        match = __import__("re").fullmatch(r"BR:BR(\d+)\.txt:(\d+)", instance_id)
        if match:
            return f"THPACK{match.group(1)}-{int(match.group(2)):03d}"
    if record["benchmark_id"] == "B02" and instance_id.startswith("LN:thpack8.txt:"):
        return f"THPACK8-{int(instance_id.rsplit(':', 1)[1]):03d}"
    if record["benchmark_id"] == "B04" and instance_id.startswith("IMM:thpack9.txt:"):
        return f"THPACK9-{int(instance_id.rsplit(':', 1)[1]):03d}"
    return instance_id.upper().replace("THPACK9_INSTANCE1", "THPACK9-001")


def validate_records(records: list[dict[str, Any]]) -> None:
    run_ids: set[str] = set()
    for record in records:
        validate_run_record(record)
        if record["run_id"] in run_ids:
            raise ValueError(f"duplicate run id: {record['run_id']}")
        run_ids.add(record["run_id"])
        for artifact in record["artifacts"].values():
            if not artifact or artifact.startswith("offline ") or artifact.startswith("exact_suite") or artifact.startswith("independent ") or artifact.startswith("crosslang_") or artifact.startswith("packingsolver_") or artifact.startswith("Skjolber"):
                continue
            path_text = artifact.split("#", 1)[0]
            if "/" in path_text and not (ROOT / path_text).exists():
                raise ValueError(f"run artifact is missing: {record['run_id']}: {path_text}")


def execution_coverage(plan: list[dict[str, Any]], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runs: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        runs[(record["benchmark_id"], record["implementation_id"])].append(record)
    rows: list[dict[str, Any]] = []
    for cell in plan:
        cell_runs = runs.get((cell["benchmark_id"], cell["implementation_id"]), [])
        legacy_runs = [record for record in cell_runs if record["record_origin"] == "LEGACY_BASELINE"]
        protocol_runs = [record for record in cell_runs if record["record_origin"] == "PROTOCOL_V3"]
        executed_protocol_runs = [record for record in protocol_runs if record["run_status"] != "NOT_RUN"]
        status_counts = Counter(record["solution_status"] for record in cell_runs)
        run_counts = Counter(record["run_status"] for record in cell_runs)
        if executed_protocol_runs and legacy_runs:
            execution_status = "PROTOCOL_V3_WITH_LEGACY_BASELINE"
        elif executed_protocol_runs:
            execution_status = "PROTOCOL_V3_EXECUTED"
        elif protocol_runs and legacy_runs:
            execution_status = "PROTOCOL_V3_STATUS_ONLY_WITH_LEGACY_BASELINE"
        elif protocol_runs:
            execution_status = "PROTOCOL_V3_STATUS_ONLY"
        elif legacy_runs:
            execution_status = "LEGACY_BASELINE_ONLY"
        else:
            execution_status = cell["termination_reason"]
        rows.append(
            {
                "benchmark_id": cell["benchmark_id"],
                "benchmark_name": cell["benchmark_name"],
                "category": cell["category"],
                "problem_family": cell["problem_family"],
                "implementation_id": cell["implementation_id"],
                "library": cell["library"],
                "algorithm": cell["algorithm"],
                "planned_input_status": cell["input_status"],
                "planned_capability_status": cell["capability_status"],
                "comparison_track": cell["comparison_track"],
                "problem_scope": cell["problem_scope"],
                "run_records": len(cell_runs),
                "legacy_run_records": len(legacy_runs),
                "protocol_v3_run_records": len(protocol_runs),
                "protocol_v3_executed_records": len(executed_protocol_runs),
                "protocol_v3_not_run_records": len(protocol_runs) - len(executed_protocol_runs),
                "unique_instances": len({canonical_instance(record) for record in cell_runs}),
                "completed": run_counts["COMPLETED"],
                "time_limit": run_counts["TIME_LIMIT"],
                "error": run_counts["ERROR"],
                "valid_complete": status_counts["VALID_COMPLETE"],
                "valid_partial": status_counts["VALID_PARTIAL"],
                "invalid_certificate": status_counts["INVALID_CERTIFICATE"],
                "constraint_violation": status_counts["CONSTRAINT_VIOLATION"],
                "no_solution": status_counts["NO_SOLUTION"],
                "execution_status": execution_status,
            }
        )
    return rows


def volume_rankings(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if not executed(record) or record["benchmark_id"] not in {"B01", "B02", "B07"}:
            continue
        key = (
            record["benchmark_id"],
            record["problem_variant"],
            record["problem_scope"],
            record["comparison_track"],
            record["implementation_id"],
            record["budget"]["time_limit_s"],
            record["item_order"],
            record["adapter"],
        )
        groups[key].append(record)
    rows: list[dict[str, Any]] = []
    for key, group in groups.items():
        valid = [record for record in group if record["solution_status"] in VALID_SOLUTIONS]
        utilizations = [record["metrics"].get("volume_utilization") for record in valid]
        instance_set = sorted(canonical_instance(record) for record in group)
        rows.append(
            {
                "benchmark_id": key[0],
                "problem_variant": key[1],
                "problem_scope": key[2],
                "comparison_track": key[3],
                "implementation_id": key[4],
                "time_limit_s": key[5],
                "item_order": key[6],
                "adapter": key[7],
                "rank_scope": "PER_SUPPORTED_INSTANCE_SET",
                "planned_records": len(group),
                "valid_records": len(valid),
                "invalid_records": len(group) - len(valid),
                "valid_rate": len(valid) / len(group),
                "instance_set_sha256": hashlib.sha256(("\n".join(instance_set) + "\n").encode()).hexdigest(),
                "mean_volume_utilization": mean(utilizations),
                "median_volume_utilization": median(utilizations),
                "p95_volume_utilization": nearest_rank([float(value) for value in utilizations if value is not None], 0.95),
                "mean_wall_s": mean(record["resources"].get("wall_s") for record in valid),
            }
        )
    rows.sort(key=lambda row: (row["benchmark_id"], -row["valid_rate"], -(row["mean_volume_utilization"] or -1), row["implementation_id"], row["item_order"]))
    return rows


def canonical_volume_records(records: list[dict[str, Any]], benchmark_id: str) -> dict[str, dict[str, dict[str, Any]]]:
    selected: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for record in records:
        if record["benchmark_id"] != benchmark_id:
            continue
        implementation_id = record["implementation_id"]
        canonical = False
        if implementation_id == "packingsolver_fork_box":
            if benchmark_id in {"B01", "B02"}:
                canonical = (
                    record["adapter"] == "packingsolver_thpack_protocol_revalidation_v1"
                    and record["budget"]["time_limit_s"] == 10.0
                )
            else:
                canonical = record["adapter"] == "legacy_import/packingsolver_thpack_v2" and record["budget"]["time_limit_s"] == 10.0
        elif implementation_id in {"py3dbp", "jerry"}:
            canonical = record["adapter"] == "legacy_import/python_thpack_v1" and record["item_order"] == "DESCENDING"
        if canonical:
            selected[implementation_id][canonical_instance(record)] = record
    return selected


def volume_common_rankings(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for benchmark_id in ("B01", "B02"):
        selected = canonical_volume_records(records, benchmark_id)
        if len(selected) < 2:
            continue
        common = set.intersection(*(set(by_instance) for by_instance in selected.values()))
        common_hash = hashlib.sha256(("\n".join(sorted(common)) + "\n").encode()).hexdigest()
        for implementation_id, by_instance in selected.items():
            group = [by_instance[instance] for instance in sorted(common)]
            valid = [record for record in group if record["solution_status"] in VALID_SOLUTIONS]
            values = [record["metrics"].get("volume_utilization") for record in valid]
            rows.append(
                {
                    "benchmark_id": benchmark_id,
                    "implementation_id": implementation_id,
                    "common_implementations": len(selected),
                    "common_instances": len(common),
                    "common_instance_set_sha256": common_hash,
                    "valid_records": len(valid),
                    "invalid_records": len(group) - len(valid),
                    "mean_volume_utilization": mean(values),
                    "median_volume_utilization": median(values),
                }
            )
    rows.sort(key=lambda row: (row["benchmark_id"], row["invalid_records"], -(row["mean_volume_utilization"] or -1)))
    return rows


def b07_version_pairwise_rankings(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compare the pinned fork and patched upstream on the identical B07 cells.

    This is deliberately separate from the library ranking: the two rows are
    source variants of the same solver, and the result is useful for tracking
    fork drift without treating the patched upstream checkout as an official
    release.
    """
    selected: dict[tuple[str, float, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for record in records:
        if record["benchmark_id"] != "B07" or record["implementation_id"] not in {
            "packingsolver_fork_box",
            "packingsolver_upstream_box",
        }:
            continue
        source_group = record["metrics"].get("source_group")
        if not source_group:
            continue
        key = (source_group, float(record["budget"]["time_limit_s"]), record["implementation_id"])
        selected[key][record["instance_id"]] = record

    rows: list[dict[str, Any]] = []
    for source_group, time_limit_s in sorted({(key[0], key[1]) for key in selected}):
        fork = selected.get((source_group, time_limit_s, "packingsolver_fork_box"), {})
        upstream = selected.get((source_group, time_limit_s, "packingsolver_upstream_box"), {})
        common = sorted(set(fork) & set(upstream))
        deltas: list[float] = []
        fork_values: list[float] = []
        upstream_values: list[float] = []
        fork_wins = ties = upstream_wins = 0
        for instance in common:
            fork_record = fork[instance]
            upstream_record = upstream[instance]
            if fork_record["solution_status"] not in VALID_SOLUTIONS or upstream_record["solution_status"] not in VALID_SOLUTIONS:
                continue
            fork_value = fork_record["metrics"].get("volume_utilization")
            upstream_value = upstream_record["metrics"].get("volume_utilization")
            if fork_value is None or upstream_value is None:
                continue
            fork_value = float(fork_value)
            upstream_value = float(upstream_value)
            fork_values.append(fork_value)
            upstream_values.append(upstream_value)
            deltas.append(upstream_value - fork_value)
            if upstream_value > fork_value:
                upstream_wins += 1
            elif upstream_value < fork_value:
                fork_wins += 1
            else:
                ties += 1
        rows.append(
            {
                "source_group": source_group,
                "time_limit_s": time_limit_s,
                "left": "packingsolver_fork_box",
                "right": "packingsolver_upstream_box",
                "common_instances": len(common),
                "valid_comparable_instances": len(deltas),
                "fork_wins": fork_wins,
                "ties": ties,
                "upstream_wins": upstream_wins,
                "mean_fork_utilization": mean(fork_values),
                "mean_upstream_utilization": mean(upstream_values),
                "mean_delta_upstream_minus_fork": mean(deltas),
                "median_delta_upstream_minus_fork": median(deltas),
            }
        )
    return rows


def b07_projection_common_rankings(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    adapters = {
        "go_bp3d": "thpack_external_projection_v1",
        "rust_extreme_point": "thpack_external_projection_v1",
        "rust_layer": "thpack_external_projection_v1",
        "rust_ga": "thpack_external_projection_v1",
        "rust_brkga": "thpack_external_projection_v1",
        "rust_sa": "thpack_external_projection_v1",
        "py3dbp": "b07_python_projection_v1",
        "jerry": "b07_python_projection_nofix_v1",
    }
    rows: list[dict[str, Any]] = []
    for item_order in ("ASCENDING", "DESCENDING"):
        selected: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        for record in records:
            implementation_id = record["implementation_id"]
            if (
                executed(record)
                and
                record["benchmark_id"] == "B07"
                and record["problem_variant"] == "RELAXED_ALL_ROTATIONS"
                and record["problem_scope"] == "GEOMETRY_PROJECTION"
                and float(record["budget"]["time_limit_s"]) == 10.0
                and record["item_order"] == item_order
                and adapters.get(implementation_id) == record["adapter"]
            ):
                selected[implementation_id][record["instance_id"]] = record
        if set(selected) != set(adapters):
            continue
        valid_sets = [
            {instance for instance, record in by_instance.items() if record["solution_status"] in VALID_SOLUTIONS}
            for by_instance in selected.values()
        ]
        common = set.intersection(*valid_sets)
        common_hash = hashlib.sha256(("\n".join(sorted(common)) + "\n").encode()).hexdigest()
        for implementation_id, by_instance in selected.items():
            values = [by_instance[instance]["metrics"].get("volume_utilization") for instance in sorted(common)]
            statuses = Counter(record["solution_status"] for record in by_instance.values())
            rows.append(
                {
                    "problem_variant": "RELAXED_ALL_ROTATIONS",
                    "time_limit_s": 10.0,
                    "item_order": item_order,
                    "implementation_id": implementation_id,
                    "adapter": adapters[implementation_id],
                    "participating_implementations": len(adapters),
                    "source_instances": len(by_instance),
                    "common_valid_instances": len(common),
                    "common_instance_set_sha256": common_hash,
                    "valid_on_source_instances": sum(statuses[status] for status in VALID_SOLUTIONS),
                    "invalid_certificates": statuses["INVALID_CERTIFICATE"],
                    "no_solution": statuses["NO_SOLUTION"],
                    "mean_volume_utilization": mean(values),
                    "median_volume_utilization": median(values),
                    "p95_volume_utilization": nearest_rank([float(value) for value in values if value is not None], 0.95),
                }
            )
    rows.sort(key=lambda row: (row["item_order"], -(row["mean_volume_utilization"] or -1), row["implementation_id"]))
    return rows


def b07_jerry_fixpoint_pairwise(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[tuple[str, str], dict[tuple[str, str], dict[str, Any]]] = defaultdict(dict)
    adapters = {
        "fix_point_true": "b07_python_projection_v1",
        "fix_point_false": "b07_python_projection_nofix_v1",
    }
    for record in records:
        if (
            executed(record)
            and
            record["benchmark_id"] == "B07"
            and record["implementation_id"] == "jerry"
            and float(record["budget"]["time_limit_s"]) == 10.0
        ):
            for label, adapter in adapters.items():
                if record["adapter"] == adapter:
                    selected[(label, record["item_order"])][(record["instance_id"], record["item_order"])] = record

    rows: list[dict[str, Any]] = []
    for item_order in ("ASCENDING", "DESCENDING", "ALL"):
        if item_order == "ALL":
            left = {key: record for (label, _), values in selected.items() if label == "fix_point_true" for key, record in values.items()}
            right = {key: record for (label, _), values in selected.items() if label == "fix_point_false" for key, record in values.items()}
        else:
            left = selected.get(("fix_point_true", item_order), {})
            right = selected.get(("fix_point_false", item_order), {})
        common = sorted(set(left) & set(right))
        deltas = []
        for key in common:
            if left[key]["solution_status"] in VALID_SOLUTIONS and right[key]["solution_status"] in VALID_SOLUTIONS:
                deltas.append(float(right[key]["metrics"]["volume_utilization"]) - float(left[key]["metrics"]["volume_utilization"]))
        left_status = Counter(left[key]["solution_status"] for key in common)
        right_status = Counter(right[key]["solution_status"] for key in common)
        rows.append(
            {
                "item_order": item_order,
                "common_records": len(common),
                "common_valid_records": len(deltas),
                "fix_true_invalid_certificates": left_status["INVALID_CERTIFICATE"],
                "fix_false_invalid_certificates": right_status["INVALID_CERTIFICATE"],
                "fix_true_no_solution": left_status["NO_SOLUTION"],
                "fix_false_no_solution": right_status["NO_SOLUTION"],
                "fix_false_wins": sum(delta > 0 for delta in deltas),
                "ties": sum(delta == 0 for delta in deltas),
                "fix_false_losses": sum(delta < 0 for delta in deltas),
                "mean_delta_fix_false_minus_true": mean(deltas),
                "median_delta_fix_false_minus_true": median(deltas),
            }
        )
    return rows


def canonical_b04(records: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    selected: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for record in records:
        if not executed(record) or record["benchmark_id"] != "B04":
            continue
        implementation_id = record["implementation_id"]
        adapter = record["adapter"]
        canonical = False
        if implementation_id == "packingsolver_fork_box":
            canonical = adapter == "legacy_import/packingsolver_thpack_v2" and record["budget"]["time_limit_s"] == 1.0
        elif implementation_id in {"py3dbp", "jerry"}:
            canonical = adapter == "legacy_import/python_thpack_v1" and record["item_order"] == "DESCENDING"
        elif implementation_id in {"skjolber_plain", "skjolber_laff", "skjolber_fast_bruteforce"}:
            canonical = adapter == "legacy_import/skjolber_thpack9_v1"
        elif implementation_id == "go_bp3d":
            canonical = adapter == "legacy_import/native_multi_bin"
        elif implementation_id == "rust_extreme_point":
            canonical = adapter == "legacy_import/repeated_single_boundary"
        if canonical:
            selected[implementation_id][canonical_instance(record)] = record
    return selected


def identical_bin_rankings(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected = canonical_b04(records)
    if not selected:
        return [], []
    common = set.intersection(*(set(by_instance) for by_instance in selected.values()))
    if not common:
        return [], []
    common_hash = hashlib.sha256(("\n".join(sorted(common)) + "\n").encode()).hexdigest()
    ranking: list[dict[str, Any]] = []
    for implementation_id, by_instance in selected.items():
        group = [by_instance[instance] for instance in sorted(common)]
        valid = [record for record in group if record["solution_status"] == "VALID_COMPLETE"]
        bins = [record["metrics"].get("bins_used") for record in valid]
        invalid = sum(record["solution_status"] in {"INVALID_CERTIFICATE", "CONSTRAINT_VIOLATION"} for record in group)
        incomplete = len(group) - len(valid) - invalid
        ranking.append(
            {
                "implementation_id": implementation_id,
                "common_instances": len(common),
                "common_instance_set_sha256": common_hash,
                "valid_complete": len(valid),
                "invalid": invalid,
                "incomplete": incomplete,
                "invalid_rate": invalid / len(group),
                "incomplete_rate": incomplete / len(group),
                "mean_bins": mean(bins),
                "median_bins": median(bins),
                "p95_bins": nearest_rank([float(value) for value in bins if value is not None], 0.95),
                "mean_wall_s": mean(record["resources"].get("wall_s") for record in valid),
                "mean_solver_s": mean(record["resources"].get("solver_s") for record in valid),
            }
        )
    ranking.sort(key=lambda row: (row["invalid_rate"], row["incomplete_rate"], row["mean_bins"] or math.inf))

    pairwise: list[dict[str, Any]] = []
    implementation_ids = sorted(selected)
    for left_index, left_id in enumerate(implementation_ids):
        for right_id in implementation_ids[left_index + 1 :]:
            left, right = selected[left_id], selected[right_id]
            pair_common = sorted(set(left) & set(right))
            wins = ties = losses = comparable = 0
            for instance in pair_common:
                left_record, right_record = left[instance], right[instance]
                if left_record["solution_status"] != "VALID_COMPLETE" or right_record["solution_status"] != "VALID_COMPLETE":
                    continue
                comparable += 1
                left_bins = left_record["metrics"]["bins_used"]
                right_bins = right_record["metrics"]["bins_used"]
                if left_bins < right_bins:
                    wins += 1
                elif left_bins > right_bins:
                    losses += 1
                else:
                    ties += 1
            pairwise.append(
                {
                    "left": left_id,
                    "right": right_id,
                    "source_common_instances": len(pair_common),
                    "valid_comparable_instances": comparable,
                    "left_wins": wins,
                    "ties": ties,
                    "left_losses": losses,
                }
            )
    return ranking, pairwise


def exact_rankings(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # A fresh protocol run supersedes an archived baseline for the same
    # logical case.  Keeping one record per case prevents re-runs from
    # inflating proof rates or sample counts.
    selected: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for record in records:
        if not executed(record) or record["benchmark_id"] not in {"B03", "B06", "B07", "B09"} or record["comparison_track"] != "EXACT_MODEL":
            continue
        key = (
            record["benchmark_id"],
            record["implementation_id"],
            record["problem_variant"],
            canonical_instance(record),
        )
        provenance = record.get("metrics", {}).get("provenance_kind")
        priority = (
            2 if provenance == "FRESH_SOLVER_INVOCATION" else
            1 if record["record_origin"] == "PROTOCOL_V3" else
            0
        )
        previous = selected.get(key)
        if previous is None or priority > (
            2 if previous.get("metrics", {}).get("provenance_kind") == "FRESH_SOLVER_INVOCATION" else
            1 if previous["record_origin"] == "PROTOCOL_V3" else
            0
        ):
            selected[key] = record

    rows: list[dict[str, Any]] = []
    for benchmark_id in ("B03", "B06", "B07", "B09"):
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in selected.values():
            if record["benchmark_id"] == benchmark_id:
                groups[record["implementation_id"]].append(record)
        for implementation_id, group in groups.items():
            proven = sum(record["proof_status"] in {"PROVEN_OPTIMAL", "PROVEN_INFEASIBLE"} for record in group)
            valid = sum(record["solution_status"] in VALID_SOLUTIONS or record["proof_status"] == "PROVEN_INFEASIBLE" for record in group)
            rows.append(
                {
                    "benchmark_id": benchmark_id,
                    "implementation_id": implementation_id,
                    "instances": len(group),
                    "valid_or_proven_infeasible": valid,
                    "proven": proven,
                    "proof_rate": proven / len(group),
                    "mean_solver_s": mean(record["resources"].get("solver_s") for record in group),
                    "max_solver_s": max(
                        (
                            float(value)
                            for record in group
                            if (value := record["resources"].get("solver_s")) is not None
                            and math.isfinite(float(value))
                        ),
                        default=None,
                    ),
                    "mean_gap": mean(
                        record["metrics"].get("gap", record["metrics"].get("solver_relative_gap"))
                        for record in group
                    ),
                }
            )
    rows.sort(key=lambda row: (row["benchmark_id"], -row["proof_rate"], row["mean_solver_s"] or math.inf))
    return rows


def profit_knapsack_rankings(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    groups: dict[tuple[str, str, float], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if not executed(record) or record["benchmark_id"] != "B03" or record["comparison_track"] == "EXACT_MODEL":
            continue
        groups[(record["problem_variant"], record["implementation_id"], float(record["budget"]["time_limit_s"]))].append(record)
    ranking: list[dict[str, Any]] = []
    selected: dict[tuple[str, str, float], dict[str, dict[str, Any]]] = defaultdict(dict)
    for (variant, implementation_id, time_limit), group in groups.items():
        valid = [record for record in group if record["solution_status"] in VALID_SOLUTIONS]
        fractions = [record["metrics"].get("packed_profit_fraction") for record in valid]
        ranking.append({
            "problem_variant": variant,
            "implementation_id": implementation_id,
            "comparison_track": group[0]["comparison_track"],
            "time_limit_s": time_limit,
            "instances": len(group),
            "valid_instances": len(valid),
            "invalid_instances": len(group) - len(valid),
            "valid_rate": len(valid) / len(group) if group else 0.0,
            "mean_packed_profit": mean(record["metrics"].get("packed_profit") for record in valid),
            "mean_profit_fraction": mean(fractions),
            "median_profit_fraction": median(fractions),
            "p95_profit_fraction": nearest_rank([float(value) for value in fractions if value is not None], 0.95),
            "mean_solver_s": mean(record["resources"].get("solver_s") for record in valid),
            "p95_solver_s": nearest_rank([float(record["resources"]["solver_s"]) for record in valid if record["resources"].get("solver_s") is not None], 0.95),
            "candidate_invalid_count": sum(int(record["metrics"].get("candidate_invalid_count", 0)) for record in group),
        })
        for record in valid:
            selected[(variant, implementation_id, time_limit)][canonical_instance(record)] = record
    ranking.sort(key=lambda row: (row["problem_variant"], row["time_limit_s"], -row["valid_rate"], -(row["mean_profit_fraction"] or -1), row["implementation_id"]))
    pairwise: list[dict[str, Any]] = []
    for variant, implementation_id, time_limit in sorted(selected):
        ids = sorted(
            other_id for other_variant, other_id, other_time in selected
            if other_variant == variant and other_time == time_limit
        )
        if implementation_id != ids[0]:
            continue
        for left_index, left_id in enumerate(ids):
            for right_id in ids[left_index + 1:]:
                left = selected[(variant, left_id, time_limit)]
                right = selected[(variant, right_id, time_limit)]
                common = sorted(set(left) & set(right))
                wins = ties = losses = 0
                for instance in common:
                    left_value = left[instance]["metrics"].get("packed_profit")
                    right_value = right[instance]["metrics"].get("packed_profit")
                    if left_value is None or right_value is None:
                        continue
                    if left_value > right_value:
                        wins += 1
                    elif left_value < right_value:
                        losses += 1
                    else:
                        ties += 1
                pairwise.append({
                    "problem_variant": variant,
                    "time_limit_s": time_limit,
                    "left": left_id,
                    "right": right_id,
                    "common_valid_instances": len(common),
                    "left_wins": wins,
                    "ties": ties,
                    "left_losses": losses,
                })
    return ranking, pairwise


def constraint_rankings(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if executed(record) and record["benchmark_id"] in {"B09", "B12", "B13", "B14", "B15", "B16", "B17", "B18"}:
            groups[(record["benchmark_id"], record["implementation_id"])].append(record)
    rows: list[dict[str, Any]] = []
    for (benchmark_id, implementation_id), group in groups.items():
        statuses = Counter(record["solution_status"] for record in group)
        expected = [record["metrics"].get("expected_behavior_pass") for record in group if record["metrics"].get("expected_behavior_pass") is not None]
        rows.append(
            {
                "benchmark_id": benchmark_id,
                "implementation_id": implementation_id,
                "records": len(group),
                "valid_complete": statuses["VALID_COMPLETE"],
                "valid_partial": statuses["VALID_PARTIAL"],
                "no_solution": statuses["NO_SOLUTION"],
                "invalid_certificate": statuses["INVALID_CERTIFICATE"],
                "constraint_violation": statuses["CONSTRAINT_VIOLATION"],
                "process_errors": sum(record["run_status"] == "ERROR" for record in group),
                "expected_behavior_pass_rate": mean(1 if value else 0 for value in expected),
            }
        )
    rows.sort(key=lambda row: (row["benchmark_id"], row["invalid_certificate"], row["process_errors"], row["implementation_id"]))
    return rows


def industrial_baytp_rankings(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Summarize B30 shelf/bay semantics separately from free-space packing.

    B30 is a warehouse placement conformance case.  A geometrically complete
    layout is not a successful result when it violates a declared shelf top,
    side gap, or bay spacing rule, so the ranking is deliberately led by hard
    constraint status rather than bins/volume.
    """
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if executed(record) and record["benchmark_id"] == "B30":
            groups[(record["implementation_id"], record["comparison_track"], record["problem_scope"])].append(record)
    rows: list[dict[str, Any]] = []
    for (implementation_id, track, scope), group in groups.items():
        statuses = Counter(record["solution_status"] for record in group)
        hard_counts = [
            float(record["metrics"].get("hard_violation_count", 0))
            for record in group
            if record["metrics"].get("hard_violation_count") is not None
        ]
        rows.append(
            {
                "benchmark_id": "B30",
                "implementation_id": implementation_id,
                "comparison_track": track,
                "problem_scope": scope,
                "records": len(group),
                "valid_complete": statuses["VALID_COMPLETE"],
                "constraint_violation": statuses["CONSTRAINT_VIOLATION"],
                "invalid_certificate": statuses["INVALID_CERTIFICATE"],
                "process_errors": sum(record["run_status"] == "ERROR" for record in group),
                "complete_rate": statuses["VALID_COMPLETE"] / len(group) if group else 0.0,
                "mean_hard_violation_count": mean(hard_counts),
                "max_hard_violation_count": max(hard_counts) if hard_counts else None,
            }
        )
    rows.sort(key=lambda row: (row["constraint_violation"], row["invalid_certificate"], row["process_errors"], row["implementation_id"]))
    return rows


def industrial_mixed_pallet_rankings(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Summarize B31 mixed-SKU pallet cases and their stack constraints."""
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if executed(record) and record["benchmark_id"] == "B31":
            groups[(record["implementation_id"], record["comparison_track"], record["problem_scope"])].append(record)
    rows: list[dict[str, Any]] = []
    for (implementation_id, track, scope), group in groups.items():
        statuses = Counter(record["solution_status"] for record in group)
        packed = [record["metrics"].get("packed_items") for record in group if record["metrics"].get("packed_items") is not None]
        hard = [record["metrics"].get("hard_violation_count") for record in group if record["metrics"].get("hard_violation_count") is not None]
        rows.append(
            {
                "benchmark_id": "B31",
                "implementation_id": implementation_id,
                "comparison_track": track,
                "problem_scope": scope,
                "records": len(group),
                "valid_complete": statuses["VALID_COMPLETE"],
                "constraint_violation": statuses["CONSTRAINT_VIOLATION"],
                "invalid_certificate": statuses["INVALID_CERTIFICATE"],
                "no_solution": statuses["NO_SOLUTION"],
                "complete_rate": statuses["VALID_COMPLETE"] / len(group) if group else 0.0,
                "mean_packed_items": mean(packed),
                "mean_hard_violation_count": mean(hard),
            }
        )
    rows.sort(key=lambda row: (-row["complete_rate"], row["constraint_violation"], row["invalid_certificate"], row["implementation_id"]))
    return rows


def variable_cost_rankings(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank only records carrying a validated variable-cost objective.

    A geometric run without ``metrics.total_cost`` is intentionally omitted:
    bin count or a solver-reported objective cannot be substituted for the
    canonical cost metric.
    """
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if not executed(record) or record["benchmark_id"] not in {"B08", "B09"}:
            continue
        if record["metrics"].get("total_cost") is None:
            continue
        groups[(record["benchmark_id"], record["problem_variant"], record["implementation_id"], record["comparison_track"])].append(record)
    rows: list[dict[str, Any]] = []
    for (benchmark_id, variant, implementation_id, track), group in groups.items():
        valid = [record for record in group if record["solution_status"] == "VALID_COMPLETE"]
        costs = [float(record["metrics"]["total_cost"]) for record in valid]
        expected = [float(record["metrics"]["expected_cost"]) for record in valid if record["metrics"].get("expected_cost") is not None]
        rows.append({
            "benchmark_id": benchmark_id,
            "problem_variant": variant,
            "implementation_id": implementation_id,
            "comparison_track": track,
            "instances": len(group),
            "valid_complete": len(valid),
            "invalid_or_incomplete": len(group) - len(valid),
            "valid_rate": len(valid) / len(group) if group else 0.0,
            "mean_total_cost": mean(costs),
            "median_total_cost": median(costs),
            "expected_cost": mean(expected),
            "mean_cost_delta": mean([cost - target for cost, target in zip(costs, expected)]) if len(expected) == len(costs) else None,
            "mean_solver_s": mean(record["resources"].get("solver_s") for record in valid),
        })
    rows.sort(key=lambda row: (row["benchmark_id"], row["problem_variant"], row["mean_total_cost"] or math.inf, row["implementation_id"]))
    return rows


def open_dimension_rankings(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Summarize B11 open-X calibration runs without mixing other objectives."""
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if not executed(record) or record["benchmark_id"] != "B11":
            continue
        key = (
            record["benchmark_id"], record["problem_variant"], record["problem_scope"],
            record["comparison_track"], record["implementation_id"],
            record["budget"].get("time_limit_s"), record["adapter"],
        )
        groups[key].append(record)
    rows: list[dict[str, Any]] = []
    for key, group in groups.items():
        valid = [record for record in group if record["solution_status"] in VALID_SOLUTIONS]
        lengths = [record["metrics"].get("used_length") for record in valid]
        rows.append({
            "benchmark_id": key[0], "problem_variant": key[1], "problem_scope": key[2],
            "comparison_track": key[3], "implementation_id": key[4],
            "time_limit_s": key[5], "adapter": key[6], "rank_scope": "PER_SUPPORTED_INSTANCE_SET",
            "planned_records": len(group), "valid_records": len(valid),
            "invalid_records": len(group) - len(valid), "valid_rate": len(valid) / len(group),
            "mean_used_length": mean(lengths), "median_used_length": median(lengths),
            "p95_used_length": nearest_rank([float(value) for value in lengths if value is not None], 0.95),
            "mean_wall_s": mean(record["resources"].get("wall_s") for record in valid),
            "mean_open_dimension_bound": mean(record["metrics"].get("open_dimension_bound") for record in valid),
        })
    rows.sort(key=lambda row: (row["benchmark_id"], -row["valid_rate"], row["mean_used_length"] if row["mean_used_length"] is not None else float("inf"), row["implementation_id"]))
    return rows


def resource_rankings(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = canonical_b04(records)
    timing_group = {
        "packingsolver_fork_box": "PACKINGSOLVER_PROCESS",
        "py3dbp": "PYTHON_WORKER",
        "jerry": "PYTHON_WORKER",
        "skjolber_plain": "SKJOLBER_JVM",
        "skjolber_laff": "SKJOLBER_JVM",
        "skjolber_fast_bruteforce": "SKJOLBER_JVM",
        "go_bp3d": "GO_PROCESS_LIBRARY_ONLY",
        "rust_extreme_point": "RUST_PROCESS_LIBRARY_ONLY",
    }
    rows: list[dict[str, Any]] = []
    for implementation_id, by_instance in selected.items():
        valid = [record for record in by_instance.values() if record["solution_status"] == "VALID_COMPLETE"]
        wall = [float(record["resources"]["wall_s"]) for record in valid if record["resources"].get("wall_s") is not None]
        solver = [float(record["resources"]["solver_s"]) for record in valid if record["resources"].get("solver_s") is not None]
        rss = [float(record["resources"]["peak_rss_bytes"]) for record in valid if record["resources"].get("peak_rss_bytes") is not None]
        rows.append(
            {
                "implementation_id": implementation_id,
                "timing_comparison_group": timing_group[implementation_id],
                "valid_instances": len(valid),
                "wall_samples": len(wall),
                "median_wall_s": median(wall),
                "p95_wall_s": nearest_rank(wall, 0.95),
                "solver_samples": len(solver),
                "median_solver_s": median(solver),
                "p95_solver_s": nearest_rank(solver, 0.95),
                "peak_rss_bytes": max(rss) if rss else None,
            }
        )
    rows.sort(key=lambda row: (row["timing_comparison_group"], row["median_wall_s"] or math.inf, row["median_solver_s"] or math.inf))
    return rows


def reliability_rankings(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Summarize B24-B29 without combining unlike reliability questions."""
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if executed(record) and record["benchmark_id"] in {"B24", "B25", "B26", "B27", "B28", "B29"}:
            grouped[(record["benchmark_id"], record["implementation_id"])].append(record)

    invariance: list[dict[str, Any]] = []
    for (benchmark_id, implementation_id), group in sorted(grouped.items()):
        if benchmark_id != "B24":
            continue
        by_variant = {record["problem_variant"]: record for record in group}
        base = by_variant.get("base")
        checks = []
        for variant in ("permuted", "renamed", "axis_swap"):
            candidate = by_variant.get(variant)
            checks.append(bool(base and candidate and base["solution_status"] == "VALID_COMPLETE"
                               and candidate["solution_status"] == "VALID_COMPLETE"
                               and base["metrics"].get("bins_used") == candidate["metrics"].get("bins_used")))
        invariance.append({"benchmark_id": "B24", "implementation_id": implementation_id,
                           "transform_cases": len(checks), "invariant_cases": sum(checks),
                           "invariance_rate": sum(checks) / len(checks) if checks else 0.0,
                           "base_status": base["solution_status"] if base else "MISSING"})

    numeric: list[dict[str, Any]] = []
    for (benchmark_id, implementation_id), group in sorted(grouped.items()):
        if benchmark_id not in {"B25", "B26"}:
            continue
        by_variant = {record["problem_variant"]: record for record in group}
        if benchmark_id == "B25":
            expected = {"cost_base": 10.0, "cost_permuted": 10.0, "cost_scaled": 70.0}
            variants = tuple(expected)
            label = "expected_cost_rate"
        else:
            expected = {"base": None, "scale10": None}
            variants = tuple(expected)
            label = "numeric_consistency_rate"
        checks = []
        for variant in variants:
            record = by_variant.get(variant)
            if not record or record["solution_status"] != "VALID_COMPLETE":
                checks.append(False)
                continue
            if benchmark_id == "B25":
                checks.append(abs(float(record["metrics"].get("total_cost", math.inf)) - expected[variant]) <= 1e-7)
            else:
                checks.append(record["metrics"].get("bins_used") == 1)
        numeric.append({"benchmark_id": benchmark_id, "implementation_id": implementation_id,
                        "cases": len(checks), "passing_cases": sum(checks), label: sum(checks) / len(checks) if checks else 0.0,
                        "invalid_or_missing": len(checks) - sum(checks)})

    repeatability: list[dict[str, Any]] = []
    for (benchmark_id, implementation_id), group in sorted(grouped.items()):
        if benchmark_id != "B27":
            continue
        valid = [record for record in group if record["solution_status"] == "VALID_COMPLETE"]
        bins = [float(record["metrics"].get("bins_used")) for record in valid if record["metrics"].get("bins_used") is not None]
        wall = [float(record["resources"].get("wall_s")) for record in valid if record["resources"].get("wall_s") is not None]
        repeatability.append({"benchmark_id": benchmark_id, "implementation_id": implementation_id,
                              "repetitions": len(group), "valid_repetitions": len(valid),
                              "valid_rate": len(valid) / len(group) if group else 0.0,
                              "mean_bins": mean(bins), "bins_stddev": statistics.pstdev(bins) if len(bins) > 1 else 0.0 if bins else None,
                              "p95_wall_s": nearest_rank(wall, 0.95), "wall_stddev_s": statistics.pstdev(wall) if len(wall) > 1 else 0.0 if wall else None})

    scalability: list[dict[str, Any]] = []
    for (benchmark_id, implementation_id), group in sorted(grouped.items()):
        if benchmark_id != "B28":
            continue
        for record in sorted(group, key=lambda row: row["problem_variant"]):
            count = int(record["problem_variant"].removeprefix("n")) if record["problem_variant"].startswith("n") else None
            scalability.append({"benchmark_id": benchmark_id, "implementation_id": implementation_id, "items": count,
                                "run_status": record["run_status"], "solution_status": record["solution_status"],
                                "bins_used": record["metrics"].get("bins_used"), "wall_s": record["resources"].get("wall_s"),
                                "peak_rss_bytes": record["resources"].get("peak_rss_bytes")})

    fault: list[dict[str, Any]] = []
    for (benchmark_id, implementation_id), group in sorted(grouped.items()):
        if benchmark_id != "B29":
            continue
        by_variant = {record["problem_variant"]: record for record in group}
        invalid = by_variant.get("invalid_json")
        cancelled = by_variant.get("cancelled")
        # A CLI that exits zero while returning no valid certificate still
        # handled malformed input; retain that distinction from a crash.
        invalid_ok = bool(invalid and (invalid["run_status"] == "ERROR" or invalid["solution_status"] == "INVALID_CERTIFICATE"))
        cancel_ok = bool(cancelled and cancelled["run_status"] == "CANCELLED")
        latency = cancelled["metrics"].get("cancel_latency_s") if cancelled else None
        fault.append({"benchmark_id": benchmark_id, "implementation_id": implementation_id,
                      "fault_cases": 2, "handled_cases": int(invalid_ok) + int(cancel_ok),
                      "fault_recovery_rate": (int(invalid_ok) + int(cancel_ok)) / 2,
                      "invalid_input_status": invalid["run_status"] if invalid else "MISSING",
                      "cancel_status": cancelled["run_status"] if cancelled else "MISSING",
                      "cancel_latency_s": latency})
    return {"metamorphic": invariance, "numeric": numeric, "repeatability": repeatability,
            "scalability": scalability, "fault": fault}


def generated_files() -> dict[Path, str]:
    manifest_path = RESULTS_DIR / "run-manifest.jsonl"
    plan_path = RESULTS_DIR / "suite-implementation-plan.jsonl"
    records = read_jsonl(manifest_path)
    plan = read_jsonl(plan_path)
    validate_records(records)
    coverage = execution_coverage(plan, records)
    volume = volume_rankings(records)
    volume_common = volume_common_rankings(records)
    b07_versions = b07_version_pairwise_rankings(records)
    b07_projection = b07_projection_common_rankings(records)
    b07_jerry_fixpoint = b07_jerry_fixpoint_pairwise(records)
    identical, pairwise = identical_bin_rankings(records)
    profit, profit_pairwise = profit_knapsack_rankings(records)
    exact = exact_rankings(records)
    constraints = constraint_rankings(records)
    industrial_baytp = industrial_baytp_rankings(records)
    industrial_mixed_pallet = industrial_mixed_pallet_rankings(records)
    variable_cost = variable_cost_rankings(records)
    open_dimension = open_dimension_rankings(records)
    resources = resource_rankings(records)
    reliability = reliability_rankings(records)

    solution_counts = Counter(record["solution_status"] for record in records)
    run_counts = Counter(record["run_status"] for record in records)
    benchmark_counts = Counter(record["benchmark_id"] for record in records)
    executed_benchmark_counts = Counter(record["benchmark_id"] for record in records if executed(record))
    evidence_cells = sum(row["run_records"] > 0 for row in coverage)
    protocol_v3_cells = sum(row["protocol_v3_executed_records"] > 0 for row in coverage)
    legacy_only_cells = sum(row["legacy_run_records"] > 0 and row["protocol_v3_run_records"] == 0 for row in coverage)
    protocol_v3_status_only_cells = sum(
        row["protocol_v3_run_records"] > 0 and row["protocol_v3_executed_records"] == 0
        for row in coverage
    )
    origin_counts = Counter(record["record_origin"] for record in records)
    aggregate = {
        "schema_version": 1,
        "protocol_version": "benchmark-protocol/3",
        "source_sha256": {
            "results/comprehensive/run-manifest.jsonl": sha256(manifest_path),
            "results/comprehensive/suite-implementation-plan.jsonl": sha256(plan_path),
            "benchmarks/comprehensive/run_reliability.py": sha256(ROOT / "benchmarks/comprehensive/run_reliability.py"),
            "benchmarks/data/comprehensive/reliability-fixture.json": sha256(ROOT / "benchmarks/data/comprehensive/reliability-fixture.json"),
            "results/comprehensive/reliability-source-audit.json": sha256(ROOT / "results/comprehensive/reliability-source-audit.json"),
            "benchmarks/data/comprehensive/b31-mixed-sku-fixture.json": sha256(ROOT / "benchmarks/data/comprehensive/b31-mixed-sku-fixture.json"),
            "results/comprehensive/b31-source-audit.json": sha256(ROOT / "results/comprehensive/b31-source-audit.json"),
            "benchmarks/comprehensive/run_constraint_adapters.py": sha256(ROOT / "benchmarks/comprehensive/run_constraint_adapters.py"),
            "benchmarks/comprehensive/run_b11_external_composed.py": sha256(ROOT / "benchmarks/comprehensive/run_b11_external_composed.py"),
            "benchmarks/data/comprehensive/b11-open-dimension/source.json": sha256(ROOT / "benchmarks/data/comprehensive/b11-open-dimension/source.json"),
            "raw/experiments/comprehensive/B11-external-composed/artifacts.tar.gz": sha256(ROOT / "raw/experiments/comprehensive/B11-external-composed/artifacts.tar.gz"),
        },
        "coverage": {
            "planned_cells": len(coverage),
            "cells_with_evidence": evidence_cells,
            "evidence_cell_rate": evidence_cells / len(coverage),
            "legacy_baseline_only_cells": legacy_only_cells,
            "protocol_v3_status_only_cells": protocol_v3_status_only_cells,
            "protocol_v3_executed_cells": protocol_v3_cells,
            "protocol_v3_executed_cell_rate": protocol_v3_cells / len(coverage),
            "run_records": len(records),
            "record_origin_counts": dict(sorted(origin_counts.items())),
            "executed_implementations": len({record["implementation_id"] for record in records}),
            # Status-only records make every suite visible in the manifest, so
            # distinguish actual execution coverage from status coverage.
            "benchmarks_with_runs": len(executed_benchmark_counts),
            "benchmarks_with_status_records": len(benchmark_counts),
            "run_status_counts": dict(sorted(run_counts.items())),
            "solution_status_counts": dict(sorted(solution_counts.items())),
            "records_by_benchmark": dict(sorted(benchmark_counts.items())),
        },
        "headline": {
            "identical_bin_packing": identical,
            "volume_knapsack_common": volume_common,
            "profit_knapsack": profit,
            "exact_proof": exact,
            "variable_cost": variable_cost,
        "open_dimension": open_dimension,
            "industrial_baytp": industrial_baytp,
            "industrial_mixed_pallet": industrial_mixed_pallet,
            "reliability": reliability,
        },
        "warnings": [
            "Imported v1/v2 baselines do not satisfy the new raw/experiments/comprehensive directory layout.",
            "Cross-language timing groups are not combined into a single speed ranking.",
            "Per-supported-instance-set volume rows are not directly comparable when instance_set_sha256 differs.",
        ],
    }
    coverage_fields = [
        "benchmark_id", "benchmark_name", "category", "problem_family", "implementation_id", "library", "algorithm",
        "planned_input_status", "planned_capability_status", "comparison_track", "problem_scope", "run_records",
        "legacy_run_records", "protocol_v3_run_records", "protocol_v3_executed_records", "protocol_v3_not_run_records",
        "unique_instances", "completed", "time_limit", "error",
        "valid_complete", "valid_partial", "invalid_certificate",
        "constraint_violation", "no_solution", "execution_status",
    ]
    volume_fields = [
        "benchmark_id", "problem_variant", "problem_scope", "comparison_track", "implementation_id", "time_limit_s",
        "item_order", "adapter", "rank_scope", "planned_records",
        "valid_records", "invalid_records", "valid_rate", "instance_set_sha256", "mean_volume_utilization",
        "median_volume_utilization", "p95_volume_utilization", "mean_wall_s",
    ]
    volume_common_fields = [
        "benchmark_id", "implementation_id", "common_implementations", "common_instances", "common_instance_set_sha256",
        "valid_records", "invalid_records", "mean_volume_utilization", "median_volume_utilization",
    ]
    b07_version_fields = [
        "source_group", "time_limit_s", "left", "right", "common_instances", "valid_comparable_instances",
        "fork_wins", "ties", "upstream_wins", "mean_fork_utilization", "mean_upstream_utilization",
        "mean_delta_upstream_minus_fork", "median_delta_upstream_minus_fork",
    ]
    b07_projection_fields = [
        "problem_variant", "time_limit_s", "item_order", "implementation_id", "adapter",
        "participating_implementations", "source_instances", "common_valid_instances", "common_instance_set_sha256",
        "valid_on_source_instances", "invalid_certificates", "no_solution", "mean_volume_utilization",
        "median_volume_utilization", "p95_volume_utilization",
    ]
    b07_jerry_fixpoint_fields = [
        "item_order", "common_records", "common_valid_records", "fix_true_invalid_certificates",
        "fix_false_invalid_certificates", "fix_true_no_solution", "fix_false_no_solution", "fix_false_wins", "ties",
        "fix_false_losses", "mean_delta_fix_false_minus_true", "median_delta_fix_false_minus_true",
    ]
    identical_fields = [
        "implementation_id", "common_instances", "common_instance_set_sha256", "valid_complete", "invalid", "incomplete",
        "invalid_rate", "incomplete_rate", "mean_bins", "median_bins", "p95_bins", "mean_wall_s", "mean_solver_s",
    ]
    pairwise_fields = [
        "left", "right", "source_common_instances", "valid_comparable_instances", "left_wins", "ties", "left_losses",
    ]
    exact_fields = [
        "benchmark_id", "implementation_id", "instances", "valid_or_proven_infeasible", "proven", "proof_rate",
        "mean_solver_s", "max_solver_s", "mean_gap",
    ]
    profit_fields = [
        "problem_variant", "implementation_id", "comparison_track", "time_limit_s", "instances", "valid_instances",
        "invalid_instances", "valid_rate", "mean_packed_profit", "mean_profit_fraction", "median_profit_fraction",
        "p95_profit_fraction", "mean_solver_s", "p95_solver_s", "candidate_invalid_count",
    ]
    profit_pairwise_fields = [
        "problem_variant", "time_limit_s", "left", "right", "common_valid_instances", "left_wins", "ties", "left_losses",
    ]
    constraint_fields = [
        "benchmark_id", "implementation_id", "records", "valid_complete", "valid_partial", "no_solution",
        "invalid_certificate", "constraint_violation", "process_errors", "expected_behavior_pass_rate",
    ]
    industrial_baytp_fields = [
        "benchmark_id", "implementation_id", "comparison_track", "problem_scope", "records", "valid_complete",
        "constraint_violation", "invalid_certificate", "process_errors", "complete_rate",
        "mean_hard_violation_count", "max_hard_violation_count",
    ]
    industrial_mixed_pallet_fields = [
        "benchmark_id", "implementation_id", "comparison_track", "problem_scope", "records", "valid_complete",
        "constraint_violation", "invalid_certificate", "no_solution", "complete_rate", "mean_packed_items",
        "mean_hard_violation_count",
    ]
    variable_cost_fields = [
        "benchmark_id", "problem_variant", "implementation_id", "comparison_track", "instances", "valid_complete",
        "invalid_or_incomplete", "valid_rate", "mean_total_cost", "median_total_cost", "expected_cost",
        "mean_cost_delta", "mean_solver_s",
    ]
    open_dimension_fields = [
        "benchmark_id", "problem_variant", "problem_scope", "comparison_track", "implementation_id",
        "time_limit_s", "adapter", "rank_scope", "planned_records", "valid_records", "invalid_records",
        "valid_rate", "mean_used_length", "median_used_length", "p95_used_length", "mean_wall_s",
        "mean_open_dimension_bound",
    ]
    resource_fields = [
        "implementation_id", "timing_comparison_group", "valid_instances", "wall_samples", "median_wall_s", "p95_wall_s",
        "solver_samples", "median_solver_s", "p95_solver_s", "peak_rss_bytes",
    ]
    reliability_fields = {
        "metamorphic": ["benchmark_id", "implementation_id", "transform_cases", "invariant_cases", "invariance_rate", "base_status"],
        "numeric": ["benchmark_id", "implementation_id", "cases", "passing_cases", "expected_cost_rate", "numeric_consistency_rate", "invalid_or_missing"],
        "repeatability": ["benchmark_id", "implementation_id", "repetitions", "valid_repetitions", "valid_rate", "mean_bins", "bins_stddev", "p95_wall_s", "wall_stddev_s"],
        "scalability": ["benchmark_id", "implementation_id", "items", "run_status", "solution_status", "bins_used", "wall_s", "peak_rss_bytes"],
        "fault": ["benchmark_id", "implementation_id", "fault_cases", "handled_cases", "fault_recovery_rate", "invalid_input_status", "cancel_status", "cancel_latency_s"],
    }
    output = {
        RESULTS_DIR / "aggregate.json": canonical_json(aggregate),
        RESULTS_DIR / "coverage.csv": write_csv(coverage, coverage_fields),
        RESULTS_DIR / "rankings" / "volume-knapsack.csv": write_csv(volume, volume_fields),
        RESULTS_DIR / "rankings" / "volume-knapsack-common.csv": write_csv(volume_common, volume_common_fields),
        RESULTS_DIR / "rankings" / "B07-version-pairwise.csv": write_csv(b07_versions, b07_version_fields),
        RESULTS_DIR / "rankings" / "B07-projection-common.csv": write_csv(b07_projection, b07_projection_fields),
        RESULTS_DIR / "rankings" / "B07-jerry-fixpoint-pairwise.csv": write_csv(b07_jerry_fixpoint, b07_jerry_fixpoint_fields),
        RESULTS_DIR / "rankings" / "identical-bin-packing.csv": write_csv(identical, identical_fields),
        RESULTS_DIR / "rankings" / "identical-bin-packing-pairwise.csv": write_csv(pairwise, pairwise_fields),
        RESULTS_DIR / "rankings" / "profit-knapsack.csv": write_csv(profit, profit_fields),
        RESULTS_DIR / "rankings" / "profit-knapsack-pairwise.csv": write_csv(profit_pairwise, profit_pairwise_fields),
        RESULTS_DIR / "rankings" / "exact-proof.csv": write_csv(exact, exact_fields),
        RESULTS_DIR / "rankings" / "constraint-conformance.csv": write_csv(constraints, constraint_fields),
        RESULTS_DIR / "rankings" / "industrial-baytp.csv": write_csv(industrial_baytp, industrial_baytp_fields),
        RESULTS_DIR / "rankings" / "industrial-mixed-pallet.csv": write_csv(industrial_mixed_pallet, industrial_mixed_pallet_fields),
        RESULTS_DIR / "rankings" / "variable-cost.csv": write_csv(variable_cost, variable_cost_fields),
        RESULTS_DIR / "rankings" / "open-dimension.csv": write_csv(open_dimension, open_dimension_fields),
        RESULTS_DIR / "rankings" / "resource-summary.csv": write_csv(resources, resource_fields),
    }
    for kind, rows in reliability.items():
        output[RESULTS_DIR / "rankings" / f"reliability-{kind}.csv"] = write_csv(rows, reliability_fields[kind])
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze protocol v3 run records")
    parser.add_argument("--check", action="store_true", help="fail if generated outputs are missing or stale")
    args = parser.parse_args()
    files = generated_files()
    if args.check:
        stale = [path for path, content in files.items() if not path.exists() or path.read_text() != content]
        if stale:
            for path in stale:
                print(f"COMPREHENSIVE_STALE: {path}", file=sys.stderr)
            return 1
        print(f"COMPREHENSIVE_OK: {len(files)} generated artifacts are current")
        return 0
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
