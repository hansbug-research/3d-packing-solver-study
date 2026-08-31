from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from time import perf_counter


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
RAW_DIR = ROOT / "raw" / "experiments" / "campaign" / "python_thpack"
OUTPUT = RAW_DIR / "jerry-fixpoint-diagnostics.jsonl"
CASES = [
    ("THPACK8-001", "descending"),
    ("THPACK8-002", "descending"),
    ("THPACK8-005", "ascending"),
    ("THPACK9-035", "descending"),
]


def main() -> None:
    records: list[dict] = []
    for instance, order in CASES:
        command = [
            sys.executable,
            str(HERE / "worker.py"),
            "--library",
            "jerry",
            "--instance",
            instance,
            "--order",
            order,
            "--jerry-fix-point",
            "false",
        ]
        started = perf_counter()
        completed = subprocess.run(command, text=True, capture_output=True, timeout=60)
        if completed.returncode:
            result = {
                "instance_key": instance,
                "order": order,
                "status": "ERROR",
                "returncode": completed.returncode,
                "stderr": completed.stderr,
            }
        else:
            result = json.loads(completed.stdout)
        result["diagnostic_elapsed_seconds"] = perf_counter() - started
        records.append(result)
        print(instance, order, result["status"], len(result.get("validation_errors", [])), flush=True)
    OUTPUT.write_text("".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records))


if __name__ == "__main__":
    main()
