from __future__ import annotations

import csv
import json
import math
import statistics
from collections import Counter
from pathlib import Path

from model import parse_all


ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = ROOT / "raw" / "experiments" / "campaign" / "python_thpack"
OUT_DIR = ROOT / "results" / "campaign" / "python_thpack"
SOURCE_DIR = ROOT / ".cache" / "esicup-datasets" / "3d_rectangular" / "thpack"


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * quantile
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - index) + ordered[upper] * (index - lower)


def quality(record: dict) -> float:
    if record["problem_kind"] == "single_container_knapsack":
        return float(record["packed_volume"])
    return -float(record["bins_used"])


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("")
        return
    fieldnames: list[str] = []
    for row in rows:
        for field in row:
            if field not in fieldnames:
                fieldnames.append(field)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    metadata = json.loads((RAW_DIR / "run-metadata.json").read_text())
    records = [json.loads(line) for line in (RAW_DIR / "records.jsonl").read_text().splitlines() if line.strip()]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    expected = metadata["inventory"]["total_instances"] * 4
    if not metadata["full_campaign"] or len(records) != expected:
        raise SystemExit(f"refusing to analyze partial campaign: expected {expected} records, got {len(records)}")

    status_counts = Counter(record["status"] for record in records)
    excluded_statuses = {"MALFORMED_SOURCE_EXCLUDED", "UNSUPPORTED_ORIENTATION_SEMANTICS"}
    executed = [record for record in records if record["status"] not in excluded_statuses]
    valid = [record for record in executed if record["status"] in {"FEASIBLE_COMPLETE", "FEASIBLE_PARTIAL"}]

    library_rows: list[dict] = []
    for library in ("py3dbp", "jerry"):
        members = [record for record in records if record["library"] == library]
        source_valid = [record for record in members if record["status"] != "MALFORMED_SOURCE_EXCLUDED"]
        supported = [record for record in members if record["status"] not in excluded_statuses]
        runs = supported
        good = [record for record in runs if record["status"] in {"FEASIBLE_COMPLETE", "FEASIBLE_PARTIAL"}]
        wall = [float(record["elapsed_seconds"]) for record in runs]
        solve = [float(record["solve_seconds"]) for record in runs if "solve_seconds" in record]
        library_rows.append(
            {
                "library": library,
                "total_records": len(members),
                "total_instances": len({record["instance_key"] for record in members}),
                "source_valid_records": len(source_valid),
                "source_valid_instances": len({record["instance_key"] for record in source_valid}),
                "semantic_supported_records": len(supported),
                "semantic_supported_instances": len({record["instance_key"] for record in supported}),
                "executed": len(runs),
                "valid": len(good),
                "invalid": sum(record["status"] == "INVALID" for record in members),
                "incomplete": sum(record["status"] == "INCOMPLETE" for record in members),
                "timeouts": sum(record["status"] == "TIMEOUT" for record in members),
                "errors": sum(record["status"] == "ERROR" for record in members),
                "unsupported": sum(record["status"] == "UNSUPPORTED_ORIENTATION_SEMANTICS" for record in members),
                "malformed_source_excluded": sum(record["status"] == "MALFORMED_SOURCE_EXCLUDED" for record in members),
                "wall_median_s": statistics.median(wall) if wall else None,
                "wall_p95_s": percentile(wall, 0.95),
                "solve_median_s": statistics.median(solve) if solve else None,
                "peak_rss_max_kib": max((record.get("peak_rss_kib", 0) for record in runs), default=None),
            }
        )

    family_rows: list[dict] = []
    inventory_by_family = {row["family"]: row for row in metadata["inventory"]["families"]}
    parsed_instances = parse_all(SOURCE_DIR)
    for family, inventory in inventory_by_family.items():
        source_valid_instances = [instance for instance in parsed_instances if instance.family == family and not instance.source_line_errors]
        item_counts = [instance.item_count for instance in source_valid_instances]
        type_counts = [len(instance.item_types) for instance in source_valid_instances]
        demand_ratios = [instance.item_volume / instance.container_volume for instance in source_valid_instances]
        row = {
            "family": family,
            "instances": inventory["instances"],
            "source_valid_instances": len(source_valid_instances),
            "problem_kind": inventory["problem_kind"],
            "declared_item_type_rows": inventory["declared_item_type_rows"],
            "parsed_item_types": inventory["parsed_item_types"],
            "parsed_item_instances": inventory["parsed_item_instances"],
            "item_count_min": min(item_counts),
            "item_count_median": statistics.median(item_counts),
            "item_count_max": max(item_counts),
            "type_count_median": statistics.median(type_counts),
            "demand_to_container_volume_median": statistics.median(demand_ratios),
            "malformed_instances": inventory["malformed_instances"],
            "flags_001_items": inventory["vertical_flag_item_counts"].get("001", 0),
            "flags_011_items": inventory["vertical_flag_item_counts"].get("011", 0),
            "flags_111_items": inventory["vertical_flag_item_counts"].get("111", 0),
        }
        for library in ("py3dbp", "jerry"):
            supported_descending = [
                record
                for record in records
                if record["family"] == family
                and record["library"] == library
                and record["order"] == "descending"
                and record["status"] not in excluded_statuses
            ]
            descending = [
                record
                for record in valid
                if record["family"] == family and record["library"] == library and record["order"] == "descending"
            ]
            row[f"{library}_expressible_instances"] = len(supported_descending)
            row[f"{library}_valid_instances"] = len(descending)
            if inventory["problem_kind"] == "single_container_knapsack":
                utilizations = [float(record["volume_utilization"]) for record in descending]
                row[f"{library}_median_utilization"] = statistics.median(utilizations) if utilizations else None
                row[f"{library}_median_capacity_gap"] = statistics.median([1.0 - value for value in utilizations]) if utilizations else None
            else:
                bins = [int(record["bins_used"]) for record in descending if record["status"] == "FEASIBLE_COMPLETE"]
                lower_bounds = [
                    math.ceil(record["instance"]["item_volume"] / record["instance"]["container_volume"])
                    for record in descending
                    if record["status"] == "FEASIBLE_COMPLETE"
                ]
                row[f"{library}_median_bins"] = statistics.median(bins) if bins else None
                row[f"{library}_median_volume_lower_bound"] = statistics.median(lower_bounds) if lower_bounds else None
                row[f"{library}_median_relative_gap_to_volume_bound"] = (
                    statistics.median((bins_used - bound) / bound for bins_used, bound in zip(bins, lower_bounds)) if bins else None
                )
        family_rows.append(row)

    by_all_variant = {(record["instance_key"], record["library"], record["order"]): record for record in records}
    by_variant = {(record["instance_key"], record["library"], record["order"]): record for record in valid}
    sensitivity_rows: list[dict] = []
    for library in ("py3dbp", "jerry"):
        keys = sorted(
            {
                record["instance_key"]
                for record in records
                if record["library"] == library and record["status"] not in excluded_statuses
            }
        )
        compared = changed = descending_better = ascending_better = ties = 0
        validity_changed = both_invalid = 0
        relative_changes: list[float] = []
        for key in keys:
            if (key, library, "descending") not in by_all_variant or (key, library, "ascending") not in by_all_variant:
                raise RuntimeError(f"missing order pair for {key}/{library}")
            descending = by_variant.get((key, library, "descending"))
            ascending = by_variant.get((key, library, "ascending"))
            if not descending or not ascending:
                if bool(descending) != bool(ascending):
                    validity_changed += 1
                else:
                    both_invalid += 1
                continue
            compared += 1
            q_descending, q_ascending = quality(descending), quality(ascending)
            if q_descending > q_ascending:
                descending_better += 1
            elif q_ascending > q_descending:
                ascending_better += 1
            else:
                ties += 1
            if q_descending != q_ascending:
                changed += 1
                denominator = max(abs(q_descending), abs(q_ascending), 1.0)
                relative_changes.append(abs(q_descending - q_ascending) / denominator)
        sensitivity_rows.append(
            {
                "library": library,
                "semantic_supported_paired_instances": len(keys),
                "valid_both_orders": compared,
                "validity_changed_by_order": validity_changed,
                "invalid_both_orders": both_invalid,
                "quality_changed": changed,
                "descending_better": descending_better,
                "ascending_better": ascending_better,
                "ties": ties,
                "median_absolute_relative_change": statistics.median(relative_changes) if relative_changes else 0.0,
                "max_absolute_relative_change": max(relative_changes, default=0.0),
            }
        )

    paired_rows: list[dict] = []
    for order in ("descending", "ascending"):
        keys = sorted(
            set(record["instance_key"] for record in valid if record["library"] == "py3dbp" and record["order"] == order)
            & set(record["instance_key"] for record in valid if record["library"] == "jerry" and record["order"] == order)
        )
        for key in keys:
            py = by_variant[(key, "py3dbp", order)]
            jerry = by_variant[(key, "jerry", order)]
            if py["problem_kind"] == "single_container_knapsack":
                metric = "packed_volume"
                py_value, jerry_value = py["packed_volume"], jerry["packed_volume"]
                winner = "py3dbp" if py_value > jerry_value else "jerry" if jerry_value > py_value else "tie"
            else:
                metric = "bins_used"
                py_value, jerry_value = py["bins_used"], jerry["bins_used"]
                winner = "py3dbp" if py_value < jerry_value else "jerry" if jerry_value < py_value else "tie"
            paired_rows.append(
                {
                    "instance_key": key,
                    "family": py["family"],
                    "order": order,
                    "metric": metric,
                    "py3dbp": py_value,
                    "jerry": jerry_value,
                    "winner": winner,
                }
            )

    winner_groups: dict[str, dict[str, int]] = {}
    for family in sorted({row["family"] for row in paired_rows}):
        for order in ("descending", "ascending"):
            group = [row for row in paired_rows if row["family"] == family and row["order"] == order]
            winner_groups[f"{family}/{order}"] = dict(Counter(row["winner"] for row in group))

    invalid_rows = [
        {
            "instance_key": record["instance_key"],
            "family": record["family"],
            "library": record["library"],
            "order": record["order"],
            "status": record["status"],
            "packed_items": record.get("packed_items"),
            "bins_used": record.get("bins_used"),
            "validation_error_count": len(record.get("validation_errors", [])),
            "first_validation_error": (record.get("validation_errors") or [""])[0],
        }
        for record in records
        if record["status"] in {"INVALID", "INCOMPLETE", "ERROR", "TIMEOUT"}
    ]

    diagnostic_path = RAW_DIR / "jerry-fixpoint-diagnostics.jsonl"
    diagnostic_records = [json.loads(line) for line in diagnostic_path.read_text().splitlines() if line.strip()] if diagnostic_path.exists() else []
    diagnostic_rows = [
        {
            "instance_key": record["instance"]["key"],
            "order": record["order"],
            "fix_point": record["parameters"]["fix_point"],
            "status": record["status"],
            "packed_items": record["packed_items"],
            "packed_volume": record["packed_volume"],
            "bins_used": record["bins_used"],
            "validation_error_count": len(record["validation_errors"]),
        }
        for record in diagnostic_records
    ]
    independent_path = RAW_DIR / "independent-invalid-validation.json"
    independent_validation = json.loads(independent_path.read_text()) if independent_path.exists() else None

    summary = {
        "schema_version": 1,
        "source_commit": metadata["source_commit"],
        "coverage": {
            "total_instances": metadata["inventory"]["total_instances"],
            "source_valid_instances": len({record["instance_key"] for record in records if record["status"] != "MALFORMED_SOURCE_EXCLUDED"}),
            "semantic_supported_library_instance_pairs": len(
                {(record["instance_key"], record["library"]) for record in records if record["status"] not in excluded_statuses}
            ),
            "total_scheduled_records": len(records),
            "source_valid_records": sum(record["status"] != "MALFORMED_SOURCE_EXCLUDED" for record in records),
            "semantic_supported_records": sum(record["status"] not in excluded_statuses for record in records),
            "executed_records": len(executed),
            "valid_records": len(valid),
        },
        "total_records": len(records),
        "source_valid_records": sum(record["status"] != "MALFORMED_SOURCE_EXCLUDED" for record in records),
        "semantic_supported_records": sum(record["status"] not in excluded_statuses for record in records),
        "status_counts": dict(sorted(status_counts.items())),
        "executed_records": len(executed),
        "valid_records": len(valid),
        "validation_error_records": sum(record["status"] == "INVALID" for record in records),
        "library_summary": library_rows,
        "order_sensitivity": sensitivity_rows,
        "paired_winners": dict(Counter(row["winner"] for row in paired_rows)),
        "paired_winners_by_family_order": winner_groups,
        "invalid_records": invalid_rows,
        "independent_invalid_validation": independent_validation,
        "jerry_fixpoint_false_diagnostics": diagnostic_rows,
        "notes": [
            "THPACK1-8 are scored as single-container knapsack by packed volume; omitted items are legal.",
            "THPACK9 is scored only when the entire consignment is placed; lower bin count is better.",
            "Unsupported orientation semantics and malformed source records are explicit statuses, not omitted runs.",
        ],
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    write_csv(OUT_DIR / "library-summary.csv", library_rows)
    write_csv(OUT_DIR / "family-summary.csv", family_rows)
    write_csv(OUT_DIR / "order-sensitivity.csv", sensitivity_rows)
    write_csv(OUT_DIR / "paired-differences.csv", paired_rows)
    write_csv(OUT_DIR / "invalid-records.csv", invalid_rows)
    write_csv(OUT_DIR / "jerry-fixpoint-diagnostics.csv", diagnostic_rows)


if __name__ == "__main__":
    main()
