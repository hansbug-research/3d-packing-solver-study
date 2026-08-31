#!/usr/bin/env python3
"""Run py3dbp and Jerry on the explicit all-rotations projection of B01/B02.

The public BR/LN records retain their source vertical flags.  This runner is a
separate projection track: it deliberately relaxes those flags, invokes the
pinned library worker, and validates the resulting geometry against the same
relaxed canonical semantics.  It never replaces native/source-semantic rows.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks" / "campaign" / "python_thpack"))
from model import ESICUP_COMMIT, parse_all  # noqa: E402

sys.path.insert(0, str(ROOT / "benchmarks"))
from comprehensive.model import canonical_json, validate_run_record  # noqa: E402

WORKER = ROOT / "benchmarks" / "campaign" / "python_thpack" / "worker.py"
WORKER_PYTHON = ROOT / ".venv" / "bin" / "python"
SOURCE_ROOT = ROOT / ".cache" / "esicup-datasets"
SOURCE_DIR = SOURCE_ROOT / "3d_rectangular" / "thpack"
RAW_ROOT = ROOT / "raw" / "experiments" / "comprehensive" / "B01-B02-python-projection"
RESULTS_ROOT = ROOT / "results" / "comprehensive" / "runs"
VALIDATOR = ROOT / "benchmarks" / "campaign" / "python_thpack" / "model.py"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def payload_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def parse_peak_rss(path: Path) -> int | None:
    if not path.exists():
        return None
    for line in path.read_text(errors="replace").splitlines():
        if line.startswith("Maximum resident set size"):
            try:
                return int(line.rsplit(": ", 1)[-1]) * 1024
            except ValueError:
                return None
    return None


def as_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def run_one(
    instance: Any,
    library: str,
    order: str,
    timeout_s: float,
    repetition: int,
    benchmark_id_override: str | None = None,
    source_instance_id_override: str | None = None,
    source_group: str | None = None,
    source_commit_override: str | None = None,
    source_items_sha256: str | None = None,
    source_bins_sha256: str | None = None,
    work_root: Path | None = None,
    archive_name: str | None = None,
    adapter_override: str | None = None,
    source_root_override: Path | None = None,
    jerry_fix_point: bool = True,
) -> dict[str, Any]:
    benchmark_id = benchmark_id_override or ("B01" if int(instance.family.removeprefix("THPACK")) <= 7 else "B02")
    effective_instance_id = source_instance_id_override or instance.key
    case_name = f"{effective_instance_id}/{library}/{order}/{timeout_s:g}s/rep-{repetition}"
    case_dir = (
        work_root / case_name.replace("/", "__")
        if work_root is not None
        else RAW_ROOT / instance.key / library / order / f"{timeout_s:g}s" / f"rep-{repetition}"
    )
    case_dir.mkdir(parents=True, exist_ok=True)
    input_payload = {
        "benchmark_id": benchmark_id,
        "problem_variant": "RELAXED_ALL_ROTATIONS",
        "instance": instance.to_dict(),
        "projection": {"removed_constraints": ["source_vertical_flags"], "allowed_orientations": "all_axis_permutations"},
        "source_commit": source_commit_override or ESICUP_COMMIT,
    }
    input_hash = payload_hash(input_payload)
    (case_dir / "input.json").write_text(canonical_json(input_payload), encoding="utf-8")
    interpreter = str(WORKER_PYTHON if WORKER_PYTHON.is_file() else Path(sys.executable))
    command = [interpreter, str(WORKER), "--library", library]
    if source_instance_id_override is None:
        command.extend(["--instance", instance.key])
    else:
        command.extend(["--input", str(case_dir / "input.json")])
    command.extend(["--order", order, "--projection"])
    if library == "jerry":
        command.extend(["--jerry-fix-point", "true" if jerry_fix_point else "false"])
    config = {
        "command": command,
        "benchmark_id": benchmark_id,
        "problem_variant": "RELAXED_ALL_ROTATIONS",
        "instance_id": effective_instance_id,
        "implementation_id": library,
        "implementation_version": "1.1.2" if library == "py3dbp" else "75764a2b8a5c8e0a6713a4f672c0a8ff81b1107a",
        "source_commit": source_commit_override or ESICUP_COMMIT,
        "python_executable": interpreter,
        "source_root": str(source_root_override or SOURCE_ROOT),
        "input_sha256": input_hash,
        "projection_removed_constraints": ["source_vertical_flags"],
        "time_limit_s": timeout_s,
        "memory_limit_bytes": 2147483648,
        "thread_limit": 1,
        "worker_sha256": sha256(WORKER),
        "validator_sha256": sha256(VALIDATOR),
    }
    if source_instance_id_override is None:
        config["source_sha256"] = sha256(SOURCE_DIR / f"thpack{int(instance.family.removeprefix('THPACK'))}.txt")
    if source_items_sha256 is not None:
        config["source_items_sha256"] = source_items_sha256
    if source_bins_sha256 is not None:
        config["source_bins_sha256"] = source_bins_sha256
    (case_dir / "effective-config.json").write_text(canonical_json(config), encoding="utf-8")
    environment = os.environ.copy()
    environment.update({name: "1" for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")})
    environment["PYTHONHASHSEED"] = "0"
    resource_path = case_dir / "resources.txt"
    timed_command = [
        "/usr/bin/time", "-v", "-o", str(resource_path),
        "timeout", "--signal=TERM", "--kill-after=1s", str(timeout_s), *command,
    ]
    started = perf_counter()
    try:
        completed = subprocess.run(timed_command, capture_output=True, text=True, timeout=timeout_s + 3, env=environment)
        timed_out = completed.returncode in {124, 137, -15, -9}
        run_status = "TIME_LIMIT" if timed_out else "COMPLETED" if completed.returncode == 0 else "ERROR"
        termination = "TIME_LIMIT" if timed_out else "RETURNED_CERTIFICATE" if completed.returncode == 0 else "PROCESS_ERROR"
        stdout = as_text(completed.stdout)
        stderr = as_text(completed.stderr)
        return_code = completed.returncode
    except subprocess.TimeoutExpired as exc:
        run_status = "TIME_LIMIT"
        termination = "TIME_LIMIT"
        stdout = as_text(exc.stdout)
        stderr = as_text(exc.stderr)
        return_code = None
    wall_s = perf_counter() - started
    (case_dir / "stdout.json").write_text(stdout, encoding="utf-8")
    (case_dir / "stderr.log").write_text(stderr, encoding="utf-8")
    try:
        worker = json.loads(stdout)
    except json.JSONDecodeError as exc:
        worker = {"status": "ERROR", "validation_errors": [f"invalid worker JSON: {exc}"]}
    validation_errors = list(worker.get("validation_errors", []))
    solution = worker.get("status")
    if solution == "FEASIBLE_COMPLETE":
        solution_status = "VALID_COMPLETE" if not validation_errors else "INVALID_CERTIFICATE"
    elif solution == "FEASIBLE_PARTIAL":
        solution_status = "VALID_PARTIAL" if not validation_errors else "INVALID_CERTIFICATE"
    elif run_status == "TIME_LIMIT":
        solution_status = "NO_SOLUTION"
    else:
        solution_status = "INVALID_CERTIFICATE" if validation_errors else "NO_SOLUTION"
    metrics = {
        "packed_items": worker.get("packed_items"),
        "unpacked_items": worker.get("unpacked_items"),
        "packed_volume": worker.get("packed_volume"),
        "volume_utilization": worker.get("volume_utilization"),
        "bins_used": worker.get("bins_used"),
        "validation_error_count": len(validation_errors),
        "projection_removed_constraints": ["source_vertical_flags"],
        "process_returncode": return_code,
    }
    validation = {"status": "PASS" if solution_status in {"VALID_COMPLETE", "VALID_PARTIAL"} else "FAIL", "errors": validation_errors, **metrics}
    (case_dir / "validation.json").write_text(canonical_json(validation), encoding="utf-8")
    peak_rss_bytes = parse_peak_rss(resource_path)
    record = {
        "schema_version": 2,
        "protocol_version": "benchmark-protocol/3",
        "record_origin": "PROTOCOL_V3",
        "run_id": f"{benchmark_id}/{effective_instance_id}/{library}/{'projection' if jerry_fix_point else 'projection-nofix'}/{order}/{timeout_s:g}s/rep-{repetition}",
        "benchmark_id": benchmark_id,
        "problem_variant": "RELAXED_ALL_ROTATIONS",
        "instance_id": effective_instance_id,
        "implementation_id": library,
        "algorithm": "pivot greedy",
        "adapter": adapter_override or "thpack_python_projection_v1",
        "comparison_track": "COMPOSED",
        "problem_scope": "GEOMETRY_PROJECTION",
        "budget": {"time_limit_s": timeout_s, "memory_limit_bytes": 2147483648, "thread_limit": 1},
        "item_order": order.upper(),
        "bin_order": "SOURCE",
        "seed": None,
        "repetition": repetition,
        "input_sha256": input_hash,
        "input_status": "VALID",
        "capability_status": "PROJECTION_ONLY",
        "run_status": run_status,
        "solution_status": solution_status,
        "proof_status": "FEASIBLE" if solution_status in {"VALID_COMPLETE", "VALID_PARTIAL"} else "UNKNOWN",
        "termination_reason": termination,
        "resources": {"wall_s": wall_s, "solver_s": worker.get("solve_seconds"), "peak_rss_bytes": peak_rss_bytes},
        "metrics": metrics,
        "artifacts": {},
    }
    if archive_name is None:
        record["artifacts"] = {
            "input": str((case_dir / "input.json").relative_to(ROOT)),
            "effective_config": str((case_dir / "effective-config.json").relative_to(ROOT)),
            "solver_output": str((case_dir / "stdout.json").relative_to(ROOT)),
            "stderr": str((case_dir / "stderr.log").relative_to(ROOT)),
            "validation": str((case_dir / "validation.json").relative_to(ROOT)),
        }
    else:
        record["artifacts"] = {
            "input": f"{archive_name}#{case_dir.name}/input.json",
            "effective_config": f"{archive_name}#{case_dir.name}/effective-config.json",
            "solver_output": f"{archive_name}#{case_dir.name}/stdout.json",
            "stderr": f"{archive_name}#{case_dir.name}/stderr.log",
            "validation": f"{archive_name}#{case_dir.name}/validation.json",
        }
    if source_group is not None:
        record["metrics"]["source_group"] = source_group
    if source_items_sha256 is not None:
        record["metrics"]["source_items_sha256"] = source_items_sha256
    if source_bins_sha256 is not None:
        record["metrics"]["source_bins_sha256"] = source_bins_sha256
    if library == "jerry":
        record["metrics"]["jerry_fix_point"] = jerry_fix_point
    validate_run_record(record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--time-limit", type=float, action="append")
    parser.add_argument("--library", choices=("py3dbp", "jerry"), action="append")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--repetition", type=int, default=0)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if subprocess.check_output(["git", "-C", str(SOURCE_ROOT), "rev-parse", "HEAD"], text=True).strip() != ESICUP_COMMIT:
        raise SystemExit("ESICUP checkout is not at the pinned commit")
    instances = [instance for instance in parse_all(SOURCE_DIR) if instance.family in {f"THPACK{i}" for i in range(1, 9)}]
    if args.limit:
        instances = instances[: args.limit]
    libraries = args.library or ["py3dbp", "jerry"]
    time_limits = args.time_limit or [10.0]
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    if args.workers < 1:
        raise SystemExit("--workers must be positive")
    records: list[dict[str, Any]] = []
    total = len(instances) * len(libraries) * len(time_limits) * 2
    done = 0
    jobs = [
        (instance, library, order, timeout_s)
        for timeout_s in time_limits
        for instance in instances
        for library in libraries
        for order in ("descending", "ascending")
    ]
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(run_one, instance, library, order, timeout_s, args.repetition) for instance, library, order, timeout_s in jobs]
        for future in as_completed(futures):
            records.append(future.result())
            done += 1
            if done % 100 == 0 or done == total:
                print(f"{done}/{total}", flush=True)
    records.sort(key=lambda record: record["run_id"])
    budget_label = "-".join(f"{value:g}s" for value in time_limits)
    library_label = "-".join(libraries)
    out = RESULTS_ROOT / f"B01-B02-python-projection-{library_label}-{budget_label}-rep-{args.repetition}.jsonl"
    out.write_text("".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records), encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
