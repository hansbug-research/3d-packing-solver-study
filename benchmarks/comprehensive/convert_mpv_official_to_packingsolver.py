#!/usr/bin/env python3
"""Convert the derived MPV JSON corpus to a temporary PackingSolver layout."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from generate_mpv_official import DEFAULT_OUTPUT


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    target = args.output / "ivancic1989"
    target.mkdir(parents=True, exist_ok=True)
    index: list[dict[str, object]] = []
    item_fields = [
        "ID", "X", "Y", "Z", "ROTATION_XYZ", "ROTATION_YXZ", "ROTATION_ZYX",
        "ROTATION_YZX", "ROTATION_XZY", "ROTATION_ZXY", "WEIGHT", "COPIES",
    ]
    bin_fields = ["ID", "X", "Y", "Z", "COST", "COPIES", "MAXIMUM_WEIGHT"]
    for source in sorted(args.corpus.glob("MPV-GEN-*.json")):
        payload = json.loads(source.read_text(encoding="utf-8"))
        # The shared THPACK runner parses the final underscore field as an
        # integer instance number; keep that field numeric for compatibility.
        parts = source.stem.removeprefix("MPV-GEN-").lower().split("-")
        token = f"{parts[0]}_{parts[1]}_{parts[2].removeprefix('r')}"
        items_name = f"mpvgen_{token}_items.csv"
        bins_name = f"mpvgen_{token}_bins.csv"
        write_csv(
            target / items_name,
            item_fields,
            [
                {
                    # PackingSolver's CSV reader normalizes IDs to integers;
                    # use numeric IDs in this transport representation.
                    "ID": index, "X": item["size"][0], "Y": item["size"][1], "Z": item["size"][2],
                    "ROTATION_XYZ": 1, "ROTATION_YXZ": 0, "ROTATION_ZYX": 0,
                    "ROTATION_YZX": 0, "ROTATION_XZY": 0, "ROTATION_ZXY": 0,
                    "WEIGHT": 1, "COPIES": 1,
                }
                for index, item in enumerate(payload["items"])
            ],
        )
        x, y, z = payload["container"]
        write_csv(
            target / bins_name,
            bin_fields,
            [{"ID": 0, "X": x, "Y": y, "Z": z, "COST": 1, "COPIES": len(payload["items"]), "MAXIMUM_WEIGHT": 100000000}],
        )
        index.append({"instance_id": payload["instance_id"], "items": items_name, "bins": bins_name})
    (args.output / "manifest.json").write_text(json.dumps({"corpus": "MPV_OFFICIAL_GENERATOR_DERIVED", "instances": index}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"converted={len(index)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
