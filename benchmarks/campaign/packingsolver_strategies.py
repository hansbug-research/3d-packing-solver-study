from __future__ import annotations

import argparse
import json
import tarfile
import tempfile
from pathlib import Path
from typing import Any

from packingsolver_thpack import run_instance, sha256


ALL_FLAGS = (
    "use-tree-search",
    "use-tree-search-maximal-spaces",
    "use-sequential-single-knapsack",
    "use-sequential-value-correction",
    "use-column-generation",
)


def strategy_args(enabled: str | None) -> tuple[str, ...]:
    if enabled is None:
        return ()
    values: list[str] = []
    for flag in ALL_FLAGS:
        values.extend((f"--{flag}", "true" if flag == enabled else "false"))
    if enabled == "use-column-generation":
        values.extend(("--linear-programming-solver", "highs"))
    return tuple(values)


def case(
    instance_id: str,
    family: str,
    number: int,
    objective: str,
    stem: Path,
) -> dict[str, Any]:
    return {
        "instance_id": instance_id,
        "family": family,
        "number": number,
        "objective": objective,
        "items": stem.with_name(f"{stem.name}_items.csv"),
        "bins": stem.with_name(f"{stem.name}_bins.csv"),
        "source_status": "VALID",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--time-limit", type=float, default=10.0)
    args = parser.parse_args()
    args.results_dir.mkdir(parents=True, exist_ok=True)
    args.raw_dir.mkdir(parents=True, exist_ok=True)

    cases = (
        case("BR:BR1.txt:001", "BR", 1, "knapsack", args.data_root / "bischoff1995" / "BR1.txt_1"),
        case("LN:thpack8.txt:001", "LN", 1, "knapsack", args.data_root / "loh1992" / "thpack8.txt_1"),
        case("IMM:thpack9.txt:001", "IMM", 1, "bin-packing", args.data_root / "ivancic1989" / "thpack9.txt_1"),
        case("IMM:thpack9.txt:047", "IMM", 47, "bin-packing", args.data_root / "ivancic1989" / "thpack9.txt_47"),
    )
    single_bin_strategies = (
        ("auto", None),
        ("tree_search", "use-tree-search"),
        ("maximal_spaces", "use-tree-search-maximal-spaces"),
    )
    multi_bin_strategies = (
        ("auto", None),
        ("tree_search", "use-tree-search"),
        ("sequential_single_knapsack", "use-sequential-single-knapsack"),
        ("sequential_value_correction", "use-sequential-value-correction"),
        ("column_generation", "use-column-generation"),
    )
    records: list[dict[str, Any]] = []
    archive_path = args.raw_dir / "artifacts.tar.gz"
    with tempfile.TemporaryDirectory(prefix="packingsolver-strategies-") as temporary:
        work_dir = Path(temporary)
        for selected_case in cases:
            strategies = single_bin_strategies if selected_case["objective"] == "knapsack" else multi_bin_strategies
            for strategy, enabled in strategies:
                strategy_case = dict(selected_case)
                strategy_case["instance_id"] = f"{selected_case['instance_id']}:{strategy}"
                record, _ = run_instance(
                    strategy_case,
                    args.binary,
                    args.time_limit,
                    work_dir,
                    strategy_args(enabled),
                )
                record["base_instance_id"] = selected_case["instance_id"]
                record["strategy"] = strategy
                record["engine_source_commit"] = args.source_commit
                record["engine_binary_sha256"] = sha256(args.binary)
                records.append(record)
                print(f"{selected_case['instance_id']} {strategy} {record['status']}", flush=True)
        with tarfile.open(archive_path, "w:gz") as archive:
            for path in sorted(work_dir.rglob("*")):
                if path.is_file():
                    archive.add(path, arcname=path.relative_to(work_dir))

    output = {
        "schema_version": 1,
        "campaign": "packingsolver-strategy-sensitivity/1",
        "source_commit": args.source_commit,
        "binary_sha256": sha256(args.binary),
        "parameters": {
            "time_limit_s": args.time_limit,
            "memory_limit_mib": 1024,
            "thread_limit": "NOT_EXPOSED_BY_CLI",
            "blas_openmp_environment_threads": 1,
        },
        "harness_sha256": {
            "strategy_runner": sha256(Path(__file__)),
            "certificate_validator": sha256(Path(__file__).with_name("packingsolver_thpack.py")),
        },
        "records": records,
    }
    (args.results_dir / "packingsolver-strategies.json").write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    main()
