"""Convert one ESICUP THPACK9 instance to the study's normalized JSON format."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".cache" / "esicup-datasets" / "3d_rectangular" / "thpack" / "thpack9.txt"
TARGET = ROOT / "benchmarks" / "data" / "public" / "thpack9_instance1.json"
EXPECTED_COMMIT = "154a8f006a8e72f65d734f2d1e36777f678f31f8"
EXPECTED_SOURCE_SHA256 = "a4f5e3a748709217cdc749f7d27940f15b9f2a31b3e840e725642237036f82cc"


def source_provenance() -> tuple[str, str]:
    checkout = SOURCE.parents[2]
    try:
        commit = subprocess.check_output(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(".cache/esicup-datasets must be a git checkout at the pinned commit") from exc
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if commit != EXPECTED_COMMIT:
        raise SystemExit(f"ESICUP checkout mismatch: expected {EXPECTED_COMMIT}, got {commit}")
    if digest != EXPECTED_SOURCE_SHA256:
        raise SystemExit(f"THPACK9 source hash mismatch: expected {EXPECTED_SOURCE_SHA256}, got {digest}")
    return commit, digest


def parse_first_instance(values: list[int], source_commit: str, source_sha256: str) -> dict:
    pos = 1  # first value is the number of instances
    instance_id = values[pos]
    pos += 1
    container = values[pos : pos + 3]
    pos += 3
    type_count = values[pos]
    pos += 1
    item_types = []
    for _ in range(type_count):
        item_type, length, rotate_x, width, rotate_y, height, rotate_z, copies = values[pos : pos + 8]
        pos += 8
        item_types.append(
            {
                "id": str(item_type),
                "size": [length, width, height],
                "copies": copies,
                "allowed_axis_rotations": [rotate_x, rotate_y, rotate_z],
            }
        )
    return {
        "dataset": "ESICUP THPACK9",
        "source_file": "3d_rectangular/thpack/thpack9.txt",
        "source_url": f"https://github.com/ESICUP/datasets/blob/{source_commit}/3d_rectangular/thpack/thpack9.txt",
        "source_commit": source_commit,
        "source_sha256": source_sha256,
        "reference": "Ivancic, Mathur & Mohanty (1989), followed by Bischoff & Ratcliff (1995)",
        "problem_kind": "3d_bin_packing",
        "objective": "minimize_bins",
        "instance": instance_id,
        "container_types": [{"id": "bin", "size": container, "copies": "unlimited", "cost": 1}],
        "item_types": item_types,
        "notes": "THPACK9 is a multiple-container benchmark; all orientations marked 1 are allowed.",
    }


def main() -> None:
    source_commit, source_sha256 = source_provenance()
    values = list(map(int, SOURCE.read_text().split()))
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(parse_first_instance(values, source_commit, source_sha256), indent=2) + "\n")
    print(TARGET)


if __name__ == "__main__":
    main()
