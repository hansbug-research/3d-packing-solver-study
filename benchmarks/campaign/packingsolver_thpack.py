from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import subprocess
import sys
import tarfile
import tempfile
from collections import Counter
from pathlib import Path
from time import perf_counter
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validation import Box, validate_aabbs


ROTATION_COLUMNS = {
    "XYZ": "ROTATION_XYZ",
    "YXZ": "ROTATION_YXZ",
    "ZYX": "ROTATION_ZYX",
    "YZX": "ROTATION_YZX",
    "XZY": "ROTATION_XZY",
    "ZXY": "ROTATION_ZXY",
}
ROTATION_AXES = {
    "XYZ": (0, 1, 2),
    "YXZ": (1, 0, 2),
    "ZYX": (2, 1, 0),
    "YZX": (1, 2, 0),
    "XZY": (0, 2, 1),
    "ZXY": (2, 0, 1),
}
MALFORMED_THpack9 = {18, 19, 20}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def discover(data_root: Path) -> list[dict[str, Any]]:
    groups = (
        ("BR", "bischoff1995", "knapsack"),
        ("LN", "loh1992", "knapsack"),
        ("IMM", "ivancic1989", "bin-packing"),
    )
    instances: list[dict[str, Any]] = []
    for family, directory, objective in groups:
        for items in (data_root / directory).glob("*_items.csv"):
            stem = items.name.removesuffix("_items.csv")
            bins = items.with_name(f"{stem}_bins.csv")
            if not bins.exists():
                continue
            number = int(stem.rsplit("_", 1)[1])
            source_name = stem.rsplit("_", 1)[0]
            instance_id = f"{family}:{source_name}:{number:03d}"
            malformed = family == "IMM" and number in MALFORMED_THpack9
            instances.append({
                "instance_id": instance_id,
                "family": family,
                "number": number,
                "objective": objective,
                "items": items,
                "bins": bins,
                "source_status": "MALFORMED_SOURCE_EXCLUDED" if malformed else "VALID",
            })
    return sorted(instances, key=lambda row: (row["family"], row["instance_id"]))


def parse_time_file(path: Path) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if not path.exists():
        return values
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if line.startswith("Elapsed (wall clock) time"):
            values["process_elapsed_text"] = line.rsplit(": ", 1)[-1]
        elif line.startswith("Maximum resident set size"):
            values["max_rss_kib"] = int(line.rsplit(": ", 1)[-1])
        elif line.startswith("User time"):
            values["user_time_s"] = float(line.rsplit(": ", 1)[-1])
        elif line.startswith("System time"):
            values["system_time_s"] = float(line.rsplit(": ", 1)[-1])
    return values


def validate_certificate(
    items_path: Path,
    bins_path: Path,
    certificate_path: Path,
    expected_packed: int,
    require_complete: bool,
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    item_specs = {row["ID"]: row for row in read_csv(items_path)}
    bin_specs = {row["ID"]: row for row in read_csv(bins_path)}
    available_bin_volume = sum(
        float(row["X"]) * float(row["Y"]) * float(row["Z"]) * int(row.get("COPIES") or 1)
        for row in bin_specs.values()
    )
    rows = read_csv(certificate_path)
    bin_rows = [row for row in rows if row["TYPE"] == "BIN"]
    item_rows = [row for row in rows if row["TYPE"] == "ITEM"]
    physical_bins: dict[str, list[str]] = {}
    bin_sizes: dict[str, tuple[float, float, float]] = {}
    bin_volume = 0.0
    for index, row in enumerate(bin_rows):
        copies = int(row["COPIES"])
        pattern = row["BIN"]
        ids = [f"pattern-{pattern}-row-{index}-copy-{copy}" for copy in range(copies)]
        physical_bins[pattern] = ids
        for ref in ids:
            bin_sizes[ref] = (float(row["LX"]), float(row["LY"]), float(row["LZ"]))
            bin_volume += float(row["LX"]) * float(row["LY"]) * float(row["LZ"])
        spec = bin_specs.get(row["ID"])
        if spec is None:
            errors.append(f"unknown bin type {row['ID']}")
        elif tuple(float(spec[axis]) for axis in ("X", "Y", "Z")) != tuple(float(row[axis]) for axis in ("LX", "LY", "LZ")):
            errors.append(f"bin {row['ID']} dimensions differ from input")

    placements: list[Box] = []
    counts: Counter[str] = Counter()
    packed_volume = 0.0
    for row_index, row in enumerate(item_rows):
        spec = item_specs.get(row["ID"])
        if spec is None:
            errors.append(f"unknown item type {row['ID']}")
            continue
        pattern_bins = physical_bins.get(row["BIN"], [])
        copies = int(row["COPIES"])
        if copies != len(pattern_bins):
            errors.append(
                f"item row {row_index} copies {copies} differ from physical pattern copies {len(pattern_bins)}"
            )
            continue
        rotation = row["ROTATION"]
        rotation_column = ROTATION_COLUMNS.get(rotation)
        if rotation_column is None or spec.get(rotation_column) != "1":
            errors.append(f"item {row['ID']} uses forbidden rotation {rotation}")
        original = tuple(float(spec[axis]) for axis in ("X", "Y", "Z"))
        expected_dimensions = (
            tuple(original[axis] for axis in ROTATION_AXES[rotation])
            if rotation in ROTATION_AXES
            else None
        )
        certificate_dimensions = tuple(float(row[axis]) for axis in ("LX", "LY", "LZ"))
        if expected_dimensions is None or certificate_dimensions != expected_dimensions:
            errors.append(
                f"item {row['ID']} dimensions {certificate_dimensions} do not match rotation {rotation}"
            )
        for copy, bin_ref in enumerate(pattern_bins):
            counts[row["ID"]] += 1
            packed_volume += original[0] * original[1] * original[2]
            placements.append(Box(
                f"{row['ID']}:{row_index}:{copy}",
                bin_ref,
                float(row["X"]),
                float(row["Y"]),
                float(row["Z"]),
                float(row["LX"]),
                float(row["LY"]),
                float(row["LZ"]),
            ))
    errors.extend(validate_aabbs(placements, bin_sizes))
    available = {item_id: int(spec["COPIES"]) for item_id, spec in item_specs.items()}
    for item_id, count in counts.items():
        if count > available[item_id]:
            errors.append(f"item type {item_id} placed {count}, available {available[item_id]}")
    if len(placements) != expected_packed:
        errors.append(f"certificate has {len(placements)} placements, solver reports {expected_packed}")
    required = sum(available.values())
    if require_complete and len(placements) != required:
        errors.append(f"required {required} items, certificate has {len(placements)}")
    return errors, {
        "certificate_rows": len(rows),
        "physical_bins": len(bin_sizes),
        "placements": len(placements),
        "required_items": required,
        "packed_volume": packed_volume,
        "bin_volume": bin_volume,
        "available_bin_volume": available_bin_volume,
    }


def apply_solver_artifacts(
    record: dict[str, Any],
    instance: dict[str, Any],
    output: Path,
    certificate: Path,
) -> dict[str, Any]:
    solver_output = json.loads(output.read_text())
    final = solver_output["Output"]
    solution = final["Solution"]
    packed = int(solution["NumberOfItems"])
    errors, certificate_metrics = validate_certificate(
        instance["items"],
        instance["bins"],
        certificate,
        packed,
        instance["objective"] == "bin-packing",
    )
    bins_used = int(solution["NumberOfBins"])
    if bins_used != certificate_metrics["physical_bins"]:
        errors.append(
            f"solver reports {bins_used} bins, certificate has {certificate_metrics['physical_bins']}"
        )
    reported_item_volume = float(solution["ItemVolume"])
    if reported_item_volume != certificate_metrics["packed_volume"]:
        errors.append(
            f"solver item volume {reported_item_volume} differs from certificate {certificate_metrics['packed_volume']}"
        )
    reported_bin_volume = float(solution["BinVolume"])
    if reported_bin_volume != certificate_metrics["bin_volume"]:
        errors.append(
            f"solver bin volume {reported_bin_volume} differs from certificate {certificate_metrics['bin_volume']}"
        )
    if instance["objective"] == "knapsack":
        primal = float(solution["ItemProfit"])
        bound = float(final["KnapsackBound"]) if final["KnapsackBound"] is not None else None
        if primal != certificate_metrics["packed_volume"]:
            errors.append(
                f"solver item profit {primal} differs from independently summed THPACK volume {certificate_metrics['packed_volume']}"
            )
        gap = (bound - primal) / bound if bound and bound > 0 else None
    else:
        primal = float(solution["NumberOfBins"])
        bound = float(final["BinPackingBound"])
        gap = (primal - bound) / primal if primal > 0 else None
    bound_closed = not errors and gap is not None and abs(gap) <= 1e-12
    record.update({
        "status": "VALID" if not errors else "INVALID",
        "solver_time_s": float(final["Time"]),
        "primal": primal,
        "solver_reported_bound": bound,
        "relative_gap_to_solver_reported_bound": gap,
        "proof_status": "SOLVER_REPORTED_BOUND_CLOSED" if bound_closed else "FEASIBLE",
        "packed_items": packed,
        "unpacked_items": int(solution["NumberOfUnpackedItems"]),
        "bins_used": bins_used,
        "packed_volume": certificate_metrics["packed_volume"],
        "bin_volume": certificate_metrics["bin_volume"],
        "volume_utilization": (
            certificate_metrics["packed_volume"]
            / (
                certificate_metrics["available_bin_volume"]
                if instance["objective"] == "knapsack"
                else certificate_metrics["bin_volume"]
            )
            if (
                certificate_metrics["available_bin_volume"]
                if instance["objective"] == "knapsack"
                else certificate_metrics["bin_volume"]
            )
            else None
        ),
        "certificate": certificate_metrics,
        "validation_errors": errors,
    })
    return record


def run_instance(
    instance: dict[str, Any],
    binary: Path,
    time_limit: float,
    work_dir: Path,
    extra_args: tuple[str, ...] = (),
    infinite_bin_copies: bool = True,
) -> tuple[dict[str, Any], dict[str, Path]]:
    safe_id = instance["instance_id"].replace(":", "_").replace(".", "_")
    case_dir = work_dir / safe_id
    case_dir.mkdir()
    output = case_dir / "output.json"
    certificate = case_dir / "certificate.csv"
    stdout_path = case_dir / "stdout.txt"
    stderr_path = case_dir / "stderr.txt"
    resource_path = case_dir / "resources.txt"
    command = [
        "/usr/bin/time", "-v", "-o", str(resource_path),
        str(binary),
        "--items", str(instance["items"]),
        "--bins", str(instance["bins"]),
        "--objective", instance["objective"],
        "--time-limit", str(time_limit),
        "--memory-limit", "1024",
        "--verbosity-level", "0",
        "--only-write-at-the-end",
        "--output", str(output),
        "--certificate", str(certificate),
    ]
    if instance["objective"] == "bin-packing" and infinite_bin_copies:
        command.append("--bin-infinite-copies")
    command.extend(extra_args)
    started = perf_counter()
    completed = subprocess.run(command, text=True, capture_output=True, timeout=max(35.0, time_limit + 10.0))
    wall_time = perf_counter() - started
    stdout_path.write_text(completed.stdout)
    stderr_path.write_text(completed.stderr)
    record: dict[str, Any] = {
        "schema_version": 1,
        "instance_id": instance["instance_id"],
        "family": instance["family"],
        "number": instance["number"],
        "source_status": instance["source_status"],
        "objective_kind": instance["objective"],
        "command": command,
        "input_sha256": {
            "items": sha256(instance["items"]),
            "bins": sha256(instance["bins"]),
        },
        "returncode": completed.returncode,
        "wall_time_s": wall_time,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        **parse_time_file(resource_path),
    }
    if completed.returncode != 0 or not output.exists() or not certificate.exists():
        record.update({
            "status": "ERROR",
            "validation_errors": ["missing solver output or certificate"],
        })
        return record, {
            "output": output,
            "certificate": certificate,
            "stdout": stdout_path,
            "stderr": stderr_path,
            "resources": resource_path,
        }
    apply_solver_artifacts(record, instance, output, certificate)
    return record, {
        "output": output,
        "certificate": certificate,
        "stdout": stdout_path,
        "stderr": stderr_path,
        "resources": resource_path,
    }


def write_summary(records: list[dict[str, Any]], path: Path, metadata: dict[str, Any]) -> None:
    by_family: dict[str, Any] = {}
    for family in ("BR", "LN", "IMM"):
        selected = [record for record in records if record["family"] == family]
        valid_source = [record for record in selected if record["source_status"] == "VALID"]
        accepted = [record for record in valid_source if record["status"] == "VALID"]
        by_family[family] = {
            "instances": len(selected),
            "source_valid": len(valid_source),
            "validated": len(accepted),
            "errors": sum(record["status"] == "ERROR" for record in valid_source),
            "invalid_certificates": sum(record["status"] == "INVALID" for record in valid_source),
            "objective_kind": selected[0]["objective_kind"] if selected else None,
            "primary_metric": "packed_volume" if family in {"BR", "LN"} else "bins_used",
            "solver_reported_bound_closed": sum(record.get("proof_status") == "SOLVER_REPORTED_BOUND_CLOSED" for record in accepted),
            "mean_relative_gap_to_solver_reported_bound": sum(record["relative_gap_to_solver_reported_bound"] for record in accepted if record.get("relative_gap_to_solver_reported_bound") is not None) / max(1, sum(record.get("relative_gap_to_solver_reported_bound") is not None for record in accepted)),
            "mean_volume_utilization": sum(record["volume_utilization"] for record in accepted if record.get("volume_utilization") is not None) / max(1, sum(record.get("volume_utilization") is not None for record in accepted)) if family in {"BR", "LN"} else None,
            "mean_bins_used": sum(record["bins_used"] for record in accepted) / max(1, len(accepted)) if family == "IMM" else None,
            "mean_wall_time_s": sum(record["wall_time_s"] for record in valid_source) / max(1, len(valid_source)),
            "max_rss_kib": max((record.get("max_rss_kib", 0) for record in valid_source), default=0),
        }
    path.write_text(json.dumps({**metadata, "families": by_family}, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--time-limit", type=float, default=1.0)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    args.results_dir.mkdir(parents=True, exist_ok=True)
    args.raw_dir.mkdir(parents=True, exist_ok=True)
    instances = discover(args.data_root)
    if args.limit is not None:
        instances = instances[: args.limit]
    metadata = {
        "schema_version": 1,
        "campaign": "packingsolver-thpack/1",
        "engine": "HansBug/packingsolver",
        "source_commit": args.source_commit,
        "binary_sha256": sha256(args.binary),
        "parameters": {
            "time_limit_s": args.time_limit,
            "memory_limit_mib": 1024,
            "thread_limit": "NOT_EXPOSED_BY_CLI",
            "blas_openmp_environment_threads": 1,
        },
        "instances": len(instances),
    }
    records: list[dict[str, Any]] = []
    result_jsonl = args.results_dir / "packingsolver-thpack.jsonl"
    archive_path = args.raw_dir / "packingsolver-thpack-artifacts.tar.gz"
    with tempfile.TemporaryDirectory(prefix="packingsolver-thpack-", dir=args.data_root.parents[2]) as temporary:
        work_dir = Path(temporary)
        with result_jsonl.open("w") as result_handle:
            for index, instance in enumerate(instances, start=1):
                if instance["source_status"] == "MALFORMED_SOURCE_EXCLUDED":
                    record = {
                        "schema_version": 1,
                        "instance_id": instance["instance_id"],
                        "family": instance["family"],
                        "number": instance["number"],
                        "source_status": instance["source_status"],
                        "objective_kind": instance["objective"],
                        "status": "MALFORMED_SOURCE_EXCLUDED",
                        "proof_status": None,
                        "validation_errors": [],
                    }
                else:
                    record, _ = run_instance(instance, args.binary, args.time_limit, work_dir)
                records.append(record)
                result_handle.write(json.dumps(record, separators=(",", ":")) + "\n")
                result_handle.flush()
                if index % 25 == 0 or index == len(instances):
                    print(f"packingsolver-thpack {index}/{len(instances)}", file=sys.stderr, flush=True)
        with tarfile.open(archive_path, "w:gz") as archive:
            for path in sorted(work_dir.rglob("*")):
                if path.is_file():
                    archive.add(path, arcname=path.relative_to(work_dir))
    summary_path = args.results_dir / "packingsolver-thpack-summary.json"
    write_summary(records, summary_path, metadata)
    with gzip.open(args.raw_dir / "packingsolver-thpack-records.jsonl.gz", "wt") as handle:
        for record in records:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
