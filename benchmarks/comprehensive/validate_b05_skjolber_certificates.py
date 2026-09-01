#!/usr/bin/env python3
"""Independently validate Skjolber MPV certificate CSVs against the corpus."""

from __future__ import annotations

import csv
import itertools
import json
from collections import defaultdict
from pathlib import Path

from generate_mpv_official import DEFAULT_OUTPUT

ROOT = Path(__file__).resolve().parents[2]


def load_cases() -> dict[str, dict]:
    manifest = json.loads((DEFAULT_OUTPUT / "manifest.json").read_text(encoding="utf-8"))
    return {json.loads((DEFAULT_OUTPUT / row["path"]).read_text(encoding="utf-8"))["instance_id"]: json.loads((DEFAULT_OUTPUT / row["path"]).read_text(encoding="utf-8")) for row in manifest["instances"]}


def validate(cert: Path, run: Path, cases: dict[str, dict]) -> dict:
    expected = {(row["instance_id"], row["algorithm"]): row for row in json.loads("[" + ",".join(line for line in run.read_text(encoding="utf-8").splitlines() if line.strip()) + "]")}
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    with cert.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            grouped[(row["INSTANCE"], row["ALGORITHM"])].append(row)
    failures = []
    checked = 0
    for key, record in expected.items():
        instance_id, algorithm = key
        if instance_id not in cases:
            failures.append(f"unknown instance {instance_id}")
            continue
        case = cases[instance_id]
        item_sizes = {item["id"]: tuple(item["size"]) for item in case["items"]}
        placements = grouped.get(key, [])
        seen: set[str] = set()
        by_bin: dict[str, list[tuple[float, ...]]] = defaultdict(list)
        errors = []
        for row in placements:
            item_id = row["ITEM_ID"]
            if item_id not in item_sizes or item_id in seen:
                errors.append(f"duplicate_or_unknown:{item_id}")
                continue
            seen.add(item_id)
            size = tuple(float(row[field]) for field in ("DX", "DY", "DZ"))
            position = tuple(float(row[field]) for field in ("X", "Y", "Z"))
            if size != tuple(float(value) for value in item_sizes[item_id]):
                errors.append(f"forbidden_orientation:{item_id}")
            if any(value < 0 for value in position) or any(position[i] + size[i] > case["container"][i] for i in range(3)):
                errors.append(f"out_of_bounds:{item_id}")
            by_bin[row["BIN_INDEX"]].append((*position, *size))
        for bin_id, boxes in by_bin.items():
            for left, right in itertools.combinations(boxes, 2):
                if not any(left[axis] + left[axis + 3] <= right[axis] or right[axis] + right[axis + 3] <= left[axis] for axis in range(3)):
                    errors.append(f"overlap:{bin_id}")
        complete = len(seen) == len(item_sizes)
        if record.get("solution_status") == "VALID_COMPLETE" and (errors or not complete):
            failures.append(f"{instance_id}/{algorithm}: " + ";".join(errors or ["incomplete"]))
        checked += 1
    result = {"certificate": str(cert), "run": str(run), "checked_records": checked, "certificate_groups": len(grouped), "failures": failures, "status": "PASS" if not failures else "FAIL"}
    return result


def main() -> None:
    cases = load_cases()
    outputs = []
    for run in sorted((ROOT / "results/comprehensive/runs").glob("B05-MPV-GEN-skjolber-*.jsonl")):
        if "fastbrute" not in run.name and ("plain" not in run.name and "laff" not in run.name):
            continue
        cert = run.with_suffix(".certificate.csv")
        if cert.exists(): outputs.append(validate(cert, run, cases))
    target = ROOT / "results/comprehensive/b05-skjolber-certificate-validation.json"
    target.write_text(json.dumps({"schema_version": 1, "status": "PASS" if all(row["status"] == "PASS" for row in outputs) else "FAIL", "results": outputs}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS" if all(row["status"] == "PASS" for row in outputs) else "FAIL", "runs": len(outputs), "checked_records": sum(row["checked_records"] for row in outputs)}, indent=2))


if __name__ == "__main__":
    main()
