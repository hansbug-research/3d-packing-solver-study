from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from benchmarks.validation import Box, validate_aabbs  # noqa: E402


RAW_DIR = ROOT / "raw" / "experiments" / "campaign" / "python_thpack"
OUTPUT = RAW_DIR / "independent-invalid-validation.json"


def main() -> None:
    records = [
        json.loads(line)
        for line in (RAW_DIR / "records.jsonl").read_text().splitlines()
        if line.strip()
    ]
    invalid = [record for record in records if record["status"] == "INVALID"]
    results: list[dict] = []
    for record in invalid:
        placements = [
            Box(
                ref=placement["item_id"],
                bin_ref=placement["bin_id"],
                x=float(placement["x"]),
                y=float(placement["y"]),
                z=float(placement["z"]),
                dx=float(placement["dx"]),
                dy=float(placement["dy"]),
                dz=float(placement["dz"]),
            )
            for placement in record["placements"]
        ]
        container = tuple(float(value) for value in record["instance"]["container"])
        bin_sizes = {placement.bin_ref: container for placement in placements}
        errors = validate_aabbs(placements, bin_sizes)
        results.append(
            {
                "instance_key": record["instance_key"],
                "library": record["library"],
                "order": record["order"],
                "primary_validator": record["validator"],
                "primary_error_count": len(record["validation_errors"]),
                "independent_validator": "benchmarks.validation.validate_aabbs",
                "independent_error_count": len(errors),
                "independent_errors": errors,
            }
        )

    output = {
        "schema_version": 1,
        "status": "PASS" if len(results) == 4 and all(result["independent_error_count"] > 0 for result in results) else "FAIL",
        "invalid_records_checked": len(results),
        "results": results,
    }
    OUTPUT.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))
    if output["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
