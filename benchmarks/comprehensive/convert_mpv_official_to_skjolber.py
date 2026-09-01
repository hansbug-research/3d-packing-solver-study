#!/usr/bin/env python3
"""Convert the MPV derived JSON corpus to the Skjolber CSV contract."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from generate_mpv_official import DEFAULT_OUTPUT


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / ".cache" / "skjolber-mpv-derived"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    manifest = json.loads((DEFAULT_OUTPUT / "manifest.json").read_text(encoding="utf-8"))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for entry in manifest["instances"]:
        source = DEFAULT_OUTPUT / entry["path"]
        case = json.loads(source.read_text(encoding="utf-8"))
        prefix = case["instance_id"]
        items_path = OUTPUT / f"{prefix}_items.csv"
        bins_path = OUTPUT / f"{prefix}_bins.csv"
        with items_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["ID", "X", "Y", "Z", "COPIES", "ROTATION_XYZ", "ROTATION_YXZ", "ROTATION_ZYX", "ROTATION_YZX", "ROTATION_XZY", "ROTATION_ZXY"])
            for item in case["items"]:
                x, y, z = item["size"]
                writer.writerow([item["id"], x, y, z, 1, 1, 0, 0, 0, 0, 0])
        with bins_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["ID", "X", "Y", "Z"])
            writer.writerow(["bin", *case["container"]])
        rows.append({"instance_id": prefix, "source": entry["path"], "source_sha256": entry["sha256"], "items_sha256": sha256(items_path), "bins_sha256": sha256(bins_path)})
    (OUTPUT / "manifest.json").write_text(json.dumps({"corpus": "MPV_OFFICIAL_GENERATOR_DERIVED", "instances": rows}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
