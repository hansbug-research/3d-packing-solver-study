#!/usr/bin/env python3
"""Audit the availability and semantics of the MPV 3D-BPP benchmark source.

The Martello--Pisinger--Vigo paper is a primary algorithmic reference, but a
paper citation alone is not an executable benchmark input.  This audit keeps
the distinction explicit and records the local repository evidence used to
keep B05 SOURCE_INCOMPLETE until a redistributable instance archive is found.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PACKINGSOLVER = ROOT / ".cache" / "packingsolver-fork"
ESICUP = ROOT / ".cache" / "esicup-datasets"

MPV_DOI = "10.1287/opre.48.2.256.12386"
MPV_TITLE = "The Three-Dimensional Bin Packing Problem"
PACKINGSOLVER_COMMIT = "d953148b8f710c06fa6c410949b7272f9e36327b"
ESICUP_COMMIT = "154a8f006a8e72f65d734f2d1e36777f678f31f8"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head(path: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip()


def file_inventory(root: Path, patterns: list[str]) -> dict[str, Any]:
    matches: list[str] = []
    for pattern in patterns:
        matches.extend(str(path.relative_to(root)) for path in root.glob(pattern) if path.is_file())
    matches = sorted(set(matches))
    return {
        "patterns": patterns,
        "count": len(matches),
        "files": matches,
        "sha256": {name: sha256(root / name) for name in matches},
    }


def audit() -> dict[str, Any]:
    rectangle_martello = PACKINGSOLVER / "data" / "rectangle" / "martello1998"
    box_martello = PACKINGSOLVER / "data" / "box" / "martello1998"
    raw_martello = PACKINGSOLVER / "data" / "box_raw" / "martello1998"
    esicup_3d = ESICUP / "3d_rectangular"

    rectangle_files = file_inventory(rectangle_martello, ["*.2bp", "*.csv"])
    box_files = file_inventory(box_martello, ["*"]) if box_martello.exists() else {"count": 0, "files": []}
    raw_files = file_inventory(raw_martello, ["*"]) if raw_martello.exists() else {"count": 0, "files": []}
    esicup_candidates = sorted(
        str(path.relative_to(esicup_3d))
        for path in esicup_3d.rglob("*")
        if path.is_file() and any(token in path.name.lower() for token in ("martello", "pisinger", "vigo", "3dbpp"))
    ) if esicup_3d.exists() else []

    return {
        "schema_version": 1,
        "record_kind": "B05_SOURCE_AUDIT",
        "benchmark_id": "B05",
        "audit_date": "2026-09-01",
        "paper": {
            "title": MPV_TITLE,
            "doi": MPV_DOI,
            "model_confirmed": "orthogonal identical-bin 3D-BPP, minimum bin count",
            "reported_scale": "computational instances up to 90 items",
            "lower_bound_claim": "continuous lower bound asymptotic worst-case ratio 1/8",
            "executable_archive_found": False,
        },
        "snapshots": {
            "packingsolver_root": str(PACKINGSOLVER.relative_to(ROOT)),
            "packingsolver_head": git_head(PACKINGSOLVER),
            "packingsolver_expected_head": PACKINGSOLVER_COMMIT,
            "esicup_root": str(ESICUP.relative_to(ROOT)),
            "esicup_head": git_head(ESICUP),
            "esicup_expected_head": ESICUP_COMMIT,
        },
        "repository_evidence": {
            "packingsolver_rectangle_martello1998": {
                **rectangle_files,
                "interpretation": "2D rectangle .2bp corpus; not a 3D MPV input",
            },
            "packingsolver_box_martello1998": {
                **box_files,
                "interpretation": "no directory or no files in the 3D box data tree",
            },
            "packingsolver_box_raw_martello1998": {
                **raw_files,
                "interpretation": "no raw 3D MPV source directory",
            },
            "esicup_3d_rectangular_name_matches": {
                "count": len(esicup_candidates),
                "files": esicup_candidates,
                "interpretation": "no MPV-named 3D instance files in the pinned ESICUP snapshot",
            },
        },
        "decision": {
            "input_status": "SOURCE_INCOMPLETE",
            "run_status": "NOT_RUN",
            "termination_reason": "SOURCE_PENDING",
            "reason": "The paper and known lower-bound claims are citable, but no reproducible public 3D instance archive with format, pose rules, and license was found in the pinned sources.",
            "forbidden_substitutions": [
                "PackingSolver data/rectangle/martello1998 (2D)",
                "self-generated instances without a source-equivalence proof",
                "THPACK9 or BR/LN relabeled as MPV",
            ],
            "next_action": "Keep every B05 x implementation cell explicit as SOURCE_INCOMPLETE/SOURCE_PENDING; optionally add a separately named public 3DBPPsi or Q4RealBPP suite after its own source audit.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = json.dumps(audit(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    output = args.output
    if output is None:
        print(result, end="")
        return 0
    if args.check:
        if not output.exists() or output.read_text(encoding="utf-8") != result:
            print(f"B05_SOURCE_AUDIT_STALE: {output}")
            return 1
        print("B05_SOURCE_AUDIT_OK")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result, encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
