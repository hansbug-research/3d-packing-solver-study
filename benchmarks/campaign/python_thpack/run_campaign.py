from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from model import ESICUP_COMMIT, JERRY_COMMIT, orientation_support, parse_all, sha256


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
SOURCE_DIR = ROOT / ".cache" / "esicup-datasets" / "3d_rectangular" / "thpack"
RAW_DIR = ROOT / "raw" / "experiments" / "campaign" / "python_thpack"
RECORDS = RAW_DIR / "records.jsonl"
METADATA = RAW_DIR / "run-metadata.json"
STDERR = RAW_DIR / "stderr.log"
TIMEOUT_SECONDS = 60
MEMORY_LIMIT_BYTES = 2 * 1024 * 1024 * 1024


def git_head(path: Path) -> str:
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()


def source_inventory(instances) -> dict:
    families = []
    for family_number in range(1, 10):
        family = f"THPACK{family_number}"
        members = [instance for instance in instances if instance.family == family]
        patterns: dict[str, int] = {}
        for instance in members:
            for item in instance.item_types:
                key = "".join(str(value) for value in item.allowed_vertical_dimensions)
                patterns[key] = patterns.get(key, 0) + item.copies
        families.append(
            {
                "family": family,
                "instances": len(members),
                "problem_kind": members[0].problem_kind,
                "objective": members[0].objective,
                "declared_item_type_rows": sum(len(instance.item_types) + len(instance.source_line_errors) for instance in members),
                "parsed_item_types": sum(len(instance.item_types) for instance in members),
                "parsed_item_instances": sum(instance.item_count for instance in members),
                "malformed_instances": sum(bool(instance.source_line_errors) for instance in members),
                "vertical_flag_item_counts": patterns,
                "source_file": f"thpack{family_number}.txt",
                "source_sha256": sha256(SOURCE_DIR / f"thpack{family_number}.txt"),
            }
        )
    return {"families": families, "total_instances": len(instances)}


def base_record(instance, library: str, order: str) -> dict:
    return {
        "schema_version": 1,
        "instance_key": instance.key,
        "family": instance.family,
        "instance_id": instance.instance_id,
        "problem_kind": instance.problem_kind,
        "objective": instance.objective,
        "library": library,
        "order": order,
        "source_commit": ESICUP_COMMIT,
    }


def run_one(instance, library: str, order: str, stderr_handle) -> dict:
    supported, reason = orientation_support(instance, library)
    record = base_record(instance, library, order)
    if instance.source_line_errors:
        record.update(
            status="MALFORMED_SOURCE_EXCLUDED",
            reason=reason,
            source_line_errors=instance.source_line_errors,
            elapsed_seconds=0.0,
        )
        return record
    if not supported:
        record.update(status="UNSUPPORTED_ORIENTATION_SEMANTICS", reason=reason, elapsed_seconds=0.0)
        return record

    command = [
        sys.executable,
        str(HERE / "worker.py"),
        "--library",
        library,
        "--instance",
        instance.key,
        "--order",
        order,
    ]
    environment = os.environ.copy()
    environment.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", NUMEXPR_NUM_THREADS="1", PYTHONHASHSEED="0")
    started = perf_counter()
    try:
        completed = subprocess.run(command, text=True, capture_output=True, timeout=TIMEOUT_SECONDS, env=environment)
    except subprocess.TimeoutExpired as exc:
        elapsed = perf_counter() - started
        stderr_handle.write(f"[{instance.key} {library} {order}] TIMEOUT\n{exc.stderr or ''}\n")
        record.update(status="TIMEOUT", reason=f"exceeded {TIMEOUT_SECONDS}s wall limit", elapsed_seconds=elapsed)
        return record
    elapsed = perf_counter() - started
    if completed.stderr:
        stderr_handle.write(f"[{instance.key} {library} {order}]\n{completed.stderr}\n")
    if completed.returncode != 0:
        record.update(
            status="ERROR",
            reason=f"worker returned {completed.returncode}",
            stderr_tail=completed.stderr[-2000:],
            stdout_tail=completed.stdout[-2000:],
            elapsed_seconds=elapsed,
        )
        return record
    try:
        worker_result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        record.update(status="ERROR", reason=f"worker emitted invalid JSON: {exc}", stdout_tail=completed.stdout[-2000:], elapsed_seconds=elapsed)
        return record
    worker_result.update(record)
    worker_result["elapsed_seconds"] = elapsed
    return worker_result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="development-only cap on parsed instances")
    args = parser.parse_args()
    if git_head(ROOT / ".cache" / "esicup-datasets") != ESICUP_COMMIT:
        raise SystemExit("ESICUP checkout is not at the pinned commit")
    if git_head(ROOT / ".cache" / "jerry-3d-bin-packing") != JERRY_COMMIT:
        raise SystemExit("Jerry checkout is not at the pinned commit")

    instances = parse_all(SOURCE_DIR)
    selected = instances[: args.limit] if args.limit else instances
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    metadata = {
        "schema_version": 1,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "executable": sys.executable,
        "platform": sys.platform,
        "source_commit": ESICUP_COMMIT,
        "jerry_commit": JERRY_COMMIT,
        "py3dbp_version": "1.1.2",
        "timeout_seconds_per_run": TIMEOUT_SECONDS,
        "memory_limit_bytes_per_worker": MEMORY_LIMIT_BYTES,
        "threads_environment": {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"},
        "orders": ["descending", "ascending"],
        "selected_instances": len(selected),
        "full_campaign": args.limit is None,
        "inventory": source_inventory(instances),
    }
    METADATA.write_text(json.dumps(metadata, indent=2) + "\n")

    total = len(selected) * 2 * 2
    completed_count = 0
    with RECORDS.open("w") as records_handle, STDERR.open("w") as stderr_handle:
        for instance in selected:
            for library in ("py3dbp", "jerry"):
                for order in ("descending", "ascending"):
                    record = run_one(instance, library, order, stderr_handle)
                    records_handle.write(json.dumps(record, separators=(",", ":")) + "\n")
                    records_handle.flush()
                    completed_count += 1
                    if completed_count % 50 == 0 or completed_count == total:
                        print(f"{completed_count}/{total} {record['instance_key']} {library} {order} {record['status']}", flush=True)

    metadata["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    metadata["record_count"] = completed_count
    metadata["records_sha256"] = sha256(RECORDS)
    METADATA.write_text(json.dumps(metadata, indent=2) + "\n")


if __name__ == "__main__":
    main()
