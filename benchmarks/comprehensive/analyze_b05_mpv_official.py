#!/usr/bin/env python3
"""Summarize all completed MPV official-generator-derived runs.

Only complete, independently validated certificates enter the quality tables.
The official C reference is reported separately because its upper bound is an
incumbent unless its lower/upper bounds close.
"""

from __future__ import annotations

import csv
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "results/comprehensive/runs"
OUT = ROOT / "results/comprehensive/rankings"
PATTERN = re.compile(r"MPV-GEN-T(?P<type>\d+)-N(?P<n>\d+)-R(?P<rep>\d+)")


def rows(path: Path):
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def classify(row: dict) -> tuple[str, str, str]:
    match = PATTERN.fullmatch(row["instance_id"])
    if not match:
        match = re.search(r"mpvgen_t(?P<type>\d+)_n(?P<n>\d+):(?P<rep>\d+)$", row["instance_id"])
    if not match:
        raise ValueError(row["instance_id"])
    return match.group("type"), match.group("n"), match.group("rep")


def normalized(path: Path) -> list[dict]:
    result = []
    for row in rows(path):
        typ, n, rep = classify(row)
        metrics = row.get("metrics", {})
        status = row.get("solution_status", row.get("status", "UNKNOWN"))
        valid = status == "VALID_COMPLETE"
        if "bins_used" in metrics:
            bins = metrics["bins_used"]
        else:
            bins = row.get("bins_used", row.get("upper_bound_bins"))
        implementation = row.get("implementation_id", row.get("implementation", path.stem))
        budget = row.get("budget", {}).get("time_limit_s", None)
        if budget is None:
            match_budget = re.search(r"-(\d+)s(?:-(?:v\d+|final))?\.jsonl$", path.name)
            budget = float(match_budget.group(1)) if match_budget else None
        result.append({
            "file": path.name,
            "implementation": implementation,
            "algorithm": row.get("algorithm", implementation),
            "instance_id": row["instance_id"],
            "type": int(typ),
            "n": int(n),
            "replicate": int(rep),
            "budget_s": budget,
            "status": status,
            "valid_complete": valid,
            "bins_used": bins,
            "lower_bound": row.get("lower_bound_bins"),
            "upper_bound": row.get("upper_bound_bins"),
            "run_status": row.get("run_status"),
            "wall_s": row.get("resources", {}).get("wall_s", row.get("wall_time_s")),
        })
    return result


def write_csv(path: Path, data: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(data)


def main() -> None:
    files = sorted(RUNS.glob("B05-MPV-GEN-*.jsonl"))
    excluded = {
        "B05-MPV-GEN-probe-go-any-1s.jsonl", "B05-MPV-GEN-probe-py-any-1s.jsonl", "B05-MPV-GEN-probe-rust-fixed-1s.jsonl",
        "B05-MPV-GEN-fork-box-1s.jsonl", "B05-MPV-GEN-fork-box-1s-v2.jsonl",
        "B05-MPV-GEN-skjolber-fastbrute-fixed-1s.jsonl", "B05-MPV-GEN-skjolber-fastbrute-fixed-10s.jsonl",
        "B05-MPV-GEN-skjolber-fastbrute-fixed-1s-v2.jsonl",
        "B05-MPV-GEN-skjolber-fastbrute-fixed-1s-v3.jsonl", "B05-MPV-GEN-skjolber-fastbrute-fixed-10s-v2.jsonl",
    }
    data = [row for path in files if path.name not in excluded for row in normalized(path)]
    fields = ["file", "implementation", "algorithm", "instance_id", "type", "n", "replicate", "budget_s", "status", "valid_complete", "bins_used", "lower_bound", "upper_bound", "run_status", "wall_s"]
    write_csv(OUT / "B05-MPV-OFFICIAL-GEN-all-runs.csv", data, fields)

    quality = [row for row in data if row["valid_complete"] and row["bins_used"] is not None]
    grouped: dict[tuple[str, str, str, str], list[dict]] = defaultdict(list)
    for row in quality:
        track = "REFERENCE" if "official" in row["file"] else ("PROJECTION" if any(token in row["file"] for token in ("go-bp3d-any", "py3dbp-any", "jerry-any")) else "FIXED")
        grouped[(track, row["implementation"], str(row["budget_s"]), row["algorithm"])].append(row)
    rank = []
    for (track, implementation, budget, algorithm), group in sorted(grouped.items()):
        values = [int(row["bins_used"]) for row in group]
        rank.append({
            "track": track,
            "implementation": implementation,
            "algorithm": algorithm,
            "budget_s": budget,
            "valid_complete": len(group),
            "total_records": sum(1 for row in data if row["implementation"] == implementation and str(row["budget_s"]) == budget),
            "mean_bins": f"{statistics.mean(values):.6f}",
            "median_bins": f"{statistics.median(values):.6f}",
            "p95_bins": f"{sorted(values)[max(0, int(len(values) * 0.95) - 1)]:.6f}",
        })
    write_csv(OUT / "B05-MPV-OFFICIAL-GEN-rankings.csv", rank, list(rank[0]) if rank else ["track"])

    stratified = []
    grouped_type: dict[tuple[str, str, str, str, int, int], list[dict]] = defaultdict(list)
    for row in quality:
        track = "REFERENCE" if "official" in row["file"] else ("PROJECTION" if any(token in row["file"] for token in ("go-bp3d-any", "py3dbp-any", "jerry-any")) else "FIXED")
        grouped_type[(track, row["implementation"], str(row["budget_s"]), row["algorithm"], row["type"], row["n"])].append(row)
    for (track, implementation, budget, algorithm, typ, n), group in sorted(grouped_type.items()):
        values = [int(row["bins_used"]) for row in group]
        stratified.append({"track": track, "implementation": implementation, "algorithm": algorithm, "budget_s": budget, "generator_type": typ, "items_n": n, "valid_complete": len(group), "mean_bins": f"{statistics.mean(values):.6f}"})
    write_csv(OUT / "B05-MPV-OFFICIAL-GEN-rankings-by-type.csv", stratified, list(stratified[0]) if stratified else ["track"])

    summary = {
        "corpus": "MPV_OFFICIAL_GENERATOR_DERIVED",
        "records": len(data),
        "quality_records": len(quality),
        "files": sorted({row["file"] for row in data}),
        "groupings": [{"track": key[0], "implementation": key[1], "budget_s": key[2], "algorithm": key[3], "records": len(value), "valid_complete": sum(row["valid_complete"] for row in value)} for key, value in sorted(grouped.items())],
        "quality_rule": "Only VALID_COMPLETE independent certificates; official C lower/upper bound is separate and not a certificate quality rank.",
    }
    (ROOT / "results/comprehensive/b05-mpv-official-gen-summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"records": len(data), "quality_records": len(quality), "groups": len(rank)}, indent=2))


if __name__ == "__main__":
    main()
