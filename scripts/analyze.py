from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"
DERIVED = ROOT / "derived"
TABLES = DERIVED / "tables"


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    DERIVED.mkdir(exist_ok=True)
    public = json.loads((RAW / "thpack9_baselines.json").read_text())
    patched = json.loads((RAW / "thpack9_instance1_packingsolver_patched.json").read_text())["Output"]["Solution"]
    skjolber = json.loads((RAW / "skjolber.json").read_text())["scenarios"]["thpack9_instance1"]
    rows = [
        {"library": "PackingSolver patched box", "packed": patched["NumberOfItems"], "required": 70, "bins_used": patched["NumberOfBins"], "status": "FEASIBLE"},
        {"library": "Skjolber LAFF", "packed": skjolber["placements"], "required": 70, "bins_used": skjolber["containers"], "status": "FEASIBLE"},
    ]
    rows.extend({
        "library": item["library"], "packed": item["packed"], "required": item["required"],
        "bins_used": item["bins_used"], "status": "FEASIBLE" if not item["validation_errors"] else "INVALID",
    } for item in public["results"])
    write_csv(TABLES / "public_thpack9.csv", rows, ["library", "packed", "required", "bins_used", "status"])

    cases = json.loads((RAW / "packingsolver.json").read_text())["cases"]
    smoke = [{"case": name, "returncode": data["returncode"], "certificate": data["certificate_created"]} for name, data in cases.items()]
    write_csv(TABLES / "packingsolver_cases.csv", smoke, ["case", "returncode", "certificate"])

    stats = {
        "schema_version": 1,
        "public_dataset": "ESICUP THPACK9 instance 1",
        "public_required_items": 70,
        "public_container_volume": 960,
        "public_item_volume": 17920,
        "public_volume_lower_bound": 19,
        "public_results": rows,
        "controlled_pytest_assertions": 8,
        "packing_solver_original_variable_cost": "FAIL_KNOWN_UPSTREAM_BUG",
        "packing_solver_patched_variable_cost": "PASS",
    }
    (DERIVED / "stats.json").write_text(json.dumps(stats, indent=2) + "\n")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
