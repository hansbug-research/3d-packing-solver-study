#!/usr/bin/env python3
"""Run the official MPV C solver on the derived corpus as a reference track."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tarfile
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from time import perf_counter
from typing import Any

from generate_mpv_official import (
    DEFAULT_OUTPUT,
    SOURCE_SHA256,
    SOURCE_URLS,
    compile_generator,
    fetch_sources,
)


ROOT = Path(__file__).resolve().parents[2]
RUNNER = Path(__file__).resolve()
SUMMARY_RE = re.compile(r"^\s*1\s*:\s*lb\s+(\d+)\s+z\s+(\d+)\s+node\s+(\d+)\s+iter\s+(\d+)\s+time\s+([0-9.]+)")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def compile_solver(source_dir: Path, build_dir: Path) -> Path:
    binary = build_dir / "mpv_3dbpp"
    subprocess.run(
        ["gcc", "-ansi", "-O2", str(source_dir / "3dbpp.c"), str(source_dir / "test3dbpp.c"), "-lm", "-o", str(binary)],
        check=True,
        capture_output=True,
        text=True,
    )
    return binary


def run_one(
    path: Path,
    binary: Path,
    time_limit: int,
    work_root: Path,
    archive_prefix: str,
    binary_sha: str,
    runner_sha: str,
) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    container = payload["container"]
    items = payload["items"]
    input_path = work_root / f"{path.stem}.txt"
    stdout_path = work_root / f"{path.stem}.stdout"
    input_path.write_text(
        "{} {} {} {}\n{}\n".format(
            len(items), *container,
            "\n".join("{} {} {}".format(*item["size"]) for item in items),
        ),
        encoding="ascii",
    )
    started = perf_counter()
    env = os.environ.copy()
    env.update({"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"})
    completed = subprocess.run(
        [str(binary), str(input_path), "0", "0", str(time_limit), "0"],
        capture_output=True,
        text=True,
        env=env,
        timeout=time_limit + 5,
    )
    wall_s = perf_counter() - started
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    match = next((SUMMARY_RE.match(line) for line in completed.stdout.splitlines() if SUMMARY_RE.match(line)), None)
    if match is None:
        status = "ERROR"
        lower_bound = upper_bound = None
        termination = "NO_SUMMARY"
    else:
        lower_bound, upper_bound = int(match.group(1)), int(match.group(2))
        status = "TIME_LIMIT" if float(match.group(5)) >= time_limit * 0.95 else "COMPLETED"
        termination = "BOUND_CLOSED" if lower_bound == upper_bound else "TIME_LIMIT_WITH_BOUND"
    input_sha = sha256(path)
    return {
        "schema_version": 1,
        "record_kind": "SUPPLEMENTAL_REFERENCE_RUN",
        "protocol_version": "benchmark-protocol/3-supplemental",
        "benchmark_id": "B05-MPV-OFFICIAL-GEN",
        "problem_variant": "OFFICIAL_GENERATOR_DERIVED_FIXED_XYZ",
        "instance_id": payload["instance_id"],
        "implementation": "mpv_official_3dbpp_c",
        "algorithm": "Martello-Pisinger-Vigo branch-and-bound / one-bin exact routine",
        "technology": "ANSI C",
        "source_urls": SOURCE_URLS,
        "source_sha256": SOURCE_SHA256,
        "binary_sha256": binary_sha,
        "runner_sha256": runner_sha,
        "input_sha256": input_sha,
        "generator": payload["generator"],
        "budget": {"time_limit_s": time_limit, "thread_limit": 1},
        "run_status": status,
        "termination_reason": termination,
        "lower_bound_bins": lower_bound,
        "upper_bound_bins": upper_bound,
        "gap_bins": upper_bound - lower_bound if lower_bound is not None else None,
        "relative_gap": ((upper_bound - lower_bound) / lower_bound) if lower_bound else None,
        "solver_time_s": float(match.group(5)) if match else None,
        "wall_time_s": wall_s,
        "nodes_thousands": int(match.group(3)) if match else None,
        "iterations_thousands": int(match.group(4)) if match else None,
        "artifacts": {"stdout": f"{archive_prefix}#{stdout_path.name}"},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--time-limit", type=int, choices=(1, 10), default=1)
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--output", type=Path, default=ROOT / "results/comprehensive/runs/B05-MPV-GEN-official-1s.jsonl")
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "raw/experiments/comprehensive/B05-MPV-GEN-official")
    args = parser.parse_args()
    if args.jobs < 1:
        raise SystemExit("--jobs must be positive")
    source_hashes = fetch_sources(args.source_dir, offline=True)
    if source_hashes != SOURCE_SHA256:
        raise SystemExit("official source hash mismatch")
    paths = sorted(path for path in args.corpus.glob("MPV-GEN-*.json") if path.name != "manifest.json")
    if len(paths) != 150:
        raise SystemExit(f"expected 150 corpus files, found {len(paths)}")
    args.raw_dir.mkdir(parents=True, exist_ok=True)
    archive_path = args.raw_dir / f"artifacts-{args.time_limit}s.tar.gz"
    archive_name = str(archive_path.relative_to(ROOT))
    with tempfile.TemporaryDirectory(prefix="mpv-reference-") as build_name:
        build_dir = Path(build_name)
        binary = compile_solver(args.source_dir, build_dir)
        binary_sha, runner_sha = sha256(binary), sha256(RUNNER)
        with tempfile.TemporaryDirectory(prefix="mpv-reference-cases-") as case_name:
            work_root = Path(case_name)
            records: list[dict[str, Any]] = []
            with ThreadPoolExecutor(max_workers=args.jobs) as executor:
                futures = {executor.submit(run_one, path, binary, args.time_limit, work_root, archive_name, binary_sha, runner_sha): path for path in paths}
                for count, future in enumerate(as_completed(futures), 1):
                    records.append(future.result())
                    if count % 25 == 0 or count == len(futures):
                        print(f"MPV official reference {count}/{len(futures)}", flush=True)
            with tarfile.open(archive_path, "w:gz") as archive:
                for path in sorted(work_root.glob("*.stdout")):
                    archive.add(path, arcname=path.name)
    records.sort(key=lambda row: row["instance_id"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in records), encoding="utf-8")
    metadata = {
        "schema_version": 1,
        "record_kind": "SUPPLEMENTAL_REFERENCE_RUN_SUMMARY",
        "benchmark_id": "B05-MPV-OFFICIAL-GEN",
        "time_limit_s": args.time_limit,
        "records": len(records),
        "source_sha256": source_hashes,
        "runner_sha256": sha256(RUNNER),
        "output_sha256": sha256(args.output),
        "artifact_archive": archive_name,
        "artifact_archive_sha256": sha256(archive_path),
        "status_counts": {status: sum(row["run_status"] == status for row in records) for status in ("COMPLETED", "TIME_LIMIT", "ERROR")},
        "bound_closed": sum(row["lower_bound_bins"] is not None and row["lower_bound_bins"] == row["upper_bound_bins"] for row in records),
    }
    (args.raw_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    print(json.dumps(metadata, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
